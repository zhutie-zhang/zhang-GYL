/* 库龄统计 - 独立顶部Tab模块
   数据源：/api/inventory/age?force=1
   按批次(上架日期)粒度展示，逐档预警：≤15天灰 / 16-30绿 / 31-45黄 / 46-60橙 / 61-120红 / >120严重整行标红。
   数据模型：每行 = 数据源 + 仓库 + SKU + 产品名 + 批次(上架日期) + 数量 + 在库天数。 */

let _agData = null;
let _agState = { wh: "", group: "", band: "", cat: "", filter: "", page: 1, pageSize: 25 };

function _agBandOf(age) {
  const a = age === undefined || age === null || isNaN(age) ? 0 : Number(age);
  if (a <= 15) return "g";        // 灰，正常
  if (a <= 30) return "green";    // 15天以上绿
  if (a <= 45) return "yellow";   // 30天以上黄
  if (a <= 60) return "orange";   // 45天以上橙
  if (a <= 120) return "red";     // 60天以上红
  return "sev";                   // 120天以上严重
}

function _agBandLabel(b) {
  switch (b) {
    case "g": return "≤15";
    case "green": return "16-30";
    case "yellow": return "31-45";
    case "orange": return "46-60";
    case "red": return "61-120";
    case "sev": return "120+";
  }
  return "";
}

function _agCatBadge(r) {
  const c = r.cat || "standalone";
  const label = r.cat_label || (c === "kit" ? "组合产品" : c === "part" ? "组合不成套" : "非组合");
  const cls = c === "kit" ? "badge-combo" : c === "part" ? "badge-part" : "badge-standalone";
  return `<span class="badge ${cls}">${escapeHtml(label)}</span>`;
}

function _agAllRows() {
  const rows = [];
  if (!_agData || !_agData.warehouses) return rows;
  for (const wid of Object.keys(_agData.warehouses)) {
    const w = _agData.warehouses[wid];
    if (w.status !== "ok") continue;
    if (_agState.wh && wid !== _agState.wh) continue;
    if (_agState.group && w.group !== _agState.group) continue;
    for (const r of (w.rows || [])) {
      rows.push({
        acc: w.name || wid,
        acc_id: wid,
        wh: r.wh_name || r.wh || w.name || wid,
        sku: r.sku,
        name: r.name,
        qty: r.qty,
        age: r.age_days,
        batch: r.shelf_date,      // 批次 = 上架日期
        stat: r.statistic_date,
        unit: r.unit,
        volume: r.volume_cm3,
        cat: r.cat,               // kit / part / standalone
        cat_label: r.cat_label,
        kit_sku: r.kit_sku,
      });
    }
  }
  return rows;
}

function _agFilteredRows() {
  const f = (_agState.filter || "").trim().toLowerCase();
  const bandKey = {
    "15": "green", "30": "yellow", "45": "orange", "60": "red", "120": "sev",
  }[_agState.band] || "";
  return _agAllRows().filter((r) => {
    if (bandKey && _agBandOf(r.age) !== bandKey) return false;
    if (_agState.cat && (r.cat || "") !== _agState.cat) return false;
    if (f && !(fuzzyMatch(r.sku, f) ||
               fuzzyMatch(r.name, f))) return false;
    return true;
  });
}

function _agRenderSources() {
  const sel = $("agWh");
  if (!sel || !_agData) return;
  const opts = [`<option value="">全部仓库</option>`];
  for (const wid of Object.keys(_agData.warehouses || {})) {
    const w = _agData.warehouses[wid];
    if (w.status !== "ok") continue;
    opts.push(`<option value="${escapeHtml(wid)}">${escapeHtml(w.name || wid)}</option>`);
  }
  sel.innerHTML = opts.join("");

  const gsel = $("agGroup");
  gsel.innerHTML = `<option value="">全部分组</option>` +
    (_agData.groups || []).map((g) => `<option value="${escapeHtml(g.id)}">${escapeHtml(g.name || g.id)}</option>`).join("");
}

