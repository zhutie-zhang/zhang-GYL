# 海外仓账单对账技能 (Overseas Warehouse Reconciliation Skill)

> WorkBuddy Skill — 自动化解析海外仓杂乱账单，对照报价表核对单价，识别重复计费、错算仓租天数、不合理杂费等隐性扣费，输出对账差异表并生成异议邮件。

## 解决什么问题

海外仓账单格式每家仓库都不一样，费用项目杂乱，人工对账耗时且容易遗漏隐性扣费。本技能通过自动化解析账单、对照报价表逐项核对，快速识别差异并生成对账报告和异议邮件。

## 核心能力

| 能力 | 说明 |
|------|------|
| 账单解析 | 支持 Excel (.xlsx/.xls) 和 PDF 格式，自动识别表头、提取费用明细 |
| 报价核对 | 逐行比对账单单价与报价表，标记价格差异 |
| 异常检测 | 13 条规则自动检测重复计费、仓租天数错误、免租期未扣、未报价费用等 |
| 报告输出 | 生成带颜色标记的 Excel 对账差异表（3 Sheet） |
| 异议邮件 | 根据差异类型自动生成中英文异议邮件 |
| 月度统计 | 按费用类型汇总，统计每个客户/仓库的月度成本 |

## 技能结构

```
overseas-warehouse-reconciliation/
├── SKILL.md                          # 主技能文件，定义 6 步对账工作流程
├── references/
│   ├── fee_types.md                  # 7 大标准费用类型 + 11 种杂费，含中英文别名映射表
│   ├── common_errors.md              # 13 条对账检测规则（R01-R13），按高/中/低三级严重度分类
│   └── email_templates.md            # 4 套中英文异议邮件模板（综合/仓租/重复计费/未报价费用）
├── scripts/
│   ├── parse_bill.py                 # Excel/PDF 账单自动解析，识别表头、提取费用明细、标准化字段
│   ├── reconcile.py                  # 对账引擎，13 条规则自动检测重复计费、仓租错误、单价差异等
│   └── generate_report.py            # 生成 Excel 差异表（3 Sheet）+ 文本格式摘要
└── README.md                         # 本文件
```

## 13 条检测规则

| 规则 | 说明 | 严重度 |
|------|------|--------|
| R01 | 重复计费（完全重复的行） | 高 |
| R02 | 包含关系重复（拆柜含打托却单独收费） | 高 |
| R03 | 仓租天数计算错误 | 高 |
| R04 | 免租期未扣除 | 高 |
| R05 | 周末计费（约定不计费但收了费） | 中 |
| R06 | 单价高于报价 | 高 |
| R07 | 汇率错误 | 中 |
| R08 | 阶梯报价未按实际量降档 | 中 |
| R09 | 件数/箱数虚高 | 高 |
| R10 | CBM 取整方式不一致 | 低 |
| R11 | 未在报价表中的费用 | 中 |
| R12 | 杂费占比超过 10% | 中 |
| R13 | 费用名称模糊无法识别 | 低 |

## 使用方式

### 在 WorkBuddy 中使用

收到海外仓账单时，直接把账单文件和报价表发给 WorkBuddy，会自动触发此技能：

1. 用 `parse_bill.py` 解析账单
2. 用 `reconcile.py` 跑 13 条检测规则
3. 用 `generate_report.py` 生成 Excel 差异表
4. 参考邮件模板生成异议邮件

### 独立运行脚本

```bash
# 安装依赖
pip install openpyxl pdfplumber

# Step 1: 解析账单
python3 scripts/parse_bill.py <账单文件> --output bill.json --quote <报价表文件>

# Step 2: 对账引擎
python3 scripts/reconcile.py bill.json quote.json --output report.json

# Step 3: 生成报告
python3 scripts/generate_report.py report.json --output 对账差异表.xlsx
```

### 输出示例

Excel 对账差异表包含 3 个 Sheet：

1. **对账摘要** — 总金额、问题数、预计多收金额、费用类型分布
2. **差异明细** — 逐条列出所有问题，按严重度颜色标记（红=高/黄=中/绿=低）
3. **原始账单** — 账单来源信息

## 字符归一化

脚本内置 `normalize_key()` 函数，自动处理以下字符差异：

- U+2011 (non-breaking hyphen) / U+2010 / U+2012–U+2015 / U+2212 → ASCII `-`
- BOM / 零宽字符 → 去除
- 全角空格 → 普通空格
- NFKC 归一化 + casefold

这确保不同来源的账单和报价表即使连字符写法不同也能正确匹配。

## 环境要求

- Python 3.10+
- 依赖库：`openpyxl`、`pdfplumber`

## 适用场景

- 跨境电商 / 外贸企业对海外仓账单进行自动化对账
- 核对仓租 / 拆柜 / 打托 / 贴标 / 处理费 / 退货费等费用
- 发现账单金额异常，需要生成异议邮件与仓库方沟通
- 统计客户海外仓月度成本

## License

MIT
