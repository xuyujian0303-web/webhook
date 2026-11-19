from datetime import datetime

import pytest

from pathlib import Path

from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder
from wecom_sales_webhook_bot.rule_service import RuleConditionDTO, RuleGroupDTO, evaluate_rule_group
from wecom_sales_webhook_bot.wecom_client import MultiWeComWebhookClient
from wecom_sales_webhook_bot.config import load_config


def _order() -> SalesOrder:
    return SalesOrder(
        order_no="SO-001", sold_at=datetime(2026, 9, 18, 14, 30),
        store_name="G621", performance_org="G889", total_amount=15000,
        salesperson="张三", attributes={"customer_source": "会员推荐"},
        items=[SalesLineItem(barcode="BC-1", style_no="PA15161E", unit_price=7500, category="外套")],
    )


def test_all_and_any_condition_groups_are_applied_together() -> None:
    rule = RuleGroupDTO(
        name="交叉店大额", conditions=[
            RuleConditionDTO("store_name", "equals", "G621", "all"),
            RuleConditionDTO("total_amount", "gte", 10000, "all"),
            RuleConditionDTO("performance_org", "equals", "G889", "any"),
            RuleConditionDTO("category", "equals", "连衣裙", "any"),
        ],
    )
    assert evaluate_rule_group(_order(), rule) is True


def test_sales_and_performance_organizations_are_distinct_rule_fields() -> None:
    order = _order()
    assert evaluate_rule_group(order, RuleGroupDTO("销售机构", conditions=[RuleConditionDTO("store_name", "equals", "G621", "all")]))
    assert evaluate_rule_group(order, RuleGroupDTO("业绩机构", conditions=[RuleConditionDTO("performance_org", "equals", "G889", "all")]))
    assert not evaluate_rule_group(order, RuleGroupDTO("不可混用", conditions=[RuleConditionDTO("performance_org", "equals", "G621", "all")]))


class _Client:
    def __init__(self, error: Exception | None = None) -> None:
        self.error, self.messages = error, []

    def send_markdown_v2(self, content: str) -> None:
        self.messages.append(content)
        if self.error:
            raise self.error


def test_multiple_webhooks_each_receive_message() -> None:
    first, second = _Client(), _Client()
    MultiWeComWebhookClient([first, second]).send_markdown_v2("hello")
    assert first.messages == ["hello"]
    assert second.messages == ["hello"]


def test_multiple_webhooks_raise_after_attempting_every_target() -> None:
    first, second = _Client(RuntimeError("offline")), _Client()
    with pytest.raises(RuntimeError, match="webhook #1"):
        MultiWeComWebhookClient([first, second]).send_markdown_v2("hello")
    assert second.messages == ["hello"]


def test_config_accepts_multiple_webhook_urls(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("""
wecom:
  webhook_urls: [https://example.test/a, https://example.test/b]
  timeout_seconds: 5
  retry_times: 1
runtime:
  scan_interval_seconds: 1200
  max_images_per_message: 8
""", encoding="utf-8")
    assert load_config(path).wecom.webhook_urls == ("https://example.test/a", "https://example.test/b")
