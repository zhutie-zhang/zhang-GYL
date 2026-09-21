# 海外仓管理看板

多海外仓统一管理工具：每天查看各仓**实时库存**和**前日出库**（按 SKU 跨仓汇总）。
网页看板，跑在本机 Windows 上。

## 快速启动

```powershell
python -m pip install -r requirements.txt
python app.py
```

浏览器打开 http://127.0.0.1:8000

启动方式（常用）：
- 本机运行：`python app.py`，浏览器访问 `http://127.0.0.1:8000`
- 局域网访问：把 `config.json` 里 `server.host` 改为 `0.0.0.0`，同事可通过 `http://你的IP:8000` 访问

## 功能

- **实时库存**：卡片展示各仓 SKU 数、库存总量、状态；表格按 SKU 横向对比各仓库存与合计，可搜索、点表头排序、导出 CSV
- **前日出库**：默认展示"各仓当地时间的前一天"（美西、美东、欧洲时区各自计算），也可用日期选择器查询任意一天；同样支持搜索、排序、导出 CSV
- **自动刷新**：默认每 5 分钟刷新一次，可手动"刷新数据"

## 目录结构

```
app.py            # Flask 服务 + 接口
config.json       # 所有配置（服务器、各海外仓）
adapters/
  base.py         # 适配器基类
  xlwms.py        # 领星 OMS 适配器（已接入，含签名算法）
  lecangs.py      # 乐歌海外仓适配器（含签名算法）
  yunwms.py       # 乐舱（易仓 WMS）SOAP 适配器
  anmei.py        # 安美海外仓适配器（OAuth + REST）
  aidelivery.py   # Aidelivery SOAP 适配器
  rest.py         # 通用 REST 适配器（对接简单 HTTP API）
  mock.py         # 模拟适配器（演示数据）
static/           # 前端页面
```

## 已接入：领星 OMS（xlwms）

一个领星账号下可有多个实体仓点。**每个仓点 = `config.json` 里一条记录**，通过 `wh_code_list` 指定只拉该仓数据，看板就会按仓点分别展示卡片和表格列。

## 分组：smartMYZ 与 实力派

看板页签按**组**展示，点进组内按仓点看明细：

| 组 | 组成 | 点进后 |
|---|---|---|
| `smartMYZ` | 领星 OMS 5 个仓点（CA1、HOU2062、Chicago WHS、SAV1、NJ1） | 按 5 个仓点分别看总数 |
| `实力派` | Aidelivery 两个账户（80196、80223） | 按 账户×仓点 分别看（如 `80196·NJ03`、`80223·CA003`） |

总览页把两组按 SKU 合并展示。`config.json` 的 `groups` 数组定义组，各仓库通过 `group` 字段归属；一个配置条目对应多个物理仓时（Aidelivery），适配器返回多个 `point`，每个 point 即一个仓点列/卡片。

## 已接入：Aidelivery（aidelivery）

Aidelivery 是 SOAP 接口（PublicService.asmx），响应为信封内嵌 JSON。适配器配置项：

| 配置项 | 说明 |
|---|---|
| `token` | API Token（必填，账户专属，与 customer_id 一一对应） |
| `customer_id` | 客户ID CustomerID（出库流水用，必填） |
| `stock_id` | 仓库 StockID；留空则自动拉全部仓 |
| `timezone` | "前一日"按此时区计算，默认 `America/New_York` |

每个账户 = `config.json` 里一条记录（token + customer_id 配对）。

数据来源与口径（实测踩坑）：
- **实时库存**：`GetStockList(Token)` 拉全部仓库 → 逐仓 `GetInventoryList(Token, StockID, SKU)`，按 SKU 汇总 `AvailableQty`
- **前日出库**：`GetInventoryLog(CustomerID, ..., StartTime, EndTime, ...)`，日期参数必须传 **Unix 秒级时间戳**（传 `2026-08-11` 这类格式会报"输入字符串的格式不正确"）；该接口**不需要 Token**；取 `changeQty<0`（网页端拣货下架）的绝对值按 `cwSkuCode` 汇总
- 有库存的仓实测为 StockID 9/10/14/16/19，其余返回"无库存记录"
- `GetOrderList`/`GetOrderInfo` 只返回订单头（无 SKU 行），不能用于出库明细
- 服务器网络不稳定，适配器内置 3 次重试；空 `StockID` 会误报 `Token Error!`，必须传真实仓库 ID

## 已接入：安美（anmei）

安美是 OAuth 授权模式，先换 token 再调用 REST 接口。配置项：

| 配置项 | 说明 |
|---|---|
| `client_id` / `client_secret` / `scope` / `redirect_uri` | OAuth 客户端参数，配合一次性 `code` 换 token |
| `code` | 浏览器授权后拿到的授权码（**只能换一次 token**） |
| `access_token` / `tenant` / `customer_id` | 换 token 后得到的凭据，**优先使用**，建议换到后填回配置（token 有效期约 180 天） |
| `inventory_qty_field` | 库存数量字段，默认 `productStockUsable`（可用库存） |
| `out_order_status` | 出库订单状态，默认 `5`（已完成） |
| `out_date_field` | 出库日期字段，默认 `completedTime`（扫描时间）；置空则信任服务端过滤 |

