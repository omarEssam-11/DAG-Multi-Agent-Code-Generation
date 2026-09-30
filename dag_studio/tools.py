"""Tool registry: the capabilities agents can use, executed inside a workspace."""
from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx

from .dag import Task
from .events import EventBus

# Commands that are never executed, whatever the agent asks.
_BLOCKED_COMMAND_PATTERNS = [
    r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)\b",
    r"\bmkfs\b",
    r"\bformat\b",
    r">\s*/dev/sd[a-z]",
    r"\bdd\b.*\bof=/dev/",
    r":\(\)\{.*\};",  # fork bomb
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bdel\s+/[sq]\b",
    r"\brd\s+/[sq]\b",
]


@dataclass
class ToolContext:
    """Runtime context handed to every tool call."""
    workspace: Path
    dag: Any = None  # dag_studio.dag.DAG, injected by the executor
    bus: EventBus | None = None  # event bus, for tools that emit events


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[dict[str, Any], ToolContext], Awaitable[str]]


# --------------------------------------------------------------------- helpers
def _safe_path(workspace: Path, raw: str) -> Path:
    """Resolve a user-supplied path inside the workspace, blocking traversal."""
    raw = (raw or "").strip().strip('"').strip("'")
    if not raw:
        raise ValueError("path must not be empty")
    candidate = Path(raw)
    if candidate.is_absolute():
        # Allow absolute paths that live inside the workspace only.
        candidate = Path(os.path.normpath(str(candidate)))
        workspace_resolved = Path(os.path.normpath(str(workspace)))
        if workspace_resolved not in candidate.parents and candidate != workspace_resolved:
            raise ValueError(f"absolute path outside workspace: {raw}")
    resolved = Path(os.path.normpath(str(workspace / candidate)))
    workspace_resolved = Path(os.path.normpath(str(workspace)))
    if workspace_resolved not in resolved.parents and resolved != workspace_resolved:
        raise ValueError(f"path escapes workspace: {raw}")
    return resolved


async def _read_text(path: Path, offset: int = 0, limit: int = 2000) -> str:
    if not path.exists():
        raise FileNotFoundError(f"no such file: {path.name}")
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if offset or limit:
        lines = lines[offset : offset + limit]
    return "\n".join(lines)


# --------------------------------------------------------------------- handlers
async def h_read_file(args: dict, ctx: ToolContext) -> str:
    path = _safe_path(ctx.workspace, args.get("path", ""))
    offset = int(args.get("offset", 0) or 0)
    limit = int(args.get("limit", 2000) or 2000)
    content = await _read_text(path, offset, limit)
    return f"--- {path.name} ({offset}:{offset + limit}) ---\n{content}"


async def h_write_file(args: dict, ctx: ToolContext) -> str:
    path = _safe_path(ctx.workspace, args.get("path", ""))
    content = args.get("content", "")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"wrote {path.name} ({len(content)} chars)"


