"""Demo-mode brains: a heuristic planner and simulated agents.

These produce a realistic DAG and stream believable progress while writing
real artifact files into the workspace, so the studio is fully functional
without an API key.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Awaitable, Callable

from .dag import DAG, Task
from .personas import get_persona
from .tools import ToolContext, execute_tool

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]


# --------------------------------------------------------------------- helpers
def _extract_name(query: str) -> str:
    m = re.search(r"(?:build|create|make|develop|design)\s+(?:a|an|the)?\s*([a-z0-9]+(?:\s+[a-z0-9]+)?)", query.lower())
    words = (m.group(1) if m else "app").split()[:2]
    return "".join(w.capitalize() for w in words) or "App"


def _extract_features(query: str) -> list[str]:
    found = []
    feature_keywords = {
        "auth": ["auth", "login", "signin", "sign in", "user account"],
        "search": ["search", "find", "query"],
        "filter": ["filter", "sort", "categor"],
        "export": ["export", "csv", "download", "report"],
        "dark mode": ["dark mode", "dark theme", "night mode"],
        "realtime": ["realtime", "real-time", "live", "websocket", "instant"],
        "upload": ["upload", "file", "image", "attachment"],
        "charts": ["chart", "graph", "dashboard", "analytics", "visuali"],
        "map": ["map", "location", "geo"],
        "payment": ["payment", "checkout", "stripe", "billing"],
        "notifications": ["notification", "alert", "email", "remind"],
        "database": ["database", "sqlite", "postgres", "persist", "storage"],
        "pagination": ["pagination", "paginate", "infinite scroll"],
    }
    q = query.lower()
    for feature, keywords in feature_keywords.items():
        if any(k in q for k in keywords):
            found.append(feature)
    return found[:6]


def _kb(text: str) -> str:
    return f"{len(text.encode('utf-8')) / 1024:.1f} KB"


# --------------------------------------------------------------------- planner
def demo_plan(query: str) -> DAG:
    q = query.lower()
    if any(k in q for k in ("api", "rest", "backend", "server", "fastapi", "endpoint")):
        return _backend_pipeline(query)
    if any(k in q for k in ("data", "ml", "model", "train", "predict", "analys", "pipeline", "dataset")):
        return _data_pipeline(query)
    return _web_pipeline(query)


def _web_pipeline(query: str) -> DAG:
    name = _extract_name(query)
    dag = DAG(query)
    dag.add_task(Task(
        id="arch", title="Design system architecture",
        description=f"Produce a design document for {name}: component breakdown, data flow, tech choices.",
        persona="architect", tools=["read_file", "list_dir", "search_files", "write_file"], depends_on=[]))
    dag.add_task(Task(
        id="frontend", title="Build the user interface",
        description=f"Implement the {name} frontend: structure, styling and interactivity.",
        persona="frontend", tools=["read_file", "write_file", "edit_file", "list_dir", "run_command"],
        depends_on=["arch"]))
    dag.add_task(Task(
        id="backend", title="Implement the backend API",
        description=f"Implement the {name} backend: models, routes, persistence and validation.",
        persona="backend", tools=["read_file", "write_file", "edit_file", "list_dir", "run_command"],
        depends_on=["arch"]))
    dag.add_task(Task(
        id="qa", title="Write and run tests",
        description="Write automated tests, run the suite, and file fix tasks for any defects found.",
        persona="qa", tools=["read_file", "run_command", "search_files", "add_task"],
        depends_on=["frontend", "backend"]))
    dag.add_task(Task(
        id="security", title="Security audit",
        description="Audit the implementation for vulnerabilities and document findings.",
        persona="security", tools=["read_file", "search_files", "add_task"],
        depends_on=["frontend", "backend"]))
    dag.add_task(Task(
        id="docs", title="Write documentation",
        description="Write the README and usage documentation for the project.",
        persona="docs", tools=["read_file", "write_file", "list_dir"],
        depends_on=["qa", "security"]))
    return dag


def _backend_pipeline(query: str) -> DAG:
    name = _extract_name(query)
    dag = DAG(query)
    dag.add_task(Task(
        id="arch", title="Design API architecture",
        description=f"Design the {name} API: endpoints, data models, validation and error handling.",
        persona="architect", tools=["read_file", "list_dir", "search_files", "write_file"], depends_on=[]))
    dag.add_task(Task(
        id="backend", title="Implement API and data layer",
        description=f"Implement the {name} FastAPI application, models and persistence.",
        persona="backend", tools=["read_file", "write_file", "edit_file", "list_dir", "run_command"],
        depends_on=["arch"]))
    dag.add_task(Task(
        id="qa", title="Write and run API tests",
        description="Write endpoint tests, run them, and file fix tasks for defects.",
        persona="qa", tools=["read_file", "run_command", "search_files", "add_task"],
        depends_on=["backend"]))
    dag.add_task(Task(
        id="security", title="Security audit",
        description="Audit for injection, auth and input-validation issues.",
        persona="security", tools=["read_file", "search_files", "add_task"],
        depends_on=["backend"]))
    dag.add_task(Task(
        id="devops", title="Package and containerize",
        description="Add dependency manifest, Dockerfile and run instructions.",
        persona="devops", tools=["read_file", "write_file", "run_command", "list_dir"],
        depends_on=["qa", "security"]))
    dag.add_task(Task(
        id="docs", title="Write API documentation",
        description="Document endpoints, request/response schemas and examples.",
        persona="docs", tools=["read_file", "write_file", "list_dir"],
        depends_on=["devops"]))
    return dag


def _data_pipeline(query: str) -> DAG:
    name = _extract_name(query)
    dag = DAG(query)
    dag.add_task(Task(
        id="arch", title="Design pipeline architecture",
        description=f"Design the {name} data pipeline: ingestion, features, training, evaluation.",
        persona="architect", tools=["read_file", "list_dir", "search_files", "write_file"], depends_on=[]))
    dag.add_task(Task(
        id="backend", title="Implement pipeline and model",
        description=f"Implement data loading, feature engineering, model and training loop for {name}.",
        persona="backend", tools=["read_file", "write_file", "edit_file", "list_dir", "run_command"],
        depends_on=["arch"]))
    dag.add_task(Task(
        id="qa", title="Validate model and tests",
        description="Write tests for data and model code, run them, file fix tasks for defects.",
        persona="qa", tools=["read_file", "run_command", "search_files", "add_task"],
        depends_on=["backend"]))
    dag.add_task(Task(
        id="docs", title="Write documentation",
        description="Document the pipeline, metrics and how to retrain.",
        persona="docs", tools=["read_file", "write_file", "list_dir"],
        depends_on=["qa"]))
    return dag


# --------------------------------------------------------------------- agents
async def demo_agent_run(task: Task, ctx: ToolContext, emit: Emit) -> None:
    """Simulate an agent working on a task: stream logs, write real files."""
    persona = get_persona(task.persona)
    await emit("task_log", {"task_id": task.id,
                            "line": f"{persona.icon} {persona.title} spawned — tools: {', '.join(task.tools)}"})
    await asyncio.sleep(0.3)

    for path, content in _file_plan(task, ctx):
        await emit("task_log", {"task_id": task.id,
                                "line": f"📄 Writing {path} ({_kb(content)}) …"})
        await execute_tool("write_file", {"path": path, "content": content}, ctx)
        await asyncio.sleep(0.35)

    await _persona_extras(task, ctx, emit)
    await emit("task_output", {"task_id": task.id, "output": _output_summary(task, ctx)})


async def _persona_extras(task: Task, ctx: ToolContext, emit: Emit) -> None:
    if task.persona == "qa":
        await emit("task_log", {"task_id": task.id, "line": "🧪 Running the test suite …"})
        try:
            result = await execute_tool("run_command", {"command": "python -m pytest -q --tb=short", "timeout": 60}, ctx)
            for line in result.splitlines()[-8:]:
                await emit("task_log", {"task_id": task.id, "line": f"   {line}"})
        except Exception as exc:
            await emit("task_log", {"task_id": task.id, "line": f"   ⚠️ {exc}"})
            await emit("task_log", {"task_id": task.id,
                                    "line": "   (pytest unavailable — simulating a green suite)"})
            for line in ["test_app.py ..", "test_server.py ....", "5 passed in 0.42s"]:
                await emit("task_log", {"task_id": task.id, "line": f"   {line}"})
                await asyncio.sleep(0.2)
        # The dynamic DAG twist: QA files a fix task that joins the graph at runtime.
        await emit("task_log", {"task_id": task.id,
                                "line": "🔎 Reviewing coverage gaps — filing a follow-up fix task …"})
        await execute_tool("add_task", {
            "id": "fix-1",
            "title": "Harden input validation found in QA",
            "description": "QA found missing edge-case validation. Tighten request validation and add regression tests.",
            "persona": "backend",
            "tools": ["read_file", "write_file", "edit_file", "run_command"],
            "depends_on": [task.id],
        }, ctx)
        await emit("task_log", {"task_id": task.id,
                                "line": "➕ Dynamically injected task 'fix-1' into the running DAG"})

    elif task.persona == "security":
        for pattern in ["password", "secret", "eval\\(", "exec\\(", "SELECT \\*"]:
            await emit("task_log", {"task_id": task.id, "line": f"🔍 grep -rn '{pattern}' …"})
            try:
                result = await execute_tool("search_files", {"pattern": pattern}, ctx)
                hits = [l for l in result.splitlines() if l and not l.startswith("(")]
                await emit("task_log", {"task_id": task.id,
                                        "line": f"   {len(hits)} hit(s)" + (f" — e.g. {hits[0][:80]}" if hits else "")})
            except Exception:
                pass
            await asyncio.sleep(0.25)


def _output_summary(task: Task, ctx: ToolContext) -> str:
    persona = get_persona(task.persona)
    files = [p for p, _ in _file_plan(task, ctx)]
    lines = [f"{persona.title} completed '{task.title}'.", ""]
    if files:
        lines.append("Files written:")
        lines += [f"  • {p}" for p in files]
    if task.persona == "qa":
        lines += ["", "Test suite: 5 passed. One follow-up fix task was filed dynamically."]
    if task.persona == "security":
        lines += ["", "Audit complete: no critical findings; recommendations documented."]
    return "\n".join(lines)


# ----------------------------------------------------------------- file plans
def _file_plan(task: Task, ctx: ToolContext) -> list[tuple[str, str]]:
    """The files a simulated agent writes, based on its persona and the DAG query."""
    query = ctx.dag.query if ctx.dag else ""
    name = _extract_name(query)
    features = _extract_features(query)
    kind = _pipeline_kind(query)

    if task.persona == "architect":
        return [("docs/architecture.md", _arch_doc(name, features, kind))]
    if task.persona == "frontend":
        return [("index.html", _index_html(name, features)),
                ("styles.css", _styles_css(name)),
                ("app.js", _app_js(name, features))]
    if task.persona == "backend":
        if kind == "backend":
            return [("main.py", _server_main(name)), ("models.py", _server_models(name)),
                    ("database.py", _server_db()), ("routers/items.py", _server_router(name))]
        if kind == "data":
            return [("data.py", _data_py(name)), ("model.py", _model_py(name)),
                    ("train.py", _train_py(name)), ("evaluate.py", _evaluate_py(name))]
        return [("server.py", _server_main(name)), ("database.py", _server_db())]
    if task.persona == "qa":
        if kind == "data":
            return [("tests/test_model.py", _test_model(name))]
        return [("tests/test_app.py", _test_app(name))]
    if task.persona == "security":
        return [("docs/security-review.md", _security_doc(name))]
    if task.persona == "devops":
        return [("requirements.txt", _requirements(name)), ("Dockerfile", _dockerfile(name))]
    if task.persona == "docs":
        return [("README.md", _readme(name, features, kind))]
    if task.id.startswith("fix-"):
        return [("validators.py", _validators_py(name))]
    return [("notes.md", f"# {task.title}\n\nNotes from {get_persona(task.persona).title}.\n")]


def _pipeline_kind(query: str) -> str:
    q = query.lower()
    if any(k in q for k in ("api", "rest", "backend", "server", "fastapi", "endpoint")):
        return "backend"
    if any(k in q for k in ("data", "ml", "model", "train", "predict", "analys", "pipeline", "dataset")):
        return "data"
    return "web"


# ------------------------------------------------------- artifact generators
def _arch_doc(name: str, features: list[str], kind: str) -> str:
    feat = ", ".join(features) if features else "core CRUD flows"
    return f"""# {name} — Architecture

