from dataclasses import replace
from datetime import date, datetime
from itertools import combinations
from types import SimpleNamespace

import pytest

from wecom_sales_webhook_bot.models import SalesOrder, SalesLineItem
from wecom_sales_webhook_bot.rule_service import (
    RuleConditionDTO as C, RuleGroupDTO as G, evaluate_rule_group as evaluate,
    operators_for_field, server_condition_key, project_rule_items,
)
from wecom_sales_webhook_bot.sales_fields import EMS_FIELD_DEFINITIONS, ITEM_RULE_FIELDS, order_field_values
from wecom_sales_webhook_bot.orchestrator import _query_kwargs_for_rule
from wecom_sales_webhook_bot.ems_source import EmsSalesDataSource


TEXT = {
    "equals": ("abc-001", "different"),
    "not_equals": ("different", "abc-001"),
    "contains": ("BC-", "absent"),
    "not_contains": ("absent", "BC-"),
    "in": ("other,abc-001", "other,last"),
    "not_in": ("other,last", "other,abc-001"),
    "starts_with": ("ab", "01"), "ends_with": ("001", "abc"),
    "is_empty": ("", ""), "is_not_empty": ("", ""),
}
NUMBER = {
    "equals": ("12.5000", "12.6"), "not_equals": ("12.6", "12.5000"),
    "gt": ("12.49", "12.5"), "gte": ("12.5", "12.51"),
    "lt": ("12.51", "12.5"), "lte": ("12.5", "12.49"),
    "between": ("13,12.5", "12.6,13"),
    "is_empty": ("", ""), "is_not_empty": ("", ""),
}
DATE = {
    "equals": ("2026/11/15", "2026-11-16"),
    "before": ("2026-11-16", "2026-11-15"),
    "after": ("2026-11-14", "2026-11-15"),
    "date_between": (",2026-11-15", ",2026-11-14"),
    "between_time": ("23:00,01:00", "00:00,22:00"),
    "is_empty": ("", ""), "is_not_empty": ("", ""),
}


def sample(field, kind, empty=False):
    value = None if empty else (12.5 if kind == "number" else
            datetime(2026, 11, 15, 23, 30, 59) if kind == "datetime" else "AbC-001")
    item = SalesLineItem("barcode", "style", 1)
    order = SalesOrder("order", datetime(2026, 11, 15), "G00J", 0, items=[item])
    if field in ITEM_RULE_FIELDS:
        if field in item.__dataclass_fields__:
            item = replace(item, **{field: value})
        else:
            item = replace(item, attributes={field: value})
        order = replace(order, items=[item])
    elif field in order.__dataclass_fields__:
        order = replace(order, **{field: value})
    else:
        order = replace(order, attributes={field: value})
    return order


CASES = [(key, label, kind, op) for key, label, kind in EMS_FIELD_DEFINITIONS
         if key not in {"season", "shipment_group"} for op in operators_for_field(key)]


@pytest.mark.parametrize("field,label,kind,op", CASES)
def test_every_local_field_and_operator(field, label, kind, op):
    positive, negative = {"text": TEXT, "number": NUMBER, "datetime": DATE}[kind][op]
    order = sample(field, kind)
    if field == "document_type":
        # The generic arbitrary value still exercises text operators; aliases
        # and all real type combinations are separately covered below.
        pass
    if op in {"is_empty", "is_not_empty"}:
        assert evaluate(order, G("filled", conditions=[C(label, op, "")])) == (op == "is_not_empty")
        assert evaluate(sample(field, kind, True), G("empty", conditions=[C(label, op, "")])) == (op == "is_empty")
    else:
        assert evaluate(order, G("positive", conditions=[C(label, op, positive)]))
        assert not evaluate(order, G("negative", conditions=[C(field, op, negative)]))


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "wrong"])
@pytest.mark.parametrize("op", ["equals", "not_equals", "gt", "gte", "lt", "lte", "between"])
def test_invalid_numbers_fail_closed(value, op):
    assert not evaluate(sample("total_amount", "number"), G("invalid", conditions=[C("total_amount", op, value)]))


@pytest.mark.parametrize("op,wanted,expected", [
    ("equals", "2026-11-15 23:30:59", True),
    ("equals", "2026-11-15T23:30:58", False),
    ("date_between", ["2026/11/15", ""], True),
    ("date_between", ["2026/11/16", ""], False),
    ("date_between", ["", "2026/11/15"], True),
    ("date_between", "bad,2026-11-16", False),
    ("between_time", "23:00,23:30", True),
    ("between_time", "23:00:00,23:30:00", False),
    ("before", "2026-11-16T00:00:00+00:00", False),
])
def test_datetime_boundaries(op, wanted, expected):
    assert evaluate(sample("created_at", "datetime"), G("date", conditions=[C("created_at", op, wanted)])) == expected


