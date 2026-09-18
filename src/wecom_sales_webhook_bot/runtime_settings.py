from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, time

from wecom_sales_webhook_bot.db import create_session_factory, initialize_database
from wecom_sales_webhook_bot.message_template_service import load_or_initialize_message_template
from wecom_sales_webhook_bot.rule_models import GlobalSetting, RuleCondition, RuleGroup
from wecom_sales_webhook_bot.rule_service import RuleConditionDTO, RuleGroupDTO

RUNTIME_SETTINGS_KEY = "runtime_settings"


@dataclass(frozen=True)
class RuntimeControls:
    scan_interval_seconds: int
    max_images_per_message: int
    push_interval_seconds: int
    push_window_start: str = "10:00"
    push_window_end: str = "22:00"
    show_chinese_org_names: bool = False


DEFAULT_RUNTIME_CONTROLS = RuntimeControls(
    scan_interval_seconds=1200,
    max_images_per_message=8,
    push_interval_seconds=10,
    show_chinese_org_names=False,
)


def _parse_clock_time(value: str) -> time:
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise ValueError("每日推送时段必须使用 HH:MM 格式") from exc


def is_within_push_window(now: datetime, controls: RuntimeControls) -> bool:
    return (
        _parse_clock_time(controls.push_window_start)
        <= now.time()
        <= _parse_clock_time(controls.push_window_end)
    )


def _parse_condition_value(condition: RuleCondition):
    if condition.field_name == "total_amount" and condition.operator == "gte":
        return float(condition.value_json)
    if condition.field_name == "sold_at" and condition.operator in {"between_time", "date_range", "date_between"}:
        start_value, end_value = condition.value_json.split(",", maxsplit=1)
        return [start_value.strip(), end_value.strip()]
    return [item.strip() for item in condition.value_json.split(",") if item.strip()]


def _normalize_runtime_controls(raw: dict | None, defaults: RuntimeControls) -> RuntimeControls:
    payload = raw or {}
    scan_interval_seconds = int(payload.get("scan_interval_seconds", defaults.scan_interval_seconds))
    max_images_per_message = int(payload.get("max_images_per_message", defaults.max_images_per_message))
    push_interval_seconds = int(payload.get("push_interval_seconds", defaults.push_interval_seconds))
    push_window_start = str(payload.get("push_window_start", defaults.push_window_start))
    push_window_end = str(payload.get("push_window_end", defaults.push_window_end))
    show_chinese_org_names = bool(payload.get("show_chinese_org_names", defaults.show_chinese_org_names))
    if scan_interval_seconds <= 0:
        raise ValueError("scan_interval_seconds must be > 0")
    if max_images_per_message <= 0:
        raise ValueError("max_images_per_message must be > 0")
    if push_interval_seconds < 0:
        raise ValueError("push_interval_seconds must be >= 0")
    if _parse_clock_time(push_window_start) >= _parse_clock_time(push_window_end):
        raise ValueError("每日推送开始时间必须早于结束时间")
    return RuntimeControls(
        scan_interval_seconds=scan_interval_seconds,
        max_images_per_message=max_images_per_message,
        push_interval_seconds=push_interval_seconds,
        push_window_start=push_window_start,
        push_window_end=push_window_end,
        show_chinese_org_names=show_chinese_org_names,
    )


def _runtime_controls_payload(controls: RuntimeControls) -> str:
    return json.dumps(asdict(controls), ensure_ascii=False, sort_keys=True)


def load_or_initialize_runtime_controls(session, defaults: RuntimeControls = DEFAULT_RUNTIME_CONTROLS) -> RuntimeControls:
    row = session.query(GlobalSetting).filter_by(setting_key=RUNTIME_SETTINGS_KEY).one_or_none()
    if row is None:
        controls = _normalize_runtime_controls(None, defaults)
        session.add(GlobalSetting(setting_key=RUNTIME_SETTINGS_KEY, setting_json=_runtime_controls_payload(controls)))
        session.commit()
        return controls
    controls = _normalize_runtime_controls(json.loads(row.setting_json), defaults)
    normalized_payload = _runtime_controls_payload(controls)
    if row.setting_json != normalized_payload:
        row.setting_json = normalized_payload
        session.commit()
    return controls


def save_runtime_controls(session, *, scan_interval_seconds: int, max_images_per_message: int, push_interval_seconds: int, push_window_start: str = "10:00", push_window_end: str = "22:00", show_chinese_org_names: bool = False, defaults: RuntimeControls = DEFAULT_RUNTIME_CONTROLS) -> RuntimeControls:
    controls = _normalize_runtime_controls(
        {"scan_interval_seconds": scan_interval_seconds, "max_images_per_message": max_images_per_message, "push_interval_seconds": push_interval_seconds, "push_window_start": push_window_start, "push_window_end": push_window_end, "show_chinese_org_names": show_chinese_org_names},
        defaults,
    )
    row = session.query(GlobalSetting).filter_by(setting_key=RUNTIME_SETTINGS_KEY).one_or_none()
    payload = _runtime_controls_payload(controls)
    if row is None:
        session.add(GlobalSetting(setting_key=RUNTIME_SETTINGS_KEY, setting_json=payload))
    else:
        row.setting_json = payload
    session.commit()
    return controls


def load_runtime_controls(database_url: str, defaults: RuntimeControls = DEFAULT_RUNTIME_CONTROLS) -> RuntimeControls:
    session_factory = create_session_factory(database_url)
    initialize_database(session_factory)
    with session_factory() as session:
        return load_or_initialize_runtime_controls(session, defaults)


def load_runtime_settings(database_url: str) -> tuple[list[RuleGroupDTO], str | None]:
    session_factory = create_session_factory(database_url)
    initialize_database(session_factory)
    with session_factory() as session:
        groups = session.query(RuleGroup).filter_by(is_enabled=True).order_by(RuleGroup.updated_at.desc(), RuleGroup.id.desc()).all()
        conditions = session.query(RuleCondition).all()
        template = load_or_initialize_message_template(session)
        group_modes = {group.id: group.match_mode for group in groups}
        condition_map: dict[int, list[RuleConditionDTO]] = {}
        for condition in conditions:
            condition_map.setdefault(condition.rule_group_id, []).append(RuleConditionDTO(field_name=condition.field_name, operator=condition.operator, value=_parse_condition_value(condition), condition_group=getattr(condition, "condition_group", "") or group_modes.get(condition.rule_group_id, "all")))
        return [RuleGroupDTO(name=group.name, match_mode=group.match_mode, conditions=condition_map.get(group.id, [])) for group in groups], template["template_body"]
