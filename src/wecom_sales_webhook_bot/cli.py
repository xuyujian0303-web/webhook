from __future__ import annotations

import argparse
from dataclasses import replace
import json
import msvcrt
import time
import yaml
from datetime import datetime
from pathlib import Path

from wecom_sales_webhook_bot.config import AppConfig, load_config
from wecom_sales_webhook_bot.csv_source import CsvSalesDataSource
from wecom_sales_webhook_bot.datasource_config import load_data_source_config
from wecom_sales_webhook_bot.filters import SalesFilter
from wecom_sales_webhook_bot.image_service import (
    LocalImageUrlProvider,
    start_image_server,
)
from wecom_sales_webhook_bot.orchestrator import run_once
from wecom_sales_webhook_bot.runtime_settings import (
    RuntimeControls,
    load_runtime_controls,
    load_runtime_settings,
)
from wecom_sales_webhook_bot.sqlserver_source import SqlServerSalesDataSource
from wecom_sales_webhook_bot.ems_source import EmsSalesDataSource
from wecom_sales_webhook_bot.state_store import PushStateStore
from wecom_sales_webhook_bot.wecom_client import MultiWeComWebhookClient, WeComWebhookClient
from wecom_sales_webhook_bot.celebration import DEFAULT_CONTENT_FIELDS, webhook_target_id
from wecom_sales_webhook_bot.single_instance import acquire_instance


REQUIRED_CSV_FIELD_MAPPING_KEYS = (
    "order_no",
    "sold_at",
    "store_name",
    "total_amount",
    "barcode",
    "style_no",
    "unit_price",
)


