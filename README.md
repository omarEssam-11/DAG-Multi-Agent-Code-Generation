# ⚡ Dynamic DAG Multi-Agent Code Generation Studio

An autonomous, multi-agent AI system for advanced code generation. The studio
decomposes a complex user request into an optimal **Directed Acyclic Graph (DAG)**
of subtasks, spawns **specialized agents on-the-fly** with custom personas and
toolsets, and executes independent tasks **concurrently in parallel** while
respecting dependency order — all visualized live in the web UI.

![mode](https://img.shields.io/badge/mode-demo%20%7C%20live-6366f1)

## Features

- **Dynamic planning & decomposition** — a planner agent breaks the request into a
  DAG of 3–8 specialized tasks (architect → engineers → QA → security → docs).
- **Async parallel DAG execution** — tasks in the same topological wave run
  concurrently (semaphore-bounded); dependents wait for their inputs.
- **Dynamic graph mutation** — agents can inject new tasks into the *running* DAG
  via the `add_task` tool (watch QA file a fix task mid-run).
- **Specialized personas** — architect, frontend, backend, QA, security, DevOps,
  docs, reviewer — each with its own system prompt and toolset.
- **Real tool use** — read/write/edit files, search, run commands, HTTP; all
  sandboxed to a workspace directory.
- **Live UI** — animated SVG DAG with pan/zoom, streaming per-node logs, agent
  cards, event terminal, artifact browser and run summary.
- **Two modes** — `demo` (no API key: simulated agents that still write real
  artifacts) and `live` (any OpenAI-compatible chat-completions endpoint).

## Quick start

```bash
py -m pip install -r requirements.txt
py run.py            # → http://127.0.0.1:8000
```

Then open http://127.0.0.1:8000, type a request (or click an example), and press
**▶ Generate with DAG**.

## Enabling live mode

```bash
copy .env.example .env
# edit .env → OPENAI_API_KEY=sk-...   (any OpenAI-compatible API works)
py run.py
```

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | enables live mode when set |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | chat-completions endpoint |
| `MODEL` | `gpt-4o-mini` | model used for planning + agents |
| `MAX_CONCURRENCY` | `4` | max parallel agent executions |
| `AGENT_MAX_STEPS` | `8` | max ReAct iterations per agent |
| `PORT` | `8000` | HTTP port |

## Architecture

```
ui/                     web UI (vanilla JS + SVG DAG renderer)
dag_studio/
├── main.py             FastAPI app: REST + WebSocket event stream + static UI
├── config.py           env-driven settings
├── events.py           async pub/sub event bus
├── dag.py              DAG model: validation, topological levels, snapshots
├── planner.py          planner agent (LLM JSON planning + fallback)
├── agents.py           agent runtime (ReAct loop with tool calls)
├── executor.py         dependency-aware parallel DAG scheduler
├── demo.py             built-in planner + simulated agents (real artifacts)
├── llm.py              OpenAI-compatible client (chat + tool calls)
├── personas.py         persona definitions (prompt + toolset + color)
└── tools.py            tool registry (fs, search, shell, http, add_task)
workspace/              generated artifacts land here
```

### Execution model

1. `POST /api/run` → planner builds the DAG → `dag` event streamed to all UIs.
2. Executor loops: `ready_tasks()` (pending + deps done) → run wave concurrently
   via `asyncio.gather` under a semaphore → repeat until the graph is terminal.
3. Failures cascade: dependents of a failed task are marked `skipped`.
4. Tasks added at runtime (`add_task`) join the next wave automatically.
5. Every status change, log line and output is streamed over `/ws`.

### Event protocol (WebSocket `/ws`)

`snapshot` · `dag` · `agent_spawned` · `task_status` · `task_log` ·
`task_output` · `run_started` · `run_finished` · `run_aborted` · `warning`

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/state` | full studio snapshot (mode, DAG, personas) |
| `POST` | `/api/run` | `{query}` — plan + execute (409 if busy) |
| `POST` | `/api/stop` | cancel the running job |
| `GET` | `/api/artifacts` | list files written to the workspace |
| `GET` | `/api/file?path=` | read one artifact |
| `WS` | `/ws` | live event stream |

## Safety

- All file tools resolve inside `workspace/` (traversal blocked).
- `run_command` is time-limited and filtered against a blocklist
  (`rm -rf`, `mkfs`, fork bombs, disk overwrites, …).
- `http_get` is restricted to `http(s)://` URLs.
