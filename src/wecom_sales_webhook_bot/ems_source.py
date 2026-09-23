from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from .ems_client import EmsTcpClient
from .ems_decoder import decode_sale_detail_orders
from .rule_service import normalize_document_type
from .sales_fields import order_field_values


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

    def load_orders(self, start_at: datetime | None = None, end_at: datetime | None = None,
                    amount_threshold: float | None = None,
                    store_names: set[str] | None = None,
                    document_types: set[str] | None = None, style_numbers: set[str] | None = None,
                    seasons: set[str] | None = None, shipment_groups: set[str] | None = None,
                    unit_price_threshold: float | None = None, unit_discount_threshold: float | None = None,
                    return_whole_order: bool = True,
                    amount_range: tuple[float | None, float | None] | None = None,
                    unit_price_range: tuple[float | None, float | None] | None = None,
                    unit_discount_range: tuple[float | None, float | None] | None = None):
        if document_types is None:
            document_types = {"sale"}
        if store_names is not None:
            store_names = {
                str(value).strip().upper()
                for value in store_names
                if str(value).strip()
            }
        start = (start_at or datetime(2023, 9, 20)).strftime("%Y%m%d")
        end = (end_at or datetime.now()).strftime("%Y%m%d")
        self.client.login(self.username, self.password)
        server_query_succeeded = True
        try:
            payload = self.client.query_sale_detail(
                start, end, store_names=store_names, amount_threshold=amount_threshold,
                document_types=document_types, style_numbers=style_numbers, seasons=seasons,
                shipment_groups=shipment_groups, unit_price_threshold=unit_price_threshold,
                unit_discount_threshold=unit_discount_threshold, return_whole_order=return_whole_order,
                amount_range=amount_range, unit_price_range=unit_price_range,
                unit_discount_range=unit_discount_range)
        except ConnectionError:
            if any((
                store_names, document_types, style_numbers, seasons, shipment_groups,
                amount_threshold is not None, amount_range is not None,
                unit_price_threshold is not None, unit_price_range is not None,
                unit_discount_threshold is not None, unit_discount_range is not None,
            )):
                raise
            server_query_succeeded = False
            payload = self.client.query_sale_detail(start, end)
        orders = decode_sale_detail_orders(payload)
        # EMS may return records just outside the visible date range. Enforce
        # the requested local boundary after decoding to match the GUI export.
        if start_at is not None:
            start_day = start_at.date()
            orders = [order for order in orders if order.sold_at.date() >= start_day]
        if end_at is not None:
            end_day = end_at.date()
            orders = [order for order in orders if order.sold_at.date() <= end_day]
        # EMS query frames currently expose only the date range. Apply the
        # remaining rule predicates immediately after decoding, before the
        # orchestrator performs deduplication and push decisions.
        if amount_threshold is not None or amount_range is not None or store_names:
            amount_low, amount_high = amount_range or (amount_threshold, None)
            orders = [order for order in orders
                      if (amount_low is None or order.total_amount >= amount_low)
                      and (amount_high is None or order.total_amount <= amount_high)
                      and (not store_names or order.store_name.strip().upper() in store_names)]
        if document_types:
            wanted_types = {
                normalize_document_type(value)
                for value in document_types
                if str(value).strip()
            }
            orders = [order for order in orders
                      if normalize_document_type(order.document_type) in wanted_types]
        if style_numbers:
            wanted = {str(value).strip().upper() for value in style_numbers if str(value).strip()}
            orders = [order for order in orders if any(
                any(wanted_value in value.upper() for wanted_value in wanted)
                for value in order_field_values(order, "style_no")
            )]
        if unit_price_range is not None:
            low, high = unit_price_range
            orders = [order for order in orders if any(
                (low is None or item.unit_price >= low)
                and (high is None or item.unit_price <= high)
                for item in order.items
            )]
        if server_query_succeeded:
            marked_orders = []
            for order in orders:
                server_fields = set()
                if unit_discount_range is not None or unit_discount_threshold is not None:
                    server_fields.add("discount")
                if seasons:
                    server_fields.add("season")
                if shipment_groups:
                    server_fields.add("shipment_group")
                if server_fields:
                    order = replace(
                        order,
                        attributes={
                            **order.attributes,
                            "_ems_server_filtered_fields": sorted(server_fields),
                        },
                    )
                marked_orders.append(order)
            orders = marked_orders
        return orders
