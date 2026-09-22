from datetime import datetime

import pytest

from wecom_sales_webhook_bot.format_settings import normalize_format_settings
from wecom_sales_webhook_bot.filters import FilterResult
from wecom_sales_webhook_bot.message_builder import build_markdown_v2_message, is_webhook_image_url
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
    assert "![A1001.jpg](http://127.0.0.1:8123/6901111111111.jpg)" in message
    assert "- **款号**：`B2002`" in message
    assert "> 图片未展示" in message
    assert "还有 1 张图片未展示" in message


def test_image_markdown_has_expected_syntax_and_url_shape() -> None:
    order = SalesOrder(
        order_no="SO-image",
        sold_at=datetime(2026, 4, 20, 10, 0),
        store_name="G621",
        total_amount=1,
        items=[SalesLineItem(barcode="BC", style_no="STYLE", unit_price=1)],
    )
    url = "https://images.example.com/products/STYLE.jpg"
    message = build_markdown_v2_message(
        order, FilterResult(True, "manual_test"), {"BC": url}, 1
    )
    assert "![STYLE.jpg](https://images.example.com/products/STYLE.jpg)" in message
    assert is_webhook_image_url(url)
    assert not is_webhook_image_url("C:/images/STYLE.jpg")
    assert not is_webhook_image_url("file:///C:/images/STYLE.jpg")


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
    assert "![C3003.jpg](https://img.example.com/p1.jpg)" in message
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
    assert "![D4004.jpg](https://img.example.com/override.jpg)" in message
    assert "https://img.example.com/fallback.jpg" not in message


def test_message_builder_limits_mixed_dict_and_item_images() -> None:
    order = SalesOrder(
        order_no="SO-005",
        sold_at=datetime(2026, 4, 20, 10, 0, 0),
        store_name="上海一店",
        total_amount=1800,
        items=[
            SalesLineItem(
                barcode="6905555555555",
                style_no="E5005",
                unit_price=900,
                image_url="https://img.example.com/item.jpg",
            ),
            SalesLineItem(
                barcode="6906666666666",
                style_no="F6006",
                unit_price=900,
                image_url="https://img.example.com/hidden-item.jpg",
            ),
        ],
    )

    message = build_markdown_v2_message(
        order=order,
        filter_result=FilterResult(matched=True, reason="manual_test"),
        image_urls={"6905555555555": "https://img.example.com/dict.jpg"},
        max_images=1,
    )

    assert "https://img.example.com/dict.jpg" in message
    assert "![E5005.jpg](https://img.example.com/dict.jpg)" in message
    assert "https://img.example.com/item.jpg" not in message
    assert "https://img.example.com/hidden-item.jpg" not in message
    assert "> 图片未展示" in message
    assert "还有 1 张图片未展示" in message


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


def test_message_builder_truncates_whole_item_blocks_with_optional_fields() -> None:
    order = SalesOrder(
        order_no="SO-LONG-OPTIONAL",
        sold_at=datetime(2026, 4, 20, 10, 0, 0),
        store_name="上海一店",
        total_amount=9999,
        items=[
            SalesLineItem(
                barcode="6907777777777",
                style_no="STYLE-KEEP",
                unit_price=1500,
                brand="Brand-A",
                category="外套",
                image_url="https://img.example.com/keep.jpg",
            ),
            SalesLineItem(
                barcode="6908888888888",
                style_no="STYLE-DROP",
                unit_price=1600,
                brand="Brand-B",
                category="连衣裙",
                image_url="https://img.example.com/drop.jpg",
            ),
        ],
    )

    message = build_markdown_v2_message(
        order=order,
        filter_result=FilterResult(matched=True, reason="amount_threshold"),
        image_urls={},
        max_images=8,
        max_bytes=260,
    )

    assert len(message.encode("utf-8")) <= 260
    assert "商品明细已截断" in message
    assert "STYLE-DROP" not in message
    assert "Brand-B" not in message
    assert "连衣裙" not in message
    assert "https://img.example.com/drop.jpg" not in message
    if "STYLE-KEEP" not in message:
        assert "Brand-A" not in message
        assert "外套" not in message
        assert "https://img.example.com/keep.jpg" not in message


