from __future__ import annotations

from datetime import datetime

from .ems_client import EmsTcpClient
from .ems_decoder import decode_sale_detail_orders


class EmsSalesDataSource:
    def __init__(self, config: dict):
        self.username = config["username"]
        self.password = config["password"]
        self.client = EmsTcpClient(config["auth_host"], int(config["auth_port"]), config["data_host"], int(config["data_port"]), int(config.get("timeout_seconds", 15)))

    def load_orders(self, start_at: datetime | None = None, end_at: datetime | None = None,
                    amount_threshold: float | None = None,
                    store_names: set[str] | None = None,
                    document_types: set[str] | None = None):
        start = (start_at or datetime.now()).strftime("%Y%m%d")
        end = (end_at or datetime.now()).strftime("%Y%m%d")
        self.client.login(self.username, self.password)
        try:
            payload = self.client.query_sale_detail(
                start, end, store_names=store_names, amount_threshold=amount_threshold,
                document_types=document_types)
        except ConnectionError:
            # Some EMS servers close the socket for the captured amount-filter
            # shape. Retry the verified broad query and apply the strict
            # whole-order threshold locally below.
            payload = self.client.query_sale_detail(
                start, end, store_names=store_names, amount_threshold=None,
                document_types=document_types)
        orders = decode_sale_detail_orders(payload)
        # EMS query frames currently expose only the date range. Apply the
        # remaining rule predicates immediately after decoding, before the
        # orchestrator performs deduplication and push decisions.
        if amount_threshold is not None or store_names:
            orders = [order for order in orders
                      if (amount_threshold is None or order.total_amount > amount_threshold)
                      and (not store_names or order.store_name in store_names)]
        return orders
