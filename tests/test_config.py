from pathlib import Path

from wecom_sales_webhook_bot.config import load_config


def test_load_config_reads_threshold_and_style_whitelist(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
csv:
  path: ./data/sales.csv
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
  style_whitelist: ["A1001", "B2002"]
runtime:
  scan_interval_seconds: 600
  max_images_per_message: 8
  state_file: ./var/push-state.json
  dry_run: false
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.rules.amount_threshold == 1000
    assert config.rules.style_whitelist == {"A1001", "B2002"}
    assert config.runtime.max_images_per_message == 8
