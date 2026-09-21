/* 海外仓分析看板：全屏分时出库图 + 排名 + 信号面板 + 策略引擎 + 回测 */

const _ax = {
  data: null,
  period: 30,
  chartSku: "",
  playIdx: 0,
  playing: false,
  playTimer: null,
  strategies: [],
  logs: [],
};

/* ---- 数据获取 ---- */

function loadAnalytics(period) {
  _ax.period = period || 30;
  return fetch(`/api/analytics?period=${_ax.period}`)
    .then((r) => r.json())
    .then((d) => { _ax.data = d; return d; });
}

function loadBacktest(sku, maS, maL, cap) {
  const p = new URLSearchParams({ sku, ma_short: maS, ma_long: maL, capital: cap, period: 30 });
  return fetch(`/api/analytics/backtest?${p}`).then((r) => r.json());
}

/* ---- Canvas 时序图 ---- */

function _drawChart(canvas, series, metrics, signals, highlightIdx) {
  if (!canvas || !series || !series.length) return;
  const ctx = canvas.getContext("2d");
  const W = canvas.width = canvas.parentElement.clientWidth;
  const H = canvas.height = 280;
  const pad = { t: 30, r: 60, b: 40, l: 60 };
  const cw = W - pad.l - pad.r;
  const ch = H - pad.t - pad.b;
  ctx.clearRect(0, 0, W, H);

  const qtys = series.map((p) => p.qty);
  const maxQ = Math.max(...qtys, 1);
  const n = series.length;
  const step = n > 1 ? cw / (n - 1) : cw;

  const xOf = (i) => pad.l + i * step;
  const yOf = (v) => pad.t + ch - (v / maxQ) * ch;

  // 网格
  ctx.strokeStyle = "#e8ecf0";
  ctx.lineWidth = 0.5;
  for (let g = 0; g <= 4; g++) {
    const y = pad.t + (ch / 4) * g;
    ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke();
    ctx.fillStyle = "#8a94a6";
    ctx.font = "10px sans-serif";
    ctx.textAlign = "right";
    ctx.fillText(Math.round(maxQ * (1 - g / 4)).toLocaleString(), pad.l - 6, y + 3);
  }

  // 日期标签
  ctx.fillStyle = "#8a94a6";
  ctx.font = "10px sans-serif";
  ctx.textAlign = "center";
  const labelStep = Math.max(1, Math.floor(n / 8));
  for (let i = 0; i < n; i += labelStep) {
    ctx.fillText(series[i].date.slice(5), xOf(i), H - pad.b + 16);
  }

  // MA线
  const drawMA = (key, color) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    let started = false;
    for (let i = 0; i < metrics.length; i++) {
      if (metrics[i][key] == null) continue;
      const y = yOf(metrics[i][key]);
      if (!started) { ctx.moveTo(xOf(i), y); started = true; }
      else ctx.lineTo(xOf(i), y);
    }
    ctx.stroke();
  };
  drawMA("ma5", "#3b82f6");
  drawMA("ma10", "#f59e0b");
  drawMA("ma20", "#ef4444");

  // 出库柱状
  for (let i = 0; i < n; i++) {
    const x = xOf(i);
    const y = yOf(qtys[i]);
    const bw = Math.max(2, step * 0.6);
    ctx.fillStyle = (highlightIdx === i) ? "#1e2a47" : "rgba(30,42,71,0.7)";
    ctx.fillRect(x - bw / 2, y, bw, pad.t + ch - y);
  }

  // 信号标记
  if (signals) {
    for (let i = 0; i < signals.length; i++) {
      const s = signals[i];
      if (s.signal === "hold") continue;
      const x = xOf(i);
      const y = yOf(qtys[i]) - 12;
      const isBuy = s.signal.includes("buy");
      ctx.fillStyle = isBuy ? "#16a34a" : "#dc2626";
      ctx.font = "bold 11px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(isBuy ? "▲" : "▼", x, y);
    }
  }

  // 图例
  ctx.font = "10px sans-serif";
  const legends = [["出库量", "rgba(30,42,71,0.7)"], ["MA5", "#3b82f6"], ["MA10", "#f59e0b"], ["MA20", "#ef4444"]];
  let lx = pad.l;
  for (const [label, color] of legends) {
    ctx.fillStyle = color;
    ctx.fillRect(lx, 6, 12, 3);
    ctx.fillStyle = "#555";
    ctx.textAlign = "left";
    ctx.fillText(label, lx + 16, 11);
    lx += ctx.measureText(label).width + 32;
  }
}

