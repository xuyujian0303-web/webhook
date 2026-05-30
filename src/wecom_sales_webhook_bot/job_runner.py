from __future__ import annotations

from datetime import datetime

from wecom_sales_webhook_bot.db import create_session_factory, initialize_database
from wecom_sales_webhook_bot.filters import FilterResult
from wecom_sales_webhook_bot.message_builder import build_markdown_v2_message
from wecom_sales_webhook_bot.rule_models import JobRun, PushRecord
from wecom_sales_webhook_bot.rule_service import evaluate_rule_group


def run_scan_cycle(
    database_url: str,
    source,
    rule_groups,
    webhook_client,
    start_at: datetime,
    end_at: datetime,
    max_images: int,
) -> list[str]:
    session_factory = create_session_factory(database_url)
    initialize_database(session_factory)

    sent_orders: list[str] = []
    with session_factory() as session:
        for order in source.load_orders(start_at=start_at, end_at=end_at):
            exists = (
                session.query(PushRecord)
                .filter_by(order_no=order.order_no, status="success")
                .first()
            )
            if exists:
                continue

            matched_group = next(
                (group for group in rule_groups if evaluate_rule_group(order, group)),
                None,
            )
            if matched_group is None:
                continue

            message = build_markdown_v2_message(
                order=order,
                filter_result=FilterResult(matched=True, reason="rule_group"),
                image_urls={},
                max_images=max_images,
            )
            webhook_client.send_markdown_v2(message)
            session.add(
                PushRecord(
                    order_no=order.order_no,
                    store_name=order.store_name,
                    total_amount=order.total_amount,
                    rule_name=matched_group.name,
                    status="success",
                )
            )
            sent_orders.append(order.order_no)

        session.add(
            JobRun(
                window_start=start_at.isoformat(),
                window_end=end_at.isoformat(),
                status="success",
                success_count=len(sent_orders),
                failed_count=0,
            )
        )
        session.commit()

    return sent_orders
