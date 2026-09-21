import sys, os, re
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
sys.path.insert(0, r'C:\Users\1\Documents\Default Project')
import openpyxl

path = r'E:\新建文件夹\海外仓\正式价格\云帆济实力派一件代发大客户报价单- 20260113.xlsx'
wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
ws = wb['库内费用']
rows = list(ws.iter_rows(values_only=True))

for ri in range(17, 28):
    row = rows[ri]
    texts = [str(c).strip() if c else "" for c in row]
    row_text = " ".join(t for t in texts if t).lower()
    has_return = "退货" in row_text
    has_storage = "仓储费" in row_text
    print("R%2d return=%s storage=%s | %s" % (ri, has_return, has_storage, repr(row_text[:200])))
wb.close()
