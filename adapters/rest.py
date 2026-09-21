import json
import re
import time
from datetime import datetime

import requests

from adapters.base import BaseAdapter


def resolve(obj, path):
    """按 a.b.c 路径取值，支持列表索引如 a.0.name。取不到返回 None。"""
    if not path:
        return obj
    cur = obj
    for part in str(path).split("."):
        if cur is None:
            return None
        if isinstance(cur, (list, tuple)):
            if part.isdigit():
                idx = int(part)
                cur = cur[idx] if 0 <= idx < len(cur) else None
                continue
            cur = [resolve(x, part) for x in cur if isinstance(x, dict)]
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
            continue
        return None
    return cur


def to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


class RestAdapter(BaseAdapter):
    """通用 REST 适配器：通过 config.json 里的字段映射对接任意海外仓 HTTP API。

    支持的鉴权方式：
      - none / apikey(header) / bearer / basic
    支持的映射字段（mapping 配置）：
      inventory: items(列表路径) sku name qty
      outbound:  items(列表路径) sku name qty date
    """

    def __init__(self, cfg):
        super().__init__(cfg)
        self.base_url = (cfg.get("base_url") or "").rstrip("/")
        self.endpoints = cfg.get("endpoints", {})
        self.mapping = cfg.get("mapping", {})
        self.params = cfg.get("params", {})
        self.timeout = int(cfg.get("timeout", 30))
        self.session = requests.Session()
        self._configure_auth()

    def _configure_auth(self):
        auth = self.cfg.get("auth") or {}
        atype = auth.get("type", "none")
        self._auth_requests = None
        if atype == "apikey":
            self.session.headers[auth.get("header", "X-API-Key")] = auth.get("key", "")
        elif atype == "bearer":
            self.session.headers["Authorization"] = f"Bearer {auth.get('token', '')}"
        elif atype == "basic":
            self._auth_requests = (auth.get("username", ""), auth.get("password", ""))

    def _call(self, endpoint_key, extra_params=None):
        path = self.endpoints.get(endpoint_key)
        if not path:
            raise ValueError(f"缺少 endpoints.{endpoint_key} 配置")
        url = self.base_url + path if self.base_url else path
        params = dict(self.params.get(endpoint_key, {}))
        if extra_params:
            params.update(extra_params)
        last = None
        for attempt in range(5):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout,
                                        auth=self._auth_requests)
                if resp.status_code >= 400:
                    last = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                    time.sleep(2 * (attempt + 1))
                    continue
                return resp.json()
            except (requests.RequestException, json.JSONDecodeError, ValueError) as e:
                last = e
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"请求失败（已重试5次）: {last}")

    def _rows(self, endpoint_key, extra_params=None, date_from=None, date_to=None):
        data = self._call(endpoint_key, extra_params)
        m = self.mapping.get(endpoint_key, {})
        items = resolve(data, m.get("items")) or []
        if not isinstance(items, list):
            items = [items]
        rows = []
        for it in items:
            if not isinstance(it, dict):
                continue
            sku = str(resolve(it, m.get("sku", "sku")) or "")
            if not sku:
                continue
            rows.append({
                "sku": sku,
                "name": str(resolve(it, m.get("name", "name")) or ""),
                "qty": to_int(resolve(it, m.get("qty", "qty"))),
                "_date": str(resolve(it, m.get("date")) or "") if m.get("date") else "",
            })
        date_field = m.get("date")
        if date_field and (date_from or date_to):
            lo = date_from or "0000-00-00"
            hi = date_to or "9999-99-99"
            rows = [r for r in rows if lo <= r.get("_date", "") <= hi]
        return rows

    def fetch_inventory(self):
        rows = self._rows("inventory")
        return self.single_point(rows), self._now()

    def fetch_outbound(self, requested_date=None, requested_end=None):
        date_param = (self.cfg.get("mapping", {}).get("outbound", {})
                      .get("date_param"))
        extra = {date_param: requested_date} if (date_param and requested_date) else None
        rows = self._rows("outbound", extra,
                          date_from=requested_date, date_to=requested_end)
        return self.single_point(rows), self._now(), requested_date

    def fetch_outbound_dated(self, requested_date=None, requested_end=None):
        """返回带日期的原始出库流水行（不聚合、不套件展开）。"""
        rows = self._rows("outbound", None,
                          date_from=requested_date, date_to=requested_end)
        return [{"sku": r["sku"], "name": r["name"], "qty": r["qty"],
                 "date": r["_date"] or (requested_date or ""),
                 "wh": self.cfg.get("id", "")}
                for r in rows]
