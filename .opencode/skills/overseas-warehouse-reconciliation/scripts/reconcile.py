#!/usr/bin/env python3
"""
海外仓账单对账引擎
比对账单与报价表，识别重复计费、单价错误、仓租天数错误、不合理杂费

Usage:
    python3 reconcile.py <bill.json> <quote.json> [--output <report.json>]
    python3 reconcile.py --bill-file <bill.json> --quote-file <quote.json> -o report.json

输入格式:
    bill.json: parse_bill.py 的输出
    quote.json: {"quote_items": [...]} 格式
"""

import json
import sys
import os
import argparse
import re
import unicodedata
from datetime import datetime, timedelta


def normalize_key(s):
    """归一化字符串键：去 BOM / 不可见字符 / 多种连字符变体 / 全角空格 / 大小写。

    处理账单/报价表导入时常见的字符差异，例如：
        '仓租‑立方' (含 U+2011 非断字符) 与 '仓租-立方' 等应视为同一键
        'WH‑ORD‑701' 与 'WH-ORD-701' 等订单号应视为同一键
        '   拆柜费  ' 与 '拆柜费' 应视为同一键
        全角'，' '。' ' ' 等标点不会导致键不一致
    """
    if s is None:
        return ''
    s = str(s)
    # 去除 BOM / 零宽字符
    s = s.replace('\ufeff', '').replace('\u200b', '').replace('\u200c', '').replace('\u200d', '')
    # 全部连字符变体归一到 ASCII '-'
    for ch in ('\u2010', '\u2011', '\u2012', '\u2013', '\u2014', '\u2015', '\u2212'):
        s = s.replace(ch, '-')
    # 全角空格 -> 普通空格，再 strip + 折叠多空格
    s = s.replace('\u3000', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    # Unicode NFKC 归一化（处理全角字母数字）
    s = unicodedata.normalize('NFKC', s)
    return s.casefold()


# ========== 费用类型映射 ==========
FEE_TYPE_MAP = {
    # 拆柜费
    'devanning': '拆柜费', 'unloading': '拆柜费', 'deconsolidation': '拆柜费', 'strip': '拆柜费',
    '拆柜': '拆柜费', '拆箱': '拆柜费', '卸柜': '拆柜费',
    # 打托费
    'palletizing': '打托费', 'pallet': '打托费', 'pallet build': '打托费', 'pallet load': '打托费',
    '打托': '打托费', '上托': '打托费', '托盘': '打托费', '组托': '打托费',
    # 贴标费
    'labeling': '贴标费', 'labelling': '贴标费', 'sticker': '贴标费', 'relabel': '贴标费', 'fba label': '贴标费',
    '贴标': '贴标费', '贴条码': '贴标费', '换标': '贴标费',
    # 仓租
    'storage': '仓租', 'warehouse': '仓租', 'warehousing': '仓租', 'storage rent': '仓租',
    '仓租': '仓租', '仓储': '仓租', '库存': '仓租',
    # 处理费
    'handling': '处理费', 'processing': '处理费', 'inbound handling': '处理费', 'outbound handling': '处理费',
    '处理': '处理费', '操作': '处理费', '收货': '处理费',
    # 退货费
    'return': '退货费', 'rma': '退货费', 'return handling': '退货费', 'return processing': '退货费',
    '退货': '退货费', '退件': '退货费',
    # 分拣
    'sorting': '分拣费', 'pick': '分拣费', 'pick and pack': '分拣费',
    '分拣': '分拣费', '拣货': '分拣费',
    # 装车
    'loading': '装车费', 'outbound loading': '装车费',
    '装车': '装车费', '出库装车': '装车费',
    # 上架
    'putaway': '上架费', 'put away': '上架费', 'shelving': '上架费',
    '上架': '上架费',
    # 快递费
    'shipping': '快递费', 'last mile': '快递费', 'outbound shipping': '快递费', 'delivery': '快递费',
    '快递': '快递费', '配送': '快递费', '尾程': '快递费',
}


def classify_fee(fee_name):
    """将费用名称分类为标准费用类型"""
    if not fee_name:
        return None
    name_lower = normalize_key(fee_name)
    for keyword, fee_type in FEE_TYPE_MAP.items():
        if normalize_key(keyword) in name_lower:
            return fee_type
    return None


def load_quote_items(quote_data):
    """加载并标准化报价表数据"""
    quote_map = {}
    raw_items = quote_data.get('quote_items', [])

    for item in raw_items:
        # 尝试多种字段名
        fee_name = (
            item.get('fee_name') or item.get('name') or item.get('fee type') or
            item.get('费用名称') or item.get('项目') or item.get('description') or
            item.get('service') or ''
        )
        fee_type = classify_fee(fee_name)

        unit_price = (
            item.get('unit_price') or item.get('price') or item.get('rate') or
            item.get('单价') or item.get('unit price')
        )
        unit = item.get('unit') or item.get('单位') or item.get('计费单位', '')
        free_days = item.get('free_days') or item.get('免租天数') or 0
        min_charge = item.get('min_charge') or item.get('最低收费') or 0
        remark = item.get('remark') or item.get('备注') or ''
        currency = item.get('currency') or item.get('币种') or 'USD'

        try:
            unit_price = float(unit_price) if unit_price else 0
            free_days = int(float(free_days)) if free_days else 0
            min_charge = float(min_charge) if min_charge else 0
        except (ValueError, TypeError):
            pass

        key = fee_type or fee_name
        key = normalize_key(key)
        quote_entry = {
            'fee_type': fee_type,
            'fee_name': fee_name,
            'unit_price': unit_price,
            'unit': unit,
            'free_days': free_days,
            'min_charge': min_charge,
            'remark': remark,
            'currency': currency,
        }
        quote_map[key] = quote_entry
        # 同时把分类后类型与原始费用名作为同一 quote 的别名键，
        # 保证 check_unquoted_fees 用 fee_type 命中报价表
        if fee_type:
            quote_map.setdefault(normalize_key(fee_type), quote_entry)
        if fee_name and fee_name != key:
            quote_map.setdefault(normalize_key(fee_name), quote_entry)

    return quote_map


# ========== 对账规则检测 ==========

def check_duplicate_charges(bill_items):
    """R01: 检测完全重复计费"""
    issues = []
    seen = {}

    for i, item in enumerate(bill_items):
        fee_name = str(item.get('fee_name', ''))
        date = str(item.get('date', ''))
        ref = str(item.get('reference', '') or item.get('order_no', '') or item.get('po', ''))
        qty = item.get('quantity', '')
        price = item.get('unit_price', '')

        # 全部字段归一化后再比较，避免连字符 / 全角空格导致漏判
        key = f"{normalize_key(fee_name)}|{normalize_key(date)}|{normalize_key(ref)}|{normalize_key(str(qty))}|{normalize_key(str(price))}"
        if key in seen:
            seen_idx = seen[key]
            amount = item.get('amount', 0) or 0
            issues.append({
                'rule': 'R01',
                'rule_name': '重复计费-完全重复',
                'severity': 'high',
                'bill_row': i + 1,
                'duplicate_of_row': seen_idx + 1,
                'fee_name': fee_name,
                'date': date,
                'reference': ref,
                'amount': amount,
                'description': f'第{i+1}行与第{seen_idx+1}行（订单 {ref or "?"}）完全相同，疑似重复计费',
            })
        else:
            seen[key] = i

    return issues


def check_unit_price(bill_items, quote_map):
    """R06: 检测单价高于报价"""
    issues = []

    for i, item in enumerate(bill_items):
        fee_name = str(item.get('fee_name', ''))
        fee_type = classify_fee(fee_name)
        billed_price = item.get('unit_price')

        if billed_price is None or fee_type is None:
            continue

        # 双重查找：按 fee_type 归一化键、原始 fee_name 归一化键
        norm_type = normalize_key(fee_type)
        norm_name = normalize_key(fee_name)
        quote = quote_map.get(norm_type) or quote_map.get(norm_name)
        if not quote:
            continue

        agreed_price = quote.get('unit_price', 0)
        if agreed_price and float(billed_price) > float(agreed_price):
            diff = float(billed_price) - float(agreed_price)
            qty = item.get('quantity', 1) or 1
            total_diff = diff * float(qty) if qty else diff
            issues.append({
                'rule': 'R06',
                'rule_name': '单价高于报价',
                'severity': 'high',
                'bill_row': i + 1,
                'fee_name': fee_name,
                'fee_type': fee_type,
                'billed_price': float(billed_price),
                'agreed_price': float(agreed_price),
                'price_diff': round(diff, 4),
                'quantity': qty,
                'amount_diff': round(total_diff, 2),
                'description': f'{fee_name} 账单单价 {billed_price} 高于报价单价 {agreed_price}，差异 {round(diff, 4)}/unit',
            })

    return issues


def check_storage_days(bill_items, quote_map):
    """R03/R04: 检测仓租天数错误和免租期未扣除"""
    issues = []

    for i, item in enumerate(bill_items):
        fee_name = str(item.get('fee_name', ''))
        fee_type = classify_fee(fee_name)

        if fee_type != '仓租':
            continue

        remark = str(item.get('remark', '') or '')
        # 尝试从 remark 中提取入库/出库日期
        # 格式可能是: "2025-01-05 to 2025-01-20" 或 "In: 2025-01-05 Out: 2025-01-20"
        import re

        dates = re.findall(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', remark)
        if len(dates) >= 2:
            try:
                fmt = '%Y-%m-%d' if '-' in dates[0] else '%Y/%m/%d'
                inbound = datetime.strptime(dates[0], fmt)
                outbound = datetime.strptime(dates[1], fmt)
                actual_days = (outbound - inbound).days
            except ValueError:
                continue

            # 检查账单天数
            billed_qty = item.get('quantity', 0) or 0
            try:
                billed_days = int(float(billed_qty))
            except (ValueError, TypeError):
                billed_days = 0

            if billed_days and actual_days and billed_days > actual_days:
                diff = billed_days - actual_days
                unit_price = item.get('unit_price', 0) or 0
                volume = 1  # 默认
                amount_diff = diff * float(unit_price) * float(volume)
                issues.append({
                    'rule': 'R03',
                    'rule_name': '仓租天数计算错误',
                    'severity': 'high',
                    'bill_row': i + 1,
                    'fee_name': fee_name,
                    'inbound_date': dates[0],
                    'outbound_date': dates[1],
                    'actual_days': actual_days,
                    'billed_days': billed_days,
                    'excess_days': diff,
                    'amount_diff': round(amount_diff, 2),
                    'description': f'仓租周期 {dates[0]}→{dates[1]} 实际{actual_days}天，账单{billed_days}天，多算{diff}天',
                })

            # 检查免租期
            quote = quote_map.get(normalize_key('仓租'))
            if quote:
                free_days = quote.get('free_days', 0)
                if free_days and actual_days <= free_days and billed_days > 0:
                    amount = item.get('amount', 0) or 0
                    issues.append({
                        'rule': 'R04',
                        'rule_name': '免租期未扣除',
                        'severity': 'high',
                        'bill_row': i + 1,
                        'fee_name': fee_name,
                        'free_days': free_days,
                        'actual_days': actual_days,
                        'billed_amount': float(amount),
                        'description': f'约定免租{free_days}天，实际存放{actual_days}天（在免租期内），不应收费',
                    })

            # 检查周末计费
            quote_remark = str(quote.get('remark', '')) if quote else ''
            if any(k in quote_remark.lower() for k in ['weekend free', '周末不计费', '周末免']):
                # 计算周末天数
                weekend_days = 0
                current = inbound
                while current <= outbound:
                    if current.weekday() >= 5:  # 5=Saturday, 6=Sunday
                        weekend_days += 1
                    current += timedelta(days=1)
                if weekend_days > 0 and billed_days >= actual_days:
                    unit_price = float(item.get('unit_price', 0) or 0)
                    volume = 1
                    weekend_amount = weekend_days * unit_price * volume
                    issues.append({
                        'rule': 'R05',
                        'rule_name': '周末计费（约定不计费）',
                        'severity': 'medium',
                        'bill_row': i + 1,
                        'fee_name': fee_name,
                        'weekend_days': weekend_days,
                        'amount_diff': round(weekend_amount, 2),
                        'description': f'报价约定周末不计费，但账单含{weekend_days}天周末仓租',
                    })

    return issues


def check_unquoted_fees(bill_items, quote_map):
    """R11: 检测未在报价表中的费用"""
    issues = []
    quote_types = set()

    # 收集报价表中所有费用类型和名称（已归一化）
    for key, quote in quote_map.items():
        if quote.get('fee_type'):
            quote_types.add(normalize_key(quote['fee_type']))
        quote_types.add(key)

    for i, item in enumerate(bill_items):
        fee_name = str(item.get('fee_name', ''))
        if not fee_name.strip():
            continue

        fee_type = classify_fee(fee_name)
        fee_name_norm = normalize_key(fee_name)

        # 检查是否能匹配到任何报价项
        matched = False
        if fee_type and normalize_key(fee_type) in quote_types:
            matched = True
        if fee_name_norm in quote_types:
            matched = True
        # 模糊匹配
        for qt in quote_types:
            if qt and (qt in fee_name_norm or fee_name_norm in qt):
                matched = True
                break

        if not matched:
            amount = item.get('amount', 0) or 0
            issues.append({
                'rule': 'R11',
                'rule_name': '未报价费用',
                'severity': 'medium',
                'bill_row': i + 1,
                'fee_name': fee_name,
                'fee_type': fee_type or '未识别',
                'amount': float(amount) if amount else 0,
                'description': f'费用 "{fee_name}" 不在报价表中',
            })

    return issues


def check_misc_fee_ratio(bill_items):
    """R12: 检测杂费占比过高"""
    issues = []

    standard_types = {'拆柜费', '打托费', '贴标费', '仓租', '处理费', '退货费', '快递费'}
    total_amount = 0
    misc_amount = 0
    misc_items = []

    for item in bill_items:
        amount = item.get('amount', 0) or 0
        try:
            amount = float(amount)
        except (ValueError, TypeError):
            amount = 0
        total_amount += amount

        fee_type = classify_fee(item.get('fee_name', ''))
        if fee_type not in standard_types:
            misc_amount += amount
            if amount > 0:
                misc_items.append({
                    'fee_name': item.get('fee_name', ''),
                    'amount': amount,
                    'row': item,
                })

    if total_amount > 0 and misc_amount / total_amount > 0.10:
        ratio = misc_amount / total_amount
        issues.append({
            'rule': 'R12',
            'rule_name': '杂费占比过高',
            'severity': 'medium',
            'total_amount': round(total_amount, 2),
            'misc_amount': round(misc_amount, 2),
            'misc_ratio': round(ratio * 100, 1),
            'misc_items': [{'fee_name': m['fee_name'], 'amount': m['amount']} for m in misc_items],
            'description': f'杂费占总费用 {ratio*100:.1f}%（${misc_amount:.2f}/${total_amount:.2f}），超过10%阈值',
        })

    return issues


def generate_summary(bill_items, all_issues):
    """生成费用统计摘要"""
    summary = {}
    total = 0
    type_totals = {}

    for item in bill_items:
        amount = item.get('amount', 0) or 0
        try:
            amount = float(amount)
        except (ValueError, TypeError):
            amount = 0
        total += amount

        fee_type = classify_fee(item.get('fee_name', '')) or '其他'
        type_totals[fee_type] = type_totals.get(fee_type, 0) + amount

    disputed = sum(i.get('amount_diff', 0) or i.get('amount', 0) or 0 for i in all_issues if i.get('severity') == 'high')
    disputed_medium = sum(i.get('amount_diff', 0) or i.get('amount', 0) or 0 for i in all_issues if i.get('severity') == 'medium')

    summary = {
        'total_bill_amount': round(total, 2),
        'total_items': len(bill_items),
        'fee_type_breakdown': {k: round(v, 2) for k, v in sorted(type_totals.items(), key=lambda x: -x[1])},
        'total_issues': len(all_issues),
        'high_severity_issues': sum(1 for i in all_issues if i.get('severity') == 'high'),
        'medium_severity_issues': sum(1 for i in all_issues if i.get('severity') == 'medium'),
        'low_severity_issues': sum(1 for i in all_issues if i.get('severity') == 'low'),
        'estimated_overcharge': round(disputed + disputed_medium, 2),
    }
    return summary


def reconcile(bill_data, quote_data):
    """主对账函数"""
    bill_items = bill_data.get('items', [])
    quote_map = load_quote_items(quote_data)

    all_issues = []

    # 执行所有检测规则
    all_issues.extend(check_duplicate_charges(bill_items))
    all_issues.extend(check_unit_price(bill_items, quote_map))
    all_issues.extend(check_storage_days(bill_items, quote_map))
    all_issues.extend(check_unquoted_fees(bill_items, quote_map))
    all_issues.extend(check_misc_fee_ratio(bill_items))

    summary = generate_summary(bill_items, all_issues)

    return {
        'reconciliation_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'bill_meta': bill_data.get('meta', {}),
        'summary': summary,
        'issues': all_issues,
        'quote_matched': len(quote_map) > 0,
    }


def main():
    parser = argparse.ArgumentParser(description='海外仓账单对账引擎')
    parser.add_argument('bill_file', help='账单 JSON 文件 (parse_bill.py 输出)')
    parser.add_argument('quote_file', help='报价表 JSON 文件')
    parser.add_argument('--output', '-o', help='输出报告 JSON 路径', default=None)
    args = parser.parse_args()

    with open(args.bill_file, 'r', encoding='utf-8') as f:
        bill_data = json.load(f)
    with open(args.quote_file, 'r', encoding='utf-8') as f:
        quote_data = json.load(f)

    result = reconcile(bill_data, quote_data)

    output = json.dumps(result, ensure_ascii=False, indent=2, default=str)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"Report saved to {args.output}")
    else:
        print(output)


if __name__ == '__main__':
    main()
