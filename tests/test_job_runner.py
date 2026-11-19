from datetime import datetime

from wecom_sales_webhook_bot.job_runner import run_scan_cycle
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder
from wecom_sales_webhook_bot.rule_service import RuleConditionDTO, RuleGroupDTO


class FakeSource:
    def load_orders(self, start_at, end_at):
        return [
            SalesOrder(
                order_no="SO-API-1",
                sold_at=datetime(2026, 4, 22, 10, 0, 0),
                store_name="G621",
                total_amount=19250,
                items=[
                    SalesLineItem(
                        barcode="b1",
                        style_no="s1",
                        unit_price=5850,
                        image_url="https://img/1.jpg",
                    )
                ],
            )
        ]


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def send_markdown_v2(self, content: str) -> None:
        self.calls.append(content)


def test_run_scan_cycle_pushes_matching_orders_once_and_logs_record(tmp_path) -> None:
    sent = run_scan_cycle(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        source=FakeSource(),
        rule_groups=[
            RuleGroupDTO(
                name="门店规则",
                match_mode="any",
                conditions=[
                    RuleConditionDTO(
                        field_name="store_name", operator="in", value=["G621"]
                    )
                ],
            )
        ],
        webhook_client=FakeClient(),
        start_at=datetime(2026, 4, 22, 10, 0, 0),
        end_at=datetime(2026, 4, 22, 10, 20, 0),
        max_images=8,
    )

    assert sent == ["SO-API-1"]


def test_run_scan_cycle_uses_template_body_when_provided(tmp_path) -> None:
    client = FakeClient()

    sent = run_scan_cycle(
        database_url=f"sqlite:///{tmp_path / 'app-template.db'}",
        source=FakeSource(),
        rule_groups=[
            RuleGroupDTO(
                name="门店规则",
                match_mode="any",
                conditions=[
                    RuleConditionDTO(
                        field_name="store_name", operator="in", value=["G621"]
                    )
                ],
            )
        ],
        webhook_client=client,
        start_at=datetime(2026, 4, 22, 10, 0, 0),
        end_at=datetime(2026, 4, 22, 10, 20, 0),
        max_images=8,
        template_body="# 扫描模板\n> {{ order.order_no }}\n{{ items_markdown }}",
    )

    assert sent == ["SO-API-1"]
    assert client.calls[0].startswith("# 扫描模板")
