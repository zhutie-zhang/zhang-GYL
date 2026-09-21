/* 统计模块：调用后端 /api/stats 完成 成套/不成套/无组合 分类统计与明细（含箱数） */

function showStats() {
  state.view = "stats";
  renderTabs();
  setPanelVisible("statsPanel");
  renderStats();
}

function openStats(source, scope, category, filter) {
  const src = $("statsSource");
  if (source && src.value !== source) src.value = source;
  if (scope) {
    if (scope === "all") {
      $("statsScopeType").value = "all";
    } else {
      const idx = scope.indexOf(":");
      const t = idx > 0 ? scope.slice(0, idx) : scope;
      const v = idx > 0 ? scope.slice(idx + 1) : "";
      populateStatsScope(t, v);
    }
  }
  const cat = $("statsCategory");
  cat.value = "";
  if (category && [...cat.options].some((o) => o.value === category)) cat.value = category;
  const f = $("statsFilter");
  state.statsFilter = filter || "";
  if (f) f.value = state.statsFilter;
  state.view = "stats";
  renderTabs();
  setPanelVisible("statsPanel");
  renderStats();
}

function bindStatsCardClicks(scope) {
  const cards = (scope || $("statsCards")).querySelectorAll(".card[data-cat]");
  for (const el of cards) {
    const cat = el.getAttribute("data-cat");
    el.classList.add("clickable");
    el.title = "点击查看该分类明细（再次点击返回全部）";
    el.addEventListener("click", () => {
      const sel = $("statsCategory");
      sel.value = sel.value === cat ? "" : cat;
      renderStatsData();
    });
  }
}

function bindDashStatsCardClicks() {
  const scope = state.activeGroup ? "group:" + state.activeGroup : "all";
  const src = $("dashStatsSource").value;
  const cards = $("dashStatsCards").querySelectorAll(".card[data-cat]");
  for (const el of cards) {
    const cat = el.getAttribute("data-cat");
    el.classList.add("clickable");
    el.title = "点击跳转组合统计查看该分类详情";
    el.addEventListener("click", () => openStats(src, scope, cat));
  }
}

/* ================= 统计范围选择器 ================= */

function populateStatsScope(forceType, forceValue, ids) {
  ids = ids || {};
  const src = $(ids.src || "statsSource").value;
  const data = state[src];
  const typeSel = $(ids.type || "statsScopeType");
  const valSel = $(ids.val || "statsScopeVal");
  const prevType = typeSel.value;
  const prevVal = valSel.value;

  const groups = state.groups || [];
  const whs = (state.warehouses || []).filter((w) => w.enabled !== false);
  const units = data ? allPointUnits(data) : (src === "both" ? (allPointUnits(state.inv).length ? allPointUnits(state.inv) : allPointUnits(state.out)) : []);

  const options = {
    group: groups.map((g) => ({ v: g.id, l: g.name })),
    warehouse: whs.map((w) => ({ v: w.id, l: w.name })),
    point: units.map((u) => ({
      v: u.key,
      l: u.name + (u.whName && u.whName !== u.name ? `（${u.whName}）` : ""),
    })),
  };

  const defs = ["all", "group", "warehouse", "point"];
  const type = defs.includes(forceType) ? forceType : (forceType === "wh" ? "warehouse" : prevType);

  typeSel.innerHTML = "";
  for (const d of defs) {
    const op = document.createElement("option");
    op.value = d;
    op.textContent = { all: "全部仓库", group: "分组", warehouse: "仓库", point: "仓点" }[d];
    typeSel.appendChild(op);
  }
  typeSel.value = type;

  valSel.innerHTML = "";
  for (const o of options[type] || []) {
    const op = document.createElement("option");
    op.value = o.v;
    op.textContent = o.l;
    valSel.appendChild(op);
  }
  if (forceValue !== undefined && [...valSel.options].some((o) => o.value === forceValue)) {
    valSel.value = forceValue;
  } else if ([...valSel.options].some((o) => o.value === prevVal)) {
    valSel.value = prevVal;
  }
  valSel.style.display = type === "all" ? "none" : "";
}

