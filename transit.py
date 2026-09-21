import csv
import hashlib
import json
import os
import re
import threading
from datetime import date, datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "transit_data.json")
UPLOAD_DIR = os.path.join(BASE_DIR, "_transit_uploads")

CONTAINER_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{4}\d{7}(?![0-9])")

HEADER_WORDS = {
    "sku": ["sku", "货号", "产品编码", "产品编号", "产品型号", "产品代码", "型号", "编码", "物料号", "item no", "item no.", "item", "part no", "part no.", "catalog no"],
    "name": ["品名", "产品名称", "名称", "品名规格", "商品名称", "货物名称", "description", "product name", "规格"],
    "qty": ["数量", "件数", "箱数", "装柜数量", "数量(pcs)", "qty", "quantity", "qty/pcs", "pcs", "carton", "ctns", "箱"],
    "container": ["柜号", "箱号", "货柜号", "container", "cntr", "cnee", "柜", "container no", "备注"],
    "so": ["so", "so号", "so no", "so no.", "订舱号", "订舱单号", "booking no", "booking", "bkg", "订舱"],
    "factory": ["工厂", "厂家", "供应商", "制造商", "生产厂家", "factory", "生产工厂"],
    "loading": ["装柜时间", "装柜日期", "装柜", "打柜日期", "打板日期", "loading date", "装货日期", "柜期"],
    "vessel": ["船名", "vessel", "船名航次"],
    "voyage": ["航次", "voyage", "voy"],
    "pol": ["起运港", "装货港", "出发港", "发货港", "pol", "port of loading"],
    "pod": ["目的港", "卸货港", "到港", "pod", "port of discharge", "port of destination"],
}

FACTORY_ALIASES = [
    ("冠域", "冠域世家"),
    ("正达", "正达"),
    ("金泽", "金泽"),
    ("麦泽", "麦泽"),
    ("城市之窗", "城市之窗"),
    ("怡嘉豪", "怡嘉豪"),
    ("家和", "家和"),
    ("海外", "海外"),
    ("惠海嘉", "惠海嘉"),
    ("惠海家", "惠海嘉"),
]

SHIP_LINES = [
    (["maersk", "马士基", "msk"], "马士基 Maersk"),
    (["msc", "地中海"], "地中海 MSC"),
    (["oocl", "东方海外"], "东方海外 OOCL"),
    (["hapag", "赫伯罗特", "hpl", "hmm"], "赫伯罗特 Hapag-Lloyd"),
    (["yang ming", "yangming", "yml", "阳明"], "阳明 Yang Ming"),
    (["evergreen", "长荣", "emc"], "长荣 Evergreen"),
    (["cma", "cma-cgm", "达飞"], "达飞 CMA CGM"),
    (["cosco", "中远", "中远海运"], "中远海运 COSCO"),
    (["one ", "one alliance", "one-line", "ocean network express", "海洋网联", "oney"], "ONE"),
    (["ocean alliance", "海洋联盟", "oa联盟"], "海洋联盟 OA"),
    (["wan hai", "万海"], "万海 Wan Hai"),
    (["pil", "太平船务"], "太平船务 PIL"),
    (["zim", "以星"], "以星 ZIM"),
    (["eastern", "美森"], "美森 Matson"),
    (["hyundai", "现代", "hmm"], "现代 HMM"),
]

ALLIANCE_SIMPLE = [("ocean alliance", "海洋联盟 OA"), ("the alliance", "THE联盟")]


def _now():
    return datetime.now()


def _today():
    return date.today()


def _fmt(d):
    if d is None:
        return None
    return d.strftime("%Y-%m-%d")


