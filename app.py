import json
import logging
import os
import re
import signal
import sys
from collections import defaultdict
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "server.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("warehouse")

from flask import Flask, jsonify, request, send_from_directory

from adapters.registry import build_adapter
from product_kit import KitMap, import_kit_excel, import_standalone_excel
import product_tags
import transit
from custom_source_manager import CustomSourceManager
import analytics
import supply_chain
import restocking
import pricing

import price_data
import zonemap
import bill_check
import outer_import


def load_config():
    path = os.path.join(BASE_DIR, "config.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


CONFIG = load_config()
SERVER = CONFIG.get("server", {})
DEFAULT_OUT_TZ = SERVER.get("default_outbound_tz", "Asia/Shanghai")


class Cache:
    """内存 + 磁盘双层缓存。内存命中优先；未命中则尝试磁盘（跨进程/重启保留）。
    仅对 JSON 可序列化的值落盘；按 key 单文件存储，get 时仍校验 TTL。"""

    _DISK_DIR = os.path.join(BASE_DIR, ".cache")
    _PERSIST = set(("flow", "outbound", "inventory", "inv", "out", "age"))

    def __init__(self):
        self._data = {}
        self._lock = threading.Lock()
        self._disk_lock = threading.Lock()
        try:
            os.makedirs(self._DISK_DIR, exist_ok=True)
        except OSError:
            pass

    def _disk_path(self, key):
        return os.path.join(self._DISK_DIR,
                            key.replace("/", "_").replace(":", "_")[:200] + ".json")

    def _persistable(self, key):
        k = key.split(":", 1)[0]
        return k in self._PERSIST

    def _load_disk(self, key):
        path = self._disk_path(key)
        try:
            with open(path, "r", encoding="utf-8") as f:
                item = json.load(f)
        except (OSError, ValueError):
            return None
        if datetime.now().timestamp() - item.get("at", 0) <= item.get("ttl", 0):
            return item
        try:
            os.remove(path)
        except OSError:
            pass
        return None

    def _save_disk(self, key, item):
        path = self._disk_path(key)
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(item, f, ensure_ascii=False)
            os.replace(tmp, path)
        except (OSError, ValueError):
            try:
                os.remove(tmp)
            except OSError:
                pass

    def get(self, key):
        with self._lock:
            item = self._data.get(key)
            if not item:
                if self._persistable(key):
                    with self._disk_lock:
                        item = self._load_disk(key)
                    if item:
                        self._data[key] = item
                return item["value"] if item else None
            if datetime.now().timestamp() - item["at"] > item["ttl"]:
                self._data.pop(key, None)
                return None
            return item["value"]

    def set(self, key, value, ttl):
        now = datetime.now().timestamp()
        item = {"at": now, "ttl": ttl, "value": value}
        with self._lock:
            self._data[key] = item
        if self._persistable(key):
            with self._disk_lock:
                self._save_disk(key, item)

    def invalidate(self):
        with self._lock:
            self._data.clear()
        with self._disk_lock:
            for name in os.listdir(self._DISK_DIR):
                if name.endswith(".json"):
                    try:
                        os.remove(os.path.join(self._DISK_DIR, name))
                    except OSError:
                        pass


CACHE = Cache()

# 单飞合并：拖取重建只允许同时一个，避免并发重复请求拖垮服务器
_FETCH_INFLIGHT = {}
_FETCH_RESULTS = {}
_FETCH_LOCK = threading.Lock()
FETCH_WH_TIMEOUT = int(SERVER.get("fetch_wh_timeout", 90))
FETCH_BUILD_TIMEOUT = int(SERVER.get("fetch_build_timeout", 150))


def _safe_remove(path, attempts=12, delay=0.5):
    """安全删除临时文件：PDF 解析超时后后台线程可能仍占用文件句柄，
    Windows 下直接删除会抛 WinError 32，重试等待句柄释放。"""
    for i in range(attempts):
        try:
            if os.path.exists(path):
                os.remove(path)
            return True
        except OSError:
            if i < attempts - 1:
                time.sleep(delay)
    return False
KIT = KitMap()
TRANSIT = transit.TransitStore()
CUSTOM_SOURCES = CustomSourceManager()
PRICING = pricing.PricingStore()
SUPPLIERS = pricing.SupplierStore()
import github_sync

PRICE_DATA = price_data

def _github_pull_startup():
    """Startup: pull files from GitHub repo."""
    try:
        result = github_sync.pull_all()
        print(f"[GitHub同步] {result}", flush=True)
    except Exception as e:
        print(f"[GitHub同步] 拉取失败: {e}", flush=True)


def _tag_lines_product_type(lines):
    """按 SKU 精确匹配产品库，给每行写入 type (combo / component / standalone) 和 combo_sku。返回 (lines, warnings)。"""
    sku_type = {}
    comp_to_combo = {}
    all_known = set()
    for p in KIT.list():
        sku_type[p["sku"]] = p["type"]
        all_known.add(p["sku"])
        if p["type"] == "combo":
            for c in p.get("components", []):
                comp_to_combo[c] = p["sku"]
                all_known.add(c)
    warnings = []
    for ln in lines:
        sku = ln.get("sku", "")
        if sku_type.get(sku) == "combo":
            ln["type"] = "combo"
        elif sku in comp_to_combo:
            ln["type"] = "component"
            ln["combo_sku"] = comp_to_combo[sku]
        else:
            ln["type"] = "standalone"
            if sku and sku not in all_known:
                warnings.append("SKU %s 未在产品库中找到" % sku)
    return lines, warnings


def ttl_for(kind):
    if kind == "outbound":
        return int(SERVER.get("cache_ttl_outbound", 1800))
    return int(SERVER.get("cache_ttl_inventory", 300))


def build_adapters(warehouses):
    result = []
    for w in warehouses:
        if not w.get("enabled", True):
            continue
        try:
            result.append((w, build_adapter(w)))
        except Exception as e:
            result.append((w, {"error": str(e)}))
    return result


ADAPTERS = build_adapters(CONFIG.get("warehouses", []))


def today_local(tz_name):
    return datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d")


def yesterday_local(tz_name):
    from datetime import timedelta

    return (datetime.now(ZoneInfo(tz_name)) - timedelta(days=1)).strftime("%Y-%m-%d")


def fetch_one(kind, w, adapter):
    wh_id = w["id"]
    tz = w.get("timezone", "UTC")
    if isinstance(adapter, dict):
        return {"id": wh_id, "name": w.get("name", wh_id), "group": w.get("group", ""),
                "status": "error", "error": adapter["error"]}
    try:
        if kind == "inventory":
            points, fetched = adapter.fetch_inventory()
            date_note = None
        else:
            points, fetched, date_used = adapter.fetch_outbound(requested_date=None)
            date_note = date_used
        points = [dict(p, rows=KIT.apply(p.get("rows") or [])) for p in points]
        return {
            "id": wh_id,
            "name": w.get("name", wh_id),
            "group": w.get("group", ""),
            "account": w.get("account", ""),
            "status": "ok",
            "error": None,
            "fetched_at": fetched,
            "points": points,
            "date_note": date_note,
        }
    except Exception as e:
        return {"id": wh_id, "name": w.get("name", wh_id), "group": w.get("group", ""),
                "account": w.get("account", ""),
                "status": "error", "error": f"{type(e).__name__}: {e}"}


def _with_single_flight(key, builder):
    """单飞合并：同一 key 同一时刻只允许一个重建任务，其余并发请求等待其结果。

    避免页面前台自动刷新 / 备货接口 / 强制刷新等多个请求在缓存过期后同时各自
    重复抓取全部海外仓，导致服务器线程被占满、请求排队甚至超时。
    """
    with _FETCH_LOCK:
        ev = _FETCH_INFLIGHT.get(key)
        if ev is None:
            ev = threading.Event()
            _FETCH_INFLIGHT[key] = ev
            owner = True
        else:
            owner = False
    if not owner:
        ev.wait(timeout=FETCH_BUILD_TIMEOUT)
        with _FETCH_LOCK:
            ok, value = _FETCH_RESULTS.get(key, (False, None))
            still_running = key in _FETCH_INFLIGHT
        if ok:
            return value
        if not still_running:
            return None
        # 原任务超时未完成：由本线程接管重建，保证请求一定返回
        owner = True
        ev = threading.Event()
        with _FETCH_LOCK:
            _FETCH_INFLIGHT[key] = ev
    built = None
    try:
        built = builder()
        return built
    finally:
        with _FETCH_LOCK:
            if key in _FETCH_INFLIGHT and _FETCH_INFLIGHT[key] is ev:
                _FETCH_INFLIGHT.pop(key, None)
                _FETCH_RESULTS[key] = (True, built)
            ev.set()


def fetch_all(kind, force=False):
    cache_key = f"{kind}:all"
    if not force:
        cached = CACHE.get(cache_key)
        if cached:
            return cached

    def _build():
        custom_configs = CUSTOM_SOURCES.to_warehouse_configs()
        all_warehouses = CONFIG.get("warehouses", []) + custom_configs
        all_adapters = build_adapters(all_warehouses)
        results = {}
        ex = ThreadPoolExecutor(max_workers=max(1, len(all_adapters)))
        futures = [ex.submit(fetch_one, kind, w, a) for w, a in all_adapters]
        try:
            for (w, a), f in zip(all_adapters, futures):
                try:
                    r = f.result(timeout=FETCH_WH_TIMEOUT)
                except Exception:
                    r = {"id": w["id"], "name": w.get("name", w["id"]),
                         "group": w.get("group", ""), "account": w.get("account", ""),
                         "status": "error", "error": "获取超时（> %ss）" % FETCH_WH_TIMEOUT}
                results[r["id"]] = r
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
        groups = list(CONFIG.get("groups", []))
        seen_gids = {g["id"] for g in groups}
        for s in CUSTOM_SOURCES.list_all():
            gid = s.get("group", "custom")
            if gid and gid not in seen_gids:
                groups.append({"id": gid, "name": gid})
                seen_gids.add(gid)
        payload = {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   "groups": groups,
                   "warehouses": results}
        CACHE.set(cache_key, payload, ttl_for(kind))
        return payload

    return _with_single_flight(cache_key, _build)


def fetch_age_one(w, adapter):
    """拉取单个领星 OMS 账号的产品库龄。非 xlwms 或无该能力的适配器返回 status=unsupported。"""
    wh_id = w["id"]
    if isinstance(adapter, dict):
        return {"id": wh_id, "name": w.get("name", wh_id), "group": w.get("group", ""),
                "status": "error", "error": adapter["error"]}
    if not hasattr(adapter, "fetch_inventory_age"):
        return {"id": wh_id, "name": w.get("name", wh_id), "group": w.get("group", ""),
                "status": "unsupported", "error": None, "rows": []}
    try:
        rows, fetched = adapter.fetch_inventory_age()
        return {"id": wh_id, "name": w.get("name", wh_id), "group": w.get("group", ""),
                "account": w.get("account", ""),
                "status": "ok", "error": None, "fetched_at": fetched, "rows": rows}
    except Exception as e:
        return {"id": wh_id, "name": w.get("name", wh_id), "group": w.get("group", ""),
                "account": w.get("account", ""),
                "status": "error", "error": f"{type(e).__name__}: {e}", "rows": []}


def fetch_all_age(force=False):
    """拉取所有已接入且支持库龄的海外仓(领星 OMS)产品库龄，聚合统计分档。"""
    key = "age:all"
    if not force:
        cached = CACHE.get(key)
        if cached:
            return cached

    def _build():
        custom_configs = CUSTOM_SOURCES.to_warehouse_configs()
        all_warehouses = CONFIG.get("warehouses", []) + custom_configs
        all_adapters = build_adapters(all_warehouses)
        results = {}
        ex = ThreadPoolExecutor(max_workers=max(1, len(all_adapters)))
        futures = [ex.submit(fetch_age_one, w, a) for w, a in all_adapters]
        try:
            for (w, a), f in zip(all_adapters, futures):
                try:
                    r = f.result(timeout=FETCH_WH_TIMEOUT)
                except Exception:
                    r = {"id": w["id"], "name": w.get("name", w["id"]),
                         "group": w.get("group", ""), "account": w.get("account", ""),
                         "status": "error", "error": "获取超时（> %ss）" % FETCH_WH_TIMEOUT,
                         "rows": []}
                results[r["id"]] = r
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
        groups = list(CONFIG.get("groups", []))
        seen_gids = {g["id"] for g in groups}
        for s in CUSTOM_SOURCES.list_all():
            gid = s.get("group", "custom")
            if gid and gid not in seen_gids:
                groups.append({"id": gid, "name": gid})
                seen_gids.add(gid)
        # 给每行标组合分类：组合产品(kit) / 非组合产品(standalone) / 组合产品不成套(part)。
        _tag_age_category(results)
        # 库龄数量按「在仓箱数」口径对齐：同一仓库库龄件数若与其在仓箱数不等，
        # 按比例缩放各批次数量以对齐在仓箱数（差额为拆开件/整机及快照日差异）。
        _reconcile_age_to_box(results)
        # 只统计在库的产品库龄：剔除不在库（数量<=0）的行，
        # 使库龄数量严格对齐库存在仓数量。
        _drop_not_in_stock(results)
        payload = {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   "groups": groups,
                   "warehouses": results}
        CACHE.set(key, payload, ttl_for("inventory"))
        return payload

    return _with_single_flight(key, _build)


def _tag_age_category(results):
    """按 SKU 给库龄每行写入组合分类字段 cat：
    kit=组合产品 / part=组合产品不成套(子件) / standalone=非组合产品。"""
    combo = set()
    comp = {}
    for p in KIT.list():
        if p["type"] == "combo":
            combo.add(p["sku"])
            for c in p.get("components") or []:
                comp[c] = p["sku"]
    for w in results.values():
        rows = w.get("rows")
        if not rows:
            continue
        for r in rows:
            sku = str(r.get("sku") or "").strip()
            if sku in combo:
                r["cat"] = "kit"
                r["cat_label"] = "组合产品"
            elif sku in comp:
                r["cat"] = "part"
                r["cat_label"] = "组合不成套"
                r.setdefault("kit_sku", comp[sku])
            else:
                r["cat"] = "standalone"
                r["cat_label"] = "非组合"


def _reconcile_age_to_box(results):
    """把每个仓库的库龄数量对齐到该仓库的在仓箱数(count of box)。

    领星/安美等库龄以「拆开件/总库存 + 统计日快照」给出，与在仓整机箱数存在
    小幅差异(≤2%)。这里按各仓库在仓箱数为基准，对该仓库所有库龄行数量做比例
    缩放并补差，使每仓库库龄总量 = 在仓箱数。在仓箱数来自 inventory 缓存。
    """
    try:
        inv_payload = fetch_all("inventory")
    except Exception:
        return
    inv_wh = (inv_payload or {}).get("warehouses", {})
    for wid, w in results.items():
        if w.get("status") != "ok" or not w.get("rows"):
            continue
        iw = inv_wh.get(wid) or {}
        box = 0
        for p in (iw.get("points") or []):
            for r in p.get("rows") or []:
                try:
                    box += int(r.get("box") or 0)
                except (TypeError, ValueError):
                    pass
        age_sum = 0
        for r in w["rows"]:
            try:
                age_sum += int(r.get("qty") or 0)
            except (TypeError, ValueError):
                pass
        if box <= 0 or age_sum == box:
            continue
        factor = box / float(age_sum)
        rows = w["rows"]
        total = 0
        new_rows = []
        for r in rows:
            nr = dict(r)
            try:
                nq = max(0, int(round(int(r.get("qty") or 0) * factor)))
            except (TypeError, ValueError):
                nq = int(r.get("qty") or 0)
            nr["qty"] = nq
            total += nq
            new_rows.append(nr)
        # 补差：把 box-total 的余数尽量平摊到数量最大的行上
        diff = box - total
        step = 1 if diff > 0 else -1
        order = sorted(range(len(new_rows)), key=lambda i: -new_rows[i]["qty"])
        k = 0
        while diff != 0 and order and k < len(order) * 2:
            i = order[k % len(order)]
            if new_rows[i]["qty"] + step >= 0:
                new_rows[i]["qty"] += step
                diff -= step
            k += 1
        w["rows"] = new_rows
        w["aligned_to_box"] = True


def _drop_not_in_stock(results):
    """只统计在库的产品库龄：剔除不在库（数量<=0）的行。

    库龄按批次统计，数量为 0 表示该批次已不在库，不参与统计。
    """
    for w in results.values():
        rows = w.get("rows")
        if not rows:
            continue
        w["rows"] = [r for r in rows if (r.get("qty") or 0) > 0]


app = Flask(__name__, static_folder="static", static_url_path="/static")


@app.errorhandler(Exception)
def handle_exception(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    log.exception("Unhandled exception")
    return jsonify({"error": str(e)}), 500


@app.before_request
def _log_request():
    pass


@app.after_request
def _log_after(response):
    if response.status_code >= 400:
        log.warning("%s %s -> %s", request.method, request.path, response.status_code)
    return response


def _handle_signal(signum, frame):
    log.warning("Received signal %s, shutting down", signum)
    sys.exit(0)


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


@app.after_request
def no_cache(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/xlsx.full.min.js")
def _xlsx_lib():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "xlsx.full.min.js")


@app.route("/pdf.min.js")
def _pdf_lib():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "pdf.min.js")


@app.route("/pdf.worker.min.js")
def _pdf_worker_lib():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "pdf.worker.min.js")


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/price-checker")
def price_checker_page():
    """serve 单文件离线版 price-checker.html，并注入服务端同步层脚本。"""
    target = os.path.join(BASE_DIR, "price-checker.html")
    if not os.path.exists(target):
        return jsonify({"error": "price-checker.html 缺失"}), 404
    with open(target, "r", encoding="utf-8") as f:
        html = f.read()
    inject = ('<script src="/static/js/price-checker-sync.js"></script>')
    marker_map = [("</body>", True)]
    for marker, _ in marker_map:
        if marker in html:
            html = html.replace(marker, inject + "\n" + marker, 1)
            break
    else:
        html += inject
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/api/price-checker")
def api_price_checker():
    """总入口信息，供首页跳转使用。"""
    return jsonify({
        "page": "/price-checker",
        "data_api": "/api/pricedata",
        "zonemap_api": "/api/zonemap",
        "official_import_api": "/api/official/import",
    })


