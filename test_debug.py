import sys, os, re
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
sys.path.insert(0, r'C:\Users\1\Documents\Default Project')
import openpyxl

path = r'E:\新建文件夹\海外仓\正式价格\云帆济实力派一件代发大客户报价单- 20260113.xlsx'
wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
ws = wb['库内费用']
rows = list(ws.iter_rows(values_only=True))

# Trace section detection
section = None
for ri, row in enumerate(rows):
    texts = [str(c).strip() if c else "" for c in row]
    row_text = " ".join(t for t in texts if t).lower()
    
    old_section = section
    if any(k in row_text for k in ["卸货上架", "卸柜", "卸货费"]):
        section = "inbound"
    elif any(k in row_text for k in ["订单出库费", "出库费", "出库服务费"]):
        section = "outbound"
    elif any(k in row_text for k in ["自提", "self pickup", "平台订单附加费"]):
        section = "self_pickup"
    elif any(k in row_text for k in ["退货收货", "退货上架", "退货"]):
        section = "return"
    elif any(k in row_text for k in ["仓储费", "存储费", "仓租"]) and "仓储费" in row_text:
        section = "storage"
    elif any(k in row_text for k in ["增值服务", "value added"]):
        section = "value_added"
    
    changed = " <-- CHANGED" if section != old_section else ""
    if texts and any(t.strip() for t in texts):
        print("R%2d [%s] %s%s" % (ri, (section or "?")[:12], texts[1][:25] if len(texts)>1 else "", changed))

wb.close()
