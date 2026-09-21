/* 总览模块：汇总卡片 + 各仓库卡片
   成套套数 / 非组合件数 / 不成套组合件 分开展示 */

function sumStats(units) {
  const skus = new Set();
  let kitQty = 0;
  let kitBox = 0;
  let stdQty = 0;
  let stdBox = 0;
  const partSkus = new Set();
  let partQty = 0;
  let partBox = 0;
  for (const u of units) {
    for (const r of u.rows) {
      if (!r.sku) continue;
      const box = r.box != null ? Number(r.box) : Number(r.qty || 0);
      if (r.tag === "kit") {
        skus.add(r.sku);
        kitQty += Number(r.qty || 0);
        kitBox += box;
        continue;
      }
      if (r.tag === "part") {
        partSkus.add(r.sku);
        partQty += Number(r.qty || 0);
        partBox += box;
        continue;
      }
      skus.add(r.sku);
      stdQty += Number(r.qty || 0);
      stdBox += box;
    }
  }
  return {
    skus: skus.size,
    kitQty, kitBox,
    stdQty, stdBox,
    qty: kitQty + stdQty,
    partSkus: partSkus.size,
    partQty, partBox,
    box: kitBox + partBox + stdBox,
  };
}

function cardDom(name, meta, st, onClick) {
  const card = document.createElement("div");
  card.className = "card" + (onClick ? " clickable" : "");
  card.innerHTML = `
    <div class="c-name">${escapeHtml(name)}</div>
    <div class="c-meta">${escapeHtml(meta)}</div>
    <div class="c-body">
      <div><div class="c-num">${st.skus}</div><div class="c-label">SKU 数</div></div>
      <div><div class="c-num">${st.kitQty.toLocaleString()}</div><div class="c-label">成套套数</div></div>
      <div><div class="c-num part-num">${st.partQty.toLocaleString()}</div><div class="c-label">不成套箱数</div></div>
      <div><div class="c-num">${st.stdQty.toLocaleString()}</div><div class="c-label">非组合箱数</div></div>
      <div><div class="c-num box-total-num">${st.box.toLocaleString()}</div><div class="c-label">总箱数</div></div>
    </div>`;
  if (onClick) {
    card.title = "点击查看详情";
    card.addEventListener("click", onClick);
  }
  return card;
}

function renderCards(data) {
  const wrap = $("warehouseCards");
  wrap.innerHTML = "";
  const pts = allPointUnits(data);
  if (!state.activeGroup) {
    wrap.appendChild(cardDom("全部仓合计", "所有海外仓库存汇总", sumStats(pts),
      () => openStats("inv", "all")));
    for (const g of state.groups) {
      const gUnits = pts.filter((p) => p.group === g.id);
      if (!gUnits.length) continue;
      wrap.appendChild(cardDom(g.name, `${gUnits.length} 个仓点`, sumStats(gUnits),
        () => switchGroup(g.id)));
    }
    return;
  }
  const units = getUnits(data);
  for (const u of units) {
    wrap.appendChild(cardDom(unitLabel(u), "更新于 " + formatTime(u.fetchedAt), sumStats([u]),
      () => openStats("inv", "point:" + u.key)));
  }
}

function overviewCardDom(name, meta, invStats, outStats, isTotal, onClick) {
  const card = document.createElement("div");
  card.className = "card ov-card" + (isTotal ? " card-total" : "") + (onClick ? " clickable" : "");
  const col = (head, st) => `
    <div class="ov-col">
      <div class="ov-col-head">${head}</div>
      <div><div class="c-num">${st.skus.toLocaleString()}</div><div class="c-label">SKU 数</div></div>
      <div><div class="c-num">${st.kitQty.toLocaleString()}</div><div class="c-label">成套套数</div></div>
      <div><div class="c-num part-num">${st.partQty.toLocaleString()}</div><div class="c-label">不成套箱数</div></div>
      <div><div class="c-num">${st.stdQty.toLocaleString()}</div><div class="c-label">非组合箱数</div></div>
      <div><div class="c-num box-total-num">${st.box.toLocaleString()}</div><div class="c-label">总箱数</div></div>
    </div>`;
  card.innerHTML = `
    <div class="c-name">${escapeHtml(name)}</div>
    <div class="c-meta">${escapeHtml(meta)}</div>
    <div class="ov-body">
      ${col("库存", invStats)}
      ${col("出库", outStats)}
    </div>`;
  if (onClick) {
    card.title = "点击查看详情";
    card.addEventListener("click", onClick);
  }
  return card;
}

