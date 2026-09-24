from datetime import datetime

from wecom_sales_webhook_bot.filters import FilterResult
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder
from wecom_sales_webhook_bot.orchestrator import run_once
from wecom_sales_webhook_bot.runtime_settings import RuntimeControls


class _DataSource:
    def load_orders(self):
        return [
            SalesOrder(
                order_no="SO-MAPPING",
                sold_at=datetime(2026, 9, 24, 10, 0),
                store_name="g899",
                performance_org="G889",
                total_amount=100,
                items=[
                    SalesLineItem(
                        barcode="B1",
                        style_no="S1",
                        unit_price=100,
                        image_url="https://img.example.com/p1.jpg",
                    )
                ],
            )
        ]


class _Filter:
    def evaluate(self, order):
        return FilterResult(matched=True, reason="manual_test")


class _Client:
    def __init__(self):
        self.messages = []

    def send_markdown_v2(self, content):
        self.messages.append(content)


def test_run_once_populates_display_names_without_runtime_toggle(tmp_path) -> None:
    client = _Client()
    sent = run_once(
        data_source=_DataSource(),
        sales_filter=_Filter(),
        image_provider=None,
        state_file=tmp_path / "state.json",
        webhook_client=client,
        max_images=8,
        dry_run=False,
        template_body="{{ order.store_name }}|{{ order.store_name_display }}|{{ order.performance_org }}|{{ order.performance_org_display }}",
        store_name_mapping={"G899": "北京SKP", "G889": "上海久光"},
        runtime_controls=RuntimeControls(1, 8, 0, "00:00", "23:59"),
        now_func=lambda: datetime(2026, 9, 24, 10, 0),
        service_started_at=datetime(2026, 9, 24, 9, 0),
    )

    assert sent == ["SO-MAPPING"]
    assert client.messages == ["g899|北京SKP|G889|上海久光"]


def test_missing_sales_org_mapping_does_not_borrow_performance_org_name(tmp_path) -> None:
    client = _Client()

    class DataSource:
        def load_orders(self):
            return [
                SalesOrder(
                    order_no="XSG00J260918002",
                    sold_at=datetime(2026, 9, 24, 10, 0),
                    store_name="G00J",
                    performance_org="G887",
                    total_amount=100,
                    items=[
                        SalesLineItem(
                            barcode="B1",
                            style_no="S1",
                            unit_price=100,
                            image_url="https://img.example.com/p1.jpg",
                        )
                    ],
                )
            ]

    sent = run_once(
        data_source=DataSource(),
        sales_filter=_Filter(),
        image_provider=None,
        state_file=tmp_path / "state.json",
        webhook_client=client,
        max_images=8,
        dry_run=False,
        template_body="{{ order.store_name_display }}|{{ order.performance_org_display }}",
        store_name_mapping={"G887": "上海港汇恒隆"},
        runtime_controls=RuntimeControls(1, 8, 0, "00:00", "23:59"),
        now_func=lambda: datetime(2026, 9, 24, 10, 0),
        service_started_at=datetime(2026, 9, 24, 9, 0),
    )

    assert sent == ["XSG00J260918002"]
    assert client.messages == ["G00J|上海港汇恒隆"]