def parse_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return _fmt(value)
    if isinstance(value, date):
        return _fmt(value)
    s = str(value).strip()
    if not s:
        return None
    if re.fullmatch(r"\d{5}", s):
        try:
            base = datetime(1899, 12, 30)
            return _fmt(base + timedelta(days=int(s)))
        except Exception:
            return None
    s = re.sub(r"[./]", "-", s)
    s = re.sub(r"年|月", "-", s)
    s = s.replace("日", "")
    s = re.sub(r"(\d{1,2})([A-Za-z]{3,9})(\d{2,4})", r"\1-\2-\3", s)
    s = re.sub(r"(\d{1,2})-([A-Za-z]{3,9})-(\d{2})\b", r"\1-\2-20\3", s)
    fmts = ["%Y-%m-%d", "%Y-%m", "%d-%m-%Y", "%m-%d-%Y", "%Y-%m-%dT%H:%M:%S", "%d-%b-%Y", "%d-%B-%Y", "%d-%b-%y", "%d-%B-%y", "%d %b %Y", "%d %B %Y"]
    for f in fmts:
        try:
            return datetime.strptime(s, f).strftime("%Y-%m-%d")
        except ValueError:
            continue
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return _fmt(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            return None
    return None


def _norm(v):
    if v is None:
        return ""
    return str(v).strip()


def detect_line(text):
    t = (text or "").lower()
    for words, name in SHIP_LINES:
        for w in words:
            if w.isascii() and w.isalpha() and len(w) <= 4:
                if re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", t):
                    return name
            elif w in t:
                return name
    for words, name in ALLIANCE_SIMPLE:
        for w in words:
            if w in t:
                return name
    return ""


def transit_days(pod):
    if not pod:
        return 15
    p = pod.lower()
    west = ["los angeles", "long beach", "oakland", "seattle", "tacoma", "vancouver", "san francisco", "portland"]
    east = ["new york", "newark", "savannah", "norfolk", "charleston", "baltimore", "boston", "miami", "jacksonville", "philadelphia"]
    gulf = ["houston", "mobile", "new orleans"]
    euro = ["rotterdam", "hamburg", "antwerp", "felixstowe", "southampton", "le havre", "bremen"]
    if any(k in p for k in west):
        return 14
    if any(k in p for k in east):
        return 28
    if any(k in p for k in gulf):
        return 30
    if any(k in p for k in euro):
        return 30
    if "us" in p or "america" in p or "usa" in p:
        return 18
    if "ca" in p or "canada" in p:
        return 15
    return 20


def _match_label(text):
    t = str(text or "").strip().lower()
    if not t:
        return None, 0
    best = None
    best_score = 0
    for field, words in HEADER_WORDS.items():
        for w in words:
            if w in t:
                score = len(w)
                if score > best_score:
                    best_score = score
                    best = field
    return best, best_score


_SO_PREFIX_RX = re.compile(r"^(?:COSU|ONEY|MSCU|CMDU|EMCU|EVGL|OOLU|MAEU|TRLU|APLU|CSLU|TEMU|ZIMU|HLXU|CMAU|SNBU|ESLU|PONL|YMLU|WANL|HMMU|SITC|GOSU|SZXU|CULU)")


def _so_key(s):
    """SO 规范化匹配键：剥离开头承运人前缀与柜号序号后缀，使订舱号/提单号可互相匹配。
    例：SZPGB3741600 == ONEYSZPGB3741600；6505281630 == COSU6505281630；29664191/1 == 29664191"""
    s = (s or "").strip()
    if not s:
        return ""
    key = _SO_PREFIX_RX.sub("", s).upper()
    # 柜号序号后缀（订舱号本身为纯数字）：29664191/1 → 29664191、29664191(1) → 29664191
    key = re.sub(r"(?:[/／]\s*\d{1,4}|\s*[（(]\d{1,4}[)）]|\s*[-_]\s*\d{1,4})$", "", key)
    return key


class TransitStore:
    def __init__(self, path=DATA_FILE):
        self.path = path
        self._lock = threading.Lock()
        self._data = []
        self.load()

    def load(self):
        with self._lock:
            if os.path.exists(self.path):
                try:
                    with open(self.path, "r", encoding="utf-8") as f:
                        self._data = json.load(f)
                except Exception:
                    self._data = []
            else:
                self._data = []

    def save(self):
        with self._lock:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)

    def list(self):
        with self._lock:
            return list(self._data)

    def find(self, rid):
        with self._lock:
            for r in self._data:
                if r.get("id") == rid:
                    return r
        return None

    def _make_id(self, rec):
        key = "|".join([str(rec.get("container_no", "")), str(rec.get("so", "")), str(rec.get("vessel", ""))])
        return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]

    def upsert(self, rec):
        with self._lock:
            rec["id"] = rec.get("id") or self._make_id(rec)
            key_so = _so_key(rec.get("so"))
            idx = None
            for i, old in enumerate(self._data):
                if old.get("container_no") and rec.get("container_no") and old.get("container_no") == rec.get("container_no"):
                    idx = i
                    break
            if idx is None and key_so:
                if rec.get("container_no"):
                    for i, old in enumerate(self._data):
                        if not old.get("container_no") and _so_key(old.get("so")) == key_so:
                            idx = i
                            break
                else:
                    for i, old in enumerate(self._data):
                        if old.get("container_no") and _so_key(old.get("so")) == key_so:
                            idx = i
                            break
                    if idx is None:
                        for i, old in enumerate(self._data):
                            if not old.get("container_no") and _so_key(old.get("so")) == key_so:
                                idx = i
                                break
            if idx is None:
                for i, old in enumerate(self._data):
                    if old.get("id") == rec["id"]:
                        idx = i
                        break
            if idx is not None:
                old = self._data[idx]
                merged = dict(old)
                for k, v in rec.items():
                    if v is None:
                        continue
                    if k == "lines":
                        by = {}
                        for ln in list(merged.get("lines") or []) + list(v or []):
                            key = (ln.get("sku") or "", ln.get("name") or "", ln.get("qty") or 0)
                            by[key] = ln
                        merged["lines"] = list(by.values())
                    elif k == "id":
                        continue
                    elif k == "eta_basis" and merged.get(k) and v in ("", "none", "est"):
                        continue
                    elif k == "so" and merged.get(k) and v and _so_key(merged.get(k)) == _so_key(v):
                        if len(v) > len(merged.get(k)):
                            merged[k] = v
                    elif k == "factory" and merged.get(k) and v:
                        merged[k] = _merge_factories(merged.get(k), v)
                    else:
                        if not v and merged.get(k):
                            continue
                        merged[k] = v
                self._data[idx] = merged
                if merged.get("container_no"):
                    self._data = [r for r in self._data if not (r.get("id") != merged.get("id") and not r.get("container_no") and key_so and _so_key(r.get("so")) == key_so)]
                return merged, "updated"
            self._data.append(rec)
            return rec, "added"

    def normalize(self, rec):
        for k in ("container_no", "so", "factory", "vessel", "voyage", "pol", "pod", "etd", "eta_so", "eta_est", "eta_basis", "loading_date", "shipping_line", "created_at", "manual_status", "actual_sail_date", "actual_arrival_date"):
            rec.setdefault(k, "")
            v = rec.get(k, "")
            if isinstance(v, str) and ("\n" in v or "\r" in v):
                rec[k] = v.strip()
        rec.setdefault("lines", [])
        return rec

    def remove(self, rid):
        with self._lock:
            for i, r in enumerate(self._data):
                if r.get("id") == rid:
                    self._data.pop(i)
                    return True
            return False

    def apply_eta(self, rec):
        return compute_eta(rec)