# ── 运费计算 /api/calc（移植自 server.js，供 price-checker 从 8000 打开时使用）──────
def _c_round2(x):
    return round(x * 100) / 100


def server_zip_to_zone(tpl, zip_str):
    z = re.sub(r"[^0-9-]", "", zip_str or "")[:5]
    if not z:
        return None
    try:
        zi = int(re.sub(r"[^0-9]", "", z))
    except ValueError:
        return None
    for r in (tpl or {}).get("zipRules") or []:
        try:
            f_, t_ = int(r.get("from", 0)), int(r.get("to", 0))
        except (ValueError, TypeError):
            continue
        if f_ <= zi <= t_:
            return r.get("zone")
    return None


def server_lookup_base(tpl, weight, zone):
    rows = sorted((tpl or {}).get("rows") or [], key=lambda r: (r.get("max") or 0))
    price = None
    for r in rows:
        mx = r.get("max")
        if weight <= (mx if mx is not None else 1e18):
            p = r.get("prices") or []
            if 1 <= zone <= len(p):
                v = p[zone - 1]
                if v not in (None, ""):
                    price = float(v)
            break
    if price is None and rows:
        last = rows[-1]
        p = last.get("prices") or []
        if 1 <= zone <= len(p) and p[zone - 1] not in (None, ""):
            price = float(p[zone - 1])
    return price


def server_calc_freight(config, params):
    try:
        actual_kg = float(params.get("weightKg"))
        if actual_kg <= 0:
            return {"ok": False, "error": "实重无效"}
        vol_kg = 0.0
        dims = params.get("dims")
        if dims:
            dl = re.split(r"[xX*\u00d7]", str(dims))
            vals = [float(s) for s in dl if _try_float(s)]
            if len(vals) == 3 and all(v > 0 for v in vals):
                vol_kg = vals[0] * vals[1] * vals[2] / (config.get("volParam") or 6000)
        charge_by = config.get("chargeBy") or "actual"
        if charge_by == "volumetric":
            weight_kg = vol_kg if vol_kg > 0 else actual_kg
        elif charge_by == "max":
            weight_kg = max(actual_kg, vol_kg)
        else:
            weight_kg = actual_kg
        zone = server_zip_to_zone(config, params.get("zip"))
        if zone is None:
            return {"ok": False, "error": "邮编未命中任何分区规则"}
        try:
            pieces = max(1, int(params.get("pieces") or 1))
        except (ValueError, TypeError):
            pieces = 1
        per_piece = config.get("calcMode") == "perPiece"
        unit_w = weight_kg / pieces if per_piece else weight_kg
        unit_base = server_lookup_base(config, unit_w, zone)
        if unit_base is None:
            return {"ok": False, "error": "Zone{} 在重量 {} 档无报价".format(zone, unit_w)}
        base = _c_round2(unit_base * pieces) if per_piece else unit_base
        items = []
        fixed_total = whop_total = pct_total = 0.0
        for s in (config.get("surcharges") or []):
            if s.get("enabled") is False:
                continue
            zs = s.get("zones") or []
            if zs and zone not in zs:
                continue
            if s.get("mode") != "fixed":
                continue
            if s.get("type") == "whop":
                whop_total += _c_round2(s.get("value", 0))
                items.append({"name": s.get("name") or "库内操作费", "kind": "whop", "mode": "fixed",
                              "value": s.get("value", 0), "zones": zs, "amount": _c_round2(s.get("value", 0)),
                              "note": "不参与百分比基数"})
            else:
                fixed_total += _c_round2(s.get("value", 0))
                items.append({"name": s.get("name") or "附加费", "kind": "normal", "mode": "fixed",
                              "value": s.get("value", 0), "zones": zs, "amount": _c_round2(s.get("value", 0)), "note": ""})
        pct_base = _c_round2(base + fixed_total)
        for s in (config.get("surcharges") or []):
            if s.get("enabled") is False:
                continue
            zs = s.get("zones") or []
            if zs and zone not in zs:
                continue
            if s.get("mode") != "percent":
                continue
            pct = s.get("value") or 0
            amt = _c_round2(pct_base * pct / 100)
            pct_total += amt
            items.append({"name": s.get("name") or "百分比附加费", "kind": s.get("type") or "normal",
                          "mode": "percent", "value": pct, "zones": zs, "amount": amt,
                          "note": "基准=(基础+{:.2f})".format(fixed_total)})
        total = _c_round2(base + fixed_total + pct_total + whop_total)
        return {"ok": True, "zone": zone, "actualKg": actual_kg, "volKg": vol_kg, "chargeBy": charge_by,
                "weightKg": weight_kg, "pieces": pieces, "perPiece": per_piece,
                "unitWeight": _c_round2(unit_w), "base": base, "fixedTotal": fixed_total,
                "pctBase": pct_base, "pctTotal": pct_total, "whopTotal": whop_total,
                "items": items, "total": total}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _try_float(s):
    try:
        float(s)
        return True
    except (TypeError, ValueError):
        return False


@app.route("/api/calc", methods=["POST", "OPTIONS"])
def api_calc():
    if request.method == "OPTIONS":
        return ("", 204)
    body = request.get_json(force=True, silent=True) or {}
    config = body.get("config") or {}
    out = server_calc_freight(config, body)
    return jsonify(out)


@app.route("/api/fuel")
def api_fuel():
    """抓取承运商官网燃油页（FedEx 等），提取百分比。"""
    target = (request.args.get("url") or "").strip()
    if not re.match(r"^https?://", target):
        return jsonify({"error": "url 必须为 http/https"}), 400
    if re.match(r"^https?://((127\.0\.0\.1)|localhost)", target):
        return jsonify({"error": "不允许访问本机地址"}), 400
    try:
        import urllib.request
        req = urllib.request.Request(target, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        pcts = [float(m) for m in re.findall(r"(\d{1,3}(?:\.\d{1,2})?)\s*%", text)]
        uniq = sorted({p for p in pcts if 0.5 <= p <= 100})
        title = re.search(r"<title>([\s\S]*?)</title>", text, re.I)
        return jsonify({"ok": True, "percentages": uniq,
                        "chars": len(text), "title": title.group(1) if title else ""})
    except Exception as e:
        return jsonify({"error": "抓取失败：{}".format(e)}), 502


@app.route("/api/warehouses")
def api_warehouses():
    out = []
    for w in CONFIG.get("warehouses", []):
        out.append({
            "id": w["id"],
            "name": w.get("name", w["id"]),
            "country": w.get("country", ""),
            "timezone": w.get("timezone", "UTC"),
            "enabled": w.get("enabled", True),
            "type": w.get("type", ""),
            "group": w.get("group", ""),
            "account": w.get("account", ""),
        })
    return jsonify({
        "groups": CONFIG.get("groups", []),
        "warehouses": out,
        "auto_refresh_seconds": int(SERVER.get("auto_refresh_seconds", 60)),
    })


@app.route("/api/inventory")
def api_inventory():
    data = fetch_all("inventory", force=request.args.get("force") == "1")
    return jsonify(data)


@app.route("/api/inventory/age")
def api_inventory_age():
    force = request.args.get("force") == "1"
    statistic_date = request.args.get("date") or None
    data = fetch_all_age(force=force)
    if statistic_date:
        # 前端传日期时按库龄统计日期过滤（仅领星返回该字段）
        results = data.get("warehouses", {})
        for wid, w in list(results.items()):
            if w.get("status") == "ok" and w.get("rows"):
                w["rows"] = [r for r in w["rows"] if r.get("statistic_date") in ("", statistic_date)]
        data["filtered_date"] = statistic_date
    return jsonify(data)


@app.route("/api/debug/aidelivery")
def api_debug_aidelivery():
    out = {}
    for w, a in ADAPTERS:
        if w.get("type") != "aidelivery":
            continue
        try:
            points, fetched = a.fetch_inventory()
            rows = [r for p in points for r in p["rows"]]
            out["inventory"] = {"fetched_at": fetched, "rows": rows[:50],
                                "count": len(rows), "points": points}
        except Exception as e:
            out["inventory_error"] = f"{type(e).__name__}: {e}"
        try:
            points2, fetched2, date_used = a.fetch_outbound(None)
            rows2 = [r for p in points2 for r in p["rows"]]
            out["outbound"] = {"fetched_at": fetched2, "date_used": date_used,
                               "rows": rows2[:50], "count": len(rows2),
                               "points": points2}
        except Exception as e:
            out["outbound_error"] = f"{type(e).__name__}: {e}"
    return jsonify(out)


def resolve_wh_filter(scope):
    """把 scope(all/group:/wh:/point:) 转成要抓取的仓库 id 集合（None 表示全部）。"""
    if not scope or scope == "all":
        return None
    custom_configs = CUSTOM_SOURCES.to_warehouse_configs()
    all_warehouses = CONFIG.get("warehouses", []) + custom_configs
    if scope.startswith("wh:"):
        wid = scope.split(":", 1)[1]
        return {wid}
    if scope.startswith("point:"):
        wid = scope.split(":", 1)[1].split("::", 1)[0]
        return {wid}
    if scope.startswith("group:"):
        gid = scope.split(":", 1)[1]
        return {w["id"] for w in all_warehouses if w.get("group") == gid}
    return None


def fetch_outbound(start, end, force=False, wh_filter=None):
    wh_key = "all"
    if wh_filter:
        wh_key = "|".join(sorted(wh_filter))
    key = f"outbound:{start or 'default'}:{end or 'default'}:{wh_key}"
    if not force:
        cached = CACHE.get(key)
        if cached:
            return cached

    def _build():
        custom_configs = CUSTOM_SOURCES.to_warehouse_configs()
        all_warehouses = CONFIG.get("warehouses", []) + custom_configs
        if wh_filter:
            all_warehouses = [w for w in all_warehouses if w["id"] in wh_filter]
        if not all_warehouses:
            all_warehouses = CONFIG.get("warehouses", []) + custom_configs
        all_adapters = build_adapters(all_warehouses)
        results = {}
        with ThreadPoolExecutor(max_workers=max(1, len(all_adapters))) as ex:
            futures = []
            for w, a in all_adapters:
                futures.append(ex.submit(fetch_outbound_one, w, a, start, end))
            for f in futures:
                r = f.result()
                results[r["id"]] = r
        groups = list(CONFIG.get("groups", []))
        seen_gids = {g["id"] for g in groups}
        for s in CUSTOM_SOURCES.list_all():
            gid = s.get("group", "custom")
            if gid and gid not in seen_gids:
                groups.append({"id": gid, "name": gid})
                seen_gids.add(gid)
        payload = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "start": start,
            "end": end,
            "groups": groups,
            "warehouses": results,
        }
        CACHE.set(key, payload, ttl_for("outbound"))
        return payload

    return _with_single_flight(key, _build)


