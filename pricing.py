"""海外仓报价比价引擎 v3 — 基于真实 Excel 格式分析"""
import os, re, json, uuid, threading, datetime as _dt
from pathlib import Path

try:
    import openpyxl
except ImportError:
    openpyxl = None

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
PRICE_FILE = DATA_DIR / "pricing_v2.json"
_lock = threading.Lock()

# ── Store (same as before) ─────────────────────────────────────────
class PricingStore:
    def __init__(self):
        self._data = {}
        if PRICE_FILE.exists():
            try: self._data = json.loads(PRICE_FILE.read_text("utf-8"))
            except: self._data = {}
    def _save(self):
        PRICE_FILE.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), "utf-8")
    def list_all(self):
        return {rid: {k: v for k, v in r.items() if k != "raw_sheets"} for rid, r in self._data.items()}
    def get(self, rid):
        r = self._data.get(rid)
        return {k: v for k, v in r.items() if k != "raw_sheets"} if r else None
    def delete(self, rid):
        with _lock:
            if rid in self._data: del self._data[rid]; self._save(); return True
            return False
    def clear(self):
        with _lock: self._data = {}; self._save()
    def add(self, record):
        with _lock:
            self._data[record["rid"]] = record; self._save()
            return record

# ── Helpers ────────────────────────────────────────────────────────
def _num(v):
    if v is None: return None
    if isinstance(v, (int, float)): return float(v)
    s = str(v).strip().replace(",", "").replace("$", "")
    s = re.sub(r"[^\d.\-]", "", s)
    try: return float(s) if s else None
    except: return None

def _txt(rows):
    return " ".join(str(c) for row in rows for c in row if c)

def _is_tier(v):
    if not v: return False
    s = str(v).strip()
    return bool(re.search(r"\d+.*[<≤].*\d+|W\s*[>≥]\s*\d+|≤\s*\d+", s, re.I) or
                re.match(r"\d+\.?\d*\s*[\-~]\s*\d+", s, re.I))

def _parse_tier(text):
    if not text: return None
    s = str(text).strip()
    m = re.search(r"(\d+\.?\d*)\s*(?:lbs?|磅|LB)?\s*<\s*W\s*[≤<]\s*(\d+\.?\d*)", s, re.I)
    if m: return (float(m.group(1)), float(m.group(2)))
    m = re.search(r"W\s*[>≥]\s*(\d+\.?\d*)", s, re.I)
    if m: return (float(m.group(1)), 9999)
    m = re.search(r"[≤<]\s*(\d+\.?\d*)\s*(?:lbs?|磅|LB)?", s, re.I)
    if m: return (0, float(m.group(1)))
    m = re.match(r"(\d+\.?\d*)\s*[\-~]\s*(\d+\.?\d*)", s, re.I)
    if m: return (float(m.group(1)), float(m.group(2)))
    return None

# ── Parse entry ────────────────────────────────────────────────────
SKIP_SHEETS = {"目录", "简介", "乐舱简介", "仓库基础信息", "客户信息表", "库内索赔标准", "磅和公斤", "厘米和英寸"}
SKIP_KEYWORDS = {"customs clearance", "trucking（pick up）", "claim", "仓储定义"}

def parse_pricing_excel(filepath, custom_name=None):
    if openpyxl is None:
        raise RuntimeError("需要 openpyxl")
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    fname = os.path.basename(filepath)
    record = {
        "rid": str(uuid.uuid4())[:8],
        "name": custom_name or _guess_name(fname, wb),
        "file": fname, "uploaded_at": _dt.datetime.now().isoformat(),
        "warehouses": [],
        "handling": {"outbound": [], "inbound": [], "storage": [], "value_added": []},
        "shipping": [], "surcharges": [],
    }

    for sn in wb.sheetnames:
        ws = wb[sn]
        rows = list(ws.iter_rows(values_only=True))
        if not rows: continue

        # Skip known non-data sheets by name
        if sn.strip() in SKIP_SHEETS: continue
        text_all = _txt(rows).lower()
        if any(k in text_all for k in SKIP_KEYWORDS): continue
        # Skip sheets that are ONLY reference/navigation
        if len(rows) < 3: continue

        # Track if this sheet was parsed as shipping (don't also parse as surcharges)
        is_shipping_sheet = False

        # ── 0) Mixed "库内费用" sheet — section-based parsing (实力派 etc.)
        if _try_parse_mixed_warehouse_fees(rows, record, sn):
            pass  # handled, skip generic parsers
        else:
            # ── 1) Outbound (订单出库费 / 一件代发)
            _try_parse_outbound(rows, record, sn)

            # ── 2) Inbound (卸货/入库)
            _try_parse_inbound(rows, record, sn)

            # ── 3) Storage (仓储费)
            _try_parse_storage(rows, record, sn)

            # ── 4) Value-added (增值服务)
            _try_parse_value_added(rows, record, sn)

        # ── 5) Shipping (Zone×重量矩阵) — run BEFORE surcharges
        was_shipping = len(record["shipping"])
        _try_parse_usps_dual(rows, record, sn) or _try_parse_shipping(rows, record, sn) or _try_parse_eu_shipping(rows, record, sn)
        is_shipping_sheet = len(record["shipping"]) > was_shipping

        # ── 6) Surcharges (附加费/AHS)
        # Only parse from sheets that are NOT shipping rate tables
        # Shipping sheets already capture surcharges as part of their structure
        if not is_shipping_sheet:
            _try_parse_surcharge(rows, record, sn)

    wb.close()

    # ── Post-process: merge standalone surcharge groups into shipping tables ──
    # If a surcharge group has Zone-based pricing and a shipping table has the same zones,
    # attach the surcharges to the shipping table.
    if record["surcharges"] and record["shipping"]:
        merged_groups = []
        for sg in record["surcharges"]:
            sg_zones = set(it.get("zone", "") for it in sg["items"])
            best_match = None
            best_overlap = 0
            for sh in record["shipping"]:
                sh_zones = set(sh["zones"].keys())
                overlap = len(sg_zones & sh_zones)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_match = sh
            if best_match and best_overlap >= 3:
                for it in sg["items"]:
                    best_match["surcharges"].append(it)
            else:
                merged_groups.append(sg)
        record["surcharges"] = merged_groups

    record["warehouses"] = sorted(set(record["warehouses"])) if record["warehouses"] else ["ALL"]
    record["summary"] = {
        "outbound_tiers": len(record["handling"]["outbound"]),
        "inbound_items": len(record["handling"]["inbound"]),
        "storage_items": len(record["handling"]["storage"]),
        "value_added_items": len(record["handling"]["value_added"]),
        "shipping_tables": len(record["shipping"]),
        "surcharge_groups": len(record["surcharges"]),
    }
    return record

def _guess_name(fname, wb):
    name = fname.rsplit(".", 1)[0]
    name = re.sub(r"[\(\)（）\d]{4,}", "", name).strip()
    name = re.sub(r"[_\-]+", " ", name).strip()
    for sn in wb.sheetnames:
        if "目录" in sn or "简介" in sn:
            try:
                ws = wb[sn]
                for row in ws.iter_rows(max_row=5, values_only=True):
                    for c in row:
                        if c and isinstance(c, str) and len(c) > 3 and "序号" not in c and "查看" not in c:
                            return c.strip()[:40]
            except: pass
    return name[:40] if name else "Unknown"

