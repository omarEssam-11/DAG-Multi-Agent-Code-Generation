/* DAG Studio — UI client */
"use strict";

// --------------------------------------------------------------------- state
const state = {
  mode: "demo",
  model: "",
  running: false,
  dag: null,            // { query, tasks: {id: task}, levels: [[ids]] }
  selected: null,       // selected task id
  agents: {},           // task_id -> {persona,title,icon,color}
  artifacts: [],
  summary: null,
  zoom: 1, panX: 0, panY: 0,
};

const NODE_W = 190, NODE_H = 64, GAP_X = 90, GAP_Y = 26, MARGIN = 40;
const $ = (id) => document.getElementById(id);

const EXAMPLES = [
  "Build a todo app with dark mode and localStorage persistence",
  "Create a REST API for a blog with validation",
  "Build a data pipeline that trains and evaluates a model",
  "Build a chat app with realtime updates and auth",
];

// ------------------------------------------------------------------ helpers
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function toast(msg, ms = 5000) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), ms);
}

function fmtTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString("en-GB", { hour12: false });
}

// ------------------------------------------------------------------ websocket
function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  state.ws = ws;

  ws.onopen = () => setConn(true);
  ws.onclose = () => {
    setConn(false);
    setTimeout(connect, 1500);
  };
  ws.onerror = () => ws.close();
  ws.onmessage = (e) => {
    try {
      handleEvent(JSON.parse(e.data));
    } catch (err) {
      console.error("bad event", err);
    }
  };
}

function setConn(online) {
  $("conn-dot").className = `conn ${online ? "online" : "offline"}`;
}

function handleEvent(ev) {
  switch (ev.type) {
    case "snapshot": applySnapshot(ev.data); break;
    case "dag": state.dag = ev.data; state.selected = null; renderDAG(); renderNodeDetail(); break;
    case "task_status": onTaskStatus(ev.data); break;
    case "task_log": onTaskLog(ev.data); break;
    case "task_output": onTaskOutput(ev.data); break;
    case "agent_spawned": onAgentSpawned(ev.data); break;
    case "run_started": onRunStarted(ev.data); break;
    case "run_finished": onRunFinished(ev.data); break;
    case "run_aborted": onRunAborted(ev.data); break;
    case "warning": toast("⚠️ " + ev.data.message); addLog(ev.data.message, "warn"); break;
  }
}

function applySnapshot(data) {
  state.mode = data.mode;
  state.model = data.model;
  state.running = data.running;
  state.dag = data.dag;
  state.agents = {};
  state.summary = null;
  state.selected = null;

  const badge = $("mode-badge");
  badge.textContent = data.mode === "live" ? "● LIVE" : "◌ DEMO";
  badge.className = `badge ${data.mode}`;
  $("model-label").textContent = data.model;

  renderExamples();
  renderDAG();
  renderAgents();
  renderNodeDetail();
  renderSummary();
  updateRunControls();
}

// ------------------------------------------------------------------- events
function onTaskStatus({ task_id, status }) {
  const task = state.dag?.tasks?.[task_id];
  if (!task) return;
  task.status = status;
  updateAgentCard(task_id, status);
  renderDAG();
  if (state.selected === task_id) renderNodeDetail();
  updateStats();
}

function onTaskLog({ task_id, line }) {
  const task = state.dag?.tasks?.[task_id];
  if (task) task.logs = task.logs || [];
  if (task && !task.logs.includes(line)) task.logs.push(line);
  addLog(line);
  if (state.selected === task_id) renderNodeDetail(false);
}

function onTaskOutput({ task_id, output }) {
  const task = state.dag?.tasks?.[task_id];
  if (task) task.output = output;
  if (state.selected === task_id) renderNodeDetail(false);
}

function onAgentSpawned({ task_id, persona, title, icon, color }) {
  state.agents[task_id] = { persona, title, icon, color };
  renderAgents();
}

function onRunStarted({ query }) {
  state.running = true;
  state.summary = null;
  $("query-input").value = query;
  updateRunControls();
  renderSummary();
  addLog(`▶ Run started — "${query}"`, "ok");
}

