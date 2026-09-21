/* 供应链分析看板：KPI卡片 + 库存趋势图 + 供应商评分 + 物流时效 */

const _sc = { data: null };

function loadSupplyChain() {
  return fetch("/api/supply_chain").then((r) => r.json()).then((d) => { _sc.data = d; return d; });
}

/* ---- KPI 卡片 ---- */

function _renderKPIs(kpis, risk) {
  const items = [
    { label: "库存周转天数", value: kpis.turnover_days, unit: "天", color: kpis.turnover_days <= 30 ? "green" : (kpis.turnover_days <= 60 ? "amber" : "red") },
    { label: "安全库存覆盖率", value: kpis.safety_coverage + "%", unit: "", color: kpis.safety_coverage >= 80 ? "green" : (kpis.safety_coverage >= 50 ? "amber" : "red") },
    { label: "准时交付率", value: kpis.on_time_delivery + "%", unit: "", color: kpis.on_time_delivery >= 90 ? "green" : (kpis.on_time_delivery >= 80 ? "amber" : "red") },
    { label: "短缺风险SKU", value: risk.high, unit: "个", color: risk.high <= 3 ? "green" : (risk.high <= 10 ? "amber" : "red") },
    { label: "单位物流成本", value: "$" + kpis.unit_logistics_cost, unit: "/kg", color: kpis.unit_logistics_cost <= 15 ? "green" : (kpis.unit_logistics_cost <= 25 ? "amber" : "red") },
    { label: "履约完成率", value: kpis.fulfillment_rate + "%", unit: "", color: kpis.fulfillment_rate >= 95 ? "green" : (kpis.fulfillment_rate >= 85 ? "amber" : "red") },
  ];
  let html = "";
  for (const it of items) {
    html += `<div class="sc-kpi sc-kpi-${it.color}">
      <div class="sc-kpi-dot"></div>
      <div class="sc-kpi-val">${it.value}<span class="sc-kpi-unit">${it.unit}</span></div>
      <div class="sc-kpi-label">${it.label}</div>
    </div>`;
  }
  return html;
}

/* ---- 库存趋势图 (Canvas) ---- */

function _drawInvTrend(canvas, trend, threshold) {
  if (!canvas || !trend || !trend.length) return;
  const ctx = canvas.getContext("2d");
  const W = canvas.width = canvas.parentElement.clientWidth;
  const H = canvas.height = 240;
  const pad = { t: 20, r: 20, b: 36, l: 56 };
  const cw = W - pad.l - pad.r;
  const ch = H - pad.t - pad.b;
  ctx.clearRect(0, 0, W, H);

  const vals = trend.map((t) => t.cum_inv);
  const maxV = Math.max(...vals, threshold, 1) * 1.1;
  const n = trend.length;
  const step = n > 1 ? cw / (n - 1) : cw;
  const xOf = (i) => pad.l + i * step;
  const yOf = (v) => pad.t + ch - (v / maxV) * ch;

  // 网格
  ctx.strokeStyle = "#e8ecf0";
  ctx.lineWidth = 0.5;
  for (let g = 0; g <= 4; g++) {
    const y = pad.t + (ch / 4) * g;
    ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke();
    ctx.fillStyle = "#8a94a6"; ctx.font = "10px sans-serif"; ctx.textAlign = "right";
    ctx.fillText(Math.round(maxV * (1 - g / 4)).toLocaleString(), pad.l - 6, y + 3);
  }

  // 日期标签
  ctx.fillStyle = "#8a94a6"; ctx.font = "10px sans-serif"; ctx.textAlign = "center";
  const ls = Math.max(1, Math.floor(n / 6));
  for (let i = 0; i < n; i += ls) ctx.fillText(trend[i].date.slice(5), xOf(i), H - pad.b + 14);

  // 面积填充
  ctx.beginPath();
  ctx.moveTo(xOf(0), yOf(vals[0]));
  for (let i = 1; i < n; i++) ctx.lineTo(xOf(i), yOf(vals[i]));
  ctx.lineTo(xOf(n - 1), pad.t + ch);
  ctx.lineTo(xOf(0), pad.t + ch);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, pad.t, 0, pad.t + ch);
  grad.addColorStop(0, "rgba(59,130,246,0.15)");
  grad.addColorStop(1, "rgba(59,130,246,0.01)");
  ctx.fillStyle = grad;
  ctx.fill();

  // 折线
  ctx.strokeStyle = "#3b82f6";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(xOf(0), yOf(vals[0]));
  for (let i = 1; i < n; i++) ctx.lineTo(xOf(i), yOf(vals[i]));
  ctx.stroke();

  // 安全库存虚线
  if (threshold > 0) {
    const ty = yOf(threshold);
    ctx.strokeStyle = "#ef4444";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([6, 4]);
    ctx.beginPath();
    ctx.moveTo(pad.l, ty);
    ctx.lineTo(W - pad.r, ty);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "#ef4444";
    ctx.font = "10px sans-serif";
    ctx.textAlign = "left";
    ctx.fillText("安全库存 " + threshold.toLocaleString(), W - pad.r - 100, ty - 6);
  }
}

