"""Canonical EMS sales-detail fields and generic value access for rules."""
from __future__ import annotations

from dataclasses import fields
from datetime import datetime
from typing import Any

from wecom_sales_webhook_bot.models import SalesOrder


# The labels mirror the columns exported by EMS ``销售详单查询``.  A field can
# be selected by either its stable key (used in the database) or its label.
EMS_FIELD_DEFINITIONS: tuple[tuple[str, str, str], ...] = (
    ("order_no", "销售单号", "text"),
    ("salesperson", "销售人员", "text"),
    ("sold_at", "销售日期", "datetime"),
    ("store_name", "销售机构", "text"),
    ("performance_org", "业绩机构", "text"),
    ("document_type", "销售类型", "text"),
    ("currency", "币种", "text"),
    ("customer_type", "顾客类型", "text"),
    ("customer_discount_type", "顾客折扣类型", "text"),
    ("customer_discount", "顾客折扣", "number"),
    ("card_type", "卡类型", "text"),
    ("card_no", "卡号", "text"),
    ("total_amount", "总金额", "number"),
    ("product_code", "产品编码", "text"),
    ("style_no", "款色码", "text"),
    ("item_id", "ItemID", "text"),
    ("barcode", "商品条码", "text"),
    ("category", "类别", "text"),
    ("product_type", "商品类型", "text"),
    ("special_sale", "特殊销售", "text"),
    ("product_status", "商品状态", "text"),
    ("operation_type", "操作方式", "text"),
    ("unit_price", "价格", "number"),
    ("discount", "折扣", "number"),
    ("actual_amount", "实际金额", "number"),
    ("actual_discount", "实际折扣", "number"),
    ("quantity", "销售件数", "number"),
    ("total_quantity", "整单件数", "number"),
    ("created_at", "创建时间", "datetime"),
    ("customer_source", "顾客来源", "text"),
    ("activity_type", "活动类型", "text"),
    ("promotion_material", "助力素材", "text"),
)

FIELD_LABELS = {key: label for key, label, _ in EMS_FIELD_DEFINITIONS}
FIELD_KINDS = {key: kind for key, _, kind in EMS_FIELD_DEFINITIONS}
FIELD_KEYS = frozenset(FIELD_LABELS)
LABEL_TO_KEY = {label: key for key, label in FIELD_LABELS.items()}


def canonical_field_name(value: str) -> str:
    return LABEL_TO_KEY.get(value, value)


def selectable_fields() -> list[tuple[str, str, str]]:
    return list(EMS_FIELD_DEFINITIONS)


def _as_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    return str(value).strip()


def order_field_values(order: SalesOrder, field_name: str) -> list[str]:
    """Return every relevant order/item value for one EMS field.

    Item-level predicates intentionally match when *any item* has the value;
    group-level AND/OR behaviour is handled by the rule service.
    """
    field_name = canonical_field_name(field_name)
    if field_name in {"product_code", "barcode", "style_no", "unit_price", "brand", "category"}:
        values: list[Any] = []
        for item in order.items:
            values.append(getattr(item, field_name, None))
            values.append(item.attributes.get(field_name))
            if field_name == "product_code":
                values.append(item.attributes.get("product_code", item.style_no))
        return [text for value in values if (text := _as_value(value))]

    if field_name in {"quantity", "discount", "actual_amount", "actual_discount", "item_id", "product_type", "special_sale", "product_status", "operation_type"}:
        values: list[Any] = []
        for item in order.items:
            # ``quantity`` is a first-class line-item property; the other
            # EMS detail fields are retained in ``attributes`` until their
            # source-specific mapping is known.  Looking in both places also
            # keeps CSV/SQL Server mappings and EMS mappings consistent.
            values.append(getattr(item, field_name, None))
            values.append(getattr(item, "attributes", {}).get(field_name))
        return [text for value in values if (text := _as_value(value))]

    if field_name in {item.name for item in fields(order)}:
        return [text for text in (_as_value(getattr(order, field_name)),) if text]
    return [text for text in (_as_value(order.attributes.get(field_name)),) if text]
