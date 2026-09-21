#!/usr/bin/env python3
"""
海外仓账单解析脚本
支持 Excel (.xlsx/.xls) 和 PDF (.pdf) 格式
输出标准化的 JSON 结构供对账引擎使用

Usage:
    python3 parse_bill.py <input_file> [--output <output.json>] [--sheet <sheet_name>]
"""

import json
import sys
import os
import argparse
from datetime import datetime


def parse_excel(file_path, sheet_name=None):
    """解析 Excel 账单文件"""
    try:
        from openpyxl import load_workbook
    except ImportError:
        print("ERROR: openpyxl not installed. Run: pip install openpyxl", file=sys.stderr)
        sys.exit(1)

    wb = load_workbook(file_path, data_only=True, read_only=True)

    # 如果未指定 sheet，使用第一个或让用户选择
    if sheet_name:
        if sheet_name not in wb.sheetnames:
            print(f"ERROR: Sheet '{sheet_name}' not found. Available: {wb.sheetnames}", file=sys.stderr)
            sys.exit(1)
        ws = wb[sheet_name]
    else:
        # 尝找包含费用数据的 sheet
        ws = wb[wb.sheetnames[0]]
        # 如果第一个 sheet 看起来不像数据，尝试其他
        for name in wb.sheetnames:
            if any(kw in name.lower() for kw in ['invoice', 'bill', '账单', '费用', 'detail', '明细']):
                ws = wb[name]
                break

    rows = list(ws.iter_rows(values_only=True))

    if not rows:
        return {"items": [], "meta": {"source_file": file_path, "format": "excel", "sheet": ws.title}}

    # 尝试识别表头行（包含费用相关关键词的行）
    header_idx = 0
    fee_keywords = [
        'fee', 'charge', 'cost', 'amount', 'qty', 'quantity', 'unit', 'price',
        'date', 'description', 'item', 'service', 'total', 'subtotal',
        '费用', '金额', '数量', '单价', '日期', '描述', '项目', '服务', '合计'
    ]

    for i, row in enumerate(rows[:20]):  # 只看前20行
        row_text = ' '.join(str(c).lower() for c in row if c)
        if sum(1 for kw in fee_keywords if kw in row_text) >= 3:
            header_idx = i
            break

    headers = [str(c).strip().lower() if c else '' for c in rows[header_idx]]

    # 标准化列名映射
    col_map = {}
    for idx, h in enumerate(headers):
        if not h:
            continue
        # 费用名称/描述
        if any(k in h for k in ['description', 'item', 'service', 'fee type', 'charge type', '费用名称', '项目', '服务', '描述']):
            col_map['fee_name'] = idx
        # 日期
        elif any(k in h for k in ['date', '日期']):
            col_map['date'] = idx
        # 数量
        elif any(k in h for k in ['qty', 'quantity', 'count', '数量', '件数']):
            col_map['quantity'] = idx
        # 单价
        elif any(k in h for k in ['unit price', 'price', 'rate', '单价']):
            col_map['unit_price'] = idx
        # 金额/总价
        elif any(k in h for k in ['amount', 'total', 'subtotal', '金额', '合计', '总价']):
            col_map['amount'] = idx
        # 单位
        elif any(k in h for k in ['unit', '单位']):
            col_map['unit'] = idx
        # 备注
        elif any(k in h for k in ['remark', 'note', 'comment', '备注']):
            col_map['remark'] = idx

    # 提取数据行
    items = []
    for row in rows[header_idx + 1:]:
        # 跳过空行
        if all(c is None or str(c).strip() == '' for c in row):
            continue
        # 跳过汇总行
        row_text = ' '.join(str(c).lower() for c in row if c)
        if any(k in row_text for k in ['total', 'subtotal', 'grand total', 'sum', '合计', '总计', '小计']):
            continue

        item = {}
        for field, idx in col_map.items():
            val = row[idx] if idx < len(row) else None
            if val is not None:
                val = val.strip() if isinstance(val, str) else val
                # 尝试转换为数值
                if field in ('quantity', 'unit_price', 'amount') and isinstance(val, str):
                    try:
                        val = float(val.replace(',', '').replace('$', '').replace('¥', '').strip())
                    except ValueError:
                        pass
            item[field] = val

        # 确保至少有费用名称或金额
        if item.get('fee_name') or item.get('amount'):
            items.append(item)

    return {
        "items": items,
        "meta": {
            "source_file": os.path.basename(file_path),
            "format": "excel",
            "sheet": ws.title,
            "total_rows": len(items),
            "headers": headers,
            "header_row": header_idx + 1,
            "column_mapping": col_map,
        }
    }