@app.route("/api/outbound")
def api_outbound():
    date = request.args.get("date") or None
    start = request.args.get("start") or date or None
    end = request.args.get("end") or date or None
    default_date = None
    if not start and not end:
        default_date = (datetime.now(ZoneInfo(DEFAULT_OUT_TZ)) - timedelta(days=1)).strftime("%Y-%m-%d")
        start = end = default_date
    force = request.args.get("force") == "1"
    scope = request.args.get("scope", "all")
    wh_filter = resolve_wh_filter(scope)
    payload = fetch_outbound(start, end, force, wh_filter=wh_filter)
    payload["requested_date"] = date
    payload["default_date"] = default_date
    payload["default_tz"] = DEFAULT_OUT_TZ if default_date else None
    return jsonify(payload)


def fetch_dated_outbound(start, end, force=False, wh_filter=None):
    """带每日日期分组的出库流水（不聚合）。KIT 套件展开打标。缓存 + 单飞。
    与排行榜共用同一份按仓×月分片的 flow 缓存，各版面数据串联复用。"""
    if not isinstance(start, str):
        start = start.isoformat()
    if not isinstance(end, str):
        end = end.isoformat()
    (s_d, e_d) = (datetime.strptime(start, "%Y-%m-%d").date(),
                  datetime.strptime(end, "%Y-%m-%d").date())
    cust_key = "all"
    if wh_filter:
        cust_key = "|".join(sorted(wh_filter))
    key = f"outbound_dated:{start}:{end}:{cust_key}"
    if not force:
        cached = CACHE.get(key)
        if cached:
            return cached

    def _build():
        custom_configs = CUSTOM_SOURCES.to_warehouse_configs()
        all_warehouses = CONFIG.get("warehouses", []) + custom_configs
        if wh_filter:
            all_warehouses = [w for w in all_warehouses if w["id"] in wh_filter]
        all_adapters = build_adapters(all_warehouses)
        results = {}

        def _run(w, adapter):
            wh_id = w["id"]
            if isinstance(adapter, dict):
                return {"id": wh_id, "name": w.get("name", wh_id), "group": w.get("group", ""),
                        "status": "error", "rows": []}
            try:
                # 复用与排行榜一致的 flow 缓存（按仓×自然月分片），实现数据串联共用
                if getattr(adapter, "FLOW_IS_FULL_HISTORY", False):
                    dated = [r for r in load_flow_full(w, adapter)
                             if start <= str(r.get("date") or "") <= end]
                else:
                    dated = []
                    for ym, ms, me in _months_covering(s_d, e_d):
                        for r in load_flow_month(w, adapter, ym, ms, me):
                            r = dict(r)
                            if start <= str(r.get("date") or "") <= end:
                                dated.append(r)
                if not dated:
                    # 无逐日流水能力的适配器（如自定义源）回退 fetch_outbound 聚合到 start
                    try:
                        points, _, _ = adapter.fetch_outbound(
                            requested_date=start, requested_end=end)
                        dated = []
                        for pt in points or []:
                            for r in pt.get("rows") or []:
                                dated.append(dict(r, date=start))
                    except Exception:
                        dated = []
                # 套件展开打标（带日期）
                kit = {}
                for r in dated:
                    d = r.get("date") or start
                    if r.get("sku"):
                        kit.setdefault(d, []).append({"sku": r["sku"], "name": r.get("name") or "",
                                                      "qty": r.get("qty") or 0})
                applied = []
                for d in sorted(kit.keys()):
                    for r in KIT.apply(kit[d]):
                        r = dict(r, date=d)
                        applied.append(r)
                return {"id": wh_id, "name": w.get("name", wh_id), "group": w.get("group", ""),
                        "account": w.get("account", ""), "status": "ok", "wh_codes": {},
                        "rows": applied}
            except Exception as e:
                return {"id": wh_id, "name": w.get("name", wh_id), "group": w.get("group", ""),
                        "status": "error", "error": f"{type(e).__name__}: {e}", "rows": []}

        with ThreadPoolExecutor(max_workers=max(1, len(all_adapters))) as ex:
            futures = [ex.submit(_run, w, a) for w, a in all_adapters]
            for f in futures:
                r = f.result()
                results[r["id"]] = r
        payload = {"start": start, "end": end, "warehouses": results}
        CACHE.set(key, payload, ttl_for("outbound"))
        return payload

    return _with_single_flight(key, _build)


def daily_outbound(start, end, wh_filter=None):
    """带每日日期的出库流水（不聚合），按日期排序；KIT 套件展开打标。"""
    cust_key = "all"
    if wh_filter:
        cust_key = "|".join(sorted(wh_filter))
    key = f"outbound_daily:{start}:{end}:{cust_key}"
    cached = CACHE.get(key)
    if cached is not None:
        return cached
    payload = fetch_dated_outbound(start, end, wh_filter=wh_filter)
    CACHE.set(key, payload, ttl_for("outbound"))
    return payload


@app.route("/api/outbound/daily")
def api_outbound_daily():
    date = request.args.get("date") or None
    start = request.args.get("start") or date or None
    end = request.args.get("end") or date or None
    if not start:
        start = end = (datetime.now(ZoneInfo(DEFAULT_OUT_TZ)) - timedelta(days=1)).strftime("%Y-%m-%d")
    scope = request.args.get("scope", "all")
    wh_filter = resolve_wh_filter(scope)
    payload = daily_outbound(start, end, wh_filter=wh_filter)
    return jsonify(payload)



@app.route("/api/stats")
def api_stats():
    source = request.args.get("source", "inv")
    if source not in ("inv", "out"):
        return jsonify({"error": "source 必须为 inv（库存）或 out（出库）"}), 400
    scope = request.args.get("scope", "all")
    category = request.args.get("category", "").strip()
    if category not in ("", "kit", "part", "standalone"):
        return jsonify({"error": "category 必须为 kit / part / standalone"}), 400
    force = request.args.get("force") == "1"

    if source == "inv":
        payload = fetch_all("inventory", force=force)
    else:
        start = request.args.get("start") or request.args.get("date") or None
        end = request.args.get("end") or start or None
        if not start:
            start = end = (datetime.now(ZoneInfo(DEFAULT_OUT_TZ)) - timedelta(days=1)).strftime("%Y-%m-%d")
        wh_filter = resolve_wh_filter(scope)
        payload = fetch_outbound(start, end, force=force, wh_filter=wh_filter)

    units = []
    for wh_id, w in payload.get("warehouses", {}).items():
        if w.get("status") != "ok":
            continue
        for p in w.get("points") or []:
            units.append({
                "wh_id": wh_id,
                "wh_name": w.get("name", wh_id),
                "group": w.get("group", ""),
                "point_id": p.get("id", ""),
                "point_name": p.get("name", ""),
                "rows": p.get("rows") or [],
            })

    scope_type = "all"
    scope_id = None
    if scope == "all":
        pass
    elif scope.startswith("group:"):
        scope_type, scope_id = "group", scope.split(":", 1)[1]
        units = [u for u in units if u["group"] == scope_id]
    elif scope.startswith("wh:"):
        scope_type, scope_id = "warehouse", scope.split(":", 1)[1]
        units = [u for u in units if u["wh_id"] == scope_id]
    elif scope.startswith("point:"):
        scope_type, scope_id = "point", scope.split(":", 1)[1]
        units = [u for u in units if f"{u['wh_id']}::{u['point_id']}" == scope_id]
    else:
        return jsonify({"error": "scope 参数无效"}), 400

    scope_label = "全部仓库"
    if scope_type == "group":
        scope_label = next((g.get("name", g.get("id", scope_id))
                            for g in CONFIG.get("groups", []) if g.get("id") == scope_id), scope_id)
    elif scope_type == "warehouse":
        scope_label = next((w.get("name", w.get("id", scope_id))
                            for w in CONFIG.get("warehouses", []) if w.get("id") == scope_id), scope_id)
    elif scope_type == "point":
        if units:
            scope_label = units[0]["point_name"]
        elif "::" in (scope_id or ""):
            scope_label = scope_id.split("::", 1)[1]
        else:
            scope_label = scope_id

    cats = {
        "kit": {"sku_count": 0, "qty": 0, "container_count": 0},
        "part": {"sku_count": 0, "qty": 0, "container_count": 0},
        "standalone": {"sku_count": 0, "qty": 0, "container_count": 0},
        "zero_kit": {"sku_count": 0, "container_count": 0},
    }
    sku_sets = {"kit": set(), "part": set(), "standalone": set(), "zero_kit": set()}
    ctn_sets = {"kit": set(), "part": set(), "standalone": set(), "zero_kit": set()}
    zk_names = {}
    items = []

    # 箱数口径：成套 = 套数 × 该组合子SKU数；不成套/非组合 = 按SKU件数，一件一箱
    kit_comp = {p["sku"]: len(p["components"] or []) for p in KIT.list()}

    for u in units:
        ckey = f"{u['wh_id']}::{u['point_id']}"
        for r in u["rows"]:
            sku = r.get("sku")
            if not sku:
                continue
            qty = r.get("qty") or 0
            try:
                qty = int(qty)
            except (TypeError, ValueError):
                qty = 0
            tag = r.get("tag")
            if tag == "kit":
                cat = "kit" if qty > 0 else "zero_kit"
            elif tag == "part":
                cat = "part"
            else:
                cat = "standalone"
            box = qty * max(1, kit_comp.get(sku, 1)) if cat == "kit" else qty
            sku_sets[cat].add(sku)
            ctn_sets[cat].add(ckey)
            if cat == "zero_kit":
                if sku not in zk_names:
                    zk_names[sku] = r.get("name") or ""
                continue
            items.append({
                "container": u["point_name"],
                "container_id": u["point_id"],
                "warehouse": u["wh_name"],
                "warehouse_id": u["wh_id"],
                "sku": sku,
                "name": r.get("name") or "",
                "category": cat,
                "qty": qty,
                "box": box,
                "kit": r.get("kit") or "",
            })

    for cat, s in sku_sets.items():
        cats[cat]["sku_count"] = len(s)
    for cat in cats:
        cats[cat]["container_count"] = len(ctn_sets[cat])
    cats["kit"]["qty"] = sum(i["qty"] for i in items if i["category"] == "kit")
    cats["part"]["qty"] = sum(i["qty"] for i in items if i["category"] == "part")
    cats["standalone"]["qty"] = sum(i["qty"] for i in items if i["category"] == "standalone")

    boxes = {"kit": 0, "part": 0, "standalone": 0, "total": 0}
    for i in items:
        boxes[i["category"]] += i["box"]
    boxes["total"] = boxes["kit"] + boxes["part"] + boxes["standalone"]

    if category:
        items = [i for i in items if i["category"] == category]

    items.sort(key=lambda i: (i["container"], i["sku"], i["name"]))
    return jsonify({
        "source": source,
        "generated_at": payload.get("generated_at", ""),
        "scope": {"type": scope_type, "id": scope_id, "label": scope_label},
        "categories": cats,
        "boxes": boxes,
        "zero_kits": sorted([{"sku": s, "name": n} for s, n in zk_names.items()],
                            key=lambda x: x["sku"]),
        "items": items,
    })


