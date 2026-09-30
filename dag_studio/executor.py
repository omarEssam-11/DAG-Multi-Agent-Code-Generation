"""DAG executor: runs tasks with dependency-aware parallel scheduling."""
from __future__ import annotations

import asyncio
import time
from typing import Any

from .agents import AgentRuntime
from .config import settings
from .dag import DAG, Task
from .events import EventBus
from .llm import LLMClient


class DAGExecutor:
    """Executes a DAG: independent tasks run concurrently, dependents wait.

    The graph is dynamic — tasks injected at runtime (via the add_task tool)
    are picked up by the scheduler on the next wave.
    """

    def __init__(self, dag: DAG, bus: EventBus, llm: LLMClient, mode: str) -> None:
        self.dag = dag
        self.bus = bus
        self.llm = llm
        self.mode = mode
        self.semaphore = asyncio.Semaphore(settings.max_concurrency)
        self._running = 0

    async def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        await self.bus.publish({"type": event_type, "data": data})

    async def run(self) -> None:
        started = time.time()
        await self._emit("run_started", {"query": self.dag.query, "tasks": len(self.dag.tasks)})

        while not self.dag.is_complete():
            ready = self.dag.ready_tasks()
            if not ready:
                if self._running == 0:
                    break  # nothing left that can run (failures cascade to skipped)
                await asyncio.sleep(0.15)
                continue
            batch = ready[: settings.max_concurrency]
            results = await asyncio.gather(
                *(self._run_one(task) for task in batch), return_exceptions=True
            )
            for task, result in zip(batch, results):
                if isinstance(result, Exception) and task.status == "running":
                    task.status = "failed"
                    task.error = str(result)
                    await self._emit("task_status", {"task_id": task.id, "status": "failed"})

        await self._emit("run_finished", self._summary(started))

    async def _run_one(self, task: Task) -> None:
        async with self.semaphore:
            self._running += 1
            try:
                runtime = AgentRuntime(self.dag, self.bus, self.llm, self.mode)
                await runtime.run(task)
            finally:
                self._running -= 1
            if task.status == "failed":
                self._cascade_skip(task)

    def _cascade_skip(self, failed: Task) -> None:
        """When a task fails, its dependents can never run — mark them skipped."""
        for task in self.dag.tasks.values():
            if task.status == "pending" and failed.id in task.depends_on:
                task.status = "skipped"
                task.error = f"dependency '{failed.id}' failed"

    def _summary(self, started: float) -> dict[str, Any]:
        tasks = list(self.dag.tasks.values())
        done = [t for t in tasks if t.status == "done"]
        failed = [t for t in tasks if t.status == "failed"]
        skipped = [t for t in tasks if t.status == "skipped"]
        return {
            "query": self.dag.query,
            "duration_s": round(time.time() - started, 1),
            "total": len(tasks),
            "done": len(done),
            "failed": len(failed),
            "skipped": len(skipped),
            "tasks": [
                {"id": t.id, "title": t.title, "status": t.status, "persona": t.persona}
                for t in tasks
            ],
        }
