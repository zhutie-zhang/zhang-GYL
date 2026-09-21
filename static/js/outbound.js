/* 出库模块：数据加载（渲染由 overseas.js 负责） */

async function loadOut(force) {
  try {
    let url = "/api/outbound";
    const params = [];
    const s = state.outStart, e = state.outEnd;
    if (s && e) {
      params.push("start=" + encodeURIComponent(s), "end=" + encodeURIComponent(e));
    } else if (s) {
      params.push("start=" + encodeURIComponent(s), "end=" + encodeURIComponent(s));
    } else if (e) {
      params.push("start=" + encodeURIComponent(e), "end=" + encodeURIComponent(e));
    }
    if (force) params.push("force=1");
    const scope = _ovLoadScope();
    if (scope) params.push("scope=" + encodeURIComponent(scope));
    if (params.length) url += "?" + params.join("&");
    state.out = await api(url);
  } catch (e) {
    throw e;
  }
  showErrors(state.out);
  if (state.view === "stats") renderStats();
  if (state.view === "boxes") renderBoxes();
  if (state.view === "rank") renderRank();
  if (state.view === "overseas") renderOverseas();
}
