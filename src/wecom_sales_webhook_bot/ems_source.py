from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from .ems_client import EmsTcpClient
from .ems_decoder import decode_sale_detail_orders
from .rule_service import (
    EMS_QUERY_FIELDS, EMS_QUERY_OPERATORS, RuleConditionDTO,
    _values, normalize_document_type, server_condition_key,
)
from .sales_fields import canonical_field_name


class EmsSalesDataSource:
    def __init__(self, config: dict):
        self.username = config["username"]
        self.password = config["password"]
        self.client = EmsTcpClient(
            config.get("auth_host", "giada-erp.redstone.com.cn"),
            int(config.get("auth_port", 9999)),
            config.get("data_host", "giada-erp.redstone.com.cn"),
            int(config.get("data_port", 9100)),
            int(config.get("timeout_seconds", 15)),
        )

    def _query(self, start: str, end: str, **kwargs):
        try:
            payload = self.client.query_sale_detail(start, end, **kwargs, _omit_empty_parameters=True)
        except ConnectionError:
            # Retry the same conditions, never a wider query.
            payload = self.client.query_sale_detail(start, end, **kwargs, _omit_empty_parameters=False)
        return decode_sale_detail_orders(payload)

    def load_orders(self, start_at: datetime | None = None, end_at: datetime | None = None,
                    amount_threshold: float | None = None,
                    store_names: set[str] | None = None,
                    document_types: set[str] | None = None, style_numbers: set[str] | None = None,
                    seasons: set[str] | None = None, shipment_groups: set[str] | None = None,
                    unit_price_threshold: float | None = None, unit_discount_threshold: float | None = None,
                    return_whole_order: bool = True,
                    amount_range: tuple[float | None, float | None] | None = None,
                    unit_price_range: tuple[float | None, float | None] | None = None,
                    unit_discount_range: tuple[float | None, float | None] | None = None,
                    ems_rule_conditions: list[RuleConditionDTO] | None = None):
        if start_at and end_at and start_at.date() > end_at.date():
            return []
        document_types = {"sale"} if document_types is None else document_types
        stores = {str(v).strip().upper() for v in store_names or set() if str(v).strip()}
        amount_range = amount_range or ((amount_threshold, None) if amount_threshold is not None else None)
        price_range = unit_price_range or ((unit_price_threshold, None) if unit_price_threshold is not None else None)
        discount_range = unit_discount_range or ((unit_discount_threshold, None) if unit_discount_threshold is not None else None)
        direct_conditions = []
        if ems_rule_conditions is None:
            for field, values in (("season", seasons), ("shipment_group", shipment_groups)):
                if values:
                    direct_conditions.append(RuleConditionDTO(field, "in", sorted(values)))
        conditions = ems_rule_conditions if ems_rule_conditions is not None else direct_conditions
        for condition in conditions:
            if canonical_field_name(condition.field_name) not in EMS_QUERY_FIELDS:
                raise ValueError("EMS查询条件只能使用季号或出货组别")
            if condition.operator not in EMS_QUERY_OPERATORS or not _values(condition.value):
                raise ValueError("季号/出货组别支持等于、不等于、属于、不属于；必须提供完整值")
        start = (start_at or datetime(2023, 9, 20)).strftime("%Y%m%d")
        end = (end_at or datetime.now()).strftime("%Y%m%d")
        self.client.login(self.username, self.password)
        query = dict(store_names=stores or None, document_types=document_types,
                     amount_range=amount_range, return_whole_order=True)
        # Item filters can truncate rows or leak unrelated preorders. Use the
        # complete response for local predicates and whole-order messages.
        orders = self._query(start, end, **query)
        if start_at:
            orders = [o for o in orders if o.sold_at.date() >= start_at.date()]
        if end_at:
            orders = [o for o in orders if o.sold_at.date() <= end_at.date()]
        if stores:
            orders = [o for o in orders if o.store_name.strip().upper() in stores]
        if amount_range:
            low, high = amount_range
            orders = [o for o in orders if (low is None or o.total_amount >= low)
                      and (high is None or o.total_amount <= high)]
        if document_types:
            wanted = {normalize_document_type(v) for v in document_types}
            orders = [o for o in orders if normalize_document_type(o.document_type) in wanted]

        proofs = {}
        cache = {}
        for condition in conditions:
            field = canonical_field_name(condition.field_name)
            values = _values(condition.value)
            # A scalar equality uses the first value, consistent with local
            # text rules. Membership accepts multiple complete codes.
            values = values[:1] if condition.operator == "equals" else values
            values = tuple(sorted({v.upper() for v in values}))
            matched_ids = set()
            # EMS treats a comma-joined season/group as one literal code.
            # Query each value and union order membership ourselves.
            for value in values:
                cache_key = (field, value)
                if cache_key not in cache:
                    kwargs = {**query, "seasons" if field == "season" else "shipment_groups": {value}}
                    cache[cache_key] = {o.order_no for o in self._query(start, end, **kwargs)}
                matched_ids.update(cache[cache_key])
            proofs[server_condition_key(condition)] = (
                matched_ids, condition.operator in {"not_equals", "not_in"})
        if proofs:
            orders = [replace(o, attributes={**o.attributes, "_ems_condition_matches": {
                key: ((o.order_no not in ids) if negative else (o.order_no in ids))
                for key, (ids, negative) in proofs.items()
            }}) for o in orders]
        if direct_conditions:
            keys = [server_condition_key(c) for c in direct_conditions]
            orders = [o for o in orders if all(o.attributes["_ems_condition_matches"][k] for k in keys)]

        def within(value, bounds):
            return value is not None and (bounds[0] is None or value >= bounds[0]) and (bounds[1] is None or value <= bounds[1])
        styles = {v.casefold() for v in style_numbers or set()}
        predicates = []
        if styles:
            predicates.append(lambda i: any(v in i.style_no.casefold() for v in styles))
        if price_range is not None:
            predicates.append(lambda i: within(i.unit_price, price_range))
        if discount_range is not None:
            predicates.append(lambda i: within(i.attributes.get("discount"), discount_range))
        orders = [o for o in orders if all(any(predicate(i) for i in o.items) for predicate in predicates)]
        if not return_whole_order and predicates:
            # Preserve the union of matching lines for independent predicates.
            orders = [replace(o, items=[i for i in o.items if any(p(i) for p in predicates)]) for o in orders]
        return orders
