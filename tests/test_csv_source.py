from pathlib import Path

from wecom_sales_webhook_bot.config import load_config
from wecom_sales_webhook_bot.csv_source import CsvSalesDataSource


def test_csv_source_groups_rows_by_order_number(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
csv:
  path: ./sales.csv
  encoding: utf-8-sig
  field_mapping:
    order_no: 销售单号
    sold_at: 销售日期（时间）
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
  webhook_url: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test
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
                "销售单号,销售日期（时间）,销售门店,销售单总额,商品条码,产品款号,产品单价",
                "SO-001,2026-04-20 10:00:00,上海一店,1200,6901111111111,A1001,699",
                "SO-001,2026-04-20 10:00:00,上海一店,1200,6902222222222,B2002,501",
            ]
        ),
        encoding="utf-8-sig",
    )

    config = load_config(config_file)
    data_source = CsvSalesDataSource(config.csv, base_dir=tmp_path)

    orders = data_source.load_orders()

    assert len(orders) == 1
    assert orders[0].order_no == "SO-001"
    assert orders[0].store_name == "上海一店"
    assert [item.barcode for item in orders[0].items] == [
        "6901111111111",
        "6902222222222",
    ]


def test_csv_source_skips_rows_missing_required_fields(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
csv:
  path: ./sales.csv
  encoding: utf-8-sig
  field_mapping:
    order_no: 销售单号
    sold_at: 销售日期（时间）
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
  webhook_url: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test
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
                "销售单号,销售日期（时间）,销售门店,销售单总额,商品条码,产品款号,产品单价",
                "SO-001,2026-04-20 10:00:00,上海一店,1200,6901111111111,A1001,699",
                "SO-002,2026-04-20 10:05:00,上海一店,1300,,B2002,1300",
            ]
        ),
        encoding="utf-8-sig",
    )

    config = load_config(config_file)
    orders = CsvSalesDataSource(config.csv, base_dir=tmp_path).load_orders()

    assert [order.order_no for order in orders] == ["SO-001"]
