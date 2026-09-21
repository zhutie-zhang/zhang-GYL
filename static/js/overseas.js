/* 海外仓统一看板模块：所有海外仓合并展示，支持选择单个仓库筛选，含出库/库存完整表格 */

/* ---- 仓库选择器 ---- */

function renderOverseasSelector() {
  const wrap = $("overseasSelector");
  if (!wrap) return;
  wrap.innerHTML = "";

  const allBtn = document.createElement("button");
  allBtn.type = "button";
  allBtn.className = "btn " + (!state.overseasWh ? "primary" : "ghost");
  allBtn.textContent = "全部仓库";
  allBtn.addEventListener("click", () => switchOverseasWh(""));
  wrap.appendChild(allBtn);

  for (const g of state.groups) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn " + (state.overseasWh === g.id ? "primary" : "ghost");
    btn.textContent = g.name;
    btn.addEventListener("click", () => switchOverseasWh(g.id));
    wrap.appendChild(btn);
  }
}

/* ---- 概览卡片 ---- */

function renderOverseasCards() {
  const wrap = $("overseasCards");
  if (!wrap) return;
  wrap.innerHTML = "";
  if (!state.inv || !state.out) return;

  const iUnits = allPointUnits(state.inv);
  const oUnits = allPointUnits(state.out);

  if (!state.overseasWh) {
    wrap.appendChild(overviewCardDom("全部仓合计",
      `${iUnits.length} 个仓点 · 库存 + 出库汇总`,
      sumStats(iUnits), sumStats(oUnits), true, () => openStats("inv", "all")));
    for (const g of state.groups) {
      const iu = iUnits.filter((p) => p.group === g.id);
      if (!iu.length) continue;
      const ou = oUnits.filter((p) => p.group === g.id);
      wrap.appendChild(overviewCardDom(g.name, `${iu.length} 个仓点`,
        sumStats(iu), sumStats(ou), false, () => switchOverseasWh(g.id)));
    }
  } else {
    const iu = iUnits.filter((p) => p.group === state.overseasWh);
    const ou = oUnits.filter((p) => p.group === state.overseasWh);
    wrap.appendChild(overviewCardDom(groupName(state.overseasWh) + " 合计",
      `${iu.length} 个仓点`, sumStats(iu), sumStats(ou), true,
      () => openStats("inv", "group:" + state.overseasWh)));
    const byAcct = new Map();
    for (const p of iu) {
      if (!byAcct.has(p.whId)) byAcct.set(p.whId, { id: p.whId, name: p.whName, ipts: [], opts: [] });
      byAcct.get(p.whId).ipts.push(p);
    }
    for (const p of ou) {
      if (!byAcct.has(p.whId)) byAcct.set(p.whId, { id: p.whId, name: p.whName, ipts: [], opts: [] });
      byAcct.get(p.whId).opts.push(p);
    }
    for (const [, a] of byAcct) {
      wrap.appendChild(overviewCardDom(a.name, `${a.ipts.length} 个仓点`,
        sumStats(a.ipts), sumStats(a.opts), false, () => openStats("inv", "wh:" + a.id)));
    }
  }
}

/* ---- 组合统计 ---- */

function _ovFilteredData(dataX) {
  if (!dataX) return null;
  if (!state.overseasWh) return dataX;
  const filtered = { warehouses: {} };
  for (const [whId, w] of Object.entries(dataX.warehouses || {})) {
    if (w.group === state.overseasWh) filtered.warehouses[whId] = w;
  }
  return filtered;
}

function _ovLoadScope() {
  if (!state.overseasWh) return "";
  return "group:" + state.overseasWh;
}

