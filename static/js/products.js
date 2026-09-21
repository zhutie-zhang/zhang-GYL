/* 产品管理模块：组合产品 / 非组合产品的添加、导入、列表、删除、导出 */

const _prodColDefs = [
  { key: "type", label: "类型" },
  { key: "sku", label: "产品SKU" },
  { key: "name", label: "名称" },
  { key: "components", label: "子SKU" },
  { key: "action", label: "操作" },
];
const _prodColKey = "product_table";

function showProducts() {
  state.view = "products";
  renderTabs();
  setPanelVisible("productPanel");
  loadProducts();
}

function showProductMsg(msg, isErr) {
  const el = $("productMsg");
  el.textContent = msg || "";
  el.className = isErr ? "hint err-text" : "hint ok-text";
}

function syncProductTypeUI() {
  const isStandalone = $("productType").value === "standalone";
  $("productCompsLabel").style.display = isStandalone ? "none" : "";
  $("productComps").required = !isStandalone;
}

async function loadProducts() {
  try {
    const res = await api("/api/products");
    state.products = res.products || [];
  } catch (e) {
    showProductMsg("⚠ 加载失败：" + e.message, true);
    state.products = [];
  }
  renderProducts();
}

function currentProductFilter() {
  return {
    field: $("productSearchField").value,
    mode: $("productSearchMode").value,
    type: $("productSearchType").value,
    term: $("productSearch").value.trim(),
  };
}

function matchProduct(p, f) {
  if (f.type === "combo" && p.type === "standalone") return false;
  if (f.type === "standalone" && p.type !== "standalone") return false;
  const term = f.term;
  if (!term) return true;
  const has = (v) => (f.mode === "exact" ? String(v ?? "") === term : fuzzyMatch(v, term));
  if (f.field === "sku") return has(p.sku);
  if (f.field === "name") return has(p.name || "");
  if (f.field === "comp") {
    const comps = p.components || [];
    return f.mode === "exact" ? comps.some((c) => String(c) === term) : fuzzySome(comps, term);
  }
  if (has(p.sku) || has(p.name || "")) return true;
  const comps = p.components || [];
  return f.mode === "exact" ? comps.some((c) => String(c) === term) : fuzzySome(comps, term);
}

function renderProducts() {
  const tbody = document.querySelector("#productTable tbody");
  const count = $("productCount");
  const all = state.products || [];
  const f = currentProductFilter();
  const hasFilter = f.term !== "" || f.type !== "all";
  const list = hasFilter ? all.filter((p) => matchProduct(p, f)) : all;
  state.productsShown = list;
  const nCombo = list.filter((p) => p.type !== "standalone").length;
  const nStand = list.length - nCombo;
  count.textContent = hasFilter
    ? `匹配 ${list.length} 个（组合 ${nCombo} / 非组合 ${nStand}），全部 ${all.length} 个`
    : `共 ${list.length} 个产品（组合 ${nCombo} / 非组合 ${nStand}）`;
  const vis = getColOrder(_prodColKey, _prodColDefs.map((c) => c.key));
  const hidden = new Set(_prodColDefs.map((c) => c.key).filter((k) => !vis.includes(k)));
  const shown = _prodColDefs.filter((c) => !hidden.has(c.key));
  const head = $("productHead");
  const colCount = shown.length;
  head.innerHTML = "<tr>" + shown.map((c) => `<th>${escapeHtml(c.label)}</th>`).join("") + "</tr>";
  tbody.innerHTML = "";
  if (!list.length) {
    tbody.innerHTML = all.length
      ? `<tr><td colspan="${colCount}" class="state-cell">未找到匹配的产品，请调整搜索条件</td></tr>`
      : `<tr><td colspan="${colCount}" class="state-cell">暂无产品，请在上方添加或导入 Excel</td></tr>`;
    return;
  }
  const esc = escapeHtml;
  for (const p of list) {
    const isCombo = p.type !== "standalone";
    const tr = document.createElement("tr");
    tr.className = "clickable";
    tr.title = "点击跳转组合统计查看该产品的明细";
    tr.addEventListener("click", () => {
      openStats("inv", "all", isCombo ? "kit" : "standalone", p.sku);
    });
    for (const c of shown) {
      const td = document.createElement("td");
      if (c.key === "type") {
        const badge = document.createElement("span");
        badge.className = isCombo ? "badge badge-combo" : "badge badge-standalone";
        badge.textContent = isCombo ? "组合" : "非组合";
        td.appendChild(badge);
      } else if (c.key === "sku") {
        td.className = "sku-cell";
        td.textContent = p.sku;
      } else if (c.key === "name") {
        td.textContent = p.name || "—";
        td.title = p.name || "";
      } else if (c.key === "components") {
        td.textContent = isCombo ? (p.components || []).join("、") : "—";
        td.title = td.textContent;
      } else if (c.key === "action") {
        const del = document.createElement("button");
        del.className = "btn ghost";
        del.textContent = "删除";
        del.addEventListener("click", async (e) => {
          e.stopPropagation();
          if (!confirm(`删除产品 ${p.sku}？`)) return;
          try {
            await api("/api/products/" + encodeURIComponent(p.sku), { method: "DELETE" });
            showProductMsg("已删除 " + p.sku);
          } catch (err) {
            showProductMsg("⚠ 删除失败：" + err.message, true);
          }
          loadProducts();
        });
        td.appendChild(del);
      }
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
}

async function submitProduct() {
  const ptype = $("productType").value;
  const sku = $("productSku").value.trim();
  const name = $("productName").value.trim();
  const comps = $("productComps").value.split(/[,，;；\s]+/).map((s) => s.trim()).filter(Boolean);
  if (!sku) return showProductMsg("⚠ 请输入产品SKU", true);
  if (ptype !== "standalone" && !comps.length) return showProductMsg("⚠ 组合产品请输入子SKU（逗号分隔）", true);
  try {
    await api("/api/products", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sku, name, components: comps, type: ptype }),
    });
    $("productSku").value = "";
    $("productName").value = "";
    $("productComps").value = "";
    showProductMsg("✓ 已保存 " + sku);
  } catch (e) {
    showProductMsg("⚠ 保存失败：" + e.message, true);
  }
  loadProducts();
}

