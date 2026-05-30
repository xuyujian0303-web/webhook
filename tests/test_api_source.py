from datetime import datetime

from wecom_sales_webhook_bot.api_source import SalesApiDataSource


class FakeSession:
    def get(self, url, headers, params, timeout):
        class Response:
            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def json():
                return {
                    "items": [
                        {
                            "order_no": "SO-API-1",
                            "sold_at": "2026-04-22T10:00:00",
                            "store_name": "G621",
                            "total_amount": 19250,
                            "barcode": "b1",
                            "style_no": "PA17047BNY0",
                            "unit_price": 5850,
                            "brand": "Brand-A",
                            "category": "外套",
                            "image_url": "https://img.example.com/p1.jpg",
                        },
                        {
                            "order_no": "SO-API-1",
                            "sold_at": "2026-04-22T10:00:00",
                            "store_name": "G621",
                            "total_amount": 19250,
                            "barcode": "b2",
                            "style_no": "PA15161ENY0",
                            "unit_price": 7550,
                            "brand": "Brand-B",
                            "category": "连衣裙",
                            "image_url": "https://img.example.com/p2.jpg",
                        },
                    ]
                }

        return Response()


def test_sales_api_data_source_groups_api_rows_into_orders() -> None:
    source = SalesApiDataSource(
        base_url="https://internal.example.com",
        path="/sales/query",
        token="token-1",
        timeout_seconds=10,
        session=FakeSession(),
    )

    orders = source.load_orders(
        start_at=datetime(2026, 4, 22, 10, 0, 0),
        end_at=datetime(2026, 4, 22, 10, 20, 0),
    )

    assert len(orders) == 1
    assert orders[0].order_no == "SO-API-1"
    assert len(orders[0].items) == 2
    assert orders[0].items[1].image_url == "https://img.example.com/p2.jpg"
