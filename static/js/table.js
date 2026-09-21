/* 表格模块：库存 / 出库共用表格渲染、排序、分页、导出 */

function colValue(row, col, units) {
  if (col === "sku") return row.sku;
  if (col === "name") return row.name;
  if (col === "total") return row.total;
  if (row.qty[col]) return row.qty[col];
  return 0;
}

function sortRows(rows, sort, units) {
  const dir = sort.dir;
  const col = sort.col;
  rows.sort((a, b) => {
    const va = colValue(a, col, units);
    const vb = colValue(b, col, units);
    if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
    return String(va).localeCompare(String(vb), "zh-CN") * dir;
  });
}

function showTableState(tableId, html) {
  const tbody = document.querySelector(`#${tableId} tbody`);
  if (tbody) tbody.innerHTML = html;
}

function showTableLoading(tableId) {
  showTableState(tableId, '<tr><td colspan="99" class="state-cell">加载中…</td></tr>');
}

function showTableError(tableId, msg) {
  showTableState(tableId, `<tr><td colspan="99" class="state-cell err">${escapeHtml(msg)}</td></tr>`);
}

function renderPagination(base, pageKey, sizeKey, total) {
  const page = state[pageKey];
  const size = state[sizeKey];
  const pages = Math.max(1, Math.ceil(total / size));
  const start = total ? (page - 1) * size + 1 : 0;
  const end = Math.min(total, page * size);
  $(base + "Range").textContent = "共 " + total + " 条" + (total ? "（" + start + "-" + end + "）" : "");
  $(base + "Info").textContent = page + " / " + pages + " 页";
  $(base + "Prev").disabled = page <= 1;
  $(base + "Next").disabled = page >= pages;
}

function renderTable(tableId, theadId, data, sortKey, filterKey, pageKey, sizeKey, colConfigKey) {
  const dataX = state[data];
  if (!dataX) return;
  const { bySku, units } = pivot(dataX, data === "out" ? state.outPoint : "");
  const sort = state[sortKey];
  const filter = state[filterKey].trim().toLowerCase();

  const allCols = [["sku", "SKU"], ["name", "产品名称"]];
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
      visCols.sort((a, b) => {
        const ia = order.indexOf(a[0]);
        const ib = order.indexOf(b[0]);
        return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
      });
    }
  }

  const visKeys = new Set(visCols.map(([k]) => k));

  let rows = Object.values(bySku);
  if (filter) {
    rows = rows.filter((r) =>
      fuzzyMatch(r.sku, filter) || fuzzyMatch(r.name, filter));
  }
  sortRows(rows, sort, units);

  const size = state[sizeKey];
  const pages = Math.max(1, Math.ceil(rows.length / size));
  if (state[pageKey] > pages) state[pageKey] = pages;
  if (state[pageKey] < 1) state[pageKey] = 1;
  const page = state[pageKey];
  const view = rows.slice((page - 1) * size, page * size);
  const base = pageKey.replace("Page", "");

  const thead = document.getElementById(theadId);
  thead.innerHTML = "";
  const tr = document.createElement("tr");
  for (const [key, label] of visCols) {
    const th = document.createElement("th");
    th.textContent = label;
    th.dataset.col = key;
    th.title = label;
    if (units.some((u) => u.key === key)) th.className = "wh";
    tr.appendChild(th);
  }
  thead.appendChild(tr);

  const tbody = document.querySelector(`#${tableId} tbody`);
  tbody.innerHTML = "";
  if (!view.length) {
    tbody.innerHTML = '<tr><td colspan="99" class="state-cell">暂无数据</td></tr>';
    renderPagination(base, pageKey, sizeKey, 0);
    return;
  }
  for (const row of view) {
    const tr2 = document.createElement("tr");
    for (const [key] of visCols) {
      const td = document.createElement("td");
      if (key === "sku") {
        td.className = "sku-cell";
        td.textContent = row.sku;
      } else if (key === "name") {
        td.textContent = row.name;
        td.title = row.name;
      } else if (key === "total") {
        td.className = "total";
        td.textContent = row.total.toLocaleString();
      } else {
        const v = row.qty[key] || 0;
        td.textContent = v === 0 ? "—" : v.toLocaleString();
        if (v === 0) td.className = "qty-zero";
      }
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
    if (key === "sku") {
      td.className = "tot-label";
      td.textContent = "合计";
    } else if (key === "name") {
      // empty
    } else if (key === "total") {
      td.className = "total";
      td.textContent = grandTotal.toLocaleString();
    } else {
      td.className = "total";
      td.textContent = (colTotals[key] || 0).toLocaleString();
    }
    foot.appendChild(td);
  }
  tbody.appendChild(foot);

  renderPagination(base, pageKey, sizeKey, rows.length);
}

function exportCSV() { return; }
