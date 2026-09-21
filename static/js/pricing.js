/* pricing.js — v5 (manual supplier entry, paste import, inline edit) */
let _suppliers = {};
let _lastBatchResult = null;
let _pasteState = null;
let _editingSid = null;
let _bulkSelected = new Set();
let _priceOrder = null; /* array of supplier ids in current display order for batch results */

function initPricing() {
  _populateZones();
  const tbody = $("batchBody");
  if (tbody && !tbody.children.length) addBatchRow();
}

function showPricing() {
  state.view = "pricing";
  renderTabs();
  setPanelVisible("pricingPanel");
  loadSuppliers();
}

function _populateZones() {
  const sel = $("pricingZone");
  if (!sel) return;
  const zones = ["Zone2","Zone3","Zone4","Zone5","Zone6","Zone7","Zone8"];
  sel.innerHTML = zones.map(function(z) {
    return '<option value="' + z + '"' + (z === "Zone5" ? " selected" : "") + '>' + z.replace("Zone","Zone ") + '</option>';
  }).join('');
}

async function loadSuppliers() {
  try {
    const res = await api("/api/suppliers");
    _suppliers = res.suppliers || {};
    renderSupplierCards();
  } catch (e) {
    console.error("loadSuppliers", e);
  }
}

/* ── Rendering ─────────────────────────────────────────────── */
function renderSupplierCards() {
  var area = $("supplierList");
  var batchArea = $("pricingBatchArea");
  if (!area) return;
  var ids = Object.keys(_suppliers);
  if (!ids.length) {
    area.innerHTML = '<div class="sc-empty">尚未创建供应商，点击上方按钮新建</div>';
    if (batchArea) batchArea.style.display = "none";
    return;
  }
  if (batchArea) batchArea.style.display = "block";
  area.innerHTML = ids.map(function(sid) {
    var sp = _suppliers[sid];
    var editing = (_editingSid === sid);
    return renderSupplierCard(sid, sp, editing);
  }).join('');
}

function renderSupplierCard(sid, sp, editing) {
  var html = '<div class="supplier-card' + (editing ? ' editing' : '') + '">';
  html += renderHead(sid, sp, editing);
  html += renderOutbound(sid, sp, editing);
  html += renderShipping(sid, sp, editing);
  html += renderFuel(sid, sp, editing);
  html += renderSurcharges(sid, sp, "residential", "住宅地址费", editing);
  html += renderSurcharges(sid, sp, "ahs_weight", "AHS超重费（≥50LB）", editing);
  html += renderCustomFees(sid, sp, editing);
  html += '</div>';
  return html;
}

function renderHead(sid, sp, editing) {
  var html = '<div class="supplier-head">';
  html += '<label class="sel-wrap" title="选择以批量编辑"><input type="checkbox" class="sel-cb" ' + (_bulkSelected.has(sid) ? 'checked' : '') + ' onchange="toggleBulkSelect(\'' + sid + '\',this.checked)"></label>';
  if (editing) {
    html += '<div class="supplier-name"><input class="cell-input" id="edit-supplier-name" value="' + escapeHtml(sp.name) + '" data-field="name" style="width:200px"></div>';
  } else {
    html += '<div class="supplier-name">' + escapeHtml(sp.name) + '</div>';
  }
  html += '<div class="supplier-actions">';
  if (editing) {
    html += '<button class="btn sm" onclick="saveSupplier(\'' + sid + '\')">✓ 保存全部</button>';
    html += '<button class="btn sm ghost" onclick="cancelEditSupplier()">取消</button>';
  } else {
    html += '<button class="btn sm primary" onclick="startEditSupplier(\'' + sid + '\')">编辑</button>';
    html += '<button class="btn sm ghost" onclick="deleteSupplier(\'' + sid + '\')">删除</button>';
  }
  html += '</div></div>';
  return html;
}

/* ── Outbound ── */
function renderOutbound(sid, sp, editing) {
  var ob = sp.outbound || [];
  var html = '<div class="supplier-module">';
  html += '<div class="module-head"><span class="module-title">&#9654; 库内操作费（出库）— ' + ob.length + '段</span>';
  html += '<span class="module-actions">';
  if (editing) {
    html += '<button class="btn sm ghost" onclick="addOutboundRow(\'' + sid + '\')">+ 添加档</button>';
  } else {
    html += '<button class="btn sm ghost" onclick="pasteOutbound(\'' + sid + '\')">粘贴导入</button>';
  }
  html += '</span></div><div class="module-body">';
  html += '<table class="mod-tbl" data-module="outbound"><thead><tr><th>重量段(lbs)</th><th>单价($)</th><th></th></tr></thead><tbody>';
  ob.forEach(function(t, i) {
    html += '<tr data-row="' + i + '">';
    if (editing) {
      var maxStr = t.max_lbs >= 9999 ? '9999' : t.max_lbs;
      html += '<td><input class="cell-input" data-k="min" value="' + escapeNum(t.min_lbs) + '" style="width:70px">–<input class="cell-input" data-k="max" value="' + escapeNum(maxStr) + '" style="width:70px"></td>';
      html += '<td><input class="cell-input" data-k="price" type="number" step="0.01" min="0" value="' + escapeNum(t.price) + '" style="width:70px"></td>';
      html += '<td><button class="btn sm" style="color:#ef4444;padding:1px 5px" onclick="delOutboundRow(\'' + sid + '\',' + i + ')">删除</button></td>';
    } else {
      var maxOut = t.max_lbs >= 9999 ? '∞' : t.max_lbs;
      html += '<td>' + t.min_lbs + ' – ' + maxOut + '</td>';
      html += '<td>$' + t.price.toFixed(2) + '</td>';
      html += '<td><button class="btn sm" style="color:#ef4444;padding:1px 5px" onclick="delOutboundRow(\'' + sid + '\',' + i + ')">删除</button></td>';
    }
    html += '</tr>';
  });
  html += '</tbody></table>';
  html += '</div></div>';
  return html;
}

/* ── Shipping ── */
function renderShipping(sid, sp, editing) {
  var sz = sp.shipping_zones || {};
  var szZones = Object.keys(sz);
  var html = '<div class="supplier-module">';
  var shipSummary = szZones.length ? sp.carrier + ' · ' + szZones.length + '区' : '未录入';
  html += '<div class="module-head"><span class="module-title">&#9654; 基础运费 — ' + escapeHtml(shipSummary) + '</span>';
  html += '<span class="module-actions">';
  if (editing) {
    html += '<button class="btn sm ghost" onclick="addShippingZones(\'' + sid + '\')">+ 添加Zone列</button>';
  } else {
    html += '<button class="btn sm ghost" onclick="pasteShipping(\'' + sid + '\')">粘贴导入</button>';
  }
  html += '</span></div><div class="module-body">';
  if (szZones.length) {
    html += _renderShippingTable(sid, sp, sz, szZones, editing);
  } else {
    html += '<div class="mod-empty">点击「粘贴导入」添加运费数据</div>';
  }
  html += '</div></div>';
  return html;
}

