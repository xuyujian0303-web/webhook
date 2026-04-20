from __future__ import annotations

from wecom_sales_webhook_bot.filters import FilterResult
from wecom_sales_webhook_bot.models import SalesOrder


def build_markdown_v2_message(
    order: SalesOrder,
    filter_result: FilterResult,
    image_urls: dict[str, str],
    max_images: int,
) -> str:
    lines = [
        "# 销售晒单",
        f"> 销售单号：`{order.order_no}`",
        f"> 销售时间：`{order.sold_at:%Y-%m-%d %H:%M:%S}`",
        f"> 门店：`{order.store_name}`",
        f"> 总额：`{order.total_amount:.2f}`",
        f"> 命中原因：`{filter_result.reason}`",
        "",
        "## 商品明细",
    ]

    for item in order.items:
        lines.append(
            f"- 条码：`{item.barcode}` 款号：`{item.style_no}` 单价：`{item.unit_price:.2f}` 数量：`{item.quantity}`"
        )

    lines.append("")
    lines.append("## 商品图片")

    unique_barcodes: list[str] = []
    for item in order.items:
        if item.barcode in image_urls and item.barcode not in unique_barcodes:
            unique_barcodes.append(item.barcode)

    displayed = unique_barcodes[:max_images]
    for barcode in displayed:
        lines.append(f"![]({image_urls[barcode]})")

    omitted = len(unique_barcodes) - len(displayed)
    if omitted > 0:
        lines.append(f"> 还有 {omitted} 张图片未展示")

    missing = [item.barcode for item in order.items if item.barcode not in image_urls]
    if missing:
        lines.append(f"> 缺失图片条码：{', '.join(missing)}")

    return "\n".join(lines)
