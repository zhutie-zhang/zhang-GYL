"""自定义数据源管理：增删改查 + 热加载，存储在 custom_sources.json。"""
import json
import os
import threading
import uuid
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCES_FILE = os.path.join(BASE_DIR, "custom_sources.json")


class CustomSourceManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._sources = []
        self._load()

    def _load(self):
        try:
            with open(SOURCES_FILE, "r", encoding="utf-8") as f:
                self._sources = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._sources = []

    def _save(self):
        with open(SOURCES_FILE, "w", encoding="utf-8") as f:
            json.dump(self._sources, f, ensure_ascii=False, indent=2)

    def list_all(self):
        with self._lock:
            return list(self._sources)

    def get(self, source_id):
        with self._lock:
            for s in self._sources:
                if s["id"] == source_id:
                    return dict(s)
        return None

    def add(self, data):
        with self._lock:
            source = {
                "id": "cs-" + uuid.uuid4().hex[:8],
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
            source.update(data)
            self._sources.append(source)
            self._save()
            return dict(source)

    def update(self, source_id, data):
        with self._lock:
            for i, s in enumerate(self._sources):
                if s["id"] == source_id:
                    for k, v in data.items():
                        if k != "id":
                            s[k] = v
                    s["updated_at"] = datetime.now().isoformat()
                    self._sources[i] = s
                    self._save()
                    return dict(s)
        return None

    def delete(self, source_id):
        with self._lock:
            before = len(self._sources)
            self._sources = [s for s in self._sources if s["id"] != source_id]
            if len(self._sources) < before:
                self._save()
                return True
        return False

    def toggle(self, source_id, enabled):
        with self._lock:
            for s in self._sources:
                if s["id"] == source_id:
                    s["enabled"] = enabled
                    s["updated_at"] = datetime.now().isoformat()
                    self._save()
                    return dict(s)
        return None

    def to_warehouse_configs(self):
        """把自定义数据源转换为 config.json 格式的仓库配置列表。"""
        configs = []
        with self._lock:
            for s in self._sources:
                if not s.get("enabled", True):
                    continue
                cfg = {
                    "id": s["id"],
                    "name": s.get("name", s["id"]),
                    "type": "custom",
                    "enabled": True,
                    "group": s.get("group", "custom"),
                    "account": s.get("account", ""),
                    "timeout": s.get("timeout", 20),
                    "auth": s.get("auth") or {},
                    "wh_name_map": s.get("wh_name_map") or {},
                    "inventory_url": s.get("inventory_url", ""),
                    "inventory_method": s.get("inventory_method", "GET"),
                    "inventory_body": s.get("inventory_body"),
                    "inventory_headers": s.get("inventory_headers"),
                    "inventory_items_path": s.get("inventory_items_path", ""),
                    "inventory_sku_path": s.get("inventory_sku_path", "sku"),
                    "inventory_name_path": s.get("inventory_name_path", "name"),
                    "inventory_qty_path": s.get("inventory_qty_path", "qty"),
                    "inventory_wh_path": s.get("inventory_wh_path", ""),
                    "outbound_url": s.get("outbound_url", ""),
                    "outbound_method": s.get("outbound_method", "GET"),
                    "outbound_body": s.get("outbound_body"),
                    "outbound_headers": s.get("outbound_headers"),
                    "outbound_items_path": s.get("outbound_items_path", ""),
                    "outbound_sku_path": s.get("outbound_sku_path", "sku"),
                    "outbound_name_path": s.get("outbound_name_path", "name"),
                    "outbound_qty_path": s.get("outbound_qty_path", "qty"),
                    "outbound_date_path": s.get("outbound_date_path", "date"),
                    "outbound_wh_path": s.get("outbound_wh_path", ""),
                }
                configs.append(cfg)
        return configs
