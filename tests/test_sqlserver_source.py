from datetime import datetime

from wecom_sales_webhook_bot.datasource_config import SqlServerDataSourceConfig
from wecom_sales_webhook_bot.sqlserver_source import SqlServerSalesDataSource


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.description = [(name,) for name in (
            "order_no", "sold_at", "store_name", "total_amount", "barcode",
            "style_no", "unit_price", "brand", "category", "image_url",
            "salesperson", "total_quantity", "customer_source",
            "promotion_material", "card_type",
        )]
        self.executed = []

    def execute(self, query: str):
        self.executed.append(query)
        return self

    def fetchall(self):
        return list(self._rows)

    def close(self) -> None:
        return None


class _FakeConnection:
    def __init__(self, rows):
        self.closed = False
        self.cursor_instance = _FakeCursor(rows)

    def cursor(self):
        return self.cursor_instance

    def close(self) -> None:
        self.closed = True


def test_sqlserver_source_groups_rows_and_keeps_order_fields_once() -> None:
    rows = [
        ("SO-1001", "2026-06-26 12:19:00", "G830", 82280, "B1", "S1", 93500, "Brand-A", "Coat", "http://intranet.images/1.jpg", "张三", 2, "会员推荐", "秋季画册", "金卡"),
        ("SO-1001", datetime(2026, 6, 26, 12, 19), "G830", 82280, "B2", "S2", 12000, "Brand-A", "Coat", "http://intranet.images/2.jpg", "张三", 2, "会员推荐", "秋季画册", "金卡"),
    ]
    connections = []

    def fake_connector(connection_string: str):
        assert "Server=localhost" in connection_string
        connection = _FakeConnection(rows)
        connections.append(connection)
        return connection

    config = SqlServerDataSourceConfig(
        connection_string="Driver={ODBC Driver 17 for SQL Server};Server=localhost;",
        query="SELECT * FROM dbo.sales_lines",
        field_mapping={name: name for name in (
            "order_no", "sold_at", "store_name", "total_amount", "barcode",
            "style_no", "unit_price", "brand", "category", "image_url",
            "salesperson", "total_quantity", "customer_source",
            "promotion_material", "card_type",
        )},
        database_columns={},
    )

    orders = SqlServerSalesDataSource(config, connector=fake_connector).load_orders()

    assert len(orders) == 1
    assert orders[0].order_no == "SO-1001"
    assert orders[0].salesperson == "张三"
    assert orders[0].total_quantity == 2
    assert orders[0].customer_source == "会员推荐"
    assert orders[0].promotion_material == "秋季画册"
    assert orders[0].card_type == "金卡"
    assert [item.image_url for item in orders[0].items] == [
        "http://intranet.images/1.jpg", "http://intranet.images/2.jpg"
    ]
    assert connections[0].cursor_instance.executed == ["SELECT * FROM dbo.sales_lines"]
    assert connections[0].closed is True
