// 前端单页应用：对话（三模式流式）、模型/软件配置、模板管理。
const API = "";
const SESSION_KEY = "web-" + (localStorage.getItem("sk") || (() => {
  const k = Math.random().toString(36).slice(2, 10);
  localStorage.setItem("sk", k);
  return k;
})());

const state = {
  mode: "plan",
  streaming: false,
  templateSel: null,
  currentSessionId: localStorage.getItem("sid") || null,
  sessionSel: null,
  abortCtrl: null,
};

const MODE_META = {
  plan: {
    title: "Plan 模式",
    hint: "主设计模型编排全流程：需求收敛 → 方案 → 计算 → 建模 → 仿真 → 交付。",
  },
  modeling: {
    title: "建模 Agent 模式",
    hint: "直接进入建模子 Agent（mcp-cad / Inventor）。输入 /exit 返回主设计模型。",
  },
  simulation: {
    title: "仿真 Agent 模式",
    hint: "直接进入仿真子 Agent（ANSYS）。需已有通过验证的几何。输入 /exit 返回主设计模型。",
  },
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function toast(msg, kind = "") {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "toast show " + kind;
  setTimeout(() => (el.className = "toast " + kind), 2600);
}

async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

function switchView(view) {
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  $$(".view").forEach((v) => v.classList.toggle("active", v.dataset.view === view));
  if (view === "config") loadConfig();
  if (view === "templates") loadTemplates();
  if (view === "sessions") loadSessions();
}

function switchMode(mode) {
  state.mode = mode;
  $$(".mode-item").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
  $("#chatModeTitle").textContent = MODE_META[mode].title;
  $("#chatModeHint").textContent = MODE_META[mode].hint;
}

function bindNav() {
  $$(".nav-item").forEach((b) => b.addEventListener("click", () => switchView(b.dataset.view)));
  $$(".mode-item").forEach((b) => b.addEventListener("click", () => switchMode(b.dataset.mode)));
}

const AGENT_LABELS = {
  chief_model: "主模型 · 思考",
  assistant: "助理",
  modeling: "建模子 Agent",
  analysis: "仿真子 Agent",
  system: "系统",
};

function addMessage(role) {
  const el = document.createElement("div");
  el.className = "msg " + role;
  $("#messages").appendChild(el);
  $("#messages").scrollTop = $("#messages").scrollHeight;
  return el;
}

function renderAssistant(el, buffers) {
  let html = "";
  if (buffers.chief_model) {
    html += `<div class="agent-tag">${AGENT_LABELS.chief_model}</div>`;
    html += `<div class="think">${escapeHtml(buffers.chief_model)}</div>`;
  }
  for (const agent of ["assistant", "modeling", "analysis", "system"]) {
    if (agent === "chief_model") continue;
    if (buffers[agent]) {
      html += `<div class="agent-tag">${AGENT_LABELS[agent] || agent}</div>`;
      html += `<div>${escapeHtml(buffers[agent])}</div>`;
    }
  }
  el.innerHTML = html || "…";
  $("#messages").scrollTop = $("#messages").scrollHeight;
}

function escapeHtml(s) {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

function setSendButton(streaming) { const btn = $("#sendBtn"); btn.textContent = streaming ? "停止" : "发送"; btn.classList.toggle("stop", streaming); btn.disabled = false; }

function stopMessage() { if (state.abortCtrl) { state.abortCtrl.abort(); state.abortCtrl = null; } }

function appendStoppedNote(assistantEl, buffers) { if (!Object.keys(buffers).length) { assistantEl.textContent = "（已停止）"; return; } const n = document.createElement("div"); n.className = "meta"; n.textContent = "已停止输出"; assistantEl.appendChild(n); }

async function sendMessage() {
  if (state.streaming) { stopMessage(); return; }
  const input = $("#input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  addMessage("user").textContent = text;

  state.streaming = true;
  state.abortCtrl = new AbortController();
  setSendButton(true);
  const assistantEl = addMessage("assistant");
  assistantEl.textContent = "…";
  const buffers = {};

  try {
    const res = await fetch(API + "/api/stream/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, session_key: SESSION_KEY, mode: state.mode, session_id: state.currentSessionId }),
      signal: state.abortCtrl.signal,
    });
    if (!res.ok || !res.body) throw new Error("请求失败: " + res.status);
    await consumeSSE(res.body, assistantEl, buffers);
  } catch (err) {
    if (err.name === "AbortError") { appendStoppedNote(assistantEl, buffers); } else { assistantEl.innerHTML = `<div class="agent-tag">系统</div><div style="color:var(--err)">${escapeHtml(err.message)}</div>`; }
  } finally {
    state.streaming = false;
    state.abortCtrl = null;
    setSendButton(false);
  }
}

async function consumeSSE(body, assistantEl, buffers) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const chunks = buf.split("\n\n");
    buf = chunks.pop();
    for (const chunk of chunks) {
      const evMatch = chunk.match(/^event: (.+)$/m);
      const dataMatch = chunk.match(/^data: (.+)$/m);
      if (!dataMatch) continue;
      const event = evMatch ? evMatch[1] : "message";
      const data = JSON.parse(dataMatch[1]);
      handleSSE(event, data, assistantEl, buffers);
    }
  }
}

