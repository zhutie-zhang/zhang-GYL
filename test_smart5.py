import sys, os, re, glob
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
sys.path.insert(0, r'C:\Users\1\Documents\Default Project')
import openpyxl

files = glob.glob(r'E:\新建文件夹\海外仓\正式价格\*.xlsx')
smart = [f for f in files if 'SMART' in os.path.basename(f) and not os.path.basename(f).startswith('~$')]
leecang_new = [f for f in files if '新乐舱' in os.path.basename(f) and not os.path.basename(f).startswith('~$')]

for f in smart:
    wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
    # 件出库处理费 - check ALL columns
    if '件出库处理费' in wb.sheetnames:
        ws = wb['件出库处理费']
        rows = list(ws.iter_rows(values_only=True))
        print('--- SMART 件出库处理费 (%d rows) ---' % len(rows))
        for ri, row in enumerate(rows[:25]):
            cells = [str(c)[:18] if c else '' for c in row]
            print('  R%d: %s' % (ri, ' | '.join(cells[:12])))
    
    # GOFO Ground - wider column range
    if 'GOFO Ground' in wb.sheetnames:
        ws = wb['GOFO Ground']
        rows = list(ws.iter_rows(values_only=True))
        print('\n--- GOFO Ground full row (R0-R8) ---')
        for ri, row in enumerate(rows[:8]):
            cells = [str(c)[:18] if c else '' for c in row]
            print('  R%d: %s' % (ri, ' | '.join(cells)))
    
    # FedEx_AHS - wider column range
    if 'Fedex_AHS' in wb.sheetnames:
        ws = wb['Fedex_AHS']
        rows = list(ws.iter_rows(values_only=True))
        print('\n--- FedEx_AHS full row (R13-R22) ---')
        for ri, row in enumerate(rows[13:23]):
            cells = [str(c)[:18] if c else '' for c in row]
            print('  R%d: %s' % (ri+13, ' | '.join(cells)))
    wb.close()

for f in leecang_new:
    wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
    if 'FEDEX- Ground & Home Delivery' in wb.sheetnames:
        ws = wb['FEDEX- Ground & Home Delivery']
        rows = list(ws.iter_rows(values_only=True))
        print('\n--- LEECANG SVIP FEDEX full row (R2-R12) ---')
        for ri, row in enumerate(rows[2:13]):
            cells = [str(c)[:18] if c else '' for c in row]
            print('  R%d: %s' % (ri+2, ' | '.join(cells)))
    wb.close()
