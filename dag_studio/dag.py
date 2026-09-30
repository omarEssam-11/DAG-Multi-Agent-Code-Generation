"""DAG data model: tasks, dependency validation and topological levelling."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Literal

Status = Literal["pending", "running", "done", "failed", "skipped"]
TERMINAL_STATUSES = ("done", "failed", "skipped")


@dataclass
class Task:
    id: str
    title: str
    description: str = ""
    persona: str = "general"
    tools: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    status: Status = "pending"
    output: str = ""
    error: str = ""
    logs: list[str] = field(default_factory=list)
    agent_name: str = ""
    started_at: float | None = None
    finished_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "persona": self.persona,
            "tools": self.tools,
            "depends_on": list(self.depends_on),
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "logs": list(self.logs),
            "agent_name": self.agent_name,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class DAG:
    """A directed acyclic graph of tasks with dynamic (runtime) mutation support."""

    def __init__(self, query: str = "") -> None:
        self.query = query
        self.tasks: dict[str, Task] = {}
        self.created_at = time.time()
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ tasks
    def add_task(self, task: Task) -> Task:
        if task.id in self.tasks:
            raise ValueError(f"duplicate task id: {task.id}")
        self.tasks[task.id] = task
        return task

    def get(self, task_id: str) -> Task | None:
        return self.tasks.get(task_id)

    # -------------------------------------------------------------- validation
    def validate(self) -> None:
        """Raise ValueError on missing dependencies or cycles."""
        for task in self.tasks.values():
            for dep in task.depends_on:
                if dep not in self.tasks:
                    raise ValueError(f"task '{task.id}' depends on unknown task '{dep}'")
        # DFS cycle detection (white=0 / gray=1 / black=2)
        color: dict[str, int] = {tid: 0 for tid in self.tasks}

        def visit(tid: str) -> None:
            color[tid] = 1
            for dep in self.tasks[tid].depends_on:
                if color[dep] == 1:
                    raise ValueError(f"cycle detected involving task '{dep}'")
                if color[dep] == 0:
                    visit(dep)
            color[tid] = 2

        for tid in self.tasks:
            if color[tid] == 0:
                visit(tid)

    # ----------------------------------------------------------------- levels
    def levels(self) -> list[list[str]]:
        """Group task ids into topological levels (longest-path levelling).

        Tasks in the same level have no inter-dependencies and can run in parallel.
        """
        level_of: dict[str, int] = {}

        def level(tid: str, seen: set[str] | None = None) -> int:
            if tid in level_of:
                return level_of[tid]
            seen = seen or set()
            if tid in seen:  # pragma: no cover - validate() guards this
                return 0
            seen.add(tid)
            deps = self.tasks[tid].depends_on
            lvl = 0 if not deps else max(level(d, seen) for d in deps) + 1
            level_of[tid] = lvl
            return lvl

        for tid in self.tasks:
            level(tid)
        max_level = max(level_of.values(), default=-1)
        result: list[list[str]] = [[] for _ in range(max_level + 1)]
        for tid, lvl in level_of.items():
            result[lvl].append(tid)
        for ids in result:
            ids.sort()
        return result

    def ready_tasks(self) -> list[Task]:
        """Pending tasks whose dependencies are all satisfied."""
        ready = []
        for task in self.tasks.values():
            if task.status != "pending":
                continue
            if all(self.tasks[d].status == "done" for d in task.depends_on):
                ready.append(task)
        return ready

    def is_complete(self) -> bool:
        return all(t.status in TERMINAL_STATUSES for t in self.tasks.values())

    # --------------------------------------------------------------- snapshot
    def snapshot(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "created_at": self.created_at,
            "tasks": {tid: t.to_dict() for tid, t in self.tasks.items()},
            "levels": self.levels(),
        }