function _renderShippingTable(sid, sp, sz, szZones, editing) {
  var allWeights = [];
  szZones.forEach(function(z) {
    Object.keys(sz[z]).forEach(function(w) {
      if (allWeights.indexOf(w) === -1) allWeights.push(w);
    });
  });
  allWeights.sort(function(a, b) { return parseFloat(a) - parseFloat(b); });
  szZones.sort();

  var html = '<div class="matrix-wrap"><table class="mod-matrix" data-module="shipping" data-szones="' + escapeHtml(szZones.join(',')) + '"><thead><tr><th>Weight(lbs)</th>';
  szZones.forEach(function(z) {
    html += '<th>' + z.replace("Zone","Zone ") + '</th>';
  });
  html += '<th></th>';
  html += '</tr></thead><tbody>';

  allWeights.forEach(function(w, wi) {
    html += '<tr data-row="' + escapeHtml(w) + '">';
    if (editing) {
      html += '<td class="mm-weight"><input class="cell-input" data-k="weight" value="' + escapeHtml(w) + '" style="width:55px"></td>';
    } else {
      html += '<td class="mm-weight">' + w + '</td>';
    }
    szZones.forEach(function(z) {
      var v = sz[z][w];
      var key = z + '|' + w;
      if (editing) {
        html += '<td><input class="cell-input" data-k="' + key + '" type="number" step="0.01" min="0" value="' + (v !== undefined ? escapeNum(v) : '') + '" style="width:65px"></td>';
      } else {
        html += '<td>' + (v !== undefined ? '$' + v.toFixed(2) : '—') + '</td>';
      }
    });
    html += '<td><button class="btn sm" style="color:#ef4444;padding:1px 5px" onclick="delShippingRow(\'' + sid + '\',\'' + escAttr(w) + '\')">删除</button></td>';
    html += '</tr>';
  });
  if (editing) {
    html += '<tr><td class="mm-weight" colspan="' + (szZones.length + 2) + '"><button class="btn sm" onclick="addShippingRow(\'' + sid + '\',\'' + escapeHtml(szZones.join(',')) + '\')">+ 添加重量段</button></td></tr>';
  }
  html += '</tbody></table></div>';
  return html;
}

/* ── Fuel ── */
function renderFuel(sid, sp, editing) {
  var html = '<div class="supplier-module">';
  html += '<div class="module-head"><span class="module-title">&#9654; 燃油附加费</span>';
  html += '<span class="module-actions">';
  if (editing) {
    html += '';
  } else {
    html += '<button class="btn sm ghost" onclick="pasteFuel(\'' + sid + '\')">粘贴导入</button>';
  }
  html += '</span></div><div class="module-body">';
  if (editing) {
    html += '<input class="cell-input" data-module="fuel" data-field="fuel_pct" type="number" step="0.1" min="0" value="' + (sp.fuel_pct || 0) + '" style="width:100px"> %';
  } else {
    html += '<div class="surcharge-tags"><span class="stag">' + (sp.fuel_pct > 0 ? sp.fuel_pct + '%' : '未录入') + '</span></div>';
  }
  html += '</div></div>';
  return html;
}

/* ── Residential / AHS ── */
function renderSurcharges(sid, sp, stype, label, editing) {
  var data = sp[stype] || {};
  var keys = Object.keys(data);
  var html = '<div class="supplier-module">';
  html += '<div class="module-head"><span class="module-title">&#9654; ' + label + ' — ' + keys.length + '个Zone</span>';
  html += '<span class="module-actions">';
  if (editing) {
    html += '<button class="btn sm ghost" onclick="addSurchargeRow(\'' + sid + '\',\'' + stype + '\')">+ 添加Zone</button>';
  } else {
    html += '<button class="btn sm ghost" onclick="pasteSurcharges(\'' + sid + '\',\'' + stype + '\')">粘贴导入</button>';
  }
  html += '</span></div><div class="module-body">';
  if (keys.length || editing) {
    html += '<table class="mod-tbl" data-module="' + stype + '"><thead><tr><th>Zone</th><th>价格($)</th><th></th></tr></thead><tbody>';
    keys.sort().forEach(function(k, i) {
      html += '<tr data-row="' + escapeHtml(k) + '">';
      if (editing) {
        html += '<td><input class="cell-input" data-k="zone" value="' + escapeHtml(k) + '" style="width:80px"></td>';
        html += '<td><input class="cell-input" data-k="price" type="number" step="0.01" min="0" value="' + escapeNum(data[k]) + '" style="width:70px"></td>';
      } else {
        html += '<td>' + k.replace("Zone","Zone ") + '</td>';
        html += '<td>$' + data[k].toFixed(2) + '</td>';
      }
      html += '<td><button class="btn sm" style="color:#ef4444;padding:1px 5px" onclick="delSurchargeRow(\'' + sid + '\',\'' + stype + '\',\'' + escAttr(k) + '\')">删除</button></td>';
      html += '</tr>';
    });
    if (editing) {
      html += '<tr><td colspan="3"><button class="btn sm" onclick="addSurchargeRow(\'' + sid + '\',\'' + stype + '\')">+ 添加Zone</button></td></tr>';
    }
    html += '</tbody></table>';
  } else {
    html += '<div class="mod-empty">点击「粘贴导入」添加数据</div>';
  }
  html += '</div></div>';
  return html;
}