# ── Mixed "库内费用" sheet parser (实力派 etc.) ──────────────────────
def _try_parse_mixed_warehouse_fees(rows, record, sheet_name):
    """Detect sheets that mix outbound, inbound, storage, value-added in one sheet.
    Returns True if handled, False to fall back to generic parsers."""
    text_all = _txt(rows).lower()
    # Must have both outbound AND inbound keywords — indicates mixed sheet
    if not ("出库费" in text_all and ("卸货" in text_all or "入库" in text_all or "卸柜" in text_all)):
        return False

    # Detect warehouse columns (美西/美东/美南/美休 etc.)
    wh_cols = []  # [(col_idx, name)]
    for ri, row in enumerate(rows[:5]):
        for ci, c in enumerate(row):
            if c and isinstance(c, str):
                s = c.strip()
                if re.match(r"^(美[东西南]|休斯顿|CA$|NJ$|ATL$|SAV$|TX$|HOU$|仓)", s):
                    if not re.match(r"^(USD|单价|\$|价格|计费)", s):
                        wh_cols.append((ci, s))

    # Classify each row into sections based on header keywords
    section = None  # "inbound" | "outbound" | "self_pickup" | "return" | "storage" | "value_added"
    outbound_done = False  # track when outbound tiers end

    for ri, row in enumerate(rows):
        texts = [str(c).strip() if c else "" for c in row]
        row_text = " ".join(t for t in texts if t).lower()

        # ── Detect section transitions ──
        # NOTE: "仓储费" must be checked BEFORE "退货" because storage notes contain "退货库存"
        if any(k in row_text for k in ["卸货上架", "卸柜", "卸货费"]):
            section = "inbound"
        elif any(k in row_text for k in ["订单出库费", "出库服务费", "订单处理费", "下架出库", "出库费"]):
            section = "outbound"
        elif any(k in row_text for k in ["自提", "self pickup", "平台订单附加费"]):
            section = "self_pickup"
        elif any(k in row_text for k in ["仓储费", "存储费", "仓租"]) and "仓储费" in row_text:
            section = "storage"
        elif any(k in row_text for k in ["增值服务", "value added"]):
            section = "value_added"
        elif any(k in row_text for k in ["退货收货", "退货上架"]):
            section = "return"

        if section is None:
            continue

        # ── Inbound: 卸货上架费 (单箱/单托/40HQ) ──
        if section == "inbound":
            # Skip headers
            if any(k in row_text for k in ["计费单位", "计费段", "单价", "备注", "说明"]):
                continue
            # Look for: desc + price rows
            desc_parts = []
            price = None
            unit = None
            for ci, t in enumerate(texts):
                t_stripped = t.strip()
                if not t_stripped: continue
                # Skip cells with Chinese chars (descriptions)
                if re.search(r"[\u4e00-\u9fff]", t_stripped):
                    desc_parts.append(t_stripped)
                    continue
                # Skip cells with letters (like "40 HQ") — only parse pure numeric cells
                if re.search(r"[a-zA-Z]", t_stripped):
                    desc_parts.append(t_stripped)
                    continue
                pv = _num(t_stripped)
                if pv is not None and 0 < pv < 50000 and price is None:
                    price = pv
                    # Check if previous cell is a unit
                    if ci > 0 and texts[ci-1].strip():
                        prev = texts[ci-1].strip()
                        if re.match(r"\$|/箱|/托|/柜|/件|箱|托|柜", prev):
                            unit = prev
                    break
                desc_parts.append(t_stripped)

            if price is not None and price > 0:
                desc = " ".join(desc_parts)[:60] if desc_parts else ""
                # Skip header-like descriptions
                if any(k in desc for k in ["计费", "库内", "费用", "USD", "单价"]):
                    pass
                else:
                    # Determine warehouse
                    wh = "ALL"
                    if wh_cols:
                        for ci, wh_name in wh_cols:
                            val = _num(row[ci] if ci < len(row) else None)
                            if val is not None and val == price:
                                wh = wh_name; break
                    record["handling"]["inbound"].append({
                        "desc": desc, "price": price, "unit": unit or "",
                        "warehouse": wh,
                    })

        # ── Outbound: 订单出库费 (0-5LB ~ 111-150LB) ──
        elif section == "outbound":
            # Skip header rows — only check first 5 columns to avoid false matches in long descriptions
            header_text = " ".join(texts[:5])
            if any(k in header_text for k in ["计费单位", "计费段", "备注"]):
                continue
            # Find weight tier
            tier = None
            tier_ci = -1
            for ci_t, t in enumerate(texts):
                tier = _parse_tier(t.strip() if t else None)
                if tier:
                    tier_ci = ci_t
                    break
            if tier is None:
                continue
            lo, hi = tier
            if lo == 0 and hi == 0:
                continue

            # Find price — skip tier text and text with weight units
            price = None
            for ci, t in enumerate(texts):
                if ci == tier_ci:
                    continue
                t_s = t.strip() if t else None
                if not t_s:
                    continue
                # Skip texts that look like weight tiers (contain LB/lbs/磅/W/≤)
                if re.search(r"(?:LB|lbs?|磅|[≤<>]|\d+\s*[-~]\s*\d+)", t_s, re.I):
                    continue
                pv = _num(t_s)
                if pv is not None and 0 < pv < 500:
                    price = pv
                    break
            if price is None:
                continue

            # Determine warehouse or single price
            if wh_cols:
                for ci, wh in wh_cols:
                    if ci < len(row):
                        pv = _num(row[ci])
                        if pv is not None and 0 < pv < 500:
                            record["handling"]["outbound"].append({
                                "min_lbs": lo, "max_lbs": hi, "price": pv,
                                "unit": "USD/件", "warehouse": wh, "service": "standard",
                            })
            else:
                record["handling"]["outbound"].append({
                    "min_lbs": lo, "max_lbs": hi, "price": price,
                    "unit": "USD/件", "warehouse": "ALL", "service": "standard",
                })

        # ── Self-pickup tiers ──
        elif section == "self_pickup":
            header_text = " ".join(texts[:5])
            if any(k in header_text for k in ["计费单位", "计费段", "备注"]):
                continue
            tier = None
            tier_ci = -1
            for ci_t, t in enumerate(texts):
                tier = _parse_tier(t.strip() if t else None)
                if tier:
                    tier_ci = ci_t
                    break
            if tier is None:
                continue
            lo, hi = tier
            price = None
            for ci, t in enumerate(texts):
                if ci == tier_ci:
                    continue
                t_s = t.strip() if t else None
                if not t_s:
                    continue
                if re.search(r"(?:LB|lbs?|磅|[≤<>]|\d+\s*[-~]\s*\d+)", t_s, re.I):
                    continue
                pv = _num(t_s)
                if pv is not None and 0 < pv < 500:
                    price = pv
                    break
            if price is None:
                continue
            if wh_cols:
                for ci, wh in wh_cols:
                    if ci < len(row):
                        pv = _num(row[ci])
                        if pv is not None and 0 < pv < 500:
                            record["handling"]["outbound"].append({
                                "min_lbs": lo, "max_lbs": hi, "price": pv,
                                "unit": "USD/件", "warehouse": wh, "service": "self_pickup",
                            })
            else:
                record["handling"]["outbound"].append({
                    "min_lbs": lo, "max_lbs": hi, "price": price,
                    "unit": "USD/件", "warehouse": "ALL", "service": "self_pickup",
                })

        # ── Return: 退货收货/上架费 ──
        elif section == "return":
            if any(k in row_text for k in ["计费单位", "计费段", "单价", "备注", "说明"]):
                continue
            desc_parts = []
            price = None
            for ci, t in enumerate(texts):
                t_stripped = t.strip()
                if not t_stripped: continue
                pv = _num(t_stripped)
                if pv is not None and 0 < pv < 1000 and price is None:
                    price = pv
                    break
                desc_parts.append(t_stripped)
            if price is not None and price > 0:
                desc = " ".join(desc_parts)[:60] if desc_parts else ""
                record["handling"]["inbound"].append({
                    "desc": desc, "price": price, "unit": "",
                    "warehouse": "ALL",
                })

        # ── Storage: 仓储费 (CBM/天) ──
        elif section == "storage":
            if any(k in row_text for k in ["计费单位", "计费段", "单价", "备注", "说明", "批次"]):
                continue
            # Extract age range and price
            age_range = ""
            price = None
            for t in texts:
                t_s = t.strip() if t else ""
                if not t_s: continue
                # Skip FREE rows
                if "free" in t_s.lower():
                    continue
                # Skip rows that are mostly text/notes (long strings, Chinese content)
                if len(t_s) > 20 or re.search(r"[\u4e00-\u9fff]", t_s):
                    # But extract age range from Chinese text
                    m = re.search(r"(\d+[\-~至]\d+\s*自然天|>\s*\d+\s*自然天)", t_s)
                    if m:
                        age_range = m.group(1)
                    continue
                pv = _num(t_s)
                if pv is not None and 0 <= pv < 100 and price is None:
                    price = pv
            if price is not None and price > 0:
                record["handling"]["storage"].append({
                    "desc": "仓储 (%s)" % age_range if age_range else "仓储",
                    "prices": [price],
                    "unit": "USD/CBM/天",
                })

        # ── Value-added: 增值服务费 ──
        elif section == "value_added":
            if any(k in row_text for k in ["计费单位", "收费项目", "服务项目", "备注", "说明", "其它"]):
                continue
            desc_parts = []
            price = None
            unit = ""
            for ci, t in enumerate(texts):
                t_stripped = t.strip()
                if not t_stripped: continue
                # Skip warehouse codes and carrier names
                if re.match(r"^(美[东西南]|仓|Ground|Home|FedEx|每票|每张|每件|每箱|\$)", t_stripped):
                    continue
                # Skip cells with letters or Chinese (like "48 in", "单箱") — only parse pure numbers
                if re.search(r"[a-zA-Z\u4e00-\u9fff]", t_stripped):
                    if not re.match(r"^(USD|单价|\$|价格)", t_stripped):
                        desc_parts.append(t_stripped)
                    continue
                pv = _num(t_stripped)
                if pv is not None and 0 < pv < 5000 and price is None:
                    price = pv
                    # Capture unit from previous cell
                    if ci > 0 and texts[ci-1].strip():
                        unit = texts[ci-1].strip()[:20]
                    break
                if not re.match(r"^(USD|单价|\$|价格)", t_stripped):
                    desc_parts.append(t_stripped)
            if price is not None and price > 0:
                desc = " ".join(desc_parts)[:60] if desc_parts else ""
                record["handling"]["value_added"].append({
                    "desc": desc, "price": price, "unit": unit,
                    "warehouse": "ALL",
                })

    return True
