"""外层仓(6家+VIP)报价 & 仓储CBM阶梯 统一入库。

职责：
1. storage 规范化：把 8 份文件的仓储费表(天档×仓)提取成统一 schema，写入 data/unified_storage.json
2. 尾程渠道：pricing record 的 shipping(zones dict) → 统一 channels 格式 → price_data.channels
3. 库内/增值模板：handling → price_data.templates
4. 全部 parse 结果同时进 PricingStore(pricing_v2.json)，供 /api/pricing 与比价使用
"""
import os, re, json, tempfile, datetime
from pathlib import Path

import openpyxl

BASE = Path(__file__).parent
OUTER_DIR = r"E:\新建文件夹\海外仓"

# ── 外层仓文件清单（provider 标签 → 文件）───────────────
FILES = {
    "乐歌VIP美": "2026乐歌公共海外仓报价vip-云帆济.xlsx",
    "乐歌VIP加": "2026加拿大乐歌公共海外仓报价-云帆济(1).xlsx",
    "乐歌VIP德": "2026德国乐歌公共海外仓报价-云帆济(1).xlsx",
    "安美VIP": "安美VIP报价.xlsx",
    "YFJ&SMART": "YFJ&SMART美国一件代发报价 Eff.260611.xlsx",
    "无忧达": "云帆济&无忧达美国海外仓2026.4.27(1).xlsx",
    "M.KiTE枫筝": "M.KiTE(CA)枫筝海外仓一件代发价格表2026年2月1日生效(1)(2).xlsx",
    "盘古Teknihall": "盘古Teknihall服务报价表_202602-德国仓V3(1).xlsx",
}

_WEIGHT_COINS = re.compile(r"[^0-9.]")

def _num(v):
    if v is None: return None
    if isinstance(v, (int, float)): return float(v)
    s = str(v).strip().replace(",", "").replace("$", "").replace("€", "")
    s = re.sub(r"[^\d.\-]", "", s)
    try: return float(s) if s else None
    except: return None

def _row_texts(row):
    out = []
    for c in row:
        if c is None or str(c).strip() == "": continue
        out.append(str(c).strip())
    return out

# ════════════════════════════════════════════════════════════════
# 1) 仓储费表特化提取 → 统一 storage record
# ════════════════════════════════════════════════════════════════
def _find_row(rows, pred, start=0, limit=None):
    end = len(rows) if limit is None else min(start + limit, len(rows))
    for ri in range(start, end):
        if pred(rows[ri], ri):
            return ri
    return -1

def _is_days_hdr(v):
    if v is None: return False
    s = str(v).strip()
    return bool(re.search(r"\d+\s*[<≤]\s*X", s) or   # 0<X≤30 / 45<X≤60 / 360<X
                re.search(r"\d+\s*[-~—]\s*\d+", s) or  # 31-60 / 0-30
                re.match(r"^\d+\s*\+", s))            # 360+

def _extract_legu(rows, wh_codes, currency):
    """乐歌式：行=仓库 列[2..8]=天档 列[9]=单位。表头含 '0<X≤30'。"""
    hri = _find_row(rows, lambda r, _: any(_is_days_hdr(c) for c in r), 0, 8)
    if hri < 0:
        return None
    hdr = rows[hri]
    day_cols = [(ci, str(hdr[ci]).strip()) for ci in range(2, len(hdr))
                if hdr[ci] is not None and _is_days_hdr(hdr[ci])]
    day_cols = [(ci, l) for ci, l in day_cols if re.search(r"360|<", l) or "X" in l][:7]
    if len(day_cols) < 2:
        return None
    unit = ""
    for c in rows[hri + 1][9:11] if hri + 1 < len(rows) else []:
        if c is not None and "/" in str(c):
            unit = str(c).strip(); break
    tiers, warehouses = [], []
    for ri in range(hri + 1, min(hri + 12, len(rows))):
        row = rows[ri]
        t = _row_texts(row)
        if not t: continue
        wh = _find_wh(t)
        if not wh or ("存储" in t[0] and "单位" in t[0]):
            continue
        prices = [_num(row[ci] if ci < len(row) else None) for ci, _ in day_cols]
        if any(p is not None for p in prices):
            warehouses.append(wh)
            tiers.append({"label": "·".join(l for _, l in day_cols),
                          "prices": [p if p is not None else None for p in prices]})
    if not tiers:
        return None
    return {"type": "cbm_day_matrix", "currency": currency,
            "unit": unit or "立方米/天",
            "warehouses": warehouses,
            "tiers": tiers}

