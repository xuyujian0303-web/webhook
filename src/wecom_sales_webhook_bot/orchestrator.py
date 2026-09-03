from __future__ import annotations

import logging
import time
from datetime import datetime

from wecom_sales_webhook_bot.filters import FilterResult
from wecom_sales_webhook_bot.message_builder import build_markdown_v2_message
from wecom_sales_webhook_bot.rule_service import evaluate_rule_group
from wecom_sales_webhook_bot.runtime_settings import RuntimeControls, is_within_push_window, load_runtime_settings
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
    format_settings: dict | None = None,
    template_body: str | None = None,
    database_rule_groups=None,
    database_url: str | None = None,
    push_interval_seconds: int = 0,
    runtime_controls: RuntimeControls | None = None,
    service_started_at: datetime | None = None,
    now_func=datetime.now,
    sleep_func=time.sleep,
) -> list[str]:
    if database_url is not None:
        database_rule_groups, database_template_body = load_runtime_settings(database_url)
        template_body = database_template_body

    state_store = PushStateStore(state_file)
    service_started_at = service_started_at or now_func()
    sent_orders: list[str] = []

    try:
        orders = data_source.load_orders()
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("failed to load csv orders: %s", exc)
        return []

    pending_orders: list[tuple[object, FilterResult]] = []
    for order in orders:
        if state_store.has_pushed(order.order_no):
            continue

        if database_rule_groups is not None:
            matched_group = next(
                (group for group in database_rule_groups if evaluate_rule_group(order, group, default_start_date=service_started_at.date())),
                None,
            )
            if matched_group is None:
                continue
            filter_result = FilterResult(matched=True, reason=matched_group.name)
        else:
            filter_result = sales_filter.evaluate(order)
            if not filter_result.matched:
                continue

        pending_orders.append((order, filter_result))

    if runtime_controls is not None and not is_within_push_window(now_func(), runtime_controls):
        return []

    for index, (order, filter_result) in enumerate(pending_orders):
        image_urls = {}
        for item in order.items:
            url = image_provider.get_url(item.barcode)
            if not url:
                url = image_provider.get_url(item.style_no)
            if url:
                image_urls[item.barcode] = url

        content = build_markdown_v2_message(
            order=order,
            filter_result=filter_result,
            image_urls=image_urls,
            max_images=max_images,
            format_settings=format_settings,
            template_body=template_body,
        )
        if not dry_run:
            webhook_client.send_markdown_v2(content)
        state_store.mark_pushed(order.order_no, order.sold_at)
        sent_orders.append(order.order_no)

        if (
            not dry_run
            and push_interval_seconds > 0
            and index < len(pending_orders) - 1
        ):
            sleep_func(push_interval_seconds)

    state_store.set_last_scan_at(now_func())
    return sent_orders


