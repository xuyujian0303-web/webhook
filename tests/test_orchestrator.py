from datetime import datetime
from pathlib import Path

from wecom_sales_webhook_bot.filters import FilterResult
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