def test_multi_item_conditions_are_independent_and_negative_checks_all():
    a = SalesLineItem("a", "CO111", 20000)
    b = SalesLineItem("b", "JA222", 100)
    c = SalesLineItem("c", "OT333", 200)
    order = replace(sample("store_name", "text"), items=[a,b,c])
    group = G("cross rows", conditions=[C("unit_price", "gt", "10000"), C("style_no", "equals", "JA222")])
    assert evaluate(order, group)
    assert project_rule_items(order, group).items == [a,b]
    assert not evaluate(order, G("negative", conditions=[C("style_no", "not_contains", "CO")]))
    assert project_rule_items(order, G("header", conditions=[C("store_name", "is_not_empty", "")])).items == [a,b,c]


@pytest.mark.parametrize("count", [1,2,3,4])
def test_all_type_subsets_and_planner(count):
    types = ["sale", "exchange", "return", "preorder"]
    for indices in combinations(range(4), count):
        group = G("types", conditions=[C("销售类型", "in", ",".join(map(str, indices)))])
        kwargs = _query_kwargs_for_rule(group, datetime(2026,11,15), datetime(2026,11,15), None)
        assert kwargs["document_types"] == {types[i] for i in indices}
        for i, kind in enumerate(types):
            assert evaluate(replace(sample("store_name", "text"), document_type=kind), group) == (i in indices)


def test_planner_preserves_cross_item_or_untyped_and_bound_intersections():
    start, end = datetime(2026,11,13), datetime(2026,11,15)
    conditions = [C("unit_price", "gt", "10000"), C("unit_price", "lt", "1000"),
                  C("discount", "equals", "12"), C("style_no", "equals", "CO111")]
    kwargs = _query_kwargs_for_rule(G("local", conditions=conditions), start, end, None)
    assert set(kwargs) == {"start_at", "end_at", "document_types", "return_whole_order"}
    assert kwargs["document_types"] == set()
    conditions = [C("total_amount", "between", "20000,0"), C("total_amount", "gte", "1000"), C("total_amount", "equals", "2000")]
    assert _query_kwargs_for_rule(G("amount", conditions=conditions), start, end, None)["amount_range"] == (2000,2000)
    conditions = [C("document_type", "equals", "0", "any"), C("total_amount", "gt", "10000", "any")]
    kwargs = _query_kwargs_for_rule(G("or", conditions=conditions), start, end, None)
    assert kwargs["document_types"] == set() and "amount_range" not in kwargs


class ProbeSource(EmsSalesDataSource):
    def __init__(self):
        self.username = "anonymous"
        self.password = "fixture"
        self.client = SimpleNamespace(login=lambda *_: None)
        self.calls = []
        self.orders = [SalesOrder(str(i), datetime(2026,11,15), "G00J", 0) for i in range(4)]

    def _query(self, start, end, **kwargs):
        self.calls.append(kwargs)
        ids = set(range(4))
        if "seasons" in kwargs:
            ids = set().union(*({"26FW": {0,1}, "26SS": {1,2}}.get(v,set()) for v in kwargs["seasons"]))
        if "shipment_groups" in kwargs:
            ids = {1,3} if "G6" in kwargs["shipment_groups"] else set()
        return [self.orders[i] for i in sorted(ids)]


@pytest.mark.parametrize("op,value,expected", [
    ("equals", "26FW", {"0","1"}), ("in", "26FW,26SS", {"0","1","2"}),
    ("not_equals", "26FW", {"2","3"}), ("not_in", "26FW,26SS", {"3"}),
    ("in", "absent", set()), ("not_in", "absent", {"0","1","2","3"}),
])
def test_query_only_operators_use_server_membership_without_fabricated_fields(op,value,expected):
    source = ProbeSource()
    c = C("季号", op, value)
    orders = source.load_orders(document_types=set(), ems_rule_conditions=[c])
    assert {o.order_no for o in orders if evaluate(o,G("season",conditions=[c]))} == expected
    assert all(order_field_values(o,"season") == [] for o in orders)
    assert all(len(q["seasons"]) == 1 for q in source.calls if "seasons" in q)


