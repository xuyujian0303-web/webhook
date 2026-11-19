from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
import json
from typing import Any

from wecom_sales_webhook_bot.models import SalesOrder
from wecom_sales_webhook_bot.sales_fields import FIELD_KINDS, ITEM_RULE_FIELDS, canonical_field_name, order_field_values


@dataclass(frozen=True)
class RuleConditionDTO:
    field_name: str
    operator: str
    value: list[str] | float | str
    condition_group: str = ""


@dataclass(frozen=True)
class RuleGroupDTO:
    name: str
    match_mode: str = "all"  # legacy groups without condition_group
    conditions: list[RuleConditionDTO] | None = None

    def __post_init__(self) -> None:
        if self.conditions is None:
            object.__setattr__(self, "conditions", [])


TEXT_OPERATORS = ("equals", "not_equals", "contains", "not_contains", "in", "not_in", "starts_with", "ends_with", "is_empty", "is_not_empty")
NUMBER_OPERATORS = ("equals", "not_equals", "gt", "gte", "lt", "lte", "between", "is_empty", "is_not_empty")
EMS_QUERY_FIELDS = frozenset({"season", "shipment_group"})
EMS_QUERY_OPERATORS = ("equals", "not_equals", "in", "not_in")
DATETIME_OPERATORS = ("equals", "before", "after", "date_between", "between_time", "is_empty", "is_not_empty")
DOCUMENT_TYPE_ALIASES = {
    "0": "sale",
    "1": "exchange",
    "2": "return",
    "3": "preorder",
    "\u9500\u552e": "sale",
    "\u9000\u8d27": "return",
    "\u6362\u8d27": "exchange",
    "\u9884\u8d2d": "preorder",
}


def normalize_document_type(value: object) -> str:
    text = str(value).strip()
    return DOCUMENT_TYPE_ALIASES.get(text, text.casefold())

def operators_for_field(field_name: str) -> tuple[str, ...]:
    field_name = canonical_field_name(field_name)
    if field_name in EMS_QUERY_FIELDS:
        return EMS_QUERY_OPERATORS
    kind = FIELD_KINDS.get(field_name, "text")
    return DATETIME_OPERATORS if kind == "datetime" else NUMBER_OPERATORS if kind == "number" else TEXT_OPERATORS


def _bounds(value: Any) -> list[str]:
    """Preserve empty lower/upper bounds in date ranges."""
    return [str(v).strip() for v in value] if isinstance(value, list) else [v.strip() for v in str(value).split(",")]


def _values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _number(value: str) -> Decimal | None:
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def server_condition_key(condition: RuleConditionDTO) -> str:
    return json.dumps([canonical_field_name(condition.field_name), condition.operator,
                       [value.casefold() for value in _values(condition.value)]], ensure_ascii=True)


def _parse_datetime(value: str) -> datetime | None:
    try:
        text = value.strip().replace("/", "-")
        parts = text.split(" ", 1)
        if "T" not in text and len(parts[0].split("-")) == 3:
            y, m, d = (int(v) for v in parts[0].split("-"))
            text = f"{y:04d}-{m:02d}-{d:02d}" + (" " + parts[1] if len(parts) > 1 else "")
        return datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return None


def _match_datetime(value: str, operator: str, wanted: list[str]) -> bool:
    actual = _parse_datetime(value)
    if actual is None:
        return False
    if operator == "between_time":
        if len(wanted) != 2:
            return False
        try:
            low, high = (time.fromisoformat(v) for v in wanted)
        except ValueError:
            return False
        # HH:MM inputs include the whole boundary minute.
        current = actual.time().replace(second=0, microsecond=0) if all(len(v) == 5 for v in wanted) else actual.time()
        return low <= current <= high if low <= high else current >= low or current <= high
    if operator in {"date_between", "date_range"}:
        bounds = (wanted + ["", ""])[:2]
        dates = [_parse_datetime(v) if v else None for v in bounds]
        if any(v and parsed is None for v, parsed in zip(bounds, dates)):
            return False
        return (dates[0] is None or actual.date() >= dates[0].date()) and (dates[1] is None or actual.date() <= dates[1].date())
    if not wanted or (target := _parse_datetime(wanted[0])) is None:
        return False
    a, b = (actual.date(), target.date()) if len(wanted[0]) <= 10 else (actual, target)
    if isinstance(a, datetime) and (a.tzinfo is None) != (b.tzinfo is None):
        return False
    if operator == "equals":
        return a == b
    if operator == "before":
        return a < b
    if operator == "after":
        return a > b
    return False


def matches_order_date_range(order: SalesOrder, start_date: date | None, end_date: date | None) -> bool:
    current = order.sold_at.date()
    return (start_date is None or current >= start_date) and (end_date is None or current <= end_date)