async function renderOverseasDashStats() {
  const src = $("ovStatsSource") ? $("ovStatsSource").value : "inv";
  const wrap = $("ovStatsCards");
  const tblWrap = $("ovStatsTables");
  if (!wrap || !tblWrap) return;

  const scope = state.overseasWh ? "group:" + state.overseasWh : "all";
  const srcLabel = src === "inv" ? "库存" : "出库";
  const scopeLabel = state.overseasWh ? groupName(state.overseasWh) : "全部海外仓";

  wrap.innerHTML = '<div class="sc-loading">统计计算中…</div>';
  tblWrap.innerHTML = "";

  try {
    const params = new URLSearchParams({ source: src, scope: scope });
    if (state.outStart) params.set("start", state.outStart);
    if (state.outEnd) params.set("end", state.outEnd);
    const res = await api("/api/stats?" + params.toString());
    const cats = res.categories || {};
    const boxes = res.boxes || { kit: 0, part: 0, standalone: 0, total: 0 };
    const kit = cats.kit || { sku_count: 0, qty: 0, container_count: 0 };
    const part = cats.part || { sku_count: 0, qty: 0, container_count: 0 };
    const standalone = cats.standalone || { sku_count: 0, qty: 0, container_count: 0 };
    const totalSkus = kit.sku_count + standalone.sku_count;
    const totalQty = kit.qty + standalone.qty;
    const totalPart = part.qty;
    const totalBox = boxes.total;

    wrap.innerHTML = `
      <div class="card card-combined">
        <div class="c-name">${escapeHtml(scopeLabel)} · ${srcLabel}合计</div>
        <div class="c-meta">${res.scope && res.scope.label ? escapeHtml(res.scope.label) : ""}</div>
        <div class="c-body">
          <div><div class="c-num">${totalSkus}</div><div class="c-label">SKU 数</div></div>
          <div><div class="c-num">${kit.qty.toLocaleString()}</div><div class="c-label">成套套数</div></div>
          <div><div class="c-num part-num">${totalPart.toLocaleString()}</div><div class="c-label">不成套件数</div></div>
          <div><div class="c-num">${standalone.qty.toLocaleString()}</div><div class="c-label">非组合件数</div></div>
          <div><div class="c-num box-total-num">${totalBox.toLocaleString()}</div><div class="c-label">总箱数</div></div>
        </div>
      </div>`;

    const items = res.items || [];
    const headsKit = ["仓库", "仓点", "SKU", "产品名称", "套数", "箱数"];
    const headsPart = ["仓库", "仓点", "SKU", "产品名称", "所属组合", "件数", "箱数"];
    const headsNone = ["仓库", "仓点", "SKU", "产品名称", "件数", "箱数"];
    const sums = (cat) => {
      const list = items.filter(it => it.category === cat);
      return {
        qty: list.reduce((s, it) => s + Number(it.qty || 0), 0),
        box: list.reduce((s, it) => s + Number(it.box || 0), 0),
      };
    };
    const esc = escapeHtml;
    const renderRows = (cat) => items.filter(it => it.category === cat).map(it =>
      `<td>${esc(it.warehouse)}</td><td>${esc(it.container)}</td><td class="sku-cell">${esc(it.sku)}</td><td title="${esc(it.name)}">${esc(it.name)}</td>` +
      (cat === "part" ? `<td class="sku-cell">${esc(it.kit || "—")}</td>` : "") +
      `<td class="num">${Number(it.qty || 0).toLocaleString()}</td><td class="num box-num">${Number(it.box || 0).toLocaleString()}</td>`
    );
    const foot = (sp, s) => `<tr class="tot-row"><td colspan="${sp}" class="tot-label">合计</td><td class="num">${s.qty.toLocaleString()}</td><td class="num box-num">${s.box.toLocaleString()}</td></tr>`;

    let tblHtml = "";
    const renderBlock = (title, subtitle, heads, rows, emptyText, footRow) => {
      const body = rows.length ? rows.map(r => `<tr>${r}</tr>`).join("") + (footRow || "")
        : `<tr><td colspan="${heads.length}" class="state-cell">${esc(emptyText)}</td></tr>`;
      return `<div class="stats-block"><div class="stats-block-head"><h3>${esc(title)}</h3><span class="hint">${esc(subtitle)}</span></div>
        <div class="table-wrap"><table class="prod-table"><thead><tr>${heads.map(h => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table></div></div>`;
    };

    const kitRows = renderRows("kit");
    const partRows = renderRows("part");
    const stdRows = renderRows("standalone");
    tblHtml += renderBlock("成套组合明细", "箱数 = 套数 × 子SKU数", headsKit, kitRows, "暂无成套组合", kitRows.length ? foot(4, sums("kit")) : "");
    tblHtml += renderBlock("不成套组合件明细", "不成套子件按SKU件数计箱", headsPart, partRows, "暂无不成套组合件", partRows.length ? foot(5, sums("part")) : "");
    tblHtml += renderBlock("无组合 SKU 明细", "非组合产品一件一箱", headsNone, stdRows, "暂无无组合 SKU", stdRows.length ? foot(4, sums("standalone")) : "");

    const zeroKits = res.zero_kits || [];
    const zk = cats.zero_kit || { sku_count: 0 };
    if (zk.sku_count) {
      tblHtml += `<div class="hint" style="margin-top:8px">另有 ${zk.sku_count} 个组合缺件、0 套可发：${zeroKits.map(z => esc(z.name ? `${z.sku}(${z.name})` : z.sku)).join("、")}</div>`;
    }
    tblWrap.innerHTML = tblHtml;
  } catch (e) {
    wrap.innerHTML = '<div class="sc-empty">统计加载失败: ' + escapeHtml(e.message) + '</div>';
  }
}

/* ---- 出库卡片（海外仓版） ---- */

