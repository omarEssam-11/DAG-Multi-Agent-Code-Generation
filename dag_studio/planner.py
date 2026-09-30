"""Planner agent: decomposes a user query into a DAG of specialized tasks."""
from __future__ import annotations

from typing import Any

from . import demo
from .dag import DAG, Task
from .events import EventBus
from .llm import LLMClient
from .personas import PERSONAS
from .tools import TOOLS

_PLANNER_SYSTEM = """You are the planner of a multi-agent software studio.
Decompose the user's request into a DAG of specialized tasks.
Rules:
- 3 to 8 tasks. Each task gets exactly one persona from: {personas}.
- Tasks in the same "wave" must not depend on each other, so they can run in parallel.
- Later tasks may depend on earlier ones (list their ids in depends_on).
- Give each task the tools it needs from: {tools}. Only list tools that exist.
- Descriptions must be concrete and self-contained.
Respond with a single JSON object: {{"tasks": [{{"id", "title", "description", "persona", "tools": [...], "depends_on": [...]}}]}}"""


async def plan_dag(query: str, llm: LLMClient, mode: str, bus: EventBus) -> DAG:
    """Build the task DAG for a query (live LLM planning or built-in demo planner)."""
    if mode == "demo":
        dag = demo.demo_plan(query)
        await bus.publish({"type": "dag", "data": dag.snapshot()})
        return dag

    try:
        dag = await _plan_live(query, llm)
        await bus.publish({"type": "dag", "data": dag.snapshot()})
        return dag
    except Exception as exc:
        await bus.publish({
            "type": "warning",
            "data": {"message": f"Live planner failed ({exc}); falling back to the built-in planner."},
        })
        dag = demo.demo_plan(query)
        await bus.publish({"type": "dag", "data": dag.snapshot()})
        return dag


def _as_id_list(value: Any) -> list[str]:
    """Coerce a planner-provided dependency field into a clean list of ids.

    LLMs sometimes return depends_on as a string ("1, 2" or "[1, 2]") or a
    single scalar instead of a JSON array — handle all of those.
    """
    if value is None:
        return []
    if isinstance(value, str):
        # Strip brackets/quotes, split on commas.
        cleaned = value.strip().strip("[]").replace('"', "").replace("'", "")
        return [part.strip() for part in cleaned.split(",") if part.strip()]
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value).strip()]


def _sanitize_task(raw: dict[str, Any]) -> dict[str, Any]:
    """Clamp planner output to known personas/tools so the DAG stays executable."""
    persona = str(raw.get("persona", "general")).lower()
    if persona not in PERSONAS:
        persona = "general"
    known = PERSONAS[persona].tools
    tools = [t for t in _as_id_list(raw.get("tools", [])) if t in TOOLS]
    tools = [t for t in tools if t in known] or list(known)
    return {
        "id": str(raw.get("id", "")).strip(),
        "title": str(raw.get("title", "Untitled task")).strip(),
        "description": str(raw.get("description", "")).strip(),
        "persona": persona,
        "tools": tools,
        "depends_on": _as_id_list(raw.get("depends_on", [])),
    }


async def _plan_live(query: str, llm: LLMClient) -> DAG:
    system = _PLANNER_SYSTEM.format(
        personas=", ".join(PERSONAS),
        tools=", ".join(TOOLS),
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Request: {query}"},
    ]
    data = await llm.complete_json(messages)
    raw_tasks = data.get("tasks") if isinstance(data, dict) else None
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ValueError("planner returned no tasks")

    dag = DAG(query)
    for raw in raw_tasks:
        task = _sanitize_task(raw)
        if not task["id"] or not task["title"]:
            continue
        dag.add_task(Task(**task))
    if not dag.tasks:
        raise ValueError("planner produced an empty DAG")
    # Drop dependencies on tasks the planner didn't actually emit.
    for task in dag.tasks.values():
        task.depends_on = [d for d in task.depends_on if d in dag.tasks]
    dag.validate()  # raises on cycles
    return dag
