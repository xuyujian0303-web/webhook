from wecom_sales_webhook_bot.cli import build_parser
from wecom_sales_webhook_bot.web_app import create_app


def test_rule_save_persists_match_mode_and_supported_conditions() -> None:
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE_URL": "sqlite:///:memory:",
            "BOOTSTRAP_ADMIN": {"username": "admin", "password": "pass123"},
        }
    )
    client = app.test_client()
    client.post("/login", data={"username": "admin", "password": "pass123"})

    response = client.post(
        "/rules/new",
        data={
            "name": "高金额门店规则",
            "is_enabled": "on",
            "match_mode": "all",
            "amount_threshold": "10000",
            "style_list": "PA17047BNY0,PA15161ENY0",
            "store_list": "G621,G609",
            "time_start": "10:00",
            "time_end": "18:00",
            "brand_list": "Brand-A,Brand-B",
            "category_list": "外套,连衣裙",
        },
        follow_redirects=True,
    )

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "高金额门店规则" in page
    assert "all" in page


def test_cli_exposes_run_server_command() -> None:
    parser = build_parser()
    args = parser.parse_args(["run-server", "--config", "config.yaml"])
    assert args.command == "run-server"


def test_status_page_loads_after_login() -> None:
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE_URL": "sqlite:///:memory:",
            "BOOTSTRAP_ADMIN": {"username": "admin", "password": "pass123"},
        }
    )
    client = app.test_client()
    client.post("/login", data={"username": "admin", "password": "pass123"})

    response = client.get("/status")

    assert response.status_code == 200
    assert "最近一次扫描" in response.get_data(as_text=True)
