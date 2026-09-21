"""账单核对引擎（服务端版）— 移植自 price-checker.html startCheck。

数据源：统一价卡 data/unified_{channels,templates,fuel}.json（price_data）。
接口：
  parse_matrix(matrix)          → 表头识别+列映射+标准行（供 /api/bill/parse）
  check_bill(rows, ...)         → 逐行核对 {summary, results}（供 /api/bill-check）
算法与原前端 1:1：渠道三路径(燃油/附加费/基础运费) + 模板匹配 + 1%容差。
"""
import re, json
import price_data  # noqa: E402

R2 = lambda x: round(x * 100) / 100


def _norm(h):
    if h is None: return ""
    s = str(h).lower()
    s = re.sub(r"[（(][^）)]*[）)]", "", s)
    s = re.sub(r"[\s_\-\\/./:：（）()【】\[\]·]", "", s)
    return s


def _score(h, kws):
    if h is None or h == "": return 0
    n = _norm(h)
    for k in kws:
        nk = _norm(k)
        if nk == n: return 3
        if nk and (nk in n or n in nk): return 2
    return 0


STANDARD_FIELDS = [
    dict(key="serviceType", kws=["服务类型", "费用类型", "费用项目", "费用名称", "项目", "类型", "服务", "description", "item", "service", "type", "chargeitem"]),
    dict(key="unitPrice", kws=["单价", "price", "unitprice", "unit price", "rate"]),
    dict(key="unit", kws=["计费单位", "计量单位", "单位", "uom", "unitofmeasure"]),
    dict(key="amount", kws=["金额", "费用", "总金额", "合计", "amount", "total", "charge", "amt", "fee"]),
    dict(key="weight", kws=["计费重", "计费重量", "重量", "weight", "磅", "chargeweight"]),
    dict(key="zone", kws=["zone", "分区"]),
    dict(key="tracking", kws=["追踪", "tracking", "运单号", "tn", "waybill", "物流单号"]),
    dict(key="ref", kws=["参考号", "订单号", "ref", "po", "order", "reference", "客户单号"]),
    dict(key="date", kws=["日期", "date", "时间", "出库日期", "账单日期"]),
    dict(key="note", kws=["备注", "说明", "note", "remark", "comment"]),
]


# ── 账单矩阵解析 ──────────────────────────────────────────────
def detect_header_row(matrix):
    best, best_score = -1, 0
    for i, row in enumerate(matrix):
        row = row or []
        non_empty = [c for c in row if c is not None and str(c).strip() != ""]
        if len(non_empty) < 2: continue
        score = 0
        for c in non_empty:
            t = str(c).strip()
            for f in STANDARD_FIELDS:
                if _score(t, f["kws"]) >= 2:
                    score += 1; break
        alpha = sum(1 for c in non_empty if re.search(r"[a-zA-Z\u4e00-\u9fa5]", str(c)))
        if alpha >= len(non_empty) * 0.3:
            score += 0.5
        if score > best_score:
            best_score, best = score, i
    return best if (best >= 0 and best_score >= 2.5) else -1


def auto_map_columns(headers):
    used, mapping = set(), {}
    for f in STANDARD_FIELDS:
        bi, bs = -1, 0
        for i, h in enumerate(headers):
            if i in used: continue
            s = _score(h, f["kws"])
            if s > bs: bs, bi = s, i
        mapping[f["key"]] = bi if (bi >= 0 and bs >= 2) else -1
        if bi >= 0: used.add(bi)
    return mapping


def build_standard_rows(matrix, header_ri, mapping):
    hdr = matrix[header_ri] if header_ri >= 0 else []
    key_cols = {}
    for f in STANDARD_FIELDS:
        ci = mapping.get(f["key"], -1)
        key_cols[f["key"]] = ci if (0 <= ci < len(hdr)) else -1
    out = []
    for r in matrix[header_ri + 1:] if header_ri >= 0 else matrix:
        if not r: continue
        o = {}
        for f in STANDARD_FIELDS:
            ci = key_cols.get(f["key"], -1)
            v = r[ci] if (ci >= 0 and ci < len(r) and r[ci] is not None) else ""
            o[f["key"]] = str(v).strip()
        if any(o.values()):
            out.append(o)
    return out