def _find_wh(t):
    for ci, t0 in enumerate(t):
        m = re.match(r"^([A-Za-z]{3,5})[（(]?([\u4e00-\u9fa5·]+)?", t0)
        if m and m.group(1).isalpha() and len(m.group(1)) >= 2:
            return {"code": m.group(1), "label": m.group(2) or ""}
    return None

def _extract_anmei(rows):
    """安美『一件代发』三、仓储费：行=CA/NJ/SAV 列[1..6]=天档(R28表头)。"""
    hri = _find_row(rows, lambda r, _: "0<X≤30" in str(r[1]) if len(r) > 1 else False, 0, 40)
    if hri < 0:
        hri = _find_row(rows, lambda r, _: any("0<X" in str(c) for c in r), 0, 40)
    if hri < 0:
        return None
    hdr = rows[hri]
    day_cols = [(ci, str(hdr[ci]).strip()) for ci in range(1, 8)
                if hdr[ci] is not None and ("X" in str(hdr[ci]) or "X>180" in str(hdr[ci]))]
    if len(day_cols) < 2:
        day_cols = [(ci, str(hdr[ci]).strip()) for ci in range(1, 8) if hdr[ci] is not None][:6]
    whs, tiers = [], []
    for ri in range(hri + 1, min(hri + 8, len(rows))):
        row = rows[ri]
        t = _row_texts(row)
        if not t: continue
        m = re.match(r"^(CA|NJ|SAV)", t[0])
        if not m: continue
        prices = [_num(row[ci] if ci < len(row) else None) for ci, _ in day_cols]
        whs.append({"code": m.group(1), "label": str(t[0])})
        tiers.append({"label": "·".join(l for _, l in day_cols),
                      "prices": [p if p is not None else None for p in prices]})
    return {"type": "cbm_day_matrix", "currency": "USD", "unit": "立方米/天",
            "warehouses": whs, "tiers": tiers} if tiers else None

def _extract_yfj(rows):
    """YFJ&SMART 库内操作内嵌仓储：R38 表头, 行=天档 列[2]=休斯顿萨凡纳 [3]=新泽西芝加哥 [4]=洛杉矶。"""
    hri = -1
    for ri in range(28, 90):
        row_texts = _row_texts(rows[ri])
        if row_texts and any("仓储费" in t for t in row_texts) and \
                any(re.match(r"^0\s*[-~—]\s*30", t) or "0-30" in t for t in row_texts):
            hri = ri
            break
    if hri < 0:
        return None
    wh_cols = [(2, "休斯顿·萨凡纳"), (3, "新泽西·芝加哥"), (4, "洛杉矶")]
    whs = [{"code": "HUO·SAV", "label": "休斯顿/萨凡纳"},
           {"code": "NJF·CHI", "label": "新泽西/芝加哥"},
           {"code": "LAX", "label": "洛杉矶"}]
    tiers = []
    for ri in range(hri, min(hri + 9, len(rows))):
        row = rows[ri]
        t = _row_texts(row)
        if not t: break
        m = re.search(r"^(\d+)\s*[-~—]\s*(\d+)", str(row[1] if len(row) > 1 else ""))
        m2 = re.match(r"^(\d+)\+", str(row[1] if len(row) > 1 else ""))
        if not m and not m2: break
        prices = [_num(row[ci] if ci < len(row) else None) for ci, _ in wh_cols]
        if not any(p is not None for p in prices): break
        tiers.append({"label": str(row[1]).strip(), "prices": [p if p is not None else None for p in prices]})
    return {"type": "cbm_day_matrix", "currency": "USD", "unit": "CBM/天",
            "warehouses": whs, "tiers": tiers} if tiers else None

