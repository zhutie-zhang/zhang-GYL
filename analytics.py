"""分析引擎：出库时序聚合、指标计算、信号生成、回测。"""
import math
import random
from collections import defaultdict
from datetime import datetime, timedelta


def _safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _aggregate_outbound(out_data, group_by="day"):
    """将出库数据按日/周聚合为时序序列。返回 {sku: [{date, qty}, ...]}"""
    by_sku = defaultdict(lambda: defaultdict(int))
    wh_data = out_data.get("warehouses", {})
    for wh_id, wh in wh_data.items():
        for pt in (wh.get("points") or []):
            for row in (pt.get("rows") or []):
                sku = row.get("sku", "")
                if not sku:
                    continue
                qty = _safe_float(row.get("qty", 0))
                date_str = row.get("date", "")[:10]
                if not date_str:
                    continue
                if group_by == "week":
                    try:
                        d = datetime.strptime(date_str, "%Y-%m-%d")
                        week_start = d - timedelta(days=d.weekday())
                        date_str = week_start.strftime("%Y-%m-%d")
                    except ValueError:
                        pass
                by_sku[sku][date_str] += qty
    result = {}
    for sku, dates in by_sku.items():
        result[sku] = sorted([{"date": d, "qty": q} for d, q in dates.items()],
                             key=lambda x: x["date"])
    return result


def _compute_metrics(series):
    """计算单个SKU的指标序列：MA5/MA10/MA20、增长率、波动率、动量。"""
    if not series:
        return []
    qtys = [_safe_float(p["qty"]) for p in series]
    n = len(qtys)
    metrics = []
    for i in range(n):
        m = {"date": series[i]["date"], "qty": qtys[i]}
        # 移动平均
        for w in [5, 10, 20]:
            if i >= w - 1:
                m[f"ma{w}"] = sum(qtys[i - w + 1:i + 1]) / w
            else:
                m[f"ma{w}"] = None
        # 环比增长率
        if i > 0 and qtys[i - 1] > 0:
            m["growth"] = round((qtys[i] - qtys[i - 1]) / qtys[i - 1] * 100, 1)
        else:
            m["growth"] = 0
        # 7日波动率
        if i >= 6:
            window = qtys[i - 6:i + 1]
            avg = sum(window) / 7
            var = sum((x - avg) ** 2 for x in window) / 7
            m["volatility"] = round(math.sqrt(var), 2) if avg > 0 else 0
        else:
            m["volatility"] = 0
        # 动量 (当日 - 20日前) / 20日前
        if i >= 20 and qtys[i - 20] > 0:
            m["momentum"] = round((qtys[i] - qtys[i - 20]) / qtys[i - 20] * 100, 1)
        else:
            m["momentum"] = 0
        metrics.append(m)
    return metrics


def _generate_signals(metrics):
    """根据指标生成交易信号：买入/卖出/持有/观望。"""
    if not metrics:
        return []
    signals = []
    for i, m in enumerate(metrics):
        sig = {"date": m["date"], "signal": "hold", "strength": 0, "reasons": []}
        score = 0
        # MA5/MA20 金叉/死叉
        if m.get("ma5") is not None and m.get("ma20") is not None:
            if m["ma5"] > m["ma20"]:
                score += 2
                sig["reasons"].append("MA5>MA20 金叉")
            else:
                score -= 2
                sig["reasons"].append("MA5<MA20 死叉")
        # 增长率
        g = m.get("growth", 0)
        if g > 20:
            score += 2
            sig["reasons"].append(f"增长率 +{g}%")
        elif g < -20:
            score -= 2
            sig["reasons"].append(f"增长率 {g}%")
        # 动量
        mom = m.get("momentum", 0)
        if mom > 30:
            score += 1
            sig["reasons"].append(f"动量 +{mom}%")
        elif mom < -30:
            score -= 1
            sig["reasons"].append(f"动量 {mom}%")
        # 波动率异常
        vol = m.get("volatility", 0)
        avg_qty = m["qty"]
        if avg_qty > 0 and vol / avg_qty > 0.5:
            sig["reasons"].append("高波动")
        if score >= 3:
            sig["signal"] = "buy"
            sig["strength"] = min(score / 6, 1.0)
        elif score <= -3:
            sig["signal"] = "sell"
            sig["strength"] = min(abs(score) / 6, 1.0)
        elif score >= 1:
            sig["signal"] = "weak_buy"
            sig["strength"] = 0.3
        elif score <= -1:
            sig["signal"] = "weak_sell"
            sig["strength"] = 0.3
        signals.append(sig)
    return signals


def _compute_rank_metrics(series_map, days_cur, days_prev):
    """排名指标：本期出库量、上期出库量、增长率、MA趋势。"""
    ranks = []
    for sku, series in series_map.items():
        qtys = {p["date"]: _safe_float(p["qty"]) for p in series}
        dates = sorted(qtys.keys())
        if not dates:
            continue
        cur_sum = sum(qtys.get(d, 0) for d in dates if _days_between(d, dates[-1]) < days_cur)
        prev_sum = sum(qtys.get(d, 0) for d in dates if days_cur <= _days_between(d, dates[-1]) < days_cur + days_prev)
        growth = round((cur_sum - prev_sum) / prev_sum * 100, 1) if prev_sum > 0 else 0
        recent_5 = [qtys.get(d, 0) for d in dates[-5:]]
        ma5 = sum(recent_5) / len(recent_5) if recent_5 else 0
        recent_10 = [qtys.get(d, 0) for d in dates[-10:]]
        ma10 = sum(recent_10) / len(recent_10) if recent_10 else 0
        trend = "up" if ma5 > ma10 else ("down" if ma5 < ma10 else "flat")
        ranks.append({
            "sku": sku,
            "cur_qty": round(cur_sum),
            "prev_qty": round(prev_sum),
            "growth": growth,
            "ma5": round(ma5, 1),
            "ma10": round(ma10, 1),
            "trend": trend,
            "days": len(dates),
        })
    ranks.sort(key=lambda x: -x["cur_qty"])
    return ranks