function statsScopeValue(ids) {
  ids = ids || {};
  const type = $(ids.type || "statsScopeType").value;
  if (type === "all") return "all";
  const val = $(ids.val || "statsScopeVal").value;
  if (!val) return "all";
  if (type === "warehouse") return "wh:" + val;
  return type + ":" + val;
}

/* ================= 公共渲染 ================= */

function catInfo(res) {
  const cats = res.categories || {};
  return {
    kit: cats.kit || { sku_count: 0, qty: 0, container_count: 0 },
    part: cats.part || { sku_count: 0, qty: 0, container_count: 0 },
    none: cats.standalone || { sku_count: 0, qty: 0, container_count: 0 },
    zk: cats.zero_kit || { sku_count: 0, container_count: 0 },
    scopeLabel: (res.scope && res.scope.label) || "",
  };
}

function statsCardsHtml(res, catSel) {
  const { kit, part, none, scopeLabel } = catInfo(res);
  const boxes = res.boxes || { kit: 0, part: 0, standalone: 0, total: 0 };
  const esc = escapeHtml;
  const card = (title, extraClass, dataCat, meta, n, q, qLabel, b, bLabel) => `
    <div class="card ${extraClass}"${dataCat !== null ? ` data-cat="${dataCat}"` : ""}>
      <div class="c-name">${esc(title)}</div>
      <div class="c-meta">${esc(meta)}</div>
      <div class="c-body">
        <div><div class="c-num">${n}</div><div class="c-label">${esc("SKU 数")}</div></div>
        <div><div class="c-num">${q.toLocaleString()}</div><div class="c-label">${esc(qLabel)}</div></div>
        ${b !== null ? `<div><div class="c-num box-num">${b.toLocaleString()}</div><div class="c-label">${esc(bLabel)}</div></div>` : ""}
      </div>
    </div>`;
  if (catSel === "kit_std") {
    const comb = {
      sku: kit.sku_count + none.sku_count,
      qty: kit.qty + none.qty,
      ctn: kit.container_count + none.container_count,
    };
    return (
      card("成套+非组合 合计", "card-combined", "kit_std", `${scopeLabel} · 涉及 ${comb.ctn} 个仓点`, comb.sku, comb.qty, "套数+件数", boxes.kit + boxes.standalone, "箱数") +
      card("不成套组合件", "card-part", "part", `${scopeLabel} · 涉及 ${part.container_count} 个仓点`, part.sku_count, part.qty, "件数合计", boxes.part, "箱数") +
      card("总箱数", "card-box-total", "", `${scopeLabel} · 按子SKU拆分`, "-", boxes.total, "总箱数", null, "")
    );
  }
  return (
    card("成套组合", "", "kit", `${scopeLabel} · 涉及 ${kit.container_count} 个仓点`, kit.sku_count, kit.qty, "套数合计", boxes.kit, "箱数") +
    card("不成套组合件", "card-part", "part", `${scopeLabel} · 涉及 ${part.container_count} 个仓点`, part.sku_count, part.qty, "件数合计", boxes.part, "箱数") +
    card("无组合 SKU", "card-none", "standalone", `${scopeLabel} · 涉及 ${none.container_count} 个仓点`, none.sku_count, none.qty, "件数合计", boxes.standalone, "箱数")
  );
}

function statsMatch(it, filter) {
  if (!filter) return true;
  return fuzzyMatch(
    [it.sku, it.name, it.container, it.warehouse, it.kit || ""].join(" "), filter);
}

