from pathlib import Path

from wecom_sales_webhook_bot.cli import validate_prototype_config
from wecom_sales_webhook_bot.config import load_config
from wecom_sales_webhook_bot.datasource_config import load_data_source_config


def test_load_config_reads_separate_sqlserver_datasource_reference(
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
data_source:
  kind: sqlserver
  config_path: ./datasource.local.yaml
image_service:
  host: 127.0.0.1
  port: 8123
  image_dir: ./images
wecom:
  webhook_url: https://example.com
  timeout_seconds: 5
  retry_times: 2
runtime:
  scan_interval_seconds: 60
  max_images_per_message: 8
  state_file: ./var/push-state.json
  dry_run: true
backend:
  database_url: sqlite:///./var/app.db
  secret_key: test-secret
  host: 127.0.0.1
  port: 5000
  bootstrap_admin_username: admin
  bootstrap_admin_password: password
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.data_source is not None
    assert config.data_source.kind == "sqlserver"
    assert config.data_source.config_path == Path("./datasource.local.yaml")


def test_validate_prototype_config_allows_sqlserver_datasource_without_csv(
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
data_source:
  kind: sqlserver
  config_path: ./datasource.local.yaml
image_service:
  host: 127.0.0.1
  port: 8123
  image_dir: ./images
wecom:
  webhook_url: https://example.com
  timeout_seconds: 5
  retry_times: 2
runtime:
  scan_interval_seconds: 60
  max_images_per_message: 8
  state_file: ./var/push-state.json
  dry_run: true
backend:
  database_url: sqlite:///./var/app.db
  secret_key: test-secret
  host: 127.0.0.1
  port: 5000
  bootstrap_admin_username: admin
  bootstrap_admin_password: password
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_file)

    validate_prototype_config("run-once", config)


def test_load_data_source_config_reads_sqlserver_query_and_field_mapping(
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "datasource.yaml"
    config_file.write_text(
        """
sqlserver:
  connection_string: Driver={ODBC Driver 17 for SQL Server};Server=localhost;Database=wecom_sales_test;Trusted_Connection=yes;TrustServerCertificate=yes;
  query: |
    SELECT
      order_no,
      sold_at,
      store_name,
      total_amount,
      barcode,
      style_no,
      unit_price,
      brand,
      category,
      image_url
    FROM dbo.sales_lines
  field_mapping:
    order_no: order_no
    sold_at: sold_at
    store_name: store_name
    total_amount: total_amount
    barcode: barcode
    style_no: style_no
    unit_price: unit_price
    brand: brand
    category: category
    image_url: image_url
""".strip(),
        encoding="utf-8",
    )

    data_source_config = load_data_source_config(config_file)

    assert "FROM dbo.sales_lines" in data_source_config.sqlserver.query
    assert data_source_config.sqlserver.field_mapping["order_no"] == "order_no"
    assert data_source_config.sqlserver.database_columns["order_no"] == "order_no"
    assert data_source_config.sqlserver.connection_string.startswith(
        "Driver={ODBC Driver 17 for SQL Server}"
    )
