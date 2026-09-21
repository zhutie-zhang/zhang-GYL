import sys, os
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
sys.path.insert(0, r'C:\Users\1\Documents\Default Project')

# Monkeypatch to add debug
import pricing
_orig_try = pricing._try_parse_outbound

def _debug_outbound(rows, record, sn):
    text_all = pricing._txt(rows).lower()
    has_kw = any(k in text_all for k in ["订单处理", "出库费", "出库服务", "toc", "一件代发"])
    if not has_kw:
        return
    
    tier_pat = pricing.re.compile(r"\d+.*[<≤].*\d+|W\s*[>≥]\s*\d+|≤\s*\d+", pricing.re.I)
    tier_count = 0
    for ri, row in enumerate(rows):
        for ci, c in enumerate(row):
            if c and isinstance(c, str) and tier_pat.search(str(c).strip()):
                tier_count += 1
                if tier_count <= 3:
                    nearby = []
                    for j in range(max(0,ci-1), min(ci+3, len(row))):
                        v = row[j] if j < len(row) else None
                        nearby.append("[%d]=%s" % (j, str(v)[:15] if v else "None"))
                    print("    TIER R%dC%d: %s  | %s" % (ri+1, ci, str(c)[:25], " ".join(nearby)))
    print("  [DEBUG] Sheet '%s': has_kw=%s, total_tiers=%d, record_outbound_before=%d" % (sn, has_kw, tier_count, len(record["handling"]["outbound"])))
    
    _orig_try(rows, record, sn)
    
    print("  [DEBUG] record_outbound_after=%d" % len(record["handling"]["outbound"]))

pricing._try_parse_outbound = _debug_outbound

path = r'E:\新建文件夹\海外仓\正式价格'
files = sorted([f for f in os.listdir(path) if f.endswith('.xlsx')])

for f in files:
    print("=== %s ===" % f[:40])
    try:
        rec = pricing.parse_pricing_excel(os.path.join(path, f))
        print("  Result: outbound=%d, inbound=%d, storage=%d, shipping=%d, surcharges=%d" % (
            len(rec["handling"]["outbound"]),
            len(rec["handling"]["inbound"]),
            len(rec["handling"]["storage"]),
            len(rec["shipping"]),
            len(rec["surcharges"]),
        ))
    except Exception as e:
        print("  ERROR: %s" % e)
        import traceback; traceback.print_exc()
    print()
