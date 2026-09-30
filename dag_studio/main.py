"""FastAPI application: REST + WebSocket streaming + static UI."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .dag import DAG
from .events import EventBus
from .executor import DAGExecutor
from .llm import LLMClient
from .personas import list_personas
from .planner import plan_dag
from .tools import _safe_path

UI_DIR = Path(__file__).resolve().parent.parent / "ui"

app = FastAPI(title="DAG Multi-Agent Code Generation Studio", version="1.0.0")


class StudioState:
    def __init__(self) -> None:
        self.bus = EventBus()
        self.dag: DAG | None = None
        self.running = False
        self._run_task: asyncio.Task | None = None
        settings.workspace_dir.mkdir(parents=True, exist_ok=True)

    def snapshot(self) -> dict[str, Any]:
        return {
            "mode": settings.mode,
            "model": settings.model,
            "running": self.running,
            "max_concurrency": settings.max_concurrency,
            "personas": list_personas(),
            "dag": self.dag.snapshot() if self.dag else None,
        }


state = StudioState()


# --------------------------------------------------------------------- routes
@app.get("/")
async def index() -> RedirectResponse:
    return RedirectResponse("/ui/")


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    return state.snapshot()


@app.post("/api/run")
async def start_run(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    query = (payload.get("query") or "").strip()
    if not query:
        raise HTTPException(400, "query must not be empty")
    if state.running:
        raise HTTPException(409, "a run is already in progress — stop it first")

    llm = LLMClient()
    dag = await plan_dag(query, llm, settings.mode, state.bus)
    state.dag = dag
    state.running = True
    state._run_task = asyncio.create_task(_execute(dag))
    return {"status": "started", "tasks": len(dag.tasks), "mode": settings.mode}


@app.post("/api/stop")
async def stop_run() -> dict[str, Any]:
    if state._run_task and not state._run_task.done():
        state._run_task.cancel()
        # Mark whatever is still pending as skipped so the UI settles.
        if state.dag:
            for task in state.dag.tasks.values():
                if task.status in ("pending", "running"):
                    task.status = "skipped"
                    task.error = "stopped by user"
        return {"status": "stopped"}
    return {"status": "not_running"}


async def _execute(dag: DAG) -> None:
    try:
        executor = DAGExecutor(dag, state.bus, LLMClient(), settings.mode)
        await executor.run()
    except asyncio.CancelledError:
        pass
    finally:
        state.running = False
        await state.bus.publish({"type": "run_aborted", "data": {"query": dag.query}})


# ------------------------------------------------------------------ artifacts
@app.get("/api/artifacts")
async def list_artifacts() -> list[dict[str, Any]]:
    workspace = settings.workspace_dir
    files = []
    for path in sorted(workspace.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            stat = path.stat()
            files.append({
                "path": str(path.relative_to(workspace)).replace("\\", "/"),
                "size": stat.st_size,
                "modified": stat.st_mtime,
            })
    return files


@app.get("/api/file")
async def read_artifact(path: str) -> dict[str, Any]:
    try:
        safe = _safe_path(settings.workspace_dir, path)
        content = safe.read_text(encoding="utf-8", errors="replace")
    except (ValueError, FileNotFoundError, OSError) as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"path": path, "content": content}


# ------------------------------------------------------------------ websocket
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    await ws.send_json({"type": "snapshot", "data": state.snapshot()})

    async def forward() -> None:
        async for event in state.bus.subscribe():
            await ws.send_json(event)

    forward_task = asyncio.create_task(forward())
    try:
        while True:
            await ws.receive_text()  # client→server channel (reserved for control)
    except WebSocketDisconnect:
        pass
    finally:
        forward_task.cancel()


# --------------------------------------------------------------------- static
app.mount("/ui", StaticFiles(directory=UI_DIR, html=True), name="ui")


@app.on_event("startup")
async def _startup() -> None:
    settings.workspace_dir.mkdir(parents=True, exist_ok=True)