def _extract_wuyouda(rows):
    """无忧达 仓储服务：行=天数档 列[3..10]=8仓位 [11]=退货区。"""
    hri = _find_row(rows, lambda r, _: "0-30" in str(r[2] if len(r) > 2 else ""), 0, 10)
    if hri < 0:
        return None
    main_cols = list(range(3, 11)); ret_col = 11
    whs_main = ["CA仓群", "NJ仓群", "NJJW05", "TX仓群", "GA仓", "SAV仓", "FL仓", "IL仓群"]
    tiers, ret_prices = [], []
    for ri in range(hri, min(hri + 10, len(rows))):
        row = rows[ri]
        t = _row_texts(row)
        if r"0-30" in str(row[2] if len(row) > 2 else "") or \
           (len(row) > 2 and re.search(r"^\d+\s*[-~—]\s*\d+", str(row[2]))):
            prices = [_num(row[ci] if ci < len(row) else None) for ci in main_cols]
            rp = _num(row[ret_col] if ret_col < len(row) else None)
            tiers.append({"label": str(row[2]).strip(), "prices": prices})
            ret_prices.append(rp)
        if len(tiers) >= 8: break
    return {"type": "cbm_day_matrix", "currency": "USD", "unit": "立方/天",
            "warehouses": [{"code": w, "label": w} for w in whs_main],
            "tiers": tiers, "return_zone_prices": ret_prices,
            "note": "超长(260≥L>130cm)仓租×1.2；特长(L>260cm)按1.4"} if tiers else None

def _extract_fzheng(rows):
    """M.KiTE 基础服务费用表：'仓储费' 编号行 R31-35：天档→价（FREE）。"""
    hri = _find_row(rows, lambda r, _: str(r[1]) if len(r) > 1 else "" == "仓储费", 0, 60)
    # 直接找含 仓储费 的名字列
    hri = -1
    for ri in range(20, len(rows)):
        if len(rows[ri]) > 1 and str(rows[ri][1] or "").strip() == "仓储费":
            hri = ri; break
    if hri < 0:
        return None
    tiers = []
    for ri in range(hri, min(hri + 8, len(rows))):
        row = rows[ri]
        if len(row) < 4: break
        label = str(row[2] or "").strip()
        price_txt = str(row[3] or "").strip()
        if not label or "包装材料费" in label: break
        if "FREE" in price_txt or "免" in price_txt:
            p = 0.0
        else:
            p = _num(price_txt)
        if p is None: break
        tiers.append({"label": label, "prices": [p]})
    return {"type": "cbm_day_matrix", "currency": "USD", "unit": "CBM/天",
            "warehouses": [{"code": "CA", "label": "枫筝加拿大"}],
            "tiers": tiers} if tiers else None

def _extract_pangu(rows):
    """盘古 teknihall 服务报价：Storage fee 行 R4-R10 天档→欧元。"""
    hri = -1
    for ri in range(0, 40):
        if len(rows[ri]) > 1 and "1.1 Storage fee" in str(rows[ri][1] or ""):
            hri = ri; break
    if hri < 0:
        for ri in range(0, 40):
            if "Storage" in " ".join(str(c) for c in (rows[ri] or []) if c) and "fee" in " ".join(str(c) for c in (rows[ri] or []) if c).lower():
                hri = ri; break
    if hri < 0:
        return None
    tiers = []
    for ri in range(hri + 1, min(hri + 9, len(rows))):
        row = rows[ri]
        if len(row) < 4: break
        label = str(row[2] or "").strip()
        price_txt = str(row[3] or "").strip()
        if not label or "€" in label: continue
        if "Free" in price_txt or "免" in price_txt:
            p = 0.0
        else:
            p = _num(price_txt)
        if p is None: break
        tiers.append({"label": label, "prices": [p]})
    return {"type": "cbm_day_matrix", "currency": "EUR", "unit": "欧元/天×体积(最小0.001m³)",
            "warehouses": [{"code": "EUWE", "label": "Heusenstamm 德国"}],
            "tiers": tiers} if tiers else None