def parse_matrix(matrix):
    hri = detect_header_row(matrix)
    rows = [[]] * len(matrix) if hri < 0 else matrix
    headers = [str(c or "") for c in rows[hri]] if hri >= 0 else []
    mapping = auto_map_columns(headers) if hri >= 0 else {f["key"]: -1 for f in STANDARD_FIELDS}
    std = build_standard_rows(matrix, hri, mapping)
    amt = sum(1 for r in std if _num(r.get("amount")) is not None)
    return {"header_row": hri, "mapping": mapping, "standard_rows": std,
            "with_amount": amt, "rows_total": len(std)}


# ── 核对辅助 ──────────────────────────────────────────────────
def _num(v):
    if v is None or v == "": return None
    if isinstance(v, (int, float)): return float(v)
    s = str(v).strip().replace(",", "").replace("$", "")
    s = re.sub(r"[^\d.\-]", "", s)
    try: return float(s) if s else None
    except: return None


def _zone_num(zt):
    if zt is None: return None
    m = re.sub(r"[^0-9]", "", str(zt))
    try: return int(m) if m else None
    except: return None


def zone_group_index(zone_num):
    if zone_num is None: return 0
    if zone_num <= 2: return 0
    if zone_num <= 4: return 1
    if zone_num <= 6: return 2
    return 3


def lookup_channel_price(channel, weight, zone_text):
    if not channel: return None
    znum = _zone_num(zone_text)
    if znum is None: return None
    zi = None
    for i, z in enumerate(channel.get("zones", [])):
        if _zone_num(z) == znum:
            zi = i; break
    if zi is None:
        for i, z in enumerate(channel.get("zones", [])):
            if znum and z and str(znum) in str(z).lower() or (zone_text and str(z).lower() in str(zone_text).lower()):
                zi = i; break
    rows = channel.get("rows", [])
    if zi is None or not rows: return None
    w = math_ceil(weight) if weight else 0
    ri = None
    for i, r in enumerate(rows):
        if r.get("weight") == w: ri = i; break
    if ri is None:
        for i, r in enumerate(rows):
            if r.get("weight", 0) > w: ri = i; break
    if ri is None: ri = len(rows) - 1
    p = rows[ri]["prices"][zi] if zi < len(rows[ri].get("prices", [])) else None
    return {"price": p, "zone": channel["zones"][zi], "weight": rows[ri].get("weight"),
            "overRange": w > rows[-1].get("weight", 0)}


def math_ceil(x):
    from math import ceil
    return ceil(x)


def lookup_surcharge(channel, text, zone_text):
    if not channel: return None
    surs = channel.get("surcharges") or []
    if not surs: return None
    n_bill = _norm(text)
    if not n_bill: return None
    znum = _zone_num(zone_text)
    group = 0 if znum is None else zone_group_index(znum)
    best, best_score = None, 0
    for s in surs:
        nm = _norm(s.get("name"))
        if not nm: continue
        name_score = 2 if n_bill == nm else (1 if (nm in n_bill or n_bill in nm) else 0)
        cn = _norm(s.get("cond"))
        cond_score = 0
        if cn:
            if n_bill == cn: cond_score = 4
            elif cn.startswith(n_bill): cond_score = 3.5
            elif cn and n_bill and n_bill in cn and len(n_bill) >= 8: cond_score = 2.5
        score = max(cond_score, name_score * 0.9) if cond_score > 0 else name_score
        if score <= best_score: continue
        is_fuel = bool(re.search(r"(fuel|燃油)", str(s.get("name")), re.I))
        prices = s.get("prices") or []
        price = None if is_fuel else (prices[group] if group < len(prices) and prices[group] is not None else
                                      (next((p for p in prices if p is not None), None)))
        best = {"name": s.get("name"), "price": price, "group": group,
                "groupLabel": "不分区" if znum is None else ("Zone%d" % znum), "fuel": is_fuel}
        best_score = score
    return best if best_score > 0 else None


def latest_fuel(channel_name, fuel):
    recs = ((fuel.get(channel_name) or {}).get("records")) or []
    if not recs: return None
    recs = sorted(recs, key=lambda r: str(r.get("date") or ""), reverse=True)
    return recs[0]


def latest_fuel_percent(channel_name, fuel):
    r = latest_fuel(channel_name, fuel)
    return r.get("percent") if r else None


def template_price_for_weight(weight, tpl):
    tiers = tpl.get("tiers") or []
    if tiers:
        for t in tiers:
            lo, hi = t.get("min"), t.get("max")
            if lo is not None and weight > lo and (hi is None or weight <= hi):
                return {"price": t.get("price"), "tier": True}
        # fallback 最近档
        return {"price": tpl.get("price"), "tier": False}
    return {"price": tpl.get("price"), "tier": False}


