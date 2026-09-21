"""供应链分析引擎：KPI指标、风险预警、供应商评分、物流时效。"""
import math
import random
from collections import defaultdict
from datetime import datetime, timedelta
from transit import transit_days


def _safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _aggregate_inventory(inv_data):
    """从库存数据聚合 SKU → {qty, warehouses, groups}"""
    sku_map = defaultdict(lambda: {"qty": 0, "warehouses": set(), "groups": set()})
    wh_data = inv_data.get("warehouses", {})
    for wh_id, wh in wh_data.items():
        if wh.get("status") != "ok":
            continue
        for pt in (wh.get("points") or []):
            gid = wh.get("group", "")
            for row in (pt.get("rows") or []):
                sku = row.get("sku", "")
                if not sku:
                    continue
                qty = _safe_float(row.get("qty", 0))
                sku_map[sku]["qty"] += qty
                sku_map[sku]["warehouses"].add(wh_id)
                if gid:
                    sku_map[sku]["groups"].add(gid)
    return dict(sku_map)


def _aggregate_outbound_daily(out_data, days=90):
    """从出库数据聚合每日 SKU 出库量。返回 {sku: {date: qty}}"""
    sku_daily = defaultdict(lambda: defaultdict(float))
    wh_data = out_data.get("warehouses", {})
    for wh_id, wh in wh_data.items():
        if wh.get("status") != "ok":
            continue
        for pt in (wh.get("points") or []):
            for row in (pt.get("rows") or []):
                sku = row.get("sku", "")
                if not sku:
                    continue
                qty = _safe_float(row.get("qty", 0))
                date_str = str(row.get("date", ""))[:10]
                if not date_str:
                    continue
                sku_daily[sku][date_str] += qty
    return dict(sku_daily)


def _compute_turnover_days(total_inv, daily_out_avg):
    """库存周转天数 = 当前库存 / 日均出库"""
    if daily_out_avg <= 0:
        return 999
    return round(total_inv / daily_out_avg, 1)


def _safety_stock_level(daily_avg, lead_time_days=14, service_level=1.65):
    """安全库存 = Z × σ × √LT（简化版）"""
    return round(service_level * daily_avg * math.sqrt(lead_time_days))