def _match_one(value: str, condition: RuleConditionDTO) -> bool:
    condition = replace(condition, field_name=canonical_field_name(condition.field_name))
    operator = condition.operator
    wanted = _values(condition.value)
    is_numeric = FIELD_KINDS.get(canonical_field_name(condition.field_name)) == "number"
    if is_numeric and operator in {"equals", "not_equals"}:
        actual = _number(value)
        numbers = [_number(item) for item in wanted]
        if actual is None or not numbers or any(item is None for item in numbers):
            return False
        return actual == numbers[0] if operator == "equals" else actual not in numbers
    if condition.field_name == "document_type":
        value = normalize_document_type(value)
        wanted = [
            normalize_document_type(item)
            for item in wanted
        ]
    if FIELD_KINDS.get(condition.field_name) == "datetime" and operator not in {"is_empty", "is_not_empty"}:
        return _match_datetime(value, operator, _bounds(condition.value) if operator in {"date_between", "date_range"} else wanted)
    # EMS organization and code values are case-insensitive in practice.
    if condition.field_name not in {"sold_at", "created_at"}:
        value = value.casefold()
        wanted = [item.casefold() for item in wanted]
    if operator == "is_empty": return not value
    if operator == "is_not_empty": return bool(value)
    if operator == "equals": return value == (wanted[0] if wanted else "")
    if operator == "not_equals": return value not in wanted if wanted else True
    if operator == "contains": return (wanted[0] if wanted else "") in value
    if operator == "not_contains": return (wanted[0] if wanted else "") not in value
    if operator == "in": return value in wanted
    if operator == "not_in": return value not in wanted
    if operator == "starts_with": return value.startswith(wanted[0] if wanted else "")
    if operator == "ends_with": return value.endswith(wanted[0] if wanted else "")
    if operator in {"gt", "gte", "lt", "lte", "between"}:
        actual = _number(value); numbers = [_number(item) for item in wanted]
        if actual is None or not numbers or any(item is None for item in numbers): return False
        if operator == "gt": return actual > numbers[0]
        if operator == "gte": return actual >= numbers[0]
        if operator == "lt": return actual < numbers[0]
        if operator == "lte": return actual <= numbers[0]
        return len(numbers) == 2 and min(numbers) <= actual <= max(numbers)
    return False



def _match_condition(order: SalesOrder, condition: RuleConditionDTO) -> bool:
    field_name = canonical_field_name(condition.field_name)
    key = server_condition_key(condition)
    proven = order.attributes.get("_ems_condition_matches", {})
    if field_name in EMS_QUERY_FIELDS and key in proven:
        return bool(proven[key])
    values = order_field_values(order, field_name)
    if condition.operator == "is_empty": return not values or all(not value for value in values)
    if condition.operator == "is_not_empty": return any(bool(value) for value in values)
    if not values: return False
    if condition.operator in {"not_equals", "not_contains", "not_in"}:
        return all(_match_one(value, condition) for value in values)
    return any(_match_one(value, condition) for value in values)


def evaluate_rule_group(
    order: SalesOrder,
    rule_group: RuleGroupDTO,
    default_start_date: date | None = None,
    server_filtered_fields: set[str] | None = None,
) -> bool:
    """Apply both groups: every ALL condition and at least one ANY condition."""
    grouped: dict[str, list[RuleConditionDTO]] = {"all": [], "any": []}
    for condition in rule_group.conditions or []:
        condition = replace(condition, field_name=canonical_field_name(condition.field_name))
        # Compatibility with the original date_range condition persisted by
        # the web UI before generic date_between was introduced.
        if condition.field_name == "sold_at" and condition.operator == "date_range":
            raw = _bounds(condition.value)
            start = raw[0] if raw else ""
            end = raw[1] if len(raw) > 1 else ""
            condition = replace(condition, operator="date_between", value=[start or (default_start_date.isoformat() if default_start_date else ""), end])
        group = condition.condition_group if condition.condition_group in grouped else rule_group.match_mode
        if condition.operator in {"date_range", "date_between"}:
            group = "all"
        grouped[group].append(condition)
    def matches(condition):
        # Compatibility for older sources: a proven positive server criterion
        # is a true Boolean operand, never remove it from an OR group.
        if (condition.field_name in EMS_QUERY_FIELDS
                and condition.field_name in (server_filtered_fields or set())
                and condition.operator in {"equals", "in"}
                and server_condition_key(condition) not in order.attributes.get("_ems_condition_matches", {})):
            return True
        return _match_condition(order, condition)
    return all(matches(item) for item in grouped["all"]) and (
        not grouped["any"] or any(matches(item) for item in grouped["any"])
    )


def project_rule_items(order: SalesOrder, rule_group: RuleGroupDTO) -> SalesOrder:
    """Project only after whole-order rule evaluation, preserving line unions.

    Each item predicate can match a different row. The displayed rows are the
    union of rows matching those predicates; header/query-only rules retain all
    rows because their results identify orders, not individual matching rows.
    """
    conditions = [c for c in rule_group.conditions or []
                  if canonical_field_name(c.field_name) in ITEM_RULE_FIELDS]
    if not conditions:
        return order
    items = [item for item in order.items if any(
        _match_condition(replace(order, items=[item]), c) for c in conditions)]
    return replace(order, items=items) if items else order
