import sys, os
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
sys.path.insert(0, r'C:\Users\1\Documents\Default Project')
import pricing

path = r'E:\新建文件夹\海外仓\正式价格'
files = [f for f in os.listdir(path) if f.endswith('.xlsx')]

for fi, f in enumerate(files):
    rec = pricing.parse_pricing_excel(os.path.join(path, f))
    print("=== %s ===" % rec["name"][:20])
    print("  Shipping: %d tables" % len(rec["shipping"]))
    for st in rec["shipping"]:
        print("    %s (%s)" % (st["carrier"], st["sheet"]))
    print("  Surcharges: %d groups" % len(rec["surcharges"]))
    for sg in rec["surcharges"]:
        tp = sum(item["price"] for item in sg["items"])
        print("    %s: %d items, sum=$%.2f" % (sg["name"][:30], len(sg["items"]), tp))
        for item in sg["items"][:5]:
            print("      [%s] %s: $%.2f zone=%s" % (item["category"], item["desc"][:30], item["price"], item.get("zone")))
    print()