def fetch_outbound_one(w, adapter, start, end):
    wh_id = w["id"]
    tz = w.get("timezone", "UTC")
    if isinstance(adapter, dict):
        return {"id": wh_id, "name": w.get("name", wh_id), "group": w.get("group", ""),
                "status": "error", "error": adapter["error"]}
    try:
        points, fetched, date_used = adapter.fetch_outbound(
            requested_date=start, requested_end=end)
        points = [dict(p, rows=KIT.apply(p.get("rows") or [])) for p in points]
        return {"id": wh_id, "name": w.get("name", wh_id), "group": w.get("group", ""),
                "account": w.get("account", ""),
                "status": "ok", "error": None, "fetched_at": fetched,
                "date_used": date_used, "points": points}
    except Exception as e:
        return {"id": wh_id, "name": w.get("name", wh_id), "group": w.get("group", ""),
                "account": w.get("account", ""),
                "status": "error", "error": f"{type(e).__name__}: {e}"}


RANK_MODES = {"7d", "30d", "mtd", "lastm", "6m", "1y"}


def rank_ranges(mode, today):
    """返回 (本期开始, 本期结束, 上期开始, 上期结束)。"""
    if mode == "7d":
        return (today - timedelta(days=6), today,
                today - timedelta(days=13), today - timedelta(days=7))
    if mode == "30d":
        return (today - timedelta(days=29), today,
                today - timedelta(days=59), today - timedelta(days=30))
    if mode == "mtd":
        cs = today.replace(day=1)
        n = (today - cs).days + 1
        return (cs, today, cs - timedelta(days=n), cs - timedelta(days=1))
    if mode == "lastm":
        last_prev = today.replace(day=1) - timedelta(days=1)
        cs = last_prev.replace(day=1)
        return (cs, last_prev, (cs - timedelta(days=1)).replace(day=1), cs - timedelta(days=1))
    if mode == "6m":
        return (today - timedelta(days=179), today,
                today - timedelta(days=359), today - timedelta(days=180))
    if mode == "1y":
        return (today - timedelta(days=364), today,
                today - timedelta(days=729), today - timedelta(days=365))
    raise ValueError("无效的排行模式")


RANK_FLOW_TTL = int(SERVER.get("cache_ttl_rank_flow", 600))
RANK_MAX_DAYS = int(SERVER.get("rank_max_days", 800))
RANK_FLOW_WH_TIMEOUT = int(SERVER.get("rank_flow_wh_timeout", 300))

_flow_locks = {}
_flow_locks_guard = threading.Lock()


def _flow_lock(key):
    with _flow_locks_guard:
        if key not in _flow_locks:
            _flow_locks[key] = threading.Lock()
        return _flow_locks[key]


def month_span(d_from, d_to):
    """返回 [(YM, 月首, 月末)] 覆盖 [d_from, d_to]，取整月便于缓存复用。
    当前实现按仓整段拉取，本函数暂保留备用。"""
    months = []
    cur = d_from.replace(day=1)
    while cur <= d_to:
        m_end = (cur.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        months.append((cur.strftime("%Y-%m"), cur, m_end))
        cur = m_end + timedelta(days=1)
    return months


def load_flow_full(w, adapter, force=False):
    """FLOW_IS_FULL_HISTORY 适配器：整窗口原始流水一次拉取并缓存。"""
    key = f"flow:{w['id']}:full"
    if not force:
        cached = CACHE.get(key)
        if cached is not None:
            return cached
    with _flow_lock(key):
        if not force:
            cached = CACHE.get(key)
            if cached is not None:
                return cached
        today = datetime.now(ZoneInfo(DEFAULT_OUT_TZ)).date()
        wide_start = (today - timedelta(days=RANK_MAX_DAYS)).isoformat()
        try:
            rows = adapter.fetch_outbound_dated(wide_start, today.isoformat())
        except Exception:
            rows = None
        if not rows:
            rows = []
        CACHE.set(key, rows, ttl=RANK_FLOW_TTL)
        return rows


def load_flow_range(w, adapter, s, e):
    """某仓某日期区间原始出库流水（按精确区间缓存）。
    FLOW_IS_FULL_HISTORY 适配器复用整窗口缓存后本地过滤。"""
    key = f"flow:{w['id']}:{s.isoformat()}:{e.isoformat()}"
    cached = CACHE.get(key)
    if cached is not None:
        return cached
    with _flow_lock(key):
        cached = CACHE.get(key)
        if cached is not None:
            return cached
        try:
            if getattr(adapter, "FLOW_IS_FULL_HISTORY", False):
                rows = [r for r in load_flow_full(w, adapter)
                        if s.isoformat() <= str(r.get("date") or "") <= e.isoformat()]
            else:
                rows = adapter.fetch_outbound_dated(s.isoformat(), e.isoformat())
        except Exception:
            rows = None
        if not rows:
            rows = []
        CACHE.set(key, rows, ttl=RANK_FLOW_TTL)
        return rows


def _months_covering(s, e):
    """覆盖 [s,e] 的日历月列表 [(YM, 月首, 月末)]。"""
    out = []
    cur = s.replace(day=1)
    while cur <= e:
        m_end = (cur.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        out.append((cur.strftime("%Y-%m"), cur, m_end))
        cur = m_end + timedelta(days=1)
    return out


def load_flow_month(w, adapter, ym, ms, me, force=False):
    """某仓某自然月的原始出库流水，按 (仓, 月) 缓存复用。
    近7天/近一月/当月/上月/半年/一年等区间会命中同一批月份缓存，
    避免每个区间各自整段重拉导致排行榜加载极慢甚至超时。
    force=True 时跳过缓存重新拉取（排行榜"刷新"按钮）。"""
    key = f"flow:{w['id']}:m:{ym}"
    if not force:
        cached = CACHE.get(key)
        if cached is not None:
            return cached
    with _flow_lock(key):
        if not force:
            cached = CACHE.get(key)
            if cached is not None:
                return cached
        try:
            rows = adapter.fetch_outbound_dated(ms.isoformat(), me.isoformat())
        except Exception:
            rows = None
        if not rows:
            rows = []
        CACHE.set(key, rows, ttl=RANK_FLOW_TTL)
        return rows


def collect_flow(s, e, force=False):
    """并行拉取 [s,e] 各仓原始流水（按自然月缓存），返回 (范围内行, 错误列表)。
    全历史适配器整段一次拉取复用，其余按 (仓, 月) 分片缓存。"""
    rows = []
    errors = []
    all_adapters = build_adapters(CONFIG.get("warehouses", []) +
                                  CUSTOM_SOURCES.to_warehouse_configs())
    months = _months_covering(s, e)
    lo = s.isoformat()
    hi = e.isoformat()

    def _full_rows(w, adapter):
        return [r for r in load_flow_full(w, adapter, force=force)
                if lo <= str(r.get("date") or "") <= hi]

    tasks = []
    for w, adapter in all_adapters:
        if getattr(adapter, "FLOW_IS_FULL_HISTORY", False):
            tasks.append((w, lambda ww=w, aa=adapter: _full_rows(ww, aa),
                          RANK_FLOW_WH_TIMEOUT * 3))
        else:
            for ym, ms, me in months:
                tasks.append((w, lambda ww=w, aa=adapter, yy=ym, ms_=ms, me_=me:
                              load_flow_month(ww, aa, yy, ms_, me_, force),
                              RANK_FLOW_WH_TIMEOUT))
    ex = ThreadPoolExecutor(max_workers=16)
    futs = {ex.submit(task): w for w, task, _tmo in tasks}
    timeouts = {f: tmo for f, (w, task, tmo) in zip(futs, tasks)}
    try:
        for fut, w in futs.items():
            try:
                rows.extend(fut.result(timeout=timeouts.get(fut, RANK_FLOW_WH_TIMEOUT)))
            except Exception as exc:
                errors.append("%s: %s" % (w.get("name", w["id"]),
                                          type(exc).__name__))
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return [r for r in rows if lo <= str(r.get("date") or "") <= hi], errors


def _rank_aggregate_rows(rows):
    """对带日期原始流水行做套件展开并汇总为 per-sku {sku, name, type, qty}。
    组合按成套套数、非组合按件(箱)数，不成套子件不参与排行。"""
    by_wh = {}
    for r in rows:
        wh = str(r.get("wh") or "") or "_"
        by_wh.setdefault(wh, []).append(r)
    agg = {}
    for wh, wrows in by_wh.items():
        for kr in KIT.apply(wrows):
            tag = kr.get("tag")
            if tag == "part":
                continue
            sku = str(kr.get("sku") or "").strip()
            if not sku:
                continue
            try:
                qty = int(kr.get("qty") or 0)
            except (TypeError, ValueError):
                qty = 0
            if qty <= 0:
                continue
            entry = agg.get(sku)
            if entry is None:
                entry = agg[sku] = {"sku": sku, "name": str(kr.get("name") or ""),
                                    "type": "combo" if tag == "kit" else "standalone",
                                    "qty": 0}
            entry["qty"] += qty
            if kr.get("name"):
                entry["name"] = str(kr["name"])
    return agg


@app.route("/api/tags")
def api_tags():
    return jsonify({"tags": product_tags.load()})


@app.route("/api/tags", methods=["POST"])
def api_tag_set():
    data = request.get_json(silent=True) or {}
    sku = str(data.get("sku") or "").strip()
    label = str(data.get("label") or "清仓").strip()
    if not sku:
        return jsonify({"error": "缺少产品SKU"}), 400
    tags = product_tags.set_tag(sku, label)
    return jsonify({"ok": True, "tags": tags})


@app.route("/api/tags/<sku>", methods=["DELETE"])
def api_tag_delete(sku):
    tags = product_tags.remove(sku)
    return jsonify({"ok": True, "tags": tags})


@app.route("/api/rank")
def api_rank():
    mode = request.args.get("mode", "").strip()
    start_s = (request.args.get("start") or "").strip()
    end_s = (request.args.get("end") or "").strip()
    force = request.args.get("force") == "1"
    exclude_tag_arg = (request.args.get("exclude_tags") or "").strip()
    exclude_tag_set = {t.strip() for t in exclude_tag_arg.split(",") if t.strip()} if exclude_tag_arg else set()
    today = datetime.now(ZoneInfo(DEFAULT_OUT_TZ)).date()

    if mode and mode in RANK_MODES:
        cs, ce, ps, pe = rank_ranges(mode, today)
    elif start_s and end_s:
        try:
            cs = datetime.strptime(start_s, "%Y-%m-%d").date()
            ce = datetime.strptime(end_s, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "日期格式无效，应为 YYYY-MM-DD"}), 400
        if cs > ce:
            return jsonify({"error": "开始日期不能晚于结束日期"}), 400
        days = (ce - cs).days + 1
        if days > RANK_MAX_DAYS:
            return jsonify({"error": f"区间不能超过 {RANK_MAX_DAYS} 天"}), 400
        ps = cs - timedelta(days=days)
        pe = cs - timedelta(days=1)
        mode = "custom"
    else:
        return jsonify({"error": "缺少 mode 或 start/end"}), 400

    combined_start = min(cs, ps)
    combined_end = max(ce, pe)
    rows, errs = collect_flow(combined_start, combined_end, force=force)
    lo = cs.isoformat()
    hi = ce.isoformat()
    cur_rows = [r for r in rows if lo <= str(r.get("date") or "") <= hi]
    lo = ps.isoformat()
    hi = pe.isoformat()
    prev_rows = [r for r in rows if lo <= str(r.get("date") or "") <= hi]

    cur = _rank_aggregate_rows(cur_rows)
    prev = _rank_aggregate_rows(prev_rows)
    tags = product_tags.load()
    if exclude_tag_set:
        cur = {k: v for k, v in cur.items() if tags.get(k, "") not in exclude_tag_set}
        prev = {k: v for k, v in prev.items() if tags.get(k, "") not in exclude_tag_set}

    def unit(entry):
        return "套" if entry["type"] == "combo" else "箱"

    top = sorted(cur.values(), key=lambda e: (-e["qty"], e["sku"]))
    volume = [{"rank": i + 1, "sku": e["sku"], "name": e["name"], "type": e["type"],
               "unit": unit(e), "qty": e["qty"], "tag": tags.get(e["sku"], "")}
              for i, e in enumerate(top)]

    growth_items = []
    for sku, e in cur.items():
        p = prev.get(sku)
        if not p or p["qty"] <= 0 or e["qty"] <= 0:
            continue
        growth_items.append((sku, e, (e["qty"] - p["qty"]) / p["qty"] * 100))
    growth_items.sort(key=lambda x: (-x[2], x[0]))
    growth = [{"rank": i + 1, "sku": sku, "name": e["name"], "type": e["type"],
               "unit": unit(e), "cur": e["qty"], "prev": prev[sku]["qty"],
               "growth": round(g, 2), "tag": tags.get(sku, "")}
              for i, (sku, e, g) in enumerate(growth_items)]

    v_tot = {"combo": 0, "standalone": 0}
    for e in top:
        v_tot[e["type"]] += e["qty"]
    g_cur = {"combo": 0, "standalone": 0}
    g_prev = {"combo": 0, "standalone": 0}
    for sku, e, _g in growth_items:
        g_cur[e["type"]] += e["qty"]
        g_prev[e["type"]] += prev[sku]["qty"]

    warnings = sorted(set(errs))
    return jsonify({
        "mode": mode,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "range": {"start": cs.isoformat(), "end": ce.isoformat()},
        "prev_range": {"start": ps.isoformat(), "end": pe.isoformat()},
        "total_products": len(cur),
        "growth_products": len(growth),
        "volume": volume,
        "growth": growth,
        "volume_totals": v_tot,
        "growth_totals": {"cur": g_cur, "prev": g_prev},
        "tags": tags,
        "warnings": warnings[:20],
    })


@app.route("/api/products")
def api_products():
    return jsonify({"products": KIT.list()})


@app.route("/api/products", methods=["POST"])
def api_product_add():
    data = request.get_json(silent=True) or {}
    sku = str(data.get("sku") or "").strip()
    name = str(data.get("name") or "").strip()
    comps = [str(c).strip() for c in (data.get("components") or []) if str(c).strip()]
    ptype = str(data.get("type") or "combo").strip()
    if not sku:
        return jsonify({"error": "缺少产品SKU"}), 400
    if ptype == "standalone":
        KIT.upsert(sku, name, [])
    elif comps:
        KIT.upsert(sku, name, comps)
    else:
        return jsonify({"error": "组合产品缺少子SKU"}), 400
    CACHE.invalidate()
    return jsonify({"ok": True, "products": KIT.list()})


@app.route("/api/products/<sku>", methods=["DELETE"])
def api_product_delete(sku):
    KIT.remove(sku)
    CACHE.invalidate()
    return jsonify({"ok": True, "products": KIT.list()})


@app.route("/api/products/import", methods=["POST"])
def api_products_import():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "未上传文件"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".xlsx", ".xls", ".csv"):
        return jsonify({"error": "仅支持 xlsx / xls / csv 文件"}), 400
    path = os.path.join(BASE_DIR, "_upload_tmp" + ext)
    f.save(path)
    try:
        count, skipped = import_kit_excel(path, KIT)
    except Exception as e:
        return jsonify({"error": f"导入失败: {e}"}), 400
    finally:
        if os.path.exists(path):
            os.remove(path)
    CACHE.invalidate()
    return jsonify({"ok": True, "count": count, "skipped": skipped, "products": KIT.list()})


