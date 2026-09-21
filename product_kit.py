"""组合产品映射模块。

存储：product_map.json，结构 {产品SKU: {"name": 名称, "components": [子SKU...]}}

- components 非空 = 组合产品
- components 为空 = 非组合产品（独立 SKU 登记）

显示与统计规则：
- 以组合 SKU 显示为主
- 成套数 = min(各子SKU数量)
- 不成套的子SKU 单独列出（数量 = 子SKU数量 - 成套数）
"""
import json
import os

DEFAULT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "product_map.json")

# 表头关键词识别（Excel 导入时列自动识别）
COMBO_KEYS = ("组合", "父", "成套", "套件", "套装", "母件")
SUB_KEYS = ("子", "单品", "散件", "零件", "配件", "内件")
NAME_KEYS = ("名称", "品名", "产品名")
SKU_KEYS = ("sku", "编码", "货号", "产品", "商品")


def _pick_col(headers, keys, exclude=()):
    for i, h in enumerate(headers):
        if i in exclude:
            continue
        if any(k in h for k in keys):
            return i, headers[i]
    return None, None


def import_kit_excel(path, kitmap, combo_col=None, sub_col=None, name_col=None):
    """从 Excel/CSV 长表导入组合映射。每行一个子SKU，组合SKU相同。
    已存在的组合SKU自动跳过，只导入新数据。
    返回 (新增数量, 跳过数量)。"""
    import pandas as pd

    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".csv":
            df = pd.read_csv(path, dtype=str)
        else:
            df = pd.read_excel(path, dtype=str)
    except Exception as e:
        raise ValueError(f"文件读取失败: {e}") from e
    if df is None or df.empty:
        raise ValueError("文件为空或无有效数据")
    headers = [str(h).strip() for h in df.columns]
    low = [h.lower() for h in headers]

    def pick(keys, exclude=()):
        i, col = _pick_col(low, keys, exclude)
        return headers[i] if col else None

    exclude = set()
    if combo_col is None:
        combo_col = pick(COMBO_KEYS)
        if combo_col:
            exclude.add(low.index(combo_col.lower()) if combo_col.lower() in low else -1)
    if sub_col is None:
        sub_col = pick(SUB_KEYS, exclude)
        if sub_col:
            exclude.add(low.index(sub_col.lower()) if sub_col.lower() in low else -1)
    if combo_col is None and sub_col is None:
        raise ValueError('无法识别组合SKU/子SKU列，请确保表头含"组合/父/成套"与"子/单品"等关键词')
    found = {headers.index(c) for c in (combo_col, sub_col) if c}
    if combo_col is None:
        for i, h in enumerate(headers):
            if i not in found:
                combo_col = h
                break
    if sub_col is None:
        for i, h in enumerate(headers):
            if i not in found:
                sub_col = h
                break
    if name_col is None:
        name_col = pick(NAME_KEYS, exclude)

    kits = {}
    for _, row in df.iterrows():
        combo = str(row.get(combo_col) or "").strip()
        sub = str(row.get(sub_col) or "").strip()
        if not combo or not sub:
            continue
        name = str(row.get(name_col) or "").strip() if name_col else ""
        k = kits.setdefault(combo, {"name": name or "", "comps": set()})
        if not k["name"] and name:
            k["name"] = name
        k["comps"].add(sub)

    if not kits:
        raise ValueError("未能解析出组合SKU/子SKU，请检查表头或列顺序")

    added = 0
    skipped = 0
    for combo, k in kits.items():
        if combo in kitmap._data:
            skipped += 1
            continue
        kitmap._data[combo] = {"name": k["name"], "components": sorted(k["comps"])}
        added += 1
    kitmap.save()
    return added, skipped


