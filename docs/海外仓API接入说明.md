# 海外仓 API 接入说明

系统通过「适配器」模式统一对接五类海外仓平台。所有适配器继承自 `adapters/base.py` 的 `BaseAdapter`，只需实现两个方法即可接入：

- `fetch_inventory()` → `(points, fetched_at)`：拉取各仓库存，按仓拆成多个仓点
- `fetch_outbound(requested_date, requested_end=None)` → `(points, fetched_at, date_used)`：拉取出库，可按单日或区间
- `fetch_outbound_dated()`：返回带日期的原始出库流水行（供流水看板用，可选）

适配器由 `adapters/registry.py` 的 `build_adapter()` 按下发仓库配置里的 `type` 字段分发到对应实现。仓库配置保存在 `config.json`（新增自定义源在 `custom_sources.json`）。

---

## 访问方式统一入口

所有数据均通过以下 HTTP 接口对外提供（服务端口见 `config.json` 的 `server.port`）：

| 接口 | 说明 |
|------|------|
| `GET /api/warehouses` | 列出所有仓库/账号、分组、启用状态、自动刷新秒数 |
| `GET /api/inventory?force=1` | 拉取全部仓库库存（`force` 可强制刷新缓存） |
| `GET /api/outbound?date=YYYY-MM-DD` 或 `?start=&end=` | 拉取出库（按日期/区间，`force` 可强制刷新） |
| `GET /api/debug/aidelivery` | 调试实力派（Aidelivery）单平台库存+出库原始数据 |

**默认出库日期**：各平台按自己时区算"前一天"——领星/乐歌/乐舱/安美用 `Asia/Shanghai`，实力派用 `America/New_York`（可在配置 `timezone` 字段调整）。

---

## 1. 领星 OMS（xlwms）— 已接入 2 账号

- **适配器**: `adapters/xlwms.py` · `LingxingAdapter`
- **Base URL**: `https://api.xlwms.com/openapi/v1`
- **鉴权**: HMAC-SHA256 加签
  - `make_authcode(appKey, appSecret, data, reqTime)`：把 `data` 内字段按字典序（不区分大小写）升序排序，转紧凑 JSON；再把 `appKey`、排序后的 `data`、`reqTime` 三值按字典序拼接，用 `appSecret` 做 HmacSHA256 输出 16 进制；
  - 生成的 `authcode` 拼到 URL `?authcode=...`，POST body 传 `{appKey, data, reqTime}`
- **接口**:
  - 库存：`POST /integratedInventory/pageOpen`（`stockType=0`，分页 100）
  - 出库：`POST /integratedInventory/pageStockFlow`（`orderTypeList`：2=出库单、3=退件出库单；取 `changeAmount<0` 记出库）
- **配置项**: `app_key` / `app_secret` / `order_type_list` / `wh_name_map` / `wh_code_list`(可选限制仓库)
- **账号**:
  - `xlwms-smartmyz` — smartMYZ（CA1 / HOU2 / CHI60440 / SAV1 / NJ1）
  - `xlwms-smartyfj` — smartYFJ（CHI60440 / HOU2）

## 2. 乐歌（lecangs）— 已接入 2 账号

- **适配器**: `adapters/lecangs.py` · `LecangsAdapter`
- **Base URL**: `https://app.lecangs.com/api`
- **鉴权**: 请求头传 `timestamp`(毫秒) / `accessKey` / `sign`
  - `sign = SHA256( 按 key 排序拼接 "k=v&..." 去掉末尾 & + appSecret )`
- **接口**:
  - 库存：`POST /oms/inventoryOverview/apiPage`（可用数量取 `uesNum` = goodsNum 扣减冻结）
  - 出库：`POST /oms/inventoryFlow/list`（按 `businessType` 拉全量后本地按日期过滤）
- **配置项**: `app_key` / `app_secret` / `out_type_list`(默认 101901 出库单) / `wh_name_map`
- **账号**: `lecangs-yfj`（乐歌YFJ）、`lecangs-myz`（乐歌MYZ）

## 3. 乐舱（yunwms / 云递）— 已接入 2 账号（SOAP）

- **适配器**: `adapters/yunwms.py` · `YunWmsAdapter`
- **Base URL**: `https://lc.yunwms.com`，端点 `POST /default/svc/web-service`
- **鉴权**: SOAP 信封调用 `callService`，公共参数 `service` / `appToken` / `appKey` / `paramsJson`(JSON 串)；响应解析 `<response>...</response>` 内 JSON，`ask` 须为 `Success`
- **接口**:
  - 仓库：`getWarehouse`
  - 库存：`getProductInventory`（可用数量取 `sellable`）
  - 出库：`getOrderList`（`order_status` 默认 D 已发货；日期须带时间分量，`ship_date_to` 用次日 00:00:00 实现闭区间）
