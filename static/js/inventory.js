/* 库存模块：数据加载（渲染由 overseas.js 负责） */

async function loadInv(force) {
  try {
    const url = "/api/inventory" + (force ? "?force=1" : "");
    state.inv = await api(url);
  } catch (e) {
    throw e;
  }
  showErrors(state.inv);
  setUpdated(state.inv.generated_at);
  if (state.view === "stats") renderStats();
  if (state.view === "boxes") renderBoxes();
  if (state.view === "rank") renderRank();
  if (state.view === "overseas") renderOverseas();
}