## Overview
{name} is a {kind}-style application generated by the DAG Multi-Agent Studio.
Target features: {feat}.

## Components
- **Presentation layer** — renders state, handles user input, talks to the API.
- **Application layer** — routes, validation, business rules.
- **Data layer** — persistence with a repository interface so the store can be swapped.

## Data flow
User input → controller validation → domain logic → repository → store.
Responses are validated at the boundary; errors are returned as structured messages.

## Design decisions
- Small, single-responsibility modules with explicit interfaces.
- Validation at system boundaries, trust internally.
- State kept on the client; the server remains stateless and restartable.
- Tests at every layer, runnable with a single command.

## Risks / trade-offs
- In-memory storage is simple but not durable across restarts (swap the repository).
- Client-side rendering keeps the backend small; SEO is out of scope.
"""


def _index_html(name: str, features: list[str]) -> str:
    feat = ", ".join(features) if features else "core flows"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{name}</title>
  <link rel="stylesheet" href="styles.css" />
</head>
<body>
  <header class="app-header">
    <h1>{name}</h1>
    <p class="tagline">Generated by the DAG Multi-Agent Studio — features: {feat}</p>
  </header>
  <main>
    <section class="composer">
      <input id="new-item" type="text" placeholder="Add a new item and press Enter" autofocus />
      <button id="add-btn" type="button">Add</button>
    </section>
    <ul id="item-list" class="item-list" aria-live="polite"></ul>
    <p id="empty-state" class="empty-state">No items yet — add your first one above.</p>
  </main>
  <script src="app.js"></script>
</body>
</html>
"""


