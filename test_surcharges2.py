import sys, os
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
sys.path.insert(0, r'C:\Users\1\Documents\Default Project')
import pricing

path = r'E:\新建文件夹\海外仓\正式价格'
files = [f for f in os.listdir(path) if f.endswith('.xlsx')]
records = {}
for f in files:
    rec = pricing.parse_pricing_excel(os.path.join(path, f))
    records[rec["rid"]] = rec

# Check surcharges for Zone5
for rid, rec in records.items():
    print("=== %s ===" % rec["name"][:25])
    zone5_items = []
    flat_items = []
    for sg in rec.get("surcharges", []):
        for item in sg.get("items", []):
            iz = item.get("zone")
            p = item.get("price", 0)
            if p <= 0: continue
            if iz == "Zone5":
                zone5_items.append((sg["name"], item["category"], item["desc"][:30], p))
            elif iz is None and p < 25:
                flat_items.append((sg["name"], item["category"], item["desc"][:30], p))
    print("  Zone5 surcharges: %d items" % len(zone5_items))
    for name, cat, desc, p in zone5_items:
        print("    %s [%s] %s: $%.2f" % (name[:20], cat, desc, p))
    print("  Flat surcharges (<$25): %d items" % len(flat_items))
    for name, cat, desc, p in flat_items:
        print("    %s [%s] %s: $%.2f" % (name[:20], cat, desc, p))
    print()