/* ---- 排名滚动表 ---- */

function _renderRankTable(rank, maxH) {
  if (!rank || !rank.length) return '<div class="state-cell">暂无排名数据</div>';
  let html = '<table class="ax-rank-table"><thead><tr><th>#</th><th>SKU</th><th>本期</th><th>上期</th><th>增长率</th><th>趋势</th></tr></thead><tbody>';
  for (let i = 0; i < rank.length; i++) {
    const r = rank[i];
    const gClass = r.growth > 10 ? "ax-up" : (r.growth < -10 ? "ax-down" : "");
    const trendIcon = r.trend === "up" ? "📈" : (r.trend === "down" ? "📉" : "➡️");
    html += `<tr class="${gClass}"><td>${i + 1}</td><td class="sku-cell">${escapeHtml(r.sku)}</td><td>${r.cur_qty.toLocaleString()}</td><td>${r.prev_qty.toLocaleString()}</td><td class="${gClass}">${r.growth > 0 ? "+" : ""}${r.growth}%</td><td>${trendIcon}</td></tr>`;
  }
  html += "</tbody></table>";
  return html;
}

/* ---- 信号面板 ---- */

function _renderSignalPanel(summary, signals, sku) {
  let html = '<div class="ax-signal-grid">';
  const items = [
    ["出库量", summary.total_outbound?.toLocaleString() || "0", "ax-blue"],
    ["周环比", (summary.total_growth > 0 ? "+" : "") + (summary.total_growth || 0) + "%",
     summary.total_growth > 0 ? "ax-green" : (summary.total_growth < 0 ? "ax-red" : "")],
    ["活跃SKU", summary.active_skus || 0, ""],
    ["↑上涨", summary.rising_count || 0, "ax-green"],
    ["↓下跌", summary.falling_count || 0, "ax-red"],
  ];
  for (const [label, val, cls] of items) {
    html += `<div class="ax-signal-item ${cls}"><div class="ax-signal-val">${val}</div><div class="ax-signal-label">${label}</div></div>`;
  }
  html += "</div>";

  if (sku && signals && signals[sku]) {
    const last = signals[sku][signals[sku].length - 1];
    if (last && last.signal !== "hold") {
      const isBuy = last.signal.includes("buy");
      html += `<div class="ax-sig-badge ${isBuy ? "ax-sig-buy" : "ax-sig-sell"}">`;
      html += `<div class="ax-sig-type">${isBuy ? "▲ 买入信号" : "▼ 卖出信号"}</div>`;
      html += `<div class="ax-sig-reason">${(last.reasons || []).join(" · ")}</div>`;
      html += `<div class="ax-sig-strength">强度 ${(last.strength * 100).toFixed(0)}%</div>`;
      html += "</div>";
    }
  }
  return html;
}

/* ---- 策略引擎 ---- */

function _renderStrategyPanel() {
  return `
    <div class="ax-strat-params">
      <div class="ax-strat-row">
        <label>短均线 <input type="number" id="axMaShort" value="5" min="2" max="30" class="ax-input"></label>
        <label>长均线 <input type="number" id="axMaLong" value="20" min="5" max="60" class="ax-input"></label>
        <label>初始资金 <input type="number" id="axCapital" value="100000" min="10000" class="ax-input" style="width:100px"></label>
        <button id="axGenBtn" class="btn primary">生成策略</button>
      </div>
      <div class="ax-strat-row">
        <label>对比 SKU（逗号分隔）
          <input type="text" id="axCompareSkus" class="ax-input" style="width:300px" placeholder="如 SKU1,SKU2,SKU3">
        </label>
        <button id="axCompareBtn" class="btn ghost">多策略对比</button>
      </div>
    </div>
    <div id="axStratResult"></div>`;
}

