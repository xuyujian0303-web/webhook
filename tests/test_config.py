from pathlib import Path

import pytest

from wecom_sales_webhook_bot.config import load_config


def test_load_config_reads_backend_database_auth_and_api_settings(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
wecom:
  webhook_url: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_WEBHOOK_KEY
  timeout_seconds: 5
  retry_times: 2
runtime:
  scan_interval_seconds: 1200
  max_images_per_message: 8
  push_interval_seconds: 10
  dry_run: false
backend:
  database_url: sqlite:///./var/app.db
  secret_key: test-secret
  host: 127.0.0.1
  port: 5000
  bootstrap_admin_username: admin
  bootstrap_admin_password: admin123
api:
  sales_base_url: https://internal.example.com
  sales_token: test-token
  sales_path: /sales/query
  timeout_seconds: 10
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.backend.database_url == "sqlite:///./var/app.db"
    assert config.backend.secret_key == "test-secret"
    assert config.backend.bootstrap_admin_username == "admin"
    assert config.runtime.push_interval_seconds == 10
    assert config.api.sales_base_url == "https://internal.example.com"
    assert config.api.sales_path == "/sales/query"
    assert config.api.timeout_seconds == 10


def test_load_config_reads_legacy_prototype_config(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
csv:
  path: ./sales.csv
  encoding: utf-8
  field_mapping:
    order_no: order_no
image_service:
  host: 127.0.0.1
  port: 8000
  image_dir: ./images
wecom:
  webhook_url: https://example.com
  timeout_seconds: 3
  retry_times: 1
rules:
  amount_threshold: 100
  style_whitelist: [A,B]
runtime:
  scan_interval_seconds: 30
  max_images_per_message: 2
  push_interval_seconds: 10
  state_file: ./state.json
  dry_run: true
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_file)
    assert config.csv.path == Path("./sales.csv")
    assert config.image_service.port == 8000
    assert config.rules.amount_threshold == 100.0
    assert config.runtime.push_interval_seconds == 10
    assert config.runtime.state_file == Path("./state.json")
    assert config.image_service.image_map_csv is None


def test_load_config_defaults_push_interval_seconds_when_missing(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
wecom:
  webhook_url: https://example.com
  timeout_seconds: 3
  retry_times: 1
runtime:
  scan_interval_seconds: 30
  max_images_per_message: 2
  state_file: ./state.json
  dry_run: false
csv:
  path: ./sales.csv
  encoding: utf-8
  field_mapping:
    order_no: order_no
image_service:
  host: 127.0.0.1
  port: 8000
  image_dir: ./images
rules:
  amount_threshold: 100
  style_whitelist: []
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.runtime.push_interval_seconds == 10


def test_load_config_reads_optional_image_map_csv(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
wecom:
  webhook_url: https://example.com
  timeout_seconds: 3
  retry_times: 1
runtime:
  scan_interval_seconds: 30
  max_images_per_message: 2
  push_interval_seconds: 10
  state_file: ./state.json
  dry_run: false
csv:
  path: ./sales.csv
  encoding: utf-8
  field_mapping:
    order_no: order_no
image_service:
  host: 127.0.0.1
  port: 8000
  image_dir: ./images
  image_map_csv: ./images.csv
rules:
  amount_threshold: 100
  style_whitelist: []
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.image_service.image_map_csv == Path("./images.csv")


def test_empty_section_raises_value_error(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
csv: {}
wecom:
  webhook_url: https://example.com
  timeout_seconds: 3
  retry_times: 1
runtime:
  scan_interval_seconds: 30
  max_images_per_message: 2
  state_file: ./state.json
  dry_run: false
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as exc_info:
        load_config(config_file)
    assert "csv" in str(exc_info.value)