function statsRowsHtml(items, filter, cat) {
  const esc = escapeHtml;
  return items
    .filter((it) => it.category === cat && statsMatch(it, filter))
    .map((it) =>
      `<td title="${esc(it.warehouse)}">${esc(it.warehouse)}</td><td title="${esc(it.container)}">${esc(it.container)}</td>` +
      `<td class="sku-cell">${esc(it.sku)}</td><td title="${esc(it.name)}">${esc(it.name)}</td>` +
      (cat === "part" ? `<td class="sku-cell">${esc(it.kit || "—")}</td>` : "") +
      `<td class="num">${Number(it.qty || 0).toLocaleString()}</td>` +
      `<td class="num box-num">${Number(it.box || 0).toLocaleString()}</td>`);
}

function statsBlockTable(title, subtitle, heads, rows, emptyText, footRow) {
  const esc = escapeHtml;
  const body = rows.length
    ? rows.map((r) => `<tr>${r}</tr>`).join("") + (footRow || "")
    : `<tr><td colspan="${heads.length}" class="state-cell">${esc(emptyText)}</td></tr>`;
  return `
    <div class="stats-block">
      <div class="stats-block-head">
        <h3>${esc(title)}</h3>
        <span class="hint">${esc(subtitle)}</span>
      </div>
      <div class="table-wrap">
        <table class="prod-table">
          <thead><tr>${heads.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    </div>`;
}

function statsTablesHtml(res, filter, catSel) {
  const { zk } = catInfo(res);
  const items = res.items || [];
  const match = (it) => statsMatch(it, filter);
  const esc = escapeHtml;
  const sums = (cat) => {
    const list = items.filter((it) => it.category === cat && match(it));
    return {
      qty: list.reduce((s, it) => s + Number(it.qty || 0), 0),
      box: list.reduce((s, it) => s + Number(it.box || 0), 0),
    };
  };
  if (catSel === "kit_std") {
    const list = items.filter((it) => (it.category === "kit" || it.category === "standalone") && match(it));
    const rows = list.map((it) =>
      `<td title="${esc(it.warehouse)}">${esc(it.warehouse)}</td><td title="${esc(it.container)}">${esc(it.container)}</td>` +
      `<td class="sku-cell">${esc(it.sku)}</td><td title="${esc(it.name)}">${esc(it.name)}</td>` +
      `<td><span class="badge ${it.category === "kit" ? "badge-combo" : "badge-standalone"}">${esc(it.category === "kit" ? "成套组合" : "非组合产品")}</span></td>` +
      `<td class="num">${Number(it.qty || 0).toLocaleString()}</td>` +
      `<td class="num box-num">${Number(it.box || 0).toLocaleString()}</td>`);
    const totalQty = list.reduce((s, it) => s + Number(it.qty || 0), 0);
    const totalBox = list.reduce((s, it) => s + Number(it.box || 0), 0);
    return statsBlockTable(
      "成套+非组合 合并明细", "组合成套与非组合产品一起统计，按行分别标注类型",
      ["仓库", "仓点", "SKU", "产品名称", "分类", "数量", "箱数"], rows, "暂无数据",
      `<tr class="tot-row"><td colspan="5" class="tot-label">合计</td><td class="num">${totalQty.toLocaleString()}</td><td class="num box-num">${totalBox.toLocaleString()}</td></tr>`
    );
  }
  const foot = (sp, s) =>
    `<tr class="tot-row"><td colspan="${sp}" class="tot-label">合计</td>` +
    `<td class="num">${s.qty.toLocaleString()}</td><td class="num box-num">${s.box.toLocaleString()}</td></tr>`;
  const headsKit = ["仓库", "仓点", "SKU", "产品名称", "套数", "箱数"];
  const headsPart = ["仓库", "仓点", "SKU", "产品名称", "所属组合", "件数", "箱数"];
  const headsNone = ["仓库", "仓点", "SKU", "产品名称", "件数", "箱数"];
  const blocks = {
    kit: statsBlockTable("成套组合明细", "箱数 = 套数 × 子SKU数", headsKit, statsRowsHtml(items, filter, "kit"), "暂无成套组合", foot(4, sums("kit"))),
    part: statsBlockTable("不成套组合件明细", "不成套子件按SKU件数计箱", headsPart, statsRowsHtml(items, filter, "part"), "暂无不成套组合件", foot(5, sums("part"))),
    standalone: statsBlockTable("无组合 SKU 明细", "非组合产品一件一箱", headsNone, statsRowsHtml(items, filter, "standalone"), "暂无无组合 SKU", foot(4, sums("standalone"))),
  };
  const zeroNote = zk.sku_count
    ? `<div class="hint" style="margin-top:8px">另有 ${zk.sku_count} 个组合缺件、0 套可发：${(res.zero_kits || []).map((z) => esc(z.name ? `${z.sku}(${z.name})` : z.sku)).join("、")}</div>`
    : "";
  if (catSel && blocks[catSel]) return blocks[catSel] + zeroNote;
  return blocks.kit + blocks.part + zeroNote + blocks.standalone;
}