/* ── Custom fees (configurable fee items) ──────────────────── */
function renderCustomFees(sid, sp, editing) {
  var fees = sp.custom_fees || [];
  var html = '<div class="supplier-module">';
  html += '<div class="module-head"><span class="module-title">&#9654; 自定义费用 — ' + fees.length + '项</span>';
  html += '<span class="module-actions">';
  if (editing) {
    html += '<button class="btn sm ghost" onclick="addCustomFeeRow(\'' + sid + '\')">+ 添加费用项</button>';
  } else if (fees.length) {
    html += '<button class="btn sm ghost" onclick="startEditSupplier(\'' + sid + '\')">编辑</button>';
  }
  html += '</span></div><div class="module-body">';
  if (fees.length || editing) {
    html += '<table class="mod-tbl" data-module="custom_fees"><thead><tr><th>名称</th><th>类型</th><th>金额/系数</th><th>条件(如 W>50)</th><th></th></tr></thead><tbody>';
    fees.forEach(function(f, i) {
      html += '<tr data-row="' + (f.id || i) + '">';
      if (editing) {
        html += '<td><input class="cell-input" data-k="name" value="' + escapeHtml(f.name || '') + '" style="width:110px"></td>';
        html += '<td><select class="cell-input" data-k="type" style="width:100px">' +
          '<option value="fixed"' + (f.type === 'fixed' ? ' selected' : '') + '>按件(固定)</option>' +
          '<option value="per_weight"' + (f.type === 'per_weight' ? ' selected' : '') + '>按重量</option>' +
          '<option value="per_shipment"' + (f.type === 'per_shipment' ? ' selected' : '') + '>每批次一次</option>' +
          '</select></td>';
        html += '<td><input class="cell-input" data-k="value" type="number" step="0.01" min="0" value="' + escapeNum(f.value) + '" style="width:70px"></td>';
        html += '<td><input class="cell-input" data-k="condition" value="' + escapeHtml(f.condition || '') + '" placeholder="空=总是" style="width:100px"></td>';
        html += '<td><button class="btn sm" style="color:#ef4444;padding:1px 5px" onclick="delCustomFeeRow(\'' + sid + '\',\'' + escAttr(f.id || i) + '\')">删除</button></td>';
      } else {
        var tlabel = {fixed: '按件', per_weight: '按重量', per_shipment: '每批次'}[f.type] || f.type;
        html += '<td>' + escapeHtml(f.name || '') + '</td>';
        html += '<td>' + tlabel + '</td>';
        html += '<td>$' + (f.value || 0).toFixed(2) + '</td>';
        html += '<td>' + (f.condition ? escapeHtml(f.condition) : '—') + '</td>';
        html += '<td><button class="btn sm" style="color:#ef4444;padding:1px 5px" onclick="delCustomFeeRow(\'' + sid + '\',\'' + escAttr(f.id || i) + '\')">删除</button></td>';
      }
      html += '</tr>';
    });
    if (editing) {
      html += '<tr><td colspan="5"><button class="btn sm" onclick="addCustomFeeRow(\'' + sid + '\')">+ 添加费用项</button></td></tr>';
    }
    html += '</tbody></table>';
  } else {
    html += '<div class="mod-empty">点击「编辑」添加自定义费用项（如打托费、偏远费等）</div>';
  }
  html += '</div></div>';
  return html;
}
function addCustomFeeRow() {
  var tbody = document.querySelector('[data-module="custom_fees"] tbody');
  if (!tbody) return;
  var tr = document.createElement("tr");
  tr.setAttribute("data-row", "new-" + Date.now());
  tr.innerHTML = '<td><input class="cell-input" data-k="name" value="新费用" style="width:110px"></td>' +
    '<td><select class="cell-input" data-k="type" style="width:100px">' +
    '<option value="fixed">按件(固定)</option>' +
    '<option value="per_weight">按重量</option>' +
    '<option value="per_shipment">每批次一次</option></select></td>' +
    '<td><input class="cell-input" data-k="value" type="number" step="0.01" min="0" value="0" style="width:70px"></td>' +
    '<td><input class="cell-input" data-k="condition" value="" placeholder="空=总是" style="width:100px"></td>' +
    '<td><button class="btn sm" style="color:#ef4444;padding:1px 5px" onclick="delCustomFeeRow(this)">删除</button></td>';
  tbody.appendChild(tr);
}
function delCustomFeeRow(elemOrSid, id) {
  if (typeof elemOrSid === "object") { elemOrSid.closest("tr").remove(); return; }
  var sid = elemOrSid;
  if (_editingSid === sid) {
    var tr = document.querySelector('[data-module="custom_fees"] tr[data-row="' + id + '"]');
    if (tr) tr.remove();
    return;
  }
  /* in non-edit mode, delete immediately could corrupt; keep via edit mode */
  if (_editingSid !== sid) { startEditSupplier(sid); return; }
}

