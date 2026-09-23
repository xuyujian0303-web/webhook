from __future__ import annotations

from datetime import datetime

import pytest

from wecom_sales_webhook_bot.ems_source import EmsSalesDataSource
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder
from wecom_sales_webhook_bot.orchestrator import run_once
from wecom_sales_webhook_bot.rule_service import RuleConditionDTO, RuleGroupDTO


def _order(*, amount: float = 12600, store: str = "G899", kind: str = "preorder") -> SalesOrder:
    return SalesOrder(
        order_no="SOG899260922002",
        sold_at=datetime(2026, 9, 22, 11, 53, 19),
        store_name=store,
        total_amount=amount,
        document_type=kind,
        items=[
            SalesLineItem(
                barcode="GJACH619CCNY0C638",
                style_no="JACH619CNY0",
                unit_price=12600,
                attributes={"product_code": "GJACH619CCNY0C6"},
            )
        ],
    )


class FakeEmsClient:
    def __init__(self, orders: list[SalesOrder], *, fail_filtered_query: bool = False):
        self.orders = orders
        self.fail_filtered_query = fail_filtered_query
        self.calls = []

    def login(self, username: str, password: str) -> None:
        self.credentials = (username, password)

    def query_sale_detail(self, start, end, **kwargs):
        self.calls.append((start, end, kwargs))
        if self.fail_filtered_query and kwargs:
            raise ConnectionError("simulated filtered-query failure")
        return self.orders


def _source(client: FakeEmsClient) -> EmsSalesDataSource:
    source = EmsSalesDataSource({"username": "user", "password": "secret"})
    source.client = client
    return source


def test_source_forwards_server_filters_and_locally_checks_decoded_fields(monkeypatch) -> None:
    client = FakeEmsClient([_order(), _order(amount=25000, store="G889")])
    monkeypatch.setattr(
        "wecom_sales_webhook_bot.ems_source.decode_sale_detail_orders",
        lambda payload: client.orders,
    )
    client.query_sale_detail = lambda start, end, **kwargs: (
        client.calls.append((start, end, kwargs)) or b"fixture-response"
    )
    source = _source(client)

    orders = source.load_orders(
        start_at=datetime(2026, 9, 22),
        end_at=datetime(2026, 9, 23, 23, 59, 59),
        store_names={"G899", "G889"},
        document_types={"sale", "exchange", "return", "preorder"},
        style_numbers={"JACH619CNY0"},
        seasons={"26FW"},
        shipment_groups={"26FWG6"},
        amount_range=(10000, 20000),
        unit_price_range=(0, 50000),
        unit_discount_range=(0, 100),
        return_whole_order=False,
    )

    assert len(client.calls) == 1
    start, end, kwargs = client.calls[0]
    assert (start, end) == ("20260922", "20260923")
    assert kwargs["amount_range"] == (10000, 20000)
    assert kwargs["unit_price_range"] == (0, 50000)
    assert kwargs["unit_discount_range"] == (0, 100)
    assert kwargs["document_types"] == {"sale", "exchange", "return", "preorder"}
    assert kwargs["style_numbers"] == {"JACH619CNY0"}
    assert len(orders) == 1
    assert orders[0].order_no == "SOG899260922002"


def test_filtered_query_failure_does_not_fall_back_to_unfiltered_request() -> None:
    client = FakeEmsClient([_order()], fail_filtered_query=True)
    source = _source(client)

    with pytest.raises(ConnectionError, match="simulated"):
        source.load_orders(
            start_at=datetime(2026, 9, 22),
            end_at=datetime(2026, 9, 23),
            amount_range=(10000, 20000),
        )

    assert len(client.calls) == 1


def test_saved_rule_conditions_become_ems_server_query_parameters(tmp_path) -> None:
    class CapturingSource:
        def __init__(self):
            self.kwargs = None

        def load_orders(self, **kwargs):
            self.kwargs = kwargs
            return []

    source = CapturingSource()
    group = RuleGroupDTO(
        name="captured EMS filters",
        match_mode="all",
        conditions=[
            RuleConditionDTO("store_name", "in", "G899,G889"),
            RuleConditionDTO("sold_at", "date_between", "2026/9/22,2026/9/23"),
            RuleConditionDTO("total_amount", "between", "10000,20000"),
            RuleConditionDTO("unit_price", "between", "0,50000"),
            RuleConditionDTO("discount", "between", "0,100"),
            RuleConditionDTO("season", "equals", "26FW"),
            RuleConditionDTO("shipment_group", "equals", "26FWG6"),
            RuleConditionDTO("style_no", "equals", "JACH619CNY0"),
            RuleConditionDTO("document_type", "in", "0,1,2,3"),
        ],
    )

    assert run_once(
        data_source=source,
        sales_filter=None,
        image_provider=None,
        state_file=tmp_path / "state.json",
        webhook_client=None,
        max_images=8,
        dry_run=True,
        database_rule_groups=[group],
        service_started_at=datetime(2026, 9, 22),
        now_func=lambda: datetime(2026, 9, 23, 12),
    ) == []

    assert source.kwargs["store_names"] == {"G899", "G889"}
    assert source.kwargs["start_at"] == datetime(2026, 9, 22)
    assert source.kwargs["end_at"] == datetime(2026, 9, 23, 23, 59, 59, 999999)
    assert source.kwargs["amount_range"] == (10000, 20000)
    assert source.kwargs["unit_price_range"] == (0, 50000)
    assert source.kwargs["unit_discount_range"] == (0, 100)
    assert source.kwargs["seasons"] == {"26FW"}
    assert source.kwargs["shipment_groups"] == {"26FWG6"}
    assert source.kwargs["style_numbers"] == {"JACH619CNY0"}
    assert source.kwargs["document_types"] == {"sale", "return", "exchange", "preorder"}