def _try_parse_outbound(rows, record, sheet_name):
    """Find weight-tier rows and extract price from adjacent columns."""
    # Must contain outbound keywords
    text_all = _txt(rows).lower()
    if not any(k in text_all for k in ["订单处理", "出库费", "出库服务", "toc", "一件代发"]):
        return

    # Find warehouse header columns: row that has warehouse codes
    wh_cols = []  # [(col, name)]
    for ri, row in enumerate(rows[:8]):
        for ci, c in enumerate(row):
            if c and isinstance(c, str):
                s = c.strip()
                if re.match(r"^(美[东西南]仓?\s*[A-Z]*|ALL|CA$|NJ$|ATL$|SAV$|TX$|HOU$|GA$|洛杉矶|新泽西|芝加哥|萨凡纳|休斯顿)", s):
                    # Exclude unit labels, non-warehouse text, and postal codes (NJ085, CA923, TX774 etc.)
                    if not re.match(r"^(USD|单价|\$|价格|计费|单位|说明|备注|每)", s):
                        wh_cols.append((ci, s))

    # Scan all rows for weight tiers
    # Find which column has the tier text, and which column(s) have prices
    tier_col = -1
    price_col_start = -1

    for ri, row in enumerate(rows):
        for ci, c in enumerate(row):
            if _is_tier(c):
                tier_col = ci
                # Scan forward to find first column with a numeric price
                for pci in range(ci + 1, min(ci + 6, len(row))):
                    pv = _num(row[pci] if pci < len(row) else None)
                    if pv is not None and pv > 0:
                        price_col_start = pci
                        break
                break
        if tier_col >= 0: break

    if tier_col < 0 or price_col_start < 0: return

    # Determine service type from nearby text (search around first tier row)
    service = "standard"
    first_tier_ri = -1
    for ri2 in range(len(rows)):
        if _is_tier(rows[ri2][tier_col] if tier_col < len(rows[ri2]) else None):
            first_tier_ri = ri2; break
    # Search 8 rows BEFORE first tier for section title
    scan_start = max(0, (first_tier_ri if first_tier_ri >= 0 else 0) - 8)
    scan_end = min(len(rows), (first_tier_ri if first_tier_ri >= 0 else 0) + 3)
    for ri in range(scan_start, scan_end):
        text = " ".join(str(c) for c in rows[ri] if c).lower()
        if "自提" in text or "self" in text or "pickup" in text: service = "self_pickup"
        elif "拒收" in text or "退货" in text or "return" in text: service = "return"
        elif "转运" in text or "批量" in text: service = "transfer"

    # Extract tiers
    seen = set()
    for ri in range(len(rows)):
        row = rows[ri]

        # Stop if we hit a new section (storage, inbound, etc.)
        row_text = " ".join(str(c) for c in row if c).lower()
        if ri > (first_tier_ri if first_tier_ri >= 0 else 0) + 2:
            if any(k in row_text for k in ["仓储费", "存储", "退货", "退货收货", "退货上架", "仓储"]):
                break

        tier_text = row[tier_col] if tier_col < len(row) else None
        tier = _parse_tier(tier_text)
        if tier is None: continue
        lo, hi = tier
        if lo == 0 and hi == 0: continue

        # Determine which columns have prices
        if wh_cols:
            # Multi-warehouse: find which warehouse columns are active
            for ci, wh in wh_cols:
                if ci >= price_col_start:
                    price = _num(row[ci] if ci < len(row) else None)
                    if price is not None and price > 0 and price < 500:  # sane price range
                        key = (lo, hi, wh, service)
                        if key not in seen:
                            seen.add(key)
                            record["handling"]["outbound"].append({
                                "min_lbs": lo, "max_lbs": hi, "price": price,
                                "unit": "USD/件", "warehouse": wh, "service": service,
                            })
                            if wh != "ALL" and wh not in record["warehouses"]:
                                record["warehouses"].append(wh)
        else:
            # Single warehouse: check price_col_start and scan forward if needed
            price = _num(row[price_col_start] if price_col_start < len(row) else None)
            if price is None or price <= 0:
                # Scan forward for price
                for pci in range(price_col_start + 1, min(price_col_start + 4, len(row))):
                    pv = _num(row[pci] if pci < len(row) else None)
                    if pv is not None and pv > 0:
                        price = pv; break
            if price is not None and price > 0 and price < 500:
                key = (lo, hi, "ALL", service)
                if key not in seen:
                    seen.add(key)
                    record["handling"]["outbound"].append({
                        "min_lbs": lo, "max_lbs": hi, "price": price,
                        "unit": "USD/件", "warehouse": "ALL", "service": service,
                    })

        # Stop at section break
        if tier_text is None and ri > 5:
            text = " ".join(str(c) for c in row if c)
            if "备注" in text or "注" in text: break

# ── Inbound ────────────────────────────────────────────────────────
def _try_parse_inbound(rows, record, sheet_name):
    text_all = _txt(rows).lower()
    if not any(k in text_all for k in ["入库", "卸货", "卸柜", "receiving", "devanning"]):
        return
    # Skip if this is purely an outbound sheet (订单处理 with weight tiers)
    if "订单处理" in text_all and not any(k in text_all for k in ["卸柜", "卸货", "入库费", "devanning"]):
        return

    for ri, row in enumerate(rows):
        texts = [str(c).strip() for c in row if c is not None and str(c).strip()]
        if not texts: continue
        # Skip header rows
        if any(k in texts[0] for k in ["服务项目", "Items", "收费项目"]): continue
        # Find first price
        for i, t in enumerate(texts):
            price = _num(t)
            if price is not None and 0 < price < 100000 and not re.match(r"^20\d{2}$", t.strip()):
                desc = " ".join(texts[:i])[:80] if i > 0 else (texts[0][:80] if texts else "")
                unit = texts[i+1][:30] if i+1 < len(texts) else ""
                record["handling"]["inbound"].append({"desc": desc, "price": price, "unit": unit})
                break

# ── Storage ────────────────────────────────────────────────────────
def _try_parse_storage(rows, record, sheet_name):
    text_all = _txt(rows).lower()
    if not any(k in text_all for k in ["仓储", "存储", "storage", "仓租"]):
        return
    # Must have price data (not just text)
    has_price = False
    for row in rows:
        for c in row:
            v = _num(c)
            if v is not None and 0 <= v < 100:
                has_price = True; break
        if has_price: break
    if not has_price: return

    for ri, row in enumerate(rows):
        texts = [str(c).strip() for c in row if c is not None and str(c).strip()]
        if not texts: continue
        # Find warehouse code
        wh = None
        for t in texts:
            if re.match(r"^(CAP|MEM|HOU|SAV|CAT|CHI|NJF|LCCA\d*|LCNJ\d*|LCGA\d*|CA|NJ|SAV|TX|GA|美[东西南])", t):
                wh = t; break
        if wh is None: continue
        # Collect prices from this row
        prices = [_num(t) for t in texts if _num(t) is not None and _num(t) >= 0]
        prices = [p for p in prices if p is not None]
        if prices:
            record["handling"]["storage"].append({
                "desc": "仓储 (%s)" % wh, "prices": prices, "warehouse": wh
            })

# ── Value-added ────────────────────────────────────────────────────
def _try_parse_value_added(rows, record, sheet_name):
    text_all = _txt(rows).lower()
    if not any(k in text_all for k in ["增值服务", "value added"]):
        return
    for ri, row in enumerate(rows):
        texts = [str(c).strip() for c in row if c is not None and str(c).strip()]
        if not texts: continue
        if any(k in texts[0] for k in ["增值", "收费", "服务项目", "Value", "服务名称"]): continue
        for i, t in enumerate(texts):
            price = _num(t)
            if price is not None and 0 < price < 100000 and not re.match(r"^20\d{2}$", t.strip()):
                desc = " ".join(texts[:i])[:80] if i > 0 else (texts[0][:80] if texts else "")
                unit = texts[i+1][:30] if i+1 < len(texts) else ""
                record["handling"]["value_added"].append({"desc": desc, "price": price, "unit": unit})
                break

# ── Surcharges ─────────────────────────────────────────────────────
def _try_parse_surcharge(rows, record, sheet_name):
    text_all = _txt(rows).lower()
    if not any(k in text_all for k in ["附加费", "surcharge", "ahs", "oversize"]):
        return

    group = {"name": sheet_name, "items": []}
    category = ""
    for ri, row in enumerate(rows):
        texts = [str(c).strip() for c in row if c is not None and str(c).strip()]
        if not texts: continue
        full = " ".join(texts)

        # Update category from col0 or col1
        for t in texts[:2]:
            if re.search(r"dimension|dimensions|超长", t, re.I): category = "AHS_Dimension"
            elif re.search(r"weight|超重", t, re.I): category = "AHS_Weight"
            elif re.search(r"packaging|异形", t, re.I): category = "AHS_Packaging"
            elif re.search(r"AHS|附加处理", t, re.I): category = "AHS"
            elif re.search(r"Oversize|超尺寸", t, re.I): category = "Oversize"
            elif re.search(r"住宅|residential", t, re.I): category = "Residential"
            elif re.search(r"燃油|fuel", t, re.I): category = "Fuel"
            elif re.search(r"旺季|demand|peak", t, re.I): category = "Peak"
            elif re.search(r"偏远|remote|DAS", t, re.I): category = "Remote"
            elif re.search(r"地址|address", t, re.I): category = "Address"

        # Find zone (col2) and price (col3)
        zone = None; price = None
        for t in texts:
            m = re.match(r"^(\d+)$", t.strip())
            if m and not zone: zone = "Zone" + m.group(1)
            v = _num(t)
            if v is not None and 0 < v < 10000 and price is None:
                # Skip zone numbers (1-8 are zones, but we already captured zone)
                if zone and v <= 8 and re.match(r"^\d+$", t.strip()): continue
                price = v

        if price is not None:
            # Validate: zone must be Zone2-Zone8 (standard) or None
            if zone:
                zone_num = int(zone.replace("Zone", ""))
                if zone_num > 10:
                    continue  # Skip postal codes and non-standard zones
            # Validate: surcharge prices should be reasonable ($0.10 - $500)
            if price > 500 or price < 0.05:
                continue
            sub_desc = category
            for t in texts:
                if re.search(r"Dimensions|Weight|Packaging|Charge|Surcharge|Fuel|DAS|Residential", t, re.I):
                    sub_desc = t.split("\n")[0][:40]; break
            group["items"].append({"category": category, "desc": sub_desc, "price": price, "zone": zone})

    if group["items"]:
        record["surcharges"].append(group)

# ── Shipping ───────────────────────────────────────────────────────
def _parse_zone_headers(rows):
    """扫描所有候选 zone header 行。返回 [{ri, segs:[{cols:{col:zone}, min_col, max_col}]}]
    支持水平分块（GA：新旧价并排）与垂直分块（PM：新旧价上下堆叠）。"""
    candidates = []
    for ri, row in enumerate(rows[:60]):
        blocks = []
        for ci, c in enumerate(row):
            if c is None:
                continue
            cs = str(c).strip().lower()
            m2 = re.match(r"^(\d+)\s*区\s*/\s*(\d+)\s*区\s*$", cs)
            if m2:
                b = int(m2.group(2))
                if 2 <= b <= 3:
                    blocks.append((ci, "Zone" + str(b)))
                continue
            m3 = re.match(r"^(\d+)\s*区\s*$", cs)
            if m3:
                z = int(m3.group(1))
                if 2 <= z <= 8:
                    blocks.append((ci, "Zone" + str(z)))
                continue
            m = re.match(r"^(\d+)\s*&\s*(\d+)$", cs)
            if m:
                a, b = int(m.group(1)), int(m.group(2))
                if b == a + 1 and 1 <= a <= 2:
                    blocks.append((ci, "Zone" + str(b)))
            elif re.match(r"^zone\s*(\d+)$", cs):
                blocks.append((ci, "Zone" + re.match(r"^zone\s*(\d+)$", cs).group(1)))
            elif re.match(r"^[3-8]$", cs):
                blocks.append((ci, "Zone" + cs))
        if len(blocks) < 3:
            continue
        blocks.sort(key=lambda b: b[0])
        # 水平分块：连续列归一组
        segs = []
        cur = [blocks[0]]
        for bl in blocks[1:]:
            if bl[0] == cur[-1][0] + 1:
                cur.append(bl)
            else:
                segs.append(cur)
                cur = [bl]
        segs.append(cur)
        segs = [{"cols": {c: z for c, z in seg}, "min_col": seg[0][0], "max_col": seg[-1][0]}
                for seg in segs if len(seg) >= 3]
        if segs:
            candidates.append({"ri": ri, "segs": segs})
    return candidates