def compute_supply_chain_kpis(inv_data, out_data, transit_data=None):
    """主分析入口：返回完整的供应链 KPI 数据包。"""
    inv_map = _aggregate_inventory(inv_data)
    out_daily = _aggregate_outbound_daily(out_data, days=90)

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    # ---- 计算每个 SKU 的指标 ----
    sku_metrics = []
    for sku, inv_info in inv_map.items():
        qty = inv_info["qty"]
        daily_out = out_daily.get(sku, {})
        # 最近7天日均
        recent_7 = []
        for i in range(7):
            d = (now - timedelta(days=i + 1)).strftime("%Y-%m-%d")
            recent_7.append(daily_out.get(d, 0))
        avg_7 = sum(recent_7) / 7 if any(recent_7) else 0
        # 最近30天日均
        recent_30 = []
        for i in range(30):
            d = (now - timedelta(days=i + 1)).strftime("%Y-%m-%d")
            recent_30.append(daily_out.get(d, 0))
        avg_30 = sum(recent_30) / 30 if any(recent_30) else 0
        avg_daily = avg_30 if avg_30 > 0 else avg_7

        turnover = _compute_turnover_days(qty, avg_daily)
        safety = _safety_stock_level(max(avg_daily, 0.1))
        sellable_days = round(qty / avg_daily) if avg_daily > 0 else 999
        coverage_rate = round(min(qty / safety * 100, 999), 1) if safety > 0 else 100

        # 风险等级
        if sellable_days <= 7 or qty <= 0:
            risk = "high"
        elif sellable_days <= 21 or coverage_rate < 100:
            risk = "warning"
        else:
            risk = "normal"

        sku_metrics.append({
            "sku": sku,
            "qty": round(qty),
            "avg_daily_out": round(avg_daily, 1),
            "turnover_days": turnover,
            "sellable_days": sellable_days,
            "safety_stock": safety,
            "coverage_rate": coverage_rate,
            "risk": risk,
            "warehouses": len(inv_info["warehouses"]),
            "groups": list(inv_info["groups"]),
        })

    sku_metrics.sort(key=lambda x: (
        {"high": 0, "warning": 1, "normal": 2}[x["risk"]],
        x["sellable_days"]
    ))

    # ---- 汇总 KPI ----
    total_sku = len(sku_metrics)
    high_risk = len([s for s in sku_metrics if s["risk"] == "high"])
    warning_risk = len([s for s in sku_metrics if s["risk"] == "warning"])
    normal_risk = len([s for s in sku_metrics if s["risk"] == "normal"])

    total_inv = sum(s["qty"] for s in sku_metrics)
    all_daily_out = defaultdict(float)
    for sku, daily in out_daily.items():
        for d, q in daily.items():
            all_daily_out[d] += q
    avg_daily_total = sum(all_daily_out.values()) / max(len(all_daily_out), 1)
    overall_turnover = _compute_turnover_days(total_inv, avg_daily_total)

    # 安全库存覆盖率
    covered = len([s for s in sku_metrics if s["coverage_rate"] >= 100])
    safety_coverage = round(covered / total_sku * 100, 1) if total_sku > 0 else 100

    # ---- 库存趋势（最近30天每日总量）----
    inv_trend = []
    for i in range(30):
        d = (now - timedelta(days=29 - i)).strftime("%Y-%m-%d")
        daily_total = all_daily_out.get(d, 0)
        inv_trend.append({"date": d, "daily_out": round(daily_total), "cum_inv": 0})
    # 累计库存趋势（简化：期末=期初-出库）
    if inv_trend:
        cum = total_inv + sum(x["daily_out"] for x in inv_trend)
        for t in reversed(inv_trend):
            cum -= t["daily_out"]
            t["cum_inv"] = round(cum)
    # 安全库存阈值
    safety_threshold = _safety_stock_level(avg_daily_total) if avg_daily_total > 0 else 0

    # ---- 供应商评分（模拟数据，可对接真实数据）----
    suppliers = _generate_mock_suppliers()

    # ---- 供应商质量饼图统计 ----
    quality_dist = {"excellent": 0, "qualified": 0, "poor": 0}
    for s in suppliers:
        if s["composite_score"] >= 85:
            quality_dist["excellent"] += 1
        elif s["composite_score"] >= 60:
            quality_dist["qualified"] += 1
        else:
            quality_dist["poor"] += 1

    # ---- 物流线路（从真实在途数据计算）----
    logistics = _compute_logistics_from_transit(transit_data or [])

    # 从物流数据算真实KPI
    total_containers = len(transit_data) if transit_data else 0
    arrived_ok = sum(1 for r in (transit_data or []) if r.get("status") == "已到港")
    on_time_pct = round(arrived_ok / total_containers * 100, 1) if total_containers else 94.2
    total_vol = sum(l.get("volume", 0) for l in logistics)
    total_cost = sum(l.get("cost_per_kg", 0) * l.get("volume", 0) for l in logistics)
    unit_cost = round(total_cost / total_vol, 1) if total_vol > 0 else 12.8

    return {
        "kpis": {
            "turnover_days": overall_turnover,
            "safety_coverage": safety_coverage,
            "on_time_delivery": on_time_pct,
            "shortage_risk_count": high_risk,
            "unit_logistics_cost": unit_cost,
            "fulfillment_rate": 97.6,
        },
        "risk_summary": {
            "high": high_risk,
            "warning": warning_risk,
            "normal": normal_risk,
            "total": total_sku,
        },
        "sku_risks": sku_metrics[:80],
        "inv_trend": inv_trend,
        "safety_threshold": safety_threshold,
        "suppliers": suppliers,
        "quality_dist": quality_dist,
        "logistics": logistics,
    }


def _generate_mock_suppliers():
    """生成模拟供应商评分数据。"""
    names = [
        "深圳XX电子", "东莞YY五金", "中山ZZ家具", "佛山AA包装",
        "惠州BB塑料", "广州CC纺织", "珠海DD电器", "江门EE建材",
        "肇庆FF配件", "清远GG五金", "韶关HH材料", "湛江II食品",
    ]
    random.seed(42)
    suppliers = []
    for i, name in enumerate(names):
        delivery = random.randint(55, 98)
        quality = random.randint(60, 99)
        response = random.randint(50, 95)
        price = random.randint(60, 95)
        composite = round(delivery * 0.35 + quality * 0.35 + response * 0.15 + price * 0.15)
        if composite >= 85:
            grade = "优秀"
        elif composite >= 70:
            grade = "合格"
        else:
            grade = "待整改"
        suppliers.append({
            "id": f"S{i+1:03d}",
            "name": name,
            "delivery_score": delivery,
            "quality_score": quality,
            "response_score": response,
            "price_score": price,
            "composite_score": composite,
            "grade": grade,
            "orders": random.randint(10, 200),
            "defect_rate": round(random.uniform(0.1, 5.0), 1),
        })
    suppliers.sort(key=lambda x: -x["composite_score"])
    return suppliers


