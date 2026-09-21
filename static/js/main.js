/* 主模块：初始化 + 全局事件绑定 + 刷新调度 */

async function refreshAll(force) {
  if (state.loading) return;
  state.loading = true;
  $("refreshBtn").disabled = true;
  $("refreshBtn").textContent = "刷新中…";
  try {
    await Promise.all([loadInv(force), loadOut(force)]);
  } catch (e) {
    $("errorBar").textContent = "⚠ " + e.message;
    $("errorBar").classList.remove("hidden");
  } finally {
    state.loading = false;
    $("refreshBtn").disabled = false;
    $("refreshBtn").textContent = "刷新数据";
  }
}

async function init() {
  let autoTimer = null;
  try {
    const res = await api("/api/warehouses");
    state.groups = res.groups || [];
    state.warehouses = res.warehouses.filter((w) => w.enabled);
    if (res.auto_refresh_seconds) AUTO_INTERVAL = res.auto_refresh_seconds * 1000;
  } catch (_) { /* ignore */ }
  renderTabs();

  initProducts();
  initStats();
  initRank();
  initTransit();
  initOverseas();
  initApiSources();
  initAnalytics();
  initSupplyChain();
  initPricing();

  $("refreshBtn").addEventListener("click", () => refreshAll(true));
  $("autoRefresh").addEventListener("change", (e) => {
    if (e.target.checked) autoTimer = setInterval(() => refreshAll(false), AUTO_INTERVAL);
    else clearInterval(autoTimer);
  });

  // 首次数据加载完成后再启用自动刷新，避免与初始加载重复触发
  await refreshAll(false);
  await showOverseas();
  if (!$("autoRefresh").checked) $("autoRefresh").checked = true;
  if (autoTimer) clearInterval(autoTimer);
  autoTimer = setInterval(() => refreshAll(false), AUTO_INTERVAL);
}

init();