def _runtime_controls_from_config(
    config_controls: RuntimeControls,
    database_url: str | None = None,
) -> RuntimeControls:
    if database_url is None:
        return config_controls
    persisted_controls = load_runtime_controls(database_url, config_controls)
    return replace(
        config_controls,
        show_chinese_org_names=persisted_controls.show_chinese_org_names,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("run-once", "schedule", "serve-images", "clear-state", "desktop-gui"):
        command = subparsers.add_parser(name)
        command.add_argument("--config", required=True)

    return parser


def _uses_sqlserver_data_source(config: AppConfig) -> bool:
    return config.data_source is not None and config.data_source.kind == "sqlserver"


def validate_prototype_config(command: str, config: AppConfig) -> None:
    missing: list[str] = []
    if command in ("run-once", "schedule"):
        uses_ems = config.data_source is not None and config.data_source.kind == "ems"
        if not _uses_sqlserver_data_source(config) and not uses_ems:
            if config.csv is None:
                missing.append("csv or data_source")
            else:
                missing.extend(
                    f"csv.field_mapping.{key}"
                    for key in REQUIRED_CSV_FIELD_MAPPING_KEYS
                    if key not in config.csv.field_mapping
                )
        if config.rules is None and config.backend is None:
            missing.append("rules or backend")
        if config.runtime.state_file is None:
            missing.append("runtime.state_file")
    elif command == "serve-images":
        if config.image_service is None:
            missing.append("image_service")
    elif command == "clear-state":
        if config.runtime.state_file is None:
            missing.append("runtime.state_file")
    if missing:
        raise ValueError(f"Command {command!r} requires config sections: {', '.join(missing)}")


def _build_data_source(config: AppConfig, base_dir: Path):
    if config.data_source is not None and config.data_source.kind == "ems":
        ems_path = (base_dir / config.data_source.config_path).resolve()
        return EmsSalesDataSource(json.loads(ems_path.read_text(encoding="utf-8")))
    if _uses_sqlserver_data_source(config):
        data_source_config_path = (base_dir / config.data_source.config_path).resolve()
        data_source_config = load_data_source_config(data_source_config_path)
        return SqlServerSalesDataSource(data_source_config.sqlserver)
    return CsvSalesDataSource(config.csv, base_dir=base_dir)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "desktop-gui":
        from wecom_sales_webhook_bot.desktop_gui import launch_gui
        launch_gui(Path(args.config).resolve())
        return
    config = load_config(Path(args.config))

    validate_prototype_config(args.command, config)

    if args.command == "serve-images":
        start_image_server(
            image_dir=config.image_service.image_dir,
            host=config.image_service.host,
            port=config.image_service.port,
        )
        while True:
            time.sleep(3600)

    if args.command == "clear-state":
        PushStateStore(config.runtime.state_file).clear()
        return

    config_path = Path(args.config).resolve()
    base_dir = config_path.parent
    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    image_map_csv = None
    if config.image_service is not None and config.image_service.image_map_csv is not None:
        image_map_csv = (base_dir / config.image_service.image_map_csv).resolve()

    data_source = _build_data_source(config, base_dir=base_dir)
    runtime_controls = RuntimeControls(
        scan_interval_seconds=config.runtime.scan_interval_seconds,
        max_images_per_message=config.runtime.max_images_per_message,
        push_interval_seconds=config.runtime.push_interval_seconds,
                    return_whole_order=config.runtime.return_whole_order,
    )
    if config.backend is not None:
        runtime_controls = _runtime_controls_from_config(
            runtime_controls,
            config.backend.database_url,
        )
    # Template variables keep the raw organization codes and expose mapped
    # names through the explicit *_display variables.  Do not gate this on
    # the legacy runtime toggle: a saved GUI template may request display
    # names directly.
    store_name_mapping = config.store_mapping
    region_mapping = config.region_mapping
    sales_filter = None
    database_rule_groups = None
    active_template_body = None
    if config.backend is not None:
        database_rule_groups, active_template_body = load_runtime_settings(
            config.backend.database_url
        )
    elif config.rules is not None:
        sales_filter = SalesFilter(
            amount_threshold=config.rules.amount_threshold,
            style_whitelist=config.rules.style_whitelist,
        )
    if config.image_service is None:
        # EMS returns an externally reachable image URL on each line item.
        # Keep a local fallback provider for records without such a URL, but
        # do not require a local image server for normal EMS scans.
        image_provider = LocalImageUrlProvider(
            image_dir=base_dir / "data" / "images",
            base_url="http://127.0.0.1:8765",
        )
    else:
        image_provider = LocalImageUrlProvider(
            image_dir=config.image_service.image_dir,
            base_url=f"http://{config.image_service.host}:{config.image_service.port}",
            image_map_csv=image_map_csv,
        )
    webhook_clients = [
        WeComWebhookClient(webhook_url=url, timeout_seconds=config.wecom.timeout_seconds,
                           retry_times=config.wecom.retry_times)
        for url in config.wecom.webhook_urls
    ]
    webhook_client = MultiWeComWebhookClient(webhook_clients)
    celebration_raw = raw_config.get("celebration") or {}
    celebration_settings = None
    celebration_targets = None
    if celebration_raw.get("enabled"):
        from decimal import Decimal, InvalidOperation

        try:
            threshold = Decimal(str(celebration_raw.get("threshold", "100000")))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("喜报金额门槛必须是有效数字") from exc
        if not threshold.is_finite() or threshold < 0:
            raise ValueError("喜报金额门槛必须是大于等于零的有限数值")
        template_path = Path(str(celebration_raw.get("template_path", "./templates/converted/捷报模板.svg")))
        output_dir = Path(str(celebration_raw.get("output_dir", "./data/celebrations")))
        if not template_path.is_absolute():
            template_path = base_dir / template_path
        if not output_dir.is_absolute():
            output_dir = base_dir / output_dir
        if not template_path.is_file():
            raise ValueError(f"喜报模板不存在：{template_path}")
        selected_ids = celebration_raw.get("webhook_targets")
        if selected_ids is None:
            selected_ids = [webhook_target_id(url) for url in config.wecom.webhook_urls]
        selected_ids = {str(value) for value in selected_ids}
        all_targets = {
            webhook_target_id(url): client
            for url, client in zip(config.wecom.webhook_urls, webhook_clients)
        }
        celebration_targets = {key: all_targets[key] for key in selected_ids if key in all_targets}
        if not celebration_targets:
            raise ValueError("启用喜报后，至少选择一个有效的Webhook接收群")
        content_fields = celebration_raw.get("content_fields", list(DEFAULT_CONTENT_FIELDS))
        if set(content_fields) - set(DEFAULT_CONTENT_FIELDS):
            raise ValueError("喜报模板字段配置中包含无法识别的字段")
        celebration_settings = {
            "enabled": True,
            "threshold": str(threshold),
            "template_path": template_path,
            "output_dir": output_dir,
            "slide_number": int(celebration_raw.get("slide_number", 1)),
            "content_fields": list(content_fields),
            "region_mapping": region_mapping,
        }

    service_started_at = datetime.now()
    if args.command in ("run-once", "schedule"):
        raw_runtime = (yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}).get("runtime", {})
        rescan_value = str(raw_runtime.get("rescan_start_date", "")).strip()
        if rescan_value:
            try:
                service_started_at = datetime.strptime(rescan_value, "%Y-%m-%d")
            except ValueError:
                raise ValueError("runtime.rescan_start_date must use YYYY-MM-DD")

    if args.command == "run-once":
        run_once(
            data_source=data_source,
            sales_filter=sales_filter,
            image_provider=image_provider,
            state_file=config.runtime.state_file,
            webhook_client=webhook_client,
            max_images=runtime_controls.max_images_per_message,
            dry_run=config.runtime.dry_run,
            template_body=active_template_body,
            database_rule_groups=database_rule_groups,
            push_interval_seconds=runtime_controls.push_interval_seconds,
            runtime_controls=runtime_controls,
            service_started_at=service_started_at,
            database_url=config.backend.database_url if config.backend is not None else None,
            store_name_mapping=store_name_mapping,
            celebration_settings=celebration_settings,
            celebration_targets=celebration_targets,
        )
        return

    if args.command == "schedule":
        schedule_guard = acquire_instance("schedule", str(Path(args.config).resolve()))
        if not schedule_guard.acquired:
            print(f"持续扫描已经在运行，跳过第二个实例: {Path(args.config).resolve()}")
            return
        lock_path = Path(config.runtime.state_file).with_name("schedule.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_handle = lock_path.open("a+", encoding="ascii")
        try:
            if lock_handle.tell() == 0:
                lock_handle.write("0")
                lock_handle.flush()
            lock_handle.seek(0)
            msvcrt.locking(lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
        except (OSError, IOError):
            lock_handle.close()
            print(f"已有扫描进程正在运行，未启动第二个实例: {lock_path}")
            return

        def release_schedule_lock() -> None:
            try:
                lock_handle.seek(0)
                msvcrt.locking(lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
            except (OSError, IOError):
                pass
            lock_handle.close()

        import atexit
        atexit.register(release_schedule_lock)
        while True:
            if config.backend is not None:
                database_rule_groups, active_template_body = load_runtime_settings(
                    config.backend.database_url
                )
            run_once(
                data_source=data_source,
                sales_filter=sales_filter,
                image_provider=image_provider,
                state_file=config.runtime.state_file,
                webhook_client=webhook_client,
                max_images=runtime_controls.max_images_per_message,
                dry_run=config.runtime.dry_run,
                template_body=active_template_body,
                database_rule_groups=database_rule_groups,
                push_interval_seconds=runtime_controls.push_interval_seconds,
                runtime_controls=runtime_controls,
                service_started_at=service_started_at,
                database_url=config.backend.database_url if config.backend is not None else None,
                store_name_mapping=store_name_mapping,
                celebration_settings=celebration_settings,
                celebration_targets=celebration_targets,
            )
            time.sleep(runtime_controls.scan_interval_seconds)


if __name__ == "__main__":
    main()