@app.route("/api/products/import-standalone", methods=["POST"])
def api_products_import_standalone():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "未上传文件"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".xlsx", ".xls", ".csv"):
        return jsonify({"error": "仅支持 xlsx / xls / csv 文件"}), 400
    path = os.path.join(BASE_DIR, "_upload_tmp" + ext)
    f.save(path)
    try:
        count, skipped = import_standalone_excel(path, KIT)
    except Exception as e:
        return jsonify({"error": f"导入失败: {e}"}), 400
    finally:
        if os.path.exists(path):
            os.remove(path)
    CACHE.invalidate()
    return jsonify({"ok": True, "count": count, "skipped": skipped, "products": KIT.list()})


@app.route("/api/transit", methods=["GET"])
def api_transit_list():
    learned = transit.learn_voyage_days(TRANSIT.list())
    records = []
    for rec in TRANSIT.list():
        rec = dict(rec)
        transit.compute_eta(rec, learned)
        eta = rec.get("eta_est")
        rec["days_left"] = None
        computed = "无ETA"
        if eta:
            try:
                d = datetime.strptime(eta, "%Y-%m-%d").date()
                rec["days_left"] = (d - date.today()).days
                if d < date.today():
                    computed = "已到港"
                elif rec["days_left"] <= 3:
                    computed = "即将到港"
                else:
                    computed = "在途"
            except ValueError:
                computed = "无ETA"
        rec["status"] = rec.get("manual_status") or computed
        records.append(rec)
    records.sort(key=lambda r: (r.get("eta_est") or "9999-12-31"))
    return jsonify({"ok": True, "records": records, "count": len(records), "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})


@app.route("/api/transit/summary")
def api_transit_summary():
    """在途 SKU 汇总：按 SKU 聚合在途量（组合/子件/非组合），附带 ETA 时间轴、目的港分布、工厂分布。"""
    records = TRANSIT.list()
    today = date.today()

    def _is_arrived(rec):
        eta = rec.get("eta_est")
        if not eta:
            return rec.get("manual_status") == "已到港"
        try:
            d = datetime.strptime(eta, "%Y-%m-%d").date()
        except ValueError:
            return False
        status = rec.get("manual_status") or ("已到港" if d < today else ("即将到港" if (d - today).days <= 3 else "在途"))
        return status == "已到港"

    for _rec in records:
        rec_lines = _rec.get("lines") or []
        if rec_lines and all(("type" in (l or {})) for l in rec_lines):
            continue
        _tag_lines_product_type(rec_lines)

    # SKU 维度聚合
    sku_rows = {}          # sku -> {"sku","name","type","qty","containers":set,"eta_min","pods":set,"lines":[labels]}
    combo_comp_qty = {}    # combo_sku -> {comp_sku: qty}
    combo_need = {}        # combo_sku -> [comp_skus]
    timeline = {"7天": {"containers": 0, "qty": 0}, "14天": {"containers": 0, "qty": 0},
                "30天": {"containers": 0, "qty": 0}, "超30天": {"containers": 0, "qty": 0}}
    pod_cnt = {}
    fac_cnt = {}
    total_qty = 0
    total_containers = 0

    for rec in records:
        cno = rec.get("container_no") or "无柜号"
        pod = rec.get("pod") or ""
        factory = rec.get("factory") or ""
        eta = rec.get("eta_est") or ""
        if pod:
            pod_cnt[pod] = pod_cnt.get(pod, 0) + 1
        if factory:
            fac_cnt[factory] = fac_cnt.get(factory, 0) + 1
        # ETA 时间轴：只统计未到港柜
        if not _is_arrived(rec) and eta:
            try:
                dl = (datetime.strptime(eta, "%Y-%m-%d").date() - today).days
            except ValueError:
                dl = None
            if dl is not None:
                bucket = "7天" if dl <= 7 else ("14天" if dl <= 14 else ("30天" if dl <= 30 else "超30天"))
                timeline[bucket]["containers"] += 1
        if _is_arrived(rec):
            continue
        total_containers += 1
        for ln in (rec.get("lines") or []):
            sku = ln.get("sku") or ""
            name = ln.get("name") or ""
            qty = ln.get("qty") or 0
            try:
                qty = float(qty)
            except (TypeError, ValueError):
                qty = 0
            if not qty and not sku:
                continue
            ltype = ln.get("type") or "standalone"
            total_qty += qty
            row = sku_rows.setdefault(sku or "__name__", {
                "sku": sku, "name": name, "type": ltype, "qty": 0,
                "containers": set(), "eta_min": "", "pods": set(), "combo_sku": ln.get("combo_sku") or ""})
            row["qty"] += qty
            row["containers"].add(cno)
            if pod:
                row["pods"].add(pod)
            if not row["eta_min"] or (eta and eta < row["eta_min"]):
                row["eta_min"] = eta
            if ltype == "combo":
                pass
            elif ltype == "component":
                cparent = ln.get("combo_sku") or ""
                combo_comp_qty.setdefault(cparent, {}).setdefault(sku, 0)
                combo_comp_qty[cparent][sku] += qty

    # 组合成套数：每套 = 同数量的一组子件，直接用产品库 components 定义
    combosets = {}
    for combo, comp_map in combo_comp_qty.items():
        comp_defs = None
        for p in KIT.list():
            if p.get("sku") == combo and p.get("type") == "combo":
                comp_defs = p.get("components") or []
                break
        need = comp_defs or list(comp_map.keys())
        if not need:
            continue
        min_qty = None
        for cs in need:
            have = comp_map.get(cs, 0)
            if min_qty is None or have < min_qty:
                min_qty = have
        if min_qty and min_qty > 0:
            combosets[combo] = min_qty

    by_sku = []
    for k, r in sku_rows.items():
        by_sku.append({
            "sku": r["sku"], "name": r["name"], "type": r["type"],
            "qty": r["qty"], "containers": len(r["containers"]),
            "cno_list": sorted(r["containers"])[:8],
            "eta_min": r["eta_min"], "pods": sorted(r["pods"])[:4],
            "combo_sku": r["combo_sku"],
        })
    by_sku.sort(key=lambda x: (-x["qty"], x["sku"]))
    return jsonify({
        "ok": True,
        "summary": {
            "containers": total_containers,
            "qty": total_qty,
            "combosets": combosets,
            "timeline": timeline,
        },
        "by_sku": by_sku,
        "pod_dist": sorted(pod_cnt.items(), key=lambda x: -x[1]),
        "fac_dist": sorted(fac_cnt.items(), key=lambda x: -x[1]),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


@app.route("/api/transit/import-packing", methods=["POST"])
def api_transit_import_packing():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "未上传文件"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".xlsx", ".xls", ".csv"):
        return jsonify({"error": "装箱单仅支持 xlsx / xls / csv 文件"}), 400
    path = os.path.join(BASE_DIR, "_transit_tmp" + ext)
    f.save(path)
    try:
        parsed_records, warnings = transit.parse_packing_excel(path)
    except Exception as e:
        return jsonify({"error": f"装箱单解析失败: {e}"}), 400
    finally:
        if os.path.exists(path):
            os.remove(path)
    added = 0
    updated = 0
    for pr in parsed_records:
        _, tag_warns = _tag_lines_product_type(pr.get("lines", []))
        warnings.extend(tag_warns)
        rec = transit.compute_eta(pr)
        TRANSIT.normalize(rec)
        _, action = TRANSIT.upsert(rec)
        if action == "added":
            added += 1
        else:
            updated += 1
    TRANSIT.save()
    return jsonify({"ok": True, "added": added, "updated": updated, "warnings": warnings, "records": TRANSIT.list()})


@app.route("/api/transit/import-so", methods=["POST"])
def api_transit_import_so():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "未上传文件"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext != ".pdf":
        return jsonify({"error": "SO 订舱书仅支持 PDF 文件"}), 400
    path = os.path.join(BASE_DIR, "_transit_tmp" + ext)
    f.save(path)
    try:
        parsed, warnings = transit.parse_so_pdf(path)
    except Exception as e:
        return jsonify({"error": f"SO 解析失败: {e}"}), 400
    finally:
        if os.path.exists(path):
            os.remove(path)
    if not parsed:
        return jsonify({"ok": True, "added": 0, "updated": 0, "matched": 0, "warnings": warnings, "records": TRANSIT.list()})
    added = 0
    updated = 0
    matched = 0
    containers = parsed.get("containers") or []
    if not containers:
        containers = [""]
    so_no = parsed.get("so", "")
    for cno in containers:
        rec = {
            "container_no": cno,
            "so": so_no,
            "vessel": parsed.get("vessel", ""),
            "voyage": parsed.get("voyage", ""),
            "pol": parsed.get("pol", ""),
            "pod": parsed.get("pod", ""),
            "etd": parsed.get("etd", ""),
            "eta_so": parsed.get("eta", ""),
            "shipping_line": parsed.get("shipping_line", ""),
            "lines": [],
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        rec = transit.compute_eta(rec)
        TRANSIT.normalize(rec)
        _, action = TRANSIT.upsert(rec)
        if action == "added":
            added += 1
        else:
            updated += 1
        if cno:
            matched += 1
    TRANSIT.save()
    return jsonify({"ok": True, "added": added, "updated": updated, "matched": matched, "warnings": warnings, "records": TRANSIT.list()})


@app.route("/api/transit/scan-sos", methods=["POST"])
def api_transit_scan_sos():
    """Upload SO PDFs, parse and match to transit records. Skip duplicates."""
    try:
        files = request.files.getlist("files")
        if not files:
            return jsonify({"error": "请选择 SO PDF 文件"}), 400
        so_map = {}
        errors = []
        skipped = []
        for f in files:
            fn = f.filename or ""
            if not fn.lower().endswith(".pdf"):
                skipped.append("%s (非PDF)" % fn)
                continue
            path = os.path.join(BASE_DIR, "_transit_so_tmp_%s.pdf" % os.getpid())
            f.save(path)
            try:
                parsed, warn = transit.parse_so_pdf(path)
                if not parsed:
                    errors.append("%s: %s" % (fn, (warn[0] if warn else "解析失败"))[:50])
                    continue
                so = parsed.get("so", "")
                if so:
                    if so not in so_map:
                        so_map[so] = parsed
                else:
                    errors.append("%s: 未提取到SO号" % fn)
            except Exception as e:
                errors.append("%s: %s" % (fn, str(e)[:40]))
            finally:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass
        data = TRANSIT.list()
        updated = 0
        skipped_dup = []
        matched_count = 0
        for rec in data:
            so = rec.get("so", "")
            if not so:
                continue
            norm = transit._normalize_so(so)
            info = None
            if so in so_map:
                info = so_map[so]
            else:
                for pdf_so, pdf_info in so_map.items():
                    if transit._normalize_so(pdf_so) == norm:
                        info = pdf_info
                        break
            if not info:
                continue
            matched_count += 1
            already_has_vessel = bool(rec.get("vessel"))
            changed = False
            for field in ["vessel", "voyage", "pol", "pod", "etd", "shipping_line"]:
                new_val = info.get(field, "")
                old_val = rec.get(field, "")
                if new_val and not old_val:
                    rec[field] = new_val
                    changed = True
            eta_new = info.get("eta_so", "")
            eta_old = rec.get("eta_so", "")
            if eta_new and not eta_old:
                rec["eta_so"] = eta_new
                changed = True
            if changed:
                transit.compute_eta(rec)
                updated += 1
            elif already_has_vessel:
                skipped_dup.append(so)
        TRANSIT.save()
        CACHE.invalidate()
        return jsonify({
            "ok": True,
            "uploaded": len(files),
            "parsed": len(so_map),
            "matched": matched_count,
            "updated": updated,
            "duplicates": skipped_dup,
            "errors": errors,
            "skipped": skipped,
            "records": TRANSIT.list(),
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": "SO导入异常: %s" % str(e)[:100]}), 500


@app.route("/api/transit/import", methods=["POST"])
def api_transit_import():
    files = request.files.getlist("files")
    manual_cno = str(request.form.get("container_no") or "").strip().upper()
    manual_so = str(request.form.get("so") or "").strip()
    if not files and not manual_cno:
        return jsonify({"error": "请选择文件或填写柜号"}), 400
    added = 0
    updated = 0
    matched = 0
    warnings = []
    errors = []
    for f in files:
        if not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in (".pdf", ".xlsx", ".xls", ".csv"):
            errors.append(f"{f.filename}: 不支持的文件类型 {ext}")
            continue
        path = os.path.join(BASE_DIR, "_transit_tmp" + ext)
        f.save(path)
        try:
            if ext == ".pdf":
                parsed, warns = transit.parse_so_pdf(path)
                warnings.extend(warns)
                if not parsed:
                    continue
                so_no = parsed.get("so", "")
                containers = [c for c in (parsed.get("containers") or []) if c]
                if not so_no and not containers:
                    warnings.append(f"{f.filename}: 未识别到 SO 号或柜号，已跳过")
                    continue
                if not containers:
                    containers = [""]
                for cno in containers:
                    rec = {
                        "container_no": cno,
                        "so": so_no,
                        "vessel": parsed.get("vessel", ""),
                        "voyage": parsed.get("voyage", ""),
                        "pol": parsed.get("pol", ""),
                        "pod": parsed.get("pod", ""),
                        "etd": parsed.get("etd", ""),
                        "eta_so": parsed.get("eta", ""),
                        "shipping_line": parsed.get("shipping_line", ""),
                        "lines": [],
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    rec = transit.compute_eta(rec)
                    TRANSIT.normalize(rec)
                    _, action = TRANSIT.upsert(rec)
                    if action == "added":
                        added += 1
                    else:
                        updated += 1
                    if cno:
                        matched += 1
            else:
                parsed_records, warns = transit.parse_packing_excel(path)
                warnings.extend(warns)
                for pr in parsed_records:
                    _, tag_warns = _tag_lines_product_type(pr.get("lines", []))
                    warnings.extend(tag_warns)
                    rec = transit.compute_eta(pr)
                    TRANSIT.normalize(rec)
                    _, action = TRANSIT.upsert(rec)
                    if action == "added":
                        added += 1
                    else:
                        updated += 1
        except Exception as e:
            errors.append(f"{f.filename}: {e}")
        finally:
            _safe_remove(path)
    if manual_cno:
        rec = {
            "container_no": manual_cno,
            "so": manual_so,
            "vessel": "", "voyage": "", "pol": "", "pod": "",
            "etd": "", "eta_so": "", "shipping_line": "",
            "lines": [],
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        rec = transit.compute_eta(rec)
        TRANSIT.normalize(rec)
        _, action = TRANSIT.upsert(rec)
        if action == "added":
            added += 1
        else:
            updated += 1
    TRANSIT.save()
    resp = {"ok": True, "added": added, "updated": updated, "matched": matched,
            "warnings": warnings, "errors": errors, "records": TRANSIT.list()}
    return jsonify(resp)


@app.route("/api/transit/<rid>", methods=["DELETE"])
def api_transit_delete(rid):
    if TRANSIT.remove(rid):
        TRANSIT.save()
        return jsonify({"ok": True})
    return jsonify({"error": "记录不存在"}), 404


@app.route("/api/transit/<rid>", methods=["PUT"])
def api_transit_update(rid):
    data = request.get_json(silent=True) or {}
    rec = TRANSIT.find(rid)
    if not rec:
        return jsonify({"error": "记录不存在"}), 404
    allowed = ("container_no", "so", "shipping_line", "vessel", "voyage", "pol", "pod", "etd", "loading_date", "eta_so", "eta_est", "manual_status", "actual_sail_date", "actual_arrival_date", "factory")
    changed = False
    for k in allowed:
        if k in data:
            rec[k] = str(data[k])
            changed = True
    if changed:
        TRANSIT.save()
    return jsonify({"ok": True, "record": rec})


@app.route("/api/transit/batch", methods=["POST"])
def api_transit_batch():
    data = request.get_json(silent=True) or {}
    ids = data.get("ids") or []
    action = data.get("action", "")
    if not ids:
        return jsonify({"error": "未选择记录"}), 400
    if action == "delete":
        deleted = 0
        for rid in ids:
            if TRANSIT.remove(rid):
                deleted += 1
        TRANSIT.save()
        return jsonify({"ok": True, "deleted": deleted, "records": TRANSIT.list()})
    elif action == "update_status":
        status = data.get("manual_status", "")
        updated = 0
        for rid in ids:
            rec = TRANSIT.find(rid)
            if rec:
                rec["manual_status"] = status
                updated += 1
        TRANSIT.save()
        return jsonify({"ok": True, "updated": updated, "records": TRANSIT.list()})
    else:
        return jsonify({"error": "未知操作: " + action}), 400


# ================= 自定义数据源 API =================

PRESET_TYPES = {
    "xlwms": {"name": "领星 OMS", "fields": ["app_key", "app_secret"]},
    "lecangs": {"name": "乐歌", "fields": ["app_key", "app_secret"]},
    "yunwms": {"name": "乐舱", "fields": ["app_token", "app_key"]},
    "anmei": {"name": "安美", "fields": ["access_token", "tenant"]},
    "aidelivery": {"name": "安得力", "fields": ["token", "customer_id"]},
}


@app.route("/api/custom_sources", methods=["GET"])
def api_custom_sources_list():
    return jsonify({"sources": CUSTOM_SOURCES.list_all(), "preset_types": PRESET_TYPES})


@app.route("/api/custom_sources", methods=["POST"])
def api_custom_sources_create():
    data = request.get_json(force=True, silent=True) or {}
    if not data.get("name"):
        return jsonify({"error": "名称不能为空"}), 400
    source = CUSTOM_SOURCES.add(data)
    CACHE.invalidate()
    return jsonify({"ok": True, "source": source})


@app.route("/api/custom_sources/<source_id>", methods=["PUT"])
def api_custom_sources_update(source_id):
    data = request.get_json(force=True, silent=True) or {}
    source = CUSTOM_SOURCES.update(source_id, data)
    if not source:
        return jsonify({"error": "数据源不存在"}), 404
    CACHE.invalidate()
    return jsonify({"ok": True, "source": source})


@app.route("/api/custom_sources/<source_id>", methods=["DELETE"])
def api_custom_sources_delete(source_id):
    ok = CUSTOM_SOURCES.delete(source_id)
    if not ok:
        return jsonify({"error": "数据源不存在"}), 404
    CACHE.invalidate()
    return jsonify({"ok": True})


@app.route("/api/custom_sources/<source_id>/toggle", methods=["POST"])
def api_custom_sources_toggle(source_id):
    data = request.get_json(force=True, silent=True) or {}
    enabled = bool(data.get("enabled", True))
    source = CUSTOM_SOURCES.toggle(source_id, enabled)
    if not source:
        return jsonify({"error": "数据源不存在"}), 404
    CACHE.invalidate()
    return jsonify({"ok": True, "source": source})


@app.route("/api/custom_sources/<source_id>/test", methods=["POST"])
def api_custom_sources_test(source_id):
    source = CUSTOM_SOURCES.get(source_id)
    if not source:
        return jsonify({"error": "数据源不存在"}), 404
    try:
        adapter = build_adapter({
            "id": source["id"],
            "name": source.get("name", source["id"]),
            "type": "custom",
            "enabled": True,
            "group": source.get("group", "custom"),
            **source,
        })
        results = adapter.test_connection()
        return jsonify({"ok": True, "results": results})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ================= 分析引擎 API =================

def _fetch_outbound_dated(start_date, end_date):
    """获取指定日期区间的出库数据。"""
    cache_key = f"outbound:{start_date}:{end_date}"
    cached = CACHE.get(cache_key)
    if cached:
        return cached
    custom_configs = CUSTOM_SOURCES.to_warehouse_configs()
    all_warehouses = CONFIG.get("warehouses", []) + custom_configs
    all_adapters = build_adapters(all_warehouses)
    results = {}
    with ThreadPoolExecutor(max_workers=max(1, len(all_adapters))) as ex:
        futures = []
        for w, a in all_adapters:
            futures.append(ex.submit(_fetch_one_dated, w, a, start_date, end_date))
        for f in futures:
            r = f.result()
            if r:
                results[r["id"]] = r
    payload = {"warehouses": results}
    CACHE.set(cache_key, payload, ttl_for("outbound"))
    return payload


def _fetch_one_dated(w, adapter, start_date, end_date):
    wh_id = w["id"]
    if isinstance(adapter, dict):
        return None
    try:
        points, fetched, date_used = adapter.fetch_outbound(
            requested_date=start_date, requested_end=end_date)
        points = [dict(p, rows=KIT.apply(p.get("rows") or [])) for p in points]
        return {
            "id": wh_id, "name": w.get("name", wh_id),
            "group": w.get("group", ""), "account": w.get("account", ""),
            "status": "ok", "points": points, "date_note": date_used,
        }
    except Exception as e:
        return {"id": wh_id, "name": w.get("name", wh_id),
                "status": "error", "error": str(e), "points": []}


@app.route("/api/analytics")
def api_analytics():
    period = int(request.args.get("period", 30))
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=period)
    start_date = start_dt.strftime("%Y-%m-%d")
    end_date = end_dt.strftime("%Y-%m-%d")
    force = request.args.get("force") == "1"

    payload = fetch_dated_outbound(start_date, end_date, force=force)
    sku_daily = defaultdict(lambda: defaultdict(float))
    for w in payload.get("warehouses", {}).values():
        if w.get("status") != "ok":
            continue
        for row in w.get("rows") or []:
            sku = row.get("sku", "")
            if not sku:
                continue
            qty = analytics._safe_float(row.get("qty", 0))
            date_str = str(row.get("date", ""))[:10]
            if not date_str or date_str < start_date or date_str > end_date:
                date_str = start_date
            sku_daily[sku][date_str] += qty

    series_map = {}
    for sku, dates in sku_daily.items():
        series_map[sku] = sorted([{"date": d, "qty": q} for d, q in dates.items()],
                                 key=lambda x: x["date"])

    result = analytics.compute_analytics_from_series(series_map, period_days=period)
    return jsonify(result)


@app.route("/api/analytics/backtest")
def api_analytics_backtest():
    sku = request.args.get("sku", "")
    ma_short = int(request.args.get("ma_short", 5))
    ma_long = int(request.args.get("ma_long", 20))
    capital = int(request.args.get("capital", 100000))
    period = int(request.args.get("period", 30))
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=period)
    start_date = start_dt.strftime("%Y-%m-%d")
    end_date = end_dt.strftime("%Y-%m-%d")
    force = request.args.get("force") == "1"

    payload = fetch_dated_outbound(start_date, end_date, force=force)
    dates_map = defaultdict(float)
    for w in payload.get("warehouses", {}).values():
        if w.get("status") != "ok":
            continue
        for row in w.get("rows") or []:
            if row.get("sku") == sku:
                qty = analytics._safe_float(row.get("qty", 0))
                date_str = str(row.get("date", ""))[:10]
                if not date_str or date_str < start_date or date_str > end_date:
                    date_str = start_date
                dates_map[date_str] += qty

    if not dates_map:
        return jsonify({"error": f"SKU {sku} 无出库数据"}), 404
    series = sorted([{"date": d, "qty": q} for d, q in dates_map.items()],
                    key=lambda x: x["date"])
    result = analytics._backtest(series, ma_short, ma_long, capital)
    result["sku"] = sku
    return jsonify(result)


# ================= 供应链分析 API =================

@app.route("/api/supply_chain")
def api_supply_chain():
    inv_data = fetch_all("inventory")
    out_data = fetch_all("outbound")
    transit_records = TRANSIT.list()
    result = supply_chain.compute_supply_chain_kpis(inv_data, out_data, transit_records)
    return jsonify(result)


@app.route("/api/restocking")
def api_restocking():
    inv_data = fetch_all("inventory")
    out_data = fetch_all("outbound")
    transit_records = TRANSIT.list()
    result = restocking.compute_restock建议(inv_data, out_data, transit_records)
    return jsonify(result)


@app.route("/api/restocking_rules", methods=["GET"])
def api_restocking_rules_get():
    return jsonify(restocking.load_rules())


@app.route("/api/restocking_rules", methods=["POST"])
def api_restocking_rules_save():
    data = request.get_json(force=True, silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "无效数据"}), 400
    restocking.save_rules(data)
    return jsonify({"ok": True, "rules": data})


@app.route("/api/restocking_overview")
def api_restocking_overview():
    inv_data = fetch_all("inventory")
    out_data = fetch_all("outbound")
    transit_records = TRANSIT.list()
    result = restocking.compute_restock建议(inv_data, out_data, transit_records)
    items = result.get("items", [])
    urgent_items = [r for r in items if r["priority"] >= 30][:10]
    need_restock_items = [r for r in items if r["restock_qty"] > 0][:10]
    return jsonify({
        "summary": result.get("summary", {}),
        "cycle_days": result.get("cycle_days", 30),
        "urgent_items": urgent_items,
        "need_restock_items": need_restock_items,
        "timestamp": datetime.now().isoformat(),
    })


@app.route("/api/pricing", methods=["GET"])
def api_pricing_list():
    records = PRICING.list_all()
    zones = pricing.get_all_zones(records)
    wmin, wmax = pricing.get_weight_range(records)
    return jsonify({
        "records": [{"id": r["rid"], "name": r["name"], "file": r.get("file", ""),
                      "uploaded_at": r.get("uploaded_at", ""),
                      "warehouses": r.get("warehouses", []),
                      "summary": r.get("summary", {})}
                     for r in records.values()],
        "zones": zones,
        "weight_range": {"min": wmin, "max": wmax},
    })


@app.route("/api/pricing/<rid>", methods=["GET"])
def api_pricing_detail(rid):
    rec = PRICING.get(rid)
    if not rec:
        return jsonify({"error": "未找到"}), 404
    return jsonify(rec)


@app.route("/api/pricing/upload", methods=["POST"])
def api_pricing_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "请上传文件"}), 400
    name = request.form.get("name", "").strip() or f.filename
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".xlsx", ".xls"):
        return jsonify({"error": "仅支持 .xlsx / .xls 文件"}), 400
    tmp = os.path.join(BASE_DIR, "_pricing_tmp" + ext)
    try:
        f.save(tmp)
        result = pricing.parse_pricing_excel(tmp, name)
        if not result:
            return jsonify({"error": "无法解析报价表格式，请确认表格包含重量段和价格列"}), 400
        record = PRICING.add(result)
        return jsonify({"ok": True, "record": record})
    except Exception as e:
        return jsonify({"error": f"解析失败: {str(e)}"}), 500
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


@app.route("/api/pricing/<rid>", methods=["DELETE"])
def api_pricing_delete(rid):
    if PRICING.delete(rid):
        return jsonify({"ok": True})
    return jsonify({"error": "未找到"}), 404


@app.route("/api/pricing/compare", methods=["GET"])
def api_pricing_compare():
    zone = request.args.get("zone") or "Zone5"
    weight = request.args.get("weight")
    weight = float(weight) if weight else 1.0
    warehouse = request.args.get("warehouse") or None
    fee_type = request.args.get("fee_type") or "total"
    fuel_str = request.args.get("fuel_pct")
    global_fuel_pct = float(fuel_str) / 100.0 if fuel_str else None
    records = PRICING.list_all()
    result = pricing.compare_pricing(records, weight=weight, zone=zone, warehouse=warehouse, fee_type=fee_type, global_fuel_pct=global_fuel_pct)
    return jsonify({"results": result})


@app.route("/api/pricing/calculate", methods=["POST"])
def api_pricing_calculate():
    body = request.get_json(force=True, silent=True) or {}
    shipments = body.get("shipments") or [{"weight": 5, "qty": 1}]
    zone = body.get("zone") or "Zone5"
    fuel_str = body.get("fuel_pct")
    global_fuel_pct = float(fuel_str) / 100.0 if fuel_str else None
    records = PRICING.list_all()
    result = pricing.calculate_batch(records, shipments, zone=zone, global_fuel_pct=global_fuel_pct)
    return jsonify(result)


@app.route("/api/pricing/clear", methods=["POST"])
def api_pricing_clear():
    PRICING.clear()
    return jsonify({"ok": True})


# ── Supplier CRUD (v4 报价比价) ───────────────────────────────────
@app.route("/api/suppliers", methods=["GET"])
def api_suppliers_list():
    return jsonify({"suppliers": SUPPLIERS.list_all()})


@app.route("/api/suppliers", methods=["POST"])
def api_suppliers_create():
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "供应商名称不能为空"}), 400
    import uuid as _uuid
    sid = str(_uuid.uuid4())[:8]
    supplier = {
        "id": sid, "name": name,
        "outbound": [], "carrier": "", "fuel_pct": 0,
        "shipping_zones": {}, "residential": {}, "ahs_weight": {},
    }
    SUPPLIERS.add(supplier)
    return jsonify({"ok": True, "supplier": supplier})