/* ---- 供应商质量饼图 (Canvas) ---- */

function _drawPie(canvas, dist) {
  if (!canvas || !dist) return;
  const ctx = canvas.getContext("2d");
  const W = canvas.width = canvas.parentElement.clientWidth;
  const H = canvas.height = 200;
  ctx.clearRect(0, 0, W, H);

  const data = [
    { label: "优秀", value: dist.excellent || 0, color: "#16a34a" },
    { label: "合格", value: dist.qualified || 0, color: "#f59e0b" },
    { label: "待整改", value: dist.poor || 0, color: "#dc2626" },
  ];
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  const cx = 90;
  const cy = H / 2;
  const r = 70;
  let start = -Math.PI / 2;

  for (const d of data) {
    const angle = (d.value / total) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, r, start, start + angle);
    ctx.closePath();
    ctx.fillStyle = d.color;
    ctx.fill();
    start += angle;
  }
  // 内圆（甜甜圈）
  ctx.beginPath();
  ctx.arc(cx, cy, 40, 0, Math.PI * 2);
  ctx.fillStyle = "#fff";
  ctx.fill();
  ctx.fillStyle = "#1e2a47";
  ctx.font = "bold 16px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(total, cx, cy - 6);
  ctx.font = "10px sans-serif";
  ctx.fillStyle = "#8a94a6";
  ctx.fillText("供应商总数", cx, cy + 10);

  // 图例
  let lx = 200;
  let ly = H / 2 - 8;
  for (const d of data) {
    ctx.fillStyle = d.color;
    ctx.fillRect(lx, ly - 6, 12, 12);
    ctx.fillStyle = "#333";
    ctx.font = "12px sans-serif";
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText(`${d.label} ${d.value}家 (${Math.round(d.value / total * 100)}%)`, lx + 18, ly);
    ly += 22;
  }
}

/* ---- 高风险 SKU 表 ---- */

function _renderRiskTable(skuRisks) {
  if (!skuRisks || !skuRisks.length) return '<div class="state-cell">暂无风险数据</div>';
  let html = '<table class="sc-table"><thead><tr><th>SKU</th><th>库存</th><th>日均出库</th><th>可售天数</th><th>安全库存</th><th>覆盖率</th><th>仓点数</th><th>风险</th></tr></thead><tbody>';
  for (const s of skuRisks) {
    const riskCls = s.risk === "high" ? "sc-red" : (s.risk === "warning" ? "sc-amber" : "sc-green");
    const riskLabel = s.risk === "high" ? "高危" : (s.risk === "warning" ? "警告" : "正常");
    html += `<tr class="${riskCls}">
      <td class="sku-cell">${escapeHtml(s.sku)}</td>
      <td>${s.qty.toLocaleString()}</td>
      <td>${s.avg_daily_out}</td>
      <td class="${riskCls}">${s.sellable_days}</td>
      <td>${s.safety_stock.toLocaleString()}</td>
      <td>${s.coverage_rate}%</td>
      <td>${s.warehouses}</td>
      <td><span class="sc-badge ${riskCls}">${riskLabel}</span></td>
    </tr>`;
  }
  html += "</tbody></table>";
  return html;
}

/* ---- 供应商评分表 ---- */

function _renderSupplierTable(suppliers) {
  if (!suppliers || !suppliers.length) return '<div class="state-cell">暂无供应商数据</div>';
  let html = '<table class="sc-table"><thead><tr><th>供应商</th><th>交付分</th><th>质量分</th><th>响应分</th><th>价格分</th><th>综合得分</th><th>等级</th><th>订单数</th><th>缺陷率</th></tr></thead><tbody>';
  for (const s of suppliers) {
    const gradeCls = s.composite_score >= 85 ? "sc-green" : (s.composite_score >= 70 ? "sc-amber" : "sc-red");
    html += `<tr>
      <td>${escapeHtml(s.name)}</td>
      <td>${s.delivery_score}</td>
      <td>${s.quality_score}</td>
      <td>${s.response_score}</td>
      <td>${s.price_score}</td>
      <td class="${gradeCls}" style="font-weight:700">${s.composite_score}</td>
      <td><span class="sc-badge ${gradeCls}">${s.grade}</span></td>
      <td>${s.orders}</td>
      <td>${s.defect_rate}%</td>
    </tr>`;
  }
  html += "</tbody></table>";
  return html;
}

