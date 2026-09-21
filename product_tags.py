"""产品标签存储模块。

存储：product_tags.json，结构 {产品SKU: 标签名}，如 {"A123": "清仓"}。
用于排行榜产品打标签（如清仓）并支持按标签排除不具代表性的数据。
"""
import json
import os
import threading

DEFAULT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "product_tags.json")

_lock = threading.Lock()


def _load():
    try:
        with open(DEFAULT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items() if str(k).strip()}
    except (OSError, ValueError):
        pass
    return {}


def _save(data):
    tmp = DEFAULT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DEFAULT_FILE)


def load():
    with _lock:
        return dict(_load())


def set_tag(sku, label):
    label = (label or "").strip()
    with _lock:
        data = _load()
        if label:
            data[sku] = label
        else:
            data.pop(sku, None)
        _save(data)
    return dict(data)


def remove(sku):
    with _lock:
        data = _load()
        data.pop(sku, None)
        _save(data)
    return dict(data)
