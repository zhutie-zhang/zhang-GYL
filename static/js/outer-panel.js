/* 外层仓报价 · 仓储CBM · 服务端账单核对 —— 单页面板（注入 price-checker.html） */
(function () {
    "use strict";
    if (window.__outerPanelInited) return;
    window.__outerPanelInited = true;

    var PANEL_ID = "op_panel", BTN_ID = "op_btn";
    var CHANNELS = [], STORAGE = {}, TEMPLATES = [];

    function esc(s) {
        return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
        });
    }
    function api(path, opts) {
        return fetch(path, {
            method: opts ? "POST" : "GET",
            headers: { "Content-Type": "application/json" },
            body: opts ? JSON.stringify(opts) : undefined
        }).then(function (r) { return r.json().catch(function () { return { error: "响应非 JSON" }; }); });
    }

    /* ── 面板骨架 ────────────────────────────────── */
    function ensurePanel() {
        var p = document.getElementById(PANEL_ID);
        if (p) return p;
        p = document.createElement("div");
        p.id = PANEL_ID;
        p.style.cssText = "position:fixed;inset:0;z-index:2147483000;background:rgba(15,23,42,.55);display:none;"
            + "align-items:flex-start;justify-content:center;overflow:auto;padding:24px;";
        p.innerHTML =
            '<div style="background:#fff;border-radius:12px;max-width:1180px;width:96%;box-shadow:0 10px 40px rgba(0,0,0,.3);overflow:hidden">'
            + '<div style="display:flex;justify-content:space-between;align-items:center;background:#1f2937;color:#fff;padding:12px 18px">'
            + '<div><b style="font-size:15px">外层仓报价 · 仓储CBM · 服务端账单核对</b>'
            + '<div style="font-size:11px;opacity:.75;margin-top:2px">统一价卡(service) ｜ 仓储8家(service) ｜ 核对引擎(service) ｜ 1% 容差</div></div>'
            + '<button id="op_close" style="background:none;border:none;color:#fff;font-size:20px;cursor:pointer">×</button></div>'
            + '<div style="display:flex;gap:0;border-bottom:1px solid #e5e7eb;padding:0 12px;background:#f9fafb">'
            + '<button data-tab="st" class="op_tab op_on" style="flex:1;border:none;background:none;padding:10px;cursor:pointer;font-weight:600;border-bottom:3px solid #2563eb">① 仓储CBM阶梯</button>'
            + '<button data-tab="cost" class="op_tab" style="flex:1;border:none;background:none;padding:10px;cursor:pointer;color:#6b7280">② 仓储费速算</button>'
            + '<button data-tab="bc" class="op_tab" style="flex:1;border:none;background:none;padding:10px;cursor:pointer;color:#6b7280">③ 服务端账单核对</button>'
            + '<button data-tab="ch" class="op_tab" style="flex:1;border:none;background:none;padding:10px;cursor:pointer;color:#6b7280">④ 外层仓渠道</button>'
            + '</div><div id="op_body" style="padding:16px 18px;max-height:70vh;overflow:auto"></div></div>';
        document.body.appendChild(p);
        document.getElementById("op_close").addEventListener("click", function () { p.style.display = "none"; });
        p.addEventListener("click", function (e) { if (e.target === p) p.style.display = "none"; });
        var tabs = p.querySelectorAll(".op_tab");
        for (var i = 0; i < tabs.length; i++) {
            tabs[i].addEventListener("click", function () { switchTab(this.getAttribute("data-tab")); });
        }
        renderStatus();
        return p;
    }
    function switchTab(t) {
        var p = document.getElementById(PANEL_ID);
        if (!p) return;
        var tabs = p.querySelectorAll(".op_tab");
        for (var i = 0; i < tabs.length; i++) {
            var on = tabs[i].getAttribute("data-tab") === t;
            tabs[i].style.color = on ? "#111" : "#6b7280";
            tabs[i].style.borderBottom = on ? "3px solid #2563eb" : "3px solid transparent";
            tabs[i].style.fontWeight = on ? "600" : "400";
        }
        if (t === "st") renderStorage();
        else if (t === "cost") renderCost();
        else if (t === "bc") renderBill();
        else if (t === "ch") renderChannels();
    }

    /* ── 状态卡 ──────────────────────────────────── */
    function renderStatus() {
        api("/api/outer/status").then(function (st) {
            var body = document.getElementById("op_body");
            if (!body) return;
            var html = '<div style="display:flex;gap:14px;flex-wrap:wrap;margin-bottom:14px">'
                + statusCard(st.channels_total, "统一渠道(含外层仓)") + statusCard(st.storage_count, "仓储费表") + statusCard(st.templates_total, "服务模板")
                + statusCard(st.pricing_records, "价卡记录") + statusCard("-", "核对引擎1.0")
                + '<div style="font-size:11px;color:#9ca3af;align-self:center">数据源：/data/unified_*.json ＋ /api/bill-check（服务端 startCheck 逻辑移植）</div></div>';
            body.insertAdjacentHTML("afterbegin", html);
        });
    }
    function statusCard(n, t) {
        return '<div style="background:#fff;border:1px solid #e3e8ef;border-radius:10px;padding:10px 16px;min-width:110px">'
            + '<div style="font-size:24px;font-weight:700;color:#2563eb">' + esc(n) + '</div>'
            + '<div style="font-size:12px;color:#6b7280">' + esc(t) + '</div></div>';
    }

    /* ── tab1 仓储阶梯 ───────────────────────────── */
    function renderStorage() {
        var body = document.getElementById("op_body");
        if (!body) return;
        ensureStorage().then(function () {
            body.innerHTML = '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px">'
                + '服务商 <select id="op_stp" style="font-size:13px;padding:5px 8px">'
                + Object.keys(STORAGE).sort().map(function (p) { return '<option>' + esc(p) + '</option>'; }).join("")
                + '</select><span id="op_ste" style="font-size:11px;color:#9ca3af"></span></div><div id="op_stt"></div>';
            document.getElementById("op_stp").addEventListener("change", drawStorageTable);
            drawStorageTable();
        });
    }
    function drawStorageTable() {
        var p = document.getElementById("op_stp").value;
        var st = STORAGE[p]; if (!st) return;
        document.getElementById("op_ste").textContent = "来源：" + (st.source || "") + " ｜ 单位 " + (st.unit || "") + " ｜ 币种 " + (st.currency || "");
        var tiers = st.tiers || [], whs = st.warehouses || [];
        var h = "<div style='overflow:auto'><table style='border-collapse:collapse;width:100%;font-size:12px'>"
            + "<tr><td style='border:1px solid #e3e8ef;padding:4px'></td>"
            + whs.map(function (w) { return "<th style='border:1px solid #e3e8ef;padding:4px 8px;white-space:nowrap'>" + esc(w.label) + "<br><span style='color:#9ca3af'>" + esc(w.code || "") + "</span></th>"; }).join("") + "</tr>";
        tiers.forEach(function (t) {
            h += "<tr><th style='border:1px solid #e3e8ef;padding:4px 8px;text-align:left;white-space:nowrap'>" + esc(t.label) + "</th>"
                + (t.prices || []).map(function (v) { return "<td style='border:1px solid #e3e8ef;padding:4px;text-align:center;font-family:Consolas'>" + (v == null ? "-" : Number(v).toFixed(2)) + "</td>"; }).join("") + "</tr>";
        });
        h += "</table></div>";
        if (st.return_zone_prices && st.return_zone_prices.length) {
            h += "<div style='font-size:12px;color:#6b7280;margin-top:8px'>退货区费率：" + st.return_zone_prices.map(function (r) {
                return esc(r.label) + " " + r.prices.map(function (x) { return Number(x).toFixed(2); }).join(" / ");
            }).join("；") + "</div>";
        }
        document.getElementById("op_stt").innerHTML = h;
    }

    /* ── tab2 仓储速算 ───────────────────────────── */
    function renderCost() {
        var body = document.getElementById("op_body");
        if (!body) return;
        ensureStorage().then(function () {
            var provs = Object.keys(STORAGE).sort();
            body.innerHTML = '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
                + '服务商 <select id="op_cp" style="font-size:13px;padding:5px 8px">' + provs.map(function (p) { return '<option>' + esc(p) + '</option>'; }).join("") + '</select>'
                + '仓库 <select id="op_cw" style="font-size:13px;padding:5px 8px"></select>'
                + 'CBM <input id="op_cbm" type="number" step="0.1" value="1" style="width:70px;font-size:13px;padding:5px">'
                + '库龄(天) <input id="op_days" type="number" step="1" value="100" style="width:70px;font-size:13px;padding:5px">'
                + '<button id="op_calc" style="font-size:13px;padding:6px 14px;background:#2563eb;color:#fff;border:none;border-radius:6px;cursor:pointer">计算</button></div>'
                + '<div id="op_cout" style="font-size:12px;color:#6b7280;margin-top:10px;line-height:1.7"></div>';
            document.getElementById("op_cp").addEventListener("change", syncCw);
            document.getElementById("op_calc").addEventListener("click", doCost);
            syncCw();
        });
    }
    function syncCw() {
        var p = document.getElementById("op_cp").value;
        var st = STORAGE[p];
        var w = document.getElementById("op_cw");
        if (!w) return;
        w.innerHTML = (st ? st.warehouses : []).map(function (x, i) { return '<option value="' + esc(x.code || i) + '">' + esc(x.label) + '</option>'; }).join("");
    }
    function doCost() {
        api("/api/storage/cost", {
            provider: document.getElementById("op_cp").value,
            warehouse: document.getElementById("op_cw").value,
            cbm: Number(document.getElementById("op_cbm").value) || 0,
            days: Number(document.getElementById("op_days").value) || 0
        }).then(function (r) {
            var el = document.getElementById("op_cout");
            if (!el) return;
            if (r.error) el.innerHTML = "✗ " + esc(r.error);
            else el.innerHTML = "库龄档 <b>" + esc(r.tier) + "</b> ｜ 单价 " + r.price_per_cbm_day + " × " + r.cbm + " CBM ｜ <b>日租 " + (r.currency || "") + " " + Number(r.total_per_day).toFixed(2) + "</b>"
                + "<br>约 30 天 " + (r.total_per_day * 30).toFixed(2) + " ｜ 约 90 天 " + (r.total_per_day * 90).toFixed(2) + "（单位：" + esc(r.unit) + "）";
        });
    }

    /* ── tab3 服务端账单核对 ─────────────────────── */
    var bcRows = "";
    function renderBill() {
        var body = document.getElementById("op_body");
        if (!body) return;
        api("/api/pricedata/channels").then(function (ch) {
            CHANNELS = ch.data || [];
            body.innerHTML = '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px">'
                + '模式 <select id="op_mode" style="font-size:13px;padding:5px 8px">'
                + '<option value="channel">按渠道（尾程：计费重+分区→价表/燃油/附加费）</option>'
                + '<option value="template">按服务商模板</option></select>'
                + '<select id="op_ch" style="font-size:13px;padding:5px 8px">' + CHANNELS.map(function (c) { return '<option>' + esc(c.name) + '</option>'; }).join("") + '</select>'
                + '<select id="op_prov" style="display:none;font-size:13px;padding:5px 8px"></select>'
                + '<select id="op_wh" style="display:none;font-size:13px;padding:5px 8px"></select>'
                + '<button id="op_demo" style="font-size:13px;padding:6px 14px;background:#fff;color:#2563eb;border:1px solid #2563eb;border-radius:6px;cursor:pointer">载入演示账单</button>'
                + '<button id="op_bc" style="font-size:13px;padding:6px 14px;background:#2563eb;color:#fff;border:none;border-radius:6px;cursor:pointer">开始核对</button></div>'
                + '<div style="font-size:11px;color:#6b7280;margin-bottom:6px">每行一条费用，列序任意，表头关键词自动识别（费用项目/计费重量/Zone分区/单位/金额/追踪号）。</div>'
                + '<textarea id="op_input" style="width:100%;height:150px;font-family:Consolas;font-size:12px;box-sizing:border-box;white-space:pre">' + bcRows + '</textarea>'
                + '<div id="op_pp" style="font-size:11px;color:#9ca3af;margin:6px 0"></div><div id="op_out"></div>';
            document.getElementById("op_demo").addEventListener("click", loadDemo);
            document.getElementById("op_bc").addEventListener("click", runCheck);
            document.getElementById("op_mode").addEventListener("change", syncModeOpts);
            document.getElementById("op_ch").value = (CHANNELS.filter(function (c) { return /Fedex_AHS/.test(c.name); })[0] || {}).name || (CHANNELS[0] || {}).name || "";
            TEMPLATES2 = [];
        });
    }
    var TEMPLATES2 = [];
    function syncModeOpts() {
        var m = document.getElementById("op_mode").value;
        document.getElementById("op_ch").style.display = m === "channel" ? "" : "none";
        document.getElementById("op_prov").style.display = m === "template" ? "" : "none";
        document.getElementById("op_wh").style.display = m === "template" ? "" : "none";
        if (m === "template") {
            api("/api/pricedata/templates").then(function (tp) {
                TEMPLATES2 = tp.data || [];
                var provs = [];
                TEMPLATES2.forEach(function (t) { if (provs.indexOf(t.provider) < 0) provs.push(t.provider); });
                provs.sort();
                var sel = document.getElementById("op_prov");
                if (!sel) return;
                sel.innerHTML = provs.map(function (p) { return '<option>' + esc(p) + '</option>'; }).join("");
                sel.dispatchEvent(new Event("change"));
            });
        }
    }
    document.addEventListener("change", function (e) {
        if (e.target && e.target.id === "op_prov") {
            var p = e.target.value, sel = document.getElementById("op_wh");
            if (!sel) return;
            var ws = [];
            TEMPLATES2.forEach(function (t) { if (t.provider === p && ws.indexOf(t.warehouse) < 0) ws.push(t.warehouse); });
            ws.sort();
            sel.innerHTML = ws.map(function (w) { return '<option>' + esc(w) + '</option>'; }).join("");
        }
    });
    function loadDemo() {
        var m = document.getElementById("op_mode");
        m.value = "channel";
        syncModeOpts();
        document.getElementById("op_input").value =
            "日期\t追踪号\t分区\t费用项目\t计费重量\t计费单位\t金额\n2026-08-30\t1Z999\tZone4\t尾程配送\t2\t磅\t9.50\n2026-08-30\t1Z999\tZone4\tFuel Surcharge（燃油费）\t2\t磅\t0.00\n2026-08-30\t2Z888\tZone4\t尾程配送\t3\t磅\t12.34";
        runCheck();
    }
    function parseMatrixTxt(txt) {
        var rows = [];
        txt.split(/\r?\n/).forEach(function (line) {
            if (!line.trim()) return;
            var cells = line.split("\t").length > 1 ? line.split("\t") : line.split(/[,，]/).map(function (s) { return s.trim(); });
            rows.push(cells);
        });
        return rows;
    }
    function runCheck() {
        var rows = parseMatrixTxt(document.getElementById("op_input").value);
        bcRows = document.getElementById("op_input").value;
        var mode = document.getElementById("op_mode").value;
        api("/api/bill/parse", { matrix: rows }).then(function (pr) {
            var pp = document.getElementById("op_pp");
            if (pp) pp.textContent = "表头行 L" + (pr.header_row + 1) + " ｜ 数据 " + pr.rows_total + " 行 ｜ 字段映射 重量/分区/金额列=" + [pr.mapping.weight, pr.mapping.zone, pr.mapping.amount].map(function (x) { return x >= 0 ? x : "-"; }).join("/") + (pr.with_amount ? "（含金额）" : "");
            var body = {
                matrix: rows,
                channelName: mode === "channel" ? document.getElementById("op_ch").value : undefined,
                provider: mode === "template" ? document.getElementById("op_prov").value : undefined,
                warehouse: mode === "template" ? document.getElementById("op_wh").value : undefined
            };
            return api("/api/bill-check", body);
        }).then(function (out) {
            var el = document.getElementById("op_out");
            if (!el) return;
            if (out.error) { el.innerHTML = "<span style='color:#b91c1c'>✗ " + esc(out.error) + "</span>"; return; }
            var sm = out.summary, i;
            var badge = function (cls, txt) { return '<span style="padding:1px 10px;border-radius:10px;font-size:12px;margin-right:6px">' + txt + "</span>"; };
            var h = '<div style="font-size:12px;margin:8px 0">共 ' + sm.total + ' 项｜'
                + '<span style="background:#dcfce7;color:#166534;padding:1px 10px;border-radius:10px;margin-right:6px">一致 ' + sm.match + '</span>'
                + '<span style="background:#fee2e2;color:#991b1b;padding:1px 10px;border-radius:10px;margin-right:6px">差异 ' + sm.diff + '</span>'
                + '<span style="background:#fef9c3;color:#854d0e;padding:1px 10px;border-radius:10px">需关注 ' + sm.warn + '</span></div>';
            h += "<div style='overflow:auto'><table style='border-collapse:collapse;width:100%;font-size:12px'>"
                + "<tr><th style='border:1px solid #e3e8ef;padding:4px'>行</th><th style='border:1px solid #e3e8ef;padding:4px'>账单项目</th>"
                + "<th style='border:1px solid #e3e8ef;padding:4px'>计费重</th><th style='border:1px solid #e3e8ef;padding:4px'>账单金额</th>"
                + "<th style='border:1px solid #e3e8ef;padding:4px'>应收</th><th style='border:1px solid #e3e8ef;padding:4px'>差额</th>"
                + "<th style='border:1px solid #e3e8ef;padding:4px'>判定</th><th style='border:1px solid #e3e8ef;padding:4px'>依据</th></tr>";
            for (i = 0; i < out.results.length; i++) {
                var r = out.results[i];
                var bg = r.status === "match" ? "background:#dcfce7" : r.status === "diff" ? "background:#fee2e2" : "background:#fef9c3";
                h += "<tr style='" + bg + "'><td style='border:1px solid #e3e8ef;padding:4px'>" + r.row + "</td>"
                    + "<td style='border:1px solid #e3e8ef;padding:4px;text-align:left'>" + esc(r.billService) + "</td>"
                    + "<td style='border:1px solid #e3e8ef;padding:4px'>" + (r.billQty ? r.billQty : "") + "</td>"
                    + "<td style='border:1px solid #e3e8ef;padding:4px'>" + (r.billAmount != null ? Number(r.billAmount).toFixed(2) : "-") + "</td>"
                    + "<td style='border:1px solid #e3e8ef;padding:4px'>" + (r.expectedAmount != null ? Number(r.expectedAmount).toFixed(2) : "-") + "</td>"
                    + "<td style='border:1px solid #e3e8ef;padding:4px'>" + (r.diff != null ? (r.diff > 0 ? "+" : "") + Number(r.diff).toFixed(2) : "-") + "</td>"
                    + "<td style='border:1px solid #e3e8ef;padding:4px'>" + (r.status === "match" ? "一致" : r.status === "diff" ? "差异" : "需关注") + "</td>"
                    + "<td style='border:1px solid #e3e8ef;padding:4px;text-align:left;color:#6b7280'>" + esc(r.note) + "</td></tr>";
            }
            h += "</table></div>";
            el.innerHTML = h;
        });
    }

    /* ── 数据缓存 ─────────────────────────────────── */
    function ensureStorage() {
        if (Object.keys(STORAGE).length) return Promise.resolve();
        return api("/api/storage").then(function (st) { STORAGE = st.storage || {}; });
    }

    /* ── 按钮 ─────────────────────────────────────── */
    function addBtn() {
        if (document.getElementById(BTN_ID)) return;
        var b = document.createElement("button");
        b.id = BTN_ID;
        b.textContent = "🧾 外仓/仓储/服务端核对";
        b.style.cssText = "position:fixed;right:16px;bottom:48px;z-index:2147482000;background:#2563eb;color:#fff;"
            + "border:none;padding:9px 14px;border-radius:999px;font-size:12px;cursor:pointer;box-shadow:0 2px 10px rgba(0,0,0,.25)";
        b.addEventListener("click", function () {
            var p = ensurePanel();
            p.style.display = "flex";
            switchTab("st");
        });
        document.body.appendChild(b);
    }
    function init() {
        if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", addBtn);
        else addBtn();
    }
    init();
})();