授权流程：浏览器打开 `https://openapi.wms-anmeiancang.com/connect/authorize/callback?response_type=code&client_id={client_id}&scope={scope}&redirect_uri={redirect_uri}&state={state}` → OMS 账号登录授权 → 回调地址带回 `code` → 适配器用 `code` 调 `/home/createToken` 换 token。

一个账户一条配置（`type: "anmei"`），账户下所有物理仓自动展开为一个仓点（按安美仓库列表的 `shortName` 命名）。

数据来源与口径：
- **实时库存**：`/api/v1/Warehouse/GetInventoryPageList`（分页），按 `productNo` 汇总 `productStockUsable`（可用库存）
- **前日出库**：`/api/v2/Order/GetOrderPageList`（分页，`orderStatus=5` 已完成），按 `productNo` 汇总 `deliverTotalqty`，本地按 `completedTime`（扫描时间）过滤日期
- 注意：安美日期过滤按服务端语义处理，若实测出库数与安美 OMS 对不上，调 `out_date_field` 或检查 `startDateTime`/`endDateTime` 过滤的时间字段

## 数据来源与口径（领星 OMS）

- **实时库存**：`/v1/integratedInventory/pageOpen`（stockType=0 产品库存），数量取 `productStockDtl.availableAmount`（可用库存），按 SKU 汇总
- **前日出库**：`/v1/integratedInventory/pageStockFlow`（库存流水），按 `orderTypeList` 过滤出库类型，把 `changeAmount`（负数）取绝对值后按 SKU 汇总

领星配置项：

| 配置项 | 说明 |
|---|---|
| `app_key` / `app_secret` | 平台密钥 |
| `order_type_list` | 出库类型编码：2-出库单，3-退件出库单（默认 `[2, 3]`） |
| `wh_code_list` | 该条目对应的实体仓编码，如 `["HOU2"]`；只填一个仓点，新增仓点就复制一条并改编码 |
| `timezone` | "前一日"按此时区计算（领星流水时间是中国时间，默认 `Asia/Shanghai`） |

注意（实测踩坑）：
- 领星库存流水接口的日期范围是**左闭右开**：查某天要传 `startTime=当天`、`endTime=次日`，否则返回空
- 加签算法：`data` 内字段按字典序升序 → `appKey + 排序后data JSON + reqTime` 按字典序拼接 → `authcode = HmacSHA256(密钥=appSecret)` 转 16 进制，GET 参数传递
- 库存接口只返回"近60天内有库存流水变动"的 SKU（接口默认窗口，无法关闭）；某仓点完全没数据时对应卡片显示 0

## 接入其他海外仓

在 `config.json` 的 `warehouses` 数组中新增一个对象，开启 `enabled: true`。

### 方式一：通用 REST 适配器（`type: "rest"`）

适用于鉴权简单（none/apikey/bearer/basic）的 HTTP 接口：

| 配置项 | 说明 |
|---|---|
| `base_url` | 海外仓 API 根地址，如 `https://open-api.xxx.com/v2` |
| `auth` | 鉴权方式：`none` / `apikey`（自定义 header）/ `bearer` / `basic` |
| `endpoints.inventory` | 查库存接口路径，如 `/inventory/list` |
| `endpoints.outbound` | 查出库接口路径，如 `/outbound/list` |
| `mapping.inventory` | 库存返回字段映射：`items`(列表路径) `sku` `name` `qty` |
| `mapping.outbound` | 出库返回字段映射：`items` `sku` `name` `qty` `date`(日期字段) `date_param`(请求参数) |

字段路径用点号分隔，如 `data.list` 表示取 JSON 中 `data.list` 数组。

两种出库日期处理方式：
1. 海外仓 API 支持按日期参数过滤 → 配置 `date_param`，如 `"date_param": "ship_date"`，系统会自动传 `ship_date=2026-08-11`
2. API 返回整个列表 → 配置 `date` 字段，系统在本地按该字段过滤

参考 `config.json` 中 `real-3pl-02` 停用模板。

### 方式二：自定义适配器

如果海外仓 API 太特殊（复杂签名、OAuth 等），参考 `adapters/xlwms.py` 写一个新适配器，在 `adapters/registry.py` 中注册，`config.json` 里 `type` 填对应名称。实现 `fetch_inventory()` 和 `fetch_outbound()` 两个方法即可。

## 安全提醒

- `config.json` 中保存的是**真实 API 密钥**，请勿提交到 git 或发给无关人员
- 若需接入新仓，直接新增一条记录；不用的仓把 `enabled` 改为 `false`

## 数据口径说明

- **前日出库** = 每个仓**当地时间**的前一天（各仓时区不同，默认按各自时区计算），看板会标注实际展示日期
- 出库结果默认缓存 30 分钟，库存缓存 5 分钟（见 `config.json` → `server.cache_ttl_*`），可手动"刷新数据"强制拉取
- 单个仓接口失败不影响其他仓，看板顶部会提示失败原因