function onRunFinished(summary) {
  state.running = false;
  state.summary = summary;
  updateRunControls();
  renderSummary();
  renderDAG();
  refreshArtifacts();
  addLog(`✔ Run finished in ${summary.duration_s}s — ${summary.done}/${summary.total} tasks done`, "ok");
}

function onRunAborted() {
  state.running = false;
  updateRunControls();
  renderDAG();
  addLog("■ Run stopped by user", "warn");
}

// -------------------------------------------------------------- run controls
function updateRunControls() {
  $("run-btn").disabled = state.running;
  $("stop-btn").classList.toggle("hidden", !state.running);
  updateStats();
}

function updateStats() {
  const dag = state.dag;
  if (!dag) { $("stats").classList.add("hidden"); return; }
  const tasks = Object.values(dag.tasks);
  const done = tasks.filter((t) => t.status === "done").length;
  const running = tasks.filter((t) => t.status === "running").length;
  $("stats").classList.remove("hidden");
  $("stat-wave").innerHTML = running ? `<b>${running}</b> running` : "idle";
  $("stat-done").innerHTML = `<b>${done}/${tasks.length}</b> done`;
}

$("run-btn").onclick = async () => {
  const query = $("query-input").value.trim();
  if (!query || state.running) return;
  try {
    const resp = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      toast("⚠️ " + (err.detail || `HTTP ${resp.status}`));
    }
  } catch (err) {
    toast("⚠️ Failed to start run: " + err.message);
  }
};

$("stop-btn").onclick = async () => {
  await fetch("/api/stop", { method: "POST" }).catch(() => {});
};

function renderExamples() {
  const wrap = $("examples");
  wrap.innerHTML = "";
  for (const ex of EXAMPLES) {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.textContent = ex.length > 42 ? ex.slice(0, 42) + "…" : ex;
    chip.title = ex;
    chip.onclick = () => { $("query-input").value = ex; $("query-input").focus(); };
    wrap.appendChild(chip);
  }
}

// ------------------------------------------------------------------ agents
function renderAgents() {
  const list = $("agents-list");
  const entries = Object.entries(state.agents);
  $("agents-count").textContent = entries.length;
  if (!entries.length) {
    list.innerHTML = `<p class="muted">No agents yet — run a query to spawn the planner.</p>`;
    return;
  }
  list.innerHTML = "";
  for (const [taskId, a] of entries) {
    const task = state.dag?.tasks?.[taskId];
    const card = document.createElement("div");
    card.className = "agent-card";
    card.id = `agent-${taskId}`;
    card.innerHTML = `
      <span class="agent-icon">${a.icon}</span>
      <div class="agent-info">
        <div class="agent-title">${esc(a.title)}</div>
        <div class="agent-task">${esc(task?.title || "")}</div>
      </div>
      <span class="status-dot ${task?.status || "pending"}"></span>`;
    card.onclick = () => selectNode(taskId);
    list.appendChild(card);
  }
}

function updateAgentCard(taskId, status) {
  const dot = document.querySelector(`#agent-${taskId} .status-dot`);
  if (dot) dot.className = `status-dot ${status}`;
}

// ------------------------------------------------------------------ DAG svg
function layoutDAG(dag) {
  const pos = {};
  const levels = dag.levels || [];
  const colW = NODE_W + GAP_X;
  const rowH = NODE_H + GAP_Y;
  const maxRows = Math.max(...levels.map((l) => l.length), 1);
  const totalH = maxRows * rowH;
  levels.forEach((ids, lvl) => {
    const colH = ids.length * rowH;
    const y0 = MARGIN + Math.max(0, (totalH - colH) / 2);
    ids.forEach((id, row) => {
      pos[id] = { x: MARGIN + lvl * colW, y: y0 + row * rowH };
    });
  });
  const width = MARGIN * 2 + levels.length * colW - GAP_X + NODE_W;
  const height = totalH + MARGIN * 2;
  return { pos, width: Math.max(width, 300), height: Math.max(height, 200) };
}

