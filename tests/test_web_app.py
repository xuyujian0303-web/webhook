from pathlib import Path

from werkzeug.datastructures import MultiDict

from wecom_sales_webhook_bot.cli import build_parser
from wecom_sales_webhook_bot.message_template_service import (
    activate_message_template,
    load_or_initialize_message_template_store,
    save_message_template,
)
from wecom_sales_webhook_bot.rule_models import (
    GlobalSetting,
    JobRun,
    PushRecord,
    RuleCondition,
    RuleGroup,
)
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


def _create_rule(app, *, is_enabled: bool = True) -> int:
    session_factory = app.config["SESSION_FACTORY"]
    with session_factory() as session:
        rule = RuleGroup(
            name="高金额测试规则",
            is_enabled=is_enabled,
            match_mode="all",
            updated_by="admin",
        )
        session.add(rule)
        session.flush()
        session.add(
            RuleCondition(
                rule_group_id=rule.id,
                field_name="total_amount",
                operator="gte",
                value_json="10000",
            )
        )
        session.commit()
        return rule.id


def test_login_page_shows_error_message_after_failed_login() -> None:
    app = _build_app()
    client = app.test_client()

    response = client.post(
        "/login",
        data={"username": "admin", "password": "wrong-pass"},
        follow_redirects=True,
    )

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "用户名或密码错误" in page
    assert "企业微信销售单推送后台" in page


def test_root_path_redirects_to_login_page() -> None:
    app = _build_app()
    client = app.test_client()

    response = client.get("/", follow_redirects=True)

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "企业微信销售单推送后台" in page
    assert "登录" in page


def test_rule_save_persists_match_mode_and_shows_condition_summary() -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)

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
    assert "全部满足" in page
    assert "金额不低于 10000" in page
    assert "门店: G621, G609" in page
    assert "时段: 10:00-18:00" in page


def test_rules_page_shows_disable_and_delete_actions_for_enabled_rule() -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)
    rule_id = _create_rule(app, is_enabled=True)

    response = client.get("/rules")

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "启用中" in page
    assert f"/rules/{rule_id}/disable" in page
    assert f"/rules/{rule_id}/delete" in page
    assert "停用" in page
    assert "删除" in page


def test_disable_rule_updates_status_and_shows_enable_action() -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)
    rule_id = _create_rule(app, is_enabled=True)

    response = client.post(f"/rules/{rule_id}/disable", follow_redirects=True)

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "已停用" in page
    assert "恢复" in page
    assert f"/rules/{rule_id}/enable" in page
    assert f"/rules/{rule_id}/disable" not in page


def test_enable_rule_restores_enabled_status() -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)
    rule_id = _create_rule(app, is_enabled=False)

    response = client.post(f"/rules/{rule_id}/enable", follow_redirects=True)

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "启用中" in page
    assert "停用" in page
    assert f"/rules/{rule_id}/disable" in page
    assert f"/rules/{rule_id}/enable" not in page


def test_delete_rule_removes_group_and_conditions_from_page_and_database() -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)
    rule_id = _create_rule(app, is_enabled=True)

    response = client.post(f"/rules/{rule_id}/delete", follow_redirects=True)

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "高金额测试规则" not in page
    assert f"/rules/{rule_id}/delete" not in page

    session_factory = app.config["SESSION_FACTORY"]
    with session_factory() as session:
        assert session.get(RuleGroup, rule_id) is None
        remaining_conditions = (
            session.query(RuleCondition)
            .filter_by(rule_group_id=rule_id)
            .all()
        )
        assert remaining_conditions == []


def test_template_workspace_shows_open_template_editor_after_login() -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)

    page = client.get("/format-settings").get_data(as_text=True)

    assert "消息模板管理" in page
    assert "变量参考" in page
    assert "自定义模板" in page
    assert "实时预览" in page
    assert "另存为" not in page
    assert "模板列表" not in page
    assert "{{ order.order_no }}" in page
    assert "item.image_url" in page


def test_template_workspace_saves_one_template_and_renders_preview() -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)

    response = client.post(
        "/format-settings",
        data={"template_body": "# 新模板\n{{ order.salesperson }}\n{% for item in order.items %}{{ item.style_no }}{% endfor %}"},
        follow_redirects=True,
    )

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "模板已保存" in page
    assert "张三" in page
    with app.config["SESSION_FACTORY"]() as session:
        row = session.query(GlobalSetting).filter_by(setting_key="message_template").one()
        assert "# 新模板" in row.setting_json

def test_rules_page_shows_empty_state_and_manual_test_navigation() -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)

    response = client.get("/rules")

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "还没有规则" in page
    assert "手动测试" in page
    assert "/manual-test" in page


def test_manual_test_page_loads_after_login() -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)

    response = client.get("/manual-test")

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "CSV + 本地图片 URL" in page
    assert "此页面将用于手动验证流程" in page