@app.route("/api/suppliers/<sid>", methods=["GET"])
def api_suppliers_get(sid):
    sp = SUPPLIERS.get(sid)
    if not sp:
        return jsonify({"error": "未找到"}), 404
    return jsonify(sp)


@app.route("/api/suppliers/<sid>", methods=["PUT"])
def api_suppliers_update(sid):
    body = request.get_json(force=True, silent=True) or {}
    sp = SUPPLIERS.update(sid, body)
    if not sp:
        return jsonify({"error": "未找到"}), 404
    return jsonify({"ok": True, "supplier": sp})


@app.route("/api/suppliers/<sid>", methods=["DELETE"])
def api_suppliers_delete(sid):
    if SUPPLIERS.delete(sid):
        return jsonify({"ok": True})
    return jsonify({"error": "未找到"}), 404


@app.route("/api/suppliers/bulk-edit", methods=["POST"])
def api_suppliers_bulk_edit():
    """Apply the same change to a field across multiple selected suppliers.

    spec: {
      "ids": [sid, ...],
      "target": "fuel"|"outbound"|"shipping"|"residential"|"ahs",
      "op": "set"|"add"|"mul",
      "value": number,
      "zone": "Zone2",            # for shipping/residential/ahs
      "min_lbs": float,           # for outbound band match
      "max_lbs": float            # for outbound band match
    }
    """
    body = request.get_json(force=True, silent=True) or {}
    ids = body.get("ids") or []
    target = body.get("target")
    op = body.get("op") or "set"
    value = body.get("value")
    zone = body.get("zone") or ""
    min_lbs = body.get("min_lbs")
    max_lbs = body.get("max_lbs")
    if not ids or target not in ("fuel", "outbound", "shipping", "residential", "ahs"):
        return jsonify({"error": "参数无效"}), 400
    if value is None:
        return jsonify({"error": "缺少值"}), 400
    try:
        value = float(value)
    except (TypeError, ValueError):
        return jsonify({"error": "值必须是数字"}), 400
    if op not in ("set", "add", "mul"):
        return jsonify({"error": "操作类型无效"}), 400

    def apply_num(v, op, value):
        if v is None:
            return None
        if op == "set":
            return value
        if op == "add":
            return round((v or 0) + value, 2)
        return round((v or 0) * value, 2)

    updated = 0
    results = []
    for sid in ids:
        sp = SUPPLIERS.get(sid)
        if not sp:
            continue
        changed = False
        if target == "fuel":
            nv = apply_num(sp.get("fuel_pct"), op, value)
            if nv is not None and nv != sp.get("fuel_pct"):
                SUPPLIERS.update(sid, {"fuel_pct": nv}); changed = True
        elif target == "outbound":
            if min_lbs is None:
                continue
            outbound = list(sp.get("outbound", []))
            for t in outbound:
                amatch = (min_lbs is None or float(t.get("min_lbs")) == min_lbs)
                bmatch = (max_lbs is None or float(t.get("max_lbs")) == max_lbs)
                if amatch and (max_lbs is None or bmatch):
                    nv = apply_num(t.get("price"), op, value)
                    if nv is not None:
                        t["price"] = nv; changed = True
            if changed:
                SUPPLIERS.update(sid, {"outbound": outbound})
        elif target == "shipping":
            if not zone:
                continue
            zones = {k: dict(v) for k, v in sp.get("shipping_zones", {}).items()}
            if zone in zones:
                for w in list(zones[zone].keys()):
                    nv = apply_num(zones[zone][w], op, value)
                    if nv is not None:
                        zones[zone][w] = nv; changed = True
                SUPPLIERS.update(sid, {"shipping_zones": zones})
        elif target in ("residential", "ahs"):
            if not zone:
                continue
            data = dict(sp.get(target, {}))
            if zone in data:
                nv = apply_num(data[zone], op, value)
                if nv is not None:
                    data[zone] = nv; changed = True
                    SUPPLIERS.update(sid, {target: data})
        if changed:
            updated += 1
            results.append({"id": sid, "name": sp.get("name")})
    return jsonify({"ok": True, "updated": updated, "results": results})