const _ovState = {
  outSort: { col: "total", dir: -1 },
  outFilter: "",
  outPage: 1,
  outPageSize: 20,
  outPoint: "",
  outStart: "",
  outEnd: "",
  invSort: { col: "total", dir: -1 },
  invFilter: "",
  invPage: 1,
  invPageSize: 20,
};

function _ovCatLabel(r) {
  const t = r.tag;
  if (t === "kit") return "组合";
  if (t === "part") return "组合子件";
  return "非组合";
}

function _ovCatSort(r) {
  const t = r.tag;
  if (t === "kit") return 0;
  if (t === "part") return 1;
  return 2;
}

function _ovPivot(dataX, filterPointKey) {
  const filtered = _ovFilteredData(dataX);
  if (!filtered) return { bySku: {}, order: [], units: [] };
  const pts = allPointUnits(filtered);
  let unitList;
  if (filterPointKey) {
    unitList = pts.filter((p) => p.key === filterPointKey);
  } else if (state.overseasWh) {
    unitList = pts;
  } else {
    unitList = [];
    for (const g of state.groups) {
      const list = pts.filter((p) => p.group === g.id);
      if (!list.length) continue;
      const agg = {};
      for (const p of list) {
        for (const r of p.rows) {
          if (!r.sku) continue;
          const e = agg[r.sku] || (agg[r.sku] = { sku: r.sku, name: r.name || "", qty: 0, tag: r.tag });
          e.qty += Number(r.qty || 0);
          if (r.name) e.name = r.name;
          if (r.tag) e.tag = e.tag || r.tag;
        }
      }
      unitList.push({ key: "group::" + g.id, name: g.name, group: g.id, rows: Object.values(agg) });
    }
  }
  const bySku = {};
  const order = [];
  for (const u of unitList) {
    for (const r of u.rows) {
      if (!r.sku) continue;
      if (!bySku[r.sku]) { bySku[r.sku] = { sku: r.sku, name: r.name || "", qty: {}, total: 0, cat: _ovCatLabel(r), _cs: _ovCatSort(r), tag: r.tag }; order.push(r.sku); }
      const e = bySku[r.sku];
      e.qty[u.key] = (e.qty[u.key] || 0) + Number(r.qty || 0);
      e.total += Number(r.qty || 0);
      if (r.name) e.name = r.name;
      if (r.tag && !e.tag) { e.tag = r.tag; e.cat = _ovCatLabel(r); e._cs = _ovCatSort(r); }
      else if (r.tag && e.tag !== r.tag && _ovCatSort(r) < e._cs) { e.tag = r.tag; e.cat = _ovCatLabel(r); e._cs = _ovCatSort(r); }
    }
  }
  return { bySku, order, units: unitList };
}