def _parse_usps_block(rows, seg, header_ri):
    """解析一个 zone 数据块（header 行下方从 header_ri+1 到 seg 区域无值为止）。
    返回 None 表示解析失败。"""
    min_col, max_col = seg["min_col"], seg["max_col"]
    seg_cols = seg["cols"]
    data_start = header_ri + 1
    # 重量列：seg 左侧找数值列
    weight_col, weight_unit = None, "lbs"
    for ci in range(0, min_col):
        for ri in range(data_start, min(data_start + 5, len(rows))):
            v = _num(rows[ri][ci] if ci < len(rows[ri]) else None)
            if v is not None and 0 < v < 1000000:
                if rows[ri] and ci < len(rows[ri]) and isinstance(rows[ri][ci], str) and ci + 1 < len(rows[ri]):
                    nxt = rows[ri][ci + 1] if rows[ri] and ci + 1 < len(rows[ri]) else None
                weight_col = ci
                break
        if weight_col is not None:
            break
    if weight_col is None:
        return None
    # 单位：重量列后续列若是 "1 OZ" 文本 -> 重量为克；表头写 lbs -> 磅；kg -> 公斤
    # 检查数据行 weight_col+1 是否为 OZ 标签
    for ri in range(data_start, min(data_start + 6, len(rows))):
        row = rows[ri]
        if ci + 1 < len(row) and isinstance(row[ci + 1], str) and re.search(r"\boz\b", str(row[ci + 1]), re.I):
            weight_unit = "g"
            break
    # 表头行本身标注单位
    for ri in range(header_ri - 1, -1, -1):
        row = rows[ri]
        if weight_col < len(row) and row[weight_col] and isinstance(row[weight_col], str):
            h = row[weight_col].lower()
            if "lb" in h:
                weight_unit = "lbs"
            elif "g" in re.sub(r"[（）()]", " ", h) and "克" in h:
                weight_unit = "g"
            elif "kg" in h or "公斤" in h:
                weight_unit = "kg"
            break
    unit_factor = {"lbs": 1.0, "g": 0.00220462, "kg": 2.20462}.get(weight_unit, 1.0)

    zones = {zn: {} for zn in seg_cols.values()}
    min_w, max_w = float("inf"), 0
    for ri in range(data_start, len(rows)):
        row = rows[ri]
        w = _num(row[weight_col] if weight_col < len(row) else None)
        if w is None or w <= 0:
            continue
        has_data = any(_num(row[ci] if ci < len(row) else None) is not None for ci in seg_cols)
        if not has_data:
            # 空白行不一定=块结束，但若连续2行无数据则停止（进入下一个块/注记）
            if ri > data_start and w == 0:
                break
            continue
        w_lbs = w * unit_factor
        min_w = min(min_w, w_lbs); max_w = max(max_w, w_lbs)
        w_key = str(round(w_lbs, 2)) if w_lbs != int(w_lbs) else str(int(w_lbs))
        for ci, zn in seg_cols.items():
            v = _num(row[ci] if ci < len(row) else None)
            if v is not None:
                zones[zn][w_key] = v
    if max_w == float("inf") or max_w == 0:
        return None
    return {"zones": zones, "min_weight": min_w, "max_weight": max_w}


def _try_parse_usps_dual(rows, record, sheet_name):
    """USPS GA/PM 专用：纯数字 zone 头(`1&2`/`1区/2区`,`3`..`8`) + 新旧价多块并存。
    水平并排取最右、垂直堆叠取最下（均视为最新）。返回 True 表示已解析。"""
    if not re.search(r"usps", sheet_name, re.I):
        return False
    candidates = _parse_zone_headers(rows)
    if not candidates:
        return False
    # 垂直：取最靠下的候选行；该行内水平：取最右 seg
    last = candidates[-1]
    chosen_rows = [c for c in candidates if c["ri"] >= 0]
    best = None
    # 优先取数据最多的块（避免 header 行重复但下方无数据）
    def _row_count(seg, hri):
        n = 0
        for ri in range(hri + 1, min(hri + 200, len(rows))):
            if any(_num(rows[ri][ci] if ci < len(rows[ri]) else None) is not None for ci in seg["cols"]):
                n += 1
        return n
    # 遍历所有候选，选 (数据行数最多, 更靠下) 的块
    scored = []
    for cand in candidates:
        for seg in cand["segs"]:
            scored.append((_row_count(seg, cand["ri"]), cand["ri"], seg, cand["ri"]))
    scored.sort(key=lambda s: (s[0], s[1]))
    if not scored or scored[-1][0] < 2:
        return False
    best_n, best_ri, best_seg, _ = scored[-1]
    if len(scored) > 1:
        print(f"[usps] {sheet_name} 发现 {len(scored)} 个价格块，取 {best_n} 行数据块", flush=True)
    parsed = _parse_usps_block(rows, best_seg, best_ri)
    if not parsed:
        return False

    # 燃油与附加费（沿用通用解析）
    fuel_pct = 0.0
    carrier_surcharges = _parse_shipping_surcharges(rows)
    for sc in carrier_surcharges:
        if sc.get("category") == "Fuel" and sc.get("zone") is None:
            fuel_pct = sc["price"]
            carrier_surcharges = [s for s in carrier_surcharges if s.get("category") != "Fuel"]
            break
    record["shipping"].append({
        "carrier": "USPS", "sheet": sheet_name,
        "zones": parsed["zones"], "min_weight": parsed["min_weight"],
        "max_weight": parsed["max_weight"],
        "fuel_surcharge_pct": fuel_pct,
        "surcharges": carrier_surcharges,
    })
    return True


def _try_parse_shipping(rows, record, sheet_name):
    """Parse Zone×weight matrix. Must have ≥3 zone columns."""
    # Detect zone header row
    zone_cols = {}
    data_start = 0
    for ri, row in enumerate(rows[:15]):
        for ci, c in enumerate(row):
            if c is not None:
                cs = str(c).strip()
                m = re.match(r"^zone\s*(\d+)$", cs, re.I)
                if m: zone_cols[ci] = "Zone" + m.group(1)
        if len(zone_cols) >= 3:
            data_start = ri + 1
            break
    if len(zone_cols) < 3: return

    # Detect carrier
    carrier = sheet_name
    all_text = _txt(rows[:10]).lower()
    for cn, kn in [("FedEx", "fedex"), ("UPS", "ups"), ("Amazon", "amazon"),
                   ("USPS", "usps"), ("WP", "wp"), ("XLM", "xlm")]:
        if kn in all_text or kn in sheet_name.lower():
            carrier = cn; break

    # Find weight column (left of first zone col)
    min_zc = min(zone_cols.keys())
    weight_col = -1
    for ci in range(min_zc):
        for ri in range(data_start, min(data_start + 5, len(rows))):
            v = _num(rows[ri][ci] if ci < len(rows[ri]) else None)
            if v is not None and 0 < v < 10000:
                weight_col = ci; break
        if weight_col >= 0: break
    if weight_col < 0: return

    # Detect weight unit from header row(s) — prefer lbs column over kg column
    weight_unit = "lbs"
    for ri in range(min(data_start + 1, 15)):
        row = rows[ri]
        if weight_col < len(row) and row[weight_col] and isinstance(row[weight_col], str):
            hdr = row[weight_col].lower()
            if "oz" in hdr or "ounce" in hdr:
                weight_unit = "oz"
            elif "kg" in hdr or "公斤" in hdr:
                weight_unit = "kg"
            if weight_unit == "kg":
                for ci2 in range(weight_col - 1, -1, -1):
                    for ri2 in range(data_start, min(data_start + 5, len(rows))):
                        v2 = _num(rows[ri2][ci2] if ci2 < len(rows[ri2]) else None)
                        if v2 is not None and 0 < v2 < 10000:
                            if ri2 < len(rows) and ci2 < len(rows[ri2]) and rows[ri2][ci2] and isinstance(rows[ri2][ci2], str):
                                h2 = rows[ri2][ci2].lower()
                                if "lb" in h2 or "磅" in h2 or "lbs" in h2:
                                    weight_col = ci2
                                    weight_unit = "lbs"
                                    break
                    if weight_unit == "lbs":
                        break

    unit_factor = {"lbs": 1.0, "lb": 1.0, "oz": 1/16.0, "kg": 2.20462, "公斤": 2.20462}.get(weight_unit, 1.0)

    zones = {zn: {} for zn in zone_cols.values()}
    min_w, max_w = float("inf"), 0

    for ri in range(data_start, len(rows)):
        row = rows[ri]
        w = _num(row[weight_col] if weight_col < len(row) else None)
        if w is None or w <= 0: continue
        has_data = any(_num(row[ci] if ci < len(row) else None) is not None for ci in zone_cols)
        if not has_data: continue
        w_lbs = w * unit_factor
        min_w = min(min_w, w_lbs); max_w = max(max_w, w_lbs)
        w_key = str(round(w_lbs, 2)) if w_lbs != int(w_lbs) else str(int(w_lbs))
        for ci, zn in zone_cols.items():
            v = _num(row[ci] if ci < len(row) else None)
            if v is not None: zones[zn][w_key] = v

    if max_w == float("inf") or max_w == 0: return

    # Fuel surcharge — detect "16%", "0.16", "燃油附加费126%" etc.
    fuel_pct = 0.0
    for ri in range(len(rows)):
        text = " ".join(str(c) for c in rows[ri] if c)
        if re.search(r"燃油附加|燃油附加费|fuel\s*surcharge", text, re.I):
            # Try "XX%" pattern first
            m = re.search(r"(\d{1,3})%", text)
            if m:
                pct_val = float(m.group(1))
                fuel_pct = pct_val / 100.0 if pct_val <= 100 else (pct_val - 100) / 100.0
            else:
                m = re.search(r"(?<!\d)0\.\d+", text)
                if m: fuel_pct = float(m.group(0))
            if fuel_pct > 0:
                break
    # Fallback: scan for standalone "燃油" rows with numeric fuel rate
    if fuel_pct == 0.0:
        for ri in range(len(rows)):
            text = " ".join(str(c) for c in rows[ri] if c)
            if re.search(r"燃油|fuel", text, re.I):
                m = re.search(r"(\d{1,3})%", text)
                if m:
                    pct_val = float(m.group(1))
                    fuel_pct = pct_val / 100.0 if pct_val <= 100 else (pct_val - 100) / 100.0
                    break
                else:
                    m = re.search(r"(?<!\d)0\.\d+", text)
                    if m:
                        fuel_pct = float(m.group(0))
                        break

    # Parse carrier-specific surcharges from right side of sheet (AHS, Residential, DAS, etc.)
    carrier_surcharges = _parse_shipping_surcharges(rows)

    # Extract fuel surcharge from parsed surcharges if present
    for sc in carrier_surcharges:
        if sc.get("category") == "Fuel" and sc.get("zone") is None:
            fuel_pct = sc["price"]
            carrier_surcharges = [s for s in carrier_surcharges if s.get("category") != "Fuel"]
            break

    record["shipping"].append({
        "carrier": carrier, "sheet": sheet_name,
        "zones": zones, "min_weight": min_w, "max_weight": max_w,
        "fuel_surcharge_pct": fuel_pct,
        "surcharges": carrier_surcharges,
    })


