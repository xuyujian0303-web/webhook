from __future__ import annotations

import logging
from datetime import datetime

from wecom_sales_webhook_bot.message_builder import build_markdown_v2_message
from wecom_sales_webhook_bot.state_store import PushStateStore


LOGGER = logging.getLogger(__name__)


def run_once(
    data_source,
    sales_filter,
    image_provider,
    state_file,
    webhook_client,
    max_images: int,
    dry_run: bool,
) -> list[str]:
    state_store = PushStateStore(state_file)
    last_scan_at = state_store.get_last_scan_at()
    sent_orders: list[str] = []

    try:
        orders = data_source.load_orders()
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("failed to load csv orders: %s", exc)
        return []

    for order in orders:
        if last_scan_at and order.sold_at <= last_scan_at:
            continue
        if state_store.has_pushed(order.order_no):
            continue

        filter_result = sales_filter.evaluate(order)
        if not filter_result.matched:
            continue

        image_urls = {}
        for item in order.items:
            url = image_provider.get_url(item.barcode)
            if url:
                image_urls[item.barcode] = url

        content = build_markdown_v2_message(
            order=order,
            filter_result=filter_result,
            image_urls=image_urls,
            max_images=max_images,
        )
        if not dry_run:
            webhook_client.send_markdown_v2(content)
        state_store.mark_pushed(order.order_no, order.sold_at)
        sent_orders.append(order.order_no)

    state_store.set_last_scan_at(datetime.now())
    return sent_orders