_SERVICE_SYN = {
    "入库上架": ["inbound", "receive", "putaway", "上架", "入库", "收货"],
    "订单处理": ["order", "pick", "pack", "处理", "拣货", "打包", "出库"],
    "仓储费": ["storage", "仓储", "存放", "库存"],
    "尾程配送": ["shipping", "delivery", "carrier", "配送", "物流", "尾程", "运输"],
    "退货处理": ["return", "退货", "退件"],
    "贴标换标": ["label", "relabel", "贴标", "换标"],
}


def match_service_type(bill, tpl):
    if not bill or not tpl: return False
    b, t = bill.lower().strip(), tpl.lower().strip()
    if b == t: return True
    if t != "其他" and (b in t or t in b): return True
    for kw in (_SERVICE_SYN.get(tpl, []) or []):
        if kw in b: return True
    nb, nt = _norm(bill), _norm(tpl)
    return nt and (nt in nb or nb in nt)


_UNIT_SYN = {"kg": ["kg", "千克", "公斤"], "件": ["件", "个", "pcs", "piece", "ea"],
             "立方": ["m3", "cbm", "立方", "方"], "单": ["单", "票", "order", "shipment"],
             "次": ["次", "回", "time"]}


def match_unit(bill, tpl):
    if not bill or not tpl: return True
    b, t = bill.lower(), tpl.lower()
    for k, kws in _UNIT_SYN.items():
        ok_b = any(kw in b for kw in kws)
        ok_t = any(kw in t for kw in kws)
        if ok_b and ok_t: return True
    return False


