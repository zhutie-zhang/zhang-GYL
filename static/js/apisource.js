/* 自定义 API 数据源管理模块 */

const _csState = {
  sources: [],
  presetTypes: {},
  editing: null,
};

function _csApi(method, path, body) {
  const opt = { method, headers: { "Content-Type": "application/json" } };
  if (body) opt.body = JSON.stringify(body);
  return fetch("/api/custom_sources" + path, opt).then((r) => r.json());
}

/* ---- 数据源列表 ---- */

function renderCsList() {
  const tbody = document.querySelector("#csListTable tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  if (!_csState.sources.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="state-cell">暂无自定义数据源，点击上方"新增"添加</td></tr>';
    return;
  }
  for (const s of _csState.sources) {
    const tr = document.createElement("tr");
    const enabled = s.enabled !== false;
    tr.innerHTML = `
      <td><span class="cs-status ${enabled ? "cs-on" : "cs-off"}">${enabled ? "启用" : "停用"}</span></td>
      <td>${escapeHtml(s.name || "")}</td>
      <td>${escapeHtml(s.type === "custom" ? "自定义 REST" : (_csState.presetTypes[s.type] || {}).name || s.type)}</td>
      <td>${escapeHtml(s.group || "")}</td>
      <td>${escapeHtml(s.inventory_url || "")}</td>
      <td class="cs-actions">
        <button class="btn ghost btn-xs" data-cs-toggle="${s.id}" title="切换启用/停用">${enabled ? "停用" : "启用"}</button>
        <button class="btn ghost btn-xs" data-cs-edit="${s.id}" title="编辑">编辑</button>
        <button class="btn ghost btn-xs" data-cs-test="${s.id}" title="测试连接">测试</button>
        <button class="btn ghost btn-xs" data-cs-del="${s.id}" title="删除" style="color:var(--err)">删除</button>
      </td>`;
    tbody.appendChild(tr);
  }
}

function refreshCsList() {
  _csApi("GET", "").then((d) => {
    _csState.sources = d.sources || [];
    _csState.presetTypes = d.preset_types || {};
    renderCsList();
  });
}

/* ---- 模态弹窗 ---- */