# 统一的仓储提取入口
def extract_storage(provider, rows_map):
    """rows_map: sheet名→rows。返回 storage record 或 None。"""
    if provider in ("乐歌VIP美", "乐歌VIP加", "乐歌VIP德"):
        sheet = rows_map.get("海外仓存储服务") or next(iter(rows_map.values()))
        cur = "USD" if "美" in provider else ("CAD" if "加" in provider else "EUR")
        return _extract_legu(sheet or [], None, cur)
    if provider == "安美VIP":
        r = _extract_anmei(rows_map.get("一件代发") or [])
        if r: r["provider"] = provider
        return r
    if provider == "YFJ&SMART":
        r = _extract_yfj(rows_map.get("库内操作") or [])
        if r: r["provider"] = provider
        return r
    if provider == "无忧达":
        r = _extract_wuyouda(rows_map.get("仓储服务") or [])
        if r: r["provider"] = provider
        return r
    if provider == "M.KiTE枫筝":
        r = _extract_fzheng(rows_map.get("基础服务费用表") or [])
        if r: r["provider"] = provider
        return r
    if provider == "盘古Teknihall":
        r = _extract_pangu(rows_map.get("teknihall 服务报价") or [])
        if r: r["provider"] = provider
        return r
    return None

# ════════════════════════════════════════════════════════════════
# 2) 尾程矩阵 → 统一 channels 格式
# ════════════════════════════════════════════════════════════════
def channel_from_shipping(provider, ship):
    zones = sorted({int(re.sub(r"[^0-9]", "", z) or i) for i, z in enumerate(ship["zones"])})
    zorder = [z for z in zones if 1 <= z <= 99]
    if not zorder:
        return None
    # 收集所有 weight 键；过滤异常（>350磅=超大件LTL 噪声）
    weights = set()
    for zn in ship["zones"].values():
        for wk in zn.keys():
            try:
                w = float(wk)
            except (ValueError, TypeError):
                continue
            if 0 < w <= 350:
                weights.add(w)
    if not weights:
        return None
    rows = []
    for w in sorted(weights):
        wk = str(round(w, 2)) if w != int(w) else str(int(w))
        prices = []
        for znum in zones:
            zn = "Zone%d" % znum
            d = ship["zones"].get(zn) or {}
            prices.append(d.get(wk) if wk in d else None)
        rows.append({"weight": w, "prices": prices})
    return {
        "name": f"{ship.get('carrier', '')}｜{provider}",
        "zones": zones, "rows": rows,
        "fuel_surcharge_pct": ship.get("fuel_surcharge_pct", 0.0),
        "surcharges": [{"name": s.get("category") or "项", "cond": s.get("zone") or "",
                        "prices": [s.get("price")]} for s in ship.get("surcharges", []) if s.get("price") is not None],
        "note": ship.get("sheet", ""),
    }

def channels_from_records(provider, rec):
    out = []
    for ship in rec.get("shipping", []):
        ch = channel_from_shipping(provider, ship)
        if ch:
            out.append(ch)
    return out

# ════════════════════════════════════════════════════════════════
# 3) 库内/增值/仓储处理项 → templates
# ════════════════════════════════════════════════════════════════
def _tiers_of(out_item):
    ts = []
    lo = out_item.get("min_lbs")
    hi = out_item.get("max_lbs")
    if lo is not None and hi is not None:
        ts.append({"min": lo, "max": hi, "price": out_item.get("price")})
    return ts or None

def templates_from_records(provider, rec):
    out = []
    for it in rec.get("handling", {}).get("outbound", []):
        tpl = {
            "provider": provider, "warehouse": str(it.get("warehouse") or "全仓"),
            "serviceType": str(it.get("service") or it.get("desc") or "下架出库"),
            "unit": str(it.get("unit") or "每件"),
            "price": it.get("price"), "minCharge": 0,
            "note": "", "tiers": _tiers_of(it),
        }
        if tpl["serviceType"] and tpl["price"] is not None:
            out.append(tpl)
    seen = set()
    dedup = []
    for t in out:
        k = (t["provider"], t["warehouse"], t["serviceType"], t["unit"], t["price"])
        if k in seen: continue
        seen.add(k); dedup.append(t)
    return dedup

