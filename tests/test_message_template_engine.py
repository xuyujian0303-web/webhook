from datetime import datetime
from decimal import Decimal

import pytest

from wecom_sales_webhook_bot.message_template_defaults import PRESET_TEMPLATES
from wecom_sales_webhook_bot.message_template_engine import TemplateRenderError, render_message_template, validate_message_template
from wecom_sales_webhook_bot.message_template_schema import REFERENCE_VARIABLES


def _sample_context() -> dict:
    return {
        "order": {
            "order_no": "SO-100",
            "store_name": "G609",
            "sold_at": datetime(2026, 6, 5, 10, 50),
            "total_amount": 21500,
            "salesperson": "张三",
            "total_quantity": 1,
            "customer_source": "会员推荐",
            "promotion_material": "画册",
            "card_type": "金卡",
            "match_reason": "金额命中",
            "items": [{"barcode": "B1", "style_no": "DRCH042ABK0", "unit_price": 21500, "brand": "Brand-A", "category": "Coat", "image_url": "http://intranet.images/1.jpg"}],
        }
    }


def test_render_message_template_applies_allowed_filters() -> None:
    rendered = render_message_template("{{ order.sold_at | datetime }} {{ order.total_amount | money }}", _sample_context())
    assert rendered.text == "2026-06-05 10:50:00 21500.00"
    assert rendered.byte_length == len(rendered.text.encode("utf-8"))


def test_default_template_uses_split_item_loop() -> None:
    assert "{% for item in order.items %}" in PRESET_TEMPLATES["standard"]["body"]
    assert "items_markdown" not in PRESET_TEMPLATES["standard"]["body"]


def test_reference_variables_include_split_item_fields() -> None:
    assert any(item["token"] == "item.image_url" for item in REFERENCE_VARIABLES)
    assert not any(item["token"] == "items_markdown" for item in REFERENCE_VARIABLES)


def test_render_message_template_formats_money_with_decimal_precision() -> None:
    context = _sample_context()
    context["order"]["total_amount"] = Decimal("12345678901234567890.12")
    assert render_message_template("{{ order.total_amount | money }}", context).text == "12345678901234567890.12"


def test_render_message_template_renders_split_item_loop() -> None:
    rendered = render_message_template("{% for item in order.items %}{{ item.style_no }} {{ item.image_url }}{% endfor %}", _sample_context())
    assert rendered.text == "DRCH042ABK0 http://intranet.images/1.jpg"


def test_validate_message_template_rejects_unknown_variable() -> None:
    assert validate_message_template("{{ order.unknown_field }}") == ["unknown variable: order.unknown_field"]


def test_validate_message_template_rejects_unknown_filter() -> None:
    assert validate_message_template("{{ order.total_amount | weird }}") == ["unknown filter: weird"]


def test_render_message_template_raises_on_invalid_template() -> None:
    with pytest.raises(TemplateRenderError, match="unknown filter"):
        render_message_template("{{ order.total_amount | weird }}", _sample_context())
