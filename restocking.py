"""备货分析引擎：日均销量、物流周期、安全库存、补货建议、产品分级。"""
import math
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCT_FILE = os.path.join(BASE_DIR, "product_map.json")
RULES_FILE = os.path.join(BASE_DIR, "restocking_rules.json")

DEFAULT_RULES = {
    "classification": {
        "hot_turnover_max": 15, "hot_avg_daily_min": 2,
        "normal_turnover_max": 30, "normal_avg_daily_min": 0.5,
        "slow_turnover_min": 60, "warning_turnover_min": 45,
    },
    "priority": {
        "critical_sellable_days": 7, "critical_score": 50,
        "warning_sellable_days": 14, "warning_score": 30,
        "caution_sellable_days": 21, "caution_score": 15,
        "no_transit_caution_days": 21, "no_transit_score": 20,
        "high_volume_min": 5, "high_volume_score": 10,
        "med_volume_min": 2, "med_volume_score": 5,
        "fast_turnover_max": 15, "fast_turnover_score": 5,
    },
    "alerts": {
        "critical_sellable_days": 7, "low_sellable_days": 14,
        "slow_turnover_min": 90, "medium_slow_turnover_min": 60,
        "excess_transit_multiplier": 3,
        "slow_trend_turnover_min": 30, "rising_trend_sellable_days": 21,
    },
    "safety_stock": {"service_level_z": 1.65, "min_safety_days": 7},
}


def load_rules():
    try:
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        merged = json.loads(json.dumps(DEFAULT_RULES))
        for section, vals in saved.items():
            if section in merged and isinstance(vals, dict):
                merged[section].update(vals)
            else:
                merged[section] = vals
        return merged
    except Exception:
        return json.loads(json.dumps(DEFAULT_RULES))


def save_rules(rules):
    with open(RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)


