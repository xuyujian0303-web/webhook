from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest

from wecom_sales_webhook_bot.ems_source import EmsSalesDataSource
from wecom_sales_webhook_bot.db import create_session_factory, initialize_database
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder
from wecom_sales_webhook_bot.orchestrator import run_once
from wecom_sales_webhook_bot.rule_service import RuleConditionDTO, RuleGroupDTO
from wecom_sales_webhook_bot.rule_models import RuleCondition, RuleGroup


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


def test_lowercase_store_filter_matches_uppercase_ems_codes(monkeypatch) -> None:
    client = FakeEmsClient([_order(kind="sale")])
    monkeypatch.setattr(
        "wecom_sales_webhook_bot.ems_source.decode_sale_detail_orders",
        lambda payload: payload,
    )
    source = _source(client)

    orders = source.load_orders(
        start_at=datetime(2026, 9, 22),
        end_at=datetime(2026, 9, 23),
        store_names={"g899"},
        document_types={"sale"},
    )

    assert client.calls[0][2]["store_names"] == {"G899"}
    assert [order.store_name for order in orders] == ["G899"]


def test_filtered_query_failure_does_not_fall_back_to_unfiltered_request() -> None:
    client = FakeEmsClient([_order()], fail_filtered_query=True)
    source = _source(client)

    with pytest.raises(ConnectionError, match="simulated"):
        source.load_orders(
            start_at=datetime(2026, 9, 22),
            end_at=datetime(2026, 9, 23),
            amount_range=(10000, 20000),
        )

    # The source first tries the compact frame and then retries with the
    # complete captured frame before surfacing the connection failure.
    assert len(client.calls) == 2


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


def test_unsupported_document_type_operator_does_not_default_to_sale(tmp_path) -> None:
    class CapturingSource:
        def __init__(self):
            self.kwargs = None

        def load_orders(self, **kwargs):
            self.kwargs = kwargs
            return []

    source = CapturingSource()
    group = RuleGroupDTO(
        name="exclude returns",
        match_mode="all",
        conditions=[RuleConditionDTO("document_type", "not_equals", "return")],
    )
    run_once(
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
    )

    assert source.kwargs["document_types"] == set()


def test_or_rule_does_not_narrow_document_types_and_can_include_other_types(tmp_path) -> None:
    class CapturingSource:
        def __init__(self):
            self.kwargs = None

        def load_orders(self, **kwargs):
            self.kwargs = kwargs
            return []

    source = CapturingSource()
    group = RuleGroupDTO(
        name="OR sale or store",
        match_mode="all",
        conditions=[
            RuleConditionDTO("document_type", "in", "0", "any"),
            RuleConditionDTO("store_name", "equals", "G899", "any"),
        ],
    )
    run_once(
        data_source=source,
        sales_filter=None,
        image_provider=None,
        state_file=tmp_path / "or-state.json",
        webhook_client=None,
        max_images=8,
        dry_run=True,
        database_rule_groups=[group],
        service_started_at=datetime(2026, 9, 22),
        now_func=lambda: datetime(2026, 9, 23, 12),
    )

    assert source.kwargs["document_types"] == set()


def test_multiple_rules_union_server_document_type_scope(tmp_path) -> None:
    class CapturingSource:
        def __init__(self):
            self.kwargs = None

        def load_orders(self, **kwargs):
            self.kwargs = kwargs
            return []

    source = CapturingSource()
    rules = [
        RuleGroupDTO(
            "preorders",
            conditions=[RuleConditionDTO("document_type", "in", "3")],
        ),
        RuleGroupDTO(
            "exchanges",
            conditions=[RuleConditionDTO("document_type", "equals", "exchange")],
        ),
    ]
    run_once(
        data_source=source,
        sales_filter=None,
        image_provider=None,
        state_file=tmp_path / "multi-state.json",
        webhook_client=None,
        max_images=8,
        dry_run=True,
        database_rule_groups=rules,
        service_started_at=datetime(2026, 9, 22),
        now_func=lambda: datetime(2026, 9, 23, 12),
    )

    assert source.kwargs["document_types"] == {"preorder", "exchange"}


