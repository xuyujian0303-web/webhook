from pathlib import Path

import pytest

from wecom_sales_webhook_bot.datasource_config import load_data_source_config


def _write_config(tmp_path: Path, field_mapping: str) -> Path:
    path = tmp_path / "datasource.yaml"
    path.write_text(
        f"""
sqlserver:
  connection_string: Driver={{ODBC Driver 17 for SQL Server}};Server=localhost;
  query: SELECT 1
  field_mapping:
{field_mapping}
""".strip(),
        encoding="utf-8",
    )
    return path


def test_three_layer_mapping_preserves_it_column_and_uses_internal_aliases(
    tmp_path: Path,
) -> None:
    config = load_data_source_config(
        _write_config(
            tmp_path,
            """    销售单号:
      数据库字段名: SALES_ORDER_NO
      模板变量: order.order_no
    销售时间:
      数据库字段名: 成交时间
      模板变量: order.sold_at
    门店:
      数据库字段名: STORE_NAME
      模板变量: order.store_name
    销售总金额:
      数据库字段名: SALE_AMOUNT
      模板变量: order.total_amount
    商品条码:
      数据库字段名: SKU_BARCODE
      模板变量: item.barcode
    款号:
      数据库字段名: STYLE_CODE
      模板变量: item.style_no
    商品单价:
      数据库字段名: LINE_PRICE
      模板变量: item.unit_price""",
        )
    )

    assert config.sqlserver.field_mapping["order_no"] == "SALES_ORDER_NO"
    assert config.sqlserver.field_mapping["sold_at"] == "成交时间"
    assert config.sqlserver.database_columns["order_no"] == "SALES_ORDER_NO"
    assert config.sqlserver.database_columns["sold_at"] == "成交时间"


def test_three_layer_mapping_rejects_missing_required_business_field(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="销售单号"):
        load_data_source_config(_write_config(tmp_path, "    销售人员: 导购姓名"))


def test_three_layer_mapping_rejects_changed_public_template_variable(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="模板变量"):
        load_data_source_config(
            _write_config(
                tmp_path,
                """    销售单号:
      数据库字段名: SALES_ORDER_NO
      模板变量: order.changed""",
            )
        )
