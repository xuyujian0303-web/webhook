from wecom_sales_webhook_bot.desktop_gui import (
    OPERATOR_CHOICE_TO_KEY,
    _operator_choices,
)
from wecom_sales_webhook_bot.rule_service import operators_for_field


def _keys(field_name: str) -> set[str]:
    return {OPERATOR_CHOICE_TO_KEY[value] for value in _operator_choices(field_name)}


def test_text_field_operator_choices_are_complete() -> None:
    expected = set(operators_for_field("store_name"))
    assert _keys("store_name") == expected
    assert {"equals", "not_equals", "contains", "not_contains", "in", "not_in", "starts_with", "ends_with", "is_empty", "is_not_empty"} <= expected


def test_number_field_operator_choices_are_complete() -> None:
    expected = set(operators_for_field("total_amount"))
    assert _keys("total_amount") == expected
    assert {"equals", "not_equals", "gt", "gte", "lt", "lte", "between", "is_empty", "is_not_empty"} <= expected


def test_date_field_operator_choices_include_before_and_after() -> None:
    expected = set(operators_for_field("sold_at"))
    assert _keys("sold_at") == expected
    assert {"equals", "before", "after", "date_between", "between_time", "is_empty", "is_not_empty"} <= expected
    assert "早于" in _operator_choices("sold_at")[1]
    assert "晚于" in _operator_choices("sold_at")[2]


def test_all_selectable_fields_have_operator_choices() -> None:
    for field_name in ("order_no", "sold_at", "store_name", "total_amount", "created_at", "style_no", "quantity"):
        assert _operator_choices(field_name)
