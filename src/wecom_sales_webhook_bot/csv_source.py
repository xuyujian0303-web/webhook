from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path

from wecom_sales_webhook_bot.config import CsvConfig
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder
from wecom_sales_webhook_bot.sales_fields import FIELD_KEYS


LOGGER = logging.getLogger(__name__)


def _parse_sold_at(value: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %I:%M %p", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"unsupported sold_at format: {value}")


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
                try:
                    required = {
                        "order_no": row[mapping["order_no"]].strip(),
                        "sold_at": row[mapping["sold_at"]].strip(),
                        "store_name": row[mapping["store_name"]].strip(),
                        "total_amount": row[mapping["total_amount"]].strip(),
                        "barcode": row[mapping["barcode"]].strip(),
                        "style_no": row[mapping["style_no"]].strip(),
                        "unit_price": row[mapping["unit_price"]].strip(),
                    }
                    if any(value == "" for value in required.values()):
                        raise ValueError("required csv field is empty")
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning("skip malformed csv row: %s", exc)
                    continue

                order_no = required["order_no"]
                item = SalesLineItem(
                    barcode=required["barcode"],
                    style_no=required["style_no"],
                    unit_price=float(required["unit_price"]),
                    quantity=int(row.get(mapping.get("quantity", ""), "1") or "1"),
                    attributes={
                        key: row.get(column, "").strip()
                        for key, column in mapping.items()
                        if key in FIELD_KEYS and key not in {"barcode", "style_no", "unit_price", "quantity"}
                    },
                )
                if order_no not in grouped:
                    grouped[order_no] = {
                        "order_no": order_no,
                        "sold_at": _parse_sold_at(required["sold_at"]),
                        "store_name": required["store_name"],
                        "total_amount": float(required["total_amount"]),
                        "performance_org": row.get(mapping.get("performance_org", ""), "").strip() or None,
                        "salesperson": row.get(mapping.get("salesperson", ""), "").strip() or None,
                        "document_type": row.get(mapping.get("document_type", ""), "sale").strip() or "sale",
                        "attributes": {
                            key: row.get(column, "").strip()
                            for key, column in mapping.items()
                            if key in FIELD_KEYS and key not in {"order_no", "sold_at", "store_name", "performance_org", "salesperson", "document_type", "total_amount", "barcode", "style_no", "unit_price", "quantity"}
                        },
                        "items": [],
                    }
                grouped[order_no]["items"].append(item)

        return [SalesOrder(**payload) for payload in grouped.values()]