def _try_parse_eu_shipping(rows, record, sheet_name):
    """欧洲渠道：国家×重量段 报价（乐歌/盘古德国仓等）。zeu 无数字分区 → zones 键=国家。
    支持三类：
      A 一维：表头 [计费重量kg | <国别>]，行 = kg→价格
      B 列头：段标签在表头行（0-2KG / 0.01-10）、国家在行首、价格在段列
      C 行头：国家/段/价格 逐行（盘古DHL 分段式）
    """
    if not rows or not rows[0]:
        return False

    # ── A 一维：计费重量kg | 国别 ──
    if "计费重量" in str(rows[0][0] if rows[0] else ""):
        dst = ""
        if len(rows[0]) > 1 and rows[0][1]:
            dst = str(rows[0][1]).strip()[:6]
        zones = {}
        for ri in range(1, len(rows)):
            row = rows[ri]
            if not row: continue
            w, p = _num(row[0]), _num(row[1] if len(row) > 1 else None)
            if w is None or p is None or w <= 0: continue
            z = zones.setdefault(dst or "DE", {})
            z[str(w) if w == int(w) else str(round(w, 2))] = p
        if zones:
            wk = [float(k) for v in zones.values() for k in v]
            record["shipping"].append({"carrier": "EU", "sheet": sheet_name,
                                       "zones": zones, "min_weight": min(wk),
                                       "max_weight": max(wk), "fuel_surcharge_pct": 0.0,
                                       "surcharges": [], "eu": True, "kind": "1d"})
            return True

    # ── A2 一维(限重/报价)：col0=重量段 col1=欧元价（乐歌德国 GLS/DHL/DPD 等）──
    top2 = " ".join(str(c) for row in rows[:3] for c in row if c)
    if "限重" in top2 or "报价（欧元）" in top2 or "报价(欧元)" in top2:
        dst = "DE"
        zones = {}
        for ri in range(1, len(rows)):
            row = rows[ri]
            if not row or not row[0]: continue
            cs = str(row[0]).strip()
            if not re.search(r"\d+\.?\d*\s*[-~––]\s*\d+", cs):
                continue
            p = _num(row[1] if len(row) > 1 else None)
            if p is None or p <= 0: continue
            zones.setdefault(dst, {})[cs] = p
        if zones:
            record["shipping"].append({"carrier": "EU", "sheet": sheet_name,
                                       "zones": zones, "min_weight": None, "max_weight": None,
                                       "fuel_surcharge_pct": 0.0, "surcharges": [],
                                       "eu": True, "kind": "1d"})
            return True

    # ── B 列头：段标签行+国家行 ──
    seg_hdr, seg_cols = -1, []
    for ri, row in enumerate(rows[:8]):
        seg_cols = []
        for ci, c in enumerate(row):
            if c is None or ci == 0: continue
            cs = str(c).strip()
            if re.match(r"^\d+\.?\d*\s*[-~––]\s*\d+", cs) or re.match(r"^\d+\s?kg", cs, re.I) or \
               re.match(r"^\d+\.\d+\s*[-~]\s*\d+", cs):
                seg_cols.append((ci, cs))
        if len(seg_cols) >= 3:
            seg_hdr = ri; break
    if seg_hdr >= 0:
        zones = {}
        for ri in range(seg_hdr + 1, min(seg_hdr + 120, len(rows))):
            row = rows[ri]
            if not row: continue
            name = str(row[0] or "").strip()
            if not name: continue
            m = re.match(r"^([A-Za-z�]+)\s*\(([A-Z]{2})\)", name)
            if not m and not re.search(r"[\u4e00-\u9fa5]", name):
                continue
            if re.match(r"^(Price|价格|kg|KG|国家|Country)", name):
                continue
            country = name.strip()[:26]
            segs = {}
            for ci, label in seg_cols:
                v = _num(row[ci] if ci < len(row) else None)
                if v is not None and v > 0:
                    segs[label] = v
            if segs:
                zones[country] = segs
        if zones:
            record["shipping"].append({"carrier": "EU", "sheet": sheet_name,
                                       "zones": zones, "min_weight": None, "max_weight": None,
                                       "fuel_surcharge_pct": 0.0, "surcharges": [],
                                       "eu": True, "kind": "matrix"})
            return True

    # ── C 行头：国家/重量段/价格 ──
    hri = -1
    for ri, row in enumerate(rows[:8]):
        t = " ".join(str(c) for c in row if c)
        if "countr" in t.lower() and ("重量段" in t or "kg" in t.lower()):
            hri = ri; break
    if hri < 0:
        return False
    zones = {}
    for ri in range(hri + 1, len(rows)):
        row = rows[ri]
        if not row: continue
        texts = [str(c).strip() for c in row if c is not None and str(c).strip()]
        if not texts: continue
        country = ""
        for t in texts[:3]:
            m = re.search(r"\(([A-Z]{2})\)", t)
            if m: country = t[:t.index("(")].strip() + "." + m.group(1); break
            if re.search(r"[\u4e00-\u9fa5]", t) and "kg" not in t.lower():
                country = re.sub(r"^.*?\)\s*", "", t).strip()[:20] or t[:20]; break
        if not country: continue
        seg = ""
        for ci, c in enumerate(row):
            if c is None: continue
            cs = str(c).strip()
            if re.search(r"\d+\.?\d*\s*[-~––]\s*\d+\s*(kg|KG|Kg)?$", cs):
                seg = cs; break
        if seg and len(row) > 2:
            v = _num(row[2])
            if v is not None and 0 < v < 100000:
                zones.setdefault(country, {})[seg] = v
    if not zones:
        return False
    record["shipping"].append({"carrier": "EU", "sheet": sheet_name,
                               "zones": zones, "min_weight": None, "max_weight": None,
                               "fuel_surcharge_pct": 0.0, "surcharges": [],
                               "eu": True, "kind": "tiered"})
    return True


def _parse_shipping_surcharges(rows):
    """Parse surcharges from the right side of a shipping sheet.
    Supports two formats:
    1. Traditional (乐歌旧版): per-zone rows with $price
    2. Zone-grouped (SMART/乐舱新版): Zone2|Zones 3–4|Zones 5–6|Zones 7+ as column headers,
       with plain numbers as values.
    Returns list of {category, zone, price, min_weight}."""
    surcharges = []

    # Phase 1: Detect zone-grouped header row (cols 9+)
    zone_col_map = {}  # col_index -> list of zone names
    header_ri = -1
    for ri, row in enumerate(rows[:20]):
        for ci in range(9, min(len(row), 25)):
            c = row[ci]
            if c and isinstance(c, str):
                zm = re.search(r"Zones?\s*(\d+)(?:\s*[\u2013\-]\s*(\d+))?(?:\+)?", c.strip(), re.I)
                if zm:
                    z1 = int(zm.group(1))
                    z2 = int(zm.group(2)) if zm.group(2) else z1
                    zone_col_map[ci] = ["Zone%d" % z for z in range(z1, z2 + 1)]
        if len(zone_col_map) >= 3:
            header_ri = ri
            break

    if len(zone_col_map) >= 3:
        return _parse_surcharges_grouped(rows, zone_col_map, header_ri)
    else:
        return _parse_surcharges_legacy(rows)


