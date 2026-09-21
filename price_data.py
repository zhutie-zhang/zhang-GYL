"""统一价卡存储层 — 把 price-checker.html 的 localStorage 数据(kind)统一落到服务端 JSON，
并保留版本哈希与漂移检测能力。兼容五种数据：
  channels  物流渠道矩阵(扁平投影) [{name,zones,rows,surcharges,note,createdAt}]
  templates 库内/增值/仓储报价模板(扁平投影) [{provider,warehouse,serviceType,unit,price,minCharge,note,tiers}]
  fuel      周燃油费率 {channelName:{url,records:[{percent,date,src}]}}
  freight   混合报价/运费计算模板 [freightTemplates]
  card      层级价卡(权威数据源) 服务商→国家仓→{modules 库内收费(自定义,一版), channels 尾程快递(多渠道)}
"""
import os, re, json, uuid, hashlib, threading, datetime as _dt
from pathlib import Path

BASE = Path(__file__).parent
DATA_DIR = BASE / "data"
DATA_DIR.mkdir(exist_ok=True)

KINDS = ("channels", "templates", "fuel", "freight", "card")
_FILES = {k: DATA_DIR / f"unified_{k}.json" for k in KINDS}
_VERSION_FILE = DATA_DIR / "price_versions.json"
_lock = threading.Lock()

_EMPTY = {"channels": [], "templates": [], "fuel": {}, "freight": [], "card": []}


# ── 层级价卡 card 辅助 ─────────────────────────────────────────
# 服务商→国家仓 两级。国家仓后缀拆解：品牌名 + 仓名（美/加/德... 单字结尾）。
_COUNTRY_CHARS = ("美", "加", "德", "英", "法", "澳", "日", "西", "意")
_DEFAULT_MODULE = "库内操作费"


def _uid():
    return uuid.uuid4().hex[:8]


def _build_label_map(labels):
    """数据驱动地判定 仓标签 是否可按「品牌+国家」拆分：
    仅当 ≥2 个标签共享同一前缀、且末位国家字不同（如 乐歌VIP美/加/德）时拆分，
    否则整体视为品牌（如 安美、无忧达 不会被误拆）。返回 {label: (品牌, 仓名, 国家)}"""
    labels = {str(x or "").strip() for x in labels}
    candidates = {l for l in labels if len(l) > 1 and l[-1] in _COUNTRY_CHARS and l not in ("全仓", "ALL")}
    split_labels = set()
    for prefix in {l[:-1] for l in candidates}:
        suffixes = {l[-1] for l in candidates if l[:-1] == prefix}
        if len(suffixes) >= 2:
            split_labels |= {l for l in candidates if l[:-1] == prefix}
    return {l: (l[:-1], l, l[-1]) if l in split_labels else (l, "全仓", "")
            for l in labels}


def card_summary(card):
    provs = len(card or [])
    whs = chs = mods = items = 0
    for p in (card or []):
        for w in p.get("warehouses", []):
            whs += 1
            chs += len(w.get("channels", []) or [])
            for m in w.get("modules", []):
                mods += 1
                items += len(m.get("items", []) or [])
    return {"providers": provs, "warehouses": whs, "channels": chs,
            "modules": mods, "items": items}


