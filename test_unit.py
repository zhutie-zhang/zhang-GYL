import sys, os
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
sys.path.insert(0, r'C:\Users\1\Documents\Default Project')
import pricing

path = r'E:\新建文件夹\海外仓\正式价格'
files = [f for f in os.listdir(path) if f.endswith('.xlsx')]
store = pricing.PricingStore()
store.clear()
for f in files:
    rec = pricing.parse_pricing_excel(os.path.join(path, f))
    store.add(rec)

records = store.list_all()
print("COMPARE 5lbs Zone5:")
results = pricing.compare_pricing(records, weight=5.0, zone="Zone5")
for x in results:
    print("  %s: total=$%.2f (h=$%.2f s=$%.2f a=$%.2f)" % (
        x["name"][:25], x["total"], x["handling"], x["shipping"], x["surcharges"]))

print()
print("COMPARE 10lbs Zone2:")
results = pricing.compare_pricing(records, weight=10.0, zone="Zone2")
for x in results:
    print("  %s: total=$%.2f (h=$%.2f s=$%.2f a=$%.2f)" % (
        x["name"][:25], x["total"], x["handling"], x["shipping"], x["surcharges"]))

print()
print("COMPARE 2lbs Zone8:")
results = pricing.compare_pricing(records, weight=2.0, zone="Zone8")
for x in results:
    print("  %s: total=$%.2f (h=$%.2f s=$%.2f a=$%.2f)" % (
        x["name"][:25], x["total"], x["handling"], x["shipping"], x["surcharges"]))