function _ovRenderTable(tableId, theadId, dataX, sortKey, filterKey, pageKey, sizeKey, colConfigKey, filterPointKey, pageBase) {
  const dataXX = dataX;
  if (!dataXX) return;
  const { bySku, units } = _ovPivot(dataXX, filterPointKey);
  const sort = _ovState[sortKey];
  const filter = (_ovState[filterKey] || "").trim().toLowerCase();

  const allCols = [["sku", "SKU"], ["name", "产品名称"], ["cat", "类别"]];
  for (const u of units) allCols.push([u.key, unitLabel(u)]);
  allCols.push(["total", "合计"]);

  let visCols = allCols;
  if (colConfigKey) {
    const cfg = loadColConfig(colConfigKey);
    if (cfg && Array.isArray(cfg.hidden) && cfg.hidden.length) {
      const hiddenSet = new Set(cfg.hidden);
      visCols = allCols.filter(([k]) => !hiddenSet.has(k));
    }
    if (cfg && Array.isArray(cfg.order)) {
      const order = cfg.order;
      visCols.sort((a, b) => (order.indexOf(a[0]) === -1 ? 999 : order.indexOf(a[0])) - (order.indexOf(b[0]) === -1 ? 999 : order.indexOf(b[0])));
    }
  }

  const visKeys = new Set(visCols.map(([k]) => k));
  let rows = Object.values(bySku);
  if (filter) rows = rows.filter((r) => r.sku.toLowerCase().includes(filter) || r.name.toLowerCase().includes(filter));

  const dir = sort.dir;
  const col = sort.col;
  rows.sort((a, b) => {
    const byTotal = col === "total";
    const ca = a._cs, cb = b._cs;
    if (byTotal) {
      if (ca !== cb) return ca - cb;
      return b.total - a.total;
    }
    const va = col === "sku" ? a.sku : col === "name" ? a.name : col === "cat" ? a.cat : (a.qty[col] || 0);
    const vb = col === "sku" ? b.sku : col === "name" ? b.name : col === "cat" ? b.cat : (b.qty[col] || 0);
    if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
    return String(va).localeCompare(String(vb), "zh-CN") * dir;
  });

  const size = _ovState[sizeKey];
  const pages = Math.max(1, Math.ceil(rows.length / size));
  if (_ovState[pageKey] > pages) _ovState[pageKey] = pages;
  if (_ovState[pageKey] < 1) _ovState[pageKey] = 1;
  const page = _ovState[pageKey];
  const view = rows.slice((page - 1) * size, page * size);
  const base = pageBase || pageKey.replace("Page", "");

  const thead = document.getElementById(theadId);
  thead.innerHTML = "";
  const tr = document.createElement("tr");
  for (const [key, label] of visCols) {
    const th = document.createElement("th");
    th.textContent = label;
    th.dataset.col = key;
    th.title = label;
    if (units.some((u) => u.key === key)) th.className = "wh";
    else if (key === "cat") th.className = "cat-th";
    tr.appendChild(th);
  }
  thead.appendChild(tr);

  const tbody = document.querySelector(`#${tableId} tbody`);
  tbody.innerHTML = "";
  if (!view.length) {
    tbody.innerHTML = '<tr><td colspan="99" class="state-cell">暂无数据</td></tr>';
    _ovRenderPagination(base, pageKey, sizeKey, 0);
    return;
  }
  for (const row of view) {
    const tr2 = document.createElement("tr");
    if (row._cs === 0) tr2.className = "ov-kit-row";
    else if (row._cs === 2) tr2.className = "ov-std-row";
    else tr2.className = "ov-part-row";
    for (const [key] of visCols) {
      const td = document.createElement("td");
      if (key === "sku") { td.className = "sku-cell"; td.textContent = row.sku; }
      else if (key === "name") { td.textContent = row.name; td.title = row.name; }
      else if (key === "cat") { td.className = "cat-cell"; td.textContent = row.cat; }
      else if (key === "total") { td.className = "total"; td.textContent = row.total.toLocaleString(); }
      else { const v = row.qty[key] || 0; td.textContent = v === 0 ? "—" : v.toLocaleString(); if (v === 0) td.className = "qty-zero"; }
      tr2.appendChild(td);
    }
    tbody.appendChild(tr2);
  }

  const colTotals = {};
  let grandTotal = 0;
  for (const r of rows) {
    for (const u of units) colTotals[u.key] = (colTotals[u.key] || 0) + (r.qty[u.key] || 0);
    grandTotal += r.total;
  }
  const foot = document.createElement("tr");
  foot.className = "tot-row";
  for (const [key] of visCols) {
    const td = document.createElement("td");
    if (key === "sku") { td.className = "tot-label"; td.textContent = "合计"; }
    else if (key === "name" || key === "cat") { /* empty */ }
    else if (key === "total") { td.className = "total"; td.textContent = grandTotal.toLocaleString(); }
    else { td.className = "total"; td.textContent = (colTotals[key] || 0).toLocaleString(); }
    foot.appendChild(td);
  }
  tbody.appendChild(foot);
  _ovRenderPagination(base, pageKey, sizeKey, rows.length);
}

function _ovRenderPagination(base, pageKey, sizeKey, total) {
  const page = _ovState[pageKey];
  const size = _ovState[sizeKey];
  const pages = Math.max(1, Math.ceil(total / size));
  const start = total ? (page - 1) * size + 1 : 0;
  const end = Math.min(total, page * size);
  $(base + "Range").textContent = "共 " + total + " 条" + (total ? "（" + start + "-" + end + "）" : "");
  $(base + "Info").textContent = page + " / " + pages + " 页";
  $(base + "Prev").disabled = page <= 1;
  $(base + "Next").disabled = page >= pages;
}

function _ovSortRows(rows, sortKey) {
  const sort = _ovState[sortKey];
  const dir = sort.dir, col = sort.col;
  rows.sort((a, b) => {
    const va = col === "sku" ? a.sku : col === "name" ? a.name : col === "total" ? a.total : (a.qty[col] || 0);
    const vb = col === "sku" ? b.sku : col === "name" ? b.name : col === "total" ? b.total : (b.qty[col] || 0);
    if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
    return String(va).localeCompare(String(vb), "zh-CN") * dir;
  });
}

/* ---- 出库卡片渲染 ---- */

function renderOvOutCards(data) {
  const wrap = $("ovOutCards");
  if (!wrap) return;
  wrap.innerHTML = "";
  if (!data) return;
  const pts = allPointUnits(_ovFilteredData(data))
    .filter((p) => !_ovState.outPoint || p.key === _ovState.outPoint);
  if (!state.overseasWh) {
    wrap.appendChild(cardDom("全部出库合计", "所选区间所有海外仓出库汇总", sumStats(pts),
      () => openStats("out", "all")));
    for (const g of state.groups) {
      const gPts = pts.filter((p) => p.group === g.id);
      if (!gPts.length) continue;
      wrap.appendChild(cardDom(g.name, `${gPts.length} 个仓点`, sumStats(gPts),
        () => switchOverseasWh(g.id)));
    }
  } else {
    for (const u of pts) {
      wrap.appendChild(cardDom(unitLabel(u), "更新于 " + formatTime(u.fetchedAt), sumStats([u]),
        () => openStats("out", "point:" + u.key)));
    }
  }
}

