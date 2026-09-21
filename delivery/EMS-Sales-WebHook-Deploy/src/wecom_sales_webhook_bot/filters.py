from __future__ import annotations

from dataclasses import dataclass

from wecom_sales_webhook_bot.models import SalesOrder


@dataclass(frozen=True)
class FilterResult:
    matched: bool
    reason: str | None


class SalesFilter:
    def __init__(self, amount_threshold: float, style_whitelist: set[str]) -> None:
        self._amount_threshold = amount_threshold
        self._style_whitelist = style_whitelist

    def evaluate(self, order: SalesOrder) -> FilterResult:
        if order.total_amount > self._amount_threshold:
            return FilterResult(matched=True, reason="amount_threshold")
        if any(item.style_no in self._style_whitelist for item in order.items):
            return FilterResult(matched=True, reason="style_whitelist")
        return FilterResult(matched=False, reason=None)