def parse_pdf(file_path):
    """解析 PDF 账单文件"""
    try:
        import pdfplumber
    except ImportError:
        print("ERROR: pdfplumber not installed. Run: pip install pdfplumber", file=sys.stderr)
        sys.exit(1)

    all_items = []
    tables_found = 0

    with pdfplumber.open(file_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            tables = page.extract_tables()
            for table_idx, table in enumerate(tables):
                if not table or len(table) < 2:
                    continue

                tables_found += 1
                headers = [str(c).strip().lower() if c else '' for c in table[0]]

                # 标准化列名
                col_map = {}
                for idx, h in enumerate(headers):
                    if not h:
                        continue
                    if any(k in h for k in ['description', 'item', 'service', 'fee', '费用', '项目', '描述']):
                        col_map['fee_name'] = idx
                    elif any(k in h for k in ['date', '日期']):
                        col_map['date'] = idx
                    elif any(k in h for k in ['qty', 'quantity', '数量']):
                        col_map['quantity'] = idx
                    elif any(k in h for k in ['price', 'rate', '单价']):
                        col_map['unit_price'] = idx
                    elif any(k in h for k in ['amount', 'total', '金额', '合计']):
                        col_map['amount'] = idx
                    elif any(k in h for k in ['unit', '单位']):
                        col_map['unit'] = idx

                for row in table[1:]:
                    if all(c is None or str(c).strip() == '' for c in row):
                        continue
                    row_text = ' '.join(str(c).lower() for c in row if c)
                    if any(k in row_text for k in ['total', 'subtotal', 'grand total', '合计', '总计']):
                        continue

                    item = {}
                    for field, idx in col_map.items():
                        val = row[idx] if idx < len(row) else None
                        if val is not None:
                            val = val.strip() if isinstance(val, str) else val
                            if field in ('quantity', 'unit_price', 'amount') and isinstance(val, str):
                                try:
                                    val = float(val.replace(',', '').replace('$', '').replace('¥', '').strip())
                                except ValueError:
                                    pass
                        item[field] = val

                    if item.get('fee_name') or item.get('amount'):
                        item['_page'] = page_num
                        all_items.append(item)

    return {
        "items": all_items,
        "meta": {
            "source_file": os.path.basename(file_path),
            "format": "pdf",
            "tables_found": tables_found,
            "total_rows": len(all_items),
            "column_mapping": col_map if tables_found > 0 else {},
        }
    }


def parse_quote(file_path):
    """解析报价表 Excel 文件"""
    try:
        from openpyxl import load_workbook
    except ImportError:
        print("ERROR: openpyxl not installed", file=sys.stderr)
        sys.exit(1)

    wb = load_workbook(file_path, data_only=True, read_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))

    if not rows:
        return {"quote_items": []}

    headers = [str(c).strip().lower() if c else '' for c in rows[0]]

    items = []
    for row in rows[1:]:
        if all(c is None or str(c).strip() == '' for c in row):
            continue
        item = {}
        for idx, h in enumerate(headers):
            if h and idx < len(row):
                val = row[idx]
                if isinstance(val, str):
                    val = val.strip()
                item[h] = val
        items.append(item)

    return {"quote_items": items, "headers": headers}


def main():
    parser = argparse.ArgumentParser(description='海外仓账单解析工具')
    parser.add_argument('input_file', help='账单文件路径 (Excel/PDF)')
    parser.add_argument('--output', '-o', help='输出 JSON 文件路径', default=None)
    parser.add_argument('--sheet', '-s', help='Excel sheet 名称', default=None)
    parser.add_argument('--quote', '-q', help='报价表文件路径 (Excel)', default=None)
    args = parser.parse_args()

    file_ext = os.path.splitext(args.input_file)[1].lower()

    if file_ext in ('.xlsx', '.xls'):
        result = parse_excel(args.input_path if hasattr(args, 'input_path') else args.input_file, args.sheet)
    elif file_ext == '.pdf':
        result = parse_pdf(args.input_file)
    else:
        print(f"ERROR: Unsupported format: {file_ext}. Supported: .xlsx, .xls, .pdf", file=sys.stderr)
        sys.exit(1)

    # 解析报价表
    if args.quote:
        quote_result = parse_quote(args.quote)
        result['quote'] = quote_result

    output = json.dumps(result, ensure_ascii=False, indent=2, default=str)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"Output saved to {args.output}")
        print(f"Parsed {len(result['items'])} bill items")
    else:
        print(output)


if __name__ == '__main__':
    main()