def _styles_css(name: str) -> str:
    return f"""/* {name} — generated styles */
:root {{
  --bg: #0f172a; --panel: #1e293b; --text: #e2e8f0; --muted: #94a3b8;
  --accent: #6366f1; --accent-2: #22d3ee; --danger: #ef4444; --ok: #10b981;
  --radius: 12px;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; font-family: "Segoe UI", system-ui, sans-serif;
  background: radial-gradient(1200px 600px at 80% -10%, #1e1b4b, var(--bg));
  color: var(--text); min-height: 100vh;
}}
.app-header {{ padding: 48px 24px 8px; text-align: center; }}
.app-header h1 {{
  margin: 0; font-size: 2.4rem; letter-spacing: -0.02em;
  background: linear-gradient(90deg, var(--accent), var(--accent-2));
  -webkit-background-clip: text; background-clip: text; color: transparent;
}}
.tagline {{ color: var(--muted); }}
main {{ max-width: 640px; margin: 24px auto; padding: 0 16px 64px; }}
.composer {{ display: flex; gap: 8px; margin-bottom: 16px; }}
.composer input {{
  flex: 1; padding: 12px 14px; border-radius: var(--radius);
  border: 1px solid #334155; background: var(--panel); color: var(--text); font-size: 1rem;
}}
.composer button, .item-list button {{
  padding: 12px 18px; border: 0; border-radius: var(--radius); cursor: pointer;
  background: linear-gradient(90deg, var(--accent), var(--accent-2)); color: white; font-weight: 600;
}}
.item-list {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }}
.item-list li {{
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  background: var(--panel); border: 1px solid #334155; border-radius: var(--radius); padding: 12px 14px;
}}
.item-list li.done span {{ text-decoration: line-through; color: var(--muted); }}
.item-list li button {{ background: transparent; color: var(--danger); padding: 4px 8px; }}
.empty-state {{ color: var(--muted); text-align: center; }}
"""


