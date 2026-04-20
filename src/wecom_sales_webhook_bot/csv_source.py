from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from wecom_sales_webhook_bot.config import CsvConfig
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder


class CsvSalesDataSource:
    def __init__(self, config: CsvConfig, base_dir: Path) -> None:
        self._config = config
        self._base_dir = base_dir

    def load_orders(self) -> list[SalesOrder]:
        csv_path = (self._base_dir / self._config.path).resolve()
        mapping = self._config.field_mapping
        grouped: dict[str, dict[str, object]] = {}

        with csv_path.open("r", encoding=self._config.encoding, newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                order_no = row[mapping["order_no"]]
                item = SalesLineItem(
                    barcode=row[mapping["barcode"]],
                    style_no=row[mapping["style_no"]],
                    unit_price=float(row[mapping["unit_price"]]),
                    quantity=int(row.get(mapping.get("quantity", ""), "1") or "1"),
                )
                if order_no not in grouped:
                    grouped[order_no] = {
                        "order_no": order_no,
                        "sold_at": datetime.strptime(
                            row[mapping["sold_at"]], "%Y-%m-%d %H:%M:%S"
                        ),
                        "store_name": row[mapping["store_name"]],
                        "total_amount": float(row[mapping["total_amount"]]),
                        "items": [],
                    }
                grouped[order_no]["items"].append(item)

        return [SalesOrder(**payload) for payload in grouped.values()]