def _parse_surcharges_grouped(rows, zone_col_map, header_ri):
    """Parse zone-grouped surcharges (SMART/乐舱 format)."""
    surcharges = []
    current_category = None
    current_condition = None

    for ri in range(header_ri + 1, len(rows)):
        row = rows[ri]

        right_texts = []
        for ci in range(9, min(len(row), 25)):
            c = row[ci]
            if c is not None:
                right_texts.append(str(c).strip())

        if not right_texts:
            current_category = None
            continue

        full_text = " ".join(right_texts)
        full_lower = full_text.lower()

        # Skip fuel surcharge lines — extract percentage for fuel storage
        if re.search(r"燃油|fuel\s*surcharge", full_lower):
            fm = re.search(r"(\d{1,3})%", full_text)
            if fm:
                pct = float(fm.group(1))
                surcharges.append({"category": "Fuel", "zone": None,
                    "price": pct / 100.0 if pct <= 100 else (pct - 100) / 100.0, "min_weight": None})
            else:
                fm = re.search(r"0\.\d+", full_text)
                if fm:
                    surcharges.append({"category": "Fuel", "zone": None,
                        "price": float(fm.group(0)), "min_weight": None})
            continue

        # Update category — check all right-side text cols for keywords
        # IMPORTANT: order matters — more specific patterns first
        cat_detected = False
        for t in right_texts:
            tl = t.lower()
            # Demand (seasonal) — must check BEFORE residential/oversize/ahs
            if re.search(r"demand", tl, re.I):
                current_category = "Demand"; current_condition = None; cat_detected = True; break
            # Oversize — check BEFORE AHS_Dimension (both contain 超尺寸)
            elif re.search(r"oversize|超大附加|超最大尺寸", tl, re.I):
                current_category = "Oversize"; current_condition = None; cat_detected = True; break
            # DAS (Delivery Area Surcharge)
            elif re.search(r"delivery\s*area|偏远地区费|das\s*[–\-]", tl, re.I):
                current_category = "DAS"; current_condition = None; cat_detected = True; break
            # AHS sub-types (specific first)
            elif re.search(r"ahs\s*[–\-–]\s*dimension|dimension.*gd|最长边.*48|次长边.*30|围长.*105|体积.*10.?368", tl, re.I):
                current_category = "AHS_Dimension"; current_condition = None; cat_detected = True; break
            elif re.search(r"ahs\s*[–\-–]\s*weight|weight.*gd|超重附加|实际重量.*50\s*lbs|重量.*50", tl, re.I):
                current_category = "AHS_Weight"; current_condition = {"min_weight": 50}; cat_detected = True; break
            elif re.search(r"ahs\s*[–\-–]\s*packag|packag.*gd|非标准.*包装|没有完全装入|外包装非瓦楞|可收缩|拉伸|软包装|圆柱形|金属.*捆扎|损坏", tl, re.I):
                current_category = "AHS_Packaging"; current_condition = None; cat_detected = True; break
            elif re.search(r"additional\s*handling|额外处理", tl, re.I):
                # Generic AHS — refine from first 3 right-side texts (col9-col11), skip long descriptions
                sub_texts = " ".join(right_texts[:3]).lower()
                if re.search(r"weight|超重附加|50\s*lbs", sub_texts):
                    current_category = "AHS_Weight"; current_condition = {"min_weight": 50}
                elif re.search(r"dimension|dimension.*gd|尺寸|48\s*inch|最长边", sub_texts):
                    current_category = "AHS_Dimension"; current_condition = None
                elif re.search(r"packag|packag.*gd|包装|瓦楞", sub_texts):
                    current_category = "AHS_Packaging"; current_condition = None
                else:
                    current_category = "AHS"; current_condition = None
                cat_detected = True; break
            # Residential — check AFTER demand/oversize to avoid false match
            elif re.search(r"residential|住宅地址附", tl, re.I):
                current_category = "Residential"; current_condition = None; cat_detected = True; break
            elif re.search(r"address.*correct|地址修正", tl, re.I):
                current_category = "Address_Correction"; current_condition = None; cat_detected = True; break
            elif re.search(r"unauthorized", tl, re.I):
                current_category = "Unauthorized"; current_condition = None; cat_detected = True; break

        if not current_category:
            continue

        # Also detect AHS sub-category from condition text — only refine if parent is generic AHS
        if current_category in ("AHS", None):
            # Only check first 3 right-side texts (col9-col11) for sub-type, not descriptions
            for t in right_texts[:3]:
                tl = t.lower()
                if re.search(r"ahs\s*[–\-–]\s*dimension|dimension.*gd|最长边.*48|次长边.*30|围长.*105|体积.*10.?368", tl, re.I):
                    current_category = "AHS_Dimension"; current_condition = None; break
                elif re.search(r"ahs\s*[–\-–]\s*weight|weight.*gd|超重附加|实际重量.*50\s*lbs|重量.*>.*50|超重附加费", tl, re.I):
                    current_category = "AHS_Weight"; current_condition = {"min_weight": 50}; break
                elif re.search(r"ahs\s*[–\-–]\s*packag|packag.*gd|没有完全装入|外包装非瓦楞|可收缩|拉伸|软包装|圆柱形|金属.*捆扎|损坏|非标准包装附加费", tl, re.I):
                    current_category = "AHS_Packaging"; current_condition = None; break

        # Check if this row has any zone column data
        row_has_data = False
        for ci in zone_col_map:
            if ci < len(row) and row[ci] is not None:
                cs = str(row[ci]).strip()
                if cs and re.search(r"\d", cs):
                    row_has_data = True
                    break

        if not row_has_data:
            continue

        # Extract prices from zone columns
        for ci, zones in zone_col_map.items():
            if ci >= len(row) or row[ci] is None:
                continue
            cs = str(row[ci]).strip()
            if not cs:
                continue
            pv = None
            pm = re.search(r"\$?(\d+\.?\d*)", cs)
            if pm:
                pv = float(pm.group(1))
            if pv is not None and pv > 0 and pv < 500:
                if re.search(r"\d{4}[./]\d{1,2}", cs): continue  # skip dates
                if re.match(r"^\d{5}$", cs): continue  # skip postal codes
                for zn in zones:
                    surcharges.append({
                        "category": current_category, "zone": zn,
                        "price": pv, "min_weight": (current_condition or {}).get("min_weight"),
                    })

    # Deduplicate: keep first per (category, zone) — regular surcharges appear first,
    # demand seasonal add-ons appear later and should be ignored.
    seen = set()
    unique = []
    for s in surcharges:
        key = (s["category"], s["zone"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(s)
    return unique


def _parse_surcharges_legacy(rows):
    """Parse surcharges from traditional format (per-zone rows with $price)."""
    surcharges = []
    current_category = None
    current_condition = None

    for ri, row in enumerate(rows):
        right_texts = []
        for ci in range(10, min(len(row), 25)):
            c = row[ci]
            if c:
                right_texts.append(str(c).strip())

        if not right_texts:
            continue

        full_text = " ".join(right_texts)
        full_lower = full_text.lower()

        # Update category context from cols 11-12
        if re.search(r"additional\s*handling|额外处理", full_lower):
            if re.search(r"weight|重量|超过.*50", full_lower):
                current_category = "AHS_Weight"
                current_condition = {"min_weight": 50}
            elif re.search(r"dimension|尺寸|超过.*48", full_lower):
                current_category = "AHS_Dimension"
                current_condition = None
            elif re.search(r"packag|包装", full_lower):
                current_category = "AHS_Packaging"
                current_condition = None
            else:
                current_category = "AHS"
                current_condition = None
        elif re.search(r"oversize|超大超尺寸", full_lower):
            current_category = "Oversize"
            if re.search(r"110", full_lower):
                current_condition = {"min_weight": 110}
            else:
                current_condition = None
        elif re.search(r"residential.*delivery|住宅地址附加费", full_lower):
            current_category = "Residential"
            current_condition = None
        elif re.search(r"delivery.*area.*surcharge.*remote|超级偏远", full_lower):
            current_category = "DAS_Remote"
            current_condition = None
        elif re.search(r"delivery.*area.*surcharge.*extended|超偏远", full_lower):
            current_category = "DAS_Extended"
            current_condition = None
        elif re.search(r"delivery.*area.*surcharge|偏远附加费", full_lower):
            current_category = "DAS"
            current_condition = None
        elif re.search(r"signature|签名", full_lower):
            current_category = "Signature"
            current_condition = None
        elif re.search(r"address.*correct|地址修正", full_lower):
            current_category = "Address_Correction"
            current_condition = None
        elif re.search(r"demand", full_lower):
            current_category = "Demand"
            current_condition = None
        elif re.search(r"燃油|fuel", full_lower) and "surcharge" not in full_lower:
            continue

        if not current_category:
            continue

        # Find zone and price in this row
        zones_found = []
        price_found = None
        for t in right_texts:
            zm = re.search(r"Zone\s*(\d+)", t, re.I)
            if zm:
                zones_found.append("Zone" + zm.group(1))
            pm = re.search(r"\$(\d+\.?\d*)", t)
            if pm:
                price_found = float(pm.group(1))

        if price_found is not None and price_found < 500:
            if re.search(r"\d{4}[./]\d{1,2}[./]\d{1,2}", full_text):
                continue
            if zones_found:
                for zn in zones_found:
                    surcharges.append({
                        "category": current_category, "zone": zn,
                        "price": price_found,
                        "min_weight": (current_condition or {}).get("min_weight"),
                    })
            else:
                if current_category not in ("Demand", "Oversize"):
                    surcharges.append({
                        "category": current_category, "zone": None,
                        "price": price_found,
                        "min_weight": (current_condition or {}).get("min_weight"),
                    })

    # Deduplicate
    seen = {}
    unique = []
    for s in surcharges:
        key = (s["category"], s["zone"])
        if key in seen:
            if s["category"] == "Residential" and s["price"] < seen[key]["price"]:
                unique = [x if x is not seen[key] else s for x in unique]
                seen[key] = s
            continue
        seen[key] = s
        unique.append(s)
    return unique

# ── Compare ────────────────────────────────────────────────────────
def compare_pricing(records, weight, zone="Zone5", warehouse=None, fee_type="total", global_fuel_pct=None):
    results = []
    for rid, rec in records.items():
        h = _find_outbound(rec, weight, warehouse)
        s, s_fee, s_surch, s_fuel = _find_shipping_detail(rec, weight, zone, global_fuel_pct=global_fuel_pct)
        total = h + s_fee + s_surch + s_fuel
        # Get fuel pct for display
        fuel_pct_val = 0.0
        if global_fuel_pct is not None and global_fuel_pct > 0:
            fuel_pct_val = global_fuel_pct * 100
        else:
            for st in rec.get("shipping", []):
                zn = st.get("zones", {}).get(zone, {})
                if zn:
                    fuel_pct_val = st.get("fuel_surcharge_pct", 0.0) * 100
                    break
        results.append({
            "rid": rid, "name": rec.get("name", ""),
            "warehouses": rec.get("warehouses", []),
            "handling": round(h, 2),
            "shipping": round(s, 2),
            "surcharges": round(s_surch, 2),
            "fuel_surcharge": round(s_fuel, 2),
            "fuel_pct": round(fuel_pct_val, 1),
            "total": round(total, 2),
            "detail": {
                "carrier": s,
                "zone": zone,
                "weight": weight,
            },
        })
    results.sort(key=lambda x: x["total"])
    return results


def _find_outbound(rec, weight, warehouse=None):
    best = None
    for t in rec.get("handling", {}).get("outbound", []):
        if t.get("service", "standard") != "standard": continue
        lo, hi = t.get("min_lbs", 0), t.get("max_lbs", 9999)
        wh = t.get("warehouse", "ALL")
        if lo <= weight <= hi:
            if warehouse and wh != "ALL" and wh != warehouse: continue
            if best is None or wh == "ALL" or (warehouse and wh == warehouse):
                best = t.get("price", 0)
                if warehouse and wh == warehouse: break
    return best or 0


def _find_shipping_detail(rec, weight, zone, global_fuel_pct=None):
    """Returns (base_shipping, base_shipping, surcharges_total, fuel_surcharge_total).
    Picks the carrier with the LOWEST total cost (shipping + surcharges + fuel)."""
    # Standard surcharge categories — only those with clear weight/zone conditions
    # AHS_Dimension, AHS_Packaging, Oversize are conditional on package dimensions (unknown)
    STANDARD_CATS = {"AHS_Weight", "AHS", "Residential", "DAS"}

    candidates = []

    for st in rec.get("shipping", []):
        zn = st.get("zones", {}).get(zone, {})
        if not zn: continue
        bp = None; bw = None
        for ws_str, price in zn.items():
            w = _num(ws_str)
            if w is not None and w <= weight:
                if bw is None or w > bw: bw = w; bp = price
        if bp is None: continue

        # Calculate surcharges for this carrier
        surch_total = 0
        seen_categories = set()
        for sc in st.get("surcharges", []):
            cat = sc.get("category", "")
            sc_zone = sc.get("zone")
            min_w = sc.get("min_weight")
            if cat not in STANDARD_CATS: continue
            if min_w is not None and weight <= min_w: continue
            if sc_zone is not None:
                if sc_zone == zone:
                    surch_total += sc.get("price", 0)
                    seen_categories.add(cat)
            else:
                if cat not in seen_categories:
                    surch_total += sc.get("price", 0)
                    seen_categories.add(cat)

        # Fuel surcharge
        fp = global_fuel_pct if (global_fuel_pct is not None and global_fuel_pct > 0) else st.get("fuel_surcharge_pct", 0.0)
        fuel_total = round((bp + surch_total) * fp, 4) if (bp + surch_total) > 0 and fp > 0 else 0
        total = bp + surch_total + fuel_total
        candidates.append((total, bp, surch_total, fuel_total, fp, st.get("carrier", ""), st.get("surcharges", [])))

    if not candidates:
        return 0, 0, 0, 0

    # Pick lowest total cost
    candidates.sort(key=lambda x: x[0])
    best = candidates[0]
    return best[1], best[1], best[2], best[3]


def _find_shipping(rec, weight, zone):
    for st in rec.get("shipping", []):
        zn = st.get("zones", {}).get(zone, {})
        if not zn: continue
        bp, bw = None, None
        for ws_str, price in zn.items():
            w = _num(ws_str)
            if w is not None and w <= weight:
                if bw is None or w > bw: bw = w; bp = price
        if bp is not None: return bp
    return 0


def _find_surcharges(rec, weight, zone):
    """Sum surcharges applicable to this specific zone."""
    total = 0
    for sg in rec.get("surcharges", []):
        for item in sg.get("items", []):
            iz = item.get("zone")
            p = item.get("price", 0)
            if p <= 0: continue
            if iz == zone:
                total += p
    return total

def get_all_zones(records):
    zones = set()
    for rec in records.values():
        for st in rec.get("shipping", []):
            zones.update(st.get("zones", {}).keys())
    return sorted(zones)

def get_weight_range(records):
    lo, hi = 1, 150
    for rec in records.values():
        for st in rec.get("shipping", []):
            lo = min(lo, st.get("min_weight", 1))
            hi = max(hi, st.get("max_weight", 150))
    return (lo, hi)


# ── Batch Calculate ─────────────────────────────────────────────────

def _custom_condition_ok(cond, weight):
    """Evaluate a simple condition string like 'W>50', 'W<=10', empty='always'.
    Variable W = weight in lbs."""
    if not cond or not str(cond).strip():
        return True
    s = str(cond).strip()
    m = re.match(r"^\s*W\s*(>|>=|<|<=|==)\s*(\d+\.?\d*)\s*$", s)
    if not m:
        return True  # unrecognized → apply (fail-open)
    op, val = m.group(1), float(m.group(2))
    if op == ">": return weight > val
    if op == ">=": return weight >= val
    if op == "<": return weight < val
    if op == "<=": return weight <= val
    if op == "==": return abs(weight - val) < 1e-6
    return True


def _calc_custom_fees(rec, weight, qty=1):
    """Compute a supplier's per-unit custom fees for a shipment of given weight & qty.
    custom fee item: {name, type: fixed|per_weight|per_shipment, value, condition}
    Returns {per_unit_total, line_total, items:[{name, amount, per_unit}]}."""
    per_unit = 0.0
    items = []
    fees = rec.get("custom_fees", []) or []
    for fee in fees:
        if not _custom_condition_ok(fee.get("condition"), weight):
            continue
        ftype = fee.get("type", "fixed")
        val = fee.get("value", 0) or 0
        if ftype == "per_weight":
            pu = round(val * weight, 2)
            per_unit += pu
            items.append({"name": fee.get("name", "自定义费"), "per_unit": pu, "type": ftype})
        elif ftype == "per_shipment":
            # charged once per shipment line regardless of qty
            per_unit += round(val / qty, 4) if qty else 0
            items.append({"name": fee.get("name", "自定义费"), "per_unit": round(val / qty, 4) if qty else 0, "type": ftype})
        else:  # fixed per unit
            per_unit += val
            items.append({"name": fee.get("name", "自定义费"), "per_unit": val, "type": ftype})
    per_unit = round(per_unit, 2)
    line_total = round(per_unit * qty, 2)
    return {"per_unit_total": per_unit, "line_total": line_total, "items": items}


def _get_fees_for_weight(rec, weight, zone, global_fuel_pct=None):
    """Return complete fee breakdown for one supplier at one weight/zone."""
    outbound = _find_outbound(rec, weight)
    options = []
    for st in rec.get("shipping", []):
        zn = st.get("zones", {}).get(zone, {})
        if not zn:
            continue
        bp = None
        bw = None
        for ws_str, price in zn.items():
            w = _num(ws_str)
            if w is not None and w <= weight:
                if bw is None or w > bw:
                    bw = w
                    bp = price
        if bp is None:
            continue
        residential = 0.0
        ahs_weight = 0.0
        ahs_other = 0.0
        das = 0.0
        for sc in st.get("surcharges", []):
            cat = sc.get("category", "")
            sc_zone = sc.get("zone")
            min_w = sc.get("min_weight")
            price_val = sc.get("price", 0)
            if min_w is not None and weight <= min_w:
                continue
            if cat == "Residential":
                if sc_zone is None or sc_zone == zone:
                    residential += price_val
            elif cat in ("AHS_Weight", "AHS"):
                if sc_zone is None or sc_zone == zone:
                    ahs_weight += price_val
            elif cat in ("AHS_Dimension", "AHS_Packaging", "Oversize"):
                if sc_zone is None or sc_zone == zone:
                    ahs_other += price_val
            elif cat in ("DAS", "DAS_Remote"):
                if sc_zone is None or sc_zone == zone:
                    das += price_val
        # Only unconditional surcharges count toward total
        surch_total = residential + ahs_weight + das
        fp = global_fuel_pct if (global_fuel_pct is not None and global_fuel_pct > 0) else st.get("fuel_surcharge_pct", 0.0)
        fuel_amount = round((bp + surch_total) * fp, 4) if (bp + surch_total) > 0 and fp > 0 else 0
        custom = _calc_custom_fees(rec, weight).get("per_unit_total", 0)
        total = outbound + bp + surch_total + fuel_amount + custom
        options.append({
            "carrier": st.get("carrier", ""),
            "base": round(bp, 2),
            "residential": round(residential, 2),
            "ahs_weight": round(ahs_weight, 2),
            "ahs_other": round(ahs_other, 2),
            "das": round(das, 2),
            "fuel_pct": round(fp * 100, 1),
            "fuel_amount": round(fuel_amount, 2),
            "custom_total": round(custom, 2),
            "total": round(total, 2),
        })
    options.sort(key=lambda x: x["total"])
    best = options[0] if options else {
        "carrier": "", "base": 0, "residential": 0, "ahs_weight": 0,
        "ahs_other": 0, "das": 0, "fuel_pct": 0, "fuel_amount": 0,
        "custom_total": round(_calc_custom_fees(rec, weight).get("per_unit_total", 0), 2),
        "total": round(outbound + _calc_custom_fees(rec, weight).get("per_unit_total", 0), 2),
    }
    return {"outbound": round(outbound, 2), "options": options, "best": best}


def calculate_batch(records, shipments, zone="Zone5", global_fuel_pct=None):
    """Compute batch comparison: overview (all zones) + details (selected zone)."""
    all_zones_set = set()
    for rec in records.values():
        for st in rec.get("shipping", []):
            all_zones_set.update(st.get("zones", {}).keys())
    all_zones = sorted(all_zones_set) or ["Zone2","Zone3","Zone4","Zone5","Zone6","Zone7","Zone8"]

    supplier_ids = list(records.keys())
    overview = []
    for z in all_zones:
        suppliers = []
        for rid in supplier_ids:
            rec = records[rid]
            grand = 0.0
            for sh in shipments:
                w = sh.get("weight", 1)
                qty = sh.get("qty", 1)
                fees = _get_fees_for_weight(rec, w, z, global_fuel_pct)
                grand += fees["best"]["total"] * qty
            suppliers.append({"rid": rid, "name": rec.get("name", ""), "total": round(grand, 2)})
        overview.append({"zone": z, "suppliers": suppliers})

    details = []
    for sh in shipments:
        w = sh.get("weight", 1)
        qty = sh.get("qty", 1)
        row_suppliers = []
        for rid in supplier_ids:
            rec = records[rid]
            fees = _get_fees_for_weight(rec, w, zone, global_fuel_pct)
            b = fees["best"]
            cf = _calc_custom_fees(rec, w, qty)
            row_suppliers.append({
                "rid": rid,
                "name": rec.get("name", ""),
                "outbound": fees["outbound"],
                "carrier": b["carrier"],
                "shipping": b["base"],
                "residential": b["residential"],
                "ahs_weight": b["ahs_weight"],
                "ahs_other": b["ahs_other"],
                "das": b["das"],
                "fuel_pct": b["fuel_pct"],
                "fuel_amount": b["fuel_amount"],
                "custom_total": b.get("custom_total", 0),
                "custom_fees": cf.get("items", []),
                "unit_total": b["total"],
                "line_total": round(b["total"] * qty, 2),
            })
        details.append({"weight": w, "qty": qty, "suppliers": row_suppliers})

    grand_totals = []
    for rid in supplier_ids:
        rec = records[rid]
        gt = 0.0
        for sh in shipments:
            w = sh.get("weight", 1)
            qty = sh.get("qty", 1)
            fees = _get_fees_for_weight(rec, w, zone, global_fuel_pct)
            gt += fees["best"]["total"] * qty
        grand_totals.append({"rid": rid, "name": rec.get("name", ""), "total": round(gt, 2)})

    return {"overview": overview, "details": details, "grand_totals": grand_totals}


# ── SupplierStore (v4 — manual entry per supplier) ──────────────
SUPPLIER_FILE = DATA_DIR / "suppliers.json"
_supplier_lock = threading.Lock()

class SupplierStore:
    def __init__(self):
        self._data = {}
        if SUPPLIER_FILE.exists():
            try:
                loaded = json.loads(SUPPLIER_FILE.read_text("utf-8"))
                if isinstance(loaded, list):
                    self._data = {r["id"]: r for r in loaded if "id" in r}
                else:
                    self._data = loaded
            except:
                self._data = {}
    def _save(self):
        SUPPLIER_FILE.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), "utf-8")
    def list_all(self):
        return dict(self._data)
    def get(self, sid):
        return self._data.get(sid)
    def add(self, supplier):
        with _supplier_lock:
            self._data[supplier["id"]] = supplier
            self._save()
            return supplier
    def update(self, sid, data):
        with _supplier_lock:
            if sid not in self._data:
                return None
            self._data[sid].update(data)
            self._save()
            return self._data[sid]
    def delete(self, sid):
        with _supplier_lock:
            if sid in self._data:
                del self._data[sid]
                self._save()
                return True
            return False
    def clear(self):
        with _supplier_lock:
            self._data = {}
            self._save()

    def to_pricing_records(self):
        """Convert suppliers to pricing record format for calculate_batch compatibility."""
        records = {}
        for sid, sp in self._data.items():
            rec = {
                "name": sp.get("name", ""),
                "custom_fees": sp.get("custom_fees", []),
                "handling": {
                    "outbound": [
                        {"min_lbs": t["min_lbs"], "max_lbs": t["max_lbs"], "price": t["price"],
                         "warehouse": "ALL", "service": "standard"}
                        for t in sp.get("outbound", [])
                    ],
                },
                "shipping": [],
            }
            if sp.get("shipping_zones"):
                carrier = sp.get("carrier", "")
                fuel_pct = sp.get("fuel_pct", 0) / 100.0
                zones_data = {}
                for zn, weights in sp.get("shipping_zones", {}).items():
                    zones_data[zn] = {str(k): v for k, v in weights.items()}
                surcharges = []
                for zn, price in sp.get("residential", {}).items():
                    surcharges.append({"category": "Residential", "zone": zn, "price": price, "min_weight": None})
                for zn, price in sp.get("ahs_weight", {}).items():
                    surcharges.append({"category": "AHS_Weight", "zone": zn, "price": price, "min_weight": 50})
                rec["shipping"].append({
                    "carrier": carrier,
                    "zones": zones_data,
                    "fuel_surcharge_pct": fuel_pct,
                    "surcharges": surcharges,
                })
            records[sid] = rec
        return records


