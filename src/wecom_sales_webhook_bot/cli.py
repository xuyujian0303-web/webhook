from __future__ import annotations

import argparse
import time
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
from wecom_sales_webhook_bot.state_store import PushStateStore
from wecom_sales_webhook_bot.wecom_client import WeComWebhookClient
from wecom_sales_webhook_bot.web_app import create_app


REQUIRED_CSV_FIELD_MAPPING_KEYS = (
    "order_no",
    "sold_at",
    "store_name",
    "total_amount",
    "barcode",
    "style_no",
    "unit_price",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("run-once", "schedule", "serve-images", "clear-state", "run-server"):
        command = subparsers.add_parser(name)
        command.add_argument("--config", required=True)

    return parser


def _uses_sqlserver_data_source(config: AppConfig) -> bool:
    return config.data_source is not None and config.data_source.kind == "sqlserver"


def validate_prototype_config(command: str, config: AppConfig) -> None:
    missing: list[str] = []
    if command in ("run-once", "schedule"):
        if not _uses_sqlserver_data_source(config):
            if config.csv is None:
                missing.append("csv or data_source")
            else:
                missing.extend(
                    f"csv.field_mapping.{key}"
                    for key in REQUIRED_CSV_FIELD_MAPPING_KEYS
                    if key not in config.csv.field_mapping
                )
        if config.image_service is None:
            missing.append("image_service")
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
    if _uses_sqlserver_data_source(config):
        data_source_config_path = (base_dir / config.data_source.config_path).resolve()
        data_source_config = load_data_source_config(data_source_config_path)
        return SqlServerSalesDataSource(data_source_config.sqlserver)
    return CsvSalesDataSource(config.csv, base_dir=base_dir)


def serve_web_app(app, host: str, port: int) -> None:
    if host == "0.0.0.0":
        raise ValueError("生产环境请配置服务器内网 IP，不要使用 0.0.0.0")
    from waitress import serve
    serve(app, host=host, port=port)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = load_config(Path(args.config))

    if args.command == "run-server":
        if config.backend is None:
            raise ValueError("Command 'run-server' requires config section: backend")
        app = create_app(
            {
                "SECRET_KEY": config.backend.secret_key,
                "DATABASE_URL": config.backend.database_url,
                "BOOTSTRAP_ADMIN": {
                    "username": config.backend.bootstrap_admin_username,
                    "password": config.backend.bootstrap_admin_password,
                },
                "RUNTIME_CONTROL_DEFAULTS": RuntimeControls(
                    scan_interval_seconds=config.runtime.scan_interval_seconds,
                    max_images_per_message=config.runtime.max_images_per_message,
                    push_interval_seconds=config.runtime.push_interval_seconds,
                ),
            }
        )
        serve_web_app(app, host=config.backend.host, port=config.backend.port)
        return

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
    image_map_csv = None
    if config.image_service.image_map_csv is not None:
        image_map_csv = (base_dir / config.image_service.image_map_csv).resolve()

    data_source = _build_data_source(config, base_dir=base_dir)
    runtime_controls = RuntimeControls(
        scan_interval_seconds=config.runtime.scan_interval_seconds,
        max_images_per_message=config.runtime.max_images_per_message,
        push_interval_seconds=config.runtime.push_interval_seconds,
    )
    if config.backend is not None:
        runtime_controls = load_runtime_controls(
            config.backend.database_url,
            runtime_controls,
        )
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
    image_provider = LocalImageUrlProvider(
        image_dir=config.image_service.image_dir,
        base_url=f"http://{config.image_service.host}:{config.image_service.port}",
        image_map_csv=image_map_csv,
    )
    webhook_client = WeComWebhookClient(
        webhook_url=config.wecom.webhook_url,
        timeout_seconds=config.wecom.timeout_seconds,
        retry_times=config.wecom.retry_times,
    )

    service_started_at = datetime.now()

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
        )
        return

    if args.command == "schedule":
        while True:
            if config.backend is not None:
                database_rule_groups, active_template_body = load_runtime_settings(
                    config.backend.database_url
                )
                runtime_controls = load_runtime_controls(
                    config.backend.database_url,
                    runtime_controls,
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
            )
            time.sleep(runtime_controls.scan_interval_seconds)


if __name__ == "__main__":
    main()