def test_separate_query_proofs_preserve_and_or_and_repeat_same_field():
    source = ProbeSource()
    a,b,c = C("season","equals","26FW"), C("season","equals","26SS"), C("shipment_group","equals","G6")
    orders = source.load_orders(document_types=set(), ems_rule_conditions=[a,b,c])
    assert len(source.calls) == 4
    assert {o.order_no for o in orders if evaluate(o,G("and",conditions=[a,b]))} == {"1"}
    assert {o.order_no for o in orders if evaluate(o,G("or",match_mode="any",conditions=[a,c]))} == {"0","1","3"}
    mixed = G("mixed", conditions=[replace(a,condition_group="any"), C("order_no","equals","3","any")])
    assert {o.order_no for o in orders if evaluate(o,mixed)} == {"0","1","3"}


@pytest.mark.parametrize("op,value", [("contains","26"),("is_empty",""),("equals","")])
def test_invalid_server_rule_rejected_before_network(op,value):
    source = ProbeSource()
    with pytest.raises(ValueError):
        source.load_orders(ems_rule_conditions=[C("season",op,value)])
    assert source.calls == []


def test_server_probe_failure_cannot_become_negative_match():
    source = ProbeSource()
    original = source._query
    def failing(start,end,**kwargs):
        if "seasons" in kwargs:
            raise ConnectionError("probe unavailable")
        return original(start,end,**kwargs)
    source._query = failing
    with pytest.raises(ConnectionError):
        source.load_orders(ems_rule_conditions=[C("season","not_in","26FW")])


def test_complete_item_queries_and_direct_false_projection():
    source = ProbeSource()
    a,b,c = (SalesLineItem("a","CO111",20000,attributes={"discount":0}),
             SalesLineItem("b","JA222",100,attributes={"discount":12}),
             SalesLineItem("c","OT333",50,attributes={"discount":0}))
    source.orders = [replace(source.orders[0],items=[a,b,c])]
    source._query = lambda *args, **kwargs: source.orders
    kwargs = dict(document_types=set(),unit_price_range=(10000,None), unit_discount_range=(12,12))
    assert source.load_orders(**kwargs)[0].items == [a,b,c]
    assert source.load_orders(**kwargs,return_whole_order=False)[0].items == [a,b]


def test_all_local_operators_survive_saved_value_parsing():
    from wecom_sales_webhook_bot.runtime_settings import _parse_condition_value
    for field,label,kind,op in CASES:
        positive,negative = {"text":TEXT,"number":NUMBER,"datetime":DATE}[kind][op]
        for value,expected in ((positive,True),(negative,False)):
            parsed = _parse_condition_value(SimpleNamespace(field_name=label,operator=op,value_json=value))
            order = sample(field,kind)
            if op in {"is_empty","is_not_empty"}:
                expected = op == "is_not_empty"
            assert evaluate(order,G("saved",conditions=[C(field,op,parsed)])) == expected,(field,op,value,parsed)


@pytest.mark.parametrize("whole",[True,False])
def test_pipeline_sale_preorder_projection_and_dedup_use_temporary_state(tmp_path,monkeypatch,whole):
    from wecom_sales_webhook_bot.orchestrator import run_once
    from wecom_sales_webhook_bot.runtime_settings import RuntimeControls
    large,small = SalesLineItem("L","CO111",20000),SalesLineItem("S","JA222",100)
    orders = [SalesOrder(kind,datetime(2026,11,15),"G00J",20100,document_type=kind,items=[large,small])
              for kind in ("sale","preorder","exchange","return")]
    rendered=[]
    def render(**kwargs):
        rendered.append(kwargs["order"])
        return kwargs["order"].order_no
    monkeypatch.setattr("wecom_sales_webhook_bot.orchestrator.build_markdown_v2_message",render)
    sent=[]
    kwargs=dict(data_source=SimpleNamespace(load_orders=lambda **_:orders),sales_filter=None,
        image_provider=SimpleNamespace(get_url=lambda _:None),state_file=tmp_path/"isolated.json",
        webhook_client=SimpleNamespace(send_markdown_v2=sent.append),max_images=8,dry_run=False,
        database_rule_groups=[G("sale/preorder",conditions=[C("document_type","in","0,3"),C("unit_price","gte","10000")])],
        runtime_controls=RuntimeControls(1200,8,0,return_whole_order=whole),
        service_started_at=datetime(2026,11,15),now_func=lambda:datetime(2026,11,15,12))
    assert run_once(**kwargs) == ["sale","preorder"]
    assert sent == ["sale","preorder"]
    assert all(o.items == ([large,small] if whole else [large]) for o in rendered)
    assert run_once(**kwargs) == []
    assert len(sent)==2