# ════════════════════════════════════════════════════════════════
# 4) 总入口：解析全部文件 → pricing store + price_data
# ════════════════════════════════════════════════════════════════
STORAGE_FILE = BASE / "data" / "unified_storage.json"

def _fix_storage_layout(st):
    """把「行=仓库、列=天档」的转置表统一成「档位×仓库」tier-major 结构。
    tier 项 label 形如 '0<X≤30·30<X≤60...'（·拼接）且 prices 长度==段数 → 判定为转置。"""
    if not isinstance(st, dict) or not st.get("tiers"):
        return st
    tiers = st["tiers"]
    first = tiers[0]
    labels = [str(l).strip() for l in str(first.get("label") or "").split("·") if str(l).strip()]
    p0 = first.get("prices")
    if not isinstance(p0, list) or len(labels) != len(p0) or len(labels) <= 1:
        return st
    for t in tiers:
        p = t.get("prices")
        if not isinstance(p, list) or len(p) != len(p0):
            return st
    st["tiers"] = [{"label": labels[k], "prices": [t["prices"][k] for t in tiers]}
                   for k in range(len(labels))]
    return st


def load_storage():
    if STORAGE_FILE.exists():
        try: return json.loads(STORAGE_FILE.read_text("utf-8"))
        except: pass
    return {}

def save_storage(data):
    tmp = STORAGE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(STORAGE_FILE)


def _tier_index(tiers, days):
    import math
    if days is None: return None
    for i, t in enumerate(tiers):
        label = t.get("label", "")
        m = re.search(r">\s*(\d+)", label)
        if m and days > int(m.group(1)):
            continue
        if re.search(r"<\s*(\d+)", label):
            mu = int(re.search(r"<\s*(\d+)", label).group(1))
            if days <= mu:
                return i
            continue
        m2 = re.search(r"0\s*[<≤]\s*X\s*[<≤]\s*(\d+)", label)
        if m2 and days <= int(m2.group(1)):
            return i
        m3 = re.search(r"(\d+)\s*[<≤]\s*X\s*[<≤]\s*(\d+)", label)
        if m3 and int(m3.group(1)) < days <= int(m3.group(2)):
            return i
        m4 = re.match(r"^(\d+)\s*[-~—]\s*(\d+)", label)
        if m4 and int(m4.group(1)) < days <= int(m4.group(2)):
            return i
        m5 = re.match(r"^\d+\s*[-~—]\s*(\d+)$", label)
        if m5 and days <= int(m5.group(1)):
            return i
    return 0 if tiers else None


def cost_storage(provider, warehouse, cbm, days):
    """按统一仓储表计算某仓某体积×库龄 的日租费用。
    returns {provider, warehouse, cbm, days, price_per_cbm_day, total_per_day, tier, note}"""
    st = load_storage().get(provider)
    if not st:
        return {"error": "未找到 %s 的仓储费表" % provider}
    tiers = st.get("tiers") or []
    idx = _tier_index(tiers, days)
    if idx is None:
        return {"error": "无库龄档"}
    whs = st.get("warehouses") or []
    prices = tiers[idx].get("prices") or []
    price = None
    if len(whs) == 1:
        price = prices[0]
    else:
        for k, w in enumerate(whs):
            if w.get("code") == warehouse or warehouse in str(w.get("label")):
                price = prices[k] if k < len(prices) else None
                break
    if price is None:
        price = prices[0] if prices else 0
    label = tiers[idx].get("label")
    return {"provider": provider, "warehouse": warehouse, "cbm": cbm, "days": days,
            "tier": label, "unit": st.get("unit"), "currency": st.get("currency"),
            "price_per_cbm_day": price,
            "total_per_day": round((cbm or 0) * (price or 0), 4)}