function renderDAG() {
  const svg = $("dag-svg");
  const viewport = $("viewport");
  const dag = state.dag;
  $("dag-empty").style.display = dag ? "none" : "flex";
  if (!dag || !Object.keys(dag.tasks).length) { viewport.innerHTML = ""; return; }

  const { pos, width, height } = layoutDAG(dag);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  applyView();

  const NS = "http://www.w3.org/2000/svg";
  viewport.innerHTML = "";

  // edges first (under nodes)
  for (const task of Object.values(dag.tasks)) {
    for (const depId of task.depends_on || []) {
      const from = pos[depId], to = pos[task.id];
      if (!from || !to) continue;
      const x1 = from.x + NODE_W, y1 = from.y + NODE_H / 2;
      const x2 = to.x, y2 = to.y + NODE_H / 2;
      const mx = (x1 + x2) / 2;
      const path = document.createElementNS(NS, "path");
      path.setAttribute("d", `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`);
      const cls = task.status === "running" ? "edge flow"
        : task.status === "done" ? "edge done" : "edge";
      path.setAttribute("class", cls);
      viewport.appendChild(path);
    }
  }

  // nodes
  for (const task of Object.values(dag.tasks)) {
    const p = pos[task.id];
    const g = document.createElementNS(NS, "g");
    g.setAttribute("class", `node ${task.status} ${state.selected === task.id ? "selected" : ""}`);
    g.setAttribute("transform", `translate(${p.x}, ${p.y})`);

    const rect = document.createElementNS(NS, "rect");
    rect.setAttribute("class", "body");
    rect.setAttribute("width", NODE_W);
    rect.setAttribute("height", NODE_H);
    rect.setAttribute("rx", 10);
    g.appendChild(rect);

    const icon = document.createElementNS(NS, "text");
    icon.setAttribute("class", "n-icon");
    icon.setAttribute("x", 12); icon.setAttribute("y", 24);
    icon.textContent = (state.agents[task.id]?.icon) || "🤖";
    g.appendChild(icon);

    const title = document.createElementNS(NS, "text");
    title.setAttribute("class", "n-title");
    title.setAttribute("x", 36); title.setAttribute("y", 22);
    title.textContent = task.title.length > 20 ? task.title.slice(0, 20) + "…" : task.title;
    g.appendChild(title);

    const persona = document.createElementNS(NS, "text");
    persona.setAttribute("class", "n-persona");
    persona.setAttribute("x", 36); persona.setAttribute("y", 42);
    persona.textContent = `${task.persona} · ${task.status}`;
    g.appendChild(persona);

    g.addEventListener("click", (e) => { e.stopPropagation(); selectNode(task.id); });
    viewport.appendChild(g);
  }
}

function selectNode(taskId) {
  state.selected = taskId;
  renderDAG();
  renderNodeDetail();
  document.querySelector('.tab[data-tab="details"]').click();
}

// pan + zoom
function applyView() {
  $("viewport").setAttribute("transform", `translate(${state.panX},${state.panY}) scale(${state.zoom})`);
}
function zoomBy(f) {
  state.zoom = Math.min(2.5, Math.max(0.3, state.zoom * f));
  applyView();
}
$("zoom-in").onclick = () => zoomBy(1.2);
$("zoom-out").onclick = () => zoomBy(1 / 1.2);
$("zoom-fit").onclick = () => { state.zoom = 1; state.panX = 0; state.panY = 0; applyView(); };

(function initPan() {
  const svg = $("dag-svg");
  let dragging = false, sx = 0, sy = 0, ox = 0, oy = 0;
  svg.addEventListener("mousedown", (e) => {
    dragging = true; sx = e.clientX; sy = e.clientY; ox = state.panX; oy = state.panY;
    svg.classList.add("panning");
  });
  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    state.panX = ox + (e.clientX - sx);
    state.panY = oy + (e.clientY - sy);
    applyView();
  });
  window.addEventListener("mouseup", () => { dragging = false; svg.classList.remove("panning"); });
  svg.addEventListener("wheel", (e) => {
    e.preventDefault();
    zoomBy(e.deltaY < 0 ? 1.1 : 1 / 1.1);
  }, { passive: false });
})();