async def h_edit_file(args: dict, ctx: ToolContext) -> str:
    path = _safe_path(ctx.workspace, args.get("path", ""))
    old = args.get("old_string", "")
    new = args.get("new_string", "")
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise ValueError(f"old_string not found in {path.name}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return f"edited {path.name}"


async def h_list_dir(args: dict, ctx: ToolContext) -> str:
    path = _safe_path(ctx.workspace, args.get("path", "."))
    if not path.is_dir():
        raise FileNotFoundError(f"no such directory: {path.name}")
    entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
    lines = []
    for p in entries:
        if p.name.startswith(".") and p.name != ".":
            continue
        kind = "dir " if p.is_dir() else "file"
        size = p.stat().st_size if p.is_file() else "-"
        lines.append(f"{kind} {p.name} ({size})")
    return "\n".join(lines) or "(empty)"


async def h_search_files(args: dict, ctx: ToolContext) -> str:
    pattern = args.get("pattern", "")
    root = _safe_path(ctx.workspace, args.get("path", "."))
    regex = re.compile(pattern)
    matches: list[str] = []
    for p in root.rglob("*"):
        if p.is_file() and ".git" not in p.parts:
            try:
                for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if regex.search(line):
                        matches.append(f"{p.relative_to(ctx.workspace)}:{i}: {line.strip()}")
            except OSError:
                continue
        if len(matches) >= 50:
            matches.append("... (truncated at 50 matches)")
            break
    return "\n".join(matches) or "(no matches)"


async def h_run_command(args: dict, ctx: ToolContext) -> str:
    command = (args.get("command") or "").strip()
    if not command:
        raise ValueError("command must not be empty")
    for pattern in _BLOCKED_COMMAND_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            raise ValueError(f"blocked by safety policy: {command}")
    timeout = min(max(float(args.get("timeout", 30) or 30), 1), 120)
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(ctx.workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as exc:
        raise ValueError(f"failed to launch command: {exc}") from exc
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        proc.kill()
        raise ValueError(f"command timed out after {timeout}s: {command}") from exc
    output = stdout.decode("utf-8", errors="replace").strip()
    tail = output[-4000:] if len(output) > 4000 else output
    return f"$ {command}\n(exit {proc.returncode})\n{tail}"


async def h_add_task(args: dict, ctx: ToolContext) -> str:
    """Dynamically inject a new task into the running DAG (the 'dynamic' in Dynamic DAG)."""
    if ctx.dag is None:
        raise ValueError("add_task is not available in this context")
    title = (args.get("title") or "").strip()
    if not title:
        raise ValueError("title must not be empty")
    task_id = args.get("id") or "fix-" + str(len(ctx.dag.tasks) + 1)
    task = Task(
        id=str(task_id),
        title=title,
        description=args.get("description", ""),
        persona=args.get("persona", "general"),
        tools=list(args.get("tools", [])),
        depends_on=[str(d) for d in args.get("depends_on", [])],
    )
    ctx.dag.add_task(task)
    if ctx.bus is not None:
        await ctx.bus.publish({"type": "dag", "data": ctx.dag.snapshot()})
    return f"added task '{task.id}' ({title}) — the DAG has been updated dynamically"


async def h_http_get(args: dict, ctx: ToolContext) -> str:
    url = (args.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("url must start with http:// or https://")
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.get(url)
        body = resp.text[:8000]
        return f"HTTP {resp.status_code} {url}\n{body}"


# --------------------------------------------------------------------- registry
TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool("read_file", "Read a file from the workspace (optionally a line range).",
             {"type": "object", "properties": {
                 "path": {"type": "string", "description": "file path relative to workspace"},
                 "offset": {"type": "integer"}, "limit": {"type": "integer"}},
              "required": ["path"]}, h_read_file),
        Tool("write_file", "Create or overwrite a file in the workspace.",
             {"type": "object", "properties": {
                 "path": {"type": "string"},
                 "content": {"type": "string"}},
              "required": ["path", "content"]}, h_write_file),
        Tool("edit_file", "Replace the first occurrence of old_string with new_string in a file.",
             {"type": "object", "properties": {
                 "path": {"type": "string"},
                 "old_string": {"type": "string"},
                 "new_string": {"type": "string"}},
              "required": ["path", "old_string", "new_string"]}, h_edit_file),
        Tool("list_dir", "List the contents of a directory in the workspace.",
             {"type": "object", "properties": {"path": {"type": "string"}}, "required": []}, h_list_dir),
        Tool("search_files", "Search file contents with a regular expression.",
             {"type": "object", "properties": {
                 "pattern": {"type": "string"},
                 "path": {"type": "string"}},
              "required": ["pattern"]}, h_search_files),
        Tool("run_command", "Run a shell command inside the workspace (time-limited, safety-filtered).",
             {"type": "object", "properties": {
                 "command": {"type": "string"},
                 "timeout": {"type": "number"}},
              "required": ["command"]}, h_run_command),
        Tool("add_task", "Inject a new task into the running DAG at runtime. Use when the work "
             "reveals follow-up work that must be tracked and executed.",
             {"type": "object", "properties": {
                 "id": {"type": "string", "description": "unique task id, e.g. fix-1"},
                 "title": {"type": "string"},
                 "description": {"type": "string"},
                 "persona": {"type": "string", "description": "persona name, e.g. backend"},
                 "tools": {"type": "array", "items": {"type": "string"}},
                 "depends_on": {"type": "array", "items": {"type": "string"}}},
              "required": ["title"]}, h_add_task),
        Tool("http_get", "Fetch a URL and return the response body (truncated).",
             {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}, h_http_get),
    ]
}


def tool_schemas(names: list[str]) -> list[dict[str, Any]]:
    schemas = []
    for name in names:
        tool = TOOLS.get(name)
        if tool:
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })
    return schemas


async def execute_tool(name: str, args: dict, ctx: ToolContext) -> str:
    tool = TOOLS.get(name)
    if not tool:
        raise ValueError(f"unknown tool: {name}")
    return await tool.handler(args or {}, ctx)