function _ovSyncOutPointOptions(data) {
  const sel = $("ovOutPoint");
  if (!sel) return;
  sel.innerHTML = "";
  if (!data) { sel.style.display = "none"; return; }
  const pts = allPointUnits(_ovFilteredData(data));
  if (!state.overseasWh || !pts.length) {
    sel.style.display = "none";
    _ovState.outPoint = "";
    return;
  }
  sel.style.display = "";
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "全部仓点";
  sel.appendChild(all);
  for (const p of pts) {
    const o = document.createElement("option");
    o.value = p.key;
    o.textContent = unitLabel(p);
    sel.appendChild(o);
  }
  if (!pts.some((p) => p.key === _ovState.outPoint)) _ovState.outPoint = "";
  sel.value = _ovState.outPoint;
}

const OV_OUT_RENDER = () => {
  if (state.out) {
    renderOvOutCards(state.out);
    _ovSyncOutPointOptions(state.out);
    _ovRenderTable("ovOutTable", "ovOutHead", state.out, "outSort", "outFilter", "outPage", "outPageSize", "ov_out_table", _ovState.outPoint, "ovOut");
  } else {
    const tbody = document.querySelector("#ovOutTable tbody");
    if (tbody) tbody.innerHTML = '<tr><td colspan="99" class="state-cell">暂无数据</td></tr>';
  }
};

const OV_INV_RENDER = () => {
  if (state.inv) {
    _ovRenderTable("ovInvTable", "ovInvHead", state.inv, "invSort", "invFilter", "invPage", "invPageSize", "ov_inv_table", "", "ovInv");
  } else {
    const tbody = document.querySelector("#ovInvTable tbody");
    if (tbody) tbody.innerHTML = '<tr><td colspan="99" class="state-cell">暂无数据</td></tr>';
  }
};

/* ---- 导出 ---- */