/* ---- 物流线路表 ---- */

function _renderLogisticsTable(logistics) {
  if (!logistics || !logistics.length) return '<div class="state-cell">暂无物流数据（请先在途追踪中导入装箱单/SO）</div>';
  let html = '<table class="sc-table"><thead><tr><th>线路</th><th>运输方式</th><th>平均时效</th><th>目标时效</th><th>延误率</th><th>发货量</th><th>柜数</th><th>准时率</th></tr></thead><tbody>';
  for (const l of logistics) {
    const delayCls = l.delay_rate > 15 ? "sc-red" : (l.delay_rate > 8 ? "sc-amber" : "sc-green");
    const modeIcon = l.mode === "海运" ? "🚢" : (l.mode === "空运" ? "✈️" : "🚛");
    html += `<tr>
      <td>${escapeHtml(l.route)}</td>
      <td>${modeIcon} ${l.mode}</td>
      <td>${l.avg_days}天</td>
      <td>${l.target_days}天</td>
      <td class="${delayCls}">${l.delay_rate}%</td>
      <td>${(l.volume || 0).toLocaleString()}</td>
      <td>${l.containers || 0}</td>
      <td class="${delayCls}">${l.on_time}%</td>
    </tr>`;
  }
  html += "</tbody></table>";
  return html;
}

/* ---- 主渲染 ---- */

async function renderSupplyChain() {
  const d = _sc.data;
  if (!d) return;

  const kpiWrap = $("scKpiCards");
  if (kpiWrap) kpiWrap.innerHTML = _renderKPIs(d.kpis || {}, d.risk_summary || {});

  const invCanvas = $("scInvChart");
  if (invCanvas) _drawInvTrend(invCanvas, d.inv_trend || [], d.safety_threshold || 0);

  const pieCanvas = $("scPieChart");
  if (pieCanvas) _drawPie(pieCanvas, d.quality_dist);

  const riskWrap = $("scRiskBody");
  if (riskWrap) riskWrap.innerHTML = _renderRiskTable(d.sku_risks || []);

  const supWrap = $("scSupplierBody");
  if (supWrap) supWrap.innerHTML = _renderSupplierTable(d.suppliers || []);

  const logWrap = $("scLogisticsBody");
  if (logWrap) logWrap.innerHTML = _renderLogisticsTable(d.logistics || []);

  await loadAndRenderRestock();
}

/* ---- 备货分析 ---- */

let _restockData = null;

async function loadAndRenderRestock() {
  try {
    const d = await api("/api/restocking");
    _restockData = d;
    renderRestockCards(d);
    renderRestockTable(d);
  } catch (e) {
    const body = $("scRestockBody");
    if (body) body.innerHTML = '<div class="state-cell">备货数据加载失败: ' + escapeHtml(e.message) + '</div>';
  }
}

function renderRestockCards(d) {
  const s = d.summary || {};
  const cycle = d.cycle_days || 30;
  const wrap = $("scRestockCards");
  if (!wrap) return;
  const cards = [
    { label: "物流周期", value: cycle + "天", cls: "" },
    { label: "爆款", value: s.hot || 0, cls: "sc-red" },
    { label: "普通款", value: s.normal || 0, cls: "" },
    { label: "滞销款", value: s.slow || 0, cls: "sc-amber" },
    { label: "预警款", value: s.warning || 0, cls: "sc-amber" },
    { label: "缺货", value: s.out_of_stock || 0, cls: "sc-red" },
    { label: "需补货", value: s.need_restock || 0, cls: "sc-green" },
    { label: "紧急补货", value: s.urgent || 0, cls: "sc-red" },
  ];
  wrap.innerHTML = cards.map(c => `<div class="sc-restock-card ${c.cls}"><div class="sc-rc-val">${c.value}</div><div class="sc-rc-lbl">${c.label}</div></div>`).join("");

  const sumEl = $("scRestockSummary");
  if (sumEl) sumEl.textContent = `共 ${s.total || 0} 个SKU · 物流周期 ${cycle} 天`;
}

