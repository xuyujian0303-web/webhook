from __future__ import annotations

import logging
from datetime import datetime

from wecom_sales_webhook_bot.csv_source import _parse_sold_at
from wecom_sales_webhook_bot.datasource_config import SqlServerDataSourceConfig
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder


LOGGER = logging.getLogger(__name__)
_ORDER_TEXT_FIELDS = (
    "salesperson",
    "customer_source",
    "promotion_material",
    "card_type",
)


class SqlServerSalesDataSource:
    def __init__(self, config: SqlServerDataSourceConfig, connector=None) -> None:
        self._config = config
        self._connector = connector or self._default_connector

    @staticmethod
    def _default_connector(connection_string: str):
        try:
            import pyodbc
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "pyodbc is required for sqlserver data source. Install it with `pip install pyodbc`."
            ) from exc
        return pyodbc.connect(connection_string)

    @staticmethod
    def _normalize_sold_at(value) -> datetime:
        if isinstance(value, datetime):
            return value
        return _parse_sold_at(str(value).strip())

    def load_orders(self) -> list[SalesOrder]:
        grouped: dict[str, dict[str, object]] = {}
        connection = self._connector(self._config.connection_string)
        cursor = connection.cursor()
        try:
            cursor.execute(self._config.query)
            columns = [item[0] for item in cursor.description]
            mapping = self._config.field_mapping

            def optional_text(row: dict[str, object], field_name: str) -> str | None:
                column = mapping.get(field_name)
                if not column:
                    return None
                value = row.get(column)
                if value is None:
                    return None
                text = str(value).strip()
                return text or None

            for raw_row in cursor.fetchall():
                row = dict(zip(columns, raw_row))
                try:
                    required = {
                        "order_no": str(row[mapping["order_no"]]).strip(),
                        "sold_at": row[mapping["sold_at"]],
                        "store_name": str(row[mapping["store_name"]]).strip(),
                        "total_amount": row[mapping["total_amount"]],
                        "barcode": str(row[mapping["barcode"]]).strip(),
                        "style_no": str(row[mapping["style_no"]]).strip(),
                        "unit_price": row[mapping["unit_price"]],
                    }
                    if any(value in (None, "") for value in required.values()):
                        raise ValueError("required sqlserver field is empty")
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning("skip malformed sqlserver row: %s", exc)
                    continue

                order_no = required["order_no"]
                order_fields = {
                    field_name: optional_text(row, field_name)
                    for field_name in _ORDER_TEXT_FIELDS
                }
                quantity_column = mapping.get("total_quantity")
                quantity_value = row.get(quantity_column) if quantity_column else None
                item = SalesLineItem(
                    barcode=required["barcode"],
                    style_no=required["style_no"],
                    unit_price=float(required["unit_price"]),
                    brand=optional_text(row, "brand"),
                    category=optional_text(row, "category"),
                    image_url=optional_text(row, "image_url"),
                )
                if order_no not in grouped:
                    grouped[order_no] = {
                        "order_no": order_no,
                        "sold_at": self._normalize_sold_at(required["sold_at"]),
                        "store_name": required["store_name"],
                        "total_amount": float(required["total_amount"]),
                        **order_fields,
                        "total_quantity": quantity_value,
                        "items": [],
                    }
                else:
                    for field_name, value in order_fields.items():
                        if value and grouped[order_no].get(field_name) not in (None, value):
                            LOGGER.warning("conflicting order field %s for %s", field_name, order_no)
                    if quantity_value is not None and grouped[order_no].get("total_quantity") not in (None, quantity_value):
                        LOGGER.warning("conflicting order field total_quantity for %s", order_no)
                grouped[order_no]["items"].append(item)
        finally:
            if hasattr(cursor, "close"):
                cursor.close()
            if hasattr(connection, "close"):
                connection.close()

        return [SalesOrder(**payload) for payload in grouped.values()]
