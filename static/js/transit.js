/* 在途产品追踪模块：装箱单(SKU明细) + SO 船期 + 预计到港 ETA */

let _transitRecords = [];
let _transitSelected = new Set();

const DETAIL_FIELDS = [
  { key: "container_no", label: "柜号" },
  { key: "so", label: "SO 号" },
  { key: "shipping_line", label: "船公司" },
  { key: "vessel_voyage", label: "船名 / 航次" },
  { key: "loading_date", label: "装柜时间" },
  { key: "pol", label: "起运港" },
  { key: "pod", label: "目的港" },
  { key: "etd", label: "离港 ETD" },
  { key: "actual_sail_date", label: "实际开船" },
  { key: "eta_est", label: "预计到港 ETA" },
  { key: "actual_arrival_date", label: "实际到港" },
  { key: "days_left", label: "剩余 / 已到" },
  { key: "status", label: "状态" },
  { key: "factory", label: "工厂" },
];
const _transitColDefs = [
  { key: "check", label: "选择" },
  { key: "container_no", label: "柜号" },
  { key: "so", label: "SO号" },
  { key: "shipping_line", label: "船公司" },
  { key: "vessel", label: "船名/航次" },
  { key: "loading_date", label: "装柜时间" },
  { key: "pol", label: "起运港" },
  { key: "pod", label: "目的港" },
  { key: "etd", label: "离港 ETD" },
  { key: "eta_est", label: "预计到港 ETA" },
  { key: "days_left", label: "剩余" },
  { key: "status", label: "状态" },
  { key: "factory", label: "工厂" },
  { key: "detail_btn", label: "详情" },
  { key: "action", label: "操作" },
];
const _transitColKey = "transit_table";

const EDITABLE_FIELDS = [
  { key: "container_no", label: "柜号", type: "text" },
  { key: "so", label: "SO 号", type: "text" },
  { key: "shipping_line", label: "船公司", type: "text" },
  { key: "vessel", label: "船名", type: "text" },
  { key: "voyage", label: "航次", type: "text" },
  { key: "loading_date", label: "装柜时间", type: "date" },
  { key: "pol", label: "起运港", type: "text" },
  { key: "pod", label: "目的港", type: "text" },
  { key: "etd", label: "离港 ETD", type: "date" },
  { key: "actual_sail_date", label: "实际开船", type: "date" },
  { key: "eta_est", label: "预计到港 ETA", type: "date" },
  { key: "actual_arrival_date", label: "实际到港", type: "date" },
  { key: "factory", label: "工厂", type: "text" },
  { key: "manual_status", label: "状态", type: "select", options: ["", "在途", "即将到港", "已到港", "国内查验", "国外查验", "延误", "甩柜", "无ETA"] },
];
const _detailDefaults = DETAIL_FIELDS.map((f) => f.key);

function _loadDetailConfig() {
  try { const c = JSON.parse(localStorage.getItem("transit_detail_cfg")); if (c && Array.isArray(c.order)) return c; } catch {}
  return { order: [..._detailDefaults], hidden: [] };
}
function _saveDetailConfig(cfg) { localStorage.setItem("transit_detail_cfg", JSON.stringify(cfg)); }

function _detailValMap(r) {
  const esc = escapeHtml;
  const days = r.days_left;
  const daysLabel = days === null || days === undefined ? "—" : (days < 0 ? "已到" + (-days) + "天" : days + "天");
  const etaLabel = r.eta_est
    ? esc(r.eta_est) + (r.eta_basis === "so" ? '<span class="muted">(SO)</span>' : r.actual_sail_date ? '<span class="muted">(已开船·推算)</span>' : '<span class="muted">(推算)</span>')
    : "—";
  return {
    container_no: esc(r.container_no) || "—",
    so: esc(r.so) || "—",
    shipping_line: esc(r.shipping_line) || "—",
    vessel_voyage: esc(r.vessel || "") + (r.voyage ? " / " + esc(r.voyage) : ""),
    loading_date: esc(r.loading_date) || "—",
    pol: esc(r.pol) || "—",
    pod: esc(r.pod) || "—",
    etd: esc(r.etd) || "—",
    actual_sail_date: esc(r.actual_sail_date) || "—",
    eta_est: etaLabel,
    actual_arrival_date: esc(r.actual_arrival_date) || "—",
    days_left: esc(daysLabel),
    status: esc(r.status) || "—",
    factory: esc(r.factory) || "—",
  };
}

