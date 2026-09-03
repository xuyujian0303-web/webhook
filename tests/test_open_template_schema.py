from datetime import datetime

from wecom_sales_webhook_bot.message_template_engine import (
    render_message_template,
    validate_message_template,
)


def _context() -> dict:
    return {
        "order": {
            "order_no": "SO-1001",
            "sold_at": datetime(2026, 8, 21, 10, 30),
            "store_name": "G830",
            "total_amount": 82280,
            "salesperson": "张三",
            "total_quantity": 2,
            "customer_source": "会员推荐",
            "promotion_material": "秋季画册",
            "card_type": "金卡",
            "match_reason": "金额命中",
            "items": [
                {
                    "barcode": "B1",
                    "style_no": "S1",
                    "unit_price": 93500,
                    "brand": "Brand-A",
                    "category": "Coat",
                    "image_url": "http://intranet.images/1.jpg",
                }
            ],
        }
    }


def test_template_renders_order_fields_and_split_item_fields_in_loop() -> None:
    rendered = render_message_template(
        "{{ order.salesperson }} {{ order.card_type }} "
        "{% for item in order.items %}{{ item.style_no }} {{ item.image_url }}{% endfor %}",
        _context(),
    )

    assert "张三" in rendered.text
    assert "金卡" in rendered.text
    assert "S1" in rendered.text
    assert "http://intranet.images/1.jpg" in rendered.text


def test_template_rejects_unknown_and_private_attributes() -> None:
    unknown_errors = validate_message_template("{{ order.password }}")
    private_errors = validate_message_template("{{ item.__class__ }}")

    assert any("order.password" in error for error in unknown_errors)
    assert any("item.__class__" in error for error in private_errors)
