// 历史会话管理：列出本地持久化的所有会话，查看其上下文/台账/契约/设计书，续接或删除。
// 依赖 app.js 暴露的全局：api, escapeHtml, toast, state, switchView, switchMode, $, $$

async function loadSessions() {
  try {
    const list = await api("/api/sessions?limit=100");
    renderSessionList(list);
    document.querySelector("#sessionCount").textContent = `共 ${list.length} 个会话`;
  } catch (err) {
    toast("加载会话失败: " + err.message, "err");
  }
}

function sessionTitle(s) {
  return s.title || s.family_label || s.family || "未命名设计";
}

function fmtTime(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString("zh-CN", { hour12: false });
}

function renderSessionList(list) {
  const box = document.querySelector("#sessionList");
  box.innerHTML = "";
  if (!list.length) {
    box.innerHTML = '<p class="muted">暂无历史会话。</p>';
    return;
  }
  for (const s of list) {
    const card = document.createElement("div");
    card.className = "session-card";
    if (s.session_id === state.currentSessionId) card.classList.add("active");
    card.innerHTML = `
      <div class="sc-title">${escapeHtml(sessionTitle(s))}</div>
      <div class="sc-meta">
        <span class="sc-badge">${escapeHtml(s.stage_label || s.design_stage)}</span>
        <span class="sc-badge">${escapeHtml(s.mode)}</span>
        <span class="sc-badge">${s.message_count} 条对话</span>
        <span>${fmtTime(s.updated_at)}</span>
      </div>
      <div class="sc-actions">
        <button class="mini-btn" data-act="open">查看</button>
        <button class="mini-btn" data-act="resume">继续对话</button>
        <button class="mini-btn danger" data-act="delete">删除</button>
      </div>`;
    card.querySelector('[data-act="open"]').addEventListener("click", () => openSession(s.session_id, card));
    card.querySelector('[data-act="resume"]').addEventListener("click", () => resumeSession(s.session_id));
    card.querySelector('[data-act="delete"]').addEventListener("click", () => deleteSession(s.session_id));
    box.appendChild(card);
  }
}

async function openSession(sessionId, card) {
  try {
    const full = await api(`/api/sessions/${sessionId}`);
    document.querySelectorAll(".session-card").forEach((c) => c.classList.remove("active"));
    if (card) card.classList.add("active");
    state.sessionSel = sessionId;
    renderSessionDetail(full);
  } catch (err) {
    toast("读取会话失败: " + err.message, "err");
  }
}

async function resumeSession(sessionId) {
  state.currentSessionId = sessionId;
  localStorage.setItem("sid", sessionId);
  try {
    const full = await api(`/api/sessions/${sessionId}`);
    restoreChatLog(full);
    const agent = full.active_agent || "none";
    switchMode(agent === "modeling" ? "modeling" : agent === "analysis" ? "simulation" : "plan");
  } catch (_) {}
  switchView("chat");
  toast("已切换到该会话，可继续对话", "ok");
}

async function deleteSession(sessionId) {
  if (!confirm("确定删除该会话及其全部上下文？此操作不可撤销。")) return;
  try {
    await api(`/api/sessions/${sessionId}`, { method: "DELETE" });
    if (state.currentSessionId === sessionId) {
      state.currentSessionId = null;
      localStorage.removeItem("sid");
    }
    if (state.sessionSel === sessionId) {
      document.querySelector("#sessionDetail").innerHTML = '<p class="muted">选择左侧会话查看详情。</p>';
      state.sessionSel = null;
    }
    toast("会话已删除", "ok");
    loadSessions();
  } catch (err) {
    toast("删除失败: " + err.message, "err");
  }
}

function restoreChatLog(full) {
  const box = document.querySelector("#messages");
  box.innerHTML = "";
  for (const m of full.chat_history || []) {
    if (m.role === "system") continue;
    const el = document.createElement("div");
    el.className = "msg " + (m.role === "user" ? "user" : "assistant");
    el.textContent = m.content;
    box.appendChild(el);
  }
  document.querySelector("#statusStage").textContent = full.design_stage || "-";
  document.querySelector("#statusAgent").textContent = full.active_agent || "-";
  box.scrollTop = box.scrollHeight;
}

function detailKV(pairs) {
  const rows = pairs.map(([k, v]) => `<div class="k">${escapeHtml(k)}</div><div>${escapeHtml(String(v))}</div>`).join("");
  return `<div class="kv">${rows}</div>`;
}