function _csBuildForm(s) {
  const isCustom = !s || s.type === "custom";
  const authType = (s && s.auth && s.auth.type) || "none";
  return `
    <div class="form-row">
      <label class="f-label">名称 <span class="req">*</span></label>
      <input type="text" id="csfName" class="date" value="${escapeHtml((s && s.name) || "")}" placeholder="如：我的仓库A">
    </div>
    <div class="form-row">
      <label class="f-label">分组</label>
      <input type="text" id="csfGroup" class="date" value="${escapeHtml((s && s.group) || "")}" placeholder="如：group1">
    </div>
    <div class="form-row">
      <label class="f-label">账号（可选）</label>
      <input type="text" id="csfAccount" class="date" value="${escapeHtml((s && s.account) || "")}" placeholder="备注用">
    </div>
    <div class="form-row">
      <label class="f-label">接入类型</label>
      <select id="csfType" class="filter-select">
        <option value="custom" ${isCustom ? "selected" : ""}>自定义 REST API</option>
        <option value="xlwms" ${s && s.type === "xlwms" ? "selected" : ""}>领星 OMS</option>
        <option value="lecangs" ${s && s.type === "lecangs" ? "selected" : ""}>乐歌</option>
        <option value="yunwms" ${s && s.type === "yunwms" ? "selected" : ""}>乐舱</option>
        <option value="anmei" ${s && s.type === "anmei" ? "selected" : ""}>安美</option>
        <option value="aidelivery" ${s && s.type === "aidelivery" ? "selected" : ""}>安得力</option>
      </select>
    </div>
    <div id="csfPresetFields" class="csf-section" style="display:${isCustom ? "none" : "block"}">
      <div class="form-row csf-preset-auth">
        <label class="f-label">鉴权方式</label>
        <select id="csfAuthType" class="filter-select">
          <option value="none" ${authType === "none" ? "selected" : ""}>无鉴权</option>
          <option value="apikey" ${authType === "apikey" ? "selected" : ""}>API Key</option>
          <option value="bearer" ${authType === "bearer" ? "selected" : ""}>Bearer Token</option>
          <option value="basic" ${authType === "basic" ? "selected" : ""}>Basic Auth</option>
          <option value="custom_header" ${authType === "custom_header" ? "selected" : ""}>自定义 Header</option>
        </select>
      </div>
      <div id="csfAuthFields"></div>
    </div>
    <div id="csfCustomSection" class="csf-section" style="display:${isCustom ? "block" : "none"}">
      <div class="csf-sub">鉴权</div>
      <div class="form-row">
        <label class="f-label">鉴权方式</label>
        <select id="csfCAuthType" class="filter-select">
          <option value="none" ${authType === "none" ? "selected" : ""}>无鉴权</option>
          <option value="apikey" ${authType === "apikey" ? "selected" : ""}>API Key</option>
          <option value="bearer" ${authType === "bearer" ? "selected" : ""}>Bearer Token</option>
          <option value="basic" ${authType === "basic" ? "selected" : ""}>Basic Auth</option>
          <option value="custom_header" ${authType === "custom_header" ? "selected" : ""}>自定义 Header</option>
        </select>
      </div>
      <div id="csfCAuthFields"></div>
      <div class="csf-sub">库存 API</div>
      <div class="form-row">
        <label class="f-label">URL</label>
        <input type="text" id="csfInvUrl" class="date" value="${escapeHtml((s && s.inventory_url) || "")}" placeholder="https://api.example.com/inventory">
      </div>
      <div class="form-row">
        <label class="f-label">方法</label>
        <select id="csfInvMethod" class="filter-select">
          <option value="GET" ${(!s || (s.inventory_method || "GET") === "GET") ? "selected" : ""}>GET</option>
          <option value="POST" ${s && s.inventory_method === "POST" ? "selected" : ""}>POST</option>
        </select>
        <label class="f-label" style="margin-left:12px">Items 路径</label>
        <input type="text" id="csfInvItems" class="date" style="width:120px" value="${escapeHtml((s && s.inventory_items_path) || "")}" placeholder="data.items">
      </div>
      <div class="form-row">
        <label class="f-label">SKU 路径</label>
        <input type="text" id="csfInvSku" class="date" style="width:100px" value="${escapeHtml((s && s.inventory_sku_path) || "sku")}" placeholder="sku">
        <label class="f-label" style="margin-left:8px">品名路径</label>
        <input type="text" id="csfInvName" class="date" style="width:100px" value="${escapeHtml((s && s.inventory_name_path) || "name")}" placeholder="name">
        <label class="f-label" style="margin-left:8px">数量路径</label>
        <input type="text" id="csfInvQty" class="date" style="width:100px" value="${escapeHtml((s && s.inventory_qty_path) || "qty")}" placeholder="qty">
      </div>
      <div class="form-row">
        <label class="f-label">仓库路径（可选，多仓时用）</label>
        <input type="text" id="csfInvWh" class="date" style="width:120px" value="${escapeHtml((s && s.inventory_wh_path) || "")}" placeholder="warehouse">
      </div>
      <div class="csf-sub">出库 API</div>
      <div class="form-row">
        <label class="f-label">URL</label>
        <input type="text" id="csfOutUrl" class="date" value="${escapeHtml((s && s.outbound_url) || "")}" placeholder="https://api.example.com/outbound">
      </div>
      <div class="form-row">
        <label class="f-label">方法</label>
        <select id="csfOutMethod" class="filter-select">
          <option value="GET" ${(!s || (s.outbound_method || "GET") === "GET") ? "selected" : ""}>GET</option>
          <option value="POST" ${s && s.outbound_method === "POST" ? "selected" : ""}>POST</option>
        </select>
        <label class="f-label" style="margin-left:12px">Items 路径</label>
        <input type="text" id="csfOutItems" class="date" style="width:120px" value="${escapeHtml((s && s.outbound_items_path) || "")}" placeholder="data.items">
      </div>
      <div class="form-row">
        <label class="f-label">SKU 路径</label>
        <input type="text" id="csfOutSku" class="date" style="width:100px" value="${escapeHtml((s && s.outbound_sku_path) || "sku")}" placeholder="sku">
        <label class="f-label" style="margin-left:8px">品名路径</label>
        <input type="text" id="csfOutName" class="date" style="width:100px" value="${escapeHtml((s && s.outbound_name_path) || "name")}" placeholder="name">
        <label class="f-label" style="margin-left:8px">数量路径</label>
        <input type="text" id="csfOutQty" class="date" style="width:100px" value="${escapeHtml((s && s.outbound_qty_path) || "qty")}" placeholder="qty">
      </div>
      <div class="form-row">
        <label class="f-label">日期路径</label>
        <input type="text" id="csfOutDate" class="date" style="width:100px" value="${escapeHtml((s && s.outbound_date_path) || "date")}" placeholder="date">
        <label class="f-label" style="margin-left:8px">仓库路径（可选）</label>
        <input type="text" id="csfOutWh" class="date" style="width:120px" value="${escapeHtml((s && s.outbound_wh_path) || "")}" placeholder="warehouse">
      </div>
      <div class="form-row">
        <label class="f-label">请求体 JSON（POST 时）</label>
        <textarea id="csfInvBody" class="csf-textarea" placeholder='{"page":1,"limit":100}'>${s && s.inventory_body ? JSON.stringify(s.inventory_body, null, 2) : ""}</textarea>
      </div>
      <div class="form-row">
        <label class="f-label">自定义请求头 JSON</label>
        <textarea id="csfHeaders" class="csf-textarea" placeholder='{"X-Custom":"value"}'>${s && s.inventory_headers ? JSON.stringify(s.inventory_headers, null, 2) : ""}</textarea>
      </div>
    </div>`;
}

