import sys, os, re
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
sys.path.insert(0, r'C:\Users\1\Documents\Default Project')
import pricing

path = r'E:\新建文件夹\海外仓\正式价格'
files = sorted([f for f in os.listdir(path) if f.endswith('.xlsx')])
import openpyxl

# Direct test of _try_parse_outbound on 乐歌
wb = openpyxl.load_workbook(os.path.join(path, files[0]), read_only=True, data_only=True)
ws = wb["海外仓出入库操作"]
rows = list(ws.iter_rows(values_only=True))

print("=== Direct test on 乐歌 ===")
record = {"handling": {"outbound": [], "inbound": [], "storage": [], "value_added": []}, "warehouses": [], "shipping": [], "surcharges": []}

# Step by step
text_all = pricing._txt(rows).lower()
print("Step 1: keyword check")
has_kw = any(k in text_all for k in ["订单处理", "出库费", "出库服务", "toc", "一件代发"])
print("  has_kw:", has_kw)

print("Step 2: warehouse columns")
wh_cols = []
for ri, row in enumerate(rows[:8]):
    for ci, c in enumerate(row):
        if c and isinstance(c, str):
            s = c.strip()
            if re.match(r"^(美[东西南]仓?\s*[A-Z]*|ALL|[A-Z]{2,4}\d?|CA$|NJ$|ATL$|SAV$|TX$|HOU$|GA$|洛杉矶|新泽西|芝加哥|萨凡纳|休斯顿)", s):
                wh_cols.append((ci, s))
print("  wh_cols:", wh_cols)

print("Step 3: find tier column")
tier_col = -1
price_col_start = -1
for ri, row in enumerate(rows):
    for ci, c in enumerate(row):
        if pricing._is_tier(c):
            tier_col = ci
            price_col_start = ci + 1
            print("  Found tier at R%dC%d: %s" % (ri+1, ci, str(c)[:30]))
            break
    if tier_col >= 0: break
print("  tier_col:", tier_col, "price_col_start:", price_col_start)

print("Step 4: service detection")
service = "standard"
for ri in range(max(0, tier_col - 5), min(tier_col + 1, len(rows))):
    text = " ".join(str(c) for c in rows[ri] if c).lower()
    if "自提" in text or "self" in text or "pickup" in text:
        service = "self_pickup"
    elif "拒收" in text or "退货" in text or "return" in text:
        service = "return"
    elif "转运" in text or "批量" in text:
        service = "transfer"
print("  service:", service, "(tier_col=%d, checking rows %d-%d)" % (tier_col, max(0, tier_col-5), min(tier_col+1, len(rows))))

print("Step 5: extract tiers")
added = 0
for ri in range(len(rows)):
    row = rows[ri]
    tier_text = row[tier_col] if tier_col < len(row) else None
    tier = pricing._parse_tier(tier_text)
    if tier is None:
        continue
    lo, hi = tier
    if lo == 0 and hi == 0:
        continue

    if wh_cols:
        for ci, wh in wh_cols:
            if ci >= price_col_start:
                price = pricing._num(row[ci] if ci < len(row) else None)
                if price is not None and price > 0:
                    key = (lo, hi, wh, service)
                    added += 1
                    if added <= 3:
                        print("  Add: %s-%s lbs, $%s, %s, %s" % (lo, hi, price, wh, service))
    else:
        price = pricing._num(row[price_col_start] if price_col_start < len(row) else None)
        if price is not None and price > 0:
            key = (lo, hi, "ALL", service)
            added += 1
            if added <= 3:
                print("  Add: %s-%s lbs, $%s, ALL, %s" % (lo, hi, price, service))

print("  Total added:", added)
wb.close()