def test_gui_saved_database_conditions_flow_through_orchestrator(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'gui-rules.db'}"
    session_factory = create_session_factory(database_url)
    initialize_database(session_factory)
    with session_factory() as session:
        group = RuleGroup(
            name="GUI saved filters",
            is_enabled=True,
            match_mode="all",
            updated_by="desktop",
        )
        session.add(group)
        session.flush()
        for field, operator, value in (
            ("store_name", "in", "G899,G889"),
            ("sold_at", "date_between", "2026-09-22,2026-09-23"),
            ("total_amount", "between", "10000,20000"),
            ("unit_price", "between", "0,50000"),
            ("discount", "between", "0,100"),
            ("season", "equals", "26FW"),
            ("shipment_group", "equals", "26FWG6"),
            ("style_no", "equals", "JACH619CNY0"),
            ("document_type", "in", "0,1,2,3"),
        ):
            session.add(RuleCondition(
                rule_group_id=group.id,
                field_name=field,
                operator=operator,
                condition_group="all",
                value_json=value,
            ))
        session.commit()

    class CapturingSource:
        def __init__(self):
            self.kwargs = None

        def load_orders(self, **kwargs):
            self.kwargs = kwargs
            return []

    source = CapturingSource()
    run_once(
        data_source=source,
        sales_filter=None,
        image_provider=None,
        state_file=tmp_path / "gui-state.json",
        webhook_client=None,
        max_images=8,
        dry_run=True,
        database_url=database_url,
        service_started_at=datetime(2026, 9, 22),
        now_func=lambda: datetime(2026, 9, 23, 12),
    )

    assert source.kwargs["store_names"] == {"G899", "G889"}
    assert source.kwargs["amount_range"] == (10000, 20000)
    assert source.kwargs["unit_price_range"] == (0, 50000)
    assert source.kwargs["unit_discount_range"] == (0, 100)
    assert source.kwargs["seasons"] == {"26FW"}
    assert source.kwargs["shipment_groups"] == {"26FWG6"}
    assert source.kwargs["style_numbers"] == {"JACH619CNY0"}
    assert source.kwargs["document_types"] == {"sale", "return", "exchange", "preorder"}
    assert source.kwargs["start_at"] == datetime(2026, 9, 22)
    assert source.kwargs["end_at"] == datetime(2026, 9, 23, 23, 59, 59, 999999)


def test_saved_gui_rule_filters_orders_before_webhook_send(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'gui-push.db'}"
    session_factory = create_session_factory(database_url)
    initialize_database(session_factory)
    with session_factory() as session:
        group = RuleGroup(
            name="GUI integration",
            is_enabled=True,
            match_mode="all",
            updated_by="desktop",
        )
        session.add(group)
        session.flush()
        for field, operator, value in (
            ("store_name", "equals", "g899"),
            ("total_amount", "between", "10000,20000"),
            ("document_type", "in", "0"),
        ):
            session.add(RuleCondition(
                rule_group_id=group.id,
                field_name=field,
                operator=operator,
                condition_group="all",
                value_json=value,
            ))
        session.commit()

    class CapturingSource:
        def __init__(self):
            self.kwargs = None
            self.orders = []

        def load_orders(self, **kwargs):
            self.kwargs = kwargs
            return self.orders

    class CapturingWebhook:
        def __init__(self):
            self.messages = []

        def send_markdown_v2(self, content):
            self.messages.append(content)

    class EmptyImageProvider:
        def get_url(self, _key):
            return None

    source = CapturingSource()
    matching = replace(_order(kind="sale", amount=12600), order_no="MATCHING-SALE")
    wrong_type = replace(_order(kind="return", amount=12600), order_no="RETURN-ORDER")
    wrong_amount = replace(_order(kind="sale", amount=25000), order_no="HIGH-AMOUNT")
    wrong_store = replace(_order(kind="sale", amount=12600, store="G889"), order_no="OTHER-STORE")
    source.orders = [matching, wrong_type, wrong_amount, wrong_store]
    webhook = CapturingWebhook()

    sent = run_once(
        data_source=source,
        sales_filter=None,
        image_provider=EmptyImageProvider(),
        state_file=tmp_path / "gui-push-state.json",
        webhook_client=webhook,
        max_images=8,
        dry_run=False,
        database_url=database_url,
        service_started_at=datetime(2026, 9, 22, 8),
        now_func=lambda: datetime(2026, 9, 23, 12),
    )

    assert source.kwargs["document_types"] == {"sale"}
    assert source.kwargs["store_names"] == {"G899"}
    assert source.kwargs["amount_range"] == (10000, 20000)
    assert sent == ["MATCHING-SALE"]
    assert len(webhook.messages) == 1
    assert "MATCHING-SALE" in webhook.messages[0]
    assert "RETURN-ORDER" not in webhook.messages[0]