def card_from_flat(templates=None, channels=None):
    """把旧的扁平 templates/channels 迁移成层级价卡（服务商→国家仓→模块/渠道）。
    渠道投影名保留原名(sourceName)；模板层可选 providerAlias/warehouseAlias 供旧匹配容错。"""
    templates = snapshot("templates") if templates is None else templates
    channels = snapshot("channels") if channels is None else channels
    # 收集全部 仓标签/品牌，数据驱动拆分 品牌+国家
    labels = set()
    for c in channels or []:
        nm = (c.get("name") or "").strip()
        labels.add(nm.rsplit("｜", 1)[1] if "｜" in nm else nm)
    for t in templates or []:
        labels.add((t.get("provider") or "").strip())
        labels.add((t.get("warehouse") or "全仓").strip())
    lmap = _build_label_map(labels)

    def splitl(x):
        return lmap.get((str(x or "").strip()), (str(x or "").strip(), "全仓", ""))

    providers, whs = {}, {}

    def ensure(brand, wh_name, country):
        p = providers.setdefault(brand or "未命名",
                                 {"id": _uid(), "name": brand or "未命名", "warehouses": []})
        key = (p["name"], wh_name)
        w = whs.get(key)
        if w is None:
            label = wh_name
            if country and not wh_name.endswith("仓"):
                label = wh_name + "仓"
            w = {"id": _uid(), "name": wh_name, "label": label, "country": country,
                 "providerAlias": None, "warehouseAlias": None,
                 "modules": [], "channels": []}
            p["warehouses"].append(w)
            whs[key] = w
        return p, w

    # 1) 渠道 → 所属仓
    for c in channels or []:
        nm = (c.get("name") or "").strip()
        if "｜" in nm:
            carrier, suffix = nm.rsplit("｜", 1)
        else:
            carrier, suffix = nm, ""
        brand, wh_name, country = splitl(suffix or nm)
        _, w = ensure(brand, wh_name, country)
        chan = {k: v for k, v in c.items() if k != "name"}
        chan.update({"id": _uid(), "name": carrier or nm, "sourceName": nm or None})
        w["channels"].append(chan)

    # 2) 模板 → 所属仓默认模块
    for t in templates or []:
        brand_raw = (t.get("provider") or "").strip()
        wh_raw = (t.get("warehouse") or "全仓").strip()
        b_brand, b_whpn, b_country = splitl(brand_raw)
        alias_p, alias_w = None, None
        brand, wh_name = brand_raw or "未命名", wh_raw
        if b_whpn != "全仓" and brand_raw:
            # 老外层仓 provider 形如 乐歌VIP美 → 品牌=乐歌VIP，仓=乐歌VIP美
            brand = b_brand
            alias_p = brand_raw
            if wh_raw in ("", "ALL", "全仓"):
                wh_name = b_whpn
                if wh_raw not in ("", "全仓"):
                    alias_w = wh_raw
        elif wh_raw in ("", "ALL"):
            alias_w = wh_raw if wh_raw else None
            wh_name = "全仓"
        _, w = ensure(brand, wh_name, splitl(brand)[2] or b_country)
        if alias_p:
            w["providerAlias"] = alias_p
        if alias_w:
            w["warehouseAlias"] = alias_w
        modules = w["modules"]
        if not modules:
            modules.append({"id": _uid(), "name": _DEFAULT_MODULE, "items": []})
        m = modules[0]
        m["items"].append({"serviceType": t.get("serviceType"), "unit": t.get("unit"),
                           "price": t.get("price"), "minCharge": t.get("minCharge") or 0,
                           "note": t.get("note") or "", "tiers": t.get("tiers")})
    return list(providers.values())


def flatten_card(card):
    """把层级价卡展开成旧版扁平 templates/channels（用于兼容 bill_check 与旧 UI）。"""
    templates, channels = [], []
    for p in card or []:
        pname = p.get("name") or "未命名"
        for w in p.get("warehouses", []):
            wname = w.get("name") or "全仓"
            for m in w.get("modules", []):
                for it in m.get("items", []):
                    tpl = {"provider": pname, "warehouse": wname,
                           "serviceType": it.get("serviceType"), "unit": it.get("unit"),
                           "price": it.get("price"), "minCharge": it.get("minCharge") or 0,
                           "note": it.get("note") or "", "tiers": it.get("tiers")}
                    if w.get("providerAlias"):
                        tpl["providerAlias"] = w["providerAlias"]
                    if w.get("warehouseAlias"):
                        tpl["warehouseAlias"] = w["warehouseAlias"]
                    templates.append(tpl)
            for c in w.get("channels", []):
                name = c.get("sourceName") or ((c.get("name") or "") + "｜" + wname
                                               if (c.get("name") and wname) else (c.get("name") or ""))
                ch = {k: v for k, v in c.items()
                      if k not in ("id", "name", "sourceName")}
                ch["name"] = name
                if "id" in c:
                    ch.pop("id", None)
                channels.append(ch)
    return templates, channels


def rebuild_card_from_flat():
    """从扁平 kinds 重建 card，并回写投影（templates/channels）。供 seed / outer 导入 / 首次启动自动迁移。"""
    card = card_from_flat()
    if not card:
        return 0
    write("card", card)
    sync_card_projections()
    return len(card)


def sync_card_projections():
    """card 是权威数据源：每次 card 写入后重建扁平投影，保持 bill_check / 旧界面一致。"""
    card = snapshot("card")
    if not card:
        return
    t, c = flatten_card(card)
    if c:
        write("channels", c)
    if t:
        write("templates", t)


def upsert_card_item(item):
    """按 name 合并单项到 card（兼容 append 端点）。"""
    cur = snapshot("card")
    nm = (item or {}).get("name") or ""
    if not nm:
        raise ValueError("card 单项需带 name")
    cur = [p for p in cur if p.get("name") != nm]
    cur.append(item)
    write("card", cur)
    sync_card_projections()
    return cur


def _load(path, default):
    if not path.exists():
        return default
    try:
        v = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return default
    return v if v is not None else default


