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

    assert "# 零售晒单" in message
    assert "## 成交摘要" in message
    assert "**销售单号**" in message
    assert "**门店**" in message
    assert "高金额命中" in message
    assert "**商品信息**" in message
    assert "- **款号**：`A1001`" in message
    assert "条码：`6901111111111`" in message
    assert "![](http://127.0.0.1:8123/6901111111111.jpg)" in message
    assert "- **款号**：`B2002`" in message
    assert "> 图片未展示" in message
    assert "还有 1 张图片未展示" in message


def test_message_builder_shows_no_image_per_item_when_missing() -> None:
    order = SalesOrder(
        order_no="SO-002",
        sold_at=datetime(2026, 4, 20, 10, 0, 0),
        store_name="上海一店",
        total_amount=1200,
        items=[
            SalesLineItem(barcode="6901111111111", style_no="A1001", unit_price=699),
        ],
    )

    message = build_markdown_v2_message(
        order=order,
        filter_result=FilterResult(matched=True, reason="manual_test"),
        image_urls={},
        max_images=8,
    )

    assert "**商品信息**" in message
    assert "- **款号**：`A1001`" in message
    assert "> 暂无图片" in message


def test_message_builder_uses_item_remote_image_and_renders_brand_and_category() -> None:
    order = SalesOrder(
        order_no="SO-003",
        sold_at=datetime(2026, 4, 20, 10, 0, 0),
        store_name="上海一店",
        total_amount=1200,
        items=[
            SalesLineItem(
                barcode="6903333333333",
                style_no="C3003",
                unit_price=799,
                brand="Brand-A",
                category="外套",
                image_url="https://img.example.com/p1.jpg",
            ),
        ],
    )

    message = build_markdown_v2_message(
        order=order,
        filter_result=FilterResult(matched=True, reason="manual_test"),
        image_urls={},
        max_images=8,
    )

    assert "https://img.example.com/p1.jpg" in message
    assert "Brand-A" in message
    assert "外套" in message


def test_message_builder_prefers_dict_image_over_item_image() -> None:
    order = SalesOrder(
        order_no="SO-004",
        sold_at=datetime(2026, 4, 20, 10, 0, 0),
        store_name="上海一店",
        total_amount=1200,
        items=[
            SalesLineItem(
                barcode="6904444444444",
                style_no="D4004",
                unit_price=899,
                image_url="https://img.example.com/fallback.jpg",
            ),
        ],
    )

    message = build_markdown_v2_message(
        order=order,
        filter_result=FilterResult(matched=True, reason="manual_test"),
        image_urls={
            "6904444444444": "https://img.example.com/override.jpg",
        },
        max_images=8,
    )

    assert "https://img.example.com/override.jpg" in message
    assert "https://img.example.com/fallback.jpg" not in message


def test_message_builder_truncates_when_content_exceeds_limit() -> None:
    order = SalesOrder(
        order_no="SO-LONG",
        sold_at=datetime(2026, 4, 20, 10, 0, 0),
        store_name="上海一店",
        total_amount=9999,
        items=[
            SalesLineItem(barcode=f"690{i:010d}", style_no=f"STYLE-{i}", unit_price=100 + i)
            for i in range(20)
        ],
    )

    image_urls = {
        item.barcode: f"http://127.0.0.1:8123/{item.barcode}.jpg" for item in order.items
    }

    message = build_markdown_v2_message(
        order=order,
        filter_result=FilterResult(matched=True, reason="amount_threshold"),
        image_urls=image_urls,
        max_images=8,
        max_bytes=1200,
    )

    assert len(message.encode("utf-8")) <= 1200
    assert "商品明细已截断" in message
