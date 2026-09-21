import sys, os
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
sys.path.insert(0, r'C:\Users\1\Documents\Default Project')
import pricing

path = r'E:\新建文件夹\海外仓\正式价格'
files = [f for f in os.listdir(path) if f.endswith('.xlsx') and not f.startswith('~$')]
store = pricing.PricingStore()
store.clear()
for f in files:
    rec = pricing.parse_pricing_excel(os.path.join(path, f))
    store.add(rec)

records = store.list_all()
print("=== 60lbs Zone2 FedEx ===")
results = pricing.compare_pricing(records, weight=60.0, zone="Zone2")
for x in results:
    print("  %s: total=$%.2f (out=$%.2f ship=$%.2f surch=$%.2f fuel=$%.2f [%.1f%%])" % (
        x["name"][:25], x["total"], x["handling"], x["shipping"], x["surcharges"],
        x["fuel_surcharge"], x["fuel_pct"]))

print()
print("=== 5lbs Zone5 ===")
results = pricing.compare_pricing(records, weight=5.0, zone="Zone5")
for x in results:
    print("  %s: total=$%.2f (out=$%.2f ship=$%.2f surch=$%.2f fuel=$%.2f [%.1f%%])" % (
        x["name"][:25], x["total"], x["handling"], x["shipping"], x["surcharges"],
        x["fuel_surcharge"], x["fuel_pct"]))

# Show 乐歌 detail for 60lbs Zone2
print()
print("=== 乐歌 FedEx surcharges (Zone2) ===")
for rid, rec in records.items():
    if "乐歌" in rec.get("name", ""):
        for st in rec.get("shipping", []):
            if st["carrier"] == "FedEx":
                print("  Carrier: %s, Fuel: %.1f%%" % (st["carrier"], st["fuel_surcharge_pct"]*100))
                print("  Surcharges:")
                for sc in st.get("surcharges", []):
                    print("    %s %s: $%.2f" % (sc["category"], sc["zone"], sc["price"]))
                # Show shipping rate for 60lbs Zone2
                zn = st.get("zones", {}).get("Zone2", {})
                print("  Shipping Zone2 rates around 60lbs:")
                for ws, p in sorted(zn.items(), key=lambda x: float(x[0])):
                    w = float(ws)
                    if 55 <= w <= 65:
                        print("    %s lbs: $%.2f" % (ws, p))
        break