function _csRenderAuthFields(containerId, prefix, s) {
  const c = $(containerId);
  if (!c) return;
  const sel = $(prefix);
  const t = sel ? sel.value : "none";
  const auth = s && s.auth ? s.auth : {};
  if (t === "apikey") {
    c.innerHTML = `<div class="form-row"><label class="f-label">Header 名</label><input type="text" id="${prefix}H" class="date" value="${escapeHtml(auth.header || "X-API-Key")}"><label class="f-label" style="margin-left:8px">Key</label><input type="text" id="${prefix}K" class="date" value="${escapeHtml(auth.key || "")}"></div>`;
  } else if (t === "bearer") {
    c.innerHTML = `<div class="form-row"><label class="f-label">Token</label><input type="text" id="${prefix}T" class="date" value="${escapeHtml(auth.token || "")}" style="width:300px"></div>`;
  } else if (t === "basic") {
    c.innerHTML = `<div class="form-row"><label class="f-label">用户名</label><input type="text" id="${prefix}U" class="date" value="${escapeHtml(auth.username || "")}"><label class="f-label" style="margin-left:8px">密码</label><input type="password" id="${prefix}P" class="date" value="${escapeHtml(auth.password || "")}"></div>`;
  } else if (t === "custom_header") {
    c.innerHTML = `<div class="form-row"><label class="f-label">自定义 Header JSON</label><textarea id="${prefix}J" class="csf-textarea">${auth.headers ? JSON.stringify(auth.headers, null, 2) : ""}</textarea></div>`;
  } else {
    c.innerHTML = "";
  }
}

function _csGatherAuth(prefix) {
  const sel = $(prefix);
  const t = sel ? sel.value : "none";
  const auth = { type: t };
  if (t === "apikey") {
    auth.header = $(prefix + "H") ? $(prefix + "H").value : "X-API-Key";
    auth.key = $(prefix + "K") ? $(prefix + "K").value : "";
  } else if (t === "bearer") {
    auth.token = $(prefix + "T") ? $(prefix + "T").value : "";
  } else if (t === "basic") {
    auth.username = $(prefix + "U") ? $(prefix + "U").value : "";
    auth.password = $(prefix + "P") ? $(prefix + "P").value : "";
  } else if (t === "custom_header") {
    try { auth.headers = JSON.parse($(prefix + "J").value || "{}"); } catch (e) { auth.headers = {}; }
  }
  return auth;
}

function _csGatherForm() {
  const type = $("csfType").value;
  const data = {
    name: $("csfName").value.trim(),
    group: $("csfGroup").value.trim(),
    account: $("csfAccount").value.trim(),
    type: type,
    enabled: true,
  };
  if (!data.name) return null;
  if (type === "custom") {
    data.auth = _csGatherAuth("csfCAuthType");
    data.inventory_url = $("csfInvUrl").value.trim();
    data.inventory_method = $("csfInvMethod").value;
    data.inventory_items_path = $("csfInvItems").value.trim();
    data.inventory_sku_path = $("csfInvSku").value.trim();
    data.inventory_name_path = $("csfInvName").value.trim();
    data.inventory_qty_path = $("csfInvQty").value.trim();
    data.inventory_wh_path = $("csfInvWh").value.trim();
    data.outbound_url = $("csfOutUrl").value.trim();
    data.outbound_method = $("csfOutMethod").value;
    data.outbound_items_path = $("csfOutItems").value.trim();
    data.outbound_sku_path = $("csfOutSku").value.trim();
    data.outbound_name_path = $("csfOutName").value.trim();
    data.outbound_qty_path = $("csfOutQty").value.trim();
    data.outbound_date_path = $("csfOutDate").value.trim();
    data.outbound_wh_path = $("csfOutWh").value.trim();
    try { data.inventory_body = JSON.parse($("csfInvBody").value || "null"); } catch (e) { data.inventory_body = null; }
    try { data.inventory_headers = JSON.parse($("csfHeaders").value || "null"); } catch (e) { data.inventory_headers = null; }
  } else {
    data.auth = _csGatherAuth("csfAuthType");
  }
  return data;
}