def _load_products():
    try:
        with open(PRODUCT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _aggregate_daily_sales(out_data, lookback=90):
    """从出库数据聚合每日每SKU出库量。返回 {sku: {date: qty}}"""
    precomputed = out_data.get("_sku_daily")
    if precomputed:
        return precomputed
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    cutoff = (now - timedelta(days=lookback)).strftime("%Y-%m-%d")
    sku_daily = defaultdict(lambda: defaultdict(float))
    has_dates = False
    for wh_id, wh in (out_data.get("warehouses") or {}).items():
        if wh.get("status") != "ok":
            continue
        for pt in (wh.get("points") or []):
            for row in (pt.get("rows") or []):
                sku = row.get("sku", "")
                if not sku:
                    continue
                date_str = str(row.get("date", ""))[:10]
                if date_str and date_str >= cutoff:
                    has_dates = True
                    qty = _safe_float(row.get("qty", 0))
                    sku_daily[sku][date_str] += qty
    if not has_dates:
        totals = defaultdict(float)
        for wh_id, wh in (out_data.get("warehouses") or {}).items():
            if wh.get("status") != "ok":
                continue
            for pt in (wh.get("points") or []):
                for row in (pt.get("rows") or []):
                    sku = row.get("sku", "")
                    if not sku:
                        continue
                    totals[sku] += _safe_float(row.get("qty", 0))
        if totals:
            days = lookback
            for sku, total in totals.items():
                avg = total / days
                for i in range(1, days + 1):
                    d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
                    sku_daily[sku][d] = avg
    return dict(sku_daily)


def _aggregate_inventory(inv_data):
    """从库存数据聚合 SKU → {qty, warehouses}"""
    sku_map = defaultdict(lambda: {"qty": 0, "warehouses": set()})
    for wh_id, wh in (inv_data.get("warehouses") or {}).items():
        if wh.get("status") != "ok":
            continue
        for pt in (wh.get("points") or []):
            for row in (pt.get("rows") or []):
                sku = row.get("sku", "")
                if not sku:
                    continue
                qty = _safe_float(row.get("qty", 0))
                sku_map[sku]["qty"] += qty
                sku_map[sku]["warehouses"].add(wh_id)
    return dict(sku_map)


def _aggregate_transit_stock(transit_records):
    """从在途记录聚合每SKU的在途库存。只计入「在途」和「即将到港」的柜子。"""
    sku_transit = defaultdict(float)
    for rec in transit_records:
        status = rec.get("status") or ""
        if status not in ("在途", "即将到港"):
            continue
        for line in (rec.get("lines") or []):
            sku = line.get("sku", "")
            if not sku:
                continue
            qty = _safe_float(line.get("qty", 0))
            sku_transit[sku] += qty
    return dict(sku_transit)


def _compute_ads(sku_daily, sku, now, days):
    """计算近N天日均销量"""
    if days <= 0:
        return 0
    total = 0.0
    for i in range(1, days + 1):
        d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        total += sku_daily.get(sku, {}).get(d, 0)
    return round(total / days, 4)


def _compute_ads_ema(sku_daily, sku, now, days, alpha=0.7):
    """指数移动平均日均销量，近期权重更高"""
    vals = []
    for i in range(1, days + 1):
        d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        vals.append(sku_daily.get(sku, {}).get(d, 0))
    if not vals:
        return 0
    ema = vals[0]
    for v in vals[1:]:
        ema = alpha * v + (1 - alpha) * ema
    return round(ema, 4)


def _transit_cycle_days(transit_records):
    """计算物流平均周转天数（从在途数据）"""
    days_list = []
    for rec in transit_records:
        etd = rec.get("etd")
        eta = rec.get("eta_est")
        if not etd or not eta:
            continue
        try:
            d1 = datetime.strptime(str(etd)[:10], "%Y-%m-%d")
            d2 = datetime.strptime(str(eta)[:10], "%Y-%m-%d")
            d = (d2 - d1).days
            if 0 < d < 120:
                days_list.append(d)
        except (ValueError, TypeError):
            continue
    return round(sum(days_list) / len(days_list)) if days_list else 30


def _safety_stock_days(daily_avg, cycle_days=30, rules=None):
    """安全库存天数 = Z × √(物流周期)。"""
    if daily_avg <= 0:
        return (rules or {}).get("safety_stock", {}).get("min_safety_days", 7)
    r = (rules or {}).get("safety_stock", {})
    z = r.get("service_level_z", 1.65)
    mn = r.get("min_safety_days", 7)
    return max(mn, round(z * math.sqrt(cycle_days)))


def _classify_product(turnover_days, avg_daily, total_qty, rules=None):
    """产品分级"""
    c = (rules or {}).get("classification", DEFAULT_RULES["classification"])
    if total_qty <= 0:
        return "out_of_stock", "缺货"
    if turnover_days <= c["hot_turnover_max"] and avg_daily >= c["hot_avg_daily_min"]:
        return "hot", "爆款"
    if turnover_days <= c["normal_turnover_max"] and avg_daily >= c["normal_avg_daily_min"]:
        return "normal", "普通款"
    if turnover_days > c["slow_turnover_min"]:
        return "slow", "滞销款"
    if turnover_days > c["warning_turnover_min"]:
        return "warning", "预警款"
    if turnover_days > c["normal_turnover_max"]:
        return "warning", "预警款"
    return "normal", "普通款"


def _restock_priority(turnover_days, sellable_days, in_transit, avg_daily, rules=None):
    """补货优先级打分：越高越急"""
    p = (rules or {}).get("priority", DEFAULT_RULES["priority"])
    score = 0
    if sellable_days <= p["critical_sellable_days"]:
        score += p["critical_score"]
    elif sellable_days <= p["warning_sellable_days"]:
        score += p["warning_score"]
    elif sellable_days <= p["caution_sellable_days"]:
        score += p["caution_score"]
    if in_transit <= 0 and sellable_days <= p["no_transit_caution_days"]:
        score += p["no_transit_score"]
    if avg_daily >= p["high_volume_min"]:
        score += p["high_volume_score"]
    elif avg_daily >= p["med_volume_min"]:
        score += p["med_volume_score"]
    if turnover_days <= p["fast_turnover_max"]:
        score += p["fast_turnover_score"]
    return score


def compute_restock建议(inv_data, out_data, transit_records, rules=None):
    """主分析入口：返回完整备货建议。"""
    if rules is None:
        rules = load_rules()
    products = _load_products()
    inv_map = _aggregate_inventory(inv_data)
    out_daily = _aggregate_daily_sales(out_data, lookback=90)
    transit_stock = _aggregate_transit_stock(transit_records)
    cycle_days = _transit_cycle_days(transit_records)
    now = datetime.now()
    a = rules.get("alerts", DEFAULT_RULES["alerts"])

    # 聚合所有出现过的SKU
    all_skus = set(inv_map.keys()) | set(out_daily.keys())

    results = []
    for sku in all_skus:
        inv_info = inv_map.get(sku, {"qty": 0, "warehouses": set()})
        current_qty = inv_info["qty"]
        in_transit = transit_stock.get(sku, 0)

        # ADS计算：加权取30天
        ads_7 = _compute_ads(out_daily, sku, now, 7)
        ads_15 = _compute_ads(out_daily, sku, now, 15)
        ads_30 = _compute_ads(out_daily, sku, now, 30)
        ads_ema = _compute_ads_ema(out_daily, sku, now, 30)

        # 基准日均：取30天EMA
        avg_daily = ads_ema if ads_ema > 0 else ads_30

        # 可售天数
        sellable_days = round(current_qty / avg_daily) if avg_daily > 0 else 999

        # 库存周转天数
        turnover = round(current_qty / avg_daily, 1) if avg_daily > 0 else 999

        # 安全天数
        safety_days = _safety_stock_days(avg_daily, cycle_days, rules)

        # 补货量 = 日均 × (物流周期 + 安全天数) - 当前库存 - 在途
        need = avg_daily * (cycle_days + safety_days)
        restock_qty = need - current_qty - in_transit
        restock_qty = max(0, round(restock_qty))

        # 产品分级
        tier_key, tier_label = _classify_product(turnover, avg_daily, current_qty, rules)

        # 补货优先级
        priority = _restock_priority(turnover, sellable_days, in_transit, avg_daily, rules)

        # 产品名
        prod_info = products.get(sku, {})
        name = prod_info.get("name", "")

        # 出库趋势：近7天 vs 前7天
        recent_7 = sum(out_daily.get(sku, {}).get((now - timedelta(days=i)).strftime("%Y-%m-%d"), 0) for i in range(1, 8))
        prev_7 = sum(out_daily.get(sku, {}).get((now - timedelta(days=i)).strftime("%Y-%m-%d"), 0) for i in range(8, 15))
        trend = "up" if recent_7 > prev_7 * 1.1 else ("down" if recent_7 < prev_7 * 0.9 else "flat")
        trend_pct = round((recent_7 - prev_7) / prev_7 * 100, 1) if prev_7 > 0 else 0

        # 风险提示（用规则阈值）
        alerts = []
        if current_qty <= 0 and in_transit <= 0:
            alerts.append("严重缺货，无在途")
        elif current_qty <= 0:
            alerts.append("已缺货，有在途")
        elif sellable_days <= a["critical_sellable_days"]:
            alerts.append("即将断货")
        elif sellable_days <= a["low_sellable_days"]:
            alerts.append("库存偏低")
        if turnover > a["slow_turnover_min"]:
            alerts.append("周转极慢，谨慎补货")
        elif turnover > a["medium_slow_turnover_min"]:
            alerts.append("周转偏慢")
        if current_qty > 0 and in_transit > current_qty * a["excess_transit_multiplier"]:
            alerts.append("在途过多")
        if trend == "down" and turnover > a["slow_trend_turnover_min"]:
            alerts.append("销量下滑")
        if trend == "up" and sellable_days < a["rising_trend_sellable_days"]:
            alerts.append("销量上升，注意备货")

        results.append({
            "sku": sku,
            "name": name,
            "current_qty": round(current_qty),
            "in_transit": round(in_transit),
            "ads_7": ads_7,
            "ads_15": ads_15,
            "ads_30": ads_30,
            "avg_daily": avg_daily,
            "sellable_days": sellable_days,
            "turnover_days": turnover,
            "safety_days": safety_days,
            "cycle_days": cycle_days,
            "restock_qty": restock_qty,
            "tier": tier_key,
            "tier_label": tier_label,
            "priority": priority,
            "trend": trend,
            "trend_pct": trend_pct,
            "alerts": alerts,
            "warehouses": len(inv_info.get("warehouses", set())),
        })

    # 排序：优先级高的在前
    results.sort(key=lambda x: (-x["priority"], x["sellable_days"]))

    # 汇总统计
    total_skus = len(results)
    hot = len([r for r in results if r["tier"] == "hot"])
    normal = len([r for r in results if r["tier"] == "normal"])
    slow = len([r for r in results if r["tier"] == "slow"])
    warning = len([r for r in results if r["tier"] == "warning"])
    out_of_stock = len([r for r in results if r["tier"] == "out_of_stock"])
    need_restock = len([r for r in results if r["restock_qty"] > 0])
    urgent = len([r for r in results if r["priority"] >= 30])
    total_restock_qty = sum(r["restock_qty"] for r in results)

    return {
        "cycle_days": cycle_days,
        "rules": rules,
        "summary": {
            "total": total_skus,
            "hot": hot,
            "normal": normal,
            "slow": slow,
            "warning": warning,
            "out_of_stock": out_of_stock,
            "need_restock": need_restock,
            "urgent": urgent,
            "total_restock_qty": total_restock_qty,
        },
        "items": results,
    }