function renderRestockTable(d) {
  const items = d.items || [];
  const body = $("scRestockBody");
  if (!body) return;
  if (!items.length) { body.innerHTML = '<div class="state-cell">暂无备货数据</div>'; return; }

  const filter = $("scRestockFilter") ? $("scRestockFilter").value : "all";
  const kw = $("scRestockSearch") ? $("scRestockSearch").value.trim().toLowerCase() : "";

  let list = items;
  if (filter === "urgent") list = list.filter(r => r.restock_qty > 0);
  else if (filter !== "all") list = list.filter(r => r.tier === filter);

  if (kw) list = list.filter(r => fuzzyMatch(r.sku, kw) || fuzzyMatch(r.name, kw));

  const esc = escapeHtml;
  let html = '<table class="sc-table"><thead><tr>';
  html += '<th>优先级</th><th>SKU</th><th>产品</th><th>分级</th>';
  html += '<th>当前库存</th><th>在途</th><th>可售天数</th>';
  html += '<th>日均销量</th><th>7天趋势</th>';
  html += '<th>周转天数</th><th>建议补货</th><th>风险提示</th>';
  html += '</tr></thead><tbody>';

  for (const r of list) {
    const tierCls = r.tier === "hot" ? "sc-red" : r.tier === "slow" ? "sc-amber" : r.tier === "out_of_stock" ? "sc-red" : r.tier === "warning" ? "sc-amber" : "";
    const priorityCls = r.priority >= 30 ? "sc-red" : r.priority >= 15 ? "sc-amber" : "";
    const trendIcon = r.trend === "up" ? "📈 +" : r.trend === "down" ? "📉 " : "➡️ ";
    const trendCls = r.trend === "up" ? "sc-green" : r.trend === "down" ? "sc-red" : "";
    const sellCls = r.sellable_days <= 7 ? "sc-red" : r.sellable_days <= 14 ? "sc-amber" : "";
    const restockCls = r.restock_qty > 0 ? "sc-green" : "";
    const alerts = (r.alerts || []).map(a => '<span class="sc-alert-tag">' + esc(a) + '</span>').join(" ");

    html += `<tr>
      <td class="${priorityCls}">${r.priority}</td>
      <td class="mono">${esc(r.sku)}</td>
      <td>${esc(r.name) || "—"}</td>
      <td><span class="sc-badge ${tierCls}">${esc(r.tier_label)}</span></td>
      <td>${r.current_qty.toLocaleString()}</td>
      <td>${r.in_transit.toLocaleString()}</td>
      <td class="${sellCls}">${r.sellable_days}天</td>
      <td>${r.avg_daily}</td>
      <td class="${trendCls}">${trendIcon}${r.trend_pct}%</td>
      <td>${r.turnover_days}天</td>
      <td class="${restockCls}">${r.restock_qty > 0 ? r.restock_qty.toLocaleString() + " 件" : "—"}</td>
      <td>${alerts || "—"}</td>
    </tr>`;
  }
  html += '</tbody></table>';
  body.innerHTML = html;
}

function initSupplyChain() {
  const filter = $("scRestockFilter");
  if (filter) filter.addEventListener("change", () => { if (_restockData) renderRestockTable(_restockData); });
  const searchBtn = $("scRestockSearchBtn");
  if (searchBtn) searchBtn.addEventListener("click", () => { if (_restockData) renderRestockTable(_restockData); });
  const searchInput = $("scRestockSearch");
  if (searchInput) searchInput.addEventListener("keydown", (e) => { if (e.key === "Enter" && _restockData) renderRestockTable(_restockData); });
  const exportBtn = $("scRestockExport");
  if (exportBtn) exportBtn.addEventListener("click", _exportRestockCsv);
  const saveBtn = $("scRulesSave");
  if (saveBtn) saveBtn.addEventListener("click", _saveRules);
  const resetBtn = $("scRulesReset");
  if (resetBtn) resetBtn.addEventListener("click", _resetRules);
}

/* ---- 规则编辑器 ---- */

