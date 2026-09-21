/* 排行榜模块：出库产品排行 + 增速排行，支持产品标签（清仓）、排除与自定义区间、合计行 */

const _rankVolColDefs = [
  { key: "rank", label: "#" },
  { key: "sku", label: "SKU" },
  { key: "name", label: "产品名称" },
  { key: "type", label: "类型" },
  { key: "qty", label: "出库量" },
  { key: "tag", label: "标签" },
];
const _rankVolColKey = "rank_vol";
const _rankGrowthColDefs = [
  { key: "rank", label: "#" },
  { key: "sku", label: "SKU" },
  { key: "name", label: "产品名称" },
  { key: "type", label: "类型" },
  { key: "cur", label: "本期出库" },
  { key: "prev", label: "上期出库" },
  { key: "growth", label: "增长率" },
  { key: "tag", label: "标签" },
];
const _rankGrowthColKey = "rank_growth";

let _rankData = null;
let _rankSeq = 0;
let _prevRankTotal = null;

function showRank() {
  state.view = "rank";
  renderTabs();
  setPanelVisible("rankPanel");
  _loadRankTags();
  if (_rankData) {
    renderRankTables(_rankData);
  } else {
    renderRank();
  }
}
function rankDateDefaults() {
  if (!$("rankStart").value || !$("rankEnd").value) {
    const today = new Date();
    const fmt = (d) =>
      d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
    $("rankEnd").value = fmt(today);
    const start = new Date(today);
    start.setDate(today.getDate() - 6);
    $("rankStart").value = fmt(start);
  }
}

function rankToggleDates() {
  $("rankDateWrap").style.display = $("rankMode").value === "custom" ? "" : "none";
}

async function _loadRankTags() {
  try {
    const d = await api("/api/tags");
    const tags = d.tags || {};
    const uniqueLabels = [...new Set(Object.values(tags))].sort();
    const wrap = $("rankTagChecks");
    if (!wrap) return;
    wrap.innerHTML = "";
    if (!uniqueLabels.length) {
      wrap.innerHTML = '<span class="hint">暂无标签</span>';
      return;
    }
    for (const label of uniqueLabels) {
      const cnt = Object.values(tags).filter((v) => v === label).length;
      const lbl = document.createElement("label");
      lbl.className = "q-label checkbox";
      lbl.style.whiteSpace = "nowrap";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.className = "check rank-tag-cb";
      cb.value = label;
      lbl.appendChild(cb);
      lbl.appendChild(document.createTextNode(label + " (" + cnt + ")"));
      wrap.appendChild(lbl);
    }
    wrap.querySelectorAll(".rank-tag-cb").forEach((cb) => cb.addEventListener("change", () => renderRank()));
  } catch {}
}

function initRank() {
  $("rankMode").addEventListener("change", () => { rankToggleDates(); renderRank(); });
  for (const id of ["rankStart", "rankEnd"]) {
    const el = $(id);
    el.addEventListener("change", () => renderRank());
    el.addEventListener("input", () => renderRank());
  }
  $("rankRefresh").addEventListener("click", () => renderRank(true));
  $("rankExport").addEventListener("click", exportRank);
  $("rankVolColSettings").addEventListener("click", () => {
    showColSettings(_rankVolColKey, _rankVolColDefs, () => { if (_rankData) renderRankTables(_rankData); });
  });
  $("rankGrowthColSettings").addEventListener("click", () => {
    showColSettings(_rankGrowthColKey, _rankGrowthColDefs, () => { if (_rankData) renderRankTables(_rankData); });
  });
  rankDateDefaults();
  rankToggleDates();
  _loadRankTags();
}

function rankModeLabel(mode) {
  return { "7d": "近7天", "30d": "近一个月", "6m": "近半年", "1y": "近一年", "custom": "自定义" }[mode] || mode;
}

