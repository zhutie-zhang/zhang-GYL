import sys, os, json
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
sys.path.insert(0, r'C:\Users\1\Documents\Default Project')
import pricing

path = r'E:\新建文件夹\海外仓\正式价格'
files = [f for f in os.listdir(path) if f.endswith('.xlsx')]

for f in files:
    fp = os.path.join(path, f)
    try:
        rec = pricing.parse_pricing_excel(fp)
        print("=== %s ===" % rec["name"])
        print("  Warehouses: %s" % rec["warehouses"])
        print("  Outbound tiers: %d" % len(rec["handling"]["outbound"]))
        for t in rec["handling"]["outbound"][:5]:
            print("    %s-%s lbs: $%s (%s)" % (t["min_lbs"], t["max_lbs"], t["price"], t["warehouse"]))
        if len(rec["handling"]["outbound"]) > 5:
            print("    ...")
        print("  Inbound items: %d" % len(rec["handling"]["inbound"]))
        for item in rec["handling"]["inbound"][:3]:
            print("    %s: $%s %s" % (item["desc"][:50], item["price"], item["unit"]))
        print("  Storage items: %d" % len(rec["handling"]["storage"]))
        print("  Value-added items: %d" % len(rec["handling"]["value_added"]))
        print("  Shipping tables: %d" % len(rec["shipping"]))
        for st in rec["shipping"]:
            print("    %s: %d zones, weight %s-%s" % (st["carrier"], len(st["zones"]), st["min_weight"], st["max_weight"]))
            for zn, prices in list(st["zones"].items())[:2]:
                items = list(prices.items())[:3]
                print("      %s: %s" % (zn, items))
        print("  Surcharges: %d" % len(rec["surcharges"]))
        for sg in rec["surcharges"]:
            print("    %s: %d items" % (sg["name"], len(sg["items"])))
            for item in sg["items"][:3]:
                print("      %s: $%s zone=%s" % (item["desc"][:40], item["price"], item.get("zone")))
        print()
    except Exception as e:
        print("ERROR %s: %s" % (f, e))
        import traceback; traceback.print_exc()
