from datetime import date, datetime

from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder
from wecom_sales_webhook_bot.ems_decoder import infer_document_type
from wecom_sales_webhook_bot.rule_service import (
    RuleConditionDTO,
    RuleGroupDTO,
    evaluate_rule_group,
    normalize_document_type,
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


def test_numeric_rule_operators_cover_boundaries_and_invalid_values() -> None:
    order = SalesOrder(
        order_no="SO-number",
        sold_at=datetime(2026, 8, 24, 10, 0),
        store_name="G621",
        total_amount=1000,
        items=[SalesLineItem(barcode="b1", style_no="A1", unit_price=100)],
    )
    for operator in ("equals", "gte", "lte"):
        assert evaluate_rule_group(
            order,
            RuleGroupDTO("match", conditions=[RuleConditionDTO("total_amount", operator, "1000")]),
        )
    for operator in ("gt", "lt"):
        assert not evaluate_rule_group(
            order,
            RuleGroupDTO("no-match", conditions=[RuleConditionDTO("total_amount", operator, "1000")]),
        )
    assert evaluate_rule_group(
        order,
        RuleGroupDTO(
            "between",
            conditions=[RuleConditionDTO("total_amount", "between", "1000,2000")],
        ),
    )
    assert not evaluate_rule_group(
        order,
        RuleGroupDTO(
            "invalid",
            conditions=[RuleConditionDTO("total_amount", "gte", "not-a-number")],
        ),
    )


def test_all_text_and_item_filters_are_evaluated() -> None:
    order = SalesOrder(
        order_no="SO-ABC-001",
        sold_at=datetime(2026, 8, 24, 10, 30),
        store_name="G621",
        performance_org="G889",
        total_amount=1000,
        salesperson="张三",
        document_type="sale",
        items=[
            SalesLineItem(
                barcode="BC-1",
                style_no="PA1",
                unit_price=100,
                quantity=2,
                brand="Brand-A",
                category="外套",
                attributes={"season": "26FW", "shipment_group": "26fwg6"},
            )
        ],
    )
    conditions = [
        ("order_no", "starts_with", "SO-"),
        ("store_name", "in", "G621,G622"),
        ("performance_org", "equals", "G889"),
        ("style_no", "contains", "PA"),
        ("barcode", "ends_with", "-1"),
        ("brand", "equals", "Brand-A"),
        ("category", "not_equals", "连衣裙"),
        ("season", "equals", "26FW"),
        ("shipment_group", "equals", "26fwg6"),
        ("sold_at", "date_between", "2026-08-24,2026-08-24"),
        ("sold_at", "between_time", "10:00,11:00"),
    ]
    rule = RuleGroupDTO(
        "all-fields",
        conditions=[RuleConditionDTO(field, operator, value) for field, operator, value in conditions],
    )
    assert evaluate_rule_group(order, rule)



def test_document_type_accepts_ems_codes_and_chinese_labels() -> None:
    assert normalize_document_type("0") == "sale"
    assert normalize_document_type("销售") == "sale"
    assert normalize_document_type("3") == "preorder"
    assert normalize_document_type("预购") == "preorder"

    sale = SalesOrder(
        order_no="SO-SALE",
        sold_at=datetime(2026, 8, 24, 10, 30),
        store_name="G899",
        total_amount=1000,
        document_type="sale",
    )
    preorder = SalesOrder(
        order_no="SO-PREORDER",
        sold_at=datetime(2026, 8, 24, 10, 30),
        store_name="G899",
        total_amount=1000,
        document_type="preorder",
    )
    rule = RuleGroupDTO(
        "销售和预购",
        conditions=[RuleConditionDTO("document_type", "in", "0,3")],
    )
    assert evaluate_rule_group(sale, rule)
    assert evaluate_rule_group(preorder, rule)


def test_negative_ems_amount_is_return_and_cannot_match_sale_preorder_rule() -> None:
    assert infer_document_type(-12600) == "return"
    assert infer_document_type(12600) == "sale"

    returned = SalesOrder(
        order_no="SO-RETURN",
        sold_at=datetime(2026, 8, 24, 10, 30),
        store_name="G899",
        total_amount=-12600,
        document_type=infer_document_type(-12600),
    )
    rule = RuleGroupDTO(
        "销售和预购",
        conditions=[RuleConditionDTO("document_type", "in", "0,3")],
    )
    assert not evaluate_rule_group(returned, rule)