function escapeNum(v) {
  if (v === undefined || v === null) return '';
  return String(v);
}
function escAttr(s) {
  return escapeHtml(String(s)).replace(/'/g, "\\'");
}

/* ── Edit state ────────────────────────────────────────────── */
function startEditSupplier(sid) {
  _editingSid = sid;
  renderSupplierCards();
}
function cancelEditSupplier() {
  _editingSid = null;
  renderSupplierCards();
}

/* ── Save (collect from DOM, PUT whole supplier) ───────────── */
async function saveSupplier(sid) {
  var sp = _suppliers[sid];
  if (!sp) return;
  var snap = JSON.parse(JSON.stringify(sp));
  var updated = {};

  /* name */
  var nameEl = $("#edit-supplier-name");
  if (nameEl) updated.name = nameEl.value.trim() || sp.name;

  /* outbound */
  var obRows = document.querySelectorAll('[data-module="outbound"] tbody tr[data-row]');
  var outbound = [];
  obRows.forEach(function(tr) {
    var min = parseFloat(tr.querySelector('[data-k="min"]').value);
    var max = parseFloat(tr.querySelector('[data-k="max"]').value);
    var price = parseFloat(tr.querySelector('[data-k="price"]').value);
    if (isNaN(min) || isNaN(price)) return;
    outbound.push({min_lbs: min, max_lbs: isNaN(max) ? 9999 : max, price: price});
  });
  updated.outbound = outbound;

  /* shipping */
  var shipTbl = document.querySelector('[data-module="shipping"]');
  var shipping_zones = {};
  if (shipTbl) {
    var zStr = shipTbl.getAttribute("data-szones") || "";
    var zList = zStr ? zStr.split(",") : [];
    zList.forEach(function(z) { shipping_zones[z] = {}; });
    var shipRows = shipTbl.querySelectorAll("tbody tr[data-row]");
    shipRows.forEach(function(tr) {
      var wEl = tr.querySelector('[data-k="weight"]');
      if (!wEl) return;
      var w = parseFloat(wEl.value);
      if (isNaN(w) || w <= 0) return;
      var wKey = String(w) === String(Math.round(w)) ? String(Math.round(w)) : String(round2(w));
      zList.forEach(function(z) {
        var valEl = tr.querySelector('[data-k="' + z + '|' + wEl.value + '"]') || tr.querySelector('[data-k="' + z + '|"]');
        if (!valEl) return;
        var pv = parseFloat(valEl.value);
        if (!isNaN(pv)) shipping_zones[z][wKey] = pv;
      });
    });
    Object.keys(shipping_zones).forEach(function(z) {
      Object.keys(shipping_zones[z]).forEach(function(w) {
        if (shipping_zones[z][w] === undefined) delete shipping_zones[z][w];
      });
    });
    updated.shipping_zones = shipping_zones;
  }

  /* fuel */
  var fuelEl = document.querySelector('[data-module="fuel"]');
  if (fuelEl) {
    var fv = parseFloat(fuelEl.value);
    updated.fuel_pct = isNaN(fv) ? 0 : fv;
  }

  /* residential & ahs */
  ["residential", "ahs_weight"].forEach(function(stype) {
    var tbl = document.querySelector('[data-module="' + stype + '"]');
    var out = {};
    if (tbl) {
      tbl.querySelectorAll("tbody tr[data-row]").forEach(function(tr) {
        var zoneEl = tr.querySelector('[data-k="zone"]');
        var priceEl = tr.querySelector('[data-k="price"]');
        var zone = zoneEl ? zoneEl.value.trim() : "";
        var pv = priceEl ? parseFloat(priceEl.value) : NaN;
        if (zone && !isNaN(pv)) out[normalizeZone(zone)] = pv;
      });
    }
    updated[stype] = out;
  });

  /* custom fees */
  var cfTbl = document.querySelector('[data-module="custom_fees"]');
  var customFees = [];
  if (cfTbl) {
    var cfIdx = 0;
    cfTbl.querySelectorAll("tbody tr[data-row]").forEach(function(tr) {
      var name = tr.querySelector('[data-k="name"]');
      var type = tr.querySelector('[data-k="type"]');
      var value = tr.querySelector('[data-k="value"]');
      var cond = tr.querySelector('[data-k="condition"]');
      if (!name || !value) return;
      if (!name.value.trim()) return;
      var pv = parseFloat(value.value);
      if (isNaN(pv)) return;
      customFees.push({
        id: tr.getAttribute("data-row") && tr.getAttribute("data-row").indexOf("new-") !== 0
            ? tr.getAttribute("data-row") : String(cfIdx++),
        name: name.value.trim(),
        type: type ? type.value : "fixed",
        value: pv,
        condition: cond ? cond.value.trim() : "",
      });
    });
  }
  updated.custom_fees = customFees;

  try {
    await api("/api/suppliers/" + sid, {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(updated),
    });
    _editingSid = null;
    await loadSuppliers();
  } catch (e) { alert("保存失败: " + e.message); }
}

function round2(n) { return Math.round(n * 100) / 100; }
function normalizeZone(s) {
  s = s.trim().replace(/\s+/g, "");
  var m = s.match(/^z(?:one)?(\d+)$/i);
  return m ? "Zone" + m.group(1) : s;
}

/* ── Row add/delete (editing state helpers) ────────────────── */
function addOutboundRow() {
  var tbody = document.querySelector('[data-module="outbound"] tbody');
  if (!tbody) return;
  var tr = document.createElement("tr");
  var rows = tbody.querySelectorAll("tr");
  var i = rows.length;
  tr.innerHTML = '<td><input class="cell-input" data-k="min" value="0" style="width:70px">–<input class="cell-input" data-k="max" value="9999" style="width:70px"></td>' +
    '<td><input class="cell-input" data-k="price" type="number" step="0.01" min="0" value="0" style="width:70px"></td>' +
    '<td><button class="btn sm" style="color:#ef4444;padding:1px 5px" onclick="delOutboundRow(this,\'\')">删除</button></td>';
  tbody.appendChild(tr);
}
function delOutboundRow(elemOrSid, idx) {
  if (typeof elemOrSid === "object") { elemOrSid.closest("tr").remove(); return; }
  if (_editingSid === elemOrSid) {
    var tbody = document.querySelector('[data-module="outbound"] tbody');
    if (tbody) { var tr = tbody.querySelector('tr[data-row="' + idx + '"]'); if (tr) tr.remove(); }
    return;
  }
  if (!confirm("确认删除这档出库费？")) return;
  api("/api/suppliers/" + elemOrSid + "/outbound/item/" + idx, { method: "DELETE" })
    .then(function(r) { if (r.ok) loadSuppliers(); else alert(r.error || "删除失败"); })
    .catch(function(e) { alert("删除失败: " + e.message); });
}

function addShippingRow(sid, zStr) {
  var tbody = document.querySelector('[data-module="shipping"] tbody');
  if (!tbody) return;
  var zList = zStr ? zStr.split(",") : [];
  var tr = document.createElement("tr");
  tr.setAttribute("data-row", "new");
  var html = '<td class="mm-weight"><input class="cell-input" data-k="weight" value="" style="width:55px"></td>';
  zList.forEach(function(z) {
    html += '<td><input class="cell-input" data-k="' + z + '|" type="number" step="0.01" min="0" value="" style="width:65px"></td>';
  });
  html += '<td><button class="btn sm" style="color:#ef4444;padding:1px 5px" onclick="delShippingRow(this)">删除</button></td>';
  tr.innerHTML = html;
  tbody.insertBefore(tr, tbody.querySelector("tr:last-child"));
}
function delShippingRow(elem, sid, w) {
  if (typeof elem === "object") { elem.closest("tr").remove(); return; }
  if (sid && _editingSid === sid) {
    var tr = document.querySelector('[data-module="shipping"] tr[data-row="' + w + '"]');
    if (tr) tr.remove();
    return;
  }
  if (!confirm("确认删除重量 " + w + " 这一行的所有Zone运费？")) return;
  api("/api/suppliers/" + sid + "/shipping/weight/" + encodeURIComponent(w), { method: "DELETE" })
    .then(function(r) { if (r.ok) loadSuppliers(); else alert(r.error || "删除失败"); })
    .catch(function(e) { alert("删除失败: " + e.message); });
}
function addShippingZones() {
  var zNum = prompt("要添加的Zone编号（数字）：");
  if (!zNum) return;
  var z = "Zone" + parseInt(zNum, 10);
  if (!/^Zone\d+$/.test(z)) return;
  var tbl = document.querySelector('[data-module="shipping"]');
  if (!tbl) return;
  var zStr = tbl.getAttribute("data-szones") || "";
  var zList = zStr ? zStr.split(",") : [];
  if (zList.indexOf(z) !== -1) { alert("该Zone已存在"); return; }
  zList.push(z);
  var sid = _editingSid;
  var sp = _suppliers[sid];
  if (!sp) { tbl.setAttribute("data-szones", zList.join(",")); return; }
  /* capture current values then re-render */
  var sz = {};
  zList.forEach(function(zn) { sz[zn] = {}; });
  var rows = tbl.querySelectorAll("tbody tr[data-row]");
  rows.forEach(function(tr) {
    var wEl = tr.querySelector('[data-k="weight"]');
    if (!wEl || !wEl.value) return;
    var w = parseFloat(wEl.value);
    if (isNaN(w) || w <= 0) return;
    var wKey = String(w) === String(Math.round(w)) ? String(Math.round(w)) : String(round2(w));
    zList.forEach(function(zn) {
      var cell = tr.querySelector('[data-k^="' + zn + '|"]');
      var v = cell && cell.value ? parseFloat(cell.value) : undefined;
      if (v !== undefined) sz[zn][wKey] = v;
    });
  });
  sp.shipping_zones = sz;
  renderSupplierCards();
}

function addSurchargeRow(sid, stype) {
  var tbody = document.querySelector('[data-module="' + stype + '"] tbody');
  if (!tbody) return;
  var tr = document.createElement("tr");
  tr.setAttribute("data-row", "new");
  tr.innerHTML = '<td><input class="cell-input" data-k="zone" value="Zone" style="width:80px"></td>' +
    '<td><input class="cell-input" data-k="price" type="number" step="0.01" min="0" value="0" style="width:70px"></td>' +
    '<td><button class="btn sm" style="color:#ef4444;padding:1px 5px" onclick="delSurchargeRow(this)">删除</button></td>';
  tbody.appendChild(tr);
}
function delSurchargeRow(elemOrSid, stype, key) {
  /* new-row delete in edit mode passes the DOM element */
  if (typeof elemOrSid === "object") { elemOrSid.closest("tr").remove(); return; }
  var sid = elemOrSid;
  /* in edit mode, just remove the rendered row; save happens on ✓ 保存全部 */
  if (_editingSid === sid) {
    var tr = document.querySelector('[data-module="' + stype + '"] tr[data-row="' + key + '"]');
    if (tr) tr.remove();
    return;
  }
  if (!confirm("确认删除该Zone？")) return;
  api("/api/suppliers/" + sid + "/surcharges/" + stype + "/" + encodeURIComponent(key), { method: "DELETE" })
    .then(function(r) { if (r.ok) loadSuppliers(); else alert(r.error || "删除失败"); })
    .catch(function(e) { alert("删除失败: " + e.message); });
}

/* ── Create / Delete ───────────────────────────────────────── */
async function createSupplier() {
  var name = prompt("供应商名称：");
  if (!name || !name.trim()) return;
  try {
    var res = await api("/api/suppliers", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name: name.trim()}),
    });
    if (res.ok) await loadSuppliers();
    else alert(res.error || "创建失败");
  } catch (e) { alert("创建失败: " + e.message); }
}