function handleSSE(event, data, assistantEl, buffers) {
  if (event === "delta") {
    buffers[data.agent] = (buffers[data.agent] || "") + data.delta;
    renderAssistant(assistantEl, buffers);
  } else if (event === "final") {
    if (!Object.keys(buffers).length) {
      assistantEl.textContent = data.reply || "任务已完成。";
    }
    const meta = [];
    if (data.tool_calls_made?.length) meta.push("工具: " + data.tool_calls_made.join(", "));
    if (data.deliverables?.length) meta.push("交付物: " + data.deliverables.join(", "));
    if (data.awaiting_decision) meta.push("等待你的答复");
    if (meta.length) {
      const m = document.createElement("div");
      m.className = "meta";
      m.textContent = meta.join(" · ");
      assistantEl.appendChild(m);
    }
    if (data.session_id) {
      state.currentSessionId = data.session_id;
      localStorage.setItem("sid", data.session_id);
    }
    $("#statusStage").textContent = data.design_stage || "-";
    $("#statusAgent").textContent = data.active_agent || "-";
  } else if (event === "error") {
    assistantEl.innerHTML = `<div class="agent-tag">系统</div><div style="color:var(--err)">${escapeHtml(data.message)}</div>`;
  }
}

function bindChat() {
  $("#sendBtn").addEventListener("click", sendMessage);
  $("#input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
  $("#newSessionBtn").addEventListener("click", () => {
    localStorage.removeItem("sk");
    localStorage.removeItem("sid");
    location.reload();
  });
}

async function loadConfig() {
  const reveal = $("#revealSecrets").checked;
  try {
    const [{ sections }, { models }] = await Promise.all([
      api(`/api/config/env?reveal=${reveal}`),
      api(`/api/config/models`),
    ]);
    renderModels(models);
    renderConfigForm(sections);
  } catch (err) {
    toast("加载配置失败: " + err.message, "err");
  }
}

function renderModels(models) {
  const box = $("#effectiveModels");
  box.innerHTML = "";
  for (const m of models) {
    const card = document.createElement("div");
    card.className = "model-card" + (m.error ? " err" : "");
    card.innerHTML = `<b>${m.label}</b>
      <span>模型: ${m.model}</span><br/>
      <span>端点: ${m.endpoint || "-"}</span><br/>
      <span>密钥: ${m.api_key}</span>
      ${m.error ? `<br/><span style="color:var(--err)">${escapeHtml(m.error)}</span>` : ""}`;
    box.appendChild(card);
  }
}

function renderConfigForm(sections) {
  const form = $("#configForm");
  form.innerHTML = "";
  for (const sec of sections) {
    const block = document.createElement("div");
    block.className = "config-section";
    block.innerHTML = `<h3>${escapeHtml(sec.section)}</h3>`;
    const grid = document.createElement("div");
    grid.className = "config-grid";
    for (const item of sec.items) {
      const field = document.createElement("div");
      field.className = "field" + (item.commented ? " commented" : "");
      const type = item.sensitive && !$("#revealSecrets").checked ? "text" : "text";
      field.innerHTML = `<label title="${escapeHtml(item.key)}">${escapeHtml(item.key)}${item.commented ? " (已注释)" : ""}</label>`;
      const inp = document.createElement("input");
      inp.type = type;
      inp.value = item.value;
      inp.dataset.key = item.key;
      inp.dataset.original = item.value;
      field.appendChild(inp);
      grid.appendChild(field);
    }
    block.appendChild(grid);
    form.appendChild(block);
  }
}

async function saveConfig() {
  const values = {};
  $$("#configForm input").forEach((inp) => {
    if (inp.value !== inp.dataset.original) values[inp.dataset.key] = inp.value;
  });
  if (!Object.keys(values).length) {
    toast("没有检测到修改");
    return;
  }
  try {
    const res = await api("/api/config/env", { method: "PUT", body: JSON.stringify({ values }) });
    toast(`已保存 ${res.updated.length} 项，已热重载`, "ok");
    loadConfig();
  } catch (err) {
    toast("保存失败: " + err.message, "err");
  }
}

function bindConfig() {
  $("#reloadConfigBtn").addEventListener("click", loadConfig);
  $("#saveConfigBtn").addEventListener("click", saveConfig);
  $("#revealSecrets").addEventListener("change", loadConfig);
}

async function loadTemplates() {
  try {
    const { categories } = await api("/api/templates");
    const list = $("#templateList");
    list.innerHTML = "";
    for (const cat of categories) {
      const group = document.createElement("div");
      group.innerHTML = `<div class="tpl-cat-title">${escapeHtml(cat.label)}</div>`;
      for (const f of cat.files) {
        const file = document.createElement("div");
        file.className = "tpl-file";
        file.textContent = f.name;
        file.dataset.category = cat.category;
        file.dataset.name = f.name;
        file.addEventListener("click", () => openTemplate(cat.category, f.name, file));
        group.appendChild(file);
      }
      list.appendChild(group);
    }
  } catch (err) {
    toast("加载模板失败: " + err.message, "err");
  }
}

async function openTemplate(category, name, el) {
  try {
    const data = await api(`/api/templates/${category}/${name}`);
    $$(".tpl-file").forEach((f) => f.classList.remove("active"));
    el.classList.add("active");
    state.templateSel = { category, name };
    $("#templateName").textContent = `${category} / ${name}`;
    $("#templateContent").value = data.content;
    $("#saveTemplateBtn").disabled = false;
  } catch (err) {
    toast("读取失败: " + err.message, "err");
  }
}

async function saveTemplate() {
  if (!state.templateSel) return;
  const { category, name } = state.templateSel;
  try {
    await api(`/api/templates/${category}/${name}`, {
      method: "PUT",
      body: JSON.stringify({ content: $("#templateContent").value }),
    });
    toast("模板已保存并重载", "ok");
  } catch (err) {
    toast("保存失败: " + err.message, "err");
  }
}

function bindTemplates() {
  $("#saveTemplateBtn").addEventListener("click", saveTemplate);
}

async function checkBackend() {
  const dot = $("#statusBackend");
  try {
    await api("/health");
    dot.textContent = "在线";
    dot.className = "dot ok";
  } catch (_) {
    dot.textContent = "离线";
    dot.className = "dot err";
  }
}

function init() {
  bindNav();
  bindChat();
  bindConfig();
  bindTemplates();
  switchMode("plan");
  checkBackend();
  setInterval(checkBackend, 15000);
}

document.addEventListener("DOMContentLoaded", init);