// ------------------------------------------------------------- node detail
function renderNodeDetail(clear = true) {
  const wrap = $("node-detail");
  const task = state.selected ? state.dag?.tasks?.[state.selected] : null;
  if (!task) {
    wrap.innerHTML = `<p class="muted">Select a node in the graph to inspect its live logs and output.</p>`;
    return;
  }
  const agent = state.agents[task.id];
  const logs = (task.logs || []).map(esc).join("\n");
  wrap.innerHTML = `
    <h3>${agent?.icon || "🤖"} ${esc(task.title)}</h3>
    <div class="nd-meta">
      <span class="nd-badge" style="border-color:${agent?.color || "#444"}">${esc(agent?.title || task.persona)}</span>
      <span class="nd-badge">${esc(task.status)}</span>
      ${(task.depends_on || []).length
        ? `<span class="nd-badge">after: ${task.depends_on.map(esc).join(", ")}</span>` : ""}
    </div>
    <p class="nd-desc">${esc(task.description || "")}</p>
    <div class="nd-section">Live log</div>
    <div class="nd-log" id="nd-log">${logs || "<span class='muted'>waiting…</span>"}</div>
    ${task.output ? `<div class="nd-section">Output</div><div class="nd-output">${esc(task.output)}</div>` : ""}
    ${task.error ? `<div class="nd-section">Error</div><div class="nd-output" style="color:#fca5a5">${esc(task.error)}</div>` : ""}`;
  const logEl = $("nd-log");
  if (logEl) logEl.scrollTop = logEl.scrollHeight;
}

// ------------------------------------------------------------------ artifacts
async function refreshArtifacts() {
  try {
    const resp = await fetch("/api/artifacts");
    state.artifacts = await resp.json();
  } catch { state.artifacts = []; }
  renderArtifacts();
}

function renderArtifacts() {
  const list = $("artifacts-list");
  $("art-count").textContent = state.artifacts.length;
  if (!state.artifacts.length) {
    list.innerHTML = `<p class="muted">No artifacts yet.</p>`;
    return;
  }
  list.innerHTML = "";
  for (const f of state.artifacts) {
    const el = document.createElement("div");
    el.className = "art-file" + (state._activeFile === f.path ? " active" : "");
    el.textContent = `${f.path} (${(f.size / 1024).toFixed(1)} KB)`;
    el.onclick = () => openArtifact(f.path);
    list.appendChild(el);
  }
}

async function openArtifact(path) {
  state._activeFile = path;
  renderArtifacts();
  const view = $("artifacts-view");
  view.classList.remove("hidden");
  view.textContent = "loading…";
  try {
    const resp = await fetch(`/api/file?path=${encodeURIComponent(path)}`);
    const data = await resp.json();
    view.textContent = data.content ?? "(empty)";
  } catch (err) {
    view.textContent = `failed to load: ${err.message}`;
  }
}

// ------------------------------------------------------------------- summary
function renderSummary() {
  const wrap = $("run-summary");
  const s = state.summary;
  if (!s) { wrap.innerHTML = `<p class="muted">No run yet.</p>`; return; }
  wrap.innerHTML = `
    <div class="sum-stats">
      <span><b>${s.done}/${s.total}</b>done</span>
      <span><b>${s.failed}</b>failed</span>
      <span><b>${s.skipped}</b>skipped</span>
      <span><b>${s.duration_s}s</b>duration</span>
    </div>
    <table>
      <tr><th>Task</th><th>Persona</th><th>Status</th></tr>
      ${s.tasks.map((t) => `
        <tr>
          <td>${esc(t.title)}</td>
          <td>${esc(t.persona)}</td>
          <td><span class="status-dot ${t.status}" style="display:inline-block;margin-right:6px"></span>${t.status}</td>
        </tr>`).join("")}
    </table>`;
}

// ------------------------------------------------------------------ event log
function addLog(line, cls = "") {
  const log = $("event-log");
  const el = document.createElement("div");
  el.className = `log-line ${cls}`;
  const t = new Date().toLocaleTimeString("en-GB", { hour12: false });
  el.innerHTML = `<span class="t">${t}</span>${esc(line)}`;
  log.appendChild(el);
  while (log.children.length > 600) log.removeChild(log.firstChild);
  log.scrollTop = log.scrollHeight;
}

// ---------------------------------------------------------------------- tabs
document.querySelectorAll(".tab").forEach((tab) => {
  tab.onclick = () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".tab-page").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    $(`tab-${tab.dataset.tab}`).classList.add("active");
    if (tab.dataset.tab === "artifacts") refreshArtifacts();
  };
});

// ---------------------------------------------------------------------- boot
connect();
refreshArtifacts();
