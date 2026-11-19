from datetime import datetime

from wecom_sales_webhook_bot.celebration import celebration_values
from wecom_sales_webhook_bot.config import load_config
from wecom_sales_webhook_bot.models import SalesOrder
from wecom_sales_webhook_bot.store_mapping import (
    load_region_mapping_file,
    load_store_mapping_file,
)


def test_mapping_file_loads_region_and_store_name_for_each_org(tmp_path):
    mapping = tmp_path / "store_mapping.yaml"
    mapping.write_text(
        "G001:\n  region: 华东区域\n  store_name: 上海示例店\n"
        "G002:\n  region: 华南区域\n  store_name: 深圳示例店\n",
        encoding="utf-8",
    )

    assert load_store_mapping_file(mapping) == {
        "G001": "上海示例店",
        "G002": "深圳示例店",
    }
    assert load_region_mapping_file(mapping) == {
        "G001": "华东区域",
        "G002": "华南区域",
    }


def test_legacy_store_name_mapping_still_loads_without_region(tmp_path):
    mapping = tmp_path / "store_mapping.yaml"
    mapping.write_text("G001: 上海示例店\n", encoding="utf-8")

    assert load_store_mapping_file(mapping) == {"G001": "上海示例店"}
    assert load_region_mapping_file(mapping) == {}


def test_config_exposes_region_mapping(tmp_path):
    mapping = tmp_path / "store_mapping.yaml"
    mapping.write_text(
        "G001:\n  region: 华东区域\n  store_name: 上海示例店\n",
        encoding="utf-8",
    )
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        f"""
store_mapping_file: {mapping.name}
wecom:
  webhook_url: https://example.invalid
  timeout_seconds: 5
  retry_times: 0
runtime:
  scan_interval_seconds: 60
  max_images_per_message: 8
  state_file: ./state.json
  dry_run: true
""",
        encoding="utf-8",
    )

    config = load_config(config_file)
    assert config.store_mapping["G001"] == "上海示例店"
    assert config.region_mapping["G001"] == "华东区域"


def test_celebration_values_exposes_independent_sales_and_performance_names_and_regions():
    order = SalesOrder(
        order_no="SO-1",
        sold_at=datetime(2026, 11, 18),
        store_name="G001",
        store_name_display="上海销售店",
        performance_org="G002",
        performance_org_display="深圳业绩店",
        total_amount=120000,
        attributes={
            "store_region": "华东区域",
            "performance_region": "华南区域",
            "region": "华东区域",
        },
    )

    values = celebration_values(order)
    assert values["store_name_display"] == "上海销售店"
    assert values["performance_org_display"] == "深圳业绩店"
    assert values["store_region"] == "华东区域"
    assert values["performance_region"] == "华南区域"
    assert values["region"] == "华南区域"