- **配置项**: `app_token` / `app_key` / `order_status_list` / `wh_name_map` / `wh_code_list`
- **账号**: `lecang-myz`（乐舱MYZ）、`lecang-yfj`（乐舱YFJ）

## 4. 安得力 / 实力派（aidelivery）— 已接入 2 账号（SOAP .asmx）

- **适配器**: `adapters/aidelivery.py` · `AideliveryAdapter`
- **Base URL**: `http://www.aideliveryinc.com/WebService/PublicService.asmx`（命名空间 `http://tempuri.org/`）
- **鉴权**: 库存类方法请求体带 `<Token>`；出库 `GetInventoryLog` **无需 Token**，需 `CustomerID`
- **接口**:
  - 库存：`GetStockList` → `GetInventoryList(StockID, SKU)`（`stock_id` 留空则自动拉全部仓并并发汇总）
  - 出库：`GetInventoryLog(CustomerID, GoodsCode, StockCode, StartTime, EndTime, PageIndex, PageSize)`，日期须为 **Unix 秒级时间戳**，`changeQty<0` 记出库
- **配置项**: `token` / `customer_id` / `stock_id`(留空自动全仓) / `mapping`(sku/qty 字段可覆盖)
- **账号**: `aidelivery-80196`、`aidelivery-80223`（实力派）

## 5. 安美（anmei）— 已接入 1 账号（OAuth2）

- **适配器**: `adapters/anmei.py` · `AnmeiAdapter`
- **Base URL**: `https://openapi.wms-anmeiancang.com`
- **鉴权流程**:
  1. 浏览器打开授权链接换取一次性 `code`；
  2. `POST /home/createToken` 用 `client_id` / `client_secret` / `scope` / `redirect_uri` + `code` 换 `accessToken` / `Tenant` / `CustomerId`（code 只能用一次，token 约 180 天有效，建议回填到配置）；
  3. 之后所有请求头带 `Authorization: bearer {token}` + `Tenant` + `CustomerId`
- **接口**:
  - 仓库：`GET /api/v1/Warehouse/GetWarehouseList`
  - 库存：`POST /api/v1/Warehouse/GetInventoryPageList`（默认量字段 `productStockUsable`）
  - 出库：`POST /api/v2/Order/GetOrderPageList`（`orderStatus=5` 已完成，日期字段默认 `completedTime`）
- **配置项**: `client_id/client_secret/scope/redirect_uri` + `access_token/tenant/customer_id`
- **账号**: `anmei-01`（安美）

---

## 测试连接 / 排查

系统**没有**为 5 类平台单独提供"测试连接"按钮接口；接入验证方式如下：

1. **通用自检**（最常用）：直接请求数据接口，观察是否有数据返回及接口报错
   ```
   # 强制刷新库存（跳过缓存）
   curl "http://127.0.0.1:8000/api/inventory?force=1"
   # 查某天出库
   curl "http://127.0.0.1:8000/api/outbound?date=2026-08-27"
   ```
   返回里每个仓库有 `status`：`ok` 表示成功；出错会返回该适配器抛出的异常信息（鉴权失败、业务错误码、HTTP 错误等）。

2. **实力派专项调试接口**：`GET /api/debug/aidelivery`，返回该平台各账号的库存与出库原始行（前 50 条）及点明细，`xxx_error` 字段显示具体报错。

3. **自定义数据源专用测试**（`adapters/custom.py`）：
   ```
   POST /api/custom_sources/<source_id>/test
   ```
   对自定义 HTTP 源分别测试库存/出库两个 URL，返回 `{inventory:{ok,count}, outbound:{ok,count}}`。**注意：该接口只适用于 type=custom 的自定义数据源**，不适用于上表 5 类平台。

4. **后端控制台日志**（`server.err.log` / `server.out.log`）：适配器异常默认打印 traceback，可按仓库 id 定位。

---

## 通用型（未启用，作模板）

- `adapters/rest.py` — 通用 REST 模板：通过 `auth`(none/apikey/bearer/basic) + `endpoints` + `mapping`(字段映射) 对接任意 HTTP API。
- `adapters/custom.py` — 任意自定义 HTTP API：可在「自定义数据源」界面配置 URL / 请求方法 / 鉴权 / 字段路径，支持按仓库维度拆点。

这两类目前处于停用/演示状态（`config.json` 中 `enabled:false`）。
