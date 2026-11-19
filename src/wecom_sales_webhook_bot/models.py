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
    attributes: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SalesOrder:
    order_no: str
    sold_at: datetime
    store_name: str
    total_amount: float
    performance_org: str | None = None
    store_name_display: str | None = None
    performance_org_display: str | None = None
    salesperson: str | None = None
    total_quantity: int | float | str | None = None
    customer_source: str | None = None
    promotion_material: str | None = None
    activity_type: str | None = None
    card_type: str | None = None
    customer_type: str | None = None
    document_type: str = "sale"
    attributes: dict[str, object] = field(default_factory=dict)
    items: list[SalesLineItem] = field(default_factory=list)
