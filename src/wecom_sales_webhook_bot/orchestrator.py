from __future__ import annotations

import logging
import inspect
import time
from dataclasses import replace
from datetime import date, datetime

from wecom_sales_webhook_bot.filters import FilterResult
from wecom_sales_webhook_bot.message_builder import build_markdown_v2_message
from wecom_sales_webhook_bot.rule_service import evaluate_rule_group, normalize_document_type
from wecom_sales_webhook_bot.runtime_settings import RuntimeControls, is_within_push_window, load_runtime_settings
from wecom_sales_webhook_bot.db import create_session_factory, initialize_database
from wecom_sales_webhook_bot.rule_models import JobRun, PushRecord
from wecom_sales_webhook_bot.state_store import PushStateStore


LOGGER = logging.getLogger(__name__)


def _condition_values(condition) -> list[str]:
    value = condition.value
    return [str(item).strip() for item in value] if isinstance(value, list) else [
        item.strip() for item in str(value).split(",")
    ]


def _numeric_bounds(conditions, field_name: str) -> tuple[float | None, float | None] | None:
    low = high = None
    found = False
    for condition in conditions:
        if condition.field_name != field_name:
            continue
        values = _condition_values(condition)
        try:
            if condition.operator == "between" and len(values) == 2:
                low, high = float(values[0]), float(values[1])
                found = True
            elif condition.operator == "equals" and values and values[0]:
                low = high = float(values[0])
                found = True
            elif condition.operator in {"gt", "gte"} and values and values[0]:
                value = float(values[0])
                low = value if low is None else max(low, value)
                found = True
            elif condition.operator in {"lt", "lte"} and values and values[0]:
                value = float(values[0])
                high = value if high is None else min(high, value)
                found = True
        except ValueError:
            continue
    return (low, high) if found else None


def _parse_rule_date(value: str) -> date | None:
    text = value.strip().replace("/", "-")
    for pattern in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    return None


def _rule_date_window(conditions, start_at: datetime, end_at: datetime) -> tuple[datetime, datetime]:
    start_day, end_day = start_at.date(), end_at.date()
    for condition in conditions:
        if condition.field_name != "sold_at":
            continue
        values = _condition_values(condition)
        if condition.operator in {"after", "gt", "gte", "equals"} and values:
            parsed = _parse_rule_date(values[0])
            if parsed:
                start_day = max(start_day, parsed)
        if condition.operator in {"before", "lt", "lte", "equals"} and values:
            parsed = _parse_rule_date(values[0])
            if parsed:
                end_day = min(end_day, parsed)
        elif condition.operator in {"date_between", "date_range", "between"}:
            bounds = (values + ["", ""])[:2]
            low = _parse_rule_date(bounds[0]) if bounds[0] else None
            high = _parse_rule_date(bounds[1]) if bounds[1] else None
            if low:
                start_day = max(start_day, low)
            if high:
                end_day = min(end_day, high)
    return (
        datetime.combine(start_day, datetime.min.time()),
        datetime.combine(end_day, datetime.max.time()),
    )


def _condition_group(condition, default_mode: str) -> str:
    return condition.condition_group if condition.condition_group in {"all", "any"} else default_mode


def _server_document_type_filter(rule_groups) -> set[str]:
    allowed: set[str] = set()
    for group in rule_groups:
        conditions = getattr(group, "conditions", [])
        mode = getattr(group, "match_mode", "all")
        grouped = {
            key: [c for c in conditions if _condition_group(c, mode) == key]
            for key in ("all", "any")
        }
        any_conditions = grouped["any"]
        any_document_types = [c for c in any_conditions if c.field_name == "document_type"]
        if any(c.field_name != "document_type" for c in any_conditions):
            return set()
        if any_document_types:
            selected_conditions = any_document_types
        else:
            selected_conditions = [
                c for c in grouped["all"] if c.field_name == "document_type"
            ]
            if not selected_conditions:
                allowed.add("sale")
                continue
        for condition in selected_conditions:
            if condition.operator not in {"equals", "in"}:
                return set()
            allowed.update(
                normalize_document_type(value)
                for value in _condition_values(condition)
                if value
            )
    return allowed


def _load_orders(data_source, query_kwargs):
    parameters = inspect.signature(data_source.load_orders).parameters
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
        return data_source.load_orders(**query_kwargs)
    supported = {key: value for key, value in query_kwargs.items() if key in parameters}
    return data_source.load_orders(**supported)


