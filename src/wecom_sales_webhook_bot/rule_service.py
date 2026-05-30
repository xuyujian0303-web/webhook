from __future__ import annotations

from dataclasses import dataclass
from datetime import time

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
        return time(start_hour, start_minute) <= current <= time(
            end_hour, end_minute
        )
    return False


def evaluate_rule_group(order: SalesOrder, rule_group: RuleGroupDTO) -> bool:
    results = [_match_condition(order, item) for item in rule_group.conditions]
    if rule_group.match_mode == "all":
        return all(results)
    return any(results)