# ── Paste Import Parsers ──────────────────────────────────────────
def parse_fuel_paste(text):
    """Parse fuel surcharge from paste text.
    Accepts formats like: '16', '16%', '0.16', '燃油 16%'."""
    for line in text.strip().splitlines():
        line_s = line.strip()
        if not line_s:
            continue
        m = re.search(r"(\d+\.?\d*)\s*%", line_s)
        if m:
            return float(m.group(1))
        m = re.search(r"0\.(\d+)", line_s)
        if m:
            val = float("0." + m.group(1))
            if val <= 1:
                return val * 100
        m = re.search(r"(\d+\.?\d*)", line_s)
        if m:
            return float(m.group(1))
    return 0


def parse_outbound_paste(text):
    """Parse outbound tiers from various formats:
    - '0-4.4\t0.80'          (dash range)
    - '0 lbs<W≤1 lbs\t0.4'  (inequality range)
    - 'W>50 lbs\t3.00'      (open-end)
    - '≤50lbs\t1.50'         (up to)
    - '150.01+\t3.00'        (plus range)
    Returns [{min_lbs, max_lbs, price}]."""
    tiers = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"[\t,]+", line)
        if len(parts) < 2:
            continue
        rng = parts[0].strip()
        price_s = parts[-1].strip().replace("$", "")
        price = _num(price_s)
        if price is None or price <= 0:
            continue
        # Try _parse_tier first (handles lbs<W≤lbs, W>lbs, ≤lbs, etc.)
        tier = _parse_tier(rng)
        if tier:
            lo, hi = tier
            tiers.append({"min_lbs": lo, "max_lbs": hi, "price": price})
            continue
        # "0-4.4" or "0 ~ 4.4"
        m = re.match(r"(\d+\.?\d*)\s*[\-~]\s*(\d+\.?\d*)", rng)
        if m:
            lo = float(m.group(1))
            hi = float(m.group(2))
            tiers.append({"min_lbs": lo, "max_lbs": hi, "price": price})
            continue
        # "150.01+" format
        m = re.match(r"(\d+\.?\d*)\s*\+", rng)
        if m:
            tiers.append({"min_lbs": float(m.group(1)), "max_lbs": 9999, "price": price})
            continue
    return tiers