async function deleteSupplier(sid) {
  var sp = _suppliers[sid];
  if (!confirm("确认删除「" + (sp ? sp.name : sid) + "」？")) return;
  try {
    await api("/api/suppliers/" + sid, { method: "DELETE" });
    await loadSuppliers();
  } catch (e) { alert("删除失败: " + e.message); }
}

/* ── Bulk edit (multi-select suppliers, apply same change) ── */
function toggleBulkSelect(sid, checked) {
  if (checked) _bulkSelected.add(sid);
  else _bulkSelected.delete(sid);
  var n = _bulkSelected.size;
  var el = $("supplierMsg");
  if (el) el.textContent = n ? ("已选 " + n + " 家供应商") : "";
}
function openBulkEdit() {
  if (!_bulkSelected.size) {
    alert("请先在供应商卡片勾选要批量编辑的供应商");
    return;
  }
  var zoneSel = $("bulkZone");
  var zones = ["Zone2","Zone3","Zone4","Zone5","Zone6","Zone7","Zone8"];
  zoneSel.innerHTML = zones.map(function(z) {
    return '<option value="' + z + '">' + z.replace("Zone","Zone ") + '</option>';
  }).join('');
  bulkTargetChange();
  $("bulkStatus").textContent = "将从 " + _bulkSelected.size + " 家选中供应商中匹配修改：";
  $("bulkModal").style.display = "flex";
}
function closeBulkEdit() {
  $("bulkModal").style.display = "none";
}
function bulkTargetChange() {
  var t = $("bulkTarget").value;
  var zoneWrap = $("bulkMatchRow");
  var minWrap = $("bulkMinWrap");
  var rule = $("bulkRuleText");
  $("bulkZone").style.display = "";
  minWrap.style.display = "";
  if (t === "fuel") {
    $("bulkZone").style.display = "none";
    minWrap.style.display = "none";
    $("bulkMatchLabel").textContent = "Zone";
    rule.textContent = "对所有选中供应商统一修改燃油附加费百分比。";
  } else if (t === "outbound") {
    $("bulkZone").style.display = "none";
    $("bulkMatchLabel").textContent = "重量段";
    rule.textContent = "匹配相同重量段(lbs)的选中供应商，对其单价应用修改。仅改价格，不新增/删除档位。";
  } else {
    $("bulkMatchLabel").textContent = "Zone";
    if (t === "shipping") {
      minWrap.style.display = "none";
      rule.textContent = "对该 Zone 的选中供应商所有重量段价格应用修改。";
    } else {
      minWrap.style.display = "none";
      rule.textContent = "对该 Zone 的选中供应商该费用项应用修改。";
    }
  }
}
async function applyBulkEdit() {
  var target = $("bulkTarget").value;
  var op = $("bulkOp").value;
  var value = parseFloat($("bulkValue").value);
  if (isNaN(value)) { alert("请输入有效的数值"); return; }
  var spec = { ids: Array.from(_bulkSelected), target: target, op: op, value: value };
  if (target === "outbound") {
    var p = $("bulkMin").value;
    if (!p) { alert("请填写重量段最小磅(lbs)"); return; }
    spec.min_lbs = parseFloat(p);
    spec.max_lbs = parseFloat(p);
  } else if (target !== "fuel") {
    spec.zone = $("bulkZone").value;
  }
  try {
    var res = await api("/api/suppliers/bulk-edit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(spec),
    });
    if (!res.ok) { alert(res.error || "批量编辑失败"); return; }
    _bulkSelected.clear();
    if ($("supplierMsg")) $("supplierMsg").textContent = "";
    $("bulkModal").style.display = "none";
    alert("已修改 " + res.updated + " 家供应商");
    await loadSuppliers();
  } catch (e) { alert("批量编辑失败: " + e.message); }
}

