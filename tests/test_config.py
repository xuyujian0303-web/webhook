from pathlib import Path

from wecom_sales_webhook_bot.config import load_config


def test_load_config_reads_backend_database_auth_and_api_settings(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
wecom:
  webhook_url: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test
  timeout_seconds: 5
  retry_times: 2
runtime:
  scan_interval_seconds: 1200
  max_images_per_message: 8
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
    assert config.api.sales_base_url == "https://internal.example.com"
    assert config.api.sales_path == "/sales/query"
    assert config.api.timeout_seconds == 10