def import_standalone_excel(path, kitmap):
    """从 Excel/CSV 导入非组合产品（独立 SKU 列表）。表头含 SKU/编码/货号 与 可选名称。
    已存在的SKU（含组合与非组合）自动跳过，只导入新数据。
    返回 (新增数量, 跳过数量)。"""
    import pandas as pd

    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".csv":
            df = pd.read_csv(path, dtype=str)
        else:
            df = pd.read_excel(path, dtype=str)
    except Exception as e:
        raise ValueError(f"文件读取失败: {e}") from e
    if df is None or df.empty:
        raise ValueError("文件为空或无有效数据")
    headers = [str(h).strip() for h in df.columns]
    low = [h.lower() for h in headers]

    sku_idx, _ = _pick_col(low, SKU_KEYS)
    if sku_idx is None:
        raise ValueError('无法识别SKU列，请确保表头含"SKU/编码/货号"等关键词')
    sku_col = headers[sku_idx]
    name_idx, _ = _pick_col(low, NAME_KEYS, exclude={sku_idx})
    name_col = headers[name_idx] if name_idx is not None else None

    count = 0
    skipped = 0
    for _, row in df.iterrows():
        sku = str(row.get(sku_col) or "").strip()
        if not sku:
            continue
        if sku in kitmap._data:
            skipped += 1
            continue
        name = str(row.get(name_col) or "").strip() if name_col else ""
        kitmap._data[sku] = {"name": name, "components": []}
        count += 1

    if not count and not skipped:
        raise ValueError("未能解析出任何非组合SKU，请检查表头或列顺序")

    kitmap.save()
    return count, skipped


class KitMap:
    def __init__(self, path=DEFAULT_FILE):
        self.path = path
        self._data = {}
        self._index = {}
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}
        else:
            self._data = {}
        self._rebuild_index()

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        self._rebuild_index()

    def _rebuild_index(self):
        idx = {}
        for kit, info in self._data.items():
            for c in (info.get("components") or []):
                idx.setdefault(c, kit)
        self._index = idx

    def list(self):
        return [
            {"sku": k, "name": v.get("name", "") or "",
             "components": list(v.get("components") or []),
             "type": "combo" if (v.get("components") or []) else "standalone"}
            for k, v in sorted(self._data.items())
        ]

    def upsert(self, sku, name, components):
        self._data[sku] = {"name": name or "", "components": [c for c in components if c]}
        self.save()

    def remove(self, sku):
        if sku in self._data:
            del self._data[sku]
            self.save()
            return True
        return False

    def apply(self, rows):
        """按套数规则变换一行产品数据。

        返回新列表：成套的组合SKU行 + 不成套的子SKU行，其余原样保留。
        行内 tag 字段标记分类：kit=成套组合 / part=不成套子件 / 无tag=无组合独立SKU；
        part 行带 kit 字段标识所属组合。
        """
        if not rows or not self._index:
            return [dict(r, box=int(r.get("qty") or 0)) for r in rows]
        comp_qty = {}
        comp_name = {}
        kit_used = {k: False for k in self._data if self._data[k].get("components")}
        out = []
        for r in rows:
            sku = str(r.get("sku") or "").strip()
            if not sku or sku in kit_used:
                continue
            kit = self._index.get(sku)
            if kit:
                comp_qty[sku] = comp_qty.get(sku, 0) + int(r.get("qty") or 0)
                comp_name.setdefault(sku, str(r.get("name") or "") or sku)
                kit_used[kit] = True
            else:
                out.append(dict(r, box=int(r.get("qty") or 0)))
        for kit, info in self._data.items():
            if not info.get("components") or not kit_used[kit]:
                continue
            comps = info.get("components") or []
            qtys = [comp_qty.get(c, 0) for c in comps]
            n_sets = min(qtys) if qtys else 0
            out.append({"sku": kit, "name": info.get("name") or kit,
                        "qty": n_sets, "tag": "kit", "box": n_sets * len(comps)})
            for c, q in zip(comps, qtys):
                left = q - n_sets
                if left > 0:
                    out.append({"sku": c, "name": comp_name.get(c, c),
                                "qty": left, "tag": "part", "kit": kit, "box": left})
        return out
