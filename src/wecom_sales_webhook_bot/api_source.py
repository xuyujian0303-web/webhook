from __future__ import annotations

from datetime import datetime

import requests

from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder


class SalesApiDataSource:
    def __init__(
        self,
        base_url: str,
        path: str,
        token: str,
        timeout_seconds: int,
        session=None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._path = path
        self._token = token
        self._timeout_seconds = timeout_seconds
        self._session = session or requests.Session()

    def load_orders(self, start_at: datetime, end_at: datetime) -> list[SalesOrder]:
        response = self._session.get(
            f"{self._base_url}{self._path}",
            headers={"Authorization": f"Bearer {self._token}"},
            params={"start_at": start_at.isoformat(), "end_at": end_at.isoformat()},
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()

        grouped: dict[str, dict] = {}
        for row in response.json()["items"]:
            order_no = row["order_no"]
            grouped.setdefault(
                order_no,
                {
                    "order_no": order_no,
                    "sold_at": datetime.fromisoformat(row["sold_at"]),
                    "store_name": row["store_name"],
                    "total_amount": float(row["total_amount"]),
                    "items": [],
                },
            )
            grouped[order_no]["items"].append(
                SalesLineItem(
                    barcode=row["barcode"],
                    style_no=row["style_no"],
                    unit_price=float(row["unit_price"]),
                    brand=row.get("brand"),
                    category=row.get("category"),
                    image_url=row.get("image_url"),
                )
            )

        return [SalesOrder(**payload) for payload in grouped.values()]
