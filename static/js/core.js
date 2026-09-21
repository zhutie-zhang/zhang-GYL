/* 核心模块：全局状态、公共工具、页签与视图切换 */

const state = {
  groups: [],
  warehouses: [],
  activeGroup: null,
  inv: null,
  out: null,
  invSort: { col: "total", dir: -1 },
  outSort: { col: "total", dir: -1 },
  invFilter: "",
  outFilter: "",
  outStart: "",
  outEnd: "",
  outPoint: "",
  invPage: 1,
  outPage: 1,
  invPageSize: 20,
  outPageSize: 20,
  loading: false,
  view: "overseas",
  statsSource: "inv",
  statsFilter: "",
  overseasWh: "",
};

const $ = (id) => document.getElementById(id);

let AUTO_INTERVAL = 60 * 1000;

async function api(url, opts) {
  opts = Object.assign({}, opts || {});
  const timeoutMs = opts.timeout || 150000;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  if (!opts.signal) opts.signal = controller.signal;
  try {
    const resp = await fetch(url, Object.assign({ cache: "no-store" }, opts));
    if (!resp.ok) {
      let msg = `请求失败: HTTP ${resp.status}`;
      try { const d = await resp.json(); if (d && d.error) msg = d.error; } catch (_) {}
      throw new Error(msg);
    }
    return resp.json();
  } catch (e) {
    if (e && e.name === "AbortError") throw new Error(`请求超时（> ${Math.round(timeoutMs / 1000)}s），服务器可能正忙，请稍后重试`);
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

/* 通用模糊匹配：大小写不敏感，按字符顺序匹配（可跳字），如 "SN66" 命中 "SAN66-BK"。
   也兼容纯子串场景（连续包含时必然匹配）。 */
function fuzzyMatch(hay, q) {
  hay = String(hay == null ? "" : hay).toLowerCase();
  q = String(q == null ? "" : q).toLowerCase();
  if (!q) return true;
  if (hay.includes(q)) return true;
  let j = 0;
  for (let i = 0; i < hay.length && j < q.length; i++) {
    if (hay[i] === q[j]) j++;
  }
  return j === q.length;
}

/* 对一组候选值做模糊匹配：任一命中即返回 true */
function fuzzySome(values, q) {
  if (!q) return true;
  for (const v of values) {
    if (fuzzyMatch(v, q)) return true;
  }
  return false;
}

function downloadCsv(filename, content) {
  const blob = new Blob(["\uFEFF" + content], { type: "text/csv;charset=utf-8;" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

function formatTime(t) {
  return t || "—";
}

function setUpdated(label) {
  $("updatedAt").textContent = "更新于 " + (label || "—");
}

function showErrors(data) {
  const errs = [];
  for (const [id, w] of Object.entries(data.warehouses || {})) {
    if (w.status === "error") errs.push(`${w.name}: ${w.error}`);
  }
  const bar = $("errorBar");
  if (errs.length) {
    bar.textContent = "⚠ 以下仓库数据获取失败：" + errs.join("；");
    bar.classList.remove("hidden");
  } else {
    bar.classList.add("hidden");
  }
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

/* ---------------- 页签导航：总览(海外仓) + 产品管理 + 组合统计 ---------------- */

function setPanelVisible(showId) {
  if (showId !== "overseasPanel" && typeof stopRestockAutoRefresh === "function") stopRestockAutoRefresh();
  ["overseasPanel", "agePanel", "productPanel", "statsPanel", "rankPanel", "transitPanel", "analyticsPanel", "supplyChainPanel", "pricingPanel"].forEach((id) => {
    $(id).style.display = id === showId ? "" : "none";
  });
}

function renderTabs() {
  const nav = $("whTabs");
  nav.innerHTML = "";
  const obtn = document.createElement("button");
  obtn.type = "button";
  obtn.className = "tab" + (state.view === "overseas" ? " active" : "");
  obtn.textContent = "总览";
  obtn.title = "所有海外仓统一看板，可选择查看单个仓库";
  obtn.addEventListener("click", showOverseas);
  nav.appendChild(obtn);
  const pbtn = document.createElement("button");
  pbtn.type = "button";
  pbtn.className = "tab" + (state.view === "products" ? " active" : "");
  pbtn.textContent = "产品管理";
  pbtn.title = "组合产品映射管理";
  pbtn.addEventListener("click", showProducts);
  nav.appendChild(pbtn);
  const sbtn = document.createElement("button");
  sbtn.type = "button";
  sbtn.className = "tab" + (state.view === "stats" ? " active" : "");
  sbtn.textContent = "组合统计";
  sbtn.title = "成套 / 不成套 / 无组合 SKU 统计";
  sbtn.addEventListener("click", showStats);
  nav.appendChild(sbtn);
  const rbtn = document.createElement("button");
  rbtn.type = "button";
  rbtn.className = "tab" + (state.view === "rank" ? " active" : "");
  rbtn.textContent = "排行榜";
  rbtn.title = "出库产品排行 / 增速排行，支持标签与排除";
  rbtn.addEventListener("click", showRank);
  nav.appendChild(rbtn);
  const tbtn = document.createElement("button");
  tbtn.type = "button";
  tbtn.className = "tab" + (state.view === "transit" ? " active" : "");
  tbtn.textContent = "在途追踪";
  tbtn.title = "在途产品追踪：装箱单 + SO 船期 + 预计到港 ETA";
  tbtn.addEventListener("click", showTransit);
  nav.appendChild(tbtn);
  const agebtn = document.createElement("button");
  agebtn.type = "button";
  agebtn.className = "tab" + (state.view === "age" ? " active" : "");
  agebtn.textContent = "库龄统计";
  agebtn.title = "各仓库存库龄，按批次逐档预警(15/30/45/60/120天)，120天以上标红";
  agebtn.addEventListener("click", showAge);
  nav.appendChild(agebtn);
  const pcbtn = document.createElement("button");
  pcbtn.type = "button";
  pcbtn.className = "tab" + (state.view === "pricing" ? " active" : "");
  pcbtn.textContent = "报价比价";
  pcbtn.title = "海外仓报价上传与多维比价";
  pcbtn.addEventListener("click", showPricing);
  nav.appendChild(pcbtn);
}

function setOverseasVisible() {
  setPanelVisible("overseasPanel");
}

async function showOverseas() {
  state.view = "overseas";
  renderTabs();
  setOverseasVisible();
  if (!state.inv || !state.out) {
    await refreshAll(false);
  }
  renderOverseas();
  startRestockAutoRefresh();
}

function switchOverseasWh(gid) {
  state.overseasWh = gid;
  renderOverseas();
}

function groupName(gid) {
  const g = state.groups.find((x) => x.id === gid);
  return g ? g.name : gid || "";
}

/* 仓点名称附上仓库名与账号名加以区分，如：HOU2062（乐歌MYZ）、Chicago WHS（smartMYZ） */
function unitLabel(u) {
  const base = u.whName && u.whName !== u.name ? `${u.name}（${u.whName}）` : u.name;
  if (u.account) return `${base}（${u.account}）`;
  return base;
}

/* ---------------- 仓点（单位）计算 ---------------- */

function pointKey(whId, pid) {
  return whId + "::" + pid;
}

function allPointUnits(data) {
  const arr = [];
  for (const [whId, w] of Object.entries(data.warehouses || {})) {
    if (w.status !== "ok") continue;
    for (const p of w.points || []) {
      arr.push({
        key: pointKey(whId, p.id),
        name: p.name || w.name,
        account: w.account || "",
        whId,
        pid: p.id,
        whName: w.name,
        group: w.group || "",
        fetchedAt: w.fetched_at,
        dateNote: w.date_note,
        rows: p.rows || [],
      });
    }
  }
  return arr;
}

function getUnits(data, filterPointKey) {
  const pts = allPointUnits(data);
  if (filterPointKey) {
    return pts.filter((p) => p.key === filterPointKey);
  }
  if (!state.activeGroup) {
    const units = [];
    for (const g of state.groups) {
      const list = pts.filter((p) => p.group === g.id);
      if (!list.length) continue;
      const agg = {};
      for (const p of list) {
        for (const r of p.rows) {
          if (!r.sku) continue;
          const e = agg[r.sku] || (agg[r.sku] = { sku: r.sku, name: r.name || "", qty: 0 });
          e.qty += Number(r.qty || 0);
          if (r.name) e.name = r.name;
        }
      }
      units.push({ key: "group::" + g.id, name: g.name, group: g.id, rows: Object.values(agg) });
    }
    return units;
  }
  return pts.filter((p) => p.group === state.activeGroup);
}

function groupPointCount(data, gid) {
  return allPointUnits(data).filter((p) => p.group === gid).length;
}

function pivot(data, filterPointKey) {
  const units = getUnits(data, filterPointKey);
  const bySku = {};
  const order = [];
  for (const u of units) {
    for (const r of u.rows) {
      if (!r.sku) continue;
      if (!bySku[r.sku]) {
        bySku[r.sku] = { sku: r.sku, name: r.name || "", qty: {}, total: 0 };
        order.push(r.sku);
      }
      const e = bySku[r.sku];
      e.qty[u.key] = (e.qty[u.key] || 0) + Number(r.qty || 0);
      e.total += Number(r.qty || 0);
      if (r.name) e.name = r.name;
    }
  }
  return { bySku, order, units };
}

function initAllColResize() {
  document.querySelectorAll("table:not(.sub-table) thead th").forEach((th, idx, allTh) => {
    if (th.querySelector(".col-resize")) return;
    if (idx >= allTh.length - 1) return;
    const h = document.createElement("span");
    h.className = "col-resize";
    th.appendChild(h);
  });
}

document.addEventListener("mousedown", (e) => {
  const handle = e.target.closest(".col-resize");
  if (!handle) return;
  e.preventDefault();
  e.stopPropagation();
  const th = handle.parentElement;
  const allTh = Array.from(th.parentElement.children);
  const idx = allTh.indexOf(th);
  const startX = e.clientX;
  const startW = th.offsetWidth;
  const nextTh = allTh[idx + 1];
  const nextStartW = nextTh ? nextTh.offsetWidth : 0;
  handle.classList.add("dragging");
  const onMove = (ev) => {
    const dx = ev.clientX - startX;
    const nw = Math.max(40, startW + dx);
    th.style.width = nw + "px";
    th.style.minWidth = nw + "px";
    th.style.maxWidth = nw + "px";
    if (nextTh) {
      const nnw = Math.max(40, nextStartW - dx);
      nextTh.style.width = nnw + "px";
      nextTh.style.minWidth = nnw + "px";
      nextTh.style.maxWidth = nnw + "px";
    }
  };
  const onUp = () => {
    handle.classList.remove("dragging");
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
  };
  document.addEventListener("mousemove", onMove);
  document.addEventListener("mouseup", onUp);
});

new MutationObserver(() => initAllColResize()).observe(document.body, { childList: true, subtree: true });

/* ---- 通用列字段设置系统 ---- */
const _colCfgCache = {};
function loadColConfig(panelId) {
  if (_colCfgCache[panelId]) return _colCfgCache[panelId];
  try {
    const c = JSON.parse(localStorage.getItem("col_cfg_" + panelId));
    if (c && Array.isArray(c.order)) { _colCfgCache[panelId] = c; return c; }
  } catch {}
  return null;
}
function saveColConfig(panelId, cfg) {
  _colCfgCache[panelId] = cfg;
  localStorage.setItem("col_cfg_" + panelId, JSON.stringify(cfg));
}
function isColVisible(panelId, colKey) {
  const cfg = loadColConfig(panelId);
  if (!cfg || !cfg.hidden) return true;
  return !cfg.hidden.includes(colKey);
}
function getColOrder(panelId, defaultKeys) {
  const cfg = loadColConfig(panelId);
  if (cfg && Array.isArray(cfg.order)) return cfg.order.filter((k) => defaultKeys.includes(k));
  return [...defaultKeys];
}
function showColSettings(panelId, colDefs, onApply) {
  const cfg = loadColConfig(panelId) || { order: colDefs.map((c) => c.key), hidden: [] };
  const order = cfg.order.filter((k) => colDefs.some((c) => c.key === k));
  for (const c of colDefs) { if (!order.includes(c.key)) order.push(c.key); }
  const hidden = new Set(cfg.hidden || []);
  let dragSrc = null;
  const items = order.map((k) => {
    const f = colDefs.find((x) => x.key === k);
    return `<div class="ds-item" draggable="true" data-key="${k}">
      <span class="ds-drag">⠿</span>
      <label class="ds-label"><input type="checkbox" class="ds-vis" data-key="${k}" ${!hidden.has(k) ? "checked" : ""}>${f ? f.label : k}</label>
    </div>`;
  }).join("");
  const ov = document.createElement("div");
  ov.className = "modal-overlay";
  ov.innerHTML = `<div class="modal-card" style="width:340px;max-width:90vw">
    <div class="modal-head"><span class="modal-title">字段显示设置</span><button type="button" class="btn ghost btn-xs" data-ds-close>关闭</button></div>
    <div class="modal-body">
      <div class="ds-list" id="dsList">${items}</div>
      <div style="margin-top:12px;display:flex;gap:8px;justify-content:flex-end">
        <button type="button" class="btn ghost btn-xs" id="dsReset">恢复默认</button>
        <button type="button" class="btn primary btn-xs" id="dsSave">保存</button>
      </div>
    </div></div>`;
  document.body.appendChild(ov);
  const list = ov.querySelector("#dsList");
  list.addEventListener("dragstart", (e) => { dragSrc = e.target.closest(".ds-item"); if (dragSrc) dragSrc.classList.add("ds-dragging"); e.dataTransfer.effectAllowed = "move"; });
  list.addEventListener("dragover", (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; const t = e.target.closest(".ds-item"); if (t && t !== dragSrc) { const mid = t.getBoundingClientRect().top + t.getBoundingClientRect().height / 2; e.clientY < mid ? list.insertBefore(dragSrc, t) : list.insertBefore(dragSrc, t.nextSibling); } });
  list.addEventListener("dragend", () => { if (dragSrc) dragSrc.classList.remove("ds-dragging"); dragSrc = null; });
  ov.querySelector("[data-ds-close]").addEventListener("click", () => ov.remove());
  ov.addEventListener("click", (e) => { if (e.target === ov) ov.remove(); });
  ov.querySelector("#dsReset").addEventListener("click", () => {
    saveColConfig(panelId, { order: colDefs.map((c) => c.key), hidden: [] });
    ov.remove(); if (onApply) onApply();
  });
  ov.querySelector("#dsSave").addEventListener("click", () => {
    const newOrder = [...list.querySelectorAll(".ds-item")].map((el) => el.getAttribute("data-key"));
    const newHidden = [];
    list.querySelectorAll(".ds-vis").forEach((cb) => { if (!cb.checked) newHidden.push(cb.getAttribute("data-key")); });
    saveColConfig(panelId, { order: newOrder, hidden: newHidden });
    ov.remove(); if (onApply) onApply();
  });
}