function renderOverview() {
  const wrap = $("overviewCards");
  if (!wrap) return;
  if (!state.inv || !state.out) return;
  const iUnits = allPointUnits(state.inv);
  const oUnits = allPointUnits(state.out);
  wrap.innerHTML = "";
  if (!state.activeGroup) {
    wrap.appendChild(overviewCardDom("全部仓合计",
      `${iUnits.length} 个仓点 · 库存 + 出库汇总`,
      sumStats(iUnits), sumStats(oUnits), true, () => openStats("inv", "all")));
    for (const g of state.groups) {
      const iu = iUnits.filter((p) => p.group === g.id);
      if (!iu.length) continue;
      const ou = oUnits.filter((p) => p.group === g.id);
      wrap.appendChild(overviewCardDom(g.name, `${iu.length} 个仓点`,
        sumStats(iu), sumStats(ou), false, () => switchGroup(g.id)));
    }
    return;
  }
  const iu = iUnits.filter((p) => p.group === state.activeGroup);
  const ou = oUnits.filter((p) => p.group === state.activeGroup);
  wrap.appendChild(overviewCardDom(groupName(state.activeGroup) + " 合计",
    `${iu.length} 个仓点`, sumStats(iu), sumStats(ou), true,
    () => openStats("inv", "group:" + state.activeGroup)));
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

function csvEsc(v) {
  v = String(v ?? "");
  return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
}

function exportOverview() {
  if (!state.inv || !state.out) return;
  const iUnits = allPointUnits(state.inv);
  const oUnits = allPointUnits(state.out);
  const lines = [["范围/仓库", "仓点数", "库存SKU数", "库存成套套数", "库存不成套箱数", "库存非组合箱数", "库存总箱数", "出库SKU数", "出库成套套数", "出库不成套箱数", "出库非组合箱数", "出库总箱数"]];
  const push = (name, iu, ou) => {
    const i = sumStats(iu), o = sumStats(ou);
    lines.push([name, iu.length, i.skus, i.kitQty, i.partQty, i.stdQty, i.box, o.skus, o.kitQty, o.partQty, o.stdQty, o.box]);
  };
  if (!state.activeGroup) {
    push("全部仓合计", iUnits, oUnits);
    for (const g of state.groups) {
      const iu = iUnits.filter((p) => p.group === g.id);
      if (!iu.length) continue;
      push(g.name, iu, oUnits.filter((p) => p.group === g.id));
    }
  } else {
    const iu = iUnits.filter((p) => p.group === state.activeGroup);
    const ou = oUnits.filter((p) => p.group === state.activeGroup);
    push(groupName(state.activeGroup) + " 合计", iu, ou);
    const byAcct = new Map();
    for (const p of iu) {
      if (!byAcct.has(p.whId)) byAcct.set(p.whId, { name: p.whName, ipts: [], opts: [] });
      byAcct.get(p.whId).ipts.push(p);
    }
    for (const p of ou) {
      if (!byAcct.has(p.whId)) byAcct.set(p.whId, { name: p.whName, ipts: [], opts: [] });
      byAcct.get(p.whId).opts.push(p);
    }
    for (const [, a] of byAcct) push(a.name, a.ipts, a.opts);
  }
  const who = state.activeGroup ? groupName(state.activeGroup) : "全部仓库";
  downloadCsv(`统计总览_${who}_${new Date().toISOString().slice(0, 10)}.csv`,
    lines.map((r) => r.map(csvEsc).join(",")).join("\r\n"));
}

function exportWarehouseCards() {
  const data = state.inv;
  if (!data) return;
  const units = getUnits(data);
  const lines = [["仓点/分组", "仓库", "SKU数", "成套套数", "不成套箱数", "非组合箱数", "总箱数"]];
  for (const u of units) {
    const s = sumStats([u]);
    lines.push([u.name, u.whName || "", s.skus, s.kitQty, s.partQty, s.stdQty, s.box]);
  }
  const who = state.activeGroup ? groupName(state.activeGroup) : "全部仓库";
  downloadCsv(`各仓库库存_${who}_${new Date().toISOString().slice(0, 10)}.csv`,
    lines.map((r) => r.map(csvEsc).join(",")).join("\r\n"));
}