def _app_js(name: str, features: list[str]) -> str:
    persist = "localStorage" if "database" in features else "in-memory"
    persist_note = "in localStorage for durability" if persist == "localStorage" else "in memory for simplicity"
    return f"""// {name} — generated application logic
// State is kept {persist_note}.
(() => {{
  "use strict";
  const STORAGE_KEY = "{name.lower().replace(' ', '-')}-items";
  const list = document.getElementById("item-list");
  const input = document.getElementById("new-item");
  const empty = document.getElementById("empty-state");

  const load = () => {{
    try {{ return JSON.parse(localStorage.getItem(STORAGE_KEY)) || []; }}
    catch {{ return []; }}
  }};
  let items = load();

  const save = () => localStorage.setItem(STORAGE_KEY, JSON.stringify(items));

  function render() {{
    list.innerHTML = "";
    empty.hidden = items.length > 0;
    items.forEach((item, i) => {{
      const li = document.createElement("li");
      if (item.done) li.classList.add("done");
      const span = document.createElement("span");
      span.textContent = item.text;
      span.style.cursor = "pointer";
      span.onclick = () => {{ items[i].done = !items[i].done; save(); render(); }};
      const del = document.createElement("button");
      del.textContent = "✕";
      del.onclick = () => {{ items.splice(i, 1); save(); render(); }};
      li.append(span, del);
      list.appendChild(li);
    }});
  }}

  function add() {{
    const text = input.value.trim();
    if (!text) return;
    items.push({{ text, done: false }});
    input.value = "";
    save(); render();
  }}

  document.getElementById("add-btn").onclick = add;
  input.addEventListener("keydown", (e) => {{ if (e.key === "Enter") add(); }});
  render();
}})();
"""


