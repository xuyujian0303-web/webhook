from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from wecom_sales_webhook_bot.celebration import CelebrationStateStore, qualifies_for_celebration
from wecom_sales_webhook_bot.celebration_memory import CelebrationImage, generate_celebration_image_memory


LOGGER = logging.getLogger(__name__)


def deliver_celebrations(
    *,
    orders: list[object],
    settings: dict | None,
    targets: dict[str, object] | None,
    state_file: Path,
    dry_run: bool,
    in_push_window: bool,
    scan_start,
    scan_end,
    store_name_mapping: dict[str, str] | None,
    now_func,
    generator=generate_celebration_image_memory,
) -> tuple[int, list[str]]:
    """Send celebration images after the ordinary sales messages are done."""
    if not (settings and settings.get("enabled") and orders and not dry_run and in_push_window):
        return 0, []
    selected_targets = targets or {}
    if not selected_targets:
        return 0, ["喜报未推送：没有选择可用的 Webhook 目标"]

    state = CelebrationStateStore(Path(state_file).with_name("celebration-state.json"))
    normalized_mapping = {
        str(key).strip().upper(): str(value).strip()
        for key, value in (store_name_mapping or {}).items()
        if str(key).strip() and str(value).strip()
    }
    sent_count = 0
    errors: list[str] = []
    seen_orders: set[str] = set()

    for raw_order in orders:
        if raw_order.order_no in seen_orders:
            continue
        seen_orders.add(raw_order.order_no)
        if not (scan_start.date() <= raw_order.sold_at.date() <= scan_end.date()):
            continue
        if not qualifies_for_celebration(raw_order, settings["threshold"]):
            continue

        order = raw_order
        if normalized_mapping:
            order = replace(
                order,
                store_name_display=normalized_mapping.get(
                    str(order.store_name).strip().upper(), order.store_name,
                ),
                performance_org_display=normalized_mapping.get(
                    str(order.performance_org or "").strip().upper(),
                    order.performance_org or "",
                ),
            )
        region_mapping = settings.get("region_mapping", {})
        attrs = dict(order.attributes or {})
        store_region = region_mapping.get(str(order.store_name or "").strip().upper(), "")
        performance_region = region_mapping.get(str(order.performance_org or "").strip().upper(), "")
        attrs["store_region"] = attrs.get("store_region") or store_region
        attrs["performance_region"] = attrs.get("performance_region") or performance_region
        # The celebration area belongs to the performance organization, which
        # may differ from the selling organization on the same order.
        attrs["region"] = attrs["performance_region"] or attrs.get("region") or attrs["store_region"]
        order = replace(order, attributes=attrs)

        try:
            record = state.get(order.order_no)
            image_path = Path(record["image_path"]) if record.get("image_path") else None
            image_bytes = None
            image_suffix = image_path.suffix if image_path is not None else ".png"
            if image_path is not None and image_path.is_file():
                try:
                    candidate = image_path.read_bytes()
                    if candidate.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")):
                        image_bytes = candidate
                except OSError:
                    image_bytes = None

            if image_bytes is None:
                generated = generator(
                    order,
                    Path(settings["template_path"]),
                    Path(settings["output_dir"]),
                    int(settings.get("slide_number", 1)),
                    settings.get("content_fields", []),
                )
                if isinstance(generated, CelebrationImage):
                    image_path = generated.path
                    image_bytes = generated.data
                    image_suffix = generated.suffix
                else:
                    image_path = Path(generated)
                    image_suffix = image_path.suffix
                    try:
                        image_bytes = image_path.read_bytes()
                    except OSError:
                        image_bytes = None
                state.record_image(order.order_no, image_path)

            sent_targets = state.sent_targets(order.order_no)
            for target_id, client in selected_targets.items():
                if target_id in sent_targets:
                    continue
                try:
                    if image_bytes is not None and hasattr(client, "send_image_bytes"):
                        client.send_image_bytes(image_bytes, image_suffix)
                    else:
                        client.send_image(image_path)
                    state.mark_target_sent(order.order_no, target_id, now_func())
                    sent_count += 1
                except Exception as exc:  # noqa: BLE001
                    message = f"喜报 {order.order_no} -> Webhook {target_id}: {exc}"
                    errors.append(message)
                    LOGGER.error(message)
        except Exception as exc:  # noqa: BLE001
            message = f"喜报 {order.order_no} 生成失败: {exc}"
            errors.append(message)
            LOGGER.exception(message)

    return sent_count, errors