function openCsModal(source) {
  _csState.editing = source || null;
  const m = $("csModal");
  const body = $("csModalBody");
  const title = $("csModalTitle");
  title.textContent = source ? "编辑数据源" : "新增数据源";
  body.innerHTML = _csBuildForm(source);
  m.classList.remove("hidden");

  const typeSel = $("csfType");
  typeSel.addEventListener("change", () => {
    const isCustom = typeSel.value === "custom";
    $("csfCustomSection").style.display = isCustom ? "block" : "none";
    $("csfPresetFields").style.display = isCustom ? "none" : "block";
  });

  const authSel = $("csfAuthType");
  if (authSel) {
    authSel.addEventListener("change", () => _csRenderAuthFields("csfAuthFields", "csfAuthType", source));
    _csRenderAuthFields("csfAuthFields", "csfAuthType", source);
  }
  const cAuthSel = $("csfCAuthType");
  if (cAuthSel) {
    cAuthSel.addEventListener("change", () => _csRenderAuthFields("csfCAuthFields", "csfCAuthType", source));
    _csRenderAuthFields("csfCAuthFields", "csfCAuthType", source);
  }
}

function closeCsModal() {
  $("csModal").classList.add("hidden");
  _csState.editing = null;
}

function _csSave() {
  const data = _csGatherForm();
  if (!data) { alert("请填写名称"); return; }
  const p = _csState.editing
    ? _csApi("PUT", "/" + _csState.editing.id, data)
    : _csApi("POST", "", data);
  p.then((d) => {
    if (d.error) { alert(d.error); return; }
    closeCsModal();
    refreshCsList();
    refreshAll(false);
  });
}

function _csDelete(id) {
  if (!confirm("确认删除该数据源？")) return;
  _csApi("DELETE", "/" + id).then(() => { refreshCsList(); refreshAll(false); });
}

function _csToggle(id) {
  const s = _csState.sources.find((x) => x.id === id);
  if (!s) return;
  _csApi("POST", "/" + id + "/toggle", { enabled: s.enabled === false }).then(() => {
    refreshCsList();
    refreshAll(false);
  });
}

function _csTest(id) {
  const btn = document.querySelector(`[data-cs-test="${id}"]`);
  if (btn) { btn.textContent = "测试中…"; btn.disabled = true; }
  _csApi("POST", "/" + id + "/test").then((d) => {
    if (btn) { btn.textContent = "测试"; btn.disabled = false; }
    let msg = "";
    if (d.results) {
      for (const [k, v] of Object.entries(d.results)) {
        if (!v) continue;
        const label = k === "inventory" ? "库存" : "出库";
        msg += label + (v.ok ? " ✓ " + v.message : " ✗ " + v.message) + "\n";
      }
    }
    if (d.error) msg = d.error;
    alert(msg || "测试完成");
  }).catch((e) => {
    if (btn) { btn.textContent = "测试"; btn.disabled = false; }
    alert("测试失败: " + e.message);
  });
}

/* ---- 初始化 ---- */

function initApiSources() {
  refreshCsList();

  $("csAddBtn").addEventListener("click", () => openCsModal(null));
  $("csModalClose").addEventListener("click", closeCsModal);
  $("csModalSave").addEventListener("click", _csSave);
  $("csModal").addEventListener("click", (e) => { if (e.target === $("csModal")) closeCsModal(); });

  const tbody = document.querySelector("#csListTable");
  if (tbody) {
    tbody.addEventListener("click", (e) => {
      const t = e.target;
      if (t.dataset.csDel) _csDelete(t.dataset.csDel);
      else if (t.dataset.csToggle) _csToggle(t.dataset.csToggle);
      else if (t.dataset.csTest) _csTest(t.dataset.csTest);
      else if (t.dataset.csEdit) {
        const s = _csState.sources.find((x) => x.id === t.dataset.csEdit);
        if (s) openCsModal(s);
      }
    });
  }
}