def parse_shipping_paste(text):
    """Parse zone×weight matrix. Returns {carrier, fuel_pct, zones: {Zone2: {1: 34.0, ...}}}.
    Lines: header 'Weight\tZone2\tZone3...' then data rows '1\t34.00\t22.00...'.
    Supports extra prefix columns (e.g. 计费重量(lbs)\t公制重量(kg)\tZone2...):
      the weight column is auto-detected as the first numeric column closest to the Zone columns.
    Optional: carrier name on first line if preceded by '#'.
    """
    lines = text.strip().splitlines()
    carrier = ""
    fuel_pct = 0.0
    data_lines = []
    for line in lines:
        line_s = line.strip()
        if not line_s:
            continue
        if line_s.startswith("#"):
            meta = line_s[1:].strip()
            cm = re.search(r"carrier\s+(.+)", meta, re.I)
            if cm:
                carrier = cm.group(1).strip()
            fm = re.search(r"fuel\s+(\d+\.?\d*)%?", meta, re.I)
            if fm:
                fuel_pct = float(fm.group(1))
            continue
        data_lines.append(line_s)

    if not data_lines:
        return {"carrier": carrier, "fuel_pct": fuel_pct, "zones": {}}

    zones = {}
    header_parts = re.split(r"[\t,]+", data_lines[0])
    zone_cols = {}
    for ci, h in enumerate(header_parts):
        h = h.strip()
        m = re.match(r"^zone\s*(\d+)$", h, re.I)
        if m:
            zone_cols[ci] = "Zone" + m.group(1)
        else:
            hm = re.match(r"^z\s*(\d+)$", h, re.I)
            if hm:
                zone_cols[ci] = "Zone" + hm.group(1)

    if not zone_cols:
        return {"carrier": carrier, "fuel_pct": fuel_pct, "zones": {}}

    for ci in zone_cols:
        zones[zone_cols[ci]] = {}

    # Auto-detect the weight column: the LAST non-zone column before the first zone column
    # that holds numeric data in the data rows. This supports prefix cols (计费重量/公制重量).
    first_zone_col = min(zone_cols.keys())
    candidates = list(range(first_zone_col))
    weight_col = None
    for line_s in data_lines[1:]:
        parts = re.split(r"[\t,]+", line_s)
        if len(parts) < 2:
            continue
        for ci in candidates:
            if ci < len(parts):
                v = _num(parts[ci])
                if v is not None and v > 0:
                    weight_col = ci
                    break
        if weight_col is not None:
            break

    if weight_col is None:
        weight_col = 0

    for line_s in data_lines[1:]:
        parts = re.split(r"[\t,]+", line_s)
        if len(parts) < 2:
            continue
        w = _num(parts[weight_col])
        if w is None or w <= 0:
            continue
        w_key = str(int(w)) if w == int(w) else str(round(w, 2))
        for ci, zn in zone_cols.items():
            if ci < len(parts):
                v = _num(parts[ci])
                if v is not None and v > 0:
                    zones[zn][w_key] = v

    return {"carrier": carrier, "fuel_pct": fuel_pct, "zones": zones}


def parse_surcharges_paste(text):
    """Parse surcharges: 'Zone2\t2.70' format → {Zone2: 2.70, ...}."""
    result = {}
    for line in text.strip().splitlines():
        line_s = line.strip()
        if not line_s:
            continue
        parts = re.split(r"[\t,]+", line_s)
        if len(parts) < 2:
            continue
        zn = parts[0].strip()
        m = re.match(r"^zone\s*(\d+)$", zn, re.I)
        if m:
            zn = "Zone" + m.group(1)
        else:
            hm = re.match(r"^z\s*(\d+)$", zn, re.I)
            if hm:
                zn = "Zone" + hm.group(1)
        price = _num(parts[1].strip().replace("$", ""))
        if price is not None and price >= 0:
            result[zn] = price
    return result