@app.route("/api/suppliers/clear", methods=["POST"])
def api_suppliers_clear():
    SUPPLIERS.clear()
    return jsonify({"ok": True})


@app.route("/api/suppliers/<sid>/outbound", methods=["POST"])
def api_suppliers_set_outbound(sid):
    sp = SUPPLIERS.get(sid)
    if not sp:
        return jsonify({"error": "未找到"}), 404
    body = request.get_json(force=True, silent=True) or {}
    tiers = body.get("tiers") or []
    SUPPLIERS.update(sid, {"outbound": tiers})
    return jsonify({"ok": True})


@app.route("/api/suppliers/<sid>/outbound/paste", methods=["POST"])
def api_suppliers_paste_outbound(sid):
    sp = SUPPLIERS.get(sid)
    if not sp:
        return jsonify({"error": "未找到"}), 404
    body = request.get_json(force=True, silent=True) or {}
    text = body.get("text") or ""
    tiers = pricing.parse_outbound_paste(text)
    SUPPLIERS.update(sid, {"outbound": tiers})
    return jsonify({"ok": True, "count": len(tiers), "tiers": tiers})


@app.route("/api/suppliers/<sid>/shipping", methods=["POST"])
def api_suppliers_set_shipping(sid):
    sp = SUPPLIERS.get(sid)
    if not sp:
        return jsonify({"error": "未找到"}), 404
    body = request.get_json(force=True, silent=True) or {}
    update = {}
    if "carrier" in body:
        update["carrier"] = body["carrier"]
    if "fuel_pct" in body:
        update["fuel_pct"] = body["fuel_pct"]
    if "zones" in body:
        update["shipping_zones"] = body["zones"]
    SUPPLIERS.update(sid, update)
    return jsonify({"ok": True})


@app.route("/api/suppliers/<sid>/shipping/paste", methods=["POST"])
def api_suppliers_paste_shipping(sid):
    sp = SUPPLIERS.get(sid)
    if not sp:
        return jsonify({"error": "未找到"}), 404
    body = request.get_json(force=True, silent=True) or {}
    text = body.get("text") or ""
    parsed = pricing.parse_shipping_paste(text)
    update = {"shipping_zones": parsed["zones"]}
    if parsed.get("carrier"):
        update["carrier"] = parsed["carrier"]
    if parsed.get("fuel_pct") and parsed["fuel_pct"] > 0:
        update["fuel_pct"] = parsed["fuel_pct"]
    SUPPLIERS.update(sid, update)
    zone_count = len(parsed["zones"])
    weight_count = max((len(v) for v in parsed["zones"].values()), default=0)
    return jsonify({"ok": True, "zones": zone_count, "weights": weight_count})


@app.route("/api/suppliers/<sid>/surcharges", methods=["POST"])
def api_suppliers_set_surcharges(sid):
    sp = SUPPLIERS.get(sid)
    if not sp:
        return jsonify({"error": "未找到"}), 404
    body = request.get_json(force=True, silent=True) or {}
    update = {}
    if "residential" in body:
        update["residential"] = body["residential"]
    if "ahs_weight" in body:
        update["ahs_weight"] = body["ahs_weight"]
    SUPPLIERS.update(sid, update)
    return jsonify({"ok": True})


@app.route("/api/suppliers/<sid>/surcharges/paste", methods=["POST"])
def api_suppliers_paste_surcharges(sid):
    sp = SUPPLIERS.get(sid)
    if not sp:
        return jsonify({"error": "未找到"}), 404
    body = request.get_json(force=True, silent=True) or {}
    text = body.get("text") or ""
    stype = body.get("type") or "residential"
    result = pricing.parse_surcharges_paste(text)
    if stype == "ahs_weight":
        SUPPLIERS.update(sid, {"ahs_weight": result})
    else:
        SUPPLIERS.update(sid, {"residential": result})
    return jsonify({"ok": True, "count": len(result)})


@app.route("/api/suppliers/<sid>/fuel/paste", methods=["POST"])
def api_suppliers_paste_fuel(sid):
    sp = SUPPLIERS.get(sid)
    if not sp:
        return jsonify({"error": "未找到"}), 404
    body = request.get_json(force=True, silent=True) or {}
    text = body.get("text") or ""
    fuel_pct = pricing.parse_fuel_paste(text)
    SUPPLIERS.update(sid, {"fuel_pct": fuel_pct})
    return jsonify({"ok": True, "fuel_pct": fuel_pct})


@app.route("/api/suppliers/<sid>/outbound/item", methods=["POST"])
def api_suppliers_add_outbound_item(sid):
    sp = SUPPLIERS.get(sid)
    if not sp:
        return jsonify({"error": "未找到"}), 404
    body = request.get_json(force=True, silent=True) or {}
    tier = {"min_lbs": body.get("min_lbs", 0), "max_lbs": body.get("max_lbs", 0),
            "price": body.get("price", 0)}
    outbound = list(sp.get("outbound", []))
    idx = body.get("index")
    if idx is not None and 0 <= idx < len(outbound):
        outbound[idx] = tier
    else:
        outbound.append(tier)
    SUPPLIERS.update(sid, {"outbound": outbound})
    return jsonify({"ok": True, "outbound": outbound})


