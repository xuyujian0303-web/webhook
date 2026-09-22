from __future__ import annotations

import logging
import time
from dataclasses import replace
from datetime import datetime

from wecom_sales_webhook_bot.filters import FilterResult
from wecom_sales_webhook_bot.message_builder import build_markdown_v2_message
from wecom_sales_webhook_bot.rule_service import evaluate_rule_group
from wecom_sales_webhook_bot.runtime_settings import RuntimeControls, is_within_push_window, load_runtime_settings
from wecom_sales_webhook_bot.db import create_session_factory, initialize_database
from wecom_sales_webhook_bot.rule_models import JobRun, PushRecord
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
    store_name_mapping: dict[str, str] | None = None,
) -> list[str]:
    if database_url is not None:
        database_rule_groups, database_template_body = load_runtime_settings(database_url)
        template_body = database_template_body

    state_store = PushStateStore(state_file)
    service_started_at = service_started_at or now_func()
    sent_orders: list[str] = []
    failed_orders = 0
    db_session = None
    if database_url is not None:
        session_factory = create_session_factory(database_url)
        initialize_database(session_factory)
        db_session = session_factory()

    try:
        # Use the previous scan timestamp as the lower bound so an EMS scan
        # can recover records created since the last cycle.  The source keeps
        # the exact wire-level query implementation; the orchestrator only
        # supplies a date window.
        last_scan = state_store.get_last_scan_at()
        scan_start = service_started_at if last_scan is None else min(last_scan, service_started_at)
        scan_end = now_func()
        query_kwargs = {"start_at": scan_start, "end_at": scan_end}
        local_rule_groups = database_rule_groups
        # A single enabled ALL-rule can safely be pushed down to the EMS
        # adapter. OR-rules must stay post-query or valid orders could be lost.
        if database_rule_groups and len(database_rule_groups) == 1:
            group = database_rule_groups[0]
            if getattr(group, "match_mode", None) == "all":
                conditions = getattr(group, "conditions", [])
                amount = next((float(c.value) for c in conditions
                               if c.field_name == "total_amount" and c.operator in {"gt", "gte"}), None)
                discount = next((float(c.value) for c in conditions
                                 if c.field_name in {"discount", "actual_discount"} and c.operator in {"gt", "gte"}), None)
                unit_price = next((float(c.value) for c in conditions
                                   if c.field_name == "unit_price" and c.operator in {"gt", "gte"}), None)
                seasons = next((set(c.value if isinstance(c.value, list) else str(c.value).split(",")) for c in conditions
                                if c.field_name == "season" and c.operator in {"equals", "in"}), None)
                shipment_groups = next((set(c.value if isinstance(c.value, list) else str(c.value).split(",")) for c in conditions
                                        if c.field_name == "shipment_group" and c.operator in {"equals", "in"}), None)
                stores = next((set(c.value if isinstance(c.value, list) else str(c.value).split(",")) for c in conditions
                               if c.field_name == "store_name" and c.operator == "in"), None)
                doc_types = next((set(c.value if isinstance(c.value, list) else str(c.value).split(",")) for c in conditions
                                  if c.field_name == "document_type" and c.operator == "in"), None)
                if amount is not None: query_kwargs["amount_threshold"] = amount
                if discount is not None: query_kwargs["unit_discount_threshold"] = discount
                if unit_price is not None: query_kwargs["unit_price_threshold"] = unit_price
                if seasons: query_kwargs["seasons"] = {x.strip() for x in seasons if x.strip()}
                if shipment_groups: query_kwargs["shipment_groups"] = {x.strip() for x in shipment_groups if x.strip()}
                query_kwargs["return_whole_order"] = bool(getattr(runtime_controls, "return_whole_order", True))
                # Query hints are optional for adapters. Keep the original
                # conditions for the local check so an adapter that ignores a
                # hint cannot accidentally turn an unmatched order into a
                # match.
                local_rule_groups = [group]
                if stores: query_kwargs["store_names"] = {x.strip() for x in stores if x.strip()}
                if doc_types: query_kwargs["document_types"] = {x.strip() for x in doc_types if x.strip()}
        try:
            orders = data_source.load_orders(**query_kwargs)
            LOGGER.info("loaded %d orders; dates=%s", len(orders), sorted({order.sold_at.date().isoformat() for order in orders}))
        except TypeError:
            # Backwards compatibility for legacy CSV/API data sources.
            orders = data_source.load_orders()
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("failed to load sales orders: %s", exc)
        if db_session is not None:
            db_session.add(JobRun(window_start=service_started_at.isoformat(), window_end=now_func().isoformat(), status="failed", success_count=0, failed_count=1, error_summary=str(exc)))
            db_session.commit()
            db_session.close()
        return []

    pending_orders: list[tuple[object, FilterResult]] = []
    seen_order_nos: set[str] = set()
    for order in orders:
        if store_name_mapping:
            order = replace(order,
                            store_name_display=store_name_mapping.get(order.store_name, order.store_name),
                            performance_org_display=store_name_mapping.get(order.performance_org or "", order.performance_org or ""))
        if order.order_no in seen_order_nos or state_store.has_pushed(order.order_no):
            continue
        seen_order_nos.add(order.order_no)

        if local_rule_groups is not None:
            matched_group = next(
                (group for group in local_rule_groups if evaluate_rule_group(order, group, default_start_date=service_started_at.date())),
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
        if db_session is not None:
            db_session.add(JobRun(window_start=service_started_at.isoformat(), window_end=now_func().isoformat(), status="deferred", success_count=0, failed_count=0, error_summary="outside push window"))
            db_session.commit()
            db_session.close()
        return []

    for index, (order, filter_result) in enumerate(pending_orders):
        image_urls = {}
        for item in order.items:
            # Prefer EMS URLs; 127.0.0.1 image URLs cannot be fetched by WeCom.
            url = item.image_url or image_provider.get_url(item.barcode)
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
        try:
            if not dry_run:
                webhook_client.send_markdown_v2(content)
        except Exception as exc:  # noqa: BLE001
            failed_orders += 1
            LOGGER.error("failed to push order %s: %s", order.order_no, exc)
            if db_session is not None:
                db_session.add(PushRecord(order_no=order.order_no, store_name=order.store_name,
                                          total_amount=order.total_amount,
                                          rule_name=filter_result.reason or "matched",
                                          status="failed", error_message=str(exc)))
                db_session.commit()
            if db_session is None:
                raise
            continue
        if not dry_run:
            state_store.mark_pushed(order.order_no, order.sold_at)
        if db_session is not None and not dry_run:
            existing_record = db_session.query(PushRecord).filter_by(order_no=order.order_no).first()
            if existing_record is None:
                db_session.add(PushRecord(order_no=order.order_no, store_name=order.store_name, total_amount=order.total_amount, rule_name=filter_result.reason or "matched", status="success"))
                db_session.commit()
        sent_orders.append(order.order_no)

        if (
            not dry_run
            and push_interval_seconds > 0
            and index < len(pending_orders) - 1
        ):
            sleep_func(push_interval_seconds)

    state_store.set_last_scan_at(now_func())
    if db_session is not None:
        db_session.add(JobRun(window_start=service_started_at.isoformat(), window_end=now_func().isoformat(), status="failed" if failed_orders else "success", success_count=len(sent_orders), failed_count=failed_orders))
        db_session.commit()
        db_session.close()
    return sent_orders


