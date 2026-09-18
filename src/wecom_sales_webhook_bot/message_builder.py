from __future__ import annotations

from pathlib import Path

from wecom_sales_webhook_bot.format_settings import normalize_format_settings
from wecom_sales_webhook_bot.filters import FilterResult
from wecom_sales_webhook_bot.message_template_engine import render_message_template
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder

PRESET_LAYOUTS = {
    "standard": {
        "summary_heading": "成交摘要",
        "show_summary_heading": True,
        "item_heading": "商品信息",
    },
    "compact": {
        "summary_heading": "核心信息",
        "show_summary_heading": False,
        "item_heading": "商品",
    },
    "detailed": {
        "summary_heading": "订单摘要",
        "show_summary_heading": True,
        "item_heading": "商品明细",
    },
}


def _format_reason(reason: str | None) -> str:
    mapping = {
        "amount_threshold": "高金额命中",
        "style_whitelist": "款号命中",
        "manual_test": "手动测试",
    }
    if reason is None:
        return "未命中"
    return mapping.get(reason, reason)


def _resolve_image_url(item: SalesLineItem, image_urls: dict[str, str]) -> str | None:
    return image_urls.get(item.barcode) or item.image_url


def _join_lines(lines: list[str]) -> str:
    return "\n".join(lines)


def _trim_lines_to_max_bytes(lines: list[str], max_bytes: int) -> str:
    trimmed = list(lines)
    while trimmed and len(_join_lines(trimmed).encode("utf-8")) > max_bytes:
        trimmed.pop()
    return _join_lines(trimmed)


def _field_enabled(settings: dict, field_name: str) -> bool:
    return settings["fields"][field_name]["enabled"]


def _field_label(settings: dict, field_name: str) -> str:
    return settings["fields"][field_name]["label"]


def _resolve_order_image_urls(
    order: SalesOrder,
    image_urls: dict[str, str],
) -> dict[str, str]:
    resolved_image_urls: dict[str, str] = {}
    for item in order.items:
        resolved_image_url = _resolve_image_url(item, image_urls)
        if resolved_image_url:
            resolved_image_urls[item.barcode] = resolved_image_url
    return resolved_image_urls


def _displayed_barcodes(
    order: SalesOrder,
    resolved_image_urls: dict[str, str],
    max_images: int,
) -> tuple[list[str], set[str], int]:
    unique_barcodes: list[str] = []
    for item in order.items:
        if item.barcode in resolved_image_urls and item.barcode not in unique_barcodes:
            unique_barcodes.append(item.barcode)

    displayed = unique_barcodes[:max_images]
    return displayed, set(displayed), len(unique_barcodes) - len(displayed)


def _image_markdown(style_no: str, url: str) -> str:
    suffix = Path(url.split("?", 1)[0]).suffix or ".jpg"
    return f"![{style_no}{suffix}]({url})"


def _build_items_markdown(
    order: SalesOrder,
    image_urls: dict[str, str],
    max_images: int,
) -> str:
    resolved_image_urls = _resolve_order_image_urls(order, image_urls)
    _, displayed_set, omitted = _displayed_barcodes(order, resolved_image_urls, max_images)

    lines: list[str] = []
    for item in order.items:
        lines.append(f"- **款号**：`{item.style_no}`")
        lines.append(f"  单价：`{item.unit_price:.2f}`")
        lines.append(f"  条码：`{item.barcode}`")
        if item.brand:
            lines.append(f"  品牌：`{item.brand}`")
        if item.category:
            lines.append(f"  类别：`{item.category}`")
        if item.barcode in displayed_set:
            lines.append(f"  {_image_markdown(item.style_no, resolved_image_urls[item.barcode])}")
        elif item.barcode in resolved_image_urls:
            lines.append("  > 图片未展示")
        else:
            lines.append("  > 暂无图片")
        lines.append("")

    if omitted > 0:
        lines.append(f"> 还有 {omitted} 张图片未展示")

    return _join_lines(lines).strip()