async function renderRank(force) {
  const mode = $("rankMode").value;
  const excludeTags = [...document.querySelectorAll(".rank-tag-cb:checked")].map((cb) => cb.value);
  const msg = $("rankMsg");
  const btn = $("rankRefresh");
  let t0 = Date.now();
  let timer = setInterval(() => {
    msg.textContent = "⏳ 正在拉取" + rankModeLabel(mode) + "原始流水… 已等待 " +
      Math.round((Date.now() - t0) / 1000) + " 秒（首次需 1-5 分钟，请勿重复点击）";
  }, 1000);
  msg.textContent = "⏳ 正在拉取" + rankModeLabel(mode) + "原始流水…";
  btn.disabled = true;
  btn.textContent = "拉取中…";
  let query = "/api/rank?exclude_tags=" + encodeURIComponent(excludeTags.join(","));
  if (force) query += "&force=1";
  if (mode === "custom") {
    const start = $("rankStart").value;
    const end = $("rankEnd").value;
    if (!start || !end) {
      clearInterval(timer);
      btn.disabled = false;
      btn.textContent = "刷新";
      msg.textContent = "⚠ 请先选择开始与结束日期";
      return;
    }
    query += "&start=" + encodeURIComponent(start) + "&end=" + encodeURIComponent(end);
  } else {
    query += "&mode=" + encodeURIComponent(mode);
  }
  try {
    const seq = ++_rankSeq;
    const data = await api(query, { timeout: 600000 });
    clearInterval(timer);
    btn.disabled = false;
    btn.textContent = "刷新";
    if (seq !== _rankSeq) return;
    _rankData = data;
    renderRankTables(data);
    const genNote = force
      ? (data.total_products === (_prevRankTotal ?? -1)
          ? " · 已从源系统强制重拉（数据无变化）"
          : " · 已从源系统强制重拉")
      : "";
    _prevRankTotal = data.total_products;
    msg.textContent = "共 " + data.total_products + " 个产品 · 本期 " +
      data.range.start + " ~ " + data.range.end + "，上期 " +
      data.prev_range.start + " ~ " + data.prev_range.end +
      " · 生成于 " + data.generated_at + genNote;
  } catch (e) {
    clearInterval(timer);
    btn.disabled = false;
    btn.textContent = "刷新";
    msg.textContent = "⚠ " + e.message;
  }
}

function rankUnit(d) {
  return d.type === "combo" ? "套" : "箱";
}

function rankTypeBadge(d) {
  return d.type === "combo"
    ? '<span class="badge badge-combo">组合</span>'
    : '<span class="badge badge-standalone">非组合</span>';
}

function rankTagCell(d) {
  if (d.tag) {
    return '<span class="tag-badge">' + escapeHtml(d.tag) + "</span> " +
      '<button class="btn mini" data-sku="' + escapeHtml(d.sku) + '" data-tag="rm">取消</button>';
  }
  return '<button class="btn mini" data-sku="' + escapeHtml(d.sku) + '" data-tag="add">打标签</button>';
}

function fmtTotals(v) {
  const parts = [];
  if (v.combo) parts.push("组合 " + v.combo.toLocaleString() + " 套");
  if (v.standalone) parts.push("非组合 " + v.standalone.toLocaleString() + " 箱");
  return parts.length ? parts.join(" · ") : "0";
}

function _rankBuildHead(colKey, colDefs) {
  const vis = getColOrder(colKey, colDefs.map((c) => c.key));
  const hidden = new Set(colDefs.map((c) => c.key).filter((k) => !vis.includes(k)));
  return colDefs.filter((c) => !hidden.has(c.key));
}
function _rankRenderRow(d, shown, helpers) {
  const esc = escapeHtml;
  const cells = [];
  for (const c of shown) {
    if (c.key === "rank") cells.push('<td class="rank-num">' + d.rank + "</td>");
    else if (c.key === "sku") cells.push('<td class="sku-cell">' + esc(d.sku) + "</td>");
    else if (c.key === "name") cells.push("<td>" + esc(d.name) + "</td>");
    else if (c.key === "type") cells.push("<td>" + rankTypeBadge(d) + "</td>");
    else if (c.key === "qty") cells.push('<td class="num">' + d.qty.toLocaleString() + " " + rankUnit(d) + "</td>");
    else if (c.key === "cur") cells.push('<td class="num">' + d.cur.toLocaleString() + " " + rankUnit(d) + "</td>");
    else if (c.key === "prev") cells.push('<td class="num">' + d.prev.toLocaleString() + " " + rankUnit(d) + "</td>");
    else if (c.key === "growth") {
      const cls = d.growth > 0 ? " growth-up" : (d.growth < 0 ? " growth-down" : "");
      cells.push('<td class="num' + cls + '">' + (d.growth > 0 ? "+" : "") + d.growth.toFixed(2) + "%</td>");
    }
    else if (c.key === "tag") cells.push("<td>" + rankTagCell(d) + "</td>");
  }
  return cells.join("");
}

