import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from adapters.base import BaseAdapter

DEFAULT_ENDPOINT = "http://www.aideliveryinc.com/WebService/PublicService.asmx"
NS = "http://tempuri.org/"


def to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


class AideliveryAdapter(BaseAdapter):
    """Aidelivery（aideliveryinc.com）SOAP 海外仓适配器。

    config 关键项：
      token         API Token（必填）
      customer_id   客户ID CustomerID（GetInventoryLog 出库流水使用，必填）
      stock_id      仓库 StockID；留空则通过 GetStockList 自动拉全部仓并汇总
      timezone      出库"前一天"按该时区计算，默认 America/New_York
      mapping       inventory / outbound 字段映射（可覆盖默认值）

    库存接口：GetStockList(Token) -> GetInventoryList(Token, StockID, SKU)
    出库接口：GetInventoryLog(CustomerID, GoodsCode, StockCode, StartTime, EndTime,
                              PageIndex, PageSize)  注：此接口无需 Token，
              日期参数须为 Unix 秒级时间戳，changeQty<0 记作出库。
    """

    def __init__(self, cfg):
        super().__init__(cfg)
        self.token = cfg["token"]
        self.customer_id = str(cfg.get("customer_id") or "")
        self.stock_id = str(cfg.get("stock_id") or "")
        self.endpoint = (cfg.get("endpoint") or DEFAULT_ENDPOINT).rstrip("/")
        self.timeout = int(cfg.get("timeout", 20))
        self.timezone = cfg.get("timezone", "America/New_York")

        inv = cfg.get("mapping", {}).get("inventory", {})
        self.inv_sku = inv.get("sku", "SKU")
        self.inv_qty = inv.get("qty", "AvailableQty")

        out = cfg.get("mapping", {}).get("outbound", {})
        self.out_sku = out.get("sku", "cwSkuCode")
        self.out_qty = out.get("qty", "changeQty")

        self._stocks = None
        self._stocks_at = 0.0
        self._inv_pts = None
        self._inv_pts_at = 0.0

    # ---------- SOAP 调用 ----------

    def _call(self, method, inner_xml, with_token=True, retries=5):
        token_tag = f"<Token>{self.token}</Token>" if with_token else ""
        body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
            'xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            f'<soap:Body><{method} xmlns="{NS}">'
            f"{token_tag}{inner_xml}"
            f"</{method}></soap:Body></soap:Envelope>"
        )
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f"{NS}{method}",
        }
        last = None
        for attempt in range(retries):
            try:
                resp = requests.post(self.endpoint, data=body.encode("utf-8"),
                                     headers=headers, timeout=self.timeout)
                if resp.status_code >= 400:
                    last = RuntimeError(
                        f"Aidelivery HTTP {resp.status_code}: {resp.text[:200]}")
                    time.sleep(2 * (attempt + 1))
                    continue
                m = re.search(rf"<{method}Result>(.*?)</{method}Result>", resp.text, re.S)
                if not m:
                    last = RuntimeError(f"Aidelivery 响应无法解析: {resp.text[:200]}")
                    time.sleep(2 * (attempt + 1))
                    continue
                raw = html.unescape(m.group(1))
                raw = re.sub(r"^<!\[CDATA\[|\]\]>$", "", raw)
                return json.loads(raw)
            except (requests.RequestException, json.JSONDecodeError) as e:
                last = e
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"Aidelivery 请求失败（已重试{retries}次）: {last}")

    def _ensure_ok(self, result):
        if isinstance(result, dict) and "success" in result:
            if not result.get("success") or to_int(result.get("errorCode")) != 0:
                raise RuntimeError(
                    f"Aidelivery 业务错误: {result.get('errorMsg') or result}")
            return
        if str(result.get("code")) != "0":
            raise RuntimeError(
                f"Aidelivery 业务错误 code={result.get('code')}: {result.get('msg')}")

    # ---------- 库存 ----------

    def _stock_list(self):
        now = time.time()
        if self._stocks is None or now - self._stocks_at > 300:
            result = self._call("GetStockList", "")
            self._ensure_ok(result)
            self._stocks = result.get("data") or []
            self._stocks_at = now
        return self._stocks

    def _inventory_ids(self):
        if self.stock_id:
            return [self.stock_id]
        ids = []
        for s in self._stock_list():
            sid = str(s.get("StockID") or "")
            if sid:
                ids.append(sid)
        return ids

    def _wh_label(self, stock_id):
        sid = str(stock_id)
        for s in self._stock_list():
            if str(s.get("StockID")) == sid:
                code = s.get("Code") or ""
                if code:
                    return f"{self.customer_id}·{code}"
                break
        return f"{self.customer_id}·仓{sid}"

    def _inv_point(self, sid):
        result = self._call("GetInventoryList", f"<StockID>{sid}</StockID><SKU />")
        self._ensure_ok(result)
        out = []
        for it in result.get("data") or []:
            if not isinstance(it, dict):
                continue
            sku = str(it.get(self.inv_sku) or "")
            if not sku:
                continue
            out.append({
                "sku": sku,
                "name": str(it.get("ProductName") or ""),
                "qty": to_int(it.get(self.inv_qty)),
                "age_days": to_int(it.get("StorageAge")),
                "shelf": str(it.get("CreateTime") or ""),
                "location": str(it.get("StockUnitNo") or ""),
            })
        if not out:
            return None
        return {"id": sid, "name": self._wh_label(sid), "rows": out}

    def fetch_inventory_age(self, statistic_date=None):
        """获取实力派产品库龄：GetInventoryList 每条已含 StorageAge(在库天数)+CreateTime(上架时间)+StockUnitNo(库位)。
        同一 SKU 在不同库位/不同批次会出多行，即批次维度库龄。"""
        points = self._inventory_points()
        rows = []
        for p in points:
            wh = p.get("name", p.get("id", ""))
            for r in p.get("rows") or []:
                rows.append({
                    "wh": p.get("id", ""),
                    "wh_name": wh,
                    "sku": r.get("sku"),
                    "name": r.get("name"),
                    "qty": r.get("qty", 0),
                    "age_days": r.get("age_days", 0),
                    "shelf_date": r.get("shelf", ""),
                    "location": r.get("location", ""),
                })
        return rows, self._now()

    def _inventory_points(self):
        """有库存的仓点列表（缓存 5 分钟，与库存面板同源）。"""
        now = time.time()
        if self._inv_pts is None or now - self._inv_pts_at > 300:
            ids = self._inventory_ids()
            results = {}
            with ThreadPoolExecutor(max_workers=min(6, max(1, len(ids)))) as ex:
                futures = [ex.submit(self._inv_point, sid) for sid in ids]
                for f in as_completed(futures):
                    try:
                        point = f.result()
                    except Exception:
                        continue
                    if point:
                        results[point["id"]] = point
            def sort_key(item):
                k = item[0]
                return (0, int(k)) if k.isdigit() else (1, k)
            self._inv_pts = [results[k] for k in sorted(results, key=sort_key)]
            self._inv_pts_at = now
        return self._inv_pts

    def fetch_inventory(self):
        return self._inventory_points(), self._now()

    # ---------- 出库 ----------

    @staticmethod
    def _naive_ts(date_str):
        return int(time.mktime(time.strptime(date_str + " 00:00:00",
                                             "%Y-%m-%d %H:%M:%S")))

    def _fetch_log_range(self, start, end):
        start_ts = self._naive_ts((start - timedelta(days=1)).strftime("%Y-%m-%d"))
        end_ts = self._naive_ts((end + timedelta(days=2)).strftime("%Y-%m-%d"))
        rows = []
        page = 1
        while page <= 50:
            inner = (
                f"<CustomerID>{self.customer_id}</CustomerID>"
                f"<GoodsCode></GoodsCode><StockCode></StockCode>"
                f"<StartTime>{start_ts}</StartTime><EndTime>{end_ts}</EndTime>"
                f"<PageIndex>{page}</PageIndex><PageSize>500</PageSize>"
            )
            result = self._call("GetInventoryLog", inner, with_token=False)
            self._ensure_ok(result)
            chunk = (result.get("result") or {}).get("inventoryChangeList") or []
            if not chunk:
                break
            rows.extend(chunk)
            if len(chunk) < 500:
                break
            page += 1
        lo = start.strftime("%Y-%m-%d")
        hi = end.strftime("%Y-%m-%d")
        out = []
        for it in rows:
            if not isinstance(it, dict):
                continue
            ctime = str(it.get("changeTime") or "")[:10]
            if not (lo <= ctime <= hi):
                continue
            sku = str(it.get(self.out_sku) or "")
            if not sku:
                continue
            change = to_int(it.get(self.out_qty))
            if change >= 0:
                continue
            wh = str(it.get("cwWarehouseCode") or "")
            out.append({"sku": sku, "wh": wh, "qty": -change, "date": ctime})
        return out

    def fetch_outbound_dated(self, requested_date=None, requested_end=None):
        """返回带日期的原始出库流水行（不聚合、不套件展开）。"""
        if requested_date:
            start = datetime.strptime(requested_date, "%Y-%m-%d").date()
            end = datetime.strptime(requested_end or requested_date, "%Y-%m-%d").date()
        else:
            start = end = self._default_out_date()
        return [{"sku": r["sku"], "name": "", "qty": r["qty"],
                 "date": r["date"], "wh": r["wh"]}
                for r in self._fetch_log_range(start, end)]

    def fetch_outbound(self, requested_date=None, requested_end=None):
        if requested_date:
            start = datetime.strptime(requested_date, "%Y-%m-%d").date()
            end = datetime.strptime(requested_end or requested_date, "%Y-%m-%d").date()
        else:
            start = end = self._default_out_date()
        raw = self._fetch_log_range(start, end)

        by_wh = {}
        for r in raw:
            d = by_wh.setdefault(r["wh"], {})
            d[r["sku"]] = d.get(r["sku"], 0) + r["qty"]

        def sort_key(item):
            k = item[0]
            return (0, int(k)) if k.isdigit() else (1, k)
        points = []
        for wh, m in sorted(by_wh.items(), key=sort_key):
            rows = [{"sku": k, "name": "", "qty": v}
                    for k, v in sorted(m.items(), key=lambda x: -x[1])]
            points.append({"id": wh, "name": self._wh_label(wh), "rows": rows})
        try:
            self.fill_empty_points(points,
                                   [(p["id"], p["name"]) for p in self._inventory_points()])
        except Exception:
            pass
        date_used = (start.strftime("%Y-%m-%d") if start == end
                     else f"{start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}")
        return points, self._now(), date_used
