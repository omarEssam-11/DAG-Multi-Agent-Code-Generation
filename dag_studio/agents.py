"""Agent runtime: executes one task as a persona, live (LLM ReAct) or simulated."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from . import demo
from .config import settings
from .dag import DAG, Task
from .events import EventBus
from .llm import LLMClient
from .personas import get_persona
from .tools import ToolContext, execute_tool, tool_schemas


class AgentRuntime:
    def __init__(self, dag: DAG, bus: EventBus, llm: LLMClient, mode: str) -> None:
        self.dag = dag
        self.bus = bus
        self.llm = llm
        self.mode = mode
        self.workspace = settings.workspace_dir

    # ------------------------------------------------------------------ events
    async def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        await self.bus.publish({"type": event_type, "data": data})

    async def _log(self, task: Task, line: str) -> None:
        task.logs.append(line)
        await self._emit("task_log", {"task_id": task.id, "line": line})

    # -------------------------------------------------------------------- run
    async def run(self, task: Task) -> None:
        persona = get_persona(task.persona)
        task.status = "running"
        task.started_at = time.time()
        task.agent_name = persona.title
        await self._emit("agent_spawned", {
            "task_id": task.id,
            "persona": persona.name,
            "title": persona.title,
            "icon": persona.icon,
            "color": persona.color,
        })
        await self._emit("task_status", {"task_id": task.id, "status": "running"})

        ctx = ToolContext(workspace=self.workspace, dag=self.dag, bus=self.bus)
        try:
            if self.mode == "demo":
                await demo.demo_agent_run(task, ctx, self._emit)
            else:
                await self._run_live(task, persona, ctx)
            task.status = "done"
        except asyncio.CancelledError:
            task.status = "skipped"
            task.error = "cancelled"
            raise
        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)
            await self._log(task, f"❌ Agent failed: {exc}")
        finally:
            task.finished_at = time.time()
            await self._emit("task_status", {"task_id": task.id, "status": task.status})
            if task.status == "done":
                await self._emit("task_output", {"task_id": task.id, "output": task.output})

    # -------------------------------------------------------------- live mode
    async def _run_live(self, task: Task, persona, ctx: ToolContext) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": persona.system_prompt},
            {"role": "user", "content": self._task_prompt(task)},
        ]
        tools = tool_schemas(persona.tools)

        for step in range(settings.agent_max_steps):
            await self._log(task, f"🧠 {persona.title} thinking… (step {step + 1})")
            text, tool_calls = await self.llm.complete(messages, tools=tools)
            if not tool_calls:
                task.output = text.strip() or "(no summary produced)"
                return

            assistant_msg: dict[str, Any] = {"role": "assistant", "content": text or ""}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            messages.append(assistant_msg)

            for call in tool_calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                await self._log(task, f"🔧 {name}({json.dumps(args, default=str)[:120]})")
                try:
                    result = await execute_tool(name, args, ctx)
                except Exception as exc:
                    result = f"ERROR: {exc}"
                await self._log(task, f"   → {result[:300].replace(chr(10), ' | ')}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": result[:4000],
                })

        task.output = f"Reached step limit ({settings.agent_max_steps}). Last message: {text[:500]}"

    def _task_prompt(self, task: Task) -> str:
        upstream = []
        for dep_id in task.depends_on:
            dep = self.dag.get(dep_id)
            if dep and dep.output:
                upstream.append(f"### Completed: {dep.title}\n{dep.output[:1500]}")
        upstream_block = "\n\n".join(upstream) if upstream else "(none — this is a root task)"
        return (
            f"Original user request:\n{self.dag.query}\n\n"
            f"Your task: {task.title}\n{task.description}\n\n"
            f"Workspace: {self.workspace} (all file tools are relative to it)\n"
            f"Available tools: {', '.join(task.tools)}\n\n"
            f"Upstream completed work:\n{upstream_block}\n\n"
            f"Do the work with the tools. When finished, reply with a concise summary "
            f"of what you did and which files you wrote."
        )