def _find_header_row(rows):
    best = -1
    best_score = 0
    for i, row in enumerate(rows[:30]):
        score = 0
        for cell in row:
            f, _ = _match_label(cell)
            if f:
                score += 1
        if score > best_score:
            best_score = score
            best = i
    if best_score < 2:
        return -1
    return best


def _find_cols(header_row):
    cols = {}
    col_scores = {}
    for i, cell in enumerate(header_row):
        f, score = _match_label(cell)
        if f:
            if f not in cols or score > col_scores.get(f, 0):
                cols[f] = i
                col_scores[f] = score
    return cols


def _short_factory(cand):
    if not cand:
        return ""
    for kw, short in FACTORY_ALIASES:
        if kw in cand:
            return short
    return ""


def _add_factory(names, raw):
    short = _short_factory(raw)
    if short and short not in names:
        names.append(short)


def _merge_factories(a, b):
    """拼柜：合并两个工厂抬头，如 正达 + 冠域世家（去重，幂等）"""
    parts = []
    for x in (a or "", b or ""):
        for p in re.split(r"\s*[+＋/、,&，]\s*", x):
            p = _short_factory(p) or p.strip()
            if p and p not in parts:
                parts.append(p)
    return " + ".join(parts)


def _scan_context(cells):
    ctx = {"containers": [], "so": "", "factory": "", "loading": ""}
    factory_names = []
    for c in cells:
        s = _norm(c)
        if not s:
            continue
        for m in CONTAINER_RE.finditer(s):
            if m.group(0).upper() not in ctx["containers"]:
                ctx["containers"].append(m.group(0).upper())
        m = re.search(r"(?i)(?:so|booking|bkg|订舱|提单)\s*(?:no|号)?\s*[:：]?\s*([A-Za-z0-9][A-Za-z0-9\-/]{4,30})", s)
        if m:
            cand = m.group(1)
            if not re.fullmatch(r"[A-Za-z]{4}\d{7}", cand) and len(re.sub(r"[^0-9A-Za-z]", "", cand)) >= 4:
                ctx["so"] = cand
        fm = re.search(r"(?i)(?:装柜时间|装柜日期|做柜时间|装柜|打柜|发货日期|装箱日期|loading\s*date|loading)\s*[:：]?\s*(\d{4}[-./年]\d{1,2}[-./月]\d{1,2}\s*日?|\d{1,2}[-./月]\d{1,2}[-./]\d{2,4})", s)
        if fm:
            ctx["loading"] = fm.group(1).strip()
        fac = re.search(r"(?i)(?:工厂名称|工厂|厂家|供应商|生产厂家|factory)\s*[:：]\s*([\u4e00-\u9fa5A-Za-z0-9（）() ]+)", s)
        if fac:
            _add_factory(factory_names, fac.group(1).strip())
        tm = re.search(r"[\u4e00-\u9fa5A-Za-z0-9（）() ]{2,40}?(?:(?:装柜|装箱)?发货明细|销售出货单)", s)
        if tm:
            name = tm.group(0)
            name = re.sub(r"^[\d.\-年月日\s]+", "", name)
            name = re.sub(r"(?:(?:装柜|装箱)?发货明细|销售出货单).*$", "", name).strip()
            if name:
                _add_factory(factory_names, name)
    ctx["factory"] = " + ".join(factory_names)
    return ctx


