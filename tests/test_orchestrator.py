from datetime import datetime
from pathlib import Path

import pytest

from wecom_sales_webhook_bot.cli import build_parser, validate_prototype_config
from wecom_sales_webhook_bot.config import load_config
from wecom_sales_webhook_bot.db import create_session_factory, initialize_database
from wecom_sales_webhook_bot.filters import FilterResult
from wecom_sales_webhook_bot.message_template_service import save_message_template
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder
from wecom_sales_webhook_bot.orchestrator import run_once
from wecom_sales_webhook_bot.runtime_settings import RuntimeControls
from wecom_sales_webhook_bot.rule_service import RuleConditionDTO, RuleGroupDTO
from wecom_sales_webhook_bot.rule_models import RuleCondition, RuleGroup
from wecom_sales_webhook_bot.wecom_client import WeComWebhookClient


class FakeSession:
    def __init__(self, payload=None) -> None:
        self.calls = []
        self.payload = payload or {"errcode": 0, "errmsg": "ok"}

    def post(self, url, json, timeout):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        payload = self.payload

        class Response:
            status_code = 200

            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def json():
                return payload

        return Response()


class FakeDataSource:
    def load_orders(self):
        return [
            SalesOrder(
                order_no="SO-001",
                sold_at=datetime(2026, 4, 20, 10, 0, 0),
                store_name="Store-A",
                total_amount=1200,
                items=[
                    SalesLineItem(
                        barcode="6901111111111",
                        style_no="A1001",
                        unit_price=699,
                    )
                ],
            )
        ]