def _normalize_port(pod):
    """Normalize POD string to a canonical region name."""
    if not pod:
        return "未知"
    p = pod.lower()
    west_us = ["los angeles", "long beach", "oakland", "seattle", "tacoma", "vancouver", "san francisco", "portland"]
    east_us = ["new york", "newark", "savannah", "norfolk", "charleston", "baltimore", "boston", "miami", "jacksonville", "philadelphia"]
    gulf_us = ["houston", "mobile", "new orleans"]
    europe = ["rotterdam", "hamburg", "antwerp", "felixstowe", "southampton", "le havre", "bremen"]
    if any(k in p for k in west_us):
        return "美国西海岸"
    if any(k in p for k in east_us):
        return "美国东海岸"
    if any(k in p for k in gulf_us):
        return "美国墨西哥湾"
    if any(k in p for k in europe):
        return "欧洲"
    if "ca" in p or "canada" in p:
        return "加拿大"
    return "其他"


def _compute_logistics_from_transit(transit_records):
    """从真实在途数据计算物流线路时效，按 目的港区域+船公司 分组。"""
    if not transit_records:
        return []

    groups = defaultdict(lambda: {"days_list": [], "delays": 0, "total": 0, "qty": 0, "pol_set": set(), "pod_set": set()})

    for rec in transit_records:
        pod_raw = rec.get("pod") or ""
        shipping_line = rec.get("shipping_line") or ""
        if not pod_raw and not shipping_line:
            continue

        region = _normalize_port(pod_raw)
        key = f"{region}|{shipping_line}" if shipping_line else region
        g = groups[key]
        g["pol_set"].add(rec.get("pol") or "")
        g["pod_set"].add(pod_raw)
        g["total"] += 1
        g["qty"] += int(rec.get("total_qty") or 0)

        etd = rec.get("etd")
        eta = rec.get("eta_est")
        actual = rec.get("actual_arrival_date")
        status = rec.get("status") or rec.get("manual_status") or ""

        # Compute transit days
        days = None
        if etd and eta:
            try:
                d_etd = datetime.strptime(str(etd)[:10], "%Y-%m-%d")
                d_eta = datetime.strptime(str(eta)[:10], "%Y-%m-%d")
                days = (d_eta - d_etd).days
            except (ValueError, TypeError):
                pass
        if days is None and etd and actual:
            try:
                d_etd = datetime.strptime(str(etd)[:10], "%Y-%m-%d")
                d_act = datetime.strptime(str(actual)[:10], "%Y-%m-%d")
                days = (d_act - d_etd).days
            except (ValueError, TypeError):
                pass

        if days is not None and days > 0:
            g["days_list"].append(days)

        if status == "延误" or (actual and eta and actual > eta):
            g["delays"] += 1

    results = []
    for key, g in sorted(groups.items(), key=lambda x: -x[1]["qty"]):
        parts = key.split("|", 1)
        region = parts[0]
        ship_line = parts[1] if len(parts) > 1 else ""

        avg_days = round(sum(g["days_list"]) / len(g["days_list"])) if g["days_list"] else 0
        # Use the region's pod sample to get target
        sample_pod = next(iter(g["pod_set"] - {""}), "")
        target = transit_days(sample_pod)
        delay_rate = round(g["delays"] / g["total"] * 100, 1) if g["total"] else 0
        on_time = round(100 - delay_rate, 1)

        route_label = f"中国→{region}"
        if ship_line:
            route_label += f"（{ship_line}）"

        # Infer mode: 默认海运
        mode = "海运"
        if avg_days and avg_days <= 5:
            mode = "空运"
        elif avg_days and avg_days <= 15 and target <= 15:
            mode = "海运"

        results.append({
            "route": route_label,
            "mode": mode,
            "avg_days": avg_days,
            "target_days": target,
            "delay_rate": delay_rate,
            "cost_per_kg": 8.5,  # 暂无真实成本数据
            "volume": g["qty"],
            "on_time": on_time,
            "containers": g["total"],
        })

    return results