function _ovExportCsv(dataKey, filterKey, prefix) {
  const dataX = state[dataKey];
  if (!dataX) return;

  const esc = (v) => { v = String(v ?? ""); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
  const filter = (_ovState[filterKey] || "").trim().toLowerCase();

  if (dataKey === "inv") {
    _ovExportInventory(dataX, filter, prefix, esc);
  } else {
    _ovExportOutbound(dataX, filter, prefix, esc);
  }
}

function _ovExportInventory(dataX, filter, prefix, esc) {
  const filtered = _ovFilteredData(dataX);
  const units = allPointUnits(filtered);

  const byGroup = new Map();
  for (const u of units) {
    const gid = u.group || "other";
    if (!byGroup.has(gid)) byGroup.set(gid, []);
    byGroup.get(gid).push(u);
  }

  const lines = [];
  let grandTotal = 0;
  const grandSkus = new Set();

  for (const [gid, gUnits] of byGroup) {
    const gName = groupName(gid);
    lines.push([]);
    lines.push([`=== ${gName} ===`].map(esc).join(","));

    const bySku = {};
    for (const u of gUnits) {
      for (const r of u.rows) {
        if (!r.sku) continue;
        if (!bySku[r.sku]) bySku[r.sku] = { sku: r.sku, name: r.name || "", qty: {}, total: 0 };
        const e = bySku[r.sku];
        e.qty[u.key] = (e.qty[u.key] || 0) + Number(r.qty || 0);
        e.total += Number(r.qty || 0);
        if (r.name) e.name = r.name;
      }
    }

    let rows = Object.values(bySku);
    if (filter) rows = rows.filter((r) => r.sku.toLowerCase().includes(filter) || r.name.toLowerCase().includes(filter));

    const allCols = [["sku", "SKU"], ["name", "产品名称"]];
    for (const u of gUnits) allCols.push([u.key, unitLabel(u)]);
    allCols.push(["total", "合计"]);

    lines.push(allCols.map(([, l]) => l).map(esc).join(","));
    let gTotal = 0;
    for (const r of rows) {
      lines.push([r.sku, r.name, ...gUnits.map((u) => r.qty[u.key] || 0), r.total].map(esc).join(","));
      gTotal += r.total;
      grandSkus.add(r.sku);
    }
    const colTotals = {};
    for (const r of rows) {
      for (const u of gUnits) colTotals[u.key] = (colTotals[u.key] || 0) + (r.qty[u.key] || 0);
    }
    lines.push(["小计", "", ...gUnits.map((u) => colTotals[u.key] || 0), gTotal].map(esc).join(","));
    grandTotal += gTotal;
  }

  lines.push([]);
  lines.push(["=== 全部合计 ===", grandSkus.size + " 个SKU", grandTotal.toLocaleString() + " 件"].map(esc).join(","));

  const scopeLabel = state.overseasWh ? groupName(state.overseasWh) : "全部海外仓";
  downloadCsv(`${prefix}_${scopeLabel}_${new Date().toISOString().slice(0, 10)}.csv`,
    lines.join("\r\n"));
}

function _ovExportOutbound(dataX, filter, prefix, esc) {
  const { bySku, units } = _ovPivot(dataX, _ovState.outPoint);
  let rows = Object.values(bySku);
  if (filter) rows = rows.filter((r) => r.sku.toLowerCase().includes(filter) || r.name.toLowerCase().includes(filter));
  _ovSortRows(rows, "outSort");

  const lines = [];
  lines.push(["SKU", "产品名称", ...units.map((u) => unitLabel(u)), "合计"].map(esc).join(","));
  for (const r of rows) {
    lines.push([r.sku, r.name, ...units.map((u) => r.qty[u.key] || 0), r.total].map(esc).join(","));
  }
  const colTotals = {};
  let grandTotal = 0;
  for (const r of rows) {
    for (const u of units) colTotals[u.key] = (colTotals[u.key] || 0) + (r.qty[u.key] || 0);
    grandTotal += r.total;
  }
  lines.push(["合计", "", ...units.map((u) => colTotals[u.key] || 0), grandTotal].map(esc).join(","));

  const scopeLabel = state.overseasWh ? groupName(state.overseasWh) : "全部海外仓";
  downloadCsv(`${prefix}_${scopeLabel}_${new Date().toISOString().slice(0, 10)}.csv`,
    lines.join("\r\n"));
}

function exportOverseasStats() {
  const src = $("ovStatsSource") ? $("ovStatsSource").value : "inv";
  const dataX = src === "inv" ? state.inv : state.out;
  if (!dataX) return;
  const filtered = _ovFilteredData(dataX);
  const units = allPointUnits(filtered);
  const byGroup = {};
  for (const u of units) {
    const gid = u.group || "other";
    if (!byGroup[gid]) byGroup[gid] = { kit: { qty: 0, box: 0 }, part: { qty: 0, box: 0 }, std: { qty: 0, box: 0 }, skus: new Set() };
    for (const r of u.rows) {
      if (!r.sku) continue;
      byGroup[gid].skus.add(r.sku);
      const box = r.box != null ? Number(r.box) : Number(r.qty || 0);
      if (r.tag === "kit") { byGroup[gid].kit.qty += Number(r.qty || 0); byGroup[gid].kit.box += box; }
      else if (r.tag === "part") { byGroup[gid].part.qty += Number(r.qty || 0); byGroup[gid].part.box += box; }
      else { byGroup[gid].std.qty += Number(r.qty || 0); byGroup[gid].std.box += box; }
    }
  }
  const lines = [["仓库", "SKU数", "成套套数", "不成套箱数", "非组合箱数", "总箱数"]];
  let totSkus = 0, totKit = 0, totPart = 0, totStd = 0, totBox = 0;
  for (const gid of Object.keys(byGroup)) {
    const gs = byGroup[gid];
    const tb = gs.kit.box + gs.part.box + gs.std.box;
    lines.push([groupName(gid), gs.skus.size, gs.kit.qty, gs.part.qty, gs.std.qty, tb]);
    totSkus += gs.skus.size; totKit += gs.kit.qty; totPart += gs.part.qty; totStd += gs.std.qty; totBox += tb;
  }
  lines.push(["合计", totSkus, totKit, totPart, totStd, totBox]);
  const scopeLabel = state.overseasWh ? groupName(state.overseasWh) : "全部海外仓";
  const srcLabel = src === "inv" ? "库存" : "出库";
  downloadCsv(`海外仓统计_${scopeLabel}_${srcLabel}_${new Date().toISOString().slice(0, 10)}.csv`,
    lines.map((r) => r.map((v) => csvEsc(v)).join(",")).join("\r\n"));
}

/* ---- 主渲染 ---- */

function renderOverseas() {
  renderOverseasSelector();
  renderOverseasCards();
  renderOverseasDashStats();
  OV_OUT_RENDER();
  OV_INV_RENDER();
  renderTransitAlert();
}

let _transitAlertData = null;
let _transitAlertLoading = false;

async function renderTransitAlert(force) {
  const wrap = $("transitAlertWrap");
  const detail = $("transitAlertDetail");
  if (!wrap || !detail) return;
  if (force) _transitAlertData = null;
  if (_transitAlertData) {
    const d = _transitAlertData;
    const s = d.summary || {};
    const tl = s.timeline || {};
    const soon = ["7天", "14天", "30天"].map((k) => (tl[k] || {}).containers || 0);
    const comboSetsN = Object.keys(s.combosets || {}).length;
    if (s.containers && s.containers > 0) {
      wrap.style.display = "";
      detail.innerHTML =
        `<b>${s.containers}</b> 柜在途 · ${Math.round(s.qty || 0).toLocaleString()} 件 ·
         预计 <b>${soon[0]}</b> 柜 / 7天 · <b>${soon[1]}</b> 柜 / 14天 · <b>${soon[2]}</b> 柜 / 30天内到港` +
        (comboSetsN ? ` · <b style='color:#b45309'>${comboSetsN}</b> 个组合可成套` : "");
    } else {
      wrap.style.display = "none";
    }
    return;
  }
  if (_transitAlertLoading) return;
  _transitAlertLoading = true;
  try {
    const data = await api("/api/transit/summary");
    _transitAlertData = data;
    renderTransitAlert();
  } catch (e) {
    wrap.style.display = "none";
  } finally {
    _transitAlertLoading = false;
  }
}

/* ---- 初始化事件 ---- */

function initOverseas() {
  $("ovStatsSource").addEventListener("change", () => renderOverseasDashStats());
  $("ovStatsExport").addEventListener("click", exportOverseasStats);

  /* 出库事件 */
  $("ovOutFilter").addEventListener("input", (e) => { _ovState.outFilter = e.target.value; _ovState.outPage = 1; OV_OUT_RENDER(); });
  $("ovOutSearchBtn").addEventListener("click", () => { _ovState.outFilter = $("ovOutFilter").value; _ovState.outPage = 1; OV_OUT_RENDER(); });
  $("ovOutFilter").addEventListener("keydown", (e) => { if (e.key === "Enter") $("ovOutSearchBtn").click(); });
  $("ovOutDateBtn").addEventListener("click", () => {
    _ovState.outStart = $("ovOutStart").value;
    _ovState.outEnd = $("ovOutEnd").value;
    if (!_ovState.outStart && !_ovState.outEnd) return;
    state.outStart = _ovState.outStart; state.outEnd = _ovState.outEnd;
    state.out = null; _ovState.outPage = 1; loadOut(true);
  });
  $("ovOutStart").addEventListener("change", () => {
    if ($("ovOutStart").value) {
      _ovState.outStart = $("ovOutStart").value;
      _ovState.outEnd = $("ovOutEnd").value || $("ovOutStart").value;
      state.outStart = _ovState.outStart; state.outEnd = _ovState.outEnd;
      state.out = null; _ovState.outPage = 1; loadOut(true);
    }
  });
  $("ovOutEnd").addEventListener("change", () => {
    if ($("ovOutEnd").value) {
      _ovState.outEnd = $("ovOutEnd").value;
      _ovState.outStart = _ovState.outStart || $("ovOutEnd").value;
      state.outStart = _ovState.outStart; state.outEnd = _ovState.outEnd;
      state.out = null; _ovState.outPage = 1; loadOut(true);
    }
  });
  $("ovOutPoint").addEventListener("change", (e) => { _ovState.outPoint = e.target.value; _ovState.outPage = 1; OV_OUT_RENDER(); });
  $("ovExportOut").addEventListener("click", () => _ovExportCsv("out", "outFilter", "出库汇总"));
  $("ovOutColSettings").addEventListener("click", () => {
    const dataX = state.out;
    if (!dataX) return;
    const { units } = _ovPivot(dataX, _ovState.outPoint);
    const cols = [{ key: "sku", label: "SKU" }, { key: "name", label: "产品名称" }];
    for (const u of units) cols.push({ key: u.key, label: unitLabel(u) });
    cols.push({ key: "total", label: "合计" });
    showColSettings("ov_out_table", cols, OV_OUT_RENDER);
  });
  $("ovOutPrev").addEventListener("click", () => { if (_ovState.outPage > 1) { _ovState.outPage--; OV_OUT_RENDER(); } });
  $("ovOutNext").addEventListener("click", () => { _ovState.outPage++; OV_OUT_RENDER(); });
  $("ovOutPageSize").addEventListener("change", (e) => { _ovState.outPageSize = Number(e.target.value); _ovState.outPage = 1; OV_OUT_RENDER(); });

  /* 库存事件 */
  $("ovInvFilter").addEventListener("input", (e) => { _ovState.invFilter = e.target.value; _ovState.invPage = 1; OV_INV_RENDER(); });
  $("ovInvSearchBtn").addEventListener("click", () => { _ovState.invFilter = $("ovInvFilter").value; _ovState.invPage = 1; OV_INV_RENDER(); });
  $("ovInvFilter").addEventListener("keydown", (e) => { if (e.key === "Enter") $("ovInvSearchBtn").click(); });
  $("ovExportInv").addEventListener("click", () => _ovExportCsv("inv", "invFilter", "实时库存"));
  $("ovInvColSettings").addEventListener("click", () => {
    const dataX = state.inv;
    if (!dataX) return;
    const { units } = _ovPivot(dataX, "");
    const cols = [{ key: "sku", label: "SKU" }, { key: "name", label: "产品名称" }];
    for (const u of units) cols.push({ key: u.key, label: unitLabel(u) });
    cols.push({ key: "total", label: "合计" });
    showColSettings("ov_inv_table", cols, OV_INV_RENDER);
  });
  $("ovInvPrev").addEventListener("click", () => { if (_ovState.invPage > 1) { _ovState.invPage--; OV_INV_RENDER(); } });
  $("ovInvNext").addEventListener("click", () => { _ovState.invPage++; OV_INV_RENDER(); });
  $("ovInvPageSize").addEventListener("change", (e) => { _ovState.invPageSize = Number(e.target.value); _ovState.invPage = 1; OV_INV_RENDER(); });
}

/* ---- 备货预警监控 ---- */

let _restockOverviewData = null;
let _restockRefreshTimer = null;

async function refreshRestockOverview() {
  try {
    const d = await api("/api/restocking_overview");
    _restockOverviewData = d;
    renderRestockOverview(d);
  } catch (e) {
    console.warn("备货数据加载失败:", e.message);
  }
}

function renderRestockOverview(d) {
  const wrap = $("ovRestockAlerts");
  if (!wrap) return;
  wrap.style.display = "block";

  const ts = $("ovRestockTs");
  if (ts && d.timestamp) ts.textContent = "更新: " + d.timestamp.slice(11, 19);

  const s = d.summary || {};
  const cards = $("ovRestockCards");
  if (cards) {
    cards.innerHTML = [
      { l: "紧急补货", v: s.urgent || 0, c: "sc-red" },
      { l: "需补货SKU", v: s.need_restock || 0, c: "sc-amber" },
      { l: "需补货总量", v: (s.total_restock_qty || 0).toLocaleString() + "件", c: "sc-green" },
      { l: "缺货", v: s.out_of_stock || 0, c: "sc-red" },
      { l: "预警", v: s.warning || 0, c: "sc-amber" },
      { l: "物流周期", v: (d.cycle_days || 30) + "天", c: "" },
    ].map(c => `<div class="ov-rc ${c.c}"><div class="ov-rc-v">${c.v}</div><div class="ov-rc-l">${c.l}</div></div>`).join("");
  }

  const urgentEl = $("ovUrgentList");
  const urgentCount = $("ovUrgentCount");
  if (urgentEl) {
    const items = (d.urgent_items || []).slice(0, 8);
    if (urgentCount) urgentCount.textContent = `(${items.length})`;
    urgentEl.innerHTML = items.length ? items.map(r => {
      const alerts = (r.alerts || []).map(a => `<span class="sc-alert-tag">${escapeHtml(a)}</span>`).join(" ");
      return `<div class="ov-ri"><span class="mono">${escapeHtml(r.sku)}</span> <span class="ov-ri-inv">${r.current_qty}件</span> <span class="ov-ri-sell">${r.sellable_days}天</span> ${r.restock_qty > 0 ? `<span class="ov-ri-qty sc-green">+${r.restock_qty}</span>` : ""} ${alerts}</div>`;
    }).join("") : '<div class="state-cell">无紧急项</div>';
  }

  const needEl = $("ovNeedList");
  const needCount = $("ovNeedCount");
  if (needEl) {
    const items = (d.need_restock_items || []).slice(0, 8);
    if (needCount) needCount.textContent = `(${items.length})`;
    needEl.innerHTML = items.length ? items.map(r => {
      const alerts = (r.alerts || []).map(a => `<span class="sc-alert-tag">${escapeHtml(a)}</span>`).join(" ");
      return `<div class="ov-ri"><span class="mono">${escapeHtml(r.sku)}</span> <span class="ov-ri-inv">${r.current_qty}件</span> <span class="ov-ri-sell">${r.sellable_days}天</span> <span class="ov-ri-qty sc-green">+${r.restock_qty}</span> ${alerts}</div>`;
    }).join("") : '<div class="state-cell">无待补货项</div>';
  }
}

function startRestockAutoRefresh() {
  stopRestockAutoRefresh();
  refreshRestockOverview();
  _restockRefreshTimer = setInterval(refreshRestockOverview, 30000);
}

function stopRestockAutoRefresh() {
  if (_restockRefreshTimer) { clearInterval(_restockRefreshTimer); _restockRefreshTimer = null; }
}