async function importProductFile() {
  const file = $("productFile").files[0];
  if (!file) return showProductMsg("⚠ 请先选择组合产品 Excel/CSV 文件", true);
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res = await api("/api/products/import", { method: "POST", body: fd });
    const skipMsg = res.skipped > 0 ? `，跳过已存在 ${res.skipped} 个` : "";
    showProductMsg("✓ 导入成功，新增 " + res.count + " 个组合产品" + skipMsg);
  } catch (e) {
    showProductMsg("⚠ 导入失败：" + e.message, true);
  }
  loadProducts();
}

async function importStandaloneFile() {
  const file = $("productStandaloneFile").files[0];
  if (!file) return showProductMsg("⚠ 请先选择非组合产品 Excel/CSV 文件", true);
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res = await api("/api/products/import-standalone", { method: "POST", body: fd });
    const skipMsg = res.skipped > 0 ? `，跳过已存在 ${res.skipped} 个` : "";
    showProductMsg("✓ 导入成功，新增 " + res.count + " 个非组合产品" + skipMsg);
  } catch (e) {
    showProductMsg("⚠ 导入失败：" + e.message, true);
  }
  loadProducts();
}

function exportProducts() {
  const list = state.productsShown || state.products || [];
  if (!list.length) {
    showProductMsg("暂无产品可导出");
    return;
  }
  const esc = (v) => {
    v = String(v ?? "");
    return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
  };
  const lines = [["类型", "产品SKU", "名称", "子SKU"]];
  for (const p of list) {
    const isCombo = p.type !== "standalone";
    lines.push([isCombo ? "组合" : "非组合", p.sku, p.name, (p.components || []).join(",")]);
  }
  downloadCsv(`产品管理_${new Date().toISOString().slice(0, 10)}.csv`,
    lines.map((r) => r.map(esc).join(",")).join("\r\n"));
}

function applyProductSearch() {
  renderProducts();
}

function clearProductSearch() {
  $("productSearch").value = "";
  $("productSearchField").value = "all";
  $("productSearchMode").value = "fuzzy";
  $("productSearchType").value = "all";
  renderProducts();
}

function initProducts() {
  $("productType").addEventListener("change", syncProductTypeUI);
  $("productAddBtn").addEventListener("click", submitProduct);
  $("productImportBtn").addEventListener("click", importProductFile);
  $("productImportStandaloneBtn").addEventListener("click", importStandaloneFile);
  $("productExport").addEventListener("click", exportProducts);
  $("productSearchBtn").addEventListener("click", applyProductSearch);
  $("productSearchClear").addEventListener("click", clearProductSearch);
  $("productSearch").addEventListener("input", applyProductSearch);
  $("productSearch").addEventListener("keydown", (e) => {
    if (e.key === "Enter") applyProductSearch();
  });
  $("productSearchField").addEventListener("change", applyProductSearch);
  $("productSearchMode").addEventListener("change", applyProductSearch);
  $("productSearchType").addEventListener("change", applyProductSearch);
  $("productColSettings").addEventListener("click", () => {
    showColSettings(_prodColKey, _prodColDefs, renderProducts);
  });
  syncProductTypeUI();
}