class TwoOrderDataSource:
    def load_orders(self):
        return [
            SalesOrder(
                order_no="SO-001",
                sold_at=datetime(2026, 4, 20, 10, 0, 0),
                store_name="Store-A",
                total_amount=1200,
                items=[
                    SalesLineItem(
                        barcode="6901111111111",
                        style_no="A1001",
                        unit_price=699,
                    )
                ],
            ),
            SalesOrder(
                order_no="SO-002",
                sold_at=datetime(2026, 4, 20, 10, 5, 0),
                store_name="Store-B",
                total_amount=1300,
                items=[
                    SalesLineItem(
                        barcode="6902222222222",
                        style_no="A1002",
                        unit_price=799,
                    )
                ],
            ),
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


class FailingClient:
    def send_markdown_v2(self, content):
        raise RuntimeError("simulated send failure")


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


def test_wecom_client_posts_markdown_message() -> None:
    session = FakeSession()
    client = WeComWebhookClient(
        webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_WEBHOOK_KEY",
        timeout_seconds=5,
        retry_times=2,
        session=session,
    )

    client.send_markdown_v2("hello")

    assert session.calls == [
        {
            "url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_WEBHOOK_KEY",
            "json": {"msgtype": "markdown_v2", "markdown_v2": {"content": "hello"}},
            "timeout": 5,
        }
    ]


def test_wecom_client_raises_when_errcode_is_non_zero() -> None:
    session = FakeSession(payload={"errcode": 93000, "errmsg": "rate limited"})
    client = WeComWebhookClient(
        webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_WEBHOOK_KEY",
        timeout_seconds=5,
        retry_times=0,
        session=session,
    )

    with pytest.raises(RuntimeError, match="93000"):
        client.send_markdown_v2("hello")


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


def test_run_once_waits_between_multiple_messages(tmp_path: Path) -> None:
    client = FakeClient()
    sleep_calls = []

    sent = run_once(
        data_source=TwoOrderDataSource(),
        sales_filter=FakeFilter(),
        image_provider=FakeImageProvider(),
        state_file=tmp_path / "state.json",
        webhook_client=client,
        max_images=8,
        dry_run=False,
        push_interval_seconds=10,
        sleep_func=sleep_calls.append,
    )

    assert sent == ["SO-001", "SO-002"]
    assert len(client.messages) == 2
    assert sleep_calls == [10]


def test_run_once_does_not_mark_state_when_send_fails(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"

    with pytest.raises(RuntimeError, match="simulated send failure"):
        run_once(
            data_source=FakeDataSource(),
            sales_filter=FakeFilter(),
            image_provider=FakeImageProvider(),
            state_file=state_file,
            webhook_client=FailingClient(),
            max_images=8,
            dry_run=False,
        )

    assert state_file.exists()
    assert '"SO-001"' not in state_file.read_text(encoding="utf-8")


def test_run_once_uses_template_body_when_provided(tmp_path: Path) -> None:
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
        template_body="# Template Test\n> {{ order.order_no }}\n{{ items_markdown }}",
    )

    assert sent == ["SO-001"]
    assert len(client.messages) == 1
    assert client.messages[0].startswith("# Template Test")


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


def test_run_once_validation_allows_backend_without_rules(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
csv:
  path: ./sales.csv
  encoding: utf-8
  field_mapping:
    order_no: order_no
    sold_at: sold_at
    store_name: store_name
    total_amount: total_amount
    barcode: barcode
    style_no: style_no
    unit_price: unit_price
image_service:
  host: 127.0.0.1
  port: 8000
  image_dir: ./images
wecom:
  webhook_url: https://example.com
  timeout_seconds: 3
  retry_times: 1
runtime:
  scan_interval_seconds: 30
  max_images_per_message: 2
  state_file: ./state.json
  dry_run: true
backend:
  database_url: sqlite:///./var/app.db
  secret_key: test-secret
  host: 127.0.0.1
  port: 5000
  bootstrap_admin_username: admin
  bootstrap_admin_password: password
""".strip(),
        encoding="utf-8",
    )
    config = load_config(config_file)

    validate_prototype_config("run-once", config)


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


def _seed_enabled_rule(session_factory, *, amount_threshold: str, name: str = "test-rule") -> None:
    with session_factory() as session:
        rule = RuleGroup(
            name=name,
            is_enabled=True,
            match_mode="all",
            updated_by="test",
        )
        session.add(rule)
        session.flush()
        session.add(
            RuleCondition(
                rule_group_id=rule.id,
                field_name="total_amount",
                operator="gte",
                value_json=amount_threshold,
            )
        )
        session.commit()


def test_run_once_uses_database_rules_when_backend_database_is_configured(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    session_factory = create_session_factory(database_url)
    initialize_database(session_factory)
    _seed_enabled_rule(session_factory, amount_threshold="2000")

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
        database_url=database_url,
    )

    assert sent == []
    assert client.messages == []


def test_run_once_uses_active_database_template_when_backend_database_is_configured(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'app-template.db'}"
    session_factory = create_session_factory(database_url)
    initialize_database(session_factory)
    _seed_enabled_rule(session_factory, amount_threshold="1000")
    with session_factory() as session:
        save_message_template(
            session,
            template_id=None,
            template_name="template-a",
            template_body="# Template A\n> {{ order.order_no }}\n{{ items_markdown }}",
            preset_key="standard",
            activate=True,
        )

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
        database_url=database_url,
    )

    assert sent == ["SO-001"]
    assert client.messages[0].startswith("# Template A")


def test_run_once_defers_outside_push_window_and_retries_later(tmp_path: Path) -> None:
    client = FakeClient()
    state_file = tmp_path / "window-state.json"
    controls = RuntimeControls(1200, 8, 0, "10:00", "22:00")

    assert run_once(
        data_source=FakeDataSource(), sales_filter=FakeFilter(), image_provider=FakeImageProvider(),
        state_file=state_file, webhook_client=client, max_images=8, dry_run=False,
        runtime_controls=controls, now_func=lambda: datetime(2026, 8, 27, 9, 0),
        service_started_at=datetime(2026, 8, 27, 8, 0),
    ) == []
    assert client.messages == []
    assert '"SO-001"' not in state_file.read_text(encoding="utf-8")

    assert run_once(
        data_source=FakeDataSource(), sales_filter=FakeFilter(), image_provider=FakeImageProvider(),
        state_file=state_file, webhook_client=client, max_images=8, dry_run=False,
        runtime_controls=controls, now_func=lambda: datetime(2026, 8, 27, 10, 0),
        service_started_at=datetime(2026, 8, 27, 8, 0),
    ) == ["SO-001"]


def test_run_once_uses_service_start_date_for_empty_date_range_rule(tmp_path: Path) -> None:
    client = FakeClient()
    state_file = tmp_path / "date-state.json"
    group = RuleGroupDTO(
        name="默认日期", match_mode="all",
        conditions=[
            RuleConditionDTO(field_name="total_amount", operator="gte", value=1000),
            RuleConditionDTO(field_name="sold_at", operator="date_range", value=["", ""]),
        ],
    )
    assert run_once(
        data_source=FakeDataSource(), sales_filter=None, image_provider=FakeImageProvider(),
        state_file=state_file, webhook_client=client, max_images=8, dry_run=True,
        database_rule_groups=[group], service_started_at=datetime(2026, 4, 20),
        now_func=lambda: datetime(2026, 4, 20, 10, 0),
    ) == ["SO-001"]

