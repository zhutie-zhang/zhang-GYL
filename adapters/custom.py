"""通用 REST API 适配器：支持任意 HTTP API 的库存和出库数据拉取。

配置格式：
{
  "id": "custom-xxx",
  "name": "我的仓库",
  "type": "custom",
  "enabled": true,
  "group": "custom",
  "auth": {
    "type": "none|apikey|bearer|basic|custom_header",
    "key": "...",
    "header": "X-API-Key",
    "token": "...",
    "username": "...",
    "password": "..."
  },
  "inventory_url": "https://api.example.com/inventory",
  "inventory_method": "GET",
  "inventory_body": {},
  "inventory_headers": {},
  "inventory_items_path": "data.items",
  "inventory_sku_path": "sku",
  "inventory_name_path": "name",
  "inventory_qty_path": "qty",
  "inventory_wh_path": "warehouse",
  "outbound_url": "https://api.example.com/outbound",
  "outbound_method": "GET",
  "outbound_body": {},
  "outbound_headers": {},
  "outbound_items_path": "data.items",
  "outbound_sku_path": "sku",
  "outbound_name_path": "name",
  "outbound_qty_path": "qty",
  "outbound_date_path": "date",
  "outbound_wh_path": "warehouse",
  "timeout": 20,
  "wh_name_map": {"WH001": "仓库A"}
}
"""
import json
import re
import time
from datetime import datetime

import requests

from adapters.base import BaseAdapter


