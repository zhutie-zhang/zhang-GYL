/*
 * price-checker.html 同步层（由 Flask /price-checker 路由注入，仅服务端模式生效）
 * 功能：
 *  1. 页面加载后，若有 localStorage 数据 → 自动推送到服务端统一价卡(/api/pricedata)；
 *  2. 拦截 4 个价卡 localStorage key，写入后异步同步到服务端；
 *  3. 提供“☁️ 服务端同步/差异”入口，查询版本哈希与漂移差异。
 * 离线模式（直接双击打开 HTML）不受影响。
 */
(function () {
    "use strict";
    var KEYMAP = {
        warehouseTemplates: "templates",
        logisticsChannels: "channels",
        fuelRates: "fuel",
        freightTemplates: "freight",
        warehouseCards: "card"
    };
    var serverKind = Object.values(KEYMAP);
    var origSet = localStorage.setItem.bind(localStorage);
    var inited = false;
    var syncing = {};

    function postJSON(url, data) {
        return fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data)
        }).then(function (r) { return r.json(); });
    }
    function putJSON(url, data) {
        return fetch(url, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data)
        }).then(function (r) { return r.json(); });
    }

    function syncOne(kind, data) {
        if (syncing[kind]) return;
        syncing[kind] = true;
        putJSON("/api/pricedata/" + kind, { data: data })
            .then(function () { })
            .catch(function () { })
            .finally(function () { syncing[kind] = false; });
    }

    // 拦截 setItem
    localStorage.setItem = function (key, val) {
        origSet(key, val);
        if (KEYMAP[key]) {
            try {
                syncOne(KEYMAP[key], JSON.parse(val));
            } catch (e) { /* ignore */ }
        }
    };

    // 页面加载：尝试服务端已有数据覆盖本地（迁移按钮由页面自身提供）
    function pullFromServer() {
        var pending = serverKind.slice();
        var merged = {};
        pending.forEach(function (kind) {
            fetch("/api/pricedata/" + kind, { cache: "no-store" })
                .then(function (r) { return r.json(); })
                .then(function (j) {
                    var remote = j && j.data;
                    merged[kind] = remote;
                    var idx = pending.indexOf(kind);
                    if (idx >= 0) pending.splice(idx, 1);
                    if (pending.length === 0) applyRemote(merged);
                })
                .catch(function () {
                    var idx = pending.indexOf(kind);
                    if (idx >= 0) pending.splice(idx, 1);
                });
        });
    }
    function applyRemote(merged) {
        if (!merged.channels || !merged.channels.length) return;
        origSet("logisticsChannels", JSON.stringify(merged.channels));
        if (merged.templates && merged.templates.length) {
            origSet("warehouseTemplates", JSON.stringify(merged.templates));
        }
        if (merged.fuel && Object.keys(merged.fuel).length) {
            origSet("fuelRates", JSON.stringify(merged.fuel));
        }
        if (merged.freight && merged.freight.length) {
            origSet("freightTemplates", JSON.stringify(merged.freight));
        }
        if (merged.card && merged.card.length) {
            origSet("warehouseCards", JSON.stringify(merged.card));
            try {
                document.dispatchEvent(new CustomEvent("pcs:card"));
            } catch (e) { /* ignore */ }
        }
    }

    function addSyncBar() {
        if (document.getElementById("pcs-syncbar")) return;
        var bar = document.createElement("div");
        bar.id = "pcs-syncbar";
        bar.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:999;display:flex;flex-direction:column;gap:6px;align-items:flex-end;";
        var syncBtn = document.createElement("button");
        syncBtn.textContent = "☁️ 同步到服务端";
        syncBtn.style.cssText = "background:#1a73e8;color:#fff;border:none;border-radius:8px;padding:8px 14px;font-size:13px;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.2);";
        syncBtn.onclick = function () {
            var total = 0;
            serverKind.forEach(function (kind) {
                var key = Object.keys(KEYMAP).find(function (k) { return KEYMAP[k] === kind; });
                var raw = localStorage.getItem(key);
                if (!raw) {
                    syncOne(kind, kind === "fuel" ? {} : []);
                    return;
                }
                try {
                    var data = JSON.parse(raw);
                    syncOne(kind, data);
                    total++;
                } catch (e) { /* skip */ }
            });
            syncBtn.textContent = "☁️ 已推送 " + total + " 类价卡到服务端";
            setTimeout(function () { syncBtn.textContent = "☁️ 同步到服务端"; }, 2000);
        };
        var diffBtn = document.createElement("button");
        diffBtn.textContent = "🔍 检查价卡差异(版本漂移)";
        diffBtn.style.cssText = "background:#fbbc04;color:#333;border:none;border-radius:8px;padding:8px 14px;font-size:13px;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.2);";
        diffBtn.onclick = function () {
            var out = [];
            serverKind.forEach(function (kind) {
                fetch("/api/pricedata/" + kind + "/diff", { cache: "no-store" })
                    .then(function (r) { return r.json(); })
                    .then(function (j) {
                        var tag = j.changed ? "🔄 变化(" + (j.diff || []).length + "处)" : "✅ 无变化";
                        out.push(kind + ": " + tag);
                        var box = document.getElementById("pcs-diffbox") || makeDiffBox();
                        box.textContent = "版本漂移检查\n" + out.join("\n");
                    })
                    .catch(function () { });
            });
        };
        bar.appendChild(syncBtn);
        bar.appendChild(diffBtn);
        document.body.appendChild(bar);
    }
    function makeDiffBox() {
        var box = document.createElement("pre");
        box.id = "pcs-diffbox";
        box.style.cssText = "position:fixed;right:16px;bottom:120px;z-index:999;background:#fff;border:1px solid #ccc;border-radius:8px;padding:10px;font-size:12px;max-width:320px;white-space:pre-wrap;box-shadow:0 2px 10px rgba(0,0,0,.15);";
        document.body.appendChild(box);
        return box;
    }

    function init() {
        if (inited) return;
        inited = true;
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", boot);
        } else {
            boot();
        }
    }
    function boot() {
        setTimeout(function () {
            pullFromServer();
            addSyncBar();
        }, 400);
    }
    init();
})();