function renderRankTables(data) {
  $("rankRange1").textContent = data.range.start + " ~ " + data.range.end;
  $("rankRange2").textContent = "本期 " + data.range.start + " ~ " + data.range.end +
    " · 上期 " + data.prev_range.start + " ~ " + data.prev_range.end;

  const volShown = _rankBuildHead(_rankVolColKey, _rankVolColDefs);
  $("rankVolHead").innerHTML = "<tr>" + volShown.map((c) => "<th>" + escapeHtml(c.label) + "</th>").join("") + "</tr>";
  const vb = $("rankVolBody");
  vb.innerHTML = "";
  const volCols = volShown.length;
  if (!data.volume.length) {
    vb.innerHTML = `<tr><td colspan="${volCols}" class="empty">暂无数据</td></tr>`;
  } else {
    for (const d of data.volume) {
      const tr = document.createElement("tr");
      tr.innerHTML = _rankRenderRow(d, volShown);
      vb.appendChild(tr);
    }
  }
  $("rankVolTotal").textContent = fmtTotals(data.volume_totals);

  const gShown = _rankBuildHead(_rankGrowthColKey, _rankGrowthColDefs);
  $("rankGrowthHead").innerHTML = "<tr>" + gShown.map((c) => "<th>" + escapeHtml(c.label) + "</th>").join("") + "</tr>";
  const gb = $("rankGrowthBody");
  gb.innerHTML = "";
  const growthCols = gShown.length;
  if (!data.growth.length) {
    gb.innerHTML = `<tr><td colspan="${growthCols}" class="empty">暂无数据</td></tr>`;
  } else {
    for (const d of data.growth) {
      const tr = document.createElement("tr");
      tr.innerHTML = _rankRenderRow(d, gShown);
      gb.appendChild(tr);
    }
  }
  const gc = data.growth_totals.cur;
  const gp = data.growth_totals.prev;
  const gct = fmtTotals(gc);
  const gpt = fmtTotals(gp);
  let gpct = "0%";
  const cTot = gc.combo + gc.standalone;
  const pTot = gp.combo + gp.standalone;
  if (pTot > 0 && cTot > 0) {
    const pct = (cTot - pTot) / pTot * 100;
    gpct = (pct > 0 ? "+" : "") + pct.toFixed(2) + "%";
  }
  $("rankGrowthCur").textContent = gct;
  $("rankGrowthPrev").textContent = gpt;
  $("rankGrowthPct").textContent = gpct;
  bindRankTagButtons();
}

function bindRankTagButtons() {
  $("rankPanel").querySelectorAll("button[data-tag]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const sku = btn.getAttribute("data-sku");
      try {
        if (btn.getAttribute("data-tag") === "add") {
          const label = ($("rankTagLabel").value || "清仓").trim();
          await api("/api/tags", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sku, label }),
          });
        } else {
          await api("/api/tags/" + encodeURIComponent(sku), { method: "DELETE" });
        }
        await renderRank();
      } catch (e) {
        $("rankMsg").textContent = "⚠ " + e.message;
      }
    });
  });
}

function csvCell(v) {
  const s = String(v ?? "");
  return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

function exportRank() {
  if (!_rankData) return;
  const d = _rankData;
  const lines = [];
  lines.push("出库产品排行（全部，" + d.range.start + " ~ " + d.range.end + "）");
  lines.push(["排名", "SKU", "产品名称", "类型", "出库量", "标签"].map(csvCell).join(","));
  for (const it of d.volume) {
    lines.push([it.rank, it.sku, it.name, it.type === "combo" ? "组合" : "非组合",
      it.qty + " " + rankUnit(it), it.tag].map(csvCell).join(","));
  }
  lines.push(["", "", "", "合计", fmtTotals(d.volume_totals), ""].map(csvCell).join(","));
  lines.push("");
  lines.push("增速排行（全部，本期 " + d.range.start + " ~ " + d.range.end +
    "，上期 " + d.prev_range.start + " ~ " + d.prev_range.end + "）");
  lines.push(["排名", "SKU", "产品名称", "类型", "本期出库", "上期出库", "增长率", "标签"].map(csvCell).join(","));
  for (const it of d.growth) {
    lines.push([it.rank, it.sku, it.name, it.type === "combo" ? "组合" : "非组合",
      it.cur + " " + rankUnit(it), it.prev + " " + rankUnit(it),
      (it.growth > 0 ? "+" : "") + it.growth.toFixed(2) + "%", it.tag].map(csvCell).join(","));
  }
  const gct = fmtTotals(d.growth_totals.cur);
  const gpt = fmtTotals(d.growth_totals.prev);
  let gpct = "0%";
  const cTot = d.growth_totals.cur.combo + d.growth_totals.cur.standalone;
  const pTot = d.growth_totals.prev.combo + d.growth_totals.prev.standalone;
  if (pTot > 0 && cTot > 0) {
    const pct = (cTot - pTot) / pTot * 100;
    gpct = (pct > 0 ? "+" : "") + pct.toFixed(2) + "%";
  }
  lines.push(["", "", "", "合计", gct, gpt, gpct, ""].map(csvCell).join(","));
  downloadCsv("排行榜.csv", lines.join("\n"));
}