const CAT_NAMES = { kit: "成套组合", part: "不成套组合件", standalone: "无组合 SKU" };

function statsCsv(res, filter, catSel) {
  const esc = (v) => {
    v = String(v ?? "");
    return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
  };
  let items = res.items || [];
  if (filter) items = items.filter((it) => statsMatch(it, filter.trim().toLowerCase()));
  if (catSel) {
    if (catSel === "kit_std") items = items.filter((it) => it.category === "kit" || it.category === "standalone");
    else items = items.filter((it) => it.category === catSel);
  }
  const lines = [["仓点", "仓库", "SKU", "产品名称", "分类", "数量", "箱数"]];
  for (const it of items) {
    lines.push([it.container, it.warehouse, it.sku, it.name, CAT_NAMES[it.category] || it.category, it.qty, it.box]);
  }
  const total = items.reduce((s, it) => s + Number(it.qty || 0), 0);
  const totalBox = items.reduce((s, it) => s + Number(it.box || 0), 0);
  lines.push(["合计", "", "", "", "", total, totalBox]);
  return lines.map((r) => r.map(esc).join(",")).join("\r\n");
}

function statsFilename(prefix, res, src) {
  const who = (res.scope && res.scope.label) || "全部仓库";
  return `${prefix}_${src}_${who}_${new Date().toISOString().slice(0, 10)}.csv`;
}

/* ================= 统计页 ================= */

async function renderStats() {
  const msg = $("statsMsg");
  populateStatsScope();
  const reqId = (state.statsReq = (state.statsReq || 0) + 1);
  const scope = statsScopeValue();
  const src = $("statsSource").value;
  const sources = src === "both" ? ["inv", "out"] : [src];
  msg.textContent = "统计计算中…";
  $("statsCards").innerHTML = "";
  $("statsTables").innerHTML = "";
  try {
    if (sources.length === 1) {
      const params = new URLSearchParams({ source: sources[0], scope });
      const res = await api("/api/stats?" + params.toString());
      if (state.statsReq !== reqId) return;
      state.statsData = res;
      msg.textContent = "";
      renderStatsData();
    } else {
      const [invRes, outRes] = await Promise.all([
        api("/api/stats?" + new URLSearchParams({ source: "inv", scope }).toString()),
        api("/api/stats?" + new URLSearchParams({ source: "out", scope }).toString()),
      ]);
      if (state.statsReq !== reqId) return;
      state.statsData = { inv: invRes, out: outRes };
      msg.textContent = "";
      renderStatsData();
    }
  } catch (e) {
    if (state.statsReq !== reqId) return;
    msg.textContent = "统计接口请求失败：" + e.message;
  }
}

function renderStatsGroup(res, groupLabel, wrapCard, wrapTable) {
  const catSel = $("statsCategory").value;
  const filter = (state.statsFilter || "").trim().toLowerCase();
  wrapCard.innerHTML =
    groupLabel +
    statsCardsHtml(res, catSel);
  wrapTable.innerHTML = statsTablesHtml(res, filter, catSel);
  bindStatsCardClicks(wrapCard);
}