def _server_main(name: str) -> str:
    return f'''"""{name} — generated FastAPI application."""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from database import get_db
from routers import items

app = FastAPI(title="{name} API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(items.router, prefix="/api/items", tags=["items"])


@app.get("/health")
def health() -> dict:
    return {{"status": "ok"}}


@app.on_event("startup")
def startup() -> None:
    get_db()  # initialize the store
'''


def _server_models(name: str) -> str:
    return f'''"""{name} — request/response models."""
from pydantic import BaseModel, Field


class ItemCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)


class Item(BaseModel):
    id: int
    text: str
    done: bool = False

    class Config:
        orm_mode = True


class ItemUpdate(BaseModel):
    text: str | None = Field(None, min_length=1, max_length=500)
    done: bool | None = None
'''


def _server_db() -> str:
    return '''"""Tiny JSON-file backed store with a repository interface."""
import json
import threading
from pathlib import Path

from models import Item

DB_PATH = Path(__file__).parent / "data.json"
_lock = threading.Lock()
_items: list[dict] = []
_next_id = 1


def _load() -> None:
    global _items, _next_id
    if DB_PATH.exists():
        _items = json.loads(DB_PATH.read_text(encoding="utf-8"))
        _next_id = max((i["id"] for i in _items), default=0) + 1


def _persist() -> None:
    DB_PATH.write_text(json.dumps(_items, indent=2), encoding="utf-8")


def get_db():
    """Initialize and return the repository functions."""
    _load()
    return {
        "list": lambda: [Item(**i) for i in _items],
        "create": _create,
        "update": _update,
        "delete": _delete,
    }


def _create(text: str) -> Item:
    global _next_id
    item = {"id": _next_id, "text": text, "done": False}
    _next_id += 1
    _items.append(item)
    _persist()
    return Item(**item)


def _update(item_id: int, **changes) -> Item | None:
    for entry in _items:
        if entry["id"] == item_id:
            entry.update(changes)
            _persist()
            return Item(**entry)
    return None


def _delete(item_id: int) -> bool:
    global _items
    before = len(_items)
    _items = [i for i in _items if i["id"] != item_id]
    if len(_items) != before:
        _persist()
        return True
    return False
'''


def _server_router(name: str) -> str:
    return f'''"""{name} — item routes."""
from fastapi import APIRouter, HTTPException

from database import get_db
from models import Item, ItemCreate, ItemUpdate

router = APIRouter()


@router.get("", response_model=list[Item])
def list_items() -> list[Item]:
    return get_db()["list"]()


@router.post("", response_model=Item, status_code=201)
def create_item(payload: ItemCreate) -> Item:
    return get_db()["create"](payload.text)


@router.patch("/{{item_id}}", response_model=Item)
def update_item(item_id: int, payload: ItemUpdate) -> Item:
    changes = {{k: v for k, v in payload.dict().items() if v is not None}}
    item = get_db()["update"](item_id, **changes)
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")
    return item


@router.delete("/{{item_id}}", status_code=204)
def delete_item(item_id: int) -> None:
    if not get_db()["delete"](item_id):
        raise HTTPException(status_code=404, detail="item not found")
'''


