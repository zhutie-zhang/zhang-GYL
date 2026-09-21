import sys, os, re, glob, shutil
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
sys.path.insert(0, r'C:\Users\1\Documents\Default Project')
for key in list(sys.modules.keys()):
    if 'pricing' in key: del sys.modules[key]
pycache = r'C:\Users\1\Documents\Default Project\__pycache__'
if os.path.exists(pycache): shutil.rmtree(pycache)

import openpyxl

files = glob.glob(r'E:\新建文件夹\海外仓\正式价格\*.xlsx')
smart = [f for f in files if 'SMART' in os.path.basename(f) and '~$' not in os.path.basename(f)]
wb = openpyxl.load_workbook(smart[0], read_only=True, data_only=True)
ws = wb['Fedex_AHS']
rows = list(ws.iter_rows(values_only=True))

# Manually trace _parse_surcharges_grouped
zone_col_map = {}
header_ri = -1
for ri, row in enumerate(rows[:20]):
    for ci in range(9, min(len(row), 25)):
        c = row[ci]
        if c and isinstance(c, str):
            zm = re.search(r"Zones?\s*(\d+)(?:\s*[\u2013\-]\s*(\d+))?(?:\+)?", c.strip(), re.I)
            if zm:
                z1 = int(zm.group(1))
                z2 = int(zm.group(2)) if zm.group(2) else z1
                zone_col_map[ci] = ["Zone%d" % z for z in range(z1, z2 + 1)]
    if len(zone_col_map) >= 3:
        header_ri = ri
        break

print('zone_col_map:', zone_col_map)
print('header_ri:', header_ri)
print()

current_category = None
for ri in range(header_ri + 1, len(rows)):
    row = rows[ri]
    right_texts = []
    for ci in range(9, min(len(row), 25)):
        c = row[ci]
        if c is not None:
            right_texts.append(str(c).strip())

    if not right_texts:
        current_category = None
        print('R%d: RESET category (empty right_texts)' % ri)
        continue

    full_text = ' '.join(right_texts)
    full_lower = full_text.lower()

    if re.search(r'燃油|fuel\s*surcharge', full_lower):
        print('R%d: SKIP fuel' % ri)
        continue

    cat_detected = False
    for t in right_texts:
        tl = t.lower()
        if re.search(r'ahs.*dimension|dimension.*gd|超尺寸|最长边.*48|次长边.*30|围长', tl, re.I):
            current_category = 'AHS_Dimension'; cat_detected = True; break
        elif re.search(r'ahs.*weight|weight.*gd|超重附加|实际重量.*50\s*lbs|重量.*50', tl, re.I):
            current_category = 'AHS_Weight'; cat_detected = True; break
        elif re.search(r'ahs.*packag|packag.*gd|非标准.*包装|没有完全装入|外包装非瓦楞', tl, re.I):
            current_category = 'AHS_Packaging'; cat_detected = True; break
        elif re.search(r'additional\s*handling', tl, re.I):
            current_category = 'AHS'; cat_detected = True; break
        elif re.search(r'oversize|超尺寸附|超大', tl, re.I):
            current_category = 'Oversize'; cat_detected = True; break
        elif re.search(r'residential|住宅地址附', tl, re.I):
            current_category = 'Residential'; cat_detected = True; break
        elif re.search(r'address.*correct|地址修正', tl, re.I):
            current_category = 'Address_Correction'; cat_detected = True; break
        elif re.search(r'demand', tl, re.I):
            current_category = 'Demand'; cat_detected = True; break

    row_has_data = False
    for ci in zone_col_map:
        if ci < len(row) and row[ci] is not None:
            cs = str(row[ci]).strip()
            if cs and re.search(r"\d", cs):
                row_has_data = True
                break

    if not row_has_data:
        continue

    for ci, zones in zone_col_map.items():
        if ci >= len(row) or row[ci] is None:
            continue
        cs = str(row[ci]).strip()
        if not cs:
            continue
        pv = None
        pm = re.search(r"\$?(\d+\.?\d*)", cs)
        if pm:
            pv = float(pm.group(1))
        if pv is not None and pv > 0 and pv < 500:
            print('R%d: cat=%s zone=%s price=%.4f cs="%s"' % (ri, current_category, zones[0] if zones else '?', pv, cs))

wb.close()