def import_all(store_add=None, write_pricedata=True):
    """返回 {'files': [...], 'channels': n, 'templates': n, 'storage': n}"""
    import pricing
    import price_data
    storage = load_storage()
    results = []
    channels_all = list(price_data.snapshot("channels"))
    tpl_all = []
    seen_tpl = set()
    for f in (price_data.snapshot("templates") if write_pricedata else []):
        k = (f.get("provider"), f.get("warehouse"), f.get("serviceType"), f.get("unit"))
        if k not in seen_tpl:
            seen_tpl.add(k); tpl_all.append(f)
    for provider, fn in FILES.items():
        fp = os.path.join(OUTER_DIR, fn)
        if not os.path.exists(fp):
            results.append({"provider": provider, "ok": False, "error": "missing"})
            continue
        try:
            rec = pricing.parse_pricing_excel(fp, custom_name=provider)
            if store_add:
                store_add(rec)
            ships = channels_from_records(provider, rec)
            in_file = {"provider": provider, "file": fn,
                       "outbound": len(rec["handling"]["outbound"]),
                       "inbound": len(rec["handling"]["inbound"]),
                       "storage": len(rec["handling"]["storage"]),
                       "shipping_tables": len(rec["shipping"]),
                       "channels": len(ships),
                       "shipping_names": [s.get("carrier") + "/" + s.get("sheet")[:20] for s in rec["shipping"][:10]]}
            # channels
            if write_pricedata:
                for ch in ships:
                    chname = ch["name"]
                    prev = next((i for i, c in enumerate(channels_all) if c.get("name") == chname), None)
                    if prev is not None:
                        channels_all[prev] = ch
                    else:
                        channels_all.append(ch)
                # templates：库内操作项
                for tpl in templates_from_records(provider, rec):
                    k = (tpl["provider"], tpl["warehouse"], tpl["serviceType"], tpl["unit"])
                    if k in seen_tpl: continue
                    seen_tpl.add(k); tpl_all.append(tpl)
            # storage：需要重开 wb 单独提取仓储 sheet
            st = None
            try:
                wb = openpyxl.load_workbook(fp, read_only=True, data_only=True)
                smap = {}
                for sn in wb.sheetnames:
                    ws = wb[sn]
                    first = []
                    try:
                        for i, rowv in enumerate(ws.iter_rows(values_only=True)):
                            first.append(rowv)
                            if i >= 60: break
                    except Exception:
                        pass
                    smap[sn.strip().lower()] = first
                wb.close()
                st = extract_storage(provider, smap)
            except Exception as e:
                in_file["storage_extract_error"] = str(e)[:80]
            if st:
                st = _fix_storage_layout(st)
                st.setdefault("provider", provider)
                st["source"] = fn
                storage[provider] = st
                in_file["storage_tiers"] = len(st.get("tiers", []))
                in_file["storage_wh"] = len(st.get("warehouses", []))
            results.append({"provider": provider, "ok": True, **in_file})
        except Exception as e:
            results.append({"provider": provider, "ok": False, "error": str(e)[:120]})
    if write_pricedata:
        price_data.write("channels", channels_all)
        price_data.write("templates", tpl_all)
        # 层级价卡：每次入库后从最新扁平 kinds 重建
        price_data.rebuild_card_from_flat()
    save_storage(storage)
    return {"files": results, "channels": len(channels_all),
            "templates": len(tpl_all), "storage": len(storage)}

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(BASE))
    from pricing import PricingStore
    S = PricingStore()
    res = import_all(store_add=S.add, write_pricedata=True)
    for f in res["files"]:
        print(f["provider"], "OK" if f.get("ok") else "FAIL", f.get("error") or
              f" ship={f['channels']} ob={f['outbound']} st_extract={f.get('storage_tiers','-')}/{f.get('storage_wh','-')}",
              f.get("shipping_names", []))
    print("TOTAL channels=%d templates=%d storage=%d" % (res["channels"], res["templates"], res["storage"]))