function renderStatsData() {
  const src = $("statsSource").value;
  $("statsCards").innerHTML = "";
  $("statsTables").innerHTML = "";
  const scopeLabel = state.statsData && state.statsData.scope && state.statsData.scope.label;
  if (src === "both" && state.statsData.inv && state.statsData.out) {
    const groupHtml = (label, sub) =>
      `<div class="stats-block-head" style="margin:10px 0 4px"><h3>${label}</h3><span class="hint">${sub} · 共用上方筛选条件</span></div>`;
    const invWrap = $("statsCards");
    const invTab = document.createElement("div");
    $("statsTables").appendChild(invTab);
    renderStatsGroup(state.statsData.inv, groupHtml("库存", "当前在库"), invWrap, invTab);
    const outWrap = document.createElement("section");
    outWrap.className = "cards stats-cards";
    outWrap.id = "statsCardsOut";
    outWrap.style.marginTop = "14px";
    $("statsCards").appendChild(outWrap);
    const outTab = document.createElement("div");
    outTab.id = "statsTablesOut";
    $("statsTables").appendChild(outTab);
    renderStatsGroup(state.statsData.out, groupHtml("出库", "统计区间出库"), outWrap, outTab);
    return;
  }
  const res = state.statsData;
  if (!res) return;
  const catSel = $("statsCategory").value;
  const filter = (state.statsFilter || "").trim().toLowerCase();
  $("statsCards").innerHTML = statsCardsHtml(res, catSel);
  $("statsTables").innerHTML = statsTablesHtml(res, filter, catSel);
  bindStatsCardClicks($("statsCards"));
}

function exportStats() {
  const src = $("statsSource").value;
  if (src === "both") {
    const inv = state.statsData && state.statsData.inv;
    const out = state.statsData && state.statsData.out;
    if (!inv || !out || !(inv.items || []).length && !(out.items || []).length) {
      $("statsMsg").textContent = "暂无统计数据可导出";
      return;
    }
    const who = ((inv.scope && inv.scope.label) || (out.scope && out.scope.label) || "全部仓库");
    const day = new Date().toISOString().slice(0, 10);
    const esc = (v) => {
      v = String(v ?? "");
      return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
    };
    const lines = [["数据源", "仓点", "仓库", "SKU", "产品名称", "分类", "数量", "箱数"]];
    const push = (res, label) => {
      for (const it of res.items || []) {
        lines.push([label, it.container, it.warehouse, it.sku, it.name, CAT_NAMES[it.category] || it.category, it.qty, it.box]);
      }
    };
    push(inv, "库存");
    push(out, "出库");
    downloadCsv(`组合统计_库存出库_${who}_${day}.csv`, lines.map((r) => r.map(esc).join(",")).join("\r\n"));
    return;
  }
  const res = state.statsData;
  if (!res || !(res.items || []).length) {
    $("statsMsg").textContent = "暂无统计数据可导出";
    return;
  }
  const label = src === "out" ? "出库" : "库存";
  downloadCsv(statsFilename("组合统计", res, label), statsCsv(res, state.statsFilter, $("statsCategory").value));
}

function initStats() {
  $("statsSource").addEventListener("change", () => {
    state.statsSource = $("statsSource").value;
    renderStats();
  });
  $("statsScopeType").addEventListener("change", () => {
    populateStatsScope();
    renderStats();
  });
  $("statsScopeVal").addEventListener("change", () => renderStats());
  $("statsCategory").addEventListener("change", () => renderStatsData());
  $("statsFilter").addEventListener("input", (e) => {
    state.statsFilter = e.target.value;
    if (state.statsData) renderStatsData();
  });
  $("statsExport").addEventListener("click", exportStats);
}
