import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from adapters.base import BaseAdapter

BASE_URL = "https://api.xlwms.com/openapi/v1"


def make_authcode(app_key: str, app_secret: str, data: dict, req_time: str) -> str:
    """领星 OMS 加签算法：
    1. data 内字段按字典序（不区分大小写）升序排列后转为紧凑 JSON
    2. appKey、排序后的 data、reqTime 三值按字典序升序拼接
    3. authcode = HmacSHA256(密钥=appSecret, 明文=拼接串)，输出 16 进制
    """
    data_str = json.dumps(
        dict(sorted(data.items(), key=lambda kv: kv[0].lower())),
        separators=(",", ":"), ensure_ascii=False)
    parts = {"appKey": app_key, "data": data_str, "reqTime": req_time}
    ordered = "".join(
        v for _, v in sorted(parts.items(), key=lambda kv: kv[0].lower()))
    return hmac.new(app_secret.encode(), ordered.encode(), hashlib.sha256).hexdigest()


def to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


class LingxingAdapter(BaseAdapter):
    """领星 OMS OpenAPI 适配器。

    config 关键项：
      app_key / app_secret   平台密钥
      order_type_list        出库类型，默认 [2]（2-出库单，3-退件出库单）
      wh_code_list           只查指定仓库编码列表（可选）；配置多个时按仓拆分多个仓点
      wh_name_map            仓库编码 -> 展示名（可选，未配置时用系统返回的仓名）
      timezone               出库"前一天"按该时区计算，默认 Asia/Shanghai
    """

    BASE = BASE_URL

    def __init__(self, cfg):
        super().__init__(cfg)
        self.app_key = cfg["app_key"]
        self.app_secret = cfg["app_secret"]
        self.timeout = int(cfg.get("timeout", 20))
        self.order_types = cfg.get("order_type_list", [2])
        self.wh_codes = cfg.get("wh_code_list") or None
        self.wh_names = cfg.get("wh_name_map") or {}
        self.timezone = cfg.get("timezone", "Asia/Shanghai")
        self._inv_whs = None
        self._inv_whs_at = 0.0

    def _wh_name(self, wh, fallback=""):
        return self.wh_names.get(wh) or fallback or wh

    def _inventory_whs(self):
        """有库存的仓点列表（与库存面板同源，作为出库补齐的依据）。"""
        now = time.time()
        if self._inv_whs is None or now - self._inv_whs_at > 300:
            rows, _ = self._paginate(
                "/integratedInventory/pageOpen",
                lambda page, size: {
                    "page": page, "pageSize": size, "stockType": 0,
                    **({"whCodeList": ",".join(self.wh_codes)} if self.wh_codes else {}),
                })
            seen = {}
            for r in rows:
                if not isinstance(r, dict):
                    continue
                wh = str(r.get("whCode") or "").strip()
                if wh:
                    seen[wh] = self._wh_name(wh, str(r.get("whName") or ""))
            self._inv_whs = list(seen.items())
            self._inv_whs_at = now
        return self._inv_whs

    def _call(self, path, data):
        last = None
        for attempt in range(5):
            req_time = str(int(datetime.now().timestamp()))
            authcode = make_authcode(self.app_key, self.app_secret, data, req_time)
            url = f"{self.BASE}{path}?authcode={authcode}"
            body = {"appKey": self.app_key, "data": data, "reqTime": req_time}
            try:
                resp = requests.post(url, json=body, timeout=self.timeout)
                if resp.status_code >= 400:
                    last = RuntimeError(f"领星 HTTP {resp.status_code}: {resp.text[:200]}")
                    time.sleep(2 * (attempt + 1))
                    continue
                j = resp.json()
                if str(j.get("code")) != "200":
                    raise RuntimeError(f"领星接口业务错误 code={j.get('code')}: {j.get('message')}")
                return j.get("data") or {}
            except (requests.RequestException, json.JSONDecodeError, ValueError) as e:
                last = e
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"领星请求失败（已重试5次）: {last}")

    def _paginate(self, path, data_factory, page_size=100):
        rows = []
        page = 1
        total = None
        while total is None or len(rows) < total:
            data = data_factory(page, page_size)
            result = self._call(path, data)
            records = result.get("records") or []
            total = to_int(result.get("total"), 0)
            rows.extend(records)
            if len(records) == 0 or len(rows) >= total:
                break
            page += 1
            if page > 2000:
                break
        return rows, total

    def fetch_inventory(self):
        wh = self.wh_codes
        rows, _ = self._paginate(
            "/integratedInventory/pageOpen",
            lambda page, size: {
                "page": page, "pageSize": size, "stockType": 0,
                **({"whCodeList": ",".join(wh)} if wh else {}),
            })
        by_wh = {}
        for r in rows:
            if not isinstance(r, dict):
                continue
            sku = str(r.get("sku") or "")
            if not sku:
                continue
            whc = str(r.get("whCode") or "").strip()
            if not whc:
                continue
            meta = by_wh.get(whc)
            if meta is None:
                meta = by_wh[whc] = [str(r.get("whName") or ""), {}]
            m = meta[1]
            qty = to_int((r.get("productStockDtl") or {}).get("availableAmount"))
            e = m.get(sku)
            if e is None:
                m[sku] = {"sku": sku, "name": str(r.get("productName") or ""), "qty": qty}
            else:
                e["qty"] += qty
        points = [{"id": whc, "name": self._wh_name(whc, wh_name),
                   "rows": sorted(m.values(), key=lambda x: -x["qty"])}
                  for whc, (wh_name, m) in by_wh.items()]
        points.sort(key=lambda p: p["name"])
        if not points:
            return self.single_point([]), self._now()
        return points, self._now()

    def fetch_inventory_age(self, statistic_date=None):
        """拉取领星 OMS 产品库龄数据。

        GET 端点为领星 OMS 独有能力：
          POST /v1/integratedInventory/pageStockAge（stockItemType=0 产品库存）
        返回每个 SKU 每批上架的库龄：
          {sku, productName, whCode, whName, stockType, totalAmount(数量),
           stockAge(库龄天数), shelfDate(上架日期), statisticDate,
           length/width/height/volume(尺寸体积)}
        库龄 = stockAge 天。领星库龄模块北京时间 16:00 后按前一日统计，
        请求时可根据需要传 statistic_date（库存统计日期，默认不传即最新）。
        注意：一只 SKU 同日多批会上架，聚合时会按 (whCode, sku) 汇总数量与体积。
        """
        rows, _ = self._paginate(
            "/integratedInventory/pageStockAge",
            lambda page, size: {
                "page": page, "pageSize": size, "stockItemType": 0,
                "timeType": "statisticDate",
                **({"whCodeList": self.wh_codes} if self.wh_codes else {}),
                **({"statisticDate": statistic_date} if statistic_date else {}),
            })
        age_rows = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            sku = str(r.get("sku") or "")
            whc = str(r.get("whCode") or "").strip()
            if not sku:
                continue
            age_rows.append({
                "sku": sku,
                "name": str(r.get("productName") or ""),
                "wh": whc,
                "wh_name": str(r.get("whName") or whc),
                "qty": to_int(r.get("totalAmount")),
                "age_days": to_int(r.get("stockAge")),
                "shelf_date": str(r.get("shelfDate") or "")[:10],
                "statistic_date": str(r.get("statisticDate") or "")[:10],
                "length_cm": r.get("length"),
                "width_cm": r.get("width"),
                "height_cm": r.get("height"),
                "volume_cm3": r.get("volume"),
            })
        # pageStockAge 带 timeType=statisticDate 时，一个真实批次(wh,sku,shelfDate)
        # 会被多个统计日期各返回一条快照，若直接累加会把同一批次数量重复放大。
        # 按 (wh, sku, shelfDate) 去重，每个批次只保留最新统计日期的快照。
        latest = {}
        for r in age_rows:
            key = (r["wh"], r["sku"], r["shelf_date"])
            st = r.get("statistic_date") or ""
            if key not in latest or st > (latest[key].get("statistic_date") or ""):
                latest[key] = r
        age_rows = list(latest.values())
        return age_rows, self._now()

    def fetch_outbound(self, requested_date=None, requested_end=None):
        if requested_date:
            start = datetime.strptime(requested_date, "%Y-%m-%d").date()
            end = datetime.strptime(requested_end or requested_date, "%Y-%m-%d").date()
        else:
            start = end = self._default_out_date()
        next_day = end + timedelta(days=1)
        rows, _ = self._paginate(
            "/integratedInventory/pageStockFlow",
            lambda page, size: {
                "page": page, "pageSize": size,
                "startTime": start.strftime("%Y-%m-%d"),
                "endTime": next_day.strftime("%Y-%m-%d"),
                "orderTypeList": self.order_types,
                **({"whCodeList": self.wh_codes} if self.wh_codes else {}),
            },
            page_size=100)
        by_wh = {}
        for r in rows:
            if not isinstance(r, dict):
                continue
            sku = str(r.get("sku") or "")
            if not sku:
                continue
            change = to_int(r.get("changeAmount"))
            if change >= 0:
                continue
            whc = str(r.get("whCode") or "").strip()
            if not whc:
                continue
            meta = by_wh.get(whc)
            if meta is None:
                meta = by_wh[whc] = [str(r.get("whName") or ""), {}]
            m = meta[1]
            e = m.get(sku)
            if e is None:
                m[sku] = {"sku": sku, "name": str(r.get("productName") or ""), "qty": -change}
            else:
                e["qty"] += -change
        points = [{"id": whc, "name": self._wh_name(whc, wh_name),
                   "rows": sorted(m.values(), key=lambda x: -x["qty"])}
                  for whc, (wh_name, m) in by_wh.items()]
        try:
            self.fill_empty_points(points, self._inventory_whs())
        except Exception:
            pass
        date_used = (start.strftime("%Y-%m-%d") if start == end
                     else f"{start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}")
        return points, self._now(), date_used

    def fetch_outbound_dated(self, requested_date=None, requested_end=None):
        """返回带日期的原始出库流水行（不聚合、不套件展开）。"""
        if requested_date:
            start = datetime.strptime(requested_date, "%Y-%m-%d").date()
            end = datetime.strptime(requested_end or requested_date, "%Y-%m-%d").date()
        else:
            start = end = self._default_out_date()
        next_day = end + timedelta(days=1)
        rows, _ = self._paginate(
            "/integratedInventory/pageStockFlow",
            lambda page, size: {
                "page": page, "pageSize": size,
                "startTime": start.strftime("%Y-%m-%d"),
                "endTime": next_day.strftime("%Y-%m-%d"),
                "orderTypeList": self.order_types,
                **({"whCodeList": self.wh_codes} if self.wh_codes else {}),
            },
            page_size=100)
        out = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            sku = str(r.get("sku") or "")
            if not sku:
                continue
            change = to_int(r.get("changeAmount"))
            if change >= 0:
                continue
            whc = str(r.get("whCode") or "").strip()
            if not whc:
                continue
            d = str(r.get("operateTime") or "")[:10]
            if d and not (start.isoformat() <= d <= end.isoformat()):
                continue
            out.append({"sku": sku, "name": str(r.get("productName") or ""),
                        "qty": -change, "date": d or start.isoformat(), "wh": whc})
        return out