function _agRenderCards() {
  const cards = $("agCards");
  if (!cards) return;
  const rows = _agAllRows();
  const totalQty = rows.reduce((s, r) => s + (r.qty || 0), 0);
  const totalBatches = rows.length;
  const maxAge = rows.length ? Math.max.apply(null, rows.map((r) => Number(r.age) || 0)) : 0;
  const quants = { g: 0, green: 0, yellow: 0, orange: 0, red: 0, sev: 0 };
  const catQty = { kit: 0, part: 0, standalone: 0 };
  const catSku = { kit: 0, part: 0, standalone: 0 };
  rows.forEach((r) => {
    const b = _agBandOf(r.age);
    quants[b] += (r.qty || 0);
    const c = r.cat || "standalone";
    catQty[c] += (r.qty || 0);
    if (String(r.sku || "").trim()) catSku[c] += 1;
  });

  const defs = [
    { b: "g", label: "正常 ≤15天", cls: "ag-card-gray" },
    { b: "green", label: "15天以上·绿", cls: "ag-card-green" },
    { b: "yellow", label: "30天以上·黄", cls: "ag-card-yellow" },
    { b: "orange", label: "45天以上·橙", cls: "ag-card-orange" },
    { b: "red", label: "60天以上·红", cls: "ag-card-red" },
    { b: "sev", label: "120天+·严重", cls: "ag-card-sev" },
  ];
  const catDefs = [
    { c: "kit", label: "组合产品", cls: "ag-cat-kit", add: "成套组合" },
    { c: "standalone", label: "非组合产品", cls: "ag-cat-std", add: "独立单品" },
    { c: "part", label: "组合产品不成套", cls: "ag-cat-part", add: "缺件子件" },
  ];
  let html = `<div class="stat-card ag-card-total"><div class="stat-label">参与统计数量</div>
      <div class="stat-value">${totalQty.toLocaleString()}</div>
      <div class="stat-sub">批次 ${totalBatches} 条 · 最长库龄 ${maxAge} 天</div></div>`;
  html += catDefs.map((d) => {
    const q = catQty[d.c] || 0;
    const pct = totalQty > 0 ? (q / totalQty * 100).toFixed(1) : "0.0";
    return `<div class="stat-card ${d.cls}"><div class="stat-label">${d.label}</div>
      <div class="stat-value">${q.toLocaleString()}</div>
      <div class="stat-sub">${d.add} · ${catSku[d.c]} 个批次 · 占比 ${pct}%</div></div>`;
  }).join("");
  defs.forEach((d) => {
    const q = quants[d.b] || 0;
    const pct = totalQty > 0 ? (q / totalQty * 100).toFixed(1) : "0.0";
    html += `<div class="stat-card ${d.cls}"><div class="stat-label">${d.label}</div>
      <div class="stat-value">${q.toLocaleString()}</div>
      <div class="stat-sub">占比 ${pct}%</div></div>`;
  });
  cards.innerHTML = html;
}

function _agRenderTable() {
  let all = _agFilteredRows();
  const total = all.length;
  all = all.slice().sort((a, b) => {
    const byAge = (Number(b.age) || 0) - (Number(a.age) || 0);
    if (byAge) return byAge;
    return String(a.sku || "").localeCompare(String(b.sku || ""), "zh");
  });
  const size = _agState.pageSize;
  const pages = Math.max(1, Math.ceil(total / size));
  if (_agState.page > pages) _agState.page = pages;
  if (_agState.page < 1) _agState.page = 1;
  const start = (_agState.page - 1) * size;
  const pageRows = all.slice(start, start + size);

  const head = $("agHead");
  const body = document.querySelector("#agTable tbody");
  if (!head || !body) return;

  head.innerHTML = "<tr><th>数据源</th><th>仓库</th><th>SKU</th><th>产品名称</th>" +
    "<th>组合分类</th><th>批次/上架日期</th><th>数量</th><th>在库天数</th><th>预警档</th><th>统计日期</th></tr>";

  if (!all.length) {
    body.innerHTML = `<tr><td colspan="10" style="text-align:center;color:#999;padding:18px">
      ${_agData ? "该筛选下暂无库龄数据" : "暂无数据，请点击「加载库龄」"}</td></tr>`;
  } else {
    body.innerHTML = pageRows.map((r) => {
      const band = _agBandOf(r.age);
      const cls = band === "g" ? "ag-gray" : band === "green" ? "ag-green"
        : band === "yellow" ? "ag-yellow" : band === "orange" ? "ag-orange"
        : band === "red" ? "ag-red" : "ag-sev";
      // 120天以上整行全字段标红（严重）
      const rowCls = band === "sev" ? "ag-row-sev" : "";
      const ageCell = band === "sev"
        ? `<b class="ag-sev-text">${Math.round(r.age)} 天 ⚠严重</b>`
        : `<b class="${cls.replace("ag-", "ag-")}">${Math.round(r.age)}</b>`;
      const batchCell = band === "sev" ? `<span class="ag-sev-text">${escapeHtml(r.batch) || "—"}</span>` : (escapeHtml(r.batch) || "—");
      return `<tr class="${rowCls}">
        <td>${escapeHtml(r.acc)}</td>
        <td>${escapeHtml(r.wh)}</td>
        <td>${escapeHtml(r.sku)}</td>
        <td>${escapeHtml(r.name)}</td>
        <td>${_agCatBadge(r)}</td>
        <td>${batchCell}</td>
        <td>${(r.qty || 0).toLocaleString()}</td>
        <td>${ageCell}</td>
        <td><span class="age-badge ${cls}">${_agBandLabel(band)}天</span></td>
        <td>${escapeHtml(r.stat) || "—"}</td>
      </tr>`;
    }).join("");
  }

  $("agRange").textContent = `共 ${total} 条`;
  $("agInfo").textContent = `${_agState.page} / ${pages} 页`;
  $("agPrev").disabled = _agState.page <= 1;
  $("agNext").disabled = _agState.page >= pages;
}

