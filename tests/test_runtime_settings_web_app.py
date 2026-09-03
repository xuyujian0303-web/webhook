from wecom_sales_webhook_bot.rule_models import GlobalSetting
from wecom_sales_webhook_bot.web_app import create_app


def _build_app():
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE_URL": "sqlite:///:memory:",
            "BOOTSTRAP_ADMIN": {"username": "admin", "password": "pass123"},
        }
    )


def _login(client) -> None:
    client.post("/login", data={"username": "admin", "password": "pass123"})


def test_runtime_settings_page_loads_after_login() -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)

    response = client.get("/runtime-settings")

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'name="scan_interval_seconds"' in page
    assert 'name="max_images_per_message"' in page
    assert 'name="push_interval_seconds"' in page
    assert 'value="1200"' in page
    assert 'value="8"' in page
    assert 'value="10"' in page


def test_runtime_settings_page_persists_scan_interval_max_images_and_push_interval() -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)

    response = client.post(
        "/runtime-settings",
        data={
            "scan_interval_seconds": "300",
            "max_images_per_message": "5",
            "push_interval_seconds": "6",
        },
        follow_redirects=True,
    )

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'value="300"' in page
    assert 'value="5"' in page
    assert 'value="6"' in page

    session_factory = app.config["SESSION_FACTORY"]
    with session_factory() as session:
        row = session.query(GlobalSetting).filter_by(setting_key="runtime_settings").one()
        assert '"scan_interval_seconds": 300' in row.setting_json
        assert '"max_images_per_message": 5' in row.setting_json
        assert '"push_interval_seconds": 6' in row.setting_json
