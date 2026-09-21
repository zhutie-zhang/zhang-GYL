import abc
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


class BaseAdapter(abc.ABC):
    """海外仓适配器基类。

    每个海外仓写一个适配器，实现两个方法即可：
      fetch_inventory()                -> (points, fetched_at)
      fetch_outbound(requested_date)   -> (points, fetched_at, date_used)

    points 为列表，每个元素形如 {"id": str, "name": str, "rows": [...]}，
    rows 为列表，每个元素形如 {"sku": str, "name": str, "qty": int}。

    一个"仓点" = points 里的一项。多数适配器一个配置条目即一个仓点
    （用 single_point 包装即可）；一个配置条目对应多个物理仓的
    （如 Aidelivery 账户下有多个 StockID），返回多个 point。

    fetch_outbound(requested_date, requested_end)：
      - 都不传：查"中国时间的前一天"（默认出库日期，可用 config.server.default_outbound_tz 调整）
      - 只传 requested_date：查该单日
      - 两个都传：查 [requested_date, requested_end] 闭区间（多条件筛选用）
    """

    DEFAULT_OUT_TZ = "Asia/Shanghai"

    def __init__(self, cfg):
        self.cfg = cfg

    def _now(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _default_out_date(self):
        """未指定日期时默认查询的日期：中国时间的前一天。"""
        tz = self.cfg.get("default_outbound_tz") or self.DEFAULT_OUT_TZ
        return (datetime.now(ZoneInfo(tz)) - timedelta(days=1)).date()

    def single_point(self, rows, name=None):
        return [{
            "id": str(self.cfg.get("id", "")),
            "name": name or self.cfg.get("name") or self.cfg.get("id", ""),
            "rows": rows,
        }]

    def fill_empty_points(self, points, warehouses):
        """把没有数据的仓点补成空 rows，保证看板展示全部仓点。

        warehouses: 可迭代的 (id, name) 列表，id 为仓点 id，name 为展示名。
        """
        seen = {str(p.get("id", "")) for p in points}
        for wid, name in warehouses:
            if str(wid) not in seen:
                points.append({"id": str(wid), "name": name, "rows": []})
        return points

    @abc.abstractmethod
    def fetch_inventory(self):
        raise NotImplementedError

    @abc.abstractmethod
    def fetch_outbound(self, requested_date=None, requested_end=None):
        raise NotImplementedError

    def fetch_outbound_dated(self, requested_date=None, requested_end=None):
        """返回带日期的原始出库流水行 [{sku, name, qty, date, wh}]。
        默认不支持（返回 None），由上层回退到 fetch_outbound。"""
        return None
