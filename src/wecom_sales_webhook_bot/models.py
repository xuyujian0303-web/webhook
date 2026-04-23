from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class SalesLineItem:
    barcode: str
    style_no: str
    unit_price: float
    quantity: int = 1
    brand: str | None = None
    category: str | None = None
    image_url: str | None = None


@dataclass(frozen=True)
class SalesOrder:
    order_no: str
    sold_at: datetime
    store_name: str
    total_amount: float
    items: list[SalesLineItem] = field(default_factory=list)