def _data_py(name: str) -> str:
    return f'''"""{name} — data loading and feature engineering."""
from __future__ import annotations

import csv
import random
from pathlib import Path

random.seed(42)


def load_dataset(path: str | Path | None = None) -> list[dict]:
    """Load the dataset, generating a deterministic demo set when absent."""
    if path and Path(path).exists():
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    return [
        {{"id": i, "value": random.uniform(0, 100), "label": i % 2}}
        for i in range(200)
    ]


def features(row: dict) -> list[float]:
    """Turn a raw row into a numeric feature vector."""
    return [float(row.get("value", 0.0)), float(row.get("id", 0)) % 7 / 7.0]


def split(data: list[dict], test_frac: float = 0.2):
    cut = int(len(data) * (1 - test_frac))
    return data[:cut], data[cut:]
'''


def _model_py(name: str) -> str:
    return f'''"""{name} — a small logistic-style classifier (pure stdlib)."""
from __future__ import annotations

import math
import random


class SimpleClassifier:
    def __init__(self, n_features: int, lr: float = 0.1):
        self.w = [random.uniform(-0.1, 0.1) for _ in range(n_features)]
        self.b = 0.0
        self.lr = lr

    @staticmethod
    def _sigmoid(x: float) -> float:
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))

    def predict_proba(self, x: list[float]) -> float:
        z = sum(wi * xi for wi, xi in zip(self.w, x)) + self.b
        return self._sigmoid(z)

    def fit(self, X: list[list[float]], y: list[int], epochs: int = 50) -> None:
        for _ in range(epochs):
            for xi, yi in zip(X, y):
                err = self.predict_proba(xi) - yi
                for j in range(len(self.w)):
                    self.w[j] -= self.lr * err * xi[j]
                self.b -= self.lr * err

    def accuracy(self, X: list[list[float]], y: list[int]) -> float:
        correct = sum(
            (self.predict_proba(xi) >= 0.5) == bool(yi) for xi, yi in zip(X, y)
        )
        return correct / max(len(y), 1)
'''


def _train_py(name: str) -> str:
    return f'''"""{name} — training entry point."""
from data import features, load_dataset, split
from model import SimpleClassifier


def main() -> None:
    data = load_dataset()
    train, test = split(data)
    X_train = [features(r) for r in train]
    y_train = [int(r["label"]) for r in train]
    X_test = [features(r) for r in test]
    y_test = [int(r["label"]) for r in test]

    clf = SimpleClassifier(n_features=len(X_train[0]))
    clf.fit(X_train, y_train)
    print(f"{{name}}: test accuracy = {{clf.accuracy(X_test, y_test):.2%}}")


if __name__ == "__main__":
    main()
'''


def _evaluate_py(name: str) -> str:
    return f'''"""{name} — evaluation report."""
from data import features, load_dataset, split
from model import SimpleClassifier


def main() -> None:
    data = load_dataset()
    train, test = split(data)
    clf = SimpleClassifier(n_features=2)
    clf.fit([features(r) for r in train], [int(r["label"]) for r in train])
    acc = clf.accuracy([features(r) for r in test], [int(r["label"]) for r in test])
    print(f"accuracy={{acc:.2%}} n_test={{len(test)}} weights={{clf.w}}")


if __name__ == "__main__":
    main()
'''


def _test_app(name: str) -> str:
    return f'''"""Tests for the {name} backend."""
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {{"status": "ok"}}


def test_create_and_list_items():
    resp = client.post("/api/items", json={{"text": "first"}})
    assert resp.status_code == 201
    body = resp.json()
    assert body["text"] == "first"
    assert body["done"] is False

    listed = client.get("/api/items")
    assert listed.status_code == 200
    assert any(i["id"] == body["id"] for i in listed.json())


def test_update_item():
    created = client.post("/api/items", json={{"text": "todo"}}).json()
    resp = client.patch(f"/api/items/{{created['id']}}", json={{"done": True}})
    assert resp.status_code == 200
    assert resp.json()["done"] is True


def test_delete_item():
    created = client.post("/api/items", json={{"text": "bye"}}).json()
    resp = client.delete(f"/api/items/{{created['id']}}")
    assert resp.status_code == 204
    assert all(i["id"] != created["id"] for i in client.get("/api/items").json())


def test_validation_rejects_empty_text():
    resp = client.post("/api/items", json={{"text": ""}})
    assert resp.status_code == 422
'''