def _save(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(path)


def snapshot(kind=None):
    with _lock:
        if kind:
            if kind not in KINDS:
                raise ValueError(f"unknown kind {kind}")
            return _load(_FILES[kind], _EMPTY[kind])
        return {k: _load(_FILES[k], _EMPTY[k]) for k in KINDS}


def write(kind, data):
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind}")
    with _lock:
        _save(_FILES[kind], data)
        return _load(_FILES[kind], _EMPTY[kind])


def append(kind, item):
    cur = snapshot(kind)
    if kind == "channels":
        cur = [c for c in cur if c.get("name") != item.get("name")]
        cur.append(item)
    elif kind == "templates":
        key = lambda t: (t.get("provider"), t.get("warehouse"), t.get("serviceType"), t.get("unit"))
        cur = [t for t in cur if key(t) != key(item)]
        cur.append(item)
    elif kind == "fuel":
        cur[item["channelName"]] = item
    elif kind == "freight":
        cur = [f for f in cur if f.get("id") != item.get("id")]
        cur.append(item)
    elif kind == "card":
        cur = [p for p in cur if p.get("name") != item.get("name")]
        cur.append(item)
    return write(kind, cur)


# ── 版本哈希与漂移检测 ──────────────────────────────────────────
def _stable_dumps(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _content_hash(kind, data=None):
    if data is None:
        data = snapshot(kind)
    if kind == "channels":
        # 仅渠道名+价格矩阵决定版本，忽略 createdAt/note 噪声？不——保留全量以准确反映内容。
        data = data
    return hashlib.sha1(_stable_dumps(data).encode("utf-8")).hexdigest()[:12]


def _load_versions():
    return _load(_VERSION_FILE, {})


def _save_versions(v):
    _save(_VERSION_FILE, v)


def current_version(kind):
    return {"kind": kind, "hash": _content_hash(kind),
            "count": len(snapshot(kind)) if isinstance(snapshot(kind), list) else len(snapshot(kind)),
            "updated_at": _load_versions().get(kind, {}).get("updated_at"),
            "label": _load_versions().get(kind, {}).get("label")}


def record_version(kind, label="手动更新"):
    h = _content_hash(kind)
    with _lock:
        versions = _load_versions()
        versions[kind] = {"hash": h, "label": label,
                          "updated_at": _dt.datetime.now().isoformat(timespec="seconds")}
        _save_versions(versions)
    return {"kind": kind, "hash": h, "label": label}


def diff(kind):
    """对比当前价卡与最近一次记录的版本，返回结构化的差异说明。"""
    cur = snapshot(kind)
    cur_hash = _content_hash(kind, cur)
    versions = _load_versions()
    rec = versions.get(kind)
    if not rec:
        return {"kind": kind, "changed": False, "reason": "no_baseline",
                "current_hash": cur_hash, "baseline_hash": None,
                "diff": []}
    if rec.get("hash") == cur_hash:
        return {"kind": kind, "changed": False, "current_hash": cur_hash,
                "baseline_hash": rec.get("hash"), "diff": []}
    diff_items = _diff_items(kind, cur, rec)
    return {"kind": kind, "changed": True,
            "current_hash": cur_hash, "baseline_hash": rec.get("hash"),
            "baseline_label": rec.get("label"), "baseline_at": rec.get("updated_at"),
            "diff": diff_items}


def _diff_items(kind, cur, rec):
    if kind == "card":
        old = _baseline(kind)
        out = []
        names = set(p.get("name") for p in cur)
        old_names = set(p.get("name") for p in old)
        for name in sorted(old_names - names):
            out.append({"type": "removed", "name": name})
        for name in sorted(names - old_names):
            out.append({"type": "added", "name": name})
        for p in cur:
            if p.get("name") not in old_names:
                continue
            o = next((x for x in old if x.get("name") == p.get("name")), None)
            if o is not None and _stable_dumps(o) != _stable_dumps(p):
                out.append({"type": "updated", "name": p.get("name")})
        return out
    if kind == "channels":
        old = _baseline(kind)
        out = []
        names = set(c.get("name") for c in cur)
        old_names = set(c.get("name") for c in old)
        for name in sorted(old_names - names):
            out.append({"type": "removed", "name": name})
        for name in sorted(names - old_names):
            out.append({"type": "added", "name": name})
        for c in cur:
            if c.get("name") not in old_names:
                continue
            o = next((x for x in old if x.get("name") == c.get("name")), None)
            changes = _channel_diff(o, c)
            if changes:
                out.append({"type": "updated", "name": c.get("name"), "changes": changes})
        return out
    if kind == "templates":
        old = _baseline(kind)
        curk = {(t.get("provider"), t.get("warehouse"), t.get("serviceType"), t.get("unit")): t for t in cur}
        out = []
        for t in old:
            k = (t.get("provider"), t.get("warehouse"), t.get("serviceType"), t.get("unit"))
            if k not in curk:
                out.append({"type": "removed", "name": f"{t.get('provider')}/{t.get('serviceType')}"})
            elif curk[k].get("price") != t.get("price") or curk[k].get("tiers") != t.get("tiers"):
                out.append({"type": "updated",
                            "name": f"{t.get('provider')}/{t.get('serviceType')}",
                            "old_price": t.get("price"), "new_price": curk[k].get("price")})
        for t in cur:
            k = (t.get("provider"), t.get("warehouse"), t.get("serviceType"), t.get("unit"))
            if k not in {(x.get("provider"), x.get("warehouse"), x.get("serviceType"), x.get("unit")) for x in old}:
                out.append({"type": "added", "name": f"{t.get('provider')}/{t.get('serviceType')}"})
        return out
    return []


_BASE = {k: DATA_DIR / f"unified_{k}.baseline.json" for k in KINDS}


def _baseline(kind):
    p = _BASE[kind]
    if not p.exists():
        return _EMPTY[kind]
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return _EMPTY[kind]


def set_baseline(kind):
    """把当前内容固定为新基线（比较基准）。"""
    cur = snapshot(kind)
    with _lock:
        _save(_BASE[kind], cur)
        versions = _load_versions()
        versions[kind] = {"hash": _content_hash(kind, cur), "label": "基线",
                          "updated_at": _dt.datetime.now().isoformat(timespec="seconds")}
        _save_versions(versions)
    return {"kind": kind, "hash": versions[kind]["hash"]}


def _channel_diff(o, c):
    changes = []
    orow = {r["weight"]: r["prices"] for r in o.get("rows", [])}
    crow = {r["weight"]: r["prices"] for r in c.get("rows", [])}
    for w in sorted(set(orow) | set(crow)):
        if w not in orow:
            changes.append({"weight": w, "type": "added"})
        elif w not in crow:
            changes.append({"weight": w, "type": "removed"})
        else:
            a, b = orow[w], crow[w]
            if a != b:
                diffs = [{"zone": o.get("zones", [2, 3, 4, 5, 6, 7, 8])[i], "old": a[i], "new": b[i]}
                         for i in range(min(len(a), len(b))) if a[i] != b[i]]
                changes.append({"weight": w, "type": "updated", "zones": diffs})
    if len(changes) > 24:
        changes = changes[:24] + [{"type": "truncated"}]
    return changes


# ── 种子导入：official-channels.json + 五份海外仓报价模板 ──────────
SEED_CHANNELS_FILE = BASE / "official-channels.json"
SEED_TPL_FILES = [
    BASE / "SMART-海外仓报价模板.json",
    BASE / "乐歌-海外仓报价模板.json",
    BASE / "乐舱-海外仓报价模板.json",
    BASE / "安美-海外仓报价模板.json",
    BASE / "实力派-海外仓报价模板.json",
]


def seed_from_files(overwrite=True):
    """从同目录的 official-channels.json 与五份『海外仓报价模板』同步到服务端存储。
    返回每个 kind 的合并统计。"""
    result = {}
    # channels
    if SEED_CHANNELS_FILE.exists():
        try:
            data = json.loads(SEED_CHANNELS_FILE.read_text("utf-8"))
            if isinstance(data, list):
                cur = [] if overwrite else snapshot("channels")
                merged = {c.get("name"): c for c in cur}
                for c in data:
                    merged[c.get("name")] = c
                write("channels", list(merged.values()))
                result["channels"] = {"count": len(data), "file": SEED_CHANNELS_FILE.name}
        except ValueError as e:
            result["channels"] = {"error": str(e)}
    # templates
    tpl_merged = {}
    if not overwrite:
        for t in snapshot("templates"):
            tpl_merged[(t.get("provider"), t.get("warehouse"), t.get("serviceType"), t.get("unit"))] = t
    added = 0
    for f in SEED_TPL_FILES:
        if not f.exists():
            continue
        try:
            obj = json.loads(f.read_text("utf-8"))
            for t in obj.get("templates", []):
                k = (t.get("provider"), t.get("warehouse"), t.get("serviceType"), t.get("unit"))
                if k not in tpl_merged:
                    tpl_merged[k] = t
                    added += 1
        except ValueError:
            continue
    if tpl_merged:
        write("templates", list(tpl_merged.values()))
    result["templates"] = {"count": added, "files": [f.name for f in SEED_TPL_FILES if f.exists()]}
    # 层级价卡：从最新扁平数据重建（渠道 + 模板 归仓）
    result["card"] = {"providers": rebuild_card_from_flat()}
    return result


def seeds_available():
    return {
        "channels": SEED_CHANNELS_FILE.exists() if SEED_CHANNELS_FILE.exists() else None,
        "templates": [f.name for f in SEED_TPL_FILES],
    }