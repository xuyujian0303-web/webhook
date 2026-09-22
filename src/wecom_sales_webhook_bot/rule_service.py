from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any

from wecom_sales_webhook_bot.models import SalesOrder
from wecom_sales_webhook_bot.sales_fields import FIELD_KINDS, canonical_field_name, order_field_values


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
DATETIME_OPERATORS = ("equals", "before", "after", "date_between", "between_time", "is_empty", "is_not_empty")


def operators_for_field(field_name: str) -> tuple[str, ...]:
    kind = FIELD_KINDS.get(canonical_field_name(field_name), "text")
    return DATETIME_OPERATORS if kind == "datetime" else NUMBER_OPERATORS if kind == "number" else TEXT_OPERATORS


def _values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _number(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def matches_order_date_range(order: SalesOrder, start_date: date | None, end_date: date | None) -> bool:
    current = order.sold_at.date()
    return (start_date is None or current >= start_date) and (end_date is None or current <= end_date)


def _match_one(value: str, condition: RuleConditionDTO) -> bool:
    operator = condition.operator
    wanted = _values(condition.value)
    # EMS organization and code values are case-insensitive in practice.
    if condition.field_name not in {"sold_at", "created_at"}:
        value = value.casefold()
        wanted = [item.casefold() for item in wanted]
    if operator == "is_empty": return not value
    if operator == "is_not_empty": return bool(value)
    if operator == "equals": return value == (wanted[0] if wanted else "")
    if operator == "not_equals": return value != (wanted[0] if wanted else "")
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
    if operator == "before": return bool(wanted) and value < wanted[0]
    if operator == "after": return bool(wanted) and value > wanted[0]
    if operator == "date_between":
        start, end = (wanted + ["", ""])[:2]; current = value[:10].replace("/", "-")
        return (not start or current >= start) and (not end or current <= end)
    if operator == "between_time":
        start, end = (wanted + ["", ""])[:2]; current = value[11:16] if len(value) >= 16 else value[-8:-3]
        return bool(start and end and start <= current <= end)
    return False


def _match_condition(order: SalesOrder, condition: RuleConditionDTO) -> bool:
    values = order_field_values(order, canonical_field_name(condition.field_name))
    if condition.operator == "is_empty": return not values or all(not value for value in values)
    if condition.operator == "is_not_empty": return any(bool(value) for value in values)
    if not values: return False
    if condition.operator in {"not_equals", "not_contains", "not_in"}:
        return all(_match_one(value, condition) for value in values)
    return any(_match_one(value, condition) for value in values)


def evaluate_rule_group(order: SalesOrder, rule_group: RuleGroupDTO, default_start_date: date | None = None) -> bool:
    """Apply both groups: every ALL condition and at least one ANY condition."""
    grouped: dict[str, list[RuleConditionDTO]] = {"all": [], "any": []}
    for condition in rule_group.conditions or []:
        # Compatibility with the original date_range condition persisted by
        # the web UI before generic date_between was introduced.
        if condition.field_name == "sold_at" and condition.operator == "date_range":
            raw = _values(condition.value)
            start = raw[0] if raw else ""
            end = raw[1] if len(raw) > 1 else ""
            condition = replace(condition, operator="date_between", value=[start or (default_start_date.isoformat() if default_start_date else ""), end])
        group = condition.condition_group if condition.condition_group in grouped else rule_group.match_mode
        if condition.operator in {"date_range", "date_between"}:
            group = "all"
        grouped[group].append(condition)
    return all(_match_condition(order, item) for item in grouped["all"]) and (
        not grouped["any"] or any(_match_condition(order, item) for item in grouped["any"])
    )