function _renderBacktestResult(d) {
  if (d.error) return `<div class="ax-bt-error">${escapeHtml(d.error)}</div>`;
  const s = d.stats || {};
  let html = `<div class="ax-bt-header">回测报告 · ${escapeHtml(d.sku || "")}</div>`;
  html += `<div class="ax-bt-stats">`;
  html += `<div class="ax-bt-stat"><div class="ax-bt-val">${s.initial_capital?.toLocaleString()}</div><div class="ax-bt-lbl">初始资金</div></div>`;
  html += `<div class="ax-bt-stat"><div class="ax-bt-val">${s.final_value?.toLocaleString()}</div><div class="ax-bt-lbl">最终价值</div></div>`;
  const retCls = s.total_return > 0 ? "ax-green" : "ax-red";
  html += `<div class="ax-bt-stat ${retCls}"><div class="ax-bt-val">${s.total_return > 0 ? "+" : ""}${s.total_return}%</div><div class="ax-bt-lbl">总收益率</div></div>`;
  html += `<div class="ax-bt-stat"><div class="ax-bt-val">${s.total_trades || 0}</div><div class="ax-bt-lbl">总交易</div></div>`;
  html += `<div class="ax-bt-stat"><div class="ax-bt-val">${s.win_rate || 0}%</div><div class="ax-bt-lbl">胜率</div></div>`;
  html += `<div class="ax-bt-stat ax-red"><div class="ax-bt-val">-${s.max_drawdown || 0}%</div><div class="ax-bt-lbl">最大回撤</div></div>`;
  html += `</div>`;

  // 交易明细
  if (d.trades && d.trades.length) {
    html += '<div class="ax-bt-trades"><div class="ax-bt-sub">交易明细</div>';
    html += '<table class="ax-rank-table"><thead><tr><th>日期</th><th>操作</th><th>价格</th><th>数量</th><th>金额</th><th>盈亏</th></tr></thead><tbody>';
    for (const t of d.trades) {
      const pnl = t.pnl != null ? `<span class="${t.pnl > 0 ? 'ax-green' : 'ax-red'}">${t.pnl > 0 ? '+' : ''}${t.pnl}%</span>` : '—';
      html += `<tr><td>${t.date}</td><td class="${t.action === 'buy' ? 'ax-green' : 'ax-red'}">${t.action === 'buy' ? '买入' : '卖出'}</td><td>${t.price}</td><td>${t.shares}</td><td>${t.value?.toLocaleString()}</td><td>${pnl}</td></tr>`;
    }
    html += '</tbody></table></div>';
  }
  return html;
}

/* ---- 日志流 ---- */

function _addLog(msg, type) {
  const ts = new Date().toLocaleTimeString("zh-CN");
  _ax.logs.unshift({ ts, msg, type: type || "info" });
  if (_ax.logs.length > 100) _ax.logs.length = 100;
  _renderLogStream();
}

function _renderLogStream() {
  const el = $("axLogBody");
  if (!el) return;
  let html = "";
  for (const l of _ax.logs.slice(0, 30)) {
    const cls = l.type === "buy" ? "ax-green" : (l.type === "sell" ? "ax-red" : (l.type === "warn" ? "ax-amber" : ""));
    html += `<div class="ax-log-line ${cls}"><span class="ax-log-ts">${l.ts}</span> ${escapeHtml(l.msg)}</div>`;
  }
  el.innerHTML = html;
}

/* ---- 动画播放 ---- */

function _startPlayback(series, metrics, signals, canvas) {
  if (_ax.playing) { _stopPlayback(); return; }
  _ax.playing = true;
  _ax.playIdx = 0;
  _addLog("开始动画播放逐根推进", "info");
  const btn = $("axPlayBtn");
  if (btn) btn.textContent = "⏸ 暂停";
  _ax.playTimer = setInterval(() => {
    if (_ax.playIdx >= series.length) { _stopPlayback(); return; }
    _drawChart(canvas, series, metrics, signals, _ax.playIdx);
    const sig = signals && signals[_ax.playIdx];
    if (sig && sig.signal !== "hold") {
      const isBuy = sig.signal.includes("buy");
      _addLog(`${series[_ax.playIdx].date} ${isBuy ? "▲ 买入" : "▼ 卖出"} ${sig.reasons?.join(", ")}`, isBuy ? "buy" : "sell");
    }
    _ax.playIdx++;
  }, 120);
}

function _stopPlayback() {
  _ax.playing = false;
  if (_ax.playTimer) { clearInterval(_ax.playTimer); _ax.playTimer = null; }
  const btn = $("axPlayBtn");
  if (btn) btn.textContent = "▶ 播放";
}

/* ---- 主渲染 ---- */

