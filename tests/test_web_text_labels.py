from wecom_sales_webhook_bot.web_app import (
    _manual_test_defaults,
    _match_mode_label,
    _run_status_label,
    create_app,
)


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


def test_web_pages_render_readable_chinese_labels() -> None:
    app = _build_app()
    client = app.test_client()

    login_page = client.get("/login").get_data(as_text=True)
    assert "用户名" in login_page
    assert "登录后台" in login_page

    _login(client)

    rules_page = client.get("/rules").get_data(as_text=True)
    assert "规则管理" in rules_page
    assert "还没有规则" in rules_page
    assert "新建规则" in rules_page
    assert "消息模板" in rules_page
    assert "运行配置" in rules_page
    assert "手动测试" in rules_page
    assert "推送记录" in rules_page
    assert "系统状态" in rules_page

    template_page = client.get("/format-settings").get_data(as_text=True)
    assert "消息模板管理" in template_page
    assert "变量参考" in template_page
    assert "自定义模板" in template_page
    assert "实时预览" in template_page

    manual_test_page = client.get("/manual-test").get_data(as_text=True)
    assert "手动测试" in manual_test_page
    assert "CSV + 本地图片 URL" in manual_test_page
    assert "销售单总额字段" in manual_test_page
    assert "商品条码字段" in manual_test_page
    assert "产品款号字段" in manual_test_page
    assert "产品单价字段" in manual_test_page

    records_page = client.get("/records").get_data(as_text=True)
    assert "推送记录" in records_page
    assert "暂无推送记录" in records_page

    status_page = client.get("/status").get_data(as_text=True)
    assert "系统状态" in status_page
    assert "尚未执行扫描任务" in status_page


def test_runtime_label_helpers_render_readable_chinese() -> None:
    assert _match_mode_label("all") == "全部满足"
    assert _match_mode_label("any") == "任一满足"
    assert _run_status_label("success") == "执行成功"
    assert _run_status_label("failed") == "执行失败"

    defaults = _manual_test_defaults()
    assert defaults["field_total_amount"] == "销售单总额"
    assert defaults["field_barcode"] == "商品条码"
    assert defaults["field_style_no"] == "产品款号"
    assert defaults["field_unit_price"] == "产品单价"