# ── 主核对入口 ────────────────────────────────────────────────
def check_bill(rows, channel_name=None, provider=None, warehouse=None,
               weight_key="weight", zone_key="zone", channels=None,
               templates=None, fuel=None):
    channels = price_data.snapshot("channels") if channels is None else channels
    templates = price_data.snapshot("templates") if templates is None else templates
    fuel = price_data.snapshot("fuel") if fuel is None else fuel

    using_channel = bool(channel_name)
    channel = None
    if using_channel:
        channel = next((c for c in channels if c.get("name") == channel_name), None)
        if channel is None:
            return {"summary": {"total": 0, "match": 0, "diff": 0, "warn": 0},
                    "error": "渠道未找到", "results": []}
    tpl_list = [t for t in templates
                if t.get("provider") == provider and t.get("warehouse") == warehouse] \
        if provider and warehouse else []
    can_template_check = bool(provider) and bool(warehouse) and bool(tpl_list)

    # 预计算 燃油按运单聚合
    fuel_group_sum = {}
    if using_channel:
        for row in rows:
            service = str(row.get("serviceType") or row.get("服务类型") or "").lower()
            if re.search(r"(fuel|燃油)", service):
                continue
            amt = _num(row.get("amount") or row.get("金额")) or 0.0
            trk = str(row.get("tracking") or row.get("ref") or "").strip()
            if not trk: continue
            fuel_group_sum[trk] = fuel_group_sum.get(trk, 0.0) + amt

    results = []
    match_count = diff_count = warn_count = 0

    def push_warn(note, extra=None):
        nonlocal warn_count
        warn_count += 1
        r = {"row": 0, "billService": "", "billUnit": "", "billQty": 0,
             "billAmount": 0.0, "billUnitPrice": None, "tplPrice": None,
             "expectedAmount": None, "diff": None, "status": "warn", "note": note}
        if extra: r.update(extra)
        results.append(r)

    def push_compared(tpl_price, expected, basis):
        nonlocal match_count, diff_count
        diff = R2(_num(row_amt) - expected)
        tol = max(0.01, abs(expected) * 0.01)
        if abs(diff) < tol:
            status, note = "match", "价格一致"
            match_count += 1
        else:
            status, note = "diff", ("多收 $%.2f" % diff if diff > 0 else "少收 $%.2f" % abs(diff))
            diff_count += 1
        if basis: note += "｜" + basis
        results.append({"row": 0, "billService": bill_service, "billUnit": bill_unit,
                        "billQty": 0, "billAmount": _num(row_amt) or 0.0,
                        "billUnitPrice": _num(row.get("unitPrice")) or None,
                        "tplPrice": tpl_price, "expectedAmount": expected,
                        "diff": diff, "status": status, "note": note})

    for idx, row in enumerate(rows):
        bill_service = str(row.get("serviceType", "") or "")
        bill_unit = str(row.get("unit", "") or "")
        row_amt = row.get("amount", 0)
        bill_amount = _num(row_amt) or 0.0
        weight = _num(row.get(weight_key)) if weight_key else None
        zone = str(row.get(zone_key) or "") if zone_key else ""
        is_freight = using_channel and weight is not None and weight > 0 and zone

        if is_freight:
            sf = lookup_surcharge(channel, bill_service, zone)
            if sf and sf.get("fuel"):
                base_price = 0.0
                hit = lookup_channel_price(channel, weight, zone)
                if hit and hit.get("price") is not None:
                    base_price = hit["price"]
                pct = latest_fuel_percent(channel_name, fuel)
                trk = str(row.get("tracking") or "").strip() or str(row.get("ref") or "").strip()
                gs = fuel_group_sum.get(trk, 0.0)
                if pct is None:
                    push_warn("「%s」未记录官网费率：请到渠道 → 「燃油」录入本周费率" % sf["name"])
                elif gs > 0:
                    expected = R2(gs * pct / 100.0)
                    push_compared(None, expected, "燃油费 %s%% × (基础+该单附加)= %.2f×%s%% → 应收 %.2f"
                                  % (pct, gs, pct, expected))
                elif hit and hit.get("price") is not None:
                    expected = R2(hit["price"] * pct / 100.0)
                    push_compared(None, expected, "燃油费 %s%% × 基础运费 %.2f（%s·%s磅）"
                                  % (pct, hit["price"], hit["zone"], hit["weight"]))
                else:
                    push_warn("「%s」%s%% 需基础运费价（找不到 %s 分区报价）" % (sf["name"], pct, zone))
                continue
            if sf and sf.get("price") is not None:
                basis = "附加费：%s@$%.2f（%s）" % (sf["name"], sf["price"], sf.get("groupLabel"))
                push_compared(sf["price"], sf["price"], basis)
                continue
            hit = lookup_channel_price(channel, weight, zone)
            if not hit:
                push_warn("渠道「%s」未找到 %s 分区" % (channel_name, zone))
                continue
            if hit.get("price") is None:
                push_warn("%s 档无报价（计费重 %s磅）" % (hit["zone"], hit["weight"]))
                continue
            basis = "%s·计费重%s磅" % (hit["zone"], hit["weight"])
            if hit.get("overRange"): basis += "｜超出价格上限，按末档"
            push_compared(hit["price"], hit["price"], basis)
            continue

        if can_template_check:
            matched = None
            for t in tpl_list:
                if match_service_type(bill_service, t.get("serviceType")) and \
                        match_unit(bill_unit, t.get("unit")):
                    matched = t; break
            if not matched:
                push_warn("未匹配到模板（服务类型「%s」）" % bill_service)
                continue
            tier_hit = template_price_for_weight(weight or 0, matched)
            base_price = tier_hit["price"] if tier_hit["price"] is not None else matched.get("price")
            if base_price is None:
                push_warn("模板「%s」无价格" % matched.get("serviceType"))
                continue
            expected = max(1 * base_price, matched.get("minCharge") or 0)
            note = "模板：%s@$%.3f×1件" % (matched.get("serviceType"), base_price)
            if matched.get("note"): note += "（%s）" % matched["note"]
            push_compared(base_price, expected, note)
            continue
        push_warn(using_channel and "缺少计费重或分区，无法按渠道核对；且未选择服务商/仓点"
                  if (using_channel and not is_freight) else "未匹配到模板")

    # 回填行号
    for i, r in enumerate(results):
        r["row"] = i + 2
    return {"summary": {"total": len(results), "match": match_count,
                        "diff": diff_count, "warn": warn_count}, "results": results}


if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    demo = [
        {"serviceType": "尾程配送", "unit": "磅", "amount": "12.34",
         "weight": "2.5", "zone": "Zone4", "tracking": "1Z999"},
        {"serviceType": "Fuel Surcharge（燃油费）", "unit": "磅", "amount": "1.5",
         "weight": "2.5", "zone": "Zone4", "tracking": "1Z999"},
    ]
    ch = price_data.snapshot("channels")
    print("channels:", len(ch), "first:", ch[0]["name"] if ch else None)
    if ch:
        out = check_bill(demo, channel_name=ch[0]["name"], weight_key="weight", zone_key="zone",
                         channels=[ch[0]])
        print(json.dumps(out, ensure_ascii=False))
        print("matrix test:", parse_matrix([["日期", "追踪号", "分区", "费用项目", "计费重量", "计费单位", "金额"],
                                            ["2026-08-30", "1Z999", "Zone4", "尾程配送", "2.5", "磅", "12.34"]]))