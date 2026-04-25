from __future__ import annotations

from wecom_sales_webhook_bot.filters import FilterResult
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder


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


def build_markdown_v2_message(
    order: SalesOrder,
    filter_result: FilterResult,
    image_urls: dict[str, str],
    max_images: int,
    max_bytes: int = 4096,
) -> str:
    header = [
        "# 零售晒单",
        "## 成交摘要",
        f"> **销售单号**：`{order.order_no}`",
        f"> **门店**：`{order.store_name}`",
        f"> **时间**：`{order.sold_at:%Y-%m-%d %H:%M:%S}`",
        f"> **总额**：`{order.total_amount:.2f}`",
        f"> **命中原因**：`{_format_reason(filter_result.reason)}`",
        "",
        "**商品信息**",
    ]

    resolved_image_urls: dict[str, str] = {}
    for item in order.items:
        resolved_image_url = _resolve_image_url(item, image_urls)
        if resolved_image_url:
            resolved_image_urls[item.barcode] = resolved_image_url

    unique_barcodes: list[str] = []
    for item in order.items:
        if item.barcode in resolved_image_urls and item.barcode not in unique_barcodes:
            unique_barcodes.append(item.barcode)

    displayed = unique_barcodes[:max_images]
    displayed_set = set(displayed)

    omitted = len(unique_barcodes) - len(displayed)
    item_blocks: list[list[str]] = []
    for item in order.items:
        block = [
            f"- **款号**：`{item.style_no}`",
            f"  单价：`{item.unit_price:.2f}`",
            f"  条码：`{item.barcode}`",
        ]
        if item.brand:
            block.append(f"  品牌：`{item.brand}`")
        if item.category:
            block.append(f"  类别：`{item.category}`")
        if item.barcode in displayed_set:
            block.append(f"  ![]({resolved_image_urls[item.barcode]})")
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
    while len("\n".join(lines).encode("utf-8")) > max_bytes and item_blocks:
        item_blocks = item_blocks[:-1]
        detail_lines = [line for block in item_blocks for line in block]
        lines = header + detail_lines + ["> 商品明细已截断"] + footer_lines

    return "\n".join(lines)