def test_message_builder_keeps_output_within_max_bytes_even_when_header_is_too_large() -> None:
    order = SalesOrder(
        order_no="SO-SMALL",
        sold_at=datetime(2026, 4, 20, 10, 0, 0),
        store_name="上海一店",
        total_amount=9999,
        items=[
            SalesLineItem(
                barcode="6909999999999",
                style_no="STYLE-SMALL",
                unit_price=999,
            ),
        ],
    )

    message = build_markdown_v2_message(
        order=order,
        filter_result=FilterResult(matched=True, reason="amount_threshold"),
        image_urls={},
        max_images=8,
        max_bytes=80,
    )

    assert len(message.encode("utf-8")) <= 80


def test_message_builder_rejects_negative_max_images() -> None:
    order = SalesOrder(
        order_no="SO-NEGATIVE",
        sold_at=datetime(2026, 4, 20, 10, 0, 0),
        store_name="上海一店",
        total_amount=1200,
        items=[
            SalesLineItem(
                barcode="6901010101010",
                style_no="NEG-1",
                unit_price=600,
                image_url="https://img.example.com/neg.jpg",
            ),
        ],
    )

    with pytest.raises(ValueError) as exc_info:
        build_markdown_v2_message(
            order=order,
            filter_result=FilterResult(matched=True, reason="manual_test"),
            image_urls={},
            max_images=-1,
        )

    assert "max_images" in str(exc_info.value)


def test_message_builder_hides_match_reason_and_renames_total_amount_label() -> None:
    order = SalesOrder(
        order_no="SO-010",
        sold_at=datetime(2026, 4, 20, 10, 0, 0),
        store_name="上海一店",
        total_amount=1200,
        items=[SalesLineItem(barcode="6901111111111", style_no="A1001", unit_price=699)],
    )

    settings = normalize_format_settings(
        {
            "preset": "standard",
            "fields": {
                "match_reason": {"enabled": False, "label": "命中原因"},
                "total_amount": {"enabled": True, "label": "成交金额"},
            },
        }
    )

    message = build_markdown_v2_message(
        order=order,
        filter_result=FilterResult(matched=True, reason="amount_threshold"),
        image_urls={},
        max_images=8,
        format_settings=settings,
    )

    assert "命中原因" not in message
    assert "成交金额" in message
    assert "总金额" not in message


def test_message_builder_uses_compact_preset_heading() -> None:
    order = SalesOrder(
        order_no="SO-011",
        sold_at=datetime(2026, 4, 20, 10, 0, 0),
        store_name="上海一店",
        total_amount=1200,
        items=[SalesLineItem(barcode="6901111111111", style_no="A1001", unit_price=699)],
    )

    settings = normalize_format_settings({"preset": "compact", "fields": {}})

    message = build_markdown_v2_message(
        order=order,
        filter_result=FilterResult(matched=True, reason="amount_threshold"),
        image_urls={},
        max_images=8,
        format_settings=settings,
    )

    assert "核心信息" in message or "**商品**" in message


def test_message_builder_renders_saved_template_body() -> None:
    order = SalesOrder(
        order_no="SO-300",
        sold_at=datetime(2026, 6, 5, 10, 50, 0),
        store_name="G609",
        total_amount=21500,
        salesperson="张三",
        items=[SalesLineItem(barcode="B1", style_no="S1", unit_price=21500)],
    )

    message = build_markdown_v2_message(
        order=order,
        filter_result=FilterResult(matched=True, reason="amount_threshold"),
        image_urls={"B1": "https://img.example.com/p1.jpg"},
        max_images=8,
        template_body="# 模板测试\n> {{ order.salesperson }}\n{% for item in order.items %}{{ item.style_no }} {{ item.image_url }}{% endfor %}",
    )

    assert "# 模板测试" in message
    assert "> 张三" in message
    assert "S1" in message
    assert "S1 https://img.example.com/p1.jpg" in message