function _renderDetailGrid(r) {
  const cfg = _loadDetailConfig();
  const hidden = new Set(cfg.hidden || []);
  const days = r.days_left;
  const daysLabel = days === null || days === undefined ? "—" : (days < 0 ? "已到" + (-days) + "天" : days + "天");
  const etaBasis = r.eta_est ? (r.eta_basis === "so" ? '<span class="muted">(SO)</span>' : '<span class="muted">(推算)</span>') : "";
  const esc = escapeHtml;
  const valMap = {
    container_no: esc(r.container_no) || "",
    so: esc(r.so) || "",
    shipping_line: esc(r.shipping_line) || "",
    vessel: esc(r.vessel) || "",
    voyage: esc(r.voyage) || "",
    loading_date: r.loading_date || "",
    pol: esc(r.pol) || "",
    pod: esc(r.pod) || "",
    etd: r.etd || "",
    actual_sail_date: r.actual_sail_date || "",
    eta_est: r.eta_est || "",
    actual_arrival_date: r.actual_arrival_date || "",
    days_left: daysLabel + " " + etaBasis,
    factory: esc(r.factory) || "",
    manual_status: r.manual_status || "",
  };
  const order = (cfg.order || _detailDefaults).filter((k) => !hidden.has(k));
  $("transitDetailGrid").innerHTML = order.map((k) => {
    const f = EDITABLE_FIELDS.find((x) => x.key === k);
    if (!f) {
      const df = DETAIL_FIELDS.find((x) => x.key === k);
      return df ? `<div class="detail-item"><span class="detail-k">${esc(df.label)}</span><span class="detail-v">${valMap[k] || "—"}</span></div>` : "";
    }
    const v = valMap[k] !== undefined ? valMap[k] : "";
    let input;
    if (f.type === "select") {
      const opts = f.options.map((o) => `<option value="${esc(o)}" ${o === v ? "selected" : ""}>${o || "自动"}</option>`).join("");
      input = `<select class="filter-select detail-input" data-field="${k}" style="font-size:12px;padding:2px 6px">${opts}</select>`;
    } else if (f.type === "date") {
      input = `<input type="date" class="detail-input" data-field="${k}" value="${esc(v)}">`;
    } else {
      input = `<input type="text" class="detail-input" data-field="${k}" value="${esc(v)}" style="width:100%">`;
    }
    return `<div class="detail-item"><span class="detail-k">${esc(f.label)}</span><span class="detail-v">${input}</span></div>`;
  }).join("");
}

