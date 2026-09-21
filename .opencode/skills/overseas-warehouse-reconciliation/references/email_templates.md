# 异议邮件模板

## 使用说明

根据对账差异表的结果，选择对应的邮件模板。将 `[placeholder]` 替换为实际数据。
邮件语言根据仓库所在国家/沟通语言选择中英文。

---

## 模板 A: 综合异议邮件（含多项差异）

### 英文版

```
Subject: Discrepancy on [MONTH] Invoice — [WAREHOUSE_NAME] — [CUSTOMER_NAME]

Dear [WAREHOUSE_CONTACT],

Thank you for sending the [MONTH] invoice. After reviewing the bill against our agreed pricing schedule, we have identified the following discrepancies that require your attention:

1. DUPLICATE CHARGES
   - [FEE_TYPE] dated [DATE]: The same charge appears [N] times. Please remove the duplicate(s).
   - Amount in question: [CURRENCY] [AMOUNT]

2. STORAGE DAYS CALCULATION
   - Storage period: [INBOUND_DATE] to [OUTBOUND_DATE]
   - Billed days: [BILLED_DAYS] | Calculated days: [CALCULATED_DAYS]
   - Free storage days per our agreement: [FREE_DAYS] days (not deducted)
   - Amount in question: [CURRENCY] [AMOUNT]

3. UNIT PRICE MISMATCH
   - [FEE_TYPE]: Billed at [BILLED_PRICE] vs. agreed price of [AGREED_PRICE]
   - Amount in question: [CURRENCY] [AMOUNT]

4. UNQUOTED FEES
   - [FEE_NAME] at [CURRENCY] [AMOUNT]: This fee is not in our pricing schedule. Please clarify or remove.

Total disputed amount: [CURRENCY] [TOTAL_AMOUNT]

Please review and provide an updated invoice. If any of the above charges are correct, please share the supporting documentation so we can verify.

We value our partnership and look forward to resolving this promptly.

Best regards,
[SENDER_NAME]
[COMPANY_NAME]
```

### 中文版

```
主题：[月份] 账单对账差异 — [仓库名称] — [客户名称]

[仓库联系人] 您好，

收到贵司 [月份] 账单，经与我方报价表核对，发现以下差异，请协助核实：

1. 重复计费
   - [费用类型]（[日期]）：同一笔费用出现 [N] 次，请删除重复项
   - 涉及金额：[币种] [金额]

2. 仓租天数计算
   - 仓租周期：[入库日期] 至 [出库日期]
   - 账单天数：[账单天数] | 实际天数：[计算天数]
   - 约定免租期：[免租天数] 天（账单未扣除）
   - 涉及金额：[币种] [金额]

3. 单价差异
   - [费用类型]：账单单价 [账单单价]，约定单价 [约定单价]
   - 涉及金额：[币种] [金额]

4. 未报价费用
   - [费用名称]：[币种] [金额]，该费用不在我方报价表中，请说明或删除

异议总金额：[币种] [总金额]

请核实并提供更新后的账单。如以上费用确有依据，请提供相关凭证以便我方核实。

期待尽快解决，谢谢合作。

[发件人姓名]
[公司名称]
```

---

## 模板 B: 单项异议邮件（仅仓租天数）

### 英文版

```
Subject: Storage Fee Discrepancy on [MONTH] Invoice — [CUSTOMER_NAME]

Dear [WAREHOUSE_CONTACT],

We noticed a discrepancy in the storage fee on the [MONTH] invoice for [CUSTOMER_NAME].

According to our agreement, the first [FREE_DAYS] days of storage are free. However, the invoice appears to bill from day one. Additionally, the billed days ([BILLED_DAYS]) do not match the actual storage period ([INBOUND_DATE] to [OUTBOUND_DATE] = [ACTUAL_DAYS] days).

Please recalculate the storage fee and send an updated invoice.

Best regards,
[SENDER_NAME]
```

---

## 模板 C: 单项异议邮件（重复计费）

### 英文版

```
Subject: Duplicate Charge on [MONTH] Invoice — [CUSTOMER_NAME]

Dear [WAREHOUSE_CONTACT],

While reviewing the [MONTH] invoice, we found that the following charge was billed multiple times:

- Fee: [FEE_TYPE]
- Date: [DATE]
- Billed [N] times at [CURRENCY] [AMOUNT] each

Please remove the duplicate charges and issue a credit note or updated invoice.

Best regards,
[SENDER_NAME]
```

---

## 模板 D: 单项异议邮件（未报价费用）

### 英文版

```
Subject: Unrecognized Charge on [MONTH] Invoice — [CUSTOMER_NAME]

Dear [WAREHOUSE_CONTACT],

The [MONTH] invoice includes a charge that is not in our pricing schedule:

- Fee name: [FEE_NAME]
- Amount: [CURRENCY] [AMOUNT]
- Date: [DATE]

Could you please clarify what this charge is for? If it is a new fee, please provide the formal pricing so we can review and approve it before it is applied.

Best regards,
[SENDER_NAME]
```