async function _agLoad(force) {
  const msg = $("agMsg");
  if (!msg) return;
  msg.textContent = "加载中…";
  try {
    const data = await api("/api/inventory/age" + (force ? "?force=1" : ""));
    _agData = data;
    _agState.page = 1;
    const w = _agData.warehouses || {};
    const ok = Object.values(w).filter((x) => x.status === "ok").length;
    const err = Object.values(w).filter((x) => x.status === "error").length;
    const un = Object.values(w).filter((x) => x.status === "unsupported").length;
    const unList = Object.values(w).filter((x) => x.status === "unsupported").map((x) => x.name);
    _agRenderSources();
    _agRenderCards();
    _agRenderTable();
    msg.textContent = `更新于 ${data.generated_at} · 已接入库龄 ${ok} 家 · 暂不支持/失败 ${err + un} 家` +
      (unList.length ? `（${unList.slice(0, 8).join("、")}${unList.length > 8 ? "…" : ""}）` : "");
  } catch (e) {
    msg.textContent = "加载失败: " + e.message;
  }
}

function _agExport() {
  const rows = _agFilteredRows().sort((a, b) => (Number(b.age) || 0) - (Number(a.age) || 0));
  const catName = (r) => r.cat_label || (r.cat === "kit" ? "组合产品" : r.cat === "part" ? "组合不成套" : "非组合");
  const lines = ["数据源,仓库,SKU,产品名称,组合分类,批次/上架日期,数量,在库天数,预警档,统计日期"];
  rows.forEach((r) => {
    lines.push([r.acc, r.wh, r.sku, r.name, catName(r), r.batch, r.qty, r.age, _agBandLabel(_agBandOf(r.age)), r.stat]
      .map((c) => `"${String(c == null ? "" : c).replace(/"/g, '""')}"`).join(","));
  });
  downloadCsv("商品库龄统计.csv", lines.join("\r\n"));
}

function showAge() {
  state.view = "age";
  renderTabs();
  setPanelVisible("agePanel");
  _agRenderSources();
  _agRenderCards();
  _agRenderTable();
  if (!_agData) _agLoad(false);
}

function _agBind() {
  [["agWh", "wh"], ["agGroup", "group"], ["agBand", "band"], ["agCat", "cat"]].forEach(([id, key]) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("change", (e) => { _agState[key] = e.target.value; _agState.page = 1; _agRenderTable(); _agRenderCards(); });
  });
  const pageSel = $("agPageSize");
  if (pageSel) pageSel.addEventListener("change", (e) => { _agState.pageSize = Number(e.target.value); _agState.page = 1; _agRenderTable(); });
  const f = $("agFilter");
  if (f) f.addEventListener("input", (e) => { _agState.filter = e.target.value; _agState.page = 1; _agRenderTable(); });
  const loadBtn = $("agLoadBtn");
  if (loadBtn) loadBtn.addEventListener("click", () => _agLoad(true));
  const exp = $("agExport");
  if (exp) exp.addEventListener("click", _agExport);
  const prev = $("agPrev");
  if (prev) prev.addEventListener("click", () => { if (_agState.page > 1) { _agState.page--; _agRenderTable(); } });
  const next = $("agNext");
  if (next) next.addEventListener("click", () => { _agState.page++; _agRenderTable(); });
}

document.addEventListener("DOMContentLoaded", _agBind);