def _test_model(name: str) -> str:
    return f'''"""Tests for the {name} data pipeline."""
from data import features, load_dataset, split
from model import SimpleClassifier


def test_dataset_loads():
    data = load_dataset()
    assert len(data) > 0
    assert {{"value", "label"}} <= set(data[0])


def test_features_are_numeric():
    data = load_dataset()
    vec = features(data[0])
    assert len(vec) == 2
    assert all(isinstance(v, float) for v in vec)


def test_split_is_disjoint():
    data = load_dataset()
    train, test = split(data, test_frac=0.25)
    assert len(train) + len(test) == len(data)
    assert not ({{r["id"] for r in train}} & {{r["id"] for r in test}})


def test_model_learns():
    data = load_dataset()
    train, test = split(data)
    clf = SimpleClassifier(n_features=2)
    clf.fit([features(r) for r in train], [int(r["label"]) for r in train])
    assert clf.accuracy([features(r) for r in test], [int(r["label"]) for r in test]) > 0.5
'''


def _security_doc(name: str) -> str:
    return f"""# {name} — Security Review

## Scope
Review of the generated {name} codebase: input validation, dependency surface,
secret handling and API exposure.

## Findings
| Severity | Area | Finding | Remediation |
|----------|------|---------|-------------|
| Low | API | CORS allows all origins in dev | Restrict `allow_origins` in production |
| Low | Storage | Data file writable by the app user | Keep `data.json` outside the web root |
| Info | Dependencies | Pinned in requirements.txt | Enable Dependabot / pip-audit in CI |

## Recommendations
- Validate all request bodies at the API boundary (done via Pydantic models).
- Never commit secrets; use environment variables.
- Add rate limiting before public deployment.
- Run `pip-audit` in CI on every dependency change.

## Verdict
No critical issues. The two low-severity items are acceptable for a local
development build and are documented for production hardening.
"""


def _requirements(name: str) -> str:
    return f"""# {name} — runtime dependencies
fastapi>=0.110
uvicorn>=0.29
pydantic>=2.0
httpx>=0.27

# test dependencies
pytest>=8.0
"""


def _dockerfile(name: str) -> str:
    return f"""FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
"""


def _validators_py(name: str) -> str:
    return f'''"""{name} — hardened validation helpers (fix-1)."""
import re

MAX_TEXT = 500
_TEXT_RE = re.compile(r"^[\\w .,!?\\-'"]{{1,{MAX_TEXT}}}$")


def validate_item_text(text: object) -> str:
    """Return cleaned text or raise ValueError with a precise message."""
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("text must not be empty")
    if len(cleaned) > MAX_TEXT:
        raise ValueError(f"text must be at most {MAX_TEXT} characters")
    if not _TEXT_RE.match(cleaned):
        raise ValueError("text contains unsupported characters")
    return cleaned
'''


def _readme(name: str, features: list[str], kind: str) -> str:
    feat = ", ".join(features) if features else "core flows"
    run_cmd = "uvicorn main:app --reload" if kind in ("backend", "web") else "python train.py"
    test_cmd = "python -m pytest -q"
    return f"""# {name}

Generated end-to-end by the **DAG Multi-Agent Code Generation Studio** — planned as a
DAG of specialized agents (architect → engineers → QA → security → docs) and executed
with parallel, dependency-aware scheduling.

## Features
- {feat}

## Layout
- `docs/architecture.md` — design decisions and data flow
- `docs/security-review.md` — security audit
- `main.py` / `server.py` — application entry point
- `routers/`, `models.py`, `database.py` — API layer
- `tests/` — automated test suite
- `validators.py` — hardened input validation (added by the dynamic fix task)

## Run
```bash
pip install -r requirements.txt
{run_cmd}
```

## Test
```bash
{test_cmd}
```

## How it was built
1. The planner decomposed the request into a task DAG.
2. Independent tasks ran concurrently; dependent tasks waited for their inputs.
3. QA dynamically injected a fix task into the running graph.
4. Every agent wrote real artifacts into this workspace.
"""
