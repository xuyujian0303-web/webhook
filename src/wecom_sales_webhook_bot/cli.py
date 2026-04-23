from __future__ import annotations

import argparse
import time
from pathlib import Path

from wecom_sales_webhook_bot.config import load_config, AppConfig
from wecom_sales_webhook_bot.csv_source import CsvSalesDataSource
from wecom_sales_webhook_bot.filters import SalesFilter
from wecom_sales_webhook_bot.image_service import (
    LocalImageUrlProvider,
    start_image_server,
)
from wecom_sales_webhook_bot.orchestrator import run_once
from wecom_sales_webhook_bot.state_store import PushStateStore
from wecom_sales_webhook_bot.wecom_client import WeComWebhookClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("run-once", "schedule", "serve-images", "clear-state"):
        command = subparsers.add_parser(name)
        command.add_argument("--config", required=True)

    return parser


def validate_prototype_config(command: str, config: AppConfig) -> None:
    missing: list[str] = []
    if command in ("run-once", "schedule"):
        if config.csv is None:
            missing.append("csv")
        if config.image_service is None:
            missing.append("image_service")
        if config.rules is None:
            missing.append("rules")
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


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
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

    data_source = CsvSalesDataSource(config.csv, base_dir=Path(args.config).resolve().parent)
    sales_filter = SalesFilter(
        amount_threshold=config.rules.amount_threshold,
        style_whitelist=config.rules.style_whitelist,
    )
    image_provider = LocalImageUrlProvider(
        image_dir=config.image_service.image_dir,
        base_url=f"http://{config.image_service.host}:{config.image_service.port}",
    )
    webhook_client = WeComWebhookClient(
        webhook_url=config.wecom.webhook_url,
        timeout_seconds=config.wecom.timeout_seconds,
        retry_times=config.wecom.retry_times,
    )

    if args.command == "run-once":
        run_once(
            data_source=data_source,
            sales_filter=sales_filter,
            image_provider=image_provider,
            state_file=config.runtime.state_file,
            webhook_client=webhook_client,
            max_images=config.runtime.max_images_per_message,
            dry_run=config.runtime.dry_run,
        )
        return

    if args.command == "schedule":
        while True:
            run_once(
                data_source=data_source,
                sales_filter=sales_filter,
                image_provider=image_provider,
                state_file=config.runtime.state_file,
                webhook_client=webhook_client,
                max_images=config.runtime.max_images_per_message,
                dry_run=config.runtime.dry_run,
            )
            time.sleep(config.runtime.scan_interval_seconds)
