from datetime import date, datetime

from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder
from wecom_sales_webhook_bot.rule_service import (
    RuleConditionDTO,
    RuleGroupDTO,
    evaluate_rule_group,
    matches_order_date_range,
)


def test_evaluate_rule_group_supports_amount_style_store_time_brand_category() -> None:
    order = SalesOrder(
        order_no="SO-2",
        sold_at=datetime(2026, 4, 22, 10, 30, 0),
        store_name="G621",
        total_amount=19250,
        items=[
            SalesLineItem(
                barcode="b1",
                style_no="PA17047BNY0",
                unit_price=5850,
                brand="Brand-A",
                category="澶栧",
            )
        ],
    )

    any_group = RuleGroupDTO(
        name="浠讳竴鍛戒腑",
        match_mode="any",
        conditions=[
            RuleConditionDTO(field_name="store_name", operator="in", value=["G999"]),
            RuleConditionDTO(field_name="brand", operator="in", value=["Brand-A"]),
        ],
    )
    all_group = RuleGroupDTO(
        name="全部命中",
        match_mode="all",
        conditions=[
            RuleConditionDTO(field_name="total_amount", operator="gte", value=10000),
            RuleConditionDTO(
                field_name="style_no", operator="in", value=["PA17047BNY0"]
            ),
            RuleConditionDTO(field_name="category", operator="in", value=["澶栧"]),
            RuleConditionDTO(
                field_name="sold_at", operator="between_time", value=["10:00", "11:00"]
            ),
        ],
    )

    assert evaluate_rule_group(order, any_group) is True
    assert evaluate_rule_group(order, all_group) is True


def test_date_range_is_a_required_gate_even_for_any_match_mode() -> None:
    order = SalesOrder(
        order_no="SO-date",
        sold_at=datetime(2026, 8, 23, 10, 0, 0),
        store_name="G621",
        total_amount=20000,
        items=[SalesLineItem(barcode="b1", style_no="A1", unit_price=100)],
    )
    rule = RuleGroupDTO(
        name="日期范围",
        match_mode="any",
        conditions=[
            RuleConditionDTO(field_name="total_amount", operator="gte", value=10000),
            RuleConditionDTO(
                field_name="sold_at",
                operator="date_range",
                value=["2026-08-24", "2026-08-31"],
            ),
        ],
    )

    assert matches_order_date_range(order, date(2026, 8, 24), None) is False
    assert evaluate_rule_group(rule_group=rule, order=order) is False

