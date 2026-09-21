import hashlib
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from adapters.base import BaseAdapter

PRODUCTS = [
    ("SKU-1001", "无线蓝牙耳机 Pro", 128, 45),
    ("SKU-1002", "智能手环 Fit5", 89, 60),
    ("SKU-1003", "便携充电宝 20000mAh", 66, 32),
    ("SKU-1004", "USB-C 快充数据线 1.5m", 55, 120),
    ("SKU-1005", "手机磁吸支架", 42, 80),
    ("SKU-1006", "户外运动水壶 750ml", 35, 55),
    ("SKU-1007", "车载手机支架", 28, 95),
    ("SKU-1008", "LED 感应夜灯", 20, 70),
    ("SKU-1009", "无线键盘 K87", 68, 40),
    ("SKU-1010", "人体工学鼠标 M560", 46, 50),
    ("SKU-1011", "桌面收纳盒 三层", 32, 66),
    ("SKU-1012", "加厚垃圾袋 100只", 18, 200),
    ("SKU-1013", "厨房计时器 磁吸款", 15, 88),
    ("SKU-1014", "不锈钢保温杯 500ml", 58, 75),
    ("SKU-1015", "瑜伽垫 加厚防滑", 76, 48),
    ("SKU-1016", "运动健身弹力带套装", 39, 60),
    ("SKU-1017", "电动牙刷旅行盒", 25, 90),
    ("SKU-1018", "行李箱绑带 两件装", 22, 110),
    ("SKU-1019", "证件收纳卡包", 12, 150),
    ("SKU-1020", "宠物自动饮水机", 95, 35),
    ("SKU-1021", "猫抓板 瓦楞纸", 30, 85),
    ("SKU-1022", "宠物梳毛刷 去浮毛", 26, 78),
    ("SKU-1023", "婴儿辅食料理机", 112, 25),
    ("SKU-1024", "儿童防走失背包", 62, 40),
    ("SKU-1025", "硅胶餐垫 儿童款", 18, 95),
    ("SKU-1026", "智能感应垃圾桶", 88, 30),
    ("SKU-1027", "折叠购物车 四轮", 70, 26),
    ("SKU-1028", "抽屉分隔板 6片装", 24, 130),
    ("SKU-1029", "真空压缩收纳袋", 45, 72),
    ("SKU-1030", "空气净化滤芯", 98, 33),
]


def _seed(*parts):
    h = hashlib.md5("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return int(h, 16)


def _rnd(seed, lo, hi):
    return lo + seed % (hi - lo + 1)


class MockAdapter(BaseAdapter):
    """模拟适配器：返回稳定的假数据，用于无真实 API 时演示看板功能。"""

    def fetch_inventory(self):
        rows = []
        for sku, name, base, _ in PRODUCTS:
            r = _seed(self.cfg["id"], "inv", sku, datetime.now().strftime("%Y-%m-%d"))
            qty = max(0, base + (r % 40) - 20)
            rows.append({"sku": sku, "name": name, "qty": qty})
        return self.single_point(rows), self._now()

    def fetch_outbound(self, requested_date=None, requested_end=None):
        if requested_date:
            start = datetime.strptime(requested_date, "%Y-%m-%d").date()
            end = datetime.strptime(requested_end or requested_date, "%Y-%m-%d").date()
        else:
            start = end = self._default_out_date()
        date_used = (start.strftime("%Y-%m-%d") if start == end
                     else f"{start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}")
        agg = {}
        d = start
        while d <= end:
            ds = d.strftime("%Y-%m-%d")
            for sku, name, base, _ in PRODUCTS:
                r = _seed(self.cfg["id"], "out", sku, ds)
                if r % 7 == 0:
                    continue
                qty = _rnd(r, 2, base // 2)
                e = agg.get(sku) or {"sku": sku, "name": name, "qty": 0}
                e["qty"] += qty
                agg[sku] = e
            d += timedelta(days=1)
        rows = sorted(agg.values(), key=lambda x: -x["qty"])
        return self.single_point(rows), self._now(), date_used

    def fetch_outbound_dated(self, requested_date=None, requested_end=None):
        """返回带日期的原始出库流水行（不聚合、不套件展开）。"""
        if requested_date:
            start = datetime.strptime(requested_date, "%Y-%m-%d").date()
            end = datetime.strptime(requested_end or requested_date, "%Y-%m-%d").date()
        else:
            start = end = self._default_out_date()
        out = []
        d = start
        while d <= end:
            ds = d.strftime("%Y-%m-%d")
            for sku, name, base, _ in PRODUCTS:
                r = _seed(self.cfg["id"], "out", sku, ds)
                if r % 7 == 0:
                    continue
                qty = _rnd(r, 2, base // 2)
                if qty > 0:
                    out.append({"sku": sku, "name": name, "qty": qty,
                                "date": ds, "wh": self.cfg["id"]})
            d += timedelta(days=1)
        return out
