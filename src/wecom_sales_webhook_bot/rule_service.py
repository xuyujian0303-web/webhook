from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from wecom_sales_webhook_bot.models import SalesOrder


@dataclass(frozen=True)
class RuleConditionDTO:
    field_name: str
    operator: str
    value: list[str] | float


@dataclass(frozen=True)
class RuleGroupDTO:
    name: str
    match_mode: str
    conditions: list[RuleConditionDTO]


def matches_order_date_range(
    order: SalesOrder,
    start_date: date | None,
    end_date: date | None,
) -> bool:
    order_date = order.sold_at.date()
    return (start_date is None or order_date >= start_date) and (
        end_date is None or order_date <= end_date
    )


def _parse_date_range(condition: RuleConditionDTO) -> tuple[date | None, date | None]:
    start_text, end_text = condition.value
    start_date = datetime.strptime(start_text, "%Y-%m-%d").date() if start_text else None
    end_date = datetime.strptime(end_text, "%Y-%m-%d").date() if end_text else None
    return start_date, end_date


def _match_condition(order: SalesOrder, condition: RuleConditionDTO) -> bool:
    if condition.field_name == "total_amount" and condition.operator == "gte":
        return order.total_amount >= float(condition.value)
    if condition.field_name == "store_name" and condition.operator == "in":
        return order.store_name in condition.value
    if condition.field_name == "style_no" and condition.operator == "in":
        return any(item.style_no in condition.value for item in order.items)
    if condition.field_name == "brand" and condition.operator == "in":
        return any((item.brand or "") in condition.value for item in order.items)
    if condition.field_name == "category" and condition.operator == "in":
        return any((item.category or "") in condition.value for item in order.items)
    if condition.field_name == "sold_at" and condition.operator == "between_time":
        start_text, end_text = condition.value
        start_hour, start_minute = map(int, start_text.split(":"))
        end_hour, end_minute = map(int, end_text.split(":"))
        current = order.sold_at.time()
        return time(start_hour, start_minute) <= current <= time(end_hour, end_minute)
    return False


def evaluate_rule_group(
    order: SalesOrder,
    rule_group: RuleGroupDTO,
    default_start_date: date | None = None,
) -> bool:
    date_conditions = [
        item
        for item in rule_group.conditions
        if item.field_name == "sold_at" and item.operator == "date_range"
    ]
    for condition in date_conditions:
        start_date, end_date = _parse_date_range(condition)
        if start_date is None:
            start_date = default_start_date
        if not matches_order_date_range(order, start_date, end_date):
            return False

    business_conditions = [item for item in rule_group.conditions if item not in date_conditions]
    if not business_conditions:
        return True
    results = [_match_condition(order, item) for item in business_conditions]
    if rule_group.match_mode == "all":
        return all(results)
    return any(results)