function _showDetailSettings() {
  const cfg = _loadDetailConfig();
  const order = cfg.order || [..._detailDefaults];
  const hidden = new Set(cfg.hidden || []);
  let dragSrc = null;
  const items = order.map((k) => {
    const f = DETAIL_FIELDS.find((x) => x.key === k);
    return `<div class="ds-item" draggable="true" data-key="${k}">
      <span class="ds-drag">⠿</span>
      <label class="ds-label"><input type="checkbox" class="ds-vis" data-key="${k}" ${!hidden.has(k) ? "checked" : ""}>${f ? f.label : k}</label>
    </div>`;
  }).join("");
  const ov = document.createElement("div");
  ov.className = "modal-overlay";
  ov.innerHTML = `<div class="modal-card" style="width:340px;max-width:90vw">
    <div class="modal-head"><span class="modal-title">自定义详情字段</span><button type="button" class="btn ghost btn-xs" data-ds-close>关闭</button></div>
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
  ov.querySelector("#dsReset").addEventListener("click", () => { _saveDetailConfig({ order: [..._detailDefaults], hidden: [] }); ov.remove(); });
  ov.querySelector("#dsSave").addEventListener("click", () => {
    const newOrder = [...list.querySelectorAll(".ds-item")].map((el) => el.getAttribute("data-key"));
    const newHidden = []; list.querySelectorAll(".ds-vis").forEach((cb) => { if (!cb.checked) newHidden.push(cb.getAttribute("data-key")); });
    _saveDetailConfig({ order: newOrder, hidden: newHidden }); ov.remove();
  });
}

function showTransit() {
  state.view = "transit";
  renderTabs();
  setPanelVisible("transitPanel");
  loadTransit();
}

function transitMsg(msg, isErr) {
  const el = $("transitMsg");
  el.textContent = msg || "";
  el.className = isErr ? "hint err-text" : "hint ok-text";
}

async function loadTransit() {
  const msg = $("transitCount");
  msg.textContent = "加载中…";
  try {
    const data = await api("/api/transit");
    _transitRecords = data.records || [];
    renderTransit();
    msg.textContent = "共 " + _transitRecords.length + " 个柜" + (data.generated_at ? " · 更新于 " + data.generated_at : "");
  } catch (e) {
    msg.textContent = "⚠ " + e.message;
  }
}

function transitFiltered() {
  const kw = $("transitSearch").value.trim().toLowerCase();
  const st = $("transitStatus").value;
  let list = _transitRecords.filter((r) => {
    if (st === "在途" && !(r.status === "在途" || r.status === "即将到港")) return false;
    if (st && st !== "在途" && r.status !== st) return false;
    if (!kw) return true;
    const hay = [
      r.container_no, r.so, r.shipping_line, r.vessel, r.voyage,
      r.pol, r.pod, r.etd, r.eta_so, r.eta_est, r.factory,
    ].join(" ").toLowerCase();
    if (fuzzyMatch(hay, kw)) return true;
    return (r.lines || []).some((l) =>
      fuzzyMatch(l.sku, kw) || fuzzyMatch(l.name, kw));
  });
  list.sort((a, b) => {
    const va = a.loading_date || "";
    const vb = b.loading_date || "";
    if (va < vb) return 1;
    if (va > vb) return -1;
    return 0;
  });
  return list;
}

function renderTransit() {
  const list = transitFiltered();
  renderTransitCards(list);
  const esc = escapeHtml;
  const vis = getColOrder(_transitColKey, _transitColDefs.map((c) => c.key));
  const hidden = new Set((_transitColDefs.map((c) => c.key)).filter((k) => !vis.includes(k)));
  const shown = _transitColDefs.filter((c) => !hidden.has(c.key));
  const head = $("transitHead");
  const colCount = shown.length;
  let hhtml = "<tr>";
  for (const c of shown) {
    if (c.key === "check") hhtml += '<th class="th-check"><input type="checkbox" id="transitCheckAll"></th>';
    else hhtml += `<th>${esc(c.label)}</th>`;
  }
  hhtml += "</tr>";
  head.innerHTML = hhtml;
  const body = $("transitBody");
  body.innerHTML = "";
  if (!list.length) {
    body.innerHTML = `<tr><td colspan="${colCount}" class="empty">暂无记录</td></tr>`;
    updateBatchBar();
    return;
  }
  for (const r of list) {
    const eta = r.eta_est;
    const etaLabel = eta
      ? esc(eta) + (r.eta_basis === "so" ? '<span class="muted">(SO)</span>' : '<span class="muted">(推算)</span>')
      : "—";
    const days = r.days_left;
    const daysLabel = days === null || days === undefined ? "—" : (days < 0 ? "已到" + (-days) + "天" : days + "天");
    const statusCls = r.status === "已到港" ? "tag-arrived" : r.status === "即将到港" ? "tag-soon" : r.status === "在途" ? "tag-transit" : r.status === "国内查验" || r.status === "国外查验" ? "tag-inspection" : r.status === "延误" ? "tag-delay" : r.status === "甩柜" ? "tag-roll" : "tag-none";
    const n = (r.lines || []).length;
    const checked = _transitSelected.has(r.id) ? "checked" : "";
    const rowCls = _transitSelected.has(r.id) ? "row-selected" : "";
    const cells = [];
    for (const c of shown) {
      if (c.key === "check") cells.push(`<td class="td-check"><input type="checkbox" class="transit-check" data-id="${esc(r.id)}" ${checked}></td>`);
      else if (c.key === "container_no") cells.push(`<td class="mono link">${esc(r.container_no) || "无柜号"}</td>`);
      else if (c.key === "so") cells.push(`<td class="link">${esc(r.so) || "—"}</td>`);
      else if (c.key === "shipping_line") cells.push(`<td>${esc(r.shipping_line) || "—"}</td>`);
      else if (c.key === "vessel") cells.push(`<td>${esc(r.vessel || "")}${r.voyage ? " / " + esc(r.voyage) : ""}</td>`);
      else if (c.key === "loading_date") cells.push(`<td>${esc(r.loading_date) || "—"}</td>`);
      else if (c.key === "pol") cells.push(`<td>${esc(r.pol) || "—"}</td>`);
      else if (c.key === "pod") cells.push(`<td>${esc(r.pod) || "—"}</td>`);
      else if (c.key === "etd") cells.push(`<td>${esc(r.etd) || "—"}</td>`);
      else if (c.key === "eta_est") cells.push(`<td>${etaLabel}</td>`);
      else if (c.key === "days_left") cells.push(`<td class="num">${daysLabel}</td>`);
      else if (c.key === "status") cells.push(`<td><span class="tag ${statusCls}">${esc(r.status)}</span></td>`);
      else if (c.key === "factory") cells.push(`<td class="fact">${esc(r.factory) || "—"}</td>`);
      else if (c.key === "detail_btn") cells.push(`<td><button type="button" class="btn ghost btn-xs" data-open-detail="${esc(r.id)}">详情${n ? " (" + n + ")" : ""}</button></td>`);
      else if (c.key === "action") cells.push(`<td><button type="button" class="btn ghost btn-xs btn-del" data-id="${esc(r.id)}">删除</button></td>`);
    }
    body.insertAdjacentHTML("beforeend", `<tr class="${rowCls}" data-rid="${esc(r.id)}" data-open-detail="${esc(r.id)}">${cells.join("")}</tr>`);
  }
  updateBatchBar();
  rebindTransitCheckAll();
}

function updateBatchBar() {
  const bar = $("transitBatchBar");
  if (_transitSelected.size === 0) {
    bar.style.display = "none";
  } else {
    bar.style.display = "";
    $("transitBatchCount").textContent = "已选 " + _transitSelected.size + " 条";
  }
  const allCheck = $("transitCheckAll");
  const checks = document.querySelectorAll(".transit-check");
  const total = checks.length;
  const checked = [...checks].filter((c) => c.checked).length;
  allCheck.checked = total > 0 && checked === total;
  allCheck.indeterminate = checked > 0 && checked < total;
}

async function batchDeleteTransit() {
  if (!_transitSelected.size) return;
  if (!confirm("确认删除选中的 " + _transitSelected.size + " 条记录？")) return;
  try {
    const data = await api("/api/transit/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: [..._transitSelected], action: "delete" }),
    });
    _transitRecords = data.records || [];
    _transitSelected.clear();
    renderTransit();
    transitMsg(data.deleted ? "已删除 " + data.deleted + " 条" : "无删除", false);
  } catch (e) {
    transitMsg("⚠ " + e.message, true);
  }
}

async function batchUpdateStatus() {
  if (!_transitSelected.size) return;
  const status = $("transitBatchStatus").value;
  try {
    const data = await api("/api/transit/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: [..._transitSelected], action: "update_status", manual_status: status }),
    });
    _transitRecords = data.records || [];
    _transitSelected.clear();
    renderTransit();
    transitMsg(data.updated ? "已更新 " + data.updated + " 条状态" : "无更新", false);
  } catch (e) {
    transitMsg("⚠ " + e.message, true);
  }
}

function renderTransitCards(list) {
  const esc = escapeHtml;
  const cnt = { "在途": 0, "即将到港": 0, "已到港": 0, "无ETA": 0 };
  for (const r of list) cnt[r.status] = (cnt[r.status] || 0) + 1;
  const inTransitAll = cnt["在途"] + cnt["即将到港"];
  const card = (title, cls, n) => `
    <div class="card ${cls}">
      <div class="c-name">${esc(title)}</div>
      <div class="c-meta">当前筛选</div>
      <div class="c-body"><div><div class="c-num">${n.toLocaleString()}</div><div class="c-label">个柜</div></div></div>
    </div>`;
  $("transitCards").innerHTML =
    card("全部", "", list.length) +
    card("在途(含即将到港)", "tag-transit", inTransitAll) +
    card("已到港", "tag-arrived", cnt["已到港"]) +
    card("无ETA", "tag-none", cnt["无ETA"]);
}

/* ---------------- 在途 SKU 汇总 ---------------- */

let _transitSummary = null;

async function loadTransitSummary(force) {
  const msg = $("transitSumMsg");
  try {
    if (force || !_transitSummary) {
      const d = await api("/api/transit/summary" + (force ? "?force=1" : ""));
      _transitSummary = d;
    }
    renderTransitSummary();
  } catch (e) {
    if (msg) msg.textContent = "⚠ " + e.message;
  }
}

function toggleTransitSum() {
  const wrap = $("transitSumWrap");
  const btn = $("transitSkuSumBtn");
  const show = wrap.style.display === "none";
  wrap.style.display = show ? "" : "none";
  btn.textContent = show ? "收起汇总" : "按 SKU 汇总";
  if (show) loadTransitSummary(false);
}

function renderTransitSummary() {
  const d = _transitSummary;
  const msg = $("transitSumMsg");
  if (!d || !d.ok) { if (msg) msg.textContent = "暂无汇总数据"; return; }
  const esc = escapeHtml;
  const s = d.summary || {};
  const comboSets = Object.entries(s.combosets || {});
  $("transitSumStats").innerHTML =
    `<span class="stat-item ok"><b>${(s.containers || 0).toLocaleString()}</b> 在途柜</span>` +
    `<span class="stat-item ok"><b>${Math.round(s.qty || 0).toLocaleString()}</b> 在途件</span>` +
    `<span class="stat-item${comboSets.length ? " warn" : ""}"><b>${comboSets.length.toLocaleString()}</b> 可成套组合</span>` +
    (comboSets.length
      ? `<span class="stat-item"><b>${comboSets.map(([k, v]) => `${esc(k)} ${Math.round(v).toLocaleString()}套`).join("、")}</b></span>`
      : "");

  // 时间轴
  const tl = s.timeline || {};
  const tlDef = ["7天", "14天", "30天", "超30天"];
  const tlMax = Math.max(1, ...tlDef.map((k) => (tl[k] || {}).containers || 0));
  $("transitTimeline").innerHTML =
    `<div class="tl-label">预计到港</div>` + tlDef.map((k) => {
      const v = (tl[k] || {}).containers || 0;
      const w = Math.max(4, Math.round((v / tlMax) * 100));
      return `<div class="tl-item"><span class="tl-k">${k}</span><div class="tl-track"><div class="tl-fill" style="width:${w}%"></div></div><span class="tl-v">${v} 柜</span></div>`;
    }).join("");

  // 目的港 / 工厂分布
  const dist = (pairs, max) => (pairs || []).slice(0, max)
    .map(([k, n]) => `<span class="chip">${esc(k)} <b>${n}</b></span>`).join("") || '<span class="muted">—</span>';
  $("transitPods").innerHTML = `<span class="dist-label">目的港</span>` + dist(d.pod_dist, 8);
  $("transitFactories").innerHTML = `<span class="dist-label">工厂</span>` + dist(d.fac_dist, 8);

  // SKU 表（在途量 对照 当前库存）
  const escSku = esc;
  const invBySku = _inventoryBySku();
  const rows = (d.by_sku || []).map((r) => {
    const typeTag = r.type === "combo"
      ? '<span class="tag tag-soon">组合</span>'
      : r.type === "component"
        ? '<span class="tag tag-transit">子件</span>'
        : '<span class="tag tag-badge">非组合</span>';
    const inv = invBySku.get(r.sku);
    const invTxt = inv === undefined ? "—" : Math.round(inv).toLocaleString();
    return `<tr>
      <td class="mono">${escSku(r.sku) || "—"}</td>
      <td>${escSku(r.name) || "—"}</td>
      <td>${typeTag}</td>
      <td class="num"><b>${Math.round(r.qty).toLocaleString()}</b></td>
      <td class="num">${r.containers}</td>
      <td class="mono">${escSku(r.eta_min) || "—"}</td>
      <td>${escSku((r.pods || []).join("、")) || "—"}</td>
      <td class="mono">${escSku(r.combo_sku) || "—"}</td>
      <td class="num">${invTxt}</td>
    </tr>`;
  }).join("");
  const head = document.querySelector("#transitSumWrap thead tr");
  if (head && !head.querySelector("th:last-child").textContent.includes("当前库存")) {
    head.insertAdjacentHTML("beforeend", "<th>当前库存</th>");
  }
  $("transitSumBody").innerHTML = rows || '<tr><td colspan="9" class="empty">暂无在途 SKU 明细</td></tr>';
}

/* 汇总各仓库当前库存到 SKU 维度（供在途对照） */
function _inventoryBySku() {
  const m = new Map();
  const data = (typeof state !== "undefined" && state.inv) || null;
  if (!data) return m;
  for (const [, w] of Object.entries(data.warehouses || {})) {
    if (w.status !== "ok") continue;
    for (const p of w.points || []) {
      for (const r of p.rows || []) {
        if (!r.sku) continue;
        m.set(r.sku, (m.get(r.sku) || 0) + Number(r.qty || 0));
      }
    }
  }
  return m;
}

function exportTransit() {
  const list = transitFiltered();
  const head = ["柜号", "SO号", "船公司", "船名", "航次", "装柜时间", "起运港", "目的港", "离港ETD", "实际开船", "预计到港ETA", "实际到港", "ETA依据", "剩余天数", "状态", "工厂", "SKU", "品名", "数量"];
  const rows = [];
  for (const r of list) {
    const lines = (r.lines && r.lines.length) ? r.lines : [{ sku: "", name: "", qty: "" }];
    for (const l of lines) {
      rows.push([
        r.container_no || "无柜号", r.so || "", r.shipping_line || "", r.vessel || "", r.voyage || "",
        r.loading_date || "", r.pol || "", r.pod || "", r.etd || "", r.actual_sail_date || "",
        r.eta_est || "", r.actual_arrival_date || "",
        r.eta_basis || "", r.days_left === null || r.days_left === undefined ? "" : r.days_left,
        r.status || "", r.factory || "", l.sku || "", l.name || "", l.qty || "",
      ]);
    }
  }
  const csv = [head, ...rows].map((row) =>
    row.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(",")
  ).join("\r\n");
  downloadCsv("transit_" + new Date().toISOString().slice(0, 10) + ".csv", csv);
}

async function importTransitFiles() {
  const input = $("transitFiles");
  const files = input.files;
  if (!files.length) { transitMsg("请先选择文件", true); return; }
  transitMsg("导入中…");
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  try {
    const data = await api("/api/transit/import", { method: "POST", body: fd });
    _transitRecords = data.records || [];
    renderTransit();
    const parts = [];
    if (data.added) parts.push("新增 " + data.added + " 条");
    if (data.updated) parts.push("更新 " + data.updated + " 条");
    if (data.matched) parts.push("匹配 " + data.matched + " 柜");
    const w = data.warnings && data.warnings.length ? "；提示：" + data.warnings.slice(0, 3).join("；") + (data.warnings.length > 3 ? " 等" : "") : "";
    const e = data.errors && data.errors.length ? "；失败：" + data.errors.join("；") : "";
    transitMsg((parts.length ? parts.join("，") : "无新增记录") + w + e, !!(data.errors && data.errors.length));
  } catch (err) {
    transitMsg("⚠ " + err.message, true);
  } finally {
    input.value = "";
  }
}

async function scanSOs() {
  const input = $("transitSOFiles");
  const files = input.files;
  if (!files.length) { transitMsg("请先选择 SO PDF 文件", true); return; }
  transitMsg("解析 SO PDF 中…");
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  try {
    const data = await api("/api/transit/scan-sos", { method: "POST", body: fd });
    _transitRecords = data.records || [];
    renderTransit();
    const parts = [];
    parts.push("上传 " + data.uploaded + " 个");
    parts.push("识别 " + data.parsed + " 个 SO");
    if (data.matched) parts.push("匹配 " + data.matched + " 条");
    if (data.updated) parts.push("更新 " + data.updated + " 条");
    if (data.duplicates && data.duplicates.length) {
      parts.push("重复 " + data.duplicates.length + " 个");
    }
    const e = data.errors && data.errors.length ? "；" + data.errors.slice(0, 3).join("；") : "";
    transitMsg(parts.join("，") + e, false);
  } catch (err) {
    transitMsg("⚠ " + err.message, true);
  } finally {
    input.value = "";
  }
}

async function addTransitManual() {
  const cno = $("transitManualCno").value.trim();
  const so = $("transitManualSo").value.trim();
  if (!cno && !so) { transitMsg("请填写柜号或 SO 号", true); return; }
  transitMsg("添加中…");
  const fd = new FormData();
  fd.append("container_no", cno);
  fd.append("so", so);
  try {
    const data = await api("/api/transit/import", { method: "POST", body: fd });
    _transitRecords = data.records || [];
    renderTransit();
    const w = data.warnings && data.warnings.length ? "；提示：" + data.warnings.join("；") : "";
    transitMsg(data.updated ? "已更新已有记录" + w : "已添加" + (cno ? " 柜号 " + cno : "") + (so ? " SO " + so : "") + w, false);
  } catch (err) {
    transitMsg("⚠ " + err.message, true);
  } finally {
    $("transitManualCno").value = "";
    $("transitManualSo").value = "";
  }
}

let _productsCache = null;

async function _getProducts() {
  if (!_productsCache) {
    const d = await api("/api/products");
    _productsCache = d.products || [];
  }
  return _productsCache;
}

async function openTransitDetail(id) {
  const r = _transitRecords.find((x) => x.id === id);
  if (!r) return;
  const esc = escapeHtml;
  $("transitModalTitle").textContent = (r.container_no || "无柜号") + (r.so ? " · " + r.so : "");
  _renderDetailGrid(r);
  $("editSave").onclick = async () => {
    const body = {};
    $("transitDetailGrid").querySelectorAll(".detail-input").forEach((el) => {
      body[el.getAttribute("data-field")] = el.value;
    });
    try {
      await api("/api/transit/" + encodeURIComponent(id), { method: "PUT", body: JSON.stringify(body), headers: {"Content-Type": "application/json"} });
      await loadTransit();
      openTransitDetail(id);
    } catch (e) { alert("保存失败: " + e.message); }
  };
  const lines = r.lines || [];
  const products = await _getProducts();
  const knownSkus = new Set(products.map((p) => p.sku));
  const compSkuSet = new Set();
  for (const p of products) {
    for (const c of (p.components || [])) {
      knownSkus.add(c);
      compSkuSet.add(c);
    }
  }
  const comboCompMap = {};
  for (const p of products) {
    if (p.type === "combo" && p.components && p.components.length) {
      comboCompMap[p.sku] = p.components;
    }
  }
  let compQty = 0, standQty = 0;
  const comboCompQty = {};
  const missingSkus = [];
  const isRealSku = (s) => s && /[A-Za-z0-9]/.test(s);
  const rows = lines.map((l) => {
    let sku = String(l.sku || "");
    let name = String(l.name || "").trim();
    const q = Number(l.qty || 0);
    const lineType = l.type || "standalone";
    const qtyLabel = q.toLocaleString();
    if (!name && sku && !isRealSku(sku)) {
      name = sku;
      sku = "";
    }
    let tag;
    if (lineType === "combo") {
      tag = `<span class="tag tag-soon">组合 · ${qtyLabel} 套</span>`;
    } else if (lineType === "component") {
      compQty += q;
      const parent = l.combo_sku || "";
      if (parent) {
        if (!comboCompQty[parent]) comboCompQty[parent] = {};
        comboCompQty[parent][sku] = (comboCompQty[parent][sku] || 0) + q;
      }
      tag = `<span class="tag tag-transit">子件 · ${qtyLabel} 件</span>` + (parent ? ` <span class="muted">→ ${esc(parent)}</span>` : "");
    } else {
      standQty += q;
      tag = `<span class="tag tag-transit">非组合 · ${qtyLabel} 件</span>`;
      if (isRealSku(sku) && !knownSkus.has(sku) && !missingSkus.includes(sku)) missingSkus.push(sku);
    }
    return `<tr><td>${esc(name) || "—"}</td><td class="muted">${esc(sku) || "—"}</td><td class="num">${qtyLabel}</td><td class="num">${q.toLocaleString()}</td><td>${tag}</td></tr>`;
  }).join("");
  $("transitDetailLines").innerHTML = rows || '<tr><td colspan="5" class="empty">无明细</td></tr>';
  let comboSets = 0;
  for (const [combo, compQtys] of Object.entries(comboCompQty)) {
    const required = comboCompMap[combo] || Object.keys(compQtys);
    let minQty = Infinity;
    for (const cs of required) {
      const have = compQtys[cs] || 0;
      if (have < minQty) minQty = have;
    }
    if (minQty !== Infinity && minQty > 0) comboSets += minQty;
  }
  const warnHtml = missingSkus.length
    ? `<span class="stat-item warn"><b>!</b> 未匹配 SKU：${missingSkus.map(esc).join("、")}</span>`
    : "";
  $("transitDetailStats").innerHTML =
    `<span class="stat-item"><b>${compQty.toLocaleString()}</b> 总件数</span>` +
    `<span class="stat-item${comboSets ? " ok" : ""}"><b>${comboSets.toLocaleString()}</b> 组合套</span>` +
    `<span class="stat-item${compQty ? " ok" : ""}"><b>${compQty.toLocaleString()}</b> 子件</span>` +
    `<span class="stat-item${standQty ? " ok" : ""}"><b>${standQty.toLocaleString()}</b> 非组合</span>` +
    warnHtml;
  $("transitModal").classList.remove("hidden");
}

function closeTransitDetail() {
  $("transitModal").classList.add("hidden");
}

async function deleteTransit(id) {
  if (!confirm("确认删除该在途记录？")) return;
  try {
    const data = await api("/api/transit/" + encodeURIComponent(id), { method: "DELETE" });
    _transitRecords = _transitRecords.filter((r) => r.id !== id);
    renderTransit();
    transitMsg(data.ok ? "已删除" : "删除失败", !data.ok);
  } catch (e) {
    transitMsg("⚠ " + e.message, true);
  }
}

function rebindTransitCheckAll() {
  const el = $("transitCheckAll");
  if (!el) return;
  el.addEventListener("change", (e) => {
    const list = transitFiltered();
    if (e.target.checked) {
      list.forEach((r) => _transitSelected.add(r.id));
    } else {
      list.forEach((r) => _transitSelected.delete(r.id));
    }
    renderTransit();
  });
}

function initTransit() {
  $("transitImport").addEventListener("click", importTransitFiles);
  $("transitSkuSumBtn").addEventListener("click", toggleTransitSum);
  $("transitRefreshBtn").addEventListener("click", () => loadTransitSummary(true));
  $("transitScanSO").addEventListener("click", () => { $("transitSOFiles").value = ""; $("transitSOFiles").click(); });
  $("transitSOFiles").addEventListener("change", scanSOs);
  $("transitManualAdd").addEventListener("click", addTransitManual);
  $("transitRefresh").addEventListener("click", () => loadTransit());
  $("transitExport").addEventListener("click", exportTransit);
  $("transitSearch").addEventListener("input", renderTransit);
  $("transitStatus").addEventListener("change", renderTransit);
  $("transitColSettings").addEventListener("click", () => {
    showColSettings(_transitColKey, _transitColDefs, renderTransit);
  });
  $("transitBody").addEventListener("change", (e) => {
    if (e.target.classList.contains("transit-check")) {
      const id = e.target.getAttribute("data-id");
      if (e.target.checked) {
        _transitSelected.add(id);
      } else {
        _transitSelected.delete(id);
      }
      const tr = e.target.closest("tr");
      if (tr) tr.classList.toggle("row-selected", e.target.checked);
      updateBatchBar();
    }
  });

  // Batch actions
  $("transitBatchDelete").addEventListener("click", batchDeleteTransit);
  $("transitBatchStatusApply").addEventListener("click", batchUpdateStatus);
  $("transitBatchClear").addEventListener("click", () => {
    _transitSelected.clear();
    renderTransit();
  });

  // Row clicks
  $("transitBody").addEventListener("click", (e) => {
    if (e.target.classList.contains("btn-del")) {
      deleteTransit(e.target.getAttribute("data-id"));
      return;
    }
    if (e.target.classList.contains("transit-check") || e.target.closest(".td-check")) return;
    const trig = e.target.closest("[data-open-detail]");
    if (trig) openTransitDetail(trig.getAttribute("data-open-detail"));
  });

  document.querySelectorAll("[data-close-modal]").forEach((b) => b.addEventListener("click", closeTransitDetail));
  $("transitDetailSettings").addEventListener("click", _showDetailSettings);
  const mask = $("transitModal");
  mask.addEventListener("click", (e) => { if (e.target === mask) closeTransitDetail(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !mask.classList.contains("hidden")) closeTransitDetail();
  });
}