function renderLedger(ledger) {
  const entries = (ledger && ledger.entries) || {};
  const keys = Object.keys(entries);
  if (!keys.length) return "";
  let rows = "";
  for (const k of keys) {
    const e = entries[k];
    const val = e.value && typeof e.value === "object" ? `${e.value.value ?? ""} ${e.value.unit ?? ""}`.trim() : (e.value ?? "");
    const basis = Array.isArray(e.basis) ? e.basis.join(", ") : (e.basis || "");
    rows += `<tr><td>${escapeHtml(e.name || e.symbol || k)}</td><td>${escapeHtml(String(val))}</td><td>${escapeHtml(e.status || "")}</td><td>${escapeHtml(basis)}</td></tr>`;
  }
  return `<div class="detail-block"><h4>参数台账（${keys.length}${ledger.frozen_at ? " · 已冻结" : ""}）</h4>
    <table class="detail-table"><tr><th>参数</th><th>值</th><th>状态</th><th>依据</th></tr>${rows}</table></div>`;
}

function renderSpec(spec) {
  const items = (spec && spec.items) || {};
  const keys = Object.keys(items);
  if (!keys.length) return "";
  let rows = "";
  for (const k of keys) {
    const it = items[k];
    let val = it.value;
    if (val && typeof val === "object") val = `${val.value ?? ""} ${val.unit ?? ""}`;
    rows += `<tr><td>${escapeHtml(it.label || k)}</td><td>${escapeHtml(String(val ?? "—"))}</td><td>${escapeHtml(it.status || "")}</td></tr>`;
  }
  const head = spec.family_label || spec.title || spec.family || "设计任务书";
  return `<div class="detail-block"><h4>${escapeHtml(head)}（${keys.length} 项）</h4>
    <table class="detail-table"><tr><th>条目</th><th>取值</th><th>状态</th></tr>${rows}</table></div>`;
}

function renderCalcs(calcs) {
  const keys = Object.keys(calcs || {});
  if (!keys.length) return "";
  let rows = "";
  for (const k of keys) {
    const c = calcs[k];
    const cls = c.verdict === "pass" ? "tag-pass" : c.verdict === "fail" ? "tag-fail" : "";
    rows += `<tr><td>${escapeHtml(c.title || c.record_id || k)}</td><td class="${cls}">${escapeHtml(c.verdict || "")}${c.stale ? " (失效)" : ""}</td></tr>`;
  }
  return `<div class="detail-block"><h4>计算记录（${keys.length} 条）</h4>
    <table class="detail-table"><tr><th>项目</th><th>结论</th></tr>${rows}</table></div>`;
}

function renderContract(full) {
  const c = full.modeling_contract;
  if (!c && !full.geometry_file) return "";
  const pairs = [];
  if (c) {
    pairs.push(["契约", c.part_name || c.name || "已生成"]);
    if (full.modeling_contract_file) pairs.push(["契约文件", full.modeling_contract_file]);
  }
  if (full.geometry_file) pairs.push(["几何文件", full.geometry_file]);
  const sim = full.simulation_report;
  if (sim) pairs.push(["仿真结论", sim.pass_or_fail || "-"]);
  if (!pairs.length) return "";
  return `<div class="detail-block"><h4>建模契约与产物</h4>${detailKV(pairs)}</div>`;
}

function renderDeliverables(full) {
  const ds = full.deliverables || [];
  if (!ds.length) return "";
  const links = ds.map((d) => `<div class="file-link">[${escapeHtml(d.kind || "")}] ${escapeHtml(d.path || d)}</div>`).join("");
  return `<div class="detail-block"><h4>交付物（设计说明书/计算书等）</h4>${links}</div>`;
}

function renderChatPreview(full) {
  const hist = (full.chat_history || []).filter((m) => m.role !== "system");
  if (!hist.length) return "";
  const recent = hist.slice(-8);
  const rows = recent.map((m) => `<div class="cl ${m.role === "user" ? "user" : ""}">${escapeHtml((m.content || "").slice(0, 400))}</div>`).join("");
  return `<div class="detail-block"><h4>对话上下文（最近 ${recent.length} / 共 ${hist.length} 条）</h4><div class="chat-log">${rows}</div></div>`;
}

function renderSessionDetail(full) {
  const box = document.querySelector("#sessionDetail");
  const head = detailKV([
    ["会话 ID", full.session_id],
    ["模式", full.mode],
    ["阶段", full.design_stage],
    ["当前 Agent", full.active_agent],
    ["设计范围", full.design_scope],
  ]);
  box.innerHTML =
    `<div class="detail-block"><h4>概览</h4>${head}</div>` +
    renderSpec(full.design_spec) +
    renderLedger(full.ledger) +
    renderCalcs(full.calculations) +
    renderContract(full) +
    renderDeliverables(full) +
    renderChatPreview(full);
}


function bindSessions() {
  document.querySelector("#reloadSessionsBtn").addEventListener("click", loadSessions);
}

document.addEventListener("DOMContentLoaded", bindSessions);
