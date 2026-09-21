import sys, os
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
sys.path.insert(0, r'C:\Users\1\Documents\Default Project')
import importlib, pricing
importlib.reload(pricing)

store = pricing.PricingStore()
store.clear()
print("Cleared old data.")

import glob
files = [f for f in glob.glob(r'E:\新建文件夹\海外仓\正式价格\*.xlsx') if not os.path.basename(f).startswith('~$')]
for f in sorted(files):
    try:
        rec = pricing.parse_pricing_excel(f)
        store.add(rec)
        h = rec['handling']
        print('%s: out=%d in=%d stg=%d va=%d ship=%d surch=%d' % (
            rec['name'][:30], len(h['outbound']), len(h['inbound']),
            len(h['storage']), len(h['value_added']),
            len(rec['shipping']), len(rec['surcharges'])))
    except Exception as e:
        print('ERROR %s: %s' % (os.path.basename(f), e))

print("\nVerifying:")
records = store.list_all()
r = pricing.compare_pricing(records, weight=60.0, zone='Zone2')
for x in r:
    print('  %s: $%.2f (out=$%.2f ship=$%.2f surch=$%.2f fuel=$%.2f)' % (
        x['name'][:25], x['total'], x['handling'], x['shipping'],
        x['surcharges'], x['fuel_surcharge']))
