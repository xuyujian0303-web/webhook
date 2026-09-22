from datetime import datetime
from pathlib import Path

from wecom_sales_webhook_bot.filters import SalesFilter
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder
from wecom_sales_webhook_bot.state_store import PushStateStore


def test_filter_matches_amount_or_style_and_state_blocks_duplicates(
    tmp_path: Path,
) -> None:
    order = SalesOrder(
        order_no="SO-900",
        sold_at=datetime(2026, 4, 20, 10, 0, 0),
        store_name="上海一店",
        total_amount=800,
        items=[
            SalesLineItem(barcode="6901111111111", style_no="VIP-001", unit_price=800)
        ],
    )

    sales_filter = SalesFilter(amount_threshold=1000, style_whitelist={"VIP-001"})
    result = sales_filter.evaluate(order)

    assert result.matched is True
    assert result.reason == "style_whitelist"

    state_store = PushStateStore(tmp_path / "push-state.json")
    assert state_store.has_pushed("SO-900") is False
    state_store.mark_pushed("SO-900", sold_at=order.sold_at)
    assert state_store.has_pushed("SO-900") is True


def test_amount_filter_requires_strictly_more_than_threshold() -> None:
    def order(amount: float) -> SalesOrder:
        return SalesOrder(
            order_no=f"SO-{amount}",
            sold_at=datetime(2026, 4, 20, 10, 0),
            store_name="G621",
            total_amount=amount,
            items=[],
        )

    sales_filter = SalesFilter(amount_threshold=1000, style_whitelist=set())
    assert sales_filter.evaluate(order(999.99)).matched is False
    assert sales_filter.evaluate(order(1000)).matched is False
    assert sales_filter.evaluate(order(1000.01)).matched is True