@app.route("/api/suppliers/<sid>/outbound/item/<int:idx>", methods=["DELETE"])
def api_suppliers_del_outbound_item(sid, idx):
    sp = SUPPLIERS.get(sid)
    if not sp:
        return jsonify({"error": "未找到"}), 404
    outbound = list(sp.get("outbound", []))
    if 0 <= idx < len(outbound):
        outbound.pop(idx)
        SUPPLIERS.update(sid, {"outbound": outbound})
    return jsonify({"ok": True, "outbound": outbound})


@app.route("/api/suppliers/<sid>/shipping/weight/<path:weight>", methods=["DELETE"])
def api_suppliers_del_shipping_weight(sid, weight):
    """Delete a weight row across all zones of the shipping table."""
    sp = SUPPLIERS.get(sid)
    if not sp:
        return jsonify({"error": "未找到"}), 404
    zones = sp.get("shipping_zones", {})
    removed = False
    for zn in zones:
        if weight in zones[zn]:
            del zones[zn][weight]
            removed = True
    if removed:
        # drop zones that became empty
        for zn in list(zones.keys()):
            if not zones[zn]:
                del zones[zn]
    SUPPLIERS.update(sid, {"shipping_zones": zones})
    return jsonify({"ok": True, "removed": removed})


@app.route("/api/suppliers/<sid>/surcharges/<stype>/<path:key>", methods=["DELETE"])
def api_suppliers_del_surcharge(sid, stype, key):
    """Delete a single surcharge key (Zone) for residential or ahs_weight."""
    sp = SUPPLIERS.get(sid)
    if not sp:
        return jsonify({"error": "未找到"}), 404
    if stype not in ("residential", "ahs_weight"):
        return jsonify({"error": "无效类型"}), 400
    data = dict(sp.get(stype, {}))
    removed = data.pop(key, None)
    SUPPLIERS.update(sid, {stype: data})
    return jsonify({"ok": True, "removed": removed is not None})


# ── Batch Calculate (v4 — supports both old pricing + new suppliers) ──
@app.route("/api/pricing/calculate_v4", methods=["POST"])
def api_pricing_calculate_v4():
    body = request.get_json(force=True, silent=True) or {}
    shipments = body.get("shipments") or [{"weight": 5, "qty": 1}]
    zone = body.get("zone") or "Zone5"
    fuel_str = body.get("fuel_pct")
    global_fuel_pct = float(fuel_str) / 100.0 if fuel_str else None
    supplier_ids = body.get("supplier_ids")
    all_suppliers = SUPPLIERS.list_all()
    if supplier_ids:
        all_suppliers = {k: v for k, v in all_suppliers.items() if k in supplier_ids}
    records = SUPPLIERS.to_pricing_records()
    result = pricing.calculate_batch(records, shipments, zone=zone, global_fuel_pct=global_fuel_pct)
    return jsonify(result)


# ── GitHub Sync API ─────────────────────────────────────────────
@app.route("/api/github/pull", methods=["POST"])
def api_github_pull():
    try:
        result = github_sync.pull_all()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/github/push", methods=["POST"])
def api_github_push():
    try:
        result = github_sync.push_all()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/github/push-file", methods=["POST"])
def api_github_push_file():
    body = request.get_json(force=True, silent=True) or {}
    path = body.get("path")
    if not path:
        return jsonify({"error": "path required"}), 400
    try:
        result = github_sync.push_file(path)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── 统一价卡存储 /api/pricedata ────────────────────────────────
@app.route("/api/pricedata")
def api_pricedata_overview():
    """返回各 kind 的版本快照（哈希/数量/更新时间）与可选基线对比。"""
    result = {}
    for k in price_data.KINDS:
        result[k] = price_data.current_version(k)
    return jsonify({"kinds": result, "seeds": price_data.seeds_available()})


@app.route("/api/pricedata/<kind>")
def api_pricedata_get(kind):
    if kind not in price_data.KINDS:
        return jsonify({"error": f"unknown kind {kind}"}), 400
    data = price_data.snapshot(kind)
    if kind == "card" and not data:
        # 兼容旧部署：card 为空时从扁平 kinds 自动迁移一次
        n = price_data.rebuild_card_from_flat()
        data = price_data.snapshot("card")
        warn = f"已从扁平数据自动迁移 {n} 个服务商价卡" if n else None
        return jsonify({"kind": kind, "data": data, "migrated": n, "warn": warn})
    return jsonify({"kind": kind, "data": data})


@app.route("/api/pricedata/<kind>", methods=["PUT"])
def api_pricedata_put(kind):
    if kind not in price_data.KINDS:
        return jsonify({"error": f"unknown kind {kind}"}), 400
    body = request.get_json(force=True, silent=True) or {}
    data = body.get("data", body)
    if not isinstance(data, (list, dict)):
        return jsonify({"error": "data 需为数组或对象"}), 400
    price_data.write(kind, data)
    if kind == "card":
        # card 为权威数据源：写入后重建扁平投影，保证账单核对/旧界面一致
        price_data.sync_card_projections()
    return jsonify({"ok": True, **price_data.current_version(kind)})


@app.route("/api/pricedata/<kind>/diff")
def api_pricedata_diff(kind):
    if kind not in price_data.KINDS:
        return jsonify({"error": f"unknown kind {kind}"}), 400
    return jsonify(price_data.diff(kind))


@app.route("/api/pricedata/<kind>/baseline", methods=["POST"])
def api_pricedata_baseline(kind):
    if kind not in price_data.KINDS:
        return jsonify({"error": f"unknown kind {kind}"}), 400
    return jsonify(price_data.set_baseline(kind))


@app.route("/api/pricedata/seed", methods=["POST"])
def api_pricedata_seed():
    body = request.get_json(force=True, silent=True) or {}
    overwrite = bool(body.get("overwrite", True))
    result = price_data.seed_from_files(overwrite=overwrite)
    return jsonify({"ok": True, "result": result})


@app.route("/api/pricedata/<kind>/append", methods=["POST"])
def api_pricedata_append(kind):
    if kind not in price_data.KINDS:
        return jsonify({"error": f"unknown kind {kind}"}), 400
    body = request.get_json(force=True, silent=True) or {}
    item = body.get("data", body)
    try:
        price_data.append(kind, item)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, **price_data.current_version(kind)})


# ── 邮编→Zone 引擎 /api/zonemap ───────────────────────────────
@app.route("/api/zonemap/stats")
def api_zonemap_stats():
    return jsonify(zonemap.stats())


@app.route("/api/zonemap/lookup")
def api_zonemap_lookup():
    zip5 = request.args.get("zip", "")
    warehouse = request.args.get("warehouse") or None
    provider = request.args.get("provider") or None
    if not zip5:
        return jsonify({"error": "zip required"}), 400
    zone = zonemap.lookup(zip5, warehouse, [provider] if provider else None)
    return jsonify({"zip": zip5, "warehouse": warehouse, "provider": provider,
                    "zone": zone, "found": zone is not None})


# ── 正式价格目录批量入库 ───────────────────────────────────────
OFFICIAL_PRICING_DIR = r"E:\新建文件夹\海外仓\正式价格"
_FUEL_CARRIER_ALIAS = {"乐歌": "乐歌", "SMART": "smart", "乐舱": "乐舱", "安美": "安美", "实力派": "shipai", "链仓": "链仓"}


def _seed_chain_into_pricedata():
    """把链仓 GZYY 的模板+渠道并入统一价卡（其余5仓已通过 seed_from_files 从模板 JSON 导入）。"""
    chain_dir = os.path.join(OFFICIAL_PRICING_DIR, "链仓")
    files = [f for f in os.listdir(chain_dir) if f.lower().endswith(".xlsx") and not f.startswith("~$")] if os.path.isdir(chain_dir) else []
    return chain_dir, files


@app.route("/api/official/import", methods=["POST"])
def api_official_import():
    """把《正式价格》目录内所有报价 Excel 解析进 pricing store。
    body: {dir?: override, dry_run?: true}  default dir = OFFICIAL_PRICING_DIR"""
    body = request.get_json(force=True, silent=True) or {}
    directory = body.get("dir") or OFFICIAL_PRICING_DIR
    dry_run = bool(body.get("dry_run"))
    if not os.path.isdir(directory):
        return jsonify({"error": f"目录不存在: {directory}"}), 400
    subdirs = [d for d in os.listdir(directory) if os.path.isdir(os.path.join(directory, d))]
    if not subdirs:
        subdirs = [""]
    if dry_run:
        return jsonify({"directory": directory, "subdirs": subdirs})
    results = []
    for sd in sorted(subdirs):
        base = os.path.join(directory, sd)
        files = [f for f in os.listdir(base) if f.lower().endswith((".xlsx", ".xls")) and not f.startswith("~$")]
        for fn in sorted(files):
            fp = os.path.join(base, fn)
            try:
                rec = pricing.parse_pricing_excel(fp, custom_name=sd or None)
                PRICING.add(rec)
                results.append({"subdir": sd, "file": fn, "ok": True, "rid": rec["rid"],
                                "shipping": len(rec["shipping"]),
                                "outbound": len(rec["handling"]["outbound"]),
                                "storage": len(rec["handling"]["storage"])})
            except Exception as e:
                results.append({"subdir": sd, "file": fn, "ok": False, "error": str(e)})
    return jsonify({"ok": True, "count": len(results), "results": results})


# ── 账单核对引擎合一 /api/bill-check & /api/bill/parse ──────────
@app.route("/api/bill/parse", methods=["POST"])
def api_bill_parse():
    body = request.get_json(force=True, silent=True) or {}
    matrix = body.get("matrix")
    if not isinstance(matrix, list) or not matrix or not isinstance(matrix[0], list):
        return jsonify({"error": "matrix 需为二维数组"}), 400
    return jsonify(bill_check.parse_matrix(matrix))


@app.route("/api/bill-check", methods=["POST", "OPTIONS"])
def api_bill_check():
    if request.method == "OPTIONS":
        return "", 204
    body = request.get_json(force=True, silent=True) or {}
    rows = body.get("rows") or body.get("matrix_rows")
    if body.get("matrix") and not rows:
        rows = bill_check.parse_matrix(body["matrix"]).get("standard_rows")
    if not isinstance(rows, list) or not rows:
        return jsonify({"error": "rows 需为账单行数组"}), 400
    try:
        out = bill_check.check_bill(
            rows,
            channel_name=body.get("channelName") or None,
            provider=body.get("provider") or None,
            warehouse=body.get("warehouse") or None,
            weight_key=body.get("weightKey") or "weight",
            zone_key=body.get("zoneKey") or "zone",
        )
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500
    return jsonify(out)


# ── 仓储 CBM 阶梯 /api/storage ─────────────────────────────────
@app.route("/api/storage")
def api_storage():
    return jsonify({"storage": outer_import.load_storage()})


@app.route("/api/storage/<provider>")
def api_storage_get(provider):
    st = outer_import.load_storage().get(provider)
    if not st:
        return jsonify({"error": f"未找到 {provider}"}), 404
    return jsonify(st)


@app.route("/api/storage/cost", methods=["POST"])
def api_storage_cost():
    body = request.get_json(force=True, silent=True) or {}
    r = outer_import.cost_storage(
        str(body.get("provider") or ""),
        str(body.get("warehouse") or ""),
        _num_or_none(body.get("cbm")),
        _num_or_none(body.get("days")),
    )
    return jsonify(r)


def _num_or_none(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── 外层仓批量入库 /api/outer ─────────────────────────────────
@app.route("/api/outer/import", methods=["POST"])
def api_outer_import():
    body = request.get_json(force=True, silent=True) or {}
    dry_run = bool(body.get("dry_run"))
    if dry_run:
        return jsonify({"directory": outer_import.OUTER_DIR, "files": list(outer_import.FILES.items())})
    res = outer_import.import_all(store_add=PRICING.add, write_pricedata=True)
    return jsonify({"ok": True, **res})


@app.route("/api/log", methods=["POST"])
def api_log():
    body = request.get_json(force=True, silent=True) or {}
    try:
        log_dir = os.path.join(BASE_DIR, "logs")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "page-errors.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {body.get('msg','')}\n")
    except Exception:
        pass
    return jsonify({"ok": True})


@app.route("/api/outer/status")
def api_outer_status():
    st = outer_import.load_storage()
    return jsonify({
        "storage_count": len(st),
        "storage_providers": sorted(st.keys()),
        "channels_total": len(price_data.snapshot("channels")),
        "templates_total": len(price_data.snapshot("templates")),
        "card": price_data.card_summary(price_data.snapshot("card")),
        "pricing_records": len(PRICING.list_all()),
    })


if __name__ == "__main__":
    from waitress import serve
    _github_pull_startup()
    host = SERVER.get("host", "127.0.0.1")
    port = int(SERVER.get("port", 8000))
    pid_file = os.path.join(BASE_DIR, "server.pid")
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))
    try:
        print(f"海外仓管理看板已启动: http://{host}:{port}", flush=True)
        run_threads = int(SERVER.get("server_threads", 12))
        run_channel_timeout = int(SERVER.get("server_channel_timeout", 600))
        serve(app, host=host, port=port, threads=run_threads, channel_timeout=run_channel_timeout)
    finally:
        try:
            os.remove(pid_file)
        except OSError:
            pass