/* ── Paste functions ───────────────────────────────────────── */
function openPasteModal(sid, type, title, hint, initial) {
  _pasteState = {sid: sid, type: type};
  var modal = $("pasteModal");
  $("pasteTitle").textContent = title;
  $("pasteHint").innerHTML = hint;
  $("pasteInput").value = initial || "";
  $("pastePreview").innerHTML = '';
  modal.style.display = "flex";
  $("pasteInput").focus();
}

function pasteOutbound(sid) {
  var sp = _suppliers[sid];
  openPasteModal(sid, "outbound",
    "粘贴导入出库费 — " + sp.name,
    '格式：Tab或逗号分隔，每行 <b>重量段</b> <b>价格</b><br>' +
    '示例：<code>0-4.4	0.80</code>　<code>0 lbs&lt;W≤1 lbs	0.4</code>　<code>150.01+	3.00</code>',
    '');
}
function pasteShipping(sid) {
  var sp = _suppliers[sid];
  var iv = sp.carrier ? '# carrier ' + sp.carrier + '\n' : '';
  openPasteModal(sid, "shipping",
    "粘贴导入运费 — " + sp.name,
    '首行表头：<code>计费重量(lbs)	Zone2	Zone3…</code><br>数据行：<code>1	34.00	22.00…</code><br>可选承运商行：<code># carrier FedEx</code>',
    iv);
}
function pasteFuel(sid) {
  var sp = _suppliers[sid];
  openPasteModal(sid, "fuel",
    "录入燃油附加费 — " + sp.name,
    '直接输入燃油费率百分比，如 <code>16</code> 或 <code>16%</code> 或 <code>0.16</code>',
    sp.fuel_pct > 0 ? sp.fuel_pct + '%' : '');
}
function pasteSurcharges(sid, stype) {
  var sp = _suppliers[sid];
  var label = stype === "ahs_weight" ? "AHS超重费" : "住宅地址费";
  var existing = sp[stype] || {};
  var iv = Object.keys(existing).sort().map(function(z) {
    return z + '\t' + existing[z].toFixed(2);
  }).join('\n');
  openPasteModal(sid, "surcharges_" + stype,
    "粘贴导入" + label + " — " + sp.name,
    '格式：每行 <b>Zone</b> <b>价格</b><br>示例：<code>Zone2	2.70</code>　<code>Zone3	2.70</code>',
    iv);
}

function closePasteModal() {
  $("pasteModal").style.display = "none";
  _pasteState = null;
}

async function applyPaste() {
  if (!_pasteState) return;
  var text = $("pasteInput").value;
  var sid = _pasteState.sid;
  var type = _pasteState.type;

  try {
    var res;
    if (type === "outbound") {
      res = await api("/api/suppliers/" + sid + "/outbound/paste", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({text: text}),
      });
      if (res.ok) { var sp = $("supplierMsg"); if (sp) sp.textContent = "已导入 " + res.count + " 个重量段"; }
    } else if (type === "shipping") {
      res = await api("/api/suppliers/" + sid + "/shipping/paste", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({text: text}),
      });
      if (res.ok) { var sp = $("supplierMsg"); if (sp) sp.textContent = "已导入 " + res.zones + " 个Zone, " + res.weights + " 个重量段"; }
    } else if (type === "fuel") {
      res = await api("/api/suppliers/" + sid + "/fuel/paste", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({text: text}),
      });
      if (res.ok) { var sp = $("supplierMsg"); if (sp) sp.textContent = "燃油费率已设为 " + res.fuel_pct + "%"; }
    } else if (type.startsWith("surcharges_")) {
      var stype = type.replace("surcharges_", "");
      res = await api("/api/suppliers/" + sid + "/surcharges/paste", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({text: text, type: stype}),
      });
      if (res.ok) { var sp = $("supplierMsg"); if (sp) sp.textContent = "已导入 " + res.count + " 个Zone"; }
    }
    if (res && res.ok) {
      closePasteModal();
      await loadSuppliers();
    } else {
      alert((res && res.error) || "导入失败");
    }
  } catch (e) {
    alert("导入失败: " + e.message);
  }
}

/* ── Batch Compare ──────────────────────────────────────────── */
function addBatchRow(weight, qty) {
  var tbody = $("batchBody");
  if (!tbody) return;
  var tr = document.createElement("tr");
  tr.innerHTML = '<td><input type="number" class="ax-input batch-w" value="' + (weight || 5) + '" min="0" step="0.1" style="width:70px"></td>' +
    '<td><input type="number" class="ax-input batch-q" value="' + (qty || 1) + '" min="1" step="1" style="width:60px"></td>' +
    '<td><button class="btn sm" style="color:#ef4444;padding:2px 6px" onclick="this.closest(\'tr\').remove()">×</button></td>';
  tbody.appendChild(tr);
}