def test_manual_test_page_runs_csv_preview_and_shows_message(tmp_path: Path) -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)

    csv_file = tmp_path / "sales.csv"
    csv_file.write_text(
        "\n".join(
            [
                "销售单号,销售日期,销售门店,销售单总额,商品条码,产品款号,产品单价",
                "SO-200,2026/4/20 10:50 AM,G609,14500,GPA22056EINY0B6380001,PA22056ENY0,14500",
            ]
        ),
        encoding="utf-8",
    )
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    (image_dir / "PA22056ENY0.png").write_bytes(b"fake-image")

    response = client.post(
        "/manual-test",
        data={
            "csv_path": str(csv_file),
            "csv_encoding": "utf-8",
            "field_order_no": "销售单号",
            "field_sold_at": "销售日期",
            "field_store_name": "销售门店",
            "field_total_amount": "销售单总额",
            "field_barcode": "商品条码",
            "field_style_no": "产品款号",
            "field_unit_price": "产品单价",
            "image_dir": str(image_dir),
            "image_base_url": "http://127.0.0.1:8123",
            "amount_threshold": "1000",
            "style_whitelist": "",
            "max_images": "8",
        },
    )

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "本次手动测试已完成" in page
    assert "命中订单 1" in page
    assert "SO-200" in page
    assert "PA22056ENY0.png" in page


def test_manual_test_page_uses_saved_message_template(tmp_path: Path) -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)

    session_factory = app.config["SESSION_FACTORY"]
    with session_factory() as session:
        session.add(
            GlobalSetting(
                setting_key="message_template",
                setting_json='{"preset_key":"compact","template_body":"# 手测模板\\n{{ items_markdown }}","template_name":"手测模板"}',
            )
        )
        session.commit()

    csv_file = tmp_path / "sales.csv"
    csv_file.write_text(
        "\n".join(
            [
                "销售单号,销售日期,销售门店,销售单总额,商品条码,产品款号,产品单价",
                "SO-201,2026/4/20 10:50 AM,G609,14500,GPA22056EINY0B6380001,PA22056ENY0,14500",
            ]
        ),
        encoding="utf-8",
    )
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    (image_dir / "PA22056ENY0.png").write_bytes(b"fake-image")

    response = client.post(
        "/manual-test",
        data={
            "csv_path": str(csv_file),
            "csv_encoding": "utf-8",
            "field_order_no": "销售单号",
            "field_sold_at": "销售日期",
            "field_store_name": "销售门店",
            "field_total_amount": "销售单总额",
            "field_barcode": "商品条码",
            "field_style_no": "产品款号",
            "field_unit_price": "产品单价",
            "image_dir": str(image_dir),
            "image_base_url": "http://127.0.0.1:8123",
            "amount_threshold": "1000",
            "style_whitelist": "",
            "max_images": "8",
        },
    )

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "# 手测模板" in page


def test_manual_test_page_validates_required_inputs() -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)

    response = client.post(
        "/manual-test",
        data={
            "csv_path": "",
            "csv_encoding": "",
            "field_order_no": "",
            "field_sold_at": "",
            "field_store_name": "",
            "field_total_amount": "",
            "field_barcode": "",
            "field_style_no": "",
            "field_unit_price": "",
            "image_dir": "",
            "image_base_url": "",
            "amount_threshold": "",
            "style_whitelist": "",
            "max_images": "",
        },
    )

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "请填写 CSV 文件路径" in page
    assert "请填写图片目录" in page
    assert "请填写图片访问前缀" in page
    assert "请填写金额阈值" in page
    assert "请填写最大图片数" in page


def test_rule_create_page_renders_validation_errors() -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)

    response = client.post(
        "/rules/new",
        data={
            "name": "",
            "match_mode": "invalid",
            "amount_threshold": "",
            "style_list": "",
            "store_list": "",
            "time_start": "10:00",
            "time_end": "",
            "brand_list": "",
            "category_list": "",
        },
    )

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "请填写规则名称" in page
    assert "匹配方式不合法" in page
    assert "时间段必须同时填写开始和结束时间" in page


def test_records_and_status_pages_render_empty_and_populated_states() -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)

    empty_records = client.get("/records")
    empty_status = client.get("/status")
    assert "暂无推送记录" in empty_records.get_data(as_text=True)
    assert "尚未执行扫描任务" in empty_status.get_data(as_text=True)

    session_factory = app.config["SESSION_FACTORY"]
    with session_factory() as session:
        session.add(
            PushRecord(
                order_no="SO-100",
                store_name="G621",
                total_amount=18888,
                rule_name="高金额门店规则",
                status="success",
                error_message=None,
            )
        )
        session.add(
            JobRun(
                window_start="2026-05-31T10:00:00",
                window_end="2026-05-31T10:20:00",
                status="success",
                success_count=1,
                failed_count=0,
                error_summary=None,
            )
        )
        session.commit()

    records = client.get("/records")
    status = client.get("/status")
    assert "SO-100" in records.get_data(as_text=True)
    assert "推送成功" in records.get_data(as_text=True)
    assert "最近一次扫描" in status.get_data(as_text=True)
    assert "成功 1" in status.get_data(as_text=True)


def test_cli_exposes_run_server_command() -> None:
    parser = build_parser()
    args = parser.parse_args(["run-server", "--config", "config.yaml"])
    assert args.command == "run-server"
