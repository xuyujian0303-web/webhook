from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


# Chinese business names are the supported configuration interface.  The
# internal key is the SQL SELECT alias and must remain stable for downstream code.
FIELD_SPECS: dict[str, tuple[str, str, bool]] = {
    "销售单号": ("order_no", "order.order_no", True),
    "销售时间": ("sold_at", "order.sold_at", True),
    "门店": ("store_name", "order.store_name", True),
    "销售总金额": ("total_amount", "order.total_amount", True),
    "销售人员": ("salesperson", "order.salesperson", False),
    "整单件数": ("total_quantity", "order.total_quantity", False),
    "顾客来源": ("customer_source", "order.customer_source", False),
    "助力素材": ("promotion_material", "order.promotion_material", False),
    "卡类型": ("card_type", "order.card_type", False),
    "商品条码": ("barcode", "item.barcode", True),
    "款号": ("style_no", "item.style_no", True),
    "商品单价": ("unit_price", "item.unit_price", True),
    "商品品牌": ("brand", "item.brand", False),
    "商品品类": ("category", "item.category", False),
    "商品图片URL": ("image_url", "item.image_url", False),
}


@dataclass(frozen=True)
class SqlServerDataSourceConfig:
    connection_string: str
    query: str
    field_mapping: dict[str, str]
    database_columns: dict[str, str]


@dataclass(frozen=True)
class DataSourceConfig:
    sqlserver: SqlServerDataSourceConfig


def _normalize_field_mapping(raw_mapping: object) -> tuple[dict[str, str], dict[str, str]]:
    if not isinstance(raw_mapping, dict):
        raise ValueError("sqlserver.field_mapping must be a mapping")

    uses_three_layer_format = any(key in FIELD_SPECS for key in raw_mapping)
    field_mapping: dict[str, str] = {}
    database_columns: dict[str, str] = {}

    if uses_three_layer_format:
        for business_name, (internal_key, template_variable, required) in FIELD_SPECS.items():
            entry = raw_mapping.get(business_name)
            if entry is None:
                if required:
                    raise ValueError(f"缺少必填字段映射: {business_name}")
                continue
            if not isinstance(entry, dict):
                raise ValueError(f"字段映射“{business_name}”必须包含“数据库字段名”")

            database_column = entry.get("数据库字段名")
            if database_column is None or not str(database_column).strip():
                raise ValueError(f"字段映射“{business_name}”缺少“数据库字段名”")

            configured_template_variable = entry.get("模板变量")
            if (
                configured_template_variable is not None
                and str(configured_template_variable).strip() != template_variable
            ):
                raise ValueError(
                    f"字段映射“{business_name}”的模板变量必须是“{template_variable}”"
                )

            field_mapping[internal_key] = str(database_column).strip()
            database_columns[internal_key] = str(database_column).strip()
        return field_mapping, database_columns

    # Compatibility with existing datasource.local.yaml files: internal key ->
    # SQL result column. New configurations should use the Chinese three-layer form.
    for internal_key, database_column in raw_mapping.items():
        if database_column is None or not str(database_column).strip():
            continue
        field_mapping[str(internal_key)] = str(database_column).strip()
        database_columns[str(internal_key)] = str(database_column).strip()
    return field_mapping, database_columns


def load_data_source_config(path: Path) -> DataSourceConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sqlserver_section = raw.get("sqlserver")
    if sqlserver_section is None:
        raise ValueError("Missing required section in datasource config: 'sqlserver'")

    try:
        connection_string = sqlserver_section["connection_string"]
        query = sqlserver_section["query"]
        raw_field_mapping = sqlserver_section["field_mapping"]
    except KeyError as e:
        raise ValueError(f"Missing required key in sqlserver datasource section: {e.args[0]!r}")

    field_mapping, database_columns = _normalize_field_mapping(raw_field_mapping)
    return DataSourceConfig(
        sqlserver=SqlServerDataSourceConfig(
            connection_string=str(connection_string),
            query=str(query).strip(),
            field_mapping=field_mapping,
            database_columns=database_columns,
        )
    )