async function runBatchCompare() {
  var esc = escapeHtml;
  var zoneSel = $("pricingZone");
  var fuelInput = $("pricingFuel");
  var overviewArea = $("pricingOverview");
  var detailArea = $("pricingDetailMatrix");
  if (!zoneSel) return;
  var zone = zoneSel.value;
  var fuelVal = fuelInput ? parseFloat(fuelInput.value) : NaN;

  var rows = document.querySelectorAll("#batchBody tr");
  var shipments = [];
  rows.forEach(function(tr) {
    var w = parseFloat(tr.querySelector(".batch-w").value) || 1;
    var q = parseInt(tr.querySelector(".batch-q").value) || 1;
    shipments.push({weight: w, qty: q});
  });
  if (!shipments.length) { alert("请至少添加一行"); return; }

  if (overviewArea) overviewArea.innerHTML = '<div class="sc-loading">计算中…</div>';
  if (detailArea) detailArea.innerHTML = '';

  try {
    var body = {shipments: shipments, zone: zone};
    if (!isNaN(fuelVal) && fuelVal > 0) body.fuel_pct = fuelVal;
    var res = await fetch("/api/pricing/calculate_v4", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    var data = await res.json();
    _lastBatchResult = data;
    _priceOrder = null;
    renderOverview(data, zone);
    renderDetailMatrix(data, zone);
  } catch (e) {
    if (overviewArea) overviewArea.innerHTML = '<div class="sc-empty">比价失败: ' + esc(e.message) + '</div>';
  }
}

function renderOverview(data, selectedZone) {
  var esc = escapeHtml;
  var area = $("pricingOverview");
  if (!area || !data.overview || !data.overview.length) return;

  var suppliers = _orderedSuppliers(data.overview[0].suppliers || []);
  var html = '<div class="sc-section-title">全分区总览</div>';
  html += '<div class="matrix-wrap"><table class="fee-matrix overview-matrix"><thead><tr><th>Zone</th>';
  suppliers.forEach(function(s) {
    html += '<th>' + esc(s.name);
    if (s.__best) html += ' <span class="best-badge">最省</span>';
    html += '</th>';
  });
  html += '</tr></thead><tbody>';

  data.overview.forEach(function(row) {
    var isSelected = row.zone === selectedZone;
    html += '<tr class="' + (isSelected ? 'pr-sel' : '') + '" style="cursor:pointer" onclick="selectZone(\'' + row.zone + '\')">';
    html += '<td class="fm-label">' + esc(row.zone.replace("Zone","Zone ")) + (isSelected ? ' ★' : '') + '</td>';
    var srow = _orderedSuppliers(row.suppliers || []);
    var totals = srow.map(function(s) { return s.total; });
    var minTotal = Math.min.apply(null, totals.filter(function(t) { return t > 0; }));
    srow.forEach(function(s) {
      var isBest = s.total === minTotal && s.total > 0;
      html += '<td class="fm-val' + (isBest ? ' fm-best' : '') + '">' + (s.total > 0 ? '$' + s.total.toFixed(2) : '—') + '</td>';
    });
    html += '</tr>';
  });

  if (data.grand_totals && data.grand_totals.length) {
    html += '<tr class="pr-total-row"><td class="fm-label"><b>总计</b></td>';
    var gt = _orderedSuppliers(data.grand_totals);
    var gtTotals = gt.map(function(g) { return g.total; });
    var gtMin = Math.min.apply(null, gtTotals.filter(function(t) { return t > 0; }));
    gt.forEach(function(g) {
      var isBest = g.total === gtMin && g.total > 0;
      html += '<td class="fm-val' + (isBest ? ' fm-best' : '') + '"><b>' + (g.total > 0 ? '$' + g.total.toFixed(2) : '—') + '</b>';
      if (isBest && gtMin > 0 && gtTotals.length > 1) {
        var second = gtTotals.slice().filter(function(t) { return t > gtMin; }).sort(function(a,b){return a-b;})[0];
        if (second) html += '<span class="save-badge">省$' + (second - gtMin).toFixed(2) + '</span>';
      }
      html += '</b></td>';
    });
    html += '</tr>';
  }

  html += '</tbody></table></div>';
  area.innerHTML = html;
}

/* Reorder an array of {rid/name,...} per _priceOrder; mark __best on the cheapest grand total */
function _orderedSuppliers(arr) {
  var out = arr.slice();
  if (_priceOrder && _priceOrder.length) {
    var map = {};
    out.forEach(function(o) { map[o.rid || o.id] = o; });
    var ordered = [];
    _priceOrder.forEach(function(rid) { if (map[rid] !== undefined) ordered.push(map[rid]); });
    if (ordered.length) out = ordered;
  }
  /* mark cheapest grand total as __best */
  var withTotal = out.filter(function(o) { return typeof o.total === "number"; });
  if (withTotal.length) {
    var mins = withTotal.filter(function(o){return o.total>0;}).map(function(o){return o.total;});
    if (mins.length) {
      var m = Math.min.apply(null, mins);
      out.forEach(function(o) { o.__best = (typeof o.total === "number" && o.total === m && o.total > 0); });
    }
  }
  return out;
}

function reorderByCost() {
  if (!_lastBatchResult) return;
  var mode = "asc";
  var sel = $("priceSortMode");
  var doReorder = !sel;
  if (sel) {
    mode = sel.value;
    /* first click after run = apply asc; toggle on subsequent */
  }
  var gts = (_lastBatchResult.grand_totals || []).slice();
  if (mode === "orig") { _priceOrder = null; }
  else {
    var filtered = gts.filter(function(g) { return g.total > 0; });
    var sorted = filtered.slice().sort(function(a, b) {
      return mode === "desc" ? b.total - a.total : a.total - b.total;
    });
    _priceOrder = sorted.map(function(g) { return g.rid; });
  }
  var zone = $("pricingZone").value;
  renderOverview(_lastBatchResult, zone);
  renderDetailMatrix(_lastBatchResult, zone);
}

function selectZone(zone) {
  var sel = $("pricingZone");
  if (sel) sel.value = zone;
  if (_lastBatchResult) {
    renderOverview(_lastBatchResult, zone);
    renderDetailMatrix(_lastBatchResult, zone);
  }
}

function renderDetailMatrix(data, zone) {
  var esc = escapeHtml;
  var area = $("pricingDetailMatrix");
  if (!area || !data.details || !data.details.length) return;

  var suppliers = _orderedSuppliers(data.details[0].suppliers || []);
  var feeRows = [
    {key: "outbound", label: "出库操作费"},
    {key: "shipping", label: "基础运费"},
    {key: "carrier", label: "承运商", isText: true},
    {key: "residential", label: "住宅地址费"},
    {key: "ahs_weight", label: "AHS超重"},
    {key: "ahs_other", label: "AHS超尺寸/包装"},
    {key: "das", label: "DAS偏远"},
    {key: "custom_total", label: "自定义费用"},
    {key: "fuel_amount", label: "燃油附加费"},
    {key: "fuel_pct", label: "燃油费率", isPct: true},
  ];

  var html = '<div class="sc-section-title">' + esc(zone.replace("Zone","Zone ")) + ' 费用明细</div>';

  data.details.forEach(function(det) {
    var srow = _orderedSuppliers(det.suppliers || []);
    var unitMin = Math.min.apply(null, srow.filter(function(s){return s.unit_total>0;}).map(function(s){return s.unit_total;}));
    html += '<div class="dm-group">';
    html += '<div class="dm-weight-header">▸ ' + det.weight + ' lbs × ' + det.qty + ' 件</div>';
    html += '<div class="matrix-wrap"><table class="fee-matrix detail-matrix"><thead><tr><th>费用项目</th>';
    srow.forEach(function(s) { html += '<th>' + esc(s.name) + (s.unit_total === unitMin && s.unit_total > 0 ? ' <span class="best-badge">最省</span>' : '') + '</th>'; });
    html += '</tr></thead><tbody>';

    var unitTotals = srow.map(function(s) { return s.unit_total; });
    var minUnit = Math.min.apply(null, unitTotals.filter(function(t) { return t > 0; }));

    feeRows.forEach(function(fr) {
      html += '<tr><td class="fm-label">' + fr.label + '</td>';
      srow.forEach(function(s) {
        var val = s[fr.key];
        var cell = '—';
        if (fr.isText) {
          cell = val ? esc(val) : '—';
        } else if (fr.isPct) {
          cell = val > 0 ? val.toFixed(1) + '%' : '—';
        } else if (val && val > 0) {
          cell = '$' + val.toFixed(2);
        }
        html += '<td class="fm-val">' + cell + '</td>';
      });
      html += '</tr>';
    });

    /* custom fees sub-detail */
    html += '<tr><td class="fm-label" style="color:#888;font-size:11px">自定义费明细</td>';
    srow.forEach(function(s) {
      var items = (s.custom_fees || []).filter(function(it){ return it && it.per_unit > 0; });
      html += '<td class="fm-val" style="font-size:11px">' + (items.length
        ? items.map(function(it){ return esc(it.name) + ' $' + it.per_unit.toFixed(2); }).join('<br>')
        : '—') + '</td>';
    });
    html += '</tr>';

    html += '<tr class="fm-total-row"><td class="fm-label"><b>单件总计</b></td>';
    srow.forEach(function(s) {
      var isBest = s.unit_total === minUnit && s.unit_total > 0;
      html += '<td class="fm-val' + (isBest ? ' fm-best' : '') + '"><b>$' + s.unit_total.toFixed(2) + '</b>';
      if (isBest && minUnit > 0 && unitTotals.length > 1) {
        var second = unitTotals.slice().filter(function(t){return t>minUnit;}).sort(function(a,b){return a-b;})[0];
        if (second) html += '<span class="save-badge">省$' + (second - minUnit).toFixed(2) + '</span>';
      }
      html += '</b></td>';
    });
    html += '</tr>';

    html += '<tr><td class="fm-label">×' + det.qty + '件 小计</td>';
    srow.forEach(function(s) {
      html += '<td class="fm-val"><b>$' + s.line_total.toFixed(2) + '</b></td>';
    });
    html += '</tr>';

    html += '</tbody></table></div></div>';
  });

  if (data.grand_totals && data.grand_totals.length) {
    var gts = _orderedSuppliers(data.grand_totals);
    html += '<div class="dm-group">';
    html += '<div class="dm-weight-header">▸ 所有批次总计</div>';
    html += '<div class="matrix-wrap"><table class="fee-matrix detail-matrix"><thead><tr><th>供应商</th><th>总费用</th></tr></thead><tbody>';
    var gtTotals = gts.map(function(g) { return g.total; });
    var gtMin = Math.min.apply(null, gtTotals.filter(function(t) { return t > 0; }));
    gts.forEach(function(g) {
      var isBest = g.total === gtMin && g.total > 0;
      html += '<tr><td class="fm-label">' + esc(g.name) + '</td>';
      html += '<td class="fm-val' + (isBest ? ' fm-best' : '') + '"><b>$' + g.total.toFixed(2) + '</b>';
      if (isBest && gtMin > 0 && gtTotals.length > 1) {
        var second = gtTotals.slice().filter(function(t){return t>gtMin;}).sort(function(a,b){return a-b;})[0];
        if (second) html += '<span class="save-badge">省$' + (second - gtMin).toFixed(2) + '</span>';
      }
      html += '</td></tr>';
    });
    html += '</tbody></table></div></div>';
  }

  area.innerHTML = html;
}

/* ── Export (CSV / Excel) for batch compare ───────────────── */
function exportCompareCSV() {
  if (!_lastBatchResult) { alert("请先生成比价表"); return; }
  var rows = _buildExportRows();
  var csv = rows.map(function(r) {
    return r.map(function(c) { return '"' + String(c == null ? "" : c).replace(/"/g, '""') + '"'; }).join(",");
  }).join("\r\n");
  _downloadCSV("\ufeff" + csv, "报价比价.csv");
}

function exportCompareExcel() {
  if (!_lastBatchResult) { alert("请先生成比价表"); return; }
  var csv = _buildExportRows().map(function(r) {
    return r.map(function(c) { return '"' + String(c == null ? "" : c).replace(/"/g, '""') + '"'; }).join(",");
  }).join("\r\n");
  _downloadCSV("\ufeff" + csv, "报价比价.xls");
}

function _buildExportRows() {
  var data = _lastBatchResult;
  var rows = [];
  var zone = "Zone" + ($("pricingZone").value || "5");
  /* overview by zone */
  rows.push(["全分区总览", "", ""]);
  var zrows = [["Zone"]];
  (data.overview[0].suppliers || []).forEach(function(s) { zrows[0].push(s.name); });
  rows.push(zrows[0]);
  data.overview.forEach(function(row) {
    var r = [row.zone.replace("Zone","Zone ")];
    row.suppliers.forEach(function(s) { r.push(s.total > 0 ? s.total.toFixed(2) : "-"); });
    rows.push(r);
  });
  rows.push([]);
  /* grand totals */
  var gt = [["供应商", "总费用($)"]];
  (data.grand_totals || []).forEach(function(g) { gt.push([g.name, g.total.toFixed(2)]); });
  rows = rows.concat(gt);
  rows.push([]);
  /* detail per shipment */
  (data.details || []).forEach(function(det) {
    rows.push(["", ""]);
    rows.push([det.weight + " lbs × " + det.qty + " 件", "", ""]);
    var head = ["费用项目"];
    det.suppliers.forEach(function(s) { head.push(s.name); });
    rows.push(head);
    var feeRows = [
      {key:"outbound",label:"出库操作费"},{key:"shipping",label:"基础运费"},
      {key:"residential",label:"住宅地址费"},{key:"ahs_weight",label:"AHS超重"},
      {key:"ahs_other",label:"AHS超尺寸/包装"},{key:"das",label:"DAS偏远"},
      {key:"fuel_amount",label:"燃油附加费"},
    ];
    feeRows.forEach(function(fr) {
      var r = [fr.label];
      det.suppliers.forEach(function(s) { r.push(s[fr.key] > 0 ? s[fr.key].toFixed(2) : "-"); });
      rows.push(r);
    });
    var cfr = ["自定义费明细"];
    det.suppliers.forEach(function(s) {
      cfr.push((s.custom_fees || []).filter(function(it){return it && it.per_unit>0;}).map(function(it){
        return it.name + " $" + it.per_unit.toFixed(2);
      }).join("; ") || "-");
    });
    rows.push(cfr);
    var t = ["单件总计"];
    det.suppliers.forEach(function(s) { t.push(s.unit_total.toFixed(2)); });
    rows.push(t);
    var lt = ["小计("+det.qty+"件)"];
    det.suppliers.forEach(function(s) { lt.push(s.line_total.toFixed(2)); });
    rows.push(lt);
  });
  return rows;
}

function _downloadCSV(content, filename) {
  var blob = new Blob([content], {type: "text/csv;charset=utf-8;"});
  var link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
