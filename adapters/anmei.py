import json
import time
from datetime import datetime, timedelta

import requests

from adapters.base import BaseAdapter

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    _HAS_CRYPTO = True
except Exception:  # pragma: no cover
    _HAS_CRYPTO = False


def _aes_cbc_encrypt(plaintext: bytes, key: bytes, iv: bytes) -> str:
    """AES-CBC + PKCS7 加密，返回 base64 字符串（与安美 OMS 前端 CryptoJS 一致）。"""
    bs = 16
    pad_len = bs - (len(plaintext) % bs)
    padded = plaintext + bytes([pad_len]) * pad_len
    enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ct = enc.update(padded) + enc.finalize()
    import base64
    return base64.b64encode(ct).decode("ascii")


def to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


class AnmeiAdapter(BaseAdapter):
    """安美海外仓（openapi.wms-anmeiancang.com）适配器。

    config 关键项：
      client_id / client_secret / scope / redirect_uri    OAuth 客户端参数（换 token 用）
      code                                                一次性授权码（可与上面的参数换 token）
      access_token / tenant / customer_id                  直接可用的凭据（优先使用）
      inventory_qty_field    库存数量字段，默认 productStockUsable（可用库存）
      out_order_status       出库订单状态，默认 5（已完成）
      out_date_field         出库日期字段，默认 completedTime（扫描时间）；
                              置空则信任服务端 startDateTime/endDateTime 过滤
      timeout                超时秒数

    鉴权流程：
      1) 浏览器打开授权链接换取 code；
      2) POST /home/createToken 用 code 换 accessToken/Tenant/CustomerId
         （code 只能使用一次，token 有效期约 180 天，建议把 token 填回配置）；
      3) 之后所有接口请求头带 Authorization: bearer {token}、Tenant、CustomerId。

    接口：
      库存：/api/v1/Warehouse/GetInventoryPageList（分页，可用数量）
      出库：/api/v2/Order/GetOrderPageList（分页，orderStatus=5 已完成）
      仓库：/api/v1/Warehouse/GetWarehouseList（账户下所有仓库，一个仓库一个仓点）
    """

    DEFAULT_BASE = "https://openapi.wms-anmeiancang.com"

    def __init__(self, cfg):
        super().__init__(cfg)
        self.base_url = (cfg.get("base_url") or self.DEFAULT_BASE).rstrip("/")
        self.timeout = int(cfg.get("timeout", 20))
        self.inv_qty_field = cfg.get("inventory_qty_field", "productStockUsable")
        self.out_status = int(cfg.get("out_order_status", 5))
        self.out_date_field = cfg.get("out_date_field", "completedTime")
        self._token_scheme = cfg.get("auth_scheme", "bearer")
        self.access_token = cfg.get("access_token") or ""
        self.tenant = cfg.get("tenant") or ""
        self.customer_id = cfg.get("customer_id") or ""
        self.code = cfg.get("code") or ""
        self._session = requests.Session()
        self._wh_cache = None
        self._wh_cache_at = 0.0
        self._inv_whs = None
        self._inv_whs_at = 0.0
        # 安美海外仓新开放平台(yc-client.anestcang.com)库龄专用
        self.age_base = (cfg.get("age_base_url")
                         or "https://api.yc-client.anestcang.com").rstrip("/")
        self.age_token = cfg.get("age_access_token") or ""
        self.age_app_key = cfg.get("age_app_key") or ""
        self.age_app_secret = cfg.get("age_app_secret") or ""
        self.age_whs = cfg.get("age_warehouse_codes") or []
        self._age_whs_at = 0.0
        self._age_whs = None
        self._age_token_at = 0.0
        # 安美 OMS 库龄专用（账号密码服务端登录）
        self.oms_base = (cfg.get("oms_base")
                         or "https://api-anmeiancang.com").rstrip("/")
        self.oms_username = cfg.get("oms_username") or ""
        self.oms_password = cfg.get("oms_password") or ""
        self._oms_token = None
        self._oms_token_at = 0.0
        self._oms_session = requests.Session()

    # ---------- 鉴权 ----------

    def _ensure_token(self):
        if self.access_token:
            return
        if not self.code:
            raise RuntimeError("安美缺少凭据：请配置 access_token/tenant/customer_id，"
                               "或用 client_id/client_secret/scope/redirect_uri + code 换 token")
        body = {
            "clientId": self.cfg.get("client_id", ""),
            "clientSecret": self.cfg.get("client_secret", ""),
            "scope": self.cfg.get("scope", ""),
            "redirecturi": self.cfg.get("redirect_uri", ""),
            "code": self.code,
            "custom": self.cfg.get("custom", ""),
        }
        resp = requests.post(f"{self.base_url}/home/createToken", json=body,
                             timeout=self.timeout)
        if resp.status_code >= 400:
            raise RuntimeError(f"安美换 token 失败 HTTP {resp.status_code}: {resp.text[:200]}")
        j = resp.json()
        data = (j.get("data") or {})
        if not j.get("success") or not data.get("accessToken"):
            raise RuntimeError(f"安美换 token 业务失败: {resp.text[:300]}")
        self.access_token = data["accessToken"]
        self.tenant = data.get("tenant") or ""
        self.customer_id = data.get("customerId") or ""

    def _headers(self):
        self._ensure_token()
        h = {"Authorization": f"{self._token_scheme} {self.access_token}",
             "Content-Type": "application/json"}
        if self.tenant:
            h["Tenant"] = self.tenant
        if self.customer_id:
            h["CustomerId"] = self.customer_id
        return h

    def _call(self, path, body=None, method="POST"):
        last = None
        for attempt in range(5):
            headers = self._headers()
            try:
                if method == "GET":
                    resp = self._session.get(f"{self.base_url}{path}", headers=headers,
                                             timeout=self.timeout)
                else:
                    resp = self._session.post(f"{self.base_url}{path}", json=body or {},
                                              headers=headers, timeout=self.timeout)
                if resp.status_code >= 400:
                    last = RuntimeError(f"安美 HTTP {resp.status_code}: {resp.text[:200]}")
                    time.sleep(2 * (attempt + 1))
                    continue
                j = resp.json()
                if not j.get("isSuccess") or str(j.get("code")) not in ("200",):
                    raise RuntimeError(f"安美接口业务错误 code={j.get('code')}: {j.get('message')}")
                return j.get("data") or {}
            except (requests.RequestException, json.JSONDecodeError, ValueError) as e:
                last = e
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"安美请求失败（已重试5次）: {last}")

    def _paginate(self, path, body_factory, page_size=100):
        rows = []
        page = 1
        total = None
        while total is None or len(rows) < total:
            body = body_factory(page, page_size)
            data = self._call(path, body)
            items = data.get("items") or []
            total = to_int(data.get("totalCount"))
            rows.extend(items)
            if not items or len(rows) >= total or page > 500:
                break
            page += 1
        return rows

    # ---------- 仓库 ----------

    def _warehouses(self):
        now = time.time()
        if self._wh_cache is None or now - self._wh_cache_at > 3600:
            data = self._call("/api/v1/Warehouse/GetWarehouseList", method="GET")
            self._wh_cache = data if isinstance(data, list) else []
            self._wh_cache_at = now
        return self._wh_cache

    def _wh_name(self, wh_id):
        try:
            whs = self._warehouses()
        except Exception:
            whs = []
        for w in whs:
            if str(w.get("id")) == str(wh_id):
                return w.get("shortName") or w.get("name") or str(wh_id)
        return str(wh_id)

    def _inventory_whs(self):
        """有库存的仓点列表（与库存面板同源，作为出库补齐的依据）。"""
        now = time.time()
        if self._inv_whs is None or now - self._inv_whs_at > 300:
            whs = {}
            for it in self._paginate(
                    "/api/v1/Warehouse/GetInventoryPageList",
                    lambda page, size: {"pageIndex": page, "pageSize": size}):
                if not isinstance(it, dict):
                    continue
                wh = str(it.get("warehouseId") or "").strip()
                if wh:
                    whs[wh] = self._wh_name(wh)
            self._inv_whs = list(whs.items())
            self._inv_whs_at = now
        return self._inv_whs

    # ---------- 库存 ----------

    def fetch_inventory(self):
        rows_raw = self._paginate(
            "/api/v1/Warehouse/GetInventoryPageList",
            lambda page, size: {"pageIndex": page, "pageSize": size})
        by_wh = {}
        for it in rows_raw:
            if not isinstance(it, dict):
                continue
            pn = str(it.get("productNo") or "").strip()
            if not pn:
                continue
            wh = str(it.get("warehouseId") or "").strip()
            if not wh:
                continue
            qty = to_int(it.get(self.inv_qty_field))
            d = by_wh.setdefault(wh, {})
            d[pn] = d.get(pn, 0) + qty
        points = [{"id": wh, "name": self._wh_name(wh),
                   "rows": [{"sku": k, "name": "", "qty": v}
                            for k, v in sorted(m.items(), key=lambda x: -x[1])]}
                  for wh, m in by_wh.items()]
        points.sort(key=lambda p: p["name"])
        if not points:
            return self.single_point([]), self._now()
        return points, self._now()

    # ---------- 库龄(OMS 系统账号密码服务端登录) ----------

    def _oms_login(self):
        """安美 OMS 登录（账号密码 AES 加密），返回 Bearer token。缓存约 1 小时。"""
        now = time.time()
        if self._oms_token and now - self._oms_token_at < 3600:
            return self._oms_token
        if not self.oms_username or not self.oms_password:
            raise RuntimeError("安美OMS库龄缺少凭据：请在 config 的 anmei-01 填 oms_username + oms_password")
        if not _HAS_CRYPTO:
            raise RuntimeError("安美OMS库龄需要 pycryptodome/cryptography 库支持 AES 登录")
        key = b"0123456789abcdef"
        enc_pwd = _aes_cbc_encrypt(json.dumps(self.oms_password).encode("utf-8"), key, key)
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
            "Origin": "https://oms-anmeiancang.com",
            "Referer": "https://oms-anmeiancang.com/",
            "System": "OMS",
        }
        body = {"userName": self.oms_username, "password": enc_pwd}
        resp = self._session.post(f"{self.oms_base}/auth/api/Auth/CoustomerValidate",
                                  json=body, headers=headers, timeout=self.timeout)
        if resp.status_code >= 400:
            raise RuntimeError(f"安美OMS登录失败 HTTP {resp.status_code}: {resp.text[:200]}")
        j = resp.json()
        data = j.get("data") or {}
        if not j.get("success") or not data.get("access_token"):
            raise RuntimeError(f"安美OMS登录业务失败: {resp.text[:300]}")
        self._oms_token = data["access_token"]
        self._oms_token_at = now
        return self._oms_token

    def _oms_age_headers(self):
        token = self._oms_login()
        h = {
            "Authorization": "Bearer " + token,
            "System": "OMS",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
            "Origin": "https://oms-anmeiancang.com",
            "Referer": "https://oms-anmeiancang.com/",
        }
        if self.tenant:
            h["Tenant"] = self.tenant
        if self.customer_id:
            h["CustomerId"] = self.customer_id
        return h

    def _oms_age_call(self, body, headers):
        """带 token 失效重试的 OMS 接口调用。"""
        try:
            resp = self._session.post(
                f"{self.oms_base}/oms/api/v1/Stock/Stock/GetListByPage",
                json=body, headers=headers, timeout=self.timeout)
        except requests.RequestException as e:
            raise RuntimeError(f"安美OMS库龄请求失败: {e}") from e
        if resp.status_code >= 400:
            raise RuntimeError(f"安美OMS库龄 HTTP {resp.status_code}: {resp.text[:200]}")
        j = resp.json()
        if not j.get("success"):
            # token 失效则重新登录重试一次
            if str(j.get("code")) == "WBS00012":
                self._oms_token = None
                self._oms_token_at = 0.0
                headers = self._oms_age_headers()
                resp = self._session.post(
                    f"{self.oms_base}/oms/api/v1/Stock/Stock/GetListByPage",
                    json=body, headers=headers, timeout=self.timeout)
                j = resp.json()
            if not j.get("success"):
                raise RuntimeError(f"安美OMS库龄业务失败 code={j.get('code')} msg={j.get('message')}")
        return j.get("data") or {}

    def fetch_inventory_age(self, statistic_date=None):
        """安美库龄：OMS 系统 GetListByPage（逐批次 stockAgeList，含上架时间/数量/库龄天数）。"""
        headers = self._oms_age_headers()
        out = []
        page = 1
        page_size = 100
        while True:
            body = {"pageIndex": page, "pageSize": page_size}
            data = self._oms_age_call(body, headers)
            items = data.get("list") or []
            total = to_int(data.get("total"))
            for it in items:
                if not isinstance(it, dict):
                    continue
                sku = str(it.get("productNo") or "").strip()
                wh_name = str(it.get("warehouseName") or "").strip() or str(it.get("warehouseId") or "")
                name = str(it.get("productNameCn") or it.get("productNameEn") or "").strip()
                for b in (it.get("stockAgeList") or []):
                    if not isinstance(b, dict):
                        continue
                    qty = to_int(b.get("qty"))
                    if not sku or qty <= 0:
                        continue
                    out.append({
                        "wh": wh_name or str(it.get("warehouseId") or ""),
                        "wh_name": wh_name or str(it.get("warehouseId") or ""),
                        "sku": sku,
                        "name": name or sku,
                        "qty": qty,
                        "age_days": to_int(b.get("day")),
                        "shelf_date": str(b.get("stockInTime") or "")[:10],
                        "batch": str(b.get("containerNo") or ""),
                        "statistic_date": "",
                    })
            if not items or not total or page * page_size >= total or page > 500:
                break
            page += 1
        return out, self._now()

    # ---------- 出库 ----------

    def _out_req_range(self, start, end):
        """返回 (请求窗口 lo, hi)。安美 OMS 的 startDateTime/endDateTime 按 createdTime
        （下单时间）过滤，而系统按 completedTime（完成时间）归日。直接传 lo/hi 会在单日
        查询时拿不到已完成的单，range 查询也会漏掉"下单早于窗口、完成在窗口内"的行。
        因此请求窗口向过去放宽 lookback 天、向未来放宽 1 天，再由调用方按 completedTime
        严格过滤到目标区间。"""
        back = int(self.cfg.get("out_lookback_days", 7))
        req_lo = (start - timedelta(days=back)).strftime("%Y-%m-%d")
        req_hi = (end + timedelta(days=1)).strftime("%Y-%m-%d")
        return req_lo, req_hi

    def fetch_outbound(self, requested_date=None, requested_end=None):
        if requested_date:
            start = datetime.strptime(requested_date, "%Y-%m-%d").date()
            end = datetime.strptime(requested_end or requested_date, "%Y-%m-%d").date()
        else:
            start = end = self._default_out_date()
        lo = start.strftime("%Y-%m-%d")
        hi = end.strftime("%Y-%m-%d")
        req_lo, req_hi = self._out_req_range(start, end)

        raw = self._paginate(
            "/api/v2/Order/GetOrderPageList",
            lambda page, size: {"pageIndex": page, "pageSize": size,
                                "orderStatus": self.out_status,
                                "startDateTime": req_lo, "endDateTime": req_hi})

        by_wh = {}
        for it in raw:
            if not isinstance(it, dict):
                continue
            if self.out_date_field:
                d = str(it.get(self.out_date_field) or "")[:10]
                if not (lo <= d <= hi):
                    continue
            sku = str(it.get("productNo") or it.get("sku") or "").strip()
            qty = to_int(it.get("deliverTotalqty"))
            if not sku or qty <= 0:
                continue
            wh = str(it.get("wareHouseId") or it.get("warehouseId") or "")
            if not wh:
                continue
            d = by_wh.setdefault(wh, {})
            d[sku] = d.get(sku, 0) + qty

        points = [{"id": wh, "name": self._wh_name(wh),
                   "rows": [{"sku": k, "name": "", "qty": v}
                            for k, v in sorted(m.items(), key=lambda x: -x[1])]}
                  for wh, m in by_wh.items()]
        points.sort(key=lambda p: p["name"])
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
        lo = start.strftime("%Y-%m-%d")
        hi = end.strftime("%Y-%m-%d")
        req_lo, req_hi = self._out_req_range(start, end)
        raw = self._paginate(
            "/api/v2/Order/GetOrderPageList",
            lambda page, size: {"pageIndex": page, "pageSize": size,
                                "orderStatus": self.out_status,
                                "startDateTime": req_lo, "endDateTime": req_hi})
        out = []
        for it in raw:
            if not isinstance(it, dict):
                continue
            if self.out_date_field:
                d = str(it.get(self.out_date_field) or "")[:10]
                if not (lo <= d <= hi):
                    continue
            else:
                d = lo
            sku = str(it.get("productNo") or it.get("sku") or "").strip()
            qty = to_int(it.get("deliverTotalqty"))
            if not sku or qty <= 0:
                continue
            wh = str(it.get("wareHouseId") or it.get("warehouseId") or "")
            if not wh:
                continue
            out.append({"sku": sku, "name": "", "qty": qty, "date": d, "wh": wh})
        return out
