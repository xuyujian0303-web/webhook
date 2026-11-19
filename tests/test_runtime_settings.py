import json
from datetime import datetime

from wecom_sales_webhook_bot.db import create_session_factory, initialize_database
from wecom_sales_webhook_bot.cli import _runtime_controls_from_config
from wecom_sales_webhook_bot.rule_models import GlobalSetting
from wecom_sales_webhook_bot.runtime_settings import (
    RuntimeControls,
    is_within_push_window,
    load_or_initialize_runtime_controls,
    load_runtime_controls,
    save_runtime_controls,
)


def test_load_or_initialize_runtime_controls_creates_default_row(tmp_path) -> None:
    session_factory = create_session_factory(f"sqlite:///{tmp_path / 'app.db'}")
    initialize_database(session_factory)

    with session_factory() as session:
        controls = load_or_initialize_runtime_controls(
            session,
            RuntimeControls(
                scan_interval_seconds=1200,
                max_images_per_message=8,
                push_interval_seconds=10,
            ),
        )

    assert controls.scan_interval_seconds == 1200
    assert controls.max_images_per_message == 8
    assert controls.push_interval_seconds == 10

    loaded = load_runtime_controls(
        f"sqlite:///{tmp_path / 'app.db'}",
        RuntimeControls(
            scan_interval_seconds=900,
            max_images_per_message=4,
            push_interval_seconds=3,
        ),
    )

    assert loaded.scan_interval_seconds == 1200
    assert loaded.max_images_per_message == 8
    assert loaded.push_interval_seconds == 10


def test_save_runtime_controls_updates_existing_row(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    session_factory = create_session_factory(database_url)
    initialize_database(session_factory)

    with session_factory() as session:
        load_or_initialize_runtime_controls(
            session,
            RuntimeControls(
                scan_interval_seconds=1200,
                max_images_per_message=8,
                push_interval_seconds=10,
            ),
        )
        save_runtime_controls(
            session,
            scan_interval_seconds=300,
            max_images_per_message=5,
            push_interval_seconds=6,
        )

    loaded = load_runtime_controls(
        database_url,
        RuntimeControls(
            scan_interval_seconds=1200,
            max_images_per_message=8,
            push_interval_seconds=10,
        ),
    )
    assert loaded.scan_interval_seconds == 300
    assert loaded.max_images_per_message == 5
    assert loaded.push_interval_seconds == 6

    with session_factory() as session:
        row = session.query(GlobalSetting).filter_by(setting_key="runtime_settings").one()
    payload = json.loads(row.setting_json)
    assert payload["scan_interval_seconds"] == 300
    assert payload["max_images_per_message"] == 5
    assert payload["push_interval_seconds"] == 6


def test_runtime_controls_default_and_enforce_daily_push_window() -> None:
    controls = RuntimeControls(
        scan_interval_seconds=1200,
        max_images_per_message=8,
        push_interval_seconds=10,
        push_window_start="10:00",
        push_window_end="22:00",
    )

    assert is_within_push_window(datetime(2026, 8, 27, 10, 0), controls) is True
    assert is_within_push_window(datetime(2026, 8, 27, 22, 1), controls) is False


def test_gui_config_runtime_controls_override_stale_database_values(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    session_factory = create_session_factory(database_url)
    initialize_database(session_factory)
    with session_factory() as session:
        save_runtime_controls(
            session,
            scan_interval_seconds=600,
            max_images_per_message=8,
            push_interval_seconds=10,
            push_window_start="10:00",
            push_window_end="22:00",
            show_chinese_org_names=True,
        )

    configured = RuntimeControls(
        scan_interval_seconds=60,
        max_images_per_message=5,
        push_interval_seconds=2,
        push_window_start="08:00",
        push_window_end="20:00",
        return_whole_order=False,
    )
    effective = _runtime_controls_from_config(configured, database_url)

    assert effective.scan_interval_seconds == 60
    assert effective.max_images_per_message == 5
    assert effective.push_interval_seconds == 2
    assert effective.push_window_start == "08:00"
    assert effective.push_window_end == "20:00"
    assert effective.return_whole_order is False
    assert effective.show_chinese_org_names is True