def _build_legacy_message(
    order: SalesOrder,
    filter_result: FilterResult,
    image_urls: dict[str, str],
    max_images: int,
    max_bytes: int,
    format_settings: dict | None,
) -> str:
    settings = normalize_format_settings(format_settings)
    preset = PRESET_LAYOUTS[settings["preset"]]

    header = ["# 零售晒单"]
    if preset["show_summary_heading"]:
        header.append(f"## {preset['summary_heading']}")

    summary_lines: list[str] = []
    if _field_enabled(settings, "order_no"):
        summary_lines.append(
            f"> **{_field_label(settings, 'order_no')}**：`{order.order_no}`"
        )
    if _field_enabled(settings, "store_name"):
        summary_lines.append(
            f"> **{_field_label(settings, 'store_name')}**：`{order.store_name}`"
        )
    if _field_enabled(settings, "performance_org"):
        summary_lines.append(
            f"> **{_field_label(settings, 'performance_org')}**：`{order.performance_org or ''}`"
        )
    if _field_enabled(settings, "sold_at"):
        summary_lines.append(
            f"> **{_field_label(settings, 'sold_at')}**：`{order.sold_at:%Y-%m-%d %H:%M:%S}`"
        )
    if _field_enabled(settings, "total_amount"):
        summary_lines.append(
            f"> **{_field_label(settings, 'total_amount')}**：`{order.total_amount:.2f}`"
        )
    if _field_enabled(settings, "match_reason"):
        summary_lines.append(
            f"> **{_field_label(settings, 'match_reason')}**：`{_format_reason(filter_result.reason)}`"
        )

    if summary_lines:
        header.extend(summary_lines)
        header.append("")
    header.append(f"**{preset['item_heading']}**")

    resolved_image_urls = _resolve_order_image_urls(order, image_urls)
    _, displayed_set, omitted = _displayed_barcodes(order, resolved_image_urls, max_images)

    item_blocks: list[list[str]] = []
    for item in order.items:
        block: list[str] = []
        if _field_enabled(settings, "style_no"):
            block.append(f"- **{_field_label(settings, 'style_no')}**：`{item.style_no}`")
        if _field_enabled(settings, "unit_price"):
            block.append(
                f"  {_field_label(settings, 'unit_price')}：`{item.unit_price:.2f}`"
            )
        if _field_enabled(settings, "barcode"):
            block.append(f"  {_field_label(settings, 'barcode')}：`{item.barcode}`")
        if item.brand and _field_enabled(settings, "brand"):
            block.append(f"  {_field_label(settings, 'brand')}：`{item.brand}`")
        if item.category and _field_enabled(settings, "category"):
            block.append(f"  {_field_label(settings, 'category')}：`{item.category}`")
        if _field_enabled(settings, "image"):
            if item.barcode in displayed_set:
                block.append(f"  {_image_markdown(item.style_no, resolved_image_urls[item.barcode])}")
            elif item.barcode in resolved_image_urls:
                block.append("  > 图片未展示")
            else:
                block.append("  > 暂无图片")
        block.append("")
        item_blocks.append(block)

    footer_lines: list[str] = []
    if omitted > 0:
        footer_lines.append(f"> 还有 {omitted} 张图片未展示")

    detail_lines = [line for block in item_blocks for line in block]
    lines = header + detail_lines + footer_lines
    while len(_join_lines(lines).encode("utf-8")) > max_bytes and item_blocks:
        item_blocks = item_blocks[:-1]
        detail_lines = [line for block in item_blocks for line in block]
        lines = header + detail_lines + ["> 商品明细已截断"] + footer_lines

    return _trim_lines_to_max_bytes(lines, max_bytes)


def build_markdown_v2_message(
    order: SalesOrder,
    filter_result: FilterResult,
    image_urls: dict[str, str],
    max_images: int,
    max_bytes: int = 4096,
    format_settings: dict | None = None,
    template_body: str | None = None,
) -> str:
    if max_images < 0:
        raise ValueError("max_images must be >= 0")
    if max_bytes < 0:
        raise ValueError("max_bytes must be >= 0")

    if template_body is not None:
        rendered = render_message_template(
            template_body,
            {
                "order": {
                    "order_no": order.order_no,
                    "store_name": order.store_name_display or order.store_name,
                    "performance_org": order.performance_org_display or order.performance_org or "",
                    "store_name_display": order.store_name_display or order.store_name,
                    "performance_org_display": order.performance_org_display or order.performance_org or "",
                    "sold_at": order.sold_at,
                    "total_amount": order.total_amount,
                    "salesperson": order.salesperson or "",
                    "total_quantity": order.total_quantity or "",
                    "customer_source": order.customer_source or "",
                    "promotion_material": order.promotion_material or "",
                    "card_type": order.card_type or "",
                    "activity_type": order.activity_type or "",
                    "match_reason": _format_reason(filter_result.reason),
                    "items": [
                        {
                            "barcode": item.barcode,
                            "style_no": item.style_no,
                            "unit_price": item.unit_price,
                            "brand": item.brand or "",
                            "category": item.category or "",
                            "image_url": _resolve_image_url(item, image_urls) or "",
                            "image_markdown": _image_markdown(item.style_no, _resolve_image_url(item, image_urls)) if _resolve_image_url(item, image_urls) else "",
                        }
                        for item in order.items
                    ],
                },
            },
        )
        if rendered.byte_length <= max_bytes:
            return rendered.text
        return _trim_lines_to_max_bytes(rendered.text.splitlines(), max_bytes)

    return _build_legacy_message(
        order=order,
        filter_result=filter_result,
        image_urls=image_urls,
        max_images=max_images,
        max_bytes=max_bytes,
        format_settings=format_settings,
    )
