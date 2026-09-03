from __future__ import annotations

from copy import deepcopy

SUPPORTED_PRESETS = ("standard", "compact", "detailed")

DEFAULT_FORMAT_SETTINGS = {
    "preset": "standard",
    "fields": {
        "order_no": {"enabled": True, "label": "销售单号"},
        "store_name": {"enabled": True, "label": "门店"},
        "sold_at": {"enabled": True, "label": "时间"},
        "total_amount": {"enabled": True, "label": "总金额"},
        "match_reason": {"enabled": True, "label": "命中原因"},
        "style_no": {"enabled": True, "label": "款号"},
        "unit_price": {"enabled": True, "label": "单价"},
        "barcode": {"enabled": True, "label": "条码"},
        "brand": {"enabled": True, "label": "品牌"},
        "category": {"enabled": True, "label": "品类"},
        "image": {"enabled": True, "label": "图片"},
    },
}


def _parse_enabled_flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value in (0, 1):
            return bool(value)
        raise ValueError(f"unsupported enabled value: {value}")
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
        raise ValueError(f"unsupported enabled value: {value}")
    raise ValueError(f"unsupported enabled value: {value}")


def normalize_format_settings(raw: dict | None) -> dict:
    normalized = deepcopy(DEFAULT_FORMAT_SETTINGS)
    if raw is None:
        return normalized

    preset = raw.get("preset", normalized["preset"])
    if preset not in SUPPORTED_PRESETS:
        raise ValueError(f"unsupported preset: {preset}")
    normalized["preset"] = preset

    raw_fields = raw.get("fields", {})
    for field_name, default_config in normalized["fields"].items():
        field_config = raw_fields.get(field_name, {})
        if "enabled" in field_config:
            default_config["enabled"] = _parse_enabled_flag(field_config["enabled"])
        label = field_config.get("label")
        if isinstance(label, str) and label.strip():
            default_config["label"] = label

    return normalized
