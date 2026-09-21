"""邮编→Zone 引擎。主数据源：乐歌《美国分区表及偏远邮编列表》xlsx（8 个主仓，~8.9万邮编/仓）。
补充数据源：链仓 GZYY 的 OneTouch可配送邮编 / GOFO可配送邮编。
输出 data/zone_map.json：{provider: {warehouse: {zip5: zone}}}，另存紧凑 zip3 前缀索引以加速。
"""
import os, re, json, threading
from pathlib import Path

BASE = Path(__file__).parent
DATA_DIR = BASE / "data"
DATA_DIR.mkdir(exist_ok=True)
ZONE_FILE = DATA_DIR / "zone_map.json"
_lock = threading.Lock()

_ZONE_POOL = ["Zone2", "Zone3", "Zone4", "Zone5", "Zone6", "Zone7", "Zone8"]
_POOL_IDX = {z: i for i, z in enumerate(_ZONE_POOL)}


def _nz(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip()
    m = re.search(r"\d+", s)
    return int(m.group()) if m else None


def _zone_str(v):
    n = _nz(v)
    if n is None or not (2 <= n <= 8):
        return None
    return "Zone" + str(n)


def _simplify_zip(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s.isdigit():
        return None
    s = s.zfill(5)
    return s[-5:]


def parse_lecang_zone_excel(filepath):
    """乐歌分区表：行3=组头(FedEx/UPS/ROADIE/USPS/Uniuni/WP)，行4=邮编+仓库分区列，行5起数据。
    以组为单位，每组一个邮编列 + 若干仓库分区列。返回 {warehouse: {zip5: zone}}。"""
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("需要 openpyxl")
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 6:
        wb.close()
        return {}
    group_hdr = rows[3]
    col_hdr = rows[4]

    groups = []
    cur = None
    for i, c in enumerate(col_hdr):
        s = (str(c).strip() if c else "")
        if "邮编" in s and "偏远" not in s:
            if cur:
                groups.append(cur)
            cur = {"zip_col": i, "wh": [], "group_name": None}
            gn = None
            for j in range(i, -1, -1):
                if group_hdr[j] and str(group_hdr[j]).strip():
                    gn = str(group_hdr[j]).strip()
                    break
            cur["group_name"] = gn
        elif s and cur is not None and "偏远" not in s:
            cur["wh"].append((i, s.replace("分区", "").strip()))
    if cur:
        groups.append(cur)

    out = {}
    for i, r in enumerate(rows[5:], start=5):
        for g in groups:
            zc = g["zip_col"]
            if zc >= len(r):
                continue
            z = _simplify_zip(r[zc])
            if not z:
                continue
            for ci, wn in g["wh"]:
                if ci >= len(r):
                    continue
                zn = _zone_str(r[ci])
                if not zn:
                    continue
                out.setdefault(wn, {})[z] = zn
    wb.close()
    return out


def parse_chain_zip_excel(filepath):
    """链仓 GZYY：OneTouch/GOFO 可配送邮编表 → {warehouse: {zip5: zone}}。
    自动识别两种格式：按 Hub 列分组的 zone 表；或 邮编+注入口岸列 的 zone 表。"""
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("需要 openpyxl")
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    out = {}
    for sn in wb.sheetnames:
        if "可配送" not in sn and "可达" not in sn:
            continue
        ws = wb[sn]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        # 方式 A：某行出现多组 "Hub|Destination Zone"，分组列
        hub_header_row = None
        for ri in range(min(6, len(rows))):
            line = " ".join(str(c) for c in rows[ri] if c)
            if "Destination Zone" in line or ("Hub" in line and "预见" not in line):
                hub_header_row = ri
                break
        if hub_header_row is not None:
            # 找每组 zip_col 与 zone_col：标题行下方一行通常是 "XXX Hub","Destination Zone"
            for ri in range(hub_header_row, min(hub_header_row + 2, len(rows))):
                r = rows[ri]
                for ci in range(len(r)):
                    cs = (str(r[ci]).strip() if r[ci] else "")
                    if "Hub" in cs and cs != "Hub" or "目的地" in cs:
                        pass
            # 直接扫描：列名 "Destination Zone" 右邻即该组 zone，左邻邮编
            zone_cols = []
            for ri in range(min(6, len(rows))):
                r = rows[ri]
                for ci in range(len(r)):
                    if r[ci] and "destination zone" in str(r[ci]).lower():
                        zone_cols.append(ci)
            if zone_cols:
                # 每个 zone 列左邻为邮编列（hub 名或者直接邮编）
                for zc in zone_cols:
                    pc = zc - 1
                    wn = sn + "#" + str(pc)
                    add = {}
                    for r in rows[2:]:
                        if pc >= len(r) or zc >= len(r):
                            continue
                        z = _simplify_zip(r[pc])
                        zn = _zone_str(r[zc])
                        if z and zn:
                            add[z] = zn
                    if add:
                        # 用 hub 名做更友好的标题：找上一行非空单元格
                        name = wn
                        for ri in range(2, -1, -1):
                            if pc < len(rows[ri]) and rows[ri][pc]:
                                name = str(rows[ri][pc]).strip()
                                break
                        if any(k in name for k in ("Hub", "加州", "新泽西", "休斯", "LAX", "NJ", "HOU", "CA")):
                            out[name] = add
                        else:
                            out[wn] = add
        # 方式 B：纯 邮编+注入口岸 表（GOFO）：第一列邮编，其后若干口岸列
        else:
            # 找到疑似邮编列起点：第二行起有 4-5 位数字
            pcols = set()
            for ri in range(1, min(6, len(rows))):
                for ci in range(min(8, len(rows[ri]))):
                    z = _simplify_zip(rows[ri][ci])
                    if z and 5 == len(z):
                        pcols.add(ci)
            for pc in sorted(pcols):
                for ri in range(min(3, len(rows))):
                    r = rows[ri]
                    if pc < len(r) and r[pc] and any("址" in str(c) or "岸" in str(c) or "港" in str(c) for c in r[:pc + 1]):
                        pass
                add = {}
                for r in rows[2:]:
                    if pc >= len(r):
                        continue
                    z = _simplify_zip(r[pc])
                    if not z:
                        continue
                    for ci in range(pc + 1, min(len(r), pc + 8)):
                        zn = _zone_str(r[ci])
                        if zn:
                            add[z] = zn
                if add:
                    name = sn
                    if pc == 1:
                        out[name] = add
    wb.close()
    return out


def _flatten(out):
    """把解析结果折叠为 {provider: {warehouse: {zip3: {zip5: zone_idx}}}} 紧凑格式。
    zone_idx 0..6 对应 Zone2..8。"""
    flat = {}
    for provider, whmap in out.items():
        fw = {}
        for wn, zm in whmap.items():
            z3 = {}
            for z, zn in zm.items():
                try:
                    z3.setdefault(z[:3], {})[z] = _POOL_IDX[zn]
                except KeyError:
                    pass
            fw[wn] = z3
        flat[provider] = fw
    return flat


def store_map(out, provider="乐歌"):
    """把 {warehouse: {zip5: zone}} 压缩为 {provider:{warehouse:{zip3:{zip5:idx}}}} 并入 zone_map.json。"""
    flat = _flatten({provider: out})
    with _lock:
        cur = {}
        if ZONE_FILE.exists():
            try:
                cur = json.loads(ZONE_FILE.read_text("utf-8"))
            except (OSError, ValueError):
                cur = {}
        if provider not in cur:
            cur[provider] = {}
        for wn, z3m in flat.get(provider, {}).items():
            cur[provider].setdefault(wn, {}).update(z3m)
        tmp = ZONE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(cur, ensure_ascii=False), "utf-8")
        tmp.replace(ZONE_FILE)
    return {"provider": provider, "warehouses": len(out)}


def load_map():
    if not ZONE_FILE.exists():
        return {}
    try:
        return json.loads(ZONE_FILE.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def lookup(zip5, warehouse=None, providers=None):
    """查询 zip5 对应 zone。warehouse 指定则仅在该仓精确查询；否则在所有仓库里找首个匹配。
    兼容两种存储：zip5 直存 {zip5: zone_str/idx} 与 zip3 索引 {zip3:{zip5:idx}}。
    返回 zone 字符串如 Zone5，找不到返回 None。"""
    if not zip5:
        return None
    z5 = str(zip5).strip().zfill(5)[-5:]
    z3 = z5[:3]
    data = load_map()
    cands = [p for p in providers] if providers else list(data.keys())
    for p in cands:
        if p not in data:
            continue
        whs = [warehouse] if warehouse and warehouse in data[p] else list(data[p].keys())
        for wn in whs:
            zmap = data[p].get(wn, {})
            if not isinstance(zmap, dict):
                continue
            # 格式1：zip5 直存
            if z5 in zmap:
                z = zmap[z5]
                if isinstance(z, str):
                    return z
                if isinstance(z, int) and 0 <= z <= 6:
                    return _ZONE_POOL[z]
                continue
            # 格式2：zip3 索引
            z3m = zmap.get(z3)
            if isinstance(z3m, dict):
                r = None
                if z5 in z3m:
                    r = z3m[z5]
                elif z3 + "0" in z3m:
                    r = z3m[z3 + "0"]
                elif z3 + "1" in z3m:
                    r = z3m[z3 + "1"]
                elif z3 + "9" in z3m:
                    r = z3m[z3 + "9"]
                if r is not None and isinstance(r, int) and 0 <= r <= 6:
                    return _ZONE_POOL[r]
    return None


def stats():
    data = load_map()
    out = {}
    for p, whs in data.items():
        out[p] = {wn: len(zm) for wn, zm in whs.items()}
    return out