from datetime import datetime
from pathlib import Path

import pytest

from wecom_sales_webhook_bot.config import load_config
from wecom_sales_webhook_bot.filters import FilterResult
from wecom_sales_webhook_bot.cli import build_parser, validate_prototype_config
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder
from wecom_sales_webhook_bot.orchestrator import run_once
from wecom_sales_webhook_bot.wecom_client import WeComWebhookClient


class FakeSession:
    def __init__(self) -> None:
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append({"url": url, "json": json, "timeout": timeout})

        class Response:
            status_code = 200

            @staticmethod
            def raise_for_status() -> None:
                return None

        return Response()


def test_wecom_client_posts_markdown_message() -> None:
    session = FakeSession()
    client = WeComWebhookClient(
        webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
        timeout_seconds=5,
        retry_times=2,
        session=session,
    )

    client.send_markdown_v2("hello")

    assert session.calls == [
        {
            "url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
            "json": {"msgtype": "markdown_v2", "markdown_v2": {"content": "hello"}},
            "timeout": 5,
        }
    ]


class FakeDataSource:
    def load_orders(self):
        return [
            SalesOrder(
                order_no="SO-001",
                sold_at=datetime(2026, 4, 20, 10, 0, 0),
                store_name="上海一店",
                total_amount=1200,
                items=[
                    SalesLineItem(
                        barcode="6901111111111", style_no="A1001", unit_price=699
                    )
                ],
            )
        ]


class FakeFilter:
    def evaluate(self, order):
        return FilterResult(matched=True, reason="amount_threshold")


class FakeImageProvider:
    def get_url(self, barcode):
        return f"http://127.0.0.1:8123/{barcode}.jpg"


class FakeClient:
    def __init__(self):
        self.messages = []

    def send_markdown_v2(self, content):
        self.messages.append(content)


def test_run_once_sends_only_new_matching_orders(tmp_path: Path) -> None:
    client = FakeClient()
    state_file = tmp_path / "state.json"

    sent = run_once(
        data_source=FakeDataSource(),
        sales_filter=FakeFilter(),
        image_provider=FakeImageProvider(),
        state_file=state_file,
        webhook_client=client,
        max_images=8,
        dry_run=False,
    )

    assert sent == ["SO-001"]
    assert len(client.messages) == 1

    sent_again = run_once(
        data_source=FakeDataSource(),
        sales_filter=FakeFilter(),
        image_provider=FakeImageProvider(),
        state_file=state_file,
        webhook_client=client,
        max_images=8,
        dry_run=False,
    )

    assert sent_again == []
    assert len(client.messages) == 1


def test_cli_exposes_run_once_schedule_and_clear_state_commands() -> None:
    parser = build_parser()

    run_once_args = parser.parse_args(["run-once", "--config", "config.yaml"])
    clear_state_args = parser.parse_args(["clear-state", "--config", "config.yaml"])
    schedule_args = parser.parse_args(["schedule", "--config", "config.yaml"])

    assert run_once_args.command == "run-once"
    assert clear_state_args.command == "clear-state"
    assert schedule_args.command == "schedule"


def test_run_once_validation_reports_missing_csv_field_mapping_keys(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
csv:
  path: ./sales.csv
  encoding: utf-8
  field_mapping:
    order_no: order_no
image_service:
  host: 127.0.0.1
  port: 8000
  image_dir: ./images
wecom:
  webhook_url: https://example.com
  timeout_seconds: 3
  retry_times: 1
rules:
  amount_threshold: 100
  style_whitelist: [A,B]
runtime:
  scan_interval_seconds: 30
  max_images_per_message: 2
  state_file: ./state.json
  dry_run: true
""".strip(),
        encoding="utf-8",
    )
    config = load_config(config_file)

    with pytest.raises(ValueError) as exc_info:
        validate_prototype_config("run-once", config)

    message = str(exc_info.value)
    assert "csv.field_mapping.sold_at" in message
    assert "csv.field_mapping.store_name" in message
    assert "csv.field_mapping.total_amount" in message
    assert "csv.field_mapping.barcode" in message
    assert "csv.field_mapping.style_no" in message
    assert "csv.field_mapping.unit_price" in message


class BrokenDataSource:
    def load_orders(self):
        raise RuntimeError("csv unavailable")


class DummyFilter:
    def evaluate(self, order):
        raise AssertionError("should not be called")


class DummyImageProvider:
    def get_url(self, barcode):
        raise AssertionError("should not be called")


class DummyClient:
    def send_markdown_v2(self, content):
        raise AssertionError("should not be called")


def test_run_once_does_not_advance_state_when_csv_read_fails(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"

    sent = run_once(
        data_source=BrokenDataSource(),
        sales_filter=DummyFilter(),
        image_provider=DummyImageProvider(),
        state_file=state_file,
        webhook_client=DummyClient(),
        max_images=8,
        dry_run=False,
    )

    assert sent == []
    assert state_file.exists()
    assert '"last_scan_at": null' in state_file.read_text(encoding="utf-8")