def parse_packing_excel(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return _parse_packing_csv(path)
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    records = []
    warnings = []
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            row = [_norm(v) for v in row]
            if any(row):
                rows.append(row)
        if not rows:
            continue
        recs, warns = _parse_packing_sheet(rows)
        records.extend(recs)
        if recs:
            warnings.extend(warns)
    wb.close()
    if not records:
        wb2 = load_workbook(path, read_only=True, data_only=False)
        for ws in wb2.worksheets:
            rows = []
            for row in ws.iter_rows(values_only=True):
                row = [_norm(v) for v in row]
                if any(row):
                    rows.append(row)
            if not rows:
                continue
            recs, warns = _parse_packing_sheet(rows)
            records.extend(recs)
            if recs:
                warnings.extend(warns)
        wb2.close()
    # 拼柜等文件可能在表头省略柜号，用文件名中的柜号兜底
    fname_m = CONTAINER_RE.search(os.path.basename(path).upper())
    if fname_m:
        fname_cno = fname_m.group(0)
        for rec in records:
            if rec.get("container_no") in ("", "无柜号"):
                rec["container_no"] = fname_cno
    return records, warnings


def _normalize_so(so):
    """Normalize SO number for fuzzy matching: strip carrier prefixes, suffixes."""
    if not so:
        return ""
    s = so.strip().upper()
    s = re.sub(r"^(COSU|OOLU|EGLV|CCLU|CSNU|ONEY|WHLC|SHZ|COSCO)", "", s)
    s = re.sub(r"^(ZIMUSHH|ZIMU)", "", s)
    s = re.sub(r"[-–]\d+[A-Z0-9]*$", "", s)
    s = re.sub(r"[-–][A-Z0-9]+$", "", s)
    return s.strip()


def _parse_packing_csv(path):
    text = None
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                text = f.read()
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return [], ["无法解码 CSV 文件"]
    rows = [r for r in csv.reader(text.splitlines())]
    rows = [[_norm(v) for v in r] for r in rows if any(_norm(v) for v in r)]
    return _parse_packing_sheet(rows)


def _parse_packing_sheet(rows):
    if not rows:
        return [], []
    hrow = _find_header_row(rows)
    warnings = []
    if hrow < 0:
        return [], ["未找到表头（SKU/品名/数量等）"]
    cols = _find_cols(rows[hrow])
    ctx_cells = [c for r in rows[:hrow + 2] for c in r]
    ctx = _scan_context(ctx_cells)
    sku_i = cols.get("sku")
    name_i = cols.get("name")
    qty_i = cols.get("qty")
    cntr_i = cols.get("container")
    so_i = cols.get("so")
    if sku_i is None and qty_i is None:
        return [], ["表头列不完整（需要 SKU 与 数量 列）"]
    if qty_i is None:
        warnings.append("未识别到“数量”列，数量按 1 计")
    fac_i = cols.get("factory")
    load_i = cols.get("loading")
    vessel_i = cols.get("vessel")
    so_i = cols.get("so")
    groups = {}
    cur_cno = ""
    cur_so = ""
    cur_fac = ""
    for row in rows[hrow + 1:]:
        if not any(row):
            continue
        cno = ""
        if cntr_i is not None and cntr_i < len(row):
            m = CONTAINER_RE.search(row[cntr_i].upper())
            cno = m.group(0) if m else ""
        if cno:
            cur_cno = cno
        elif cur_cno:
            cno = cur_cno
        else:
            cno = ctx["containers"][0] if ctx["containers"] else ""
        if not cno:
            cno = "无柜号"
        sku = row[sku_i] if sku_i is not None and sku_i < len(row) else ""
        name = row[name_i] if name_i is not None and name_i < len(row) else ""
        qty_s = row[qty_i] if qty_i is not None and qty_i < len(row) else "1"
        if not sku and not name:
            continue
        qty_text = re.sub(r"(?i)\b(pcs|件|箱|set|套|cases?|units?|cartons?|ctns?)\b.*$", "", str(qty_s))
        qty_text = qty_text.replace(",", "").replace("，", "").strip()
        try:
            q = float(qty_text) if qty_text else 0
        except ValueError:
            q = 0
        if fac_i is not None and fac_i < len(row):
            fraw = row[fac_i]
            if fraw:
                cur_fac = _short_factory(fraw) or fraw.strip()
        g = groups.setdefault(cno, {"container_no": cno, "so": "", "factory": "", "loading_date": "", "lines": []})
        if so_i is not None and so_i < len(row) and row[so_i]:
            cur_so = row[so_i]
        if not g["so"] and cur_so:
            g["so"] = cur_so
        if not g["factory"] and cur_fac:
            g["factory"] = cur_fac
        if not g["loading_date"] and load_i is not None and load_i < len(row) and row[load_i]:
            g["loading_date"] = row[load_i]
        g["lines"].append({"sku": sku, "name": name, "qty": q})
    for cno, g in groups.items():
        g["so"] = g.get("so") or ctx.get("so", "")
        if not g["factory"]:
            g["factory"] = ctx.get("factory", "")
        if not g["loading_date"]:
            g["loading_date"] = ctx.get("loading", "")
        if not g["so"]:
            warnings.append(f"柜 {cno} 未识别到 SO 号")
        if g["loading_date"]:
            g["loading_date"] = parse_date(g["loading_date"]) or g["loading_date"]
    return list(groups.values()), warnings


def _kv(text, keys):
    labels = "|".join(r"\s*".join(re.escape(part) for part in k.split()) for k in keys)
    pat = r"(?i)(" + labels + r")(\s*no\.?\s*[:：]\s*|\s*[:：]\s*|\s+)([^\n\r]{1,120})"
    m = re.search(pat, text)
    if not m:
        return ""
    val = m.group(3).strip().strip("|").strip()
    val = re.sub(r"^(?:no\.?|num\.?|number)\s*[:：]?\s*", "", val, flags=re.I)
    val = re.sub(r"\s+", " ", val)
    return val


_DATE_RX = r"(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[\s/-][A-Za-z]{3,9}[\s/-]\d{2,4}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{1,2}[A-Za-z]{3,9}\d{2,4})"


def _extract_so(t):
    pats = [
        r"(?i)(ZIM[0-9A-Z]{3}\d{6,8})\b",
        r"\*([0-9]{6,15})\*",
        r"(?i)book(?:ing)?\s*(?:number|no\.?|#)\s*[^0-9A-Za-z]{0,10}([0-9A-Z][0-9A-Za-z\-/]{4,29})",
        r"(?i)\bbkg\s*ref\.?\s*[:：.\s]*([0-9A-Z][0-9A-Za-z\-/]{4,29})",
        r"我司的参考号\s*[:：]?\s*([0-9A-Za-z][0-9A-Za-z\-/]{2,25})",
        r"订舱(?:单)?号\s*[:：]?\s*([0-9A-Za-z][0-9A-Za-z\-/]{2,25})",
        r"提单号\s*[:：]?\s*([0-9A-Za-z][0-9A-Za-z\-/]{4,25})",
        r"(?i)\b(?:so|bkg)\s*(?:no\.?|number|#)\s*[:：.\s]*([0-9A-Z][0-9A-Za-z\-/]{4,29})",
        r"(?i)shipping\s+order\s*(?:no\.?|number|#)?\s*[:：.]?\s*([0-9A-Z][0-9A-Za-z\-/]{4,29})",
        r"(?i)\b(0\d{2}[A-Z]\d{6})",
    ]
    best = None
    for p in pats:
        m = re.search(p, t)
        if not m:
            continue
        cand = m.group(1)
        if not re.search(r"\d", cand):
            for m2 in re.finditer(r"([0-9A-Z][0-9A-Za-z\-/]{4,29})", t[m.end():m.end() + 25]):
                if re.search(r"\d", m2.group(1)):
                    cand = m2.group(1)
                    break
        if re.search(r"\d", cand) and (best is None or m.start() < best[0]):
            best = (m.start(), cand)
    return best[1] if best else ""


def _join_words(tokens):
    out = []
    i = 0
    while i < len(tokens):
        if len(tokens[i]) == 1 and i + 1 < len(tokens):
            out.append(tokens[i] + tokens[i + 1])
            i += 2
        else:
            out.append(tokens[i])
            i += 1
    return " ".join(out)


def _extract_plan(text):
    """运输计划表（马士基 MVS 模式）：MVS 船名 航次 ETD ETA"""
    m = re.search(r"\bMVS\b", text)
    if not m:
        return None
    tokens = re.findall(r"[A-Za-z0-9\-/\.]+", text[m.end():m.end() + 250])
    for i, tk in enumerate(tokens):
        if not re.fullmatch(r"\d{2,5}[A-Z]{0,2}", tk):
            continue
        if i + 2 >= len(tokens):
            continue
        d1, d2 = tokens[i + 1], tokens[i + 2]
        if not re.fullmatch(_DATE_RX, d1) or not re.fullmatch(_DATE_RX, d2):
            continue
        vessel = _join_words(tokens[:i])
        return {"vessel": vessel, "voyage": tk, "etd": d1, "eta": d2}
    return None


def _extract_vessel(text, plan):
    if plan and plan.get("vessel"):
        return plan["vessel"]
    pats = [
        r"(?i)\bvsl\s*/\s*voy\s*[:：]?\s*([A-Za-z0-9][A-Za-z0-9 \-/:]{2,50})",
        r"(?i)vessel\s*voyage\s*(?:dir)?\s*[:：]\s*([A-Za-z0-9][A-Za-z0-9 \-/]{2,50})",
        r"(?:船名|船名航次)\s*[/／]?\s*航次\s*[:：]\s*([A-Za-z0-9][A-Za-z0-9 \-/]{2,50})",
        r"(?i)vessel\s*(?:name|code|/voyage)?\s*[-:]\s*([A-Za-z0-9][A-Za-z0-9 \-/]{2,50})",
        r"((?:APM TERMINALS|MAERSK|COSCO|EVERGREEN|CMA CGM|MSC|HMM|YANG MING|HYUNDAI|ZIM|ONE)\s+[A-Z][A-Z0-9 \-]{2,60}?)\s+\d{2}:\d{2}\s+\d{2}:\d{2}",
        r"(?mi)^[ \t]*b/?l[ \t]*\r?\n[ \t]*([A-Z][A-Z0-9 \-/:.]{1,50}\d[A-Z0-9 \-/:.]{0,50})",
    ]
    best = None
    for p in pats:
        m = re.search(p, text)
        if not m:
            continue
        v = m.group(1).strip().rstrip(" -/")
        if re.match(r"(?i)^(?:etd|eta|atd|cut\s*off|departure|arrival|voyage)", v):
            continue
        if re.match(r"(?i)^b/?l", v) and re.search(r"[0-9]", v):
            continue
        v = re.sub(r"(?i)\s+(?:etd|eta)\s*(?:date)?\s*[:：].*$", "", v).strip()
        v = re.sub(r"(?i)\s*(?:vessel|voyage|vessel/voyage)\s*[:：]?.*$", "", v).strip()
        if v and (best is None or m.start() < best[0]):
            best = (m.start(), v)
    if not best:
        m = re.search(r"(?i)船名\s*[/／]?\s*航次\s*[:：][^\n\r]{0,60}\n(?:[^\n]{0,120}\n){0,6}\s*([A-Z][A-Za-z .'-]{2,30}\s+\d{2,4}[EW])", text)
        if m:
            best = (m.start(), m.group(1))
    return best[1] if best else ""


def _split_vessel_voyage(vessel):
    v = vessel.strip()
    m = re.search(r"\s(\d{1,5}(?:-\d{1,5})?[A-Z]{0,2})$", v, re.I)
    if m:
        return v[:m.start()].strip(), m.group(1)
    m = re.search(r"\s([0-9][A-Za-z0-9]{3,11})$", v)
    if m:
        return v[:m.start()].strip(), m.group(1)
    return v, ""


def _extract_voyage(text, plan):
    if plan and plan.get("voyage"):
        return plan["voyage"]
    m = re.search(r"(?i)voy(?:age)?\s*\.?\s*no\.?\s*[:：.\s]*(\d{2,5}[A-Z]{0,2})", text)
    if m:
        return m.group(1)
    m = re.search(r"(?i)(?:航次|voyage)\s*[:：]?\s*(\d{2,5}[A-Z]{0,2})", text)
    if m and not re.match(r"20\d{3}$", m.group(1)):
        return m.group(1)
    return ""


def _clean_port(v):
    if not v:
        return ""
    v = re.sub(r"(?:^|\s+)(?:ETA|ETD)\s*[:：]?\s*\d.*$", "", v, flags=re.I)
    v = re.sub(r"\s*\(SUBJECT TO CHANGE[^)]*\)", "", v, flags=re.I)
    v = re.sub(r"\s+\d{1,2}[\s/-][A-Za-z]{3,9}[\s/-]\d{2,4}\b.*$", "", v, flags=re.I)
    v = v.strip()
    if re.match(r"(?i)^(?:bill\b|b/?l\b|no\.?\b)", v):
        return ""
    if "/" in v:
        parts = re.split(r"\s*/\s*", v)
        if len(parts) > 1:
            v = parts[0].strip()
    v = re.sub(r"^[^A-Za-z0-9]+(?=[A-Za-z])", "", v)
    v = re.sub(r",\s*[A-Z]{3,}[A-Z ]*$", "", v, flags=re.I)
    m = re.search(r"(.+?)\s*\(([A-Z]{2})\)$", v)
    if m:
        v = m.group(1).strip() + ", " + m.group(2)
    m = re.match(r"^([A-Z]{2,8})\s*\(([^()]{3,40})\)$", v.strip())
    if m and not re.search(r"\d", m.group(2)):
        v = m.group(2).strip()
    v = re.sub(r",?\s*PEOPLE['’]*$", "", v, flags=re.I)
    if re.search(r"[\u4e00-\u9fff]", v):
        m = re.search(r"[A-Z]{3,}(?:[,，][A-Z]{2})?", v)
        if m:
            v = m.group(0)
    return v.strip()


def _extract_pol_pod(text):
    pol = pod = ""
    m = re.search(r"装港\s*[(（]?[^:：]*?[)）]?\s*[:：]\s*([^\n\r]{2,80})", text)
    if m:
        pol = m.group(1).strip()
    m = re.search(r"卸港\s*[:：]\s*([^\n\r]{2,80})", text)
    if m and not re.match(r"(?i)^\s*(?:eta|etd|cut)", m.group(1)):
        pod = m.group(1).strip()
    if not pol:
        m = re.search(r"\bFrom\s*[:：]\s*([A-Za-z0-9,\.\- ]{3,70})", text, re.I)
        if m:
            pol = m.group(1).strip()
    if not pod:
        m = re.search(r"\bTo\s*[:：]\s*([A-Za-z0-9,\.\- ]{3,70})", text, re.I)
        if m and re.search(r"\bFrom\s*[:：][^\n\r]*", text[max(0, m.start() - 200):m.start()], re.I):
            pod = m.group(1).strip()
    if not pol and not pod:
        m = re.search(r"起点\s+终点\s+运输方式\s+预计开船时间\s+预计到达时间[^\n]*\n\s*([A-Za-z0-9 ]+?)\s+(.+?)\s+Vessel\s+" + _DATE_RX + r"\s+" + _DATE_RX, text)
        if m:
            pol = m.group(1).strip()
            pod = m.group(2).strip()
    if not pol:
        m = re.search(r"(?i)last\s+foreign\s+port[^:\n]*[:：]\s*[A-Z]{3,8}\s+([A-Z][A-Za-z ]{2,40})(?:\n|$)", text)
        if m:
            pol = m.group(1).strip()
    if not pol:
        pol = _kv(text, ["port of loading", "loading port", "pol", "起运港", "装货港", "发货港", "出发港"])
    if not pod:
        m = re.search(r"(?m)^[ \t]*([A-Z][A-Za-z .'-]{2,25}),\s*(CA|NY|TX|GA|SC|FL|IL|WA|LA|VA|MD|PA|NC|AL|MA|NJ|OR|NC)\s*$", text)
        if m:
            pod = m.group(1).strip() + ", " + m.group(2)
    if not pod:
        m = re.search(r"卸港\s*[:：][^\n]*\n(?:[^\n]{0,120}\n){0,8}\s*([A-Z][A-Za-z]{2,25})\s*/\s*", text)
        if m:
            pod = m.group(1)
    if not pod:
        pod = _kv(text, ["port of discharge", "discharge port", "pod", "port of destination", "目的港", "卸货港"])
    return _clean_port(pol), _clean_port(pod)


def _extract_etd_eta(text, plan):
    etd = eta = ""
    if plan:
        etd, eta = plan["etd"], plan["eta"]
    if not eta:
        m = re.search(r"(?i)p\s*o\s*d\s*/\s*d\s*e\s*l\s*e\s*t\s*a\s*[:：]?\s*(" + _DATE_RX + r")", text)
        if m:
            eta = m.group(1)
    if not eta:
        m = re.search(r"(?:卸港|port of discharge|discharge)[\s\S]{0,400}?eta\s*(?:date)?\s*[:：]?\s*(" + _DATE_RX + r")", text, re.I)
        if m:
            eta = m.group(1)
    if not etd or not eta:
        m = re.search(r"(?i)latest\s+eta\s*/\s*etd\s*[:：]?\s*(" + _DATE_RX + r")\s*/\s*(" + _DATE_RX + r")", text)
        if m:
            if not eta:
                eta = m.group(1)
            if not etd:
                etd = m.group(2)
    if not etd or not eta:
        m = re.search(r"起点\s+终点\s+运输方式\s+预计开船时间\s+预计到达时间[^\n]*\n\s*[^\n]*?\b(" + _DATE_RX + r")\s+(" + _DATE_RX + r")", text)
        if m:
            if not etd:
                etd = m.group(1)
            if not eta:
                eta = m.group(2)
    if not etd:
        m = re.search(r"(?i)estimated departure date\s*[:：]?\s*(\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4})", text)
        if m:
            etd = m.group(1)
    if not eta:
        m = re.search(r"(?i)estimated dates? of arrival\s*[:：]?\s*(\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4})", text)
        if m:
            eta = m.group(1)
    if not etd:
        m = re.search(r"(?i)\betd\b\s*(?:date)?\s*[:：]?", text)
        if m:
            dm = re.search(_DATE_RX, text[m.end():m.end() + 500])
            if dm:
                etd = dm.group(0)
    if not eta:
        matches = list(re.finditer(r"(?i)\beta\b\s*(?:date)?\s*[:：]", text))
        if matches:
            dm = re.search(_DATE_RX, text[matches[-1].end():matches[-1].end() + 500])
            if dm:
                eta = dm.group(0)
    if not etd:
        m = re.search(r"预计开船时间[\s:：]*(" + _DATE_RX + r")", text)
        if m:
            etd = m.group(1)
    if not eta:
        m = re.search(r"预计到达时间[\s:：]*(" + _DATE_RX + r")", text)
        if m:
            eta = m.group(1)
    return parse_date(etd), parse_date(eta)


_OCR_ENGINE = None
# OCR 全局串行锁：RapidOCR 吃 CPU，超时放弃的解析线程可能仍在后台跑，
# 加锁保证同一时间只有一个 OCR 在执行，避免任务堆积拖垮服务器。
_OCR_LOCK = threading.Lock()


def _ocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE


def _ocr_text(path):
    if not _OCR_LOCK.acquire(timeout=15):
        return ""
    try:
        import numpy as np
        import pymupdf
        eng = _ocr_engine()
        doc = pymupdf.open(path)
        out = []
        for page in doc:
            pix = page.get_pixmap(dpi=170, colorspace=pymupdf.csRGB)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            result, _ = eng(arr)
            if result:
                for r in result:
                    out.append(r[1])
        return "\n".join(out)
    except Exception:
        return ""
    finally:
        _OCR_LOCK.release()


def _ocr_vessel(path):
    if not _OCR_LOCK.acquire(timeout=15):
        return "", ""
    try:
        import numpy as np
        import pymupdf
        eng = _ocr_engine()
        doc = pymupdf.open(path)
        pix = doc[0].get_pixmap(dpi=170, colorspace=pymupdf.csRGB)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        result, _ = eng(arr)
        if not result:
            return "", ""
        for r in result:
            t = r[1].strip().upper()
            m = re.match(r"^([A-Z]{4,})([A-Z])(\d{2})/(E\d{3}|W\d{3})$", t)
            if m:
                return m.group(1) + " " + m.group(2) + m.group(3), m.group(4)
        return "", ""
    except Exception:
        return "", ""


def _is_mojibake(text):
    if not text:
        return False
    suspicious = len(re.findall(r"[\u00ad\u00b0-\u00ff]", text))
    ascii_n = len(re.findall(r"[A-Za-z]", text))
    return suspicious >= 10 and suspicious >= ascii_n * 0.4


def _parse_so_text(raw):
    text = re.sub(r"(?<=[A-Za-z])[\s]+(?=[a-z])", "", raw)
    text = re.sub(r"(?<=[^A-Za-z0-9])([A-Za-z])[ \t]+([A-Za-z]{1,60})", lambda m: m.group(1) + m.group(2), text)
    text = "\n".join(line.strip() for line in text.splitlines())
    one = text.replace("\n", " ")
    parsed = {}
    containers = []
    for m in CONTAINER_RE.finditer(text.upper()):
        if m.group(0) not in containers:
            containers.append(m.group(0))
    parsed["containers"] = containers
    parsed["so"] = _extract_so(one)
    if parsed["so"]:
        containers = [c for c in containers if parsed["so"] not in c]
    parsed["containers"] = containers
    plan = _extract_plan(text)
    parsed["vessel"] = _extract_vessel(text, plan)
    parsed["voyage"] = _extract_voyage(text, plan)
    if "/" in parsed["vessel"]:
        parts = parsed["vessel"].rsplit("/", 1)
        parsed["vessel"] = parts[0].strip()
        cand = parts[1].strip()
        if not parsed["voyage"] and re.match(r"^[0-9][A-Za-z0-9]{2,11}$", cand):
            parsed["voyage"] = cand
    if not parsed["voyage"]:
        v, vg = _split_vessel_voyage(parsed["vessel"])
        if vg:
            parsed["vessel"], parsed["voyage"] = v, vg
    parsed["etd"], parsed["eta"] = _extract_etd_eta(text, plan)
    parsed["pol"], parsed["pod"] = _extract_pol_pod(text)
    parsed["shipping_line"] = detect_line(one)
    if re.search(r"\bONE\b", one) and not parsed["shipping_line"]:
        parsed["shipping_line"] = "ONE"
    low = one.lower()
    if "zim.com" in low or "zimushh" in low:
        parsed["shipping_line"] = "以星 ZIM"
    return parsed, []


def parse_so_pdf(path, timeout=8):
    """Parse a booking confirmation PDF. Returns (parsed_dict, warnings_list)."""
    import threading
    result = [None, None]
    def _do():
        try:
            result[0], result[1] = _parse_so_pdf_inner(path)
        except Exception as e:
            result[0] = None
            result[1] = [str(e)[:100]]
    th = threading.Thread(target=_do, daemon=True)
    th.start()
    th.join(timeout=timeout)
    if th.is_alive():
        return None, ["PDF 解析超时（> %ds）" % timeout]
    return result[0], result[1] or []


def _parse_so_pdf_inner(path):
    from pypdf import PdfReader
    reader = PdfReader(path)
    texts = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        texts.append(t)
    raw = "\n".join(texts)
    if _is_mojibake(raw) or not raw.strip():
        ocr = _ocr_text(path)
        if ocr.strip():
            parsed, warn = _parse_so_text(ocr)
        elif not raw.strip():
            return None, ["PDF 未提取到文本（可能是扫描件，需要 OCR）"]
        else:
            parsed, warn = _parse_so_text(raw)
    else:
        parsed, warn = _parse_so_text(raw)
    if not parsed["vessel"]:
        v, vg = _ocr_vessel(path)
        if v:
            parsed["vessel"] = v
            if not parsed["voyage"]:
                parsed["voyage"] = vg
    return parsed, warn


def _date_obj(s):
    s = parse_date(s)
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def learn_voyage_days(records):
    """从历史记录学习航程天数（中位数），key 分三级：船公司+目的港 → 目的港 → 全局。"""
    stats = {}

    def push(key, days):
        if not key or not days or not (5 <= days <= 120):
            return
        stats.setdefault(key, []).append(days)

    for r in records or []:
        dep = _date_obj(r.get("actual_sail_date")) or _date_obj(r.get("etd"))
        arr = _date_obj(r.get("actual_arrival_date")) or _date_obj(r.get("eta_so"))
        if not dep or not arr or arr < dep:
            continue
        days = (arr - dep).days
        pod = (r.get("pod") or "").strip().lower()
        line = (r.get("shipping_line") or "").strip().lower()
        push(("line", line, pod), days)
        push(("pod", pod), days)
        push(("all",), days)
    learned = {}
    for key, vals in stats.items():
        vals.sort()
        learned[key] = vals[len(vals) // 2]
    return learned


def voyage_days_for(learned, pod, shipping_line, default):
    podk = (pod or "").strip().lower()
    lk = (shipping_line or "").strip().lower()
    for key in [("line", lk, podk), ("pod", podk), ("all",)]:
        if key in (learned or {}):
            return learned[key]
    return default


def compute_eta(rec, learned=None):
    eta_so = parse_date(rec.get("eta_so"))
    etd = parse_date(rec.get("etd"))
    loading = parse_date(rec.get("loading_date"))
    sail = parse_date(rec.get("actual_sail_date"))
    rec["eta_so"] = eta_so
    rec["etd"] = etd
    rec["loading_date"] = loading
    rec["actual_sail_date"] = sail
    if eta_so:
        rec["eta_est"] = eta_so
        rec["eta_basis"] = "so"
    else:
        base = sail or etd
        if base:
            try:
                b = datetime.strptime(base, "%Y-%m-%d").date()
                days = voyage_days_for(learned, rec.get("pod"), rec.get("shipping_line"), transit_days(rec.get("pod")))
                rec["eta_est"] = _fmt(b + timedelta(days=days))
                rec["eta_basis"] = "est"
            except ValueError:
                rec["eta_est"] = None
                rec["eta_basis"] = "none"
        else:
            rec["eta_est"] = None
            rec["eta_basis"] = "none"
    return rec


def build_record(parsed):
    rec = {
        "container_no": parsed.get("container_no", ""),
        "so": parsed.get("so", ""),
        "factory": parsed.get("factory", ""),
        "vessel": parsed.get("vessel", ""),
        "voyage": parsed.get("voyage", ""),
        "pol": parsed.get("pol", ""),
        "pod": parsed.get("pod", ""),
        "etd": parsed.get("etd", ""),
        "eta_so": parsed.get("eta", ""),
        "loading_date": parsed.get("loading_date", ""),
        "shipping_line": parsed.get("shipping_line", ""),
        "lines": parsed.get("lines", []),
        "created_at": _now().strftime("%Y-%m-%d %H:%M:%S"),
        "manual_status": "",
        "actual_sail_date": "",
        "actual_arrival_date": "",
    }
    return compute_eta(rec)