def to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _resolve(obj, path):
    if not path:
        return obj
    for part in str(path).split("."):
        if obj is None:
            return None
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif isinstance(obj, (list, tuple)):
            try:
                obj = obj[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return obj


class CustomAdapter(BaseAdapter):
    def __init__(self, cfg):
        super().__init__(cfg)
        self.timeout = int(cfg.get("timeout", 20))
        self.auth = cfg.get("auth") or {}
        self.wh_names = cfg.get("wh_name_map") or {}

        self.inv_url = cfg.get("inventory_url", "")
        self.inv_method = cfg.get("inventory_method", "GET").upper()
        self.inv_body = cfg.get("inventory_body") or {}
        self.inv_headers = cfg.get("inventory_headers") or {}
        self.inv_items = cfg.get("inventory_items_path") or ""
        self.inv_sku = cfg.get("inventory_sku_path") or "sku"
        self.inv_name = cfg.get("inventory_name_path") or "name"
        self.inv_qty = cfg.get("inventory_qty_path") or "qty"
        self.inv_wh = cfg.get("inventory_wh_path") or ""

        self.out_url = cfg.get("outbound_url", "")
        self.out_method = cfg.get("outbound_method", "GET").upper()
        self.out_body = cfg.get("outbound_body") or {}
        self.out_headers = cfg.get("outbound_headers") or {}
        self.out_items = cfg.get("outbound_items_path") or ""
        self.out_sku = cfg.get("outbound_sku_path") or "sku"
        self.out_name = cfg.get("outbound_name_path") or "name"
        self.out_qty = cfg.get("outbound_qty_path") or "qty"
        self.out_date = cfg.get("outbound_date_path") or "date"
        self.out_wh = cfg.get("outbound_wh_path") or ""

    def _auth_headers(self):
        h = {}
        atype = self.auth.get("type", "none")
        if atype == "apikey":
            h[self.auth.get("header", "X-API-Key")] = self.auth.get("key", "")
        elif atype == "bearer":
            h["Authorization"] = f"Bearer {self.auth.get('token', '')}"
        elif atype == "custom_header":
            for k, v in (self.auth.get("headers") or {}).items():
                h[k] = v
        return h

    def _auth_kwargs(self):
        kw = {}
        atype = self.auth.get("type", "none")
        if atype == "basic":
            kw["auth"] = (self.auth.get("username", ""), self.auth.get("password", ""))
        return kw

    def _request(self, url, method, body=None, extra_headers=None):
        headers = {}
        headers.update(self._auth_headers())
        if extra_headers:
            headers.update(extra_headers)
        kw = {"timeout": self.timeout, **self._auth_kwargs()}
        last = None
        for attempt in range(5):
            try:
                if method == "POST":
                    headers.setdefault("Content-Type", "application/json")
                    resp = requests.post(url, json=body, headers=headers, **kw)
                else:
                    resp = requests.get(url, headers=headers, **kw)
                if resp.status_code >= 400:
                    last = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                    time.sleep(2 * (attempt + 1))
                    continue
                return resp.json()
            except (requests.RequestException, json.JSONDecodeError, ValueError) as e:
                last = e
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"请求失败（已重试5次）: {last}")

    def fetch_inventory(self):
        if not self.inv_url:
            return [], self._now()
        data = self._request(self.inv_url, self.inv_method, self.inv_body, self.inv_headers)
        items = _resolve(data, self.inv_items)
        if isinstance(items, dict):
            items = list(items.values())
        if not isinstance(items, list):
            items = []

        if self.inv_wh:
            by_wh = {}
            for it in items:
                if not isinstance(it, dict):
                    continue
                wh = str(_resolve(it, self.inv_wh) or "").strip()
                sku = str(_resolve(it, self.inv_sku) or "").strip()
                if not sku:
                    continue
                d = by_wh.setdefault(wh, [])
                d.append({
                    "sku": sku,
                    "name": str(_resolve(it, self.inv_name) or ""),
                    "qty": to_int(_resolve(it, self.inv_qty)),
                })
            points = []
            for wh, rows in sorted(by_wh.items()):
                name = self.wh_names.get(wh, wh)
                points.append({"id": wh, "name": name, "rows": rows})
            return points, self._now()
        else:
            rows = []
            for it in items:
                if not isinstance(it, dict):
                    continue
                sku = str(_resolve(it, self.inv_sku) or "").strip()
                if not sku:
                    continue
                rows.append({
                    "sku": sku,
                    "name": str(_resolve(it, self.inv_name) or ""),
                    "qty": to_int(_resolve(it, self.inv_qty)),
                })
            return self.single_point(rows), self._now()

    def fetch_outbound(self, requested_date=None, requested_end=None):
        if not self.out_url:
            return [], self._now(), None
        data = self._request(self.out_url, self.out_method, self.out_body, self.out_headers)
        items = _resolve(data, self.out_items)
        if isinstance(items, dict):
            items = list(items.values())
        if not isinstance(items, list):
            items = []

        if requested_date:
            start = datetime.strptime(requested_date, "%Y-%m-%d").date()
            end = datetime.strptime(requested_end or requested_date, "%Y-%m-%d").date()
        else:
            start = end = self._default_out_date()
        lo, hi = start.isoformat(), end.isoformat()

        filtered = []
        for it in items:
            if not isinstance(it, dict):
                continue
            sku = str(_resolve(it, self.out_sku) or "").strip()
            if not sku:
                continue
            d = str(_resolve(it, self.out_date) or "")[:10]
            if not (lo <= d <= hi):
                continue
            qty = to_int(_resolve(it, self.out_qty))
            if qty <= 0:
                continue
            wh = str(_resolve(it, self.out_wh) or "") if self.out_wh else ""
            filtered.append({"sku": sku, "name": str(_resolve(it, self.out_name) or ""),
                             "qty": qty, "date": d, "wh": wh})

        if self.out_wh:
            by_wh = {}
            for r in filtered:
                by_wh.setdefault(r["wh"], {}).setdefault(r["sku"], 0)
                by_wh[r["wh"]][r["sku"]] += r["qty"]
            points = []
            for wh, m in sorted(by_wh.items()):
                name = self.wh_names.get(wh, wh)
                rows = [{"sku": k, "name": "", "qty": v} for k, v in sorted(m.items(), key=lambda x: -x[1])]
                points.append({"id": wh, "name": name, "rows": rows})
        else:
            agg = {}
            for r in filtered:
                agg.setdefault(r["sku"], {"sku": r["sku"], "name": r["name"], "qty": 0})
                agg[r["sku"]]["qty"] += r["qty"]
            rows = sorted(agg.values(), key=lambda x: -x["qty"])
            points = self.single_point(rows)

        date_used = lo if lo == hi else f"{lo} ~ {hi}"
        return points, self._now(), date_used

    def test_connection(self):
        results = {"inventory": None, "outbound": None}
        if self.inv_url:
            try:
                data = self._request(self.inv_url, self.inv_method, self.inv_body, self.inv_headers)
                items = _resolve(data, self.inv_items)
                count = len(items) if isinstance(items, list) else 0
                results["inventory"] = {"ok": True, "count": count, "message": f"获取到 {count} 条记录"}
            except Exception as e:
                results["inventory"] = {"ok": False, "message": str(e)}
        if self.out_url:
            try:
                data = self._request(self.out_url, self.out_method, self.out_body, self.out_headers)
                items = _resolve(data, self.out_items)
                count = len(items) if isinstance(items, list) else 0
                results["outbound"] = {"ok": True, "count": count, "message": f"获取到 {count} 条记录"}
            except Exception as e:
                results["outbound"] = {"ok": False, "message": str(e)}
        return results
