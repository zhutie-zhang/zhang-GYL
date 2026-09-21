import sys, os, re
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
sys.path.insert(0, r'C:\Users\1\Documents\Default Project')
import openpyxl

path = r'E:\新建文件夹\海外仓\正式价格\云帆济实力派一件代发大客户报价单- 20260113.xlsx'
wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
ws = wb['库内费用']
rows = list(ws.iter_rows(values_only=True))

# Check rows 3-6 (0-indexed) in detail
for ri in range(3, 7):
    row = rows[ri]
    print("R%d: %s" % (ri, repr(row[:8])))
wb.close()
