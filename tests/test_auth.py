from wecom_sales_webhook_bot.web_app import create_app


def test_login_redirects_to_rules_after_success() -> None:
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE_URL": "sqlite:///:memory:",
            "BOOTSTRAP_ADMIN": {"username": "admin", "password": "pass123"},
        }
    )
    client = app.test_client()

    response = client.post(
        "/login",
        data={"username": "admin", "password": "pass123"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/rules")