def _query_kwargs_for_rule(
    rule_group,
    scan_start: datetime,
    scan_end: datetime,
    runtime_controls: RuntimeControls | None,
) -> dict:
    """Build one EMS query from one rule without mixing other rules into it."""
    conditions = getattr(rule_group, "conditions", [])
    query_kwargs = {
        "start_at": scan_start,
        "end_at": scan_end,
        "return_whole_order": bool(getattr(runtime_controls, "return_whole_order", True)),
    }
    document_types = _server_document_type_filter([rule_group])
    if document_types is not None:
        query_kwargs["document_types"] = document_types

    if not all(
        _condition_group(condition, getattr(rule_group, "match_mode", "all")) == "all"
        for condition in conditions
    ):
        return query_kwargs

    amount = _numeric_bounds(conditions, "total_amount")
    unit_price = _numeric_bounds(conditions, "unit_price")
    discount = _numeric_bounds(conditions, "discount")
    seasons = next(
        (
            set(_condition_values(condition))
            for condition in conditions
            if condition.field_name == "season"
            and condition.operator in {"equals", "in"}
        ),
        None,
    )
    shipment_groups = next(
        (
            set(_condition_values(condition))
            for condition in conditions
            if condition.field_name == "shipment_group"
            and condition.operator in {"equals", "in"}
        ),
        None,
    )
    stores = next(
        (
            set(_condition_values(condition))
            for condition in conditions
            if condition.field_name == "store_name"
            and condition.operator in {"equals", "in"}
        ),
        None,
    )
    style_numbers = next(
        (
            set(_condition_values(condition))
            for condition in conditions
            if condition.field_name == "style_no"
            and condition.operator in {"equals", "in", "contains"}
        ),
        None,
    )
    if amount is not None:
        query_kwargs["amount_range"] = amount
    if discount is not None:
        query_kwargs["unit_discount_range"] = discount
    if unit_price is not None:
        query_kwargs["unit_price_range"] = unit_price
    if seasons:
        query_kwargs["seasons"] = {value.strip() for value in seasons if value.strip()}
    if shipment_groups:
        query_kwargs["shipment_groups"] = {
            value.strip() for value in shipment_groups if value.strip()
        }
    if style_numbers:
        query_kwargs["style_numbers"] = {
            value.strip() for value in style_numbers if value.strip()
        }
    query_kwargs["start_at"], query_kwargs["end_at"] = _rule_date_window(
        conditions,
        query_kwargs["start_at"],
        query_kwargs["end_at"],
    )
    if stores:
        query_kwargs["store_names"] = {
            value.strip().upper() for value in stores if value.strip()
        }
    return query_kwargs


def _server_query_orders(
    data_source,
    rule_groups,
    scan_start: datetime,
    scan_end: datetime,
    runtime_controls: RuntimeControls | None,
) -> tuple[list[tuple[object, object]], list[str]]:
    """Query each rule independently and return orders tagged with that rule."""
    matched_orders: list[tuple[object, object]] = []
    errors: list[str] = []
    for rule_group in rule_groups:
        query_kwargs = _query_kwargs_for_rule(
            rule_group,
            scan_start,
            scan_end,
            runtime_controls,
        )
        try:
            orders = _load_orders(data_source, query_kwargs)
            LOGGER.info(
                "loaded %d orders for rule %s; dates=%s",
                len(orders),
                getattr(rule_group, "name", "<unnamed>"),
                sorted({order.sold_at.date().isoformat() for order in orders}),
            )
        except Exception as exc:  # noqa: BLE001
            message = f"{getattr(rule_group, 'name', '<unnamed>')}: {exc}"
            errors.append(message)
            LOGGER.error("failed to load sales orders for rule %s: %s", getattr(rule_group, "name", "<unnamed>"), exc)
            continue
        matched_orders.extend((order, rule_group) for order in orders)
    return matched_orders, errors


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

    query_errors: list[str] = []
    try:
        # Use the previous scan timestamp as the lower bound so an EMS scan
        # can recover records created since the last cycle.  The source keeps
        # the exact wire-level query implementation; the orchestrator only
        # supplies a date window.
        last_scan = state_store.get_last_scan_at()
        scan_start = service_started_at if last_scan is None else min(last_scan, service_started_at)
        scan_end = now_func()
        if database_rule_groups:
            queried_orders = _server_query_orders(
                data_source,
                database_rule_groups,
                scan_start,
                scan_end,
                runtime_controls,
            )
            orders_with_rules, query_errors = queried_orders
        else:
            orders_with_rules = [
                (order, None)
                for order in _load_orders(
                    data_source,
                    {"start_at": scan_start, "end_at": scan_end},
                )
            ]
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("failed to load sales orders: %s", exc)
        query_errors.append(str(exc))
        orders_with_rules = []

    if not orders_with_rules and query_errors:
        if db_session is not None:
            db_session.add(JobRun(
                window_start=service_started_at.isoformat(),
                window_end=now_func().isoformat(),
                status="failed",
                success_count=0,
                failed_count=len(query_errors),
                error_summary="; ".join(query_errors),
            ))
            db_session.commit()
            db_session.close()
        return []

    pending_orders: list[tuple[object, FilterResult]] = []
    seen_order_nos: set[str] = set()
    normalized_mapping = {
        str(key).strip().upper(): str(value).strip()
        for key, value in (store_name_mapping or {}).items()
        if str(key).strip() and str(value).strip()
    }
    selected_by_order_no: dict[str, tuple[object, FilterResult]] = {}
    for order, queried_rule in orders_with_rules:
        if normalized_mapping:
            order = replace(order,
                            store_name_display=normalized_mapping.get(
                                str(order.store_name).strip().upper(),
                                order.store_name,
                            ),
                            performance_org_display=normalized_mapping.get(
                                str(order.performance_org or "").strip().upper(),
                                order.performance_org or "",
                            ))
        if order.order_no in seen_order_nos or state_store.has_pushed(order.order_no):
            continue

        if queried_rule is not None:
            server_filtered_fields = set(order.attributes.get("_ems_server_filtered_fields", ()))
            if not evaluate_rule_group(
                order,
                queried_rule,
                default_start_date=service_started_at.date(),
                server_filtered_fields=server_filtered_fields,
            ):
                continue
            filter_result = FilterResult(matched=True, reason=queried_rule.name)
        elif database_rule_groups is not None:
            continue
        else:
            filter_result = sales_filter.evaluate(order)
            if not filter_result.matched:
                continue
        seen_order_nos.add(order.order_no)
        selected_by_order_no[order.order_no] = (order, filter_result)

    pending_orders = list(selected_by_order_no.values())

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
        db_session.add(JobRun(
            window_start=service_started_at.isoformat(),
            window_end=now_func().isoformat(),
            status="failed" if query_errors or failed_orders else "success",
            success_count=len(sent_orders),
            failed_count=len(query_errors) + failed_orders,
            error_summary="; ".join(query_errors) if query_errors else None,
        ))
        db_session.commit()
        db_session.close()
    return sent_orders


