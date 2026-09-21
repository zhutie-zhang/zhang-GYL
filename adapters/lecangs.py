import hashlib
import json
import time
from datetime import date, datetime, timedelta

import requests

from adapters.base import BaseAdapter

DEFAULT_BASE = "https://app.lecangs.com/api"


def to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def sort_key(item):
    k = item[0]
    return (0, int(k)) if k.isdigit() else (1, k)


class LecangsAdapter(BaseAdapter):
    """乐歌海外仓（app.lecangs.com）适配器。

    config 关键项：
      app_key / app_secret   平台 AccessKey / SecretKey（必填）
      base_url               可选，默认 https://app.lecangs.com/api
      out_type_list          出库业务类型列表，默认 [101901]（出库单）；
                             101907 入库单(ASN)、101909 调拨等
      wh_name_map            仓库编码 -> 展示名（可选）

    接口：
      库存：/oms/inventoryOverview/apiPage（分页，可用数量取 uesNum，
           即 goodsNum 扣除 blockedNum 冻结后的可用库存）
      出库：/oms/inventoryFlow/list（分页，按业务类型拉全部后本地按日期过滤）

    鉴权：header 传 timestamp(毫秒)/accessKey/sign；
      sign = sha256( 按 key 排序拼接 "k=v&..." 去掉末尾 & 后 + secretKey )
    """

    FLOW_IS_FULL_HISTORY = True

    def __init__(self, cfg):
        super().__init__(cfg)
        self.app_key = cfg["app_key"]
        self.app_secret = cfg["app_secret"]
        self.base_url = (cfg.get("base_url") or DEFAULT_BASE).rstrip("/")
        self.timeout = int(cfg.get("timeout", 20))
        self.out_types = cfg.get("out_type_list", [101901])
        self.wh_names = cfg.get("wh_name_map") or {}
        self._full_flow_cache = None
        self._full_flow_ts = 0
        self._full_flow_ttl = int(cfg.get("full_flow_ttl", 3600))

    # ---------- 鉴权 ----------

    def _sign(self, body, ts):
        b = dict(body)
        b["timestamp"] = ts
        b["accessKey"] = self.app_key
        parts = []
        for k in sorted(b.keys()):
            if k == "sign":
                continue
            v = b[k]
            if isinstance(v, (list, dict)):
                v = json.dumps(v, separators=(",", ":"))
            parts.append(f"{k}={v}")
        plain = "&".join(parts) + self.app_secret
        return hashlib.sha256(plain.encode()).hexdigest()

    def _call(self, path, body):
        last = None
        for attempt in range(5):
            ts = str(int(time.time() * 1000))
            sig = self._sign(body, ts)
            headers = {
                "timestamp": ts,
                "accessKey": self.app_key,
                "sign": sig,
                "Content-Type": "application/json;charset=UTF-8",
            }
            try:
                resp = requests.post(f"{self.base_url}{path}", json=body,
                                     headers=headers, timeout=self.timeout)
                if resp.status_code >= 400:
                    last = RuntimeError(f"乐歌 HTTP {resp.status_code}: {resp.text[:200]}")
                    time.sleep(2 * (attempt + 1))
                    continue
                j = resp.json()
                if not j.get("success") or str(j.get("code")) != "200":
                    raise RuntimeError(f"乐歌接口业务错误 code={j.get('code')}: {j.get('message')}")
                return j.get("data") or {}
            except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
                last = e
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"乐歌请求失败（已重试5次）: {last}")

    def _paginate(self, path, body_factory):
        rows = []
        page = 1
        page_size = 500
        total = None
        while total is None or len(rows) < total:
            result = self._call(path, body_factory(page, page_size))
            chunk = result.get("list") or []
            total = to_int(result.get("total"), 0)
            rows.extend(chunk)
            if not chunk or len(rows) >= total:
                break
            page += 1
            if page > 2000:
                break
        return rows

    @staticmethod
    def _sku(r):
        code = str(r.get("goodsCode") or r.get("lecangsCode") or "").strip()
        if not code:
            return ""
        cust = str(r.get("customCode") or "").strip()
        if cust and code.startswith(cust + "-"):
            code = code[len(cust) + 1:]
        return code

    def _point(self, wh, rows):
        return {"id": wh, "name": self.wh_names.get(wh, wh), "rows": rows}

    # ---------- 库存 ----------

    def fetch_inventory(self):
        rows = self._paginate("/oms/inventoryOverview/apiPage",
                              lambda page, size: {"pageNum": page, "pageSize": size})
        by_wh = {}
        for r in rows:
            if not isinstance(r, dict):
                continue
            wh = str(r.get("warehouseCode") or "").strip()
            sku = self._sku(r)
            if not wh or not sku:
                continue
            d = by_wh.setdefault(wh, {})
            qty = to_int(r.get("uesNum"))
            e = d.get(sku)
            if e is None:
                d[sku] = {"sku": sku, "name": str(r.get("cnName") or r.get("enName") or ""),
                          "qty": qty}
            else:
                e["qty"] += qty
                if not e["name"]:
                    e["name"] = str(r.get("cnName") or r.get("enName") or "")
        points = [self._point(wh, sorted(m.values(), key=lambda x: -x["qty"]))
                  for wh, m in sorted(by_wh.items(), key=sort_key)]
        return points, self._now()

    def fetch_inventory_age(self, statistic_date=None):
        """乐歌库龄：无批次/库龄专用接口，用入库流水(101907)按仓库+SKU 分组，
        取当前在库(uesNum)，把该SKU所有入库流水按 timeWarehouseDate 倒序累加，
        累加到覆盖当前库存的那条入库日期即最近一批上架日，库龄=今天-该日。
        逐批次不可得，为近似(每仓库每SKU最近入库日)。若当前在库为0不计入。"""
        rows = self._paginate("/oms/inventoryOverview/apiPage",
                              lambda page, size: {"pageNum": page, "pageSize": size})
        by_wh = {}
        for r in rows:
            if not isinstance(r, dict):
                continue
            wh = str(r.get("warehouseCode") or "").strip()
            sku = self._sku(r)
            if not wh or not sku:
                continue
            d = by_wh.setdefault(wh, {})
            qty = to_int(r.get("uesNum"))
            if qty <= 0:
                continue
            e = d.get(sku)
            if e is None:
                d[sku] = {"sku": sku, "name": str(r.get("cnName") or r.get("enName") or ""),
                          "qty": qty}
            else:
                e["qty"] += qty
        # 拉入库流水(101907)
        flow = self._paginate("/oms/inventoryFlow/list",
                              lambda page, size: {"pageNum": page, "pageSize": size,
                                                  "businessType": "101907"})
        inbound = {}
        for f in flow:
            if not isinstance(f, dict):
                continue
            wh = str(f.get("warehouseCode") or "").strip()
            sku = self._sku(f)
            if not wh or not sku:
                continue
            wdate = str(f.get("warehouseDate") or "")[:10]
            q = to_int(f.get("goodsNum"))
            if not wdate or q <= 0:
                continue
            inbound.setdefault((wh, sku), []).append({"date": wdate, "qty": q})
        today = date.today().strftime("%Y-%m-%d")
        out = []
        for wh, m in by_wh.items():
            for sku, e in m.items():
                target = e["qty"]
                lifts = sorted(inbound.get((wh, sku), []),
                               key=lambda x: x["date"], reverse=True)
                acc = 0
                cover_date = None
                for li in lifts:
                    acc += li["qty"]
                    if acc >= target:
                        cover_date = li["date"]
                        break
                if not cover_date and lifts:
                    # 入库流水不足以覆盖当前在库（多为拆开件/初始库存）：
                    # 以最近一次入库日近似上架日，保证在库不错漏统计。
                    cover_date = lifts[0]["date"]
                if not cover_date:
                    # 完全无入库流水：视为初始/历史库存，按今天(库龄0)计入，
                    # 确保所有在库数量都被统计到。
                    cover_date = today
                age = (datetime.strptime(today, "%Y-%m-%d")
                       - datetime.strptime(cover_date, "%Y-%m-%d")).days
                out.append({
                    "wh": wh, "wh_name": self.wh_names.get(wh, wh), "sku": sku,
                    "name": e["name"], "qty": e["qty"],
                    "age_days": age, "shelf_date": cover_date, "batch": "",
                })
        return out, self._now()

    # ---------- 出库 ----------

    def _warehouse_codes(self):
        codes = set()
        rows = self._paginate("/oms/inventoryOverview/apiPage",
                              lambda page, size: {"pageNum": page, "pageSize": size})
        for r in rows:
            if isinstance(r, dict):
                c = str(r.get("warehouseCode") or "").strip()
                if c:
                    codes.add(c)
        return sorted(codes, key=sort_key)

    def _flow_rows(self, start, end):
        lo = start.strftime("%Y-%m-%d")
        hi = end.strftime("%Y-%m-%d")
        now = time.time()
        use_cache = (self._full_flow_cache is not None
                     and (now - self._full_flow_ts) < self._full_flow_ttl)
        if not use_cache:
            rows = []
            for otype in self.out_types:
                rows.extend(self._paginate("/oms/inventoryFlow/list",
                                           lambda page, size, t=otype: {
                                               "pageNum": page, "pageSize": size,
                                               "businessType": str(t)}))
            self._full_flow_cache = rows
            self._full_flow_ts = now
        else:
            rows = self._full_flow_cache
        out = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            wdate = str(r.get("warehouseDate") or "")[:10]
            if not (lo <= wdate <= hi):
                continue
            sku = self._sku(r)
            change = to_int(r.get("goodsNum"))
            if not sku or change >= 0:
                continue
            wh = str(r.get("warehouseCode") or "").strip()
            if not wh:
                continue
            out.append({"sku": sku, "wh": wh, "qty": -change, "date": wdate})
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
                for r in self._flow_rows(start, end)]

    def fetch_outbound(self, requested_date=None, requested_end=None):
        if requested_date:
            start = datetime.strptime(requested_date, "%Y-%m-%d").date()
            end = datetime.strptime(requested_end or requested_date, "%Y-%m-%d").date()
        else:
            start = end = self._default_out_date()
        raw = self._flow_rows(start, end)
        by_wh = {}
        for r in raw:
            d = by_wh.setdefault(r["wh"], {})
            d[r["sku"]] = d.get(r["sku"], 0) + r["qty"]
        points = [self._point(wh, [{"sku": k, "name": "", "qty": v}
                                   for k, v in sorted(m.items(), key=lambda x: -x[1])])
                  for wh, m in sorted(by_wh.items(), key=sort_key)]
        try:
            self.fill_empty_points(points, [(c, self.wh_names.get(c, c))
                                            for c in self._warehouse_codes()])
        except Exception:
            pass
        date_used = (start.strftime("%Y-%m-%d") if start == end
                     else f"{start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}")
        return points, self._now(), date_used