function renderAnalytics() {
  const d = _ax.data;
  if (!d) return;

  // 图表
  const skus = Object.keys(d.series || {});
  if (skus.length && !_ax.chartSku) _ax.chartSku = skus[0];
  const canvas = $("axChart");
  const sel = $("axSkuSel");
  if (sel && !sel.options.length) {
    for (const s of skus) {
      const o = document.createElement("option");
      o.value = s; o.textContent = s;
      sel.appendChild(o);
    }
    sel.value = _ax.chartSku;
  }
  if (canvas && _ax.chartSku && d.series[_ax.chartSku]) {
    _drawChart(canvas, d.series[_ax.chartSku], d.metrics[_ax.chartSku] || [], d.signals || {});
  }

  // 排名
  const rankWrap = $("axRankBody");
  if (rankWrap) rankWrap.innerHTML = _renderRankTable(d.rank || []);

  // 信号面板
  const sigWrap = $("axSignals");
  if (sigWrap) sigWrap.innerHTML = _renderSignalPanel(d.summary || {}, d.signals || {}, _ax.chartSku);

  // 日志
  _renderLogStream();
}

function initAnalytics() {
  $("axPeriod7")?.addEventListener("click", () => _changePeriod(7));
  $("axPeriod30")?.addEventListener("click", () => _changePeriod(30));
  $("axPeriod60")?.addEventListener("click", () => _changePeriod(60));
  $("axSkuSel")?.addEventListener("change", (e) => {
    _ax.chartSku = e.target.value;
    renderAnalytics();
  });
  $("axPlayBtn")?.addEventListener("click", () => {
    const d = _ax.data;
    if (!d || !_ax.chartSku || !d.series[_ax.chartSku]) return;
    _startPlayback(d.series[_ax.chartSku], d.metrics[_ax.chartSku] || [],
      (d.signals || {})[_ax.chartSku] || [], $("axChart"));
  });
  const stratPanel = $("axStratPanel");
  if (stratPanel) stratPanel.innerHTML = _renderStrategyPanel();
  $("axGenBtn")?.addEventListener("click", _onGenStrategy);
  $("axCompareBtn")?.addEventListener("click", _onCompareStrategy);
}

async function _changePeriod(p) {
  document.querySelectorAll(".ax-period-btn").forEach((b) => b.classList.remove("active"));
  $("axPeriod" + p)?.classList.add("active");
  _addLog(`切换周期: ${p}天`, "info");
  await loadAnalytics(p);
  renderAnalytics();
}

async function _onGenStrategy() {
  const sku = _ax.chartSku;
  if (!sku) { alert("请先选择SKU"); return; }
  const maS = $("axMaShort")?.value || 5;
  const maL = $("axMaLong")?.value || 20;
  const cap = $("axCapital")?.value || 100000;
  _addLog(`生成策略: ${sku} MA${maS}/${maL}`, "info");
  const res = $("axStratResult");
  if (res) res.innerHTML = '<div class="ax-loading">回测中...</div>';
  try {
    const d = await loadBacktest(sku, maS, maL, cap);
    if (res) res.innerHTML = _renderBacktestResult(d);
    _addLog(`回测完成: 收益 ${(d.stats?.total_return || 0)}%, 胜率 ${(d.stats?.win_rate || 0)}%`, d.stats?.total_return > 0 ? "buy" : "sell");
  } catch (e) {
    if (res) res.innerHTML = `<div class="ax-bt-error">${escapeHtml(e.message)}</div>`;
    _addLog(`回测失败: ${e.message}`, "warn");
  }
}

async function _onCompareStrategy() {
  const skusStr = $("axCompareSkus")?.value || "";
  const skus = skusStr.split(",").map((s) => s.trim()).filter(Boolean);
  if (!skus.length) { alert("请输入至少一个SKU"); return; }
  const maS = $("axMaShort")?.value || 5;
  const maL = $("axMaLong")?.value || 20;
  const cap = $("axCapital")?.value || 100000;
  _addLog(`多策略对比: ${skus.join(", ")}`, "info");
  const res = $("axStratResult");
  if (res) res.innerHTML = '<div class="ax-loading">批量回测中...</div>';
  try {
    const results = await Promise.all(skus.map((s) => loadBacktest(s, maS, maL, cap).catch((e) => ({ sku: s, error: e.message }))));
    let html = '<div class="ax-compare-grid">';
    for (const d of results) {
      html += `<div class="ax-compare-card">${_renderBacktestResult(d)}</div>`;
    }
    html += "</div>";
    if (res) res.innerHTML = html;
  } catch (e) {
    if (res) res.innerHTML = `<div class="ax-bt-error">${escapeHtml(e.message)}</div>`;
  }
}

/* ---- 从海外仓切换到分析视图 ---- */

async function showAnalytics() {
  setPanelVisible("analyticsPanel");
  _addLog("加载分析数据...", "info");
  await loadAnalytics(_ax.period);
  renderAnalytics();
  _addLog(`数据加载完成: ${Object.keys(_ax.data?.series || {}).length} 个SKU`, "info");
}
