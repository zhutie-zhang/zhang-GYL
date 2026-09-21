# 海外仓费用类型参考

## 标准费用分类

### 1. 拆柜费 (Devanning / Unloading Fee)
- **别名**: 拆箱费, 卸柜费, Devanning, Unloading, Deconsolidation, Strip Cargo
- **计费单位**: per carton (按箱), per CBM (按方), per pallet (按托), per shipment (按票)
- **计费逻辑**: 货物从集装箱中卸出并拆分到托盘的费用
- **常见错误**: 重复计费（已含在处理费中却单独列出）；按CBM计费时体积取整方式不一致

### 2. 打托费 (Palletizing Fee)
- **别名**: 上托, 托盘费, 组托, Palletizing, Pallet Build, Pallet Load, Palletization
- **计费单位**: per pallet (按托)
- **计费逻辑**: 将散件货物码放到托盘上并缠绕膜固定的费用
- **常见错误**: 托数计算错误（实际托数与账单托数不符）；同时收打托费和拆柜费中的打托部分

### 3. 贴标费 (Labeling Fee)
- **别名**: 贴条码, 换标, 贴FBA标, Labeling, Stickering, Relabeling, FBA Label
- **计费单位**: per piece (按件), per carton (按箱)
- **计费逻辑**: 在产品或外箱上贴标签的费用
- **常见错误**: 件数虚高；贴标+换标重复收费；已含在处理费中却单独列出

### 4. 仓租 (Storage / Warehouse Rent)
- **别名**: 仓储费, 仓租费, 库存费, Storage, Warehouse Fee, Storage Rent, Warehousing
- **计费单位**: per CBM/day (按方/天), per pallet/day (按托/天), per sqft/day (按平方英尺/天)
- **计费逻辑**: 货物在仓库存放产生的按天费用
- **计算公式**: 仓租 = 体积(CBM) 或 托数 × 日费率 × 天数
- **常见错误**:
  - 天数计算错误（入库日和出库日均计费、周末/节假日也计费）
  - 免租期未扣除（报价中约定前N天免租但账单未执行）
  - 计费基数错误（CBM与托数混用）
  - 按出库时的总体积而非实际存放体积计费

### 5. 处理费 (Handling / Processing Fee)
- **别名**: 操作费, 进出仓处理, 收货费, Handling, Inbound Handling, Outbound Handling, Processing
- **计费单位**: per carton (按箱), per order (按单), per CBM (按方), per shipment (按票)
- **计费逻辑**: 货物进出仓库时的操作处理费用
- **常见错误**: 拆柜+处理+收货三项重叠收费；入仓和出仓分别收费但报价中只约定一方

### 6. 退货费 (Return Fee)
- **别名**: 退件处理费, 退货处理, Return Processing, Return Handling, RMA Fee
- **计费单位**: per piece (按件), per return (按次)
- **计费逻辑**: 处理客户退回商品的费用
- **常见错误**: 退货费+处理费重复；退货运费未在报价中但被收取

### 7. 其他常见杂费
| 费用名称 | 别名 | 说明 | 是否常见 |
|---------|------|------|---------|
| 分拣费 | Sorting, Pick & Pack | 按订单分拣货物 | 常见 |
| 装车费 | Loading, Outbound Loading | 装车出库费用 | 常见 |
| 快递费 | Shipping, Last Mile, Outbound Shipping | 尾程派送费 | 常见 |
| 上架费 | Putaway, Shelving | 货物上架费用 | 较常见 |
| 盘点费 | Inventory Check, Stocktake | 库存盘点费用 | 较少见 |
| 换箱费 | Re-boxing, Carton Change | 更换外箱费用 | 较少见 |
| 缠膜费 | Wrapping, Stretch Wrap | 缠绕膜费用 | 较少见 |
| 叉车费 | Forklift, Forklift Handling | 叉车操作费用 | 较少见 |
| 旺季附加费 | Peak Season Surcharge | 旺季额外收费 | 季节性 |
| 燃油附加费 | Fuel Surcharge | 燃油附加费 | 较少见 |
| 文件费 | Documentation Fee, Doc Fee | 文件处理费 | 较少见 |

## 费用匹配规则

当账单中的费用名称无法直接匹配到上述标准类型时，按以下规则进行模糊匹配：

1. **关键词匹配**: 提取费用名称中的关键词，与各类型的"别名"列表进行比对
2. **语言无关**: 同时支持中英文关键词匹配
3. **上下文推断**: 根据费用金额、数量单位等上下文信息辅助判断类型
4. **未匹配标记**: 无法匹配的费用标记为"未识别费用"，需人工确认

## 报价表标准格式

报价表应包含以下字段（供对账引擎使用）：

| 字段 | 说明 | 示例 |
|------|------|------|
| fee_type | 费用类型（标准名称） | 仓租 |
| fee_name | 报价表中的原始名称 | Storage Fee |
| unit | 计费单位 | CBM/day |
| unit_price | 单价 | 0.15 |
| currency | 币种 | USD |
| min_charge | 最低收费 | 10.00 |
| free_days | 免租天数（仅仓租） | 7 |
| effective_date | 生效日期 | 2025-01-01 |
| expiry_date | 失效日期 | 2025-12-31 |
| remark | 备注 | 周末不计费 |