def _days_between(d1, d2):
    try:
        return abs((datetime.strptime(d2, "%Y-%m-%d") - datetime.strptime(d1, "%Y-%m-%d")).days)
    except ValueError:
        return 999


def _backtest(series, ma_short=5, ma_long=20, initial_capital=100000):
    """简单均线回测：金叉买入、死叉卖出。"""
    if not series or len(series) < ma_long:
        return {"error": "数据不足", "trades": [], "equity": [], "stats": {}}
    qtys = [_safe_float(p["qty"]) for p in series]
    dates = [p["date"] for p in series]
    n = len(qtys)
    capital = initial_capital
    position = 0
    trades = []
    equity = []
    buy_price = 0
    for i in range(ma_long - 1, n):
        ma_s = sum(qtys[i - ma_short + 1:i + 1]) / ma_short
        ma_l = sum(qtys[i - ma_long + 1:i + 1]) / ma_long
        price = qtys[i]
        if price <= 0:
            equity.append({"date": dates[i], "value": capital + position * price})
            continue
        # 金叉买入
        if i > ma_long - 1:
            prev_ma_s = sum(qtys[i - ma_short:i + 1]) / ma_short
            prev_ma_l = sum(qtys[i - ma_long:i + 1]) / ma_long
            if prev_ma_s <= prev_ma_l and ma_s > ma_l and position == 0 and capital > 0:
                shares = int(capital * 0.95 / price)
                if shares > 0:
                    position = shares
                    buy_price = price
                    cost = shares * price
                    capital -= cost
                    trades.append({"date": dates[i], "action": "buy", "price": round(price, 2),
                                   "shares": shares, "value": round(cost, 2)})
            # 死叉卖出
            elif prev_ma_s >= prev_ma_l and ma_s < ma_l and position > 0:
                revenue = position * price
                capital += revenue
                pnl = round((price - buy_price) / buy_price * 100, 1)
                trades.append({"date": dates[i], "action": "sell", "price": round(price, 2),
                               "shares": position, "value": round(revenue, 2), "pnl": pnl})
                position = 0
        equity.append({"date": dates[i], "value": round(capital + position * price, 2)})
    # 最终统计
    final_val = equity[-1]["value"] if equity else initial_capital
    total_return = round((final_val - initial_capital) / initial_capital * 100, 2)
    win_trades = [t for t in trades if t["action"] == "sell" and t.get("pnl", 0) > 0]
    all_sells = [t for t in trades if t["action"] == "sell"]
    win_rate = round(len(win_trades) / len(all_sells) * 100, 1) if all_sells else 0
    max_dd = 0
    peak = 0
    for e in equity:
        v = e["value"]
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = round(dd, 2)
    return {
        "trades": trades,
        "equity": equity,
        "stats": {
            "initial_capital": initial_capital,
            "final_value": round(final_val, 2),
            "total_return": total_return,
            "total_trades": len(trades),
            "win_rate": win_rate,
            "max_drawdown": max_dd,
            "ma_short": ma_short,
            "ma_long": ma_long,
        }
    }


def compute_analytics(out_data, period_days=30):
    """主分析入口：返回完整的分析数据包。"""
    series_map = _aggregate_outbound(out_data)
    return compute_analytics_from_series(series_map, period_days)


def compute_analytics_from_series(series_map, period_days=30):
    """从预聚合的 series_map 计算分析数据包。"""
    all_dates = set()
    for s in series_map.values():
        for p in s:
            all_dates.add(p["date"])
    if not all_dates:
        return {"series": {}, "metrics": {}, "signals": {}, "rank": [], "summary": {},
                "period": period_days, "date_range": ["", ""]}
    date_range = sorted(all_dates)
    end_date = date_range[-1]
    start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=period_days)).strftime("%Y-%m-%d")
    filtered = {}
    for sku, s in series_map.items():
        fs = [p for p in s if p["date"] >= start_date]
        if fs:
            filtered[sku] = fs
    result_series = {}
    result_metrics = {}
    result_signals = {}
    for sku, s in filtered.items():
        result_series[sku] = s
        m = _compute_metrics(s)
        result_metrics[sku] = m
        result_signals[sku] = _generate_signals(m)
    rank = _compute_rank_metrics(series_map, 7, 7)
    total_cur = sum(r["cur_qty"] for r in rank)
    total_prev = sum(r["prev_qty"] for r in rank)
    total_growth = round((total_cur - total_prev) / total_prev * 100, 1) if total_prev > 0 else 0
    active_skus = len([r for r in rank if r["cur_qty"] > 0])
    rising = len([r for r in rank if r["growth"] > 10])
    falling = len([r for r in rank if r["growth"] < -10])
    summary = {
        "total_outbound": round(total_cur),
        "total_growth": total_growth,
        "active_skus": active_skus,
        "rising_count": rising,
        "falling_count": falling,
        "date_range": [start_date, end_date],
    }
    return {"series": result_series, "metrics": result_metrics, "signals": result_signals,
            "rank": rank[:50], "summary": summary, "period": period_days,
            "date_range": [start_date, end_date]}
