from datetime import datetime

from wecom_sales_webhook_bot.filters import FilterResult
from wecom_sales_webhook_bot.message_builder import build_markdown_v2_message
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder


def test_message_builder_renders_order_details_and_limits_images() -> None:
    order = SalesOrder(
        order_no="SO-001",
        sold_at=datetime(2026, 4, 20, 10, 0, 0),
        store_name="上海一店",
        total_amount=1200,
        items=[
            SalesLineItem(barcode="6901111111111", style_no="A1001", unit_price=699),
            SalesLineItem(barcode="6902222222222", style_no="B2002", unit_price=501),
        ],
    )

    message = build_markdown_v2_message(
        order=order,
        filter_result=FilterResult(matched=True, reason="amount_threshold"),
        image_urls={
            "6901111111111": "http://127.0.0.1:8123/6901111111111.jpg",
            "6902222222222": "http://127.0.0.1:8123/6902222222222.jpg",
        },
        max_images=1,
    )

    assert "SO-001" in message
    assert "amount_threshold" in message
    assert "6901111111111" in message
    assert "![](http://127.0.0.1:8123/6901111111111.jpg)" in message
    assert "还有 1 张图片未展示" in message
