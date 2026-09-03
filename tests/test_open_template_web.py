from wecom_sales_webhook_bot.web_app import create_app


def _app():
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test",
        "DATABASE_URL": "sqlite:///:memory:",
        "BOOTSTRAP_ADMIN": {"username": "admin", "password": "pass123"},
    })


def _login(client) -> None:
    client.post("/login", data={"username": "admin", "password": "pass123"})


def test_format_page_has_only_reference_template_and_preview_sections() -> None:
    app = _app()
    client = app.test_client()
    _login(client)

    page = client.get("/format-settings").get_data(as_text=True)

    assert "变量参考" in page
    assert "自定义模板" in page
    assert "实时预览" in page
    assert "另存为" not in page
    assert "模板列表" not in page


def test_format_page_saves_one_template_and_renders_preview() -> None:
    app = _app()
    client = app.test_client()
    _login(client)

    page = client.post(
        "/format-settings",
        data={"template_body": "{{ order.salesperson }}"},
    ).get_data(as_text=True)

    assert "模板已保存" in page
    assert "张三" in page
