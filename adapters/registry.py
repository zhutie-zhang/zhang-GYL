def build_adapter(warehouse_cfg):
    wtype = warehouse_cfg.get("type", "rest").lower()
    if wtype == "mock":
        from adapters.mock import MockAdapter
        return MockAdapter(warehouse_cfg)
    if wtype == "rest":
        from adapters.rest import RestAdapter
        return RestAdapter(warehouse_cfg)
    if wtype == "xlwms":
        from adapters.xlwms import LingxingAdapter
        return LingxingAdapter(warehouse_cfg)
    if wtype == "aidelivery":
        from adapters.aidelivery import AideliveryAdapter
        return AideliveryAdapter(warehouse_cfg)
    if wtype == "lecangs":
        from adapters.lecangs import LecangsAdapter
        return LecangsAdapter(warehouse_cfg)
    if wtype == "yunwms":
        from adapters.yunwms import YunWmsAdapter
        return YunWmsAdapter(warehouse_cfg)
    if wtype == "anmei":
        from adapters.anmei import AnmeiAdapter
        return AnmeiAdapter(warehouse_cfg)
    if wtype == "custom":
        from adapters.custom import CustomAdapter
        return CustomAdapter(warehouse_cfg)
    raise ValueError(f"未知的仓库适配器类型: {wtype}")
