from datetime import datetime
from pathlib import Path

from wecom_sales_webhook_bot.config import load_config
from wecom_sales_webhook_bot.csv_source import CsvSalesDataSource
from wecom_sales_webhook_bot.filters import FilterResult
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder
from wecom_sales_webhook_bot.orchestrator import run_once
from wecom_sales_webhook_bot.ems_decoder import build_ems_image_url


def test_ems_image_url_uses_full_product_code() -> None:
    assert (
        build_ems_image_url("GJA14344PIBL0B6")
        == "http://giada-erp.redstone.com.cn/giada/images/GJA14344PIBL0B6_01.jpg"
    )


def test_csv_source_parses_slash_date_with_am_pm(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
csv:
  path: ./sales.csv
  encoding: gbk
  field_mapping:
    order_no: 销售单号
    sold_at: 销售日期
    store_name: 销售门店
    total_amount: 销售单总额
    barcode: 商品条码
    style_no: 产品款号
    unit_price: 产品单价
image_service:
  host: 127.0.0.1
  port: 8123
  image_dir: ./images
wecom:
  webhook_url: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_WEBHOOK_KEY
  timeout_seconds: 5
  retry_times: 2
rules:
  amount_threshold: 1000
  style_whitelist: []
runtime:
  scan_interval_seconds: 600
  max_images_per_message: 8
  state_file: ./var/push-state.json
  dry_run: false
""".strip(),
        encoding="utf-8",
    )
    sales_file = tmp_path / "sales.csv"
    sales_file.write_text(
        "\n".join(
            [
                "销售单号,销售日期,销售门店,销售单总额,商品条码,产品款号,产品单价",
                "SO-001,2026/4/20 10:50 AM,G609,14500,GPA22056EINY0B6380001,PA22056ENY0,14500",
            ]
        ),
        encoding="gbk",
    )

    config = load_config(config_file)
    orders = CsvSalesDataSource(config.csv, base_dir=tmp_path).load_orders()

    assert len(orders) == 1
    assert orders[0].sold_at == datetime(2026, 4, 20, 10, 50, 0)


class _FakeDataSource:
    def load_orders(self):
        return [
            SalesOrder(
                order_no="SO-STYLE",
                sold_at=datetime(2026, 4, 20, 10, 50, 0),
                store_name="G609",
                total_amount=14500,
                items=[
                    SalesLineItem(
                        barcode="GPA22056EINY0B6380001",
                        style_no="PA22056ENY0",
                        unit_price=14500,
                    )
                ],
            )
        ]


class _FakeFilter:
    def evaluate(self, order):
        return FilterResult(matched=True, reason="amount_threshold")


class _StyleOnlyImageProvider:
    def get_url(self, key):
        if key == "PA22056ENY0":
            return "http://127.0.0.1:8123/PA22056ENY0.png"
        return None


class _FakeClient:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send_markdown_v2(self, content):
        self.messages.append(content)


def test_run_once_falls_back_to_style_number_for_images(tmp_path: Path) -> None:
    client = _FakeClient()

    sent = run_once(
        data_source=_FakeDataSource(),
        sales_filter=_FakeFilter(),
        image_provider=_StyleOnlyImageProvider(),
        state_file=tmp_path / "state.json",
        webhook_client=client,
        max_images=8,
        dry_run=False,
    )

    assert sent == ["SO-STYLE"]
    assert len(client.messages) == 1
    assert "PA22056ENY0.png" in client.messages[0]
