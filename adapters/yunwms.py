import json
import time
from datetime import datetime, timedelta

import requests

from adapters.base import BaseAdapter

DEFAULT_BASE = "https://lc.yunwms.com"


def to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def sort_key(item):
    k = item[0]
    return (0, int(k)) if k.isdigit() else (1, k)


class YunWmsAdapter(BaseAdapter):
    """乐舱海外仓（YunWMS/云递 WMS）SOAP 适配器。

    config 关键项：
      app_token / app_key    API密钥 / API标识（必填）
      base_url               可选，默认 https://lc.yunwms.com
      wh_codes               只查指定仓库编码（可选）
      wh_name_map            仓库编码 -> 展示名（可选，未配置时用系统返回的仓库名）
      order_status_list      出库订单状态，默认 ["D"]（D-已发货）

    接口：POST {base}/default/svc/web-service，SOAP 信封 callService，
      公共参数 service / appToken / appKey / paramsJson(JSON串)。
      库存：getProductInventory（分页，可用数量取 sellable）
      出库：getOrderList（按订单状态 + 出库时间 ship_date_from/to 过滤；
            日期须带时间分量，to 取次日 00:00:00 实现闭区间，否则单日查询返回空）
    """

    def __init__(self, cfg):
        super().__init__(cfg)
        self.app_token = cfg["app_token"]
        self.app_key = cfg["app_key"]
        self.base_url = (cfg.get("base_url") or DEFAULT_BASE).rstrip("/")
        self.timeout = int(cfg.get("timeout", 20))
        self.wh_codes = cfg.get("wh_code_list") or None
        self.wh_names = cfg.get("wh_name_map") or {}
        self.order_statuses = cfg.get("order_status_list", ["D"])
        self._whs = None
        self._whs_at = 0.0
        self._inv_whs = None
        self._inv_whs_at = 0.0

    # ---------- SOAP 调用 ----------

    def _call(self, service, params):
        env = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" '
            'xmlns:ns1="http://www.example.org/Ec/">'
            '<SOAP-ENV:Body><ns1:callService>'
            f"<paramsJson>{json.dumps(params, ensure_ascii=False)}</paramsJson>"
            f"<appToken>{self.app_token}</appToken>"
            f"<appKey>{self.app_key}</appKey>"
            f"<service>{service}</service>"
            "</ns1:callService></SOAP-ENV:Body></SOAP-ENV:Envelope>"
        )
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "callService",
        }
        last = None
        for attempt in range(5):
            try:
                resp = requests.post(f"{self.base_url}/default/svc/web-service",
                                     data=env.encode("utf-8"), headers=headers,
                                     timeout=self.timeout)
                if resp.status_code >= 400:
                    last = RuntimeError(f"乐舱 HTTP {resp.status_code}: {resp.text[:200]}")
                    time.sleep(2 * (attempt + 1))
                    continue
                text = resp.text
                start = text.find("<response>")
                end = text.rfind("</response>")
                if start < 0 or end < 0:
                    last = RuntimeError(f"乐舱响应无法解析: {text[:200]}")
                    time.sleep(2 * (attempt + 1))
                    continue
                raw = text[start + len("<response>"):end]
                j = json.loads(raw)
                if isinstance(j, list):
                    j = j[0] if j else {"ask": "Success", "data": []}
                if str(j.get("ask")) != "Success":
                    raise RuntimeError(f"乐舱业务错误: {j}")
                return j.get("data") or []
            except (requests.RequestException, json.JSONDecodeError) as e:
                last = e
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"乐舱请求失败（已重试5次）: {last}")

    def _paginate(self, service, params_factory):
        rows = []
        page = 1
        page_size = 500
        while page <= 2000:
            j = self._call(service, params_factory(page, page_size))
            if isinstance(j, list):
                rows.extend(j)
                break
            chunk = j.get("data") or []
            if isinstance(chunk, dict):
                chunk = [chunk]
            rows.extend(chunk)
            if str(j.get("nextPage")) != "true":
                break
            page += 1
        return rows

    # ---------- 仓库 ----------

    def _warehouses(self):
        now = time.time()
        if self._whs is None or now - self._whs_at > 3600:
            m = {}
            for w in self._paginate("getWarehouse",
                                    lambda p, s: {"pageSize": s, "page": p}):
                code = str(w.get("warehouse_code") or "")
                name = str(w.get("warehouse_name") or "")
                if code:
                    m[code] = name or code
            self._whs = m
            self._whs_at = now
        return self._whs

    def _wh_name(self, code):
        if code in self.wh_names:
            return self.wh_names[code]
        return self._warehouses().get(code, code)

    def _inventory_whs(self):
        """有库存的仓点列表（与库存面板同源，作为出库补齐的依据）。"""
        now = time.time()
        if self._inv_whs is None or now - self._inv_whs_at > 300:
            rows = self._paginate(
                "getProductInventory",
                lambda page, size: {
                    "pageSize": size, "page": page,
                    **({"warehouse_code_arr": self.wh_codes} if self.wh_codes else {}),
                })
            seen = {}
            for r in rows:
                if not isinstance(r, dict):
                    continue
                c = str(r.get("warehouse_code") or "").strip()
                if c:
                    seen[c] = self._wh_name(c)
            self._inv_whs = list(seen.items())
            self._inv_whs_at = now
        return self._inv_whs

    # ---------- 库存 ----------

    def fetch_inventory_age(self, statistic_date=None):
        """获取乐舱产品库龄：getProductInventory 返回 batch_info[] 含每SKU每批次
        ib_fifo_time(上架时间)+stock_age(库龄天数)+sellable_quantity(在库可售)。
        只统计在库(sellable)数据。若无批次则回退到 SKU 级 mage/mfifotime。"""
        wh = self.wh_codes
        rows = self._paginate(
            "getProductInventory",
            lambda page, size: {
                "pageSize": size, "page": page,
                **({"warehouse_code_arr": wh} if wh else {}),
            })
        out = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            whc = str(r.get("warehouse_code") or "").strip()
            sku = str(r.get("product_sku") or "").strip()
            if not whc or not sku:
                continue
            name = str(r.get("product_title") or "")
            batches = r.get("batch_info") or []
            sku_age = to_int(r.get("mage"))
            sku_fifo = str(r.get("mfifotime") or "")
            if batches:
                for b in batches:
                    if not isinstance(b, dict):
                        continue
                    qty = to_int(b.get("sellable_quantity") or b.get("ib_quantity"))
                    if qty <= 0:
                        continue
                    out.append({
                        "wh": whc, "wh_name": self._wh_name(whc), "sku": sku, "name": name,
                        "qty": qty,
                        "age_days": to_int(b.get("stock_age") or sku_age),
                        "shelf_date": str(b.get("ib_fifo_time") or "")[:10],
                        "batch": str(b.get("receiving_code") or "")[:10],
                    })
            else:
                qty = to_int(r.get("sellable"))
                if qty > 0:
                    out.append({
                        "wh": whc, "wh_name": self._wh_name(whc), "sku": sku, "name": name,
                        "qty": qty, "age_days": sku_age,
                        "shelf_date": str(sku_fifo or "")[:10], "batch": "",
                    })
        return out, self._now()

    def fetch_inventory(self):
        wh = self.wh_codes
        rows = self._paginate(
            "getProductInventory",
            lambda page, size: {
                "pageSize": size, "page": page,
                **({"warehouse_code_arr": wh} if wh else {}),
            })
        by_wh = {}
        for r in rows:
            if not isinstance(r, dict):
                continue
            whc = str(r.get("warehouse_code") or "").strip()
            sku = str(r.get("product_sku") or "").strip()
            if not whc or not sku:
                continue
            d = by_wh.setdefault(whc, {})
            qty = to_int(r.get("sellable"))
            e = d.get(sku)
            if e is None:
                d[sku] = {"sku": sku, "name": str(r.get("product_title") or ""), "qty": qty}
            else:
                e["qty"] += qty
                if not e["name"]:
                    e["name"] = str(r.get("product_title") or "")
        points = [{"id": whc, "name": self._wh_name(whc),
                   "rows": sorted(m.values(), key=lambda x: -x["qty"])}
                  for whc, m in sorted(by_wh.items(), key=sort_key)]
        return points, self._now()

    # ---------- 出库 ----------

    def _order_rows(self, start, end):
        s = f"{start.strftime('%Y-%m-%d')} 00:00:00"
        e = f"{(end + timedelta(days=1)).strftime('%Y-%m-%d')} 00:00:00"
        out = []
        for status in self.order_statuses:
            rows = self._paginate(
                "getOrderList",
                lambda page, size, st=status: {
                    "pageSize": size, "page": page,
                    "order_status": st,
                    "ship_date_from": s, "ship_date_to": e,
                })
            for o in rows:
                if not isinstance(o, dict):
                    continue
                whc = str(o.get("warehouse_code") or "").strip()
                if not whc:
                    continue
                for it in (o.get("items") or []):
                    sku = str(it.get("product_sku") or "").strip()
                    if not sku:
                        continue
                    out.append({"sku": sku, "wh": whc, "qty": to_int(it.get("quantity"))})
        return out

    def fetch_outbound(self, requested_date=None, requested_end=None):
        if requested_date:
            start = datetime.strptime(requested_date, "%Y-%m-%d").date()
            end = datetime.strptime(requested_end or requested_date, "%Y-%m-%d").date()
        else:
            start = end = self._default_out_date()
        raw = self._order_rows(start, end)
        by_wh = {}
        for r in raw:
            d = by_wh.setdefault(r["wh"], {})
            d[r["sku"]] = d.get(r["sku"], 0) + r["qty"]
        points = [{"id": whc, "name": self._wh_name(whc),
                   "rows": [{"sku": k, "name": "", "qty": v}
                            for k, v in sorted(m.items(), key=lambda x: -x[1])]}
                  for whc, m in sorted(by_wh.items(), key=sort_key)]
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
        lo = start.isoformat()
        hi = end.isoformat()
        out = []
        for status in self.order_statuses:
            rows = self._paginate(
                "getOrderList",
                lambda page, size, st=status: {
                    "pageSize": size, "page": page,
                    "order_status": st,
                    "ship_date_from": f"{start.strftime('%Y-%m-%d')} 00:00:00",
                    "ship_date_to": f"{(end + timedelta(days=1)).strftime('%Y-%m-%d')} 00:00:00",
                })
            for o in rows:
                if not isinstance(o, dict):
                    continue
                whc = str(o.get("warehouse_code") or "").strip()
                if not whc:
                    continue
                d = str(o.get("date_shipping") or "")[:10]
                if d and not (lo <= d <= hi):
                    continue
                d = d or start.isoformat()
                for it in (o.get("items") or []):
                    sku = str(it.get("product_sku") or "").strip()
                    if not sku:
                        continue
                    out.append({"sku": sku, "name": str(it.get("product_title") or ""),
                                "qty": to_int(it.get("quantity")), "date": d, "wh": whc})
        return out