function loadRulesIntoUI(rules) {
  const c = rules.classification || {};
  const p = rules.priority || {};
  const a = rules.alerts || {};
  const s = rules.safety_stock || {};
  const set = (id, v) => { const el = $(id); if (el) el.value = v; };
  set("rule_hot_turnover", c.hot_turnover_max);
  set("rule_hot_daily", c.hot_avg_daily_min);
  set("rule_normal_turnover", c.normal_turnover_max);
  set("rule_normal_daily", c.normal_avg_daily_min);
  set("rule_warning_turnover", c.warning_turnover_min);
  set("rule_slow_turnover", c.slow_turnover_min);
  set("rule_prio_critical", p.critical_sellable_days);
  set("rule_prio_critical_s", p.critical_score);
  set("rule_prio_warning", p.warning_sellable_days);
  set("rule_prio_warning_s", p.warning_score);
  set("rule_prio_caution", p.caution_sellable_days);
  set("rule_prio_caution_s", p.caution_score);
  set("rule_prio_notransit", p.no_transit_caution_days);
  set("rule_prio_notransit_s", p.no_transit_score);
  set("rule_alert_critical", a.critical_sellable_days);
  set("rule_alert_low", a.low_sellable_days);
  set("rule_alert_slow", a.slow_turnover_min);
  set("rule_alert_transit", a.excess_transit_multiplier);
  set("rule_safety_z", s.service_level_z);
  set("rule_safety_min", s.min_safety_days);
}

function getRulesFromUI() {
  const g = (id) => parseFloat($(id)?.value) || 0;
  return {
    classification: {
      hot_turnover_max: g("rule_hot_turnover"), hot_avg_daily_min: g("rule_hot_daily"),
      normal_turnover_max: g("rule_normal_turnover"), normal_avg_daily_min: g("rule_normal_daily"),
      slow_turnover_min: g("rule_slow_turnover"), warning_turnover_min: g("rule_warning_turnover"),
    },
    priority: {
      critical_sellable_days: g("rule_prio_critical"), critical_score: g("rule_prio_critical_s"),
      warning_sellable_days: g("rule_prio_warning"), warning_score: g("rule_prio_warning_s"),
      caution_sellable_days: g("rule_prio_caution"), caution_score: g("rule_prio_caution_s"),
      no_transit_caution_days: g("rule_prio_notransit"), no_transit_score: g("rule_prio_notransit_s"),
      high_volume_min: 5, high_volume_score: 10, med_volume_min: 2, med_volume_score: 5,
      fast_turnover_max: 15, fast_turnover_score: 5,
    },
    alerts: {
      critical_sellable_days: g("rule_alert_critical"), low_sellable_days: g("rule_alert_low"),
      slow_turnover_min: g("rule_alert_slow"), medium_slow_turnover_min: 60,
      excess_transit_multiplier: g("rule_alert_transit"),
      slow_trend_turnover_min: 30, rising_trend_sellable_days: 21,
    },
    safety_stock: { service_level_z: g("rule_safety_z"), min_safety_days: g("rule_safety_min") },
  };
}

async function _saveRules() {
  const rules = getRulesFromUI();
  try {
    await api("/api/restocking_rules", { method: "POST", body: JSON.stringify(rules) });
    await loadAndRenderRestock();
  } catch (e) {
    alert("保存失败: " + e.message);
  }
}

async function _resetRules() {
  if (!confirm("恢复默认规则？")) return;
  try {
    const rules = await api("/api/restocking_rules");
    loadRulesIntoUI(rules);
  } catch (e) {
    alert("加载失败: " + e.message);
  }
}

function _exportRestockCsv() {
  if (!_restockData || !_restockData.items || !_restockData.items.length) return;
  const head = ["优先级", "SKU", "产品名", "分级", "当前库存", "在途库存", "可售天数", "日均销量", "7天均", "15天均", "30天均", "周转天数", "安全天数", "物流周期", "建议补货", "趋势", "趋势%", "风险提示"];
  const rows = _restockData.items.map(r => [
    r.priority, r.sku, r.name || "", r.tier_label, r.current_qty, r.in_transit, r.sellable_days,
    r.avg_daily, r.ads_7, r.ads_15, r.ads_30, r.turnover_days, r.safety_days, r.cycle_days,
    r.restock_qty, r.trend, r.trend_pct, (r.alerts || []).join("; ")
  ]);
  const csv = [head, ...rows].map(row => row.map(v => '"' + String(v ?? "").replace(/"/g, '""') + '"').join(",")).join("\r\n");
  downloadCsv("restock_" + new Date().toISOString().slice(0, 10) + ".csv", csv);
}

/* ---- 导航 ---- */

async function showSupplyChain() {
  setPanelVisible("supplyChainPanel");
  await loadSupplyChain();
  renderSupplyChain();
  try {
    const rules = await api("/api/restocking_rules");
    loadRulesIntoUI(rules);
  } catch (e) { /* ignore */ }
}
