from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime

from flask import Flask, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, login_required, login_user

from wecom_sales_webhook_bot.auth import hash_password, verify_password
from wecom_sales_webhook_bot.config import CsvConfig
from wecom_sales_webhook_bot.csv_source import CsvSalesDataSource
from wecom_sales_webhook_bot.db import create_session_factory, initialize_database
from wecom_sales_webhook_bot.filters import SalesFilter
from wecom_sales_webhook_bot.image_service import LocalImageUrlProvider
from wecom_sales_webhook_bot.message_template_defaults import PRESET_TEMPLATES
from wecom_sales_webhook_bot.message_template_schema import REFERENCE_VARIABLES
from wecom_sales_webhook_bot.message_template_engine import (
    TemplateRenderError,
    render_message_template,
    validate_message_template,
)
from wecom_sales_webhook_bot.message_template_service import (
    DEFAULT_TEMPLATE_NAME,
    TemplateDeleteError,
    activate_message_template,
    build_preview_template_context,
    delete_message_template,
    load_or_initialize_message_template,
    load_or_initialize_message_template_store,
    save_message_template,
)
from wecom_sales_webhook_bot.orchestrator import run_once
from wecom_sales_webhook_bot.runtime_settings import (
    DEFAULT_RUNTIME_CONTROLS,
    RuntimeControls,
    load_or_initialize_runtime_controls,
    save_runtime_controls,
)
from wecom_sales_webhook_bot.rule_models import (
    JobRun,
    PushRecord,
    RuleCondition,
    RuleGroup,
    UserAccount,
)


class LoginUser(UserMixin):
    def __init__(self, user_id: int) -> None:
        self.id = str(user_id)


class _PreviewWebhookClient:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send_markdown_v2(self, content: str) -> None:
        self.messages.append(content)


def _page_context(*, active_nav: str, page_title: str, **extra: object) -> dict[str, object]:
    nav_items = [
        {"endpoint": "rules_page", "label": "瑙勫垯绠＄悊", "key": "rules"},
        {"endpoint": "rule_new_page", "label": "鏂板缓瑙勫垯", "key": "rule_new"},
        {"endpoint": "format_settings_page", "label": "娑堟伅妯℃澘", "key": "format_settings"},
        {"endpoint": "runtime_settings_page", "label": "\u8fd0\u884c\u914d\u7f6e", "key": "runtime_settings"},
        {"endpoint": "manual_test_page", "label": "鎵嬪姩娴嬭瘯", "key": "manual_test"},
        {"endpoint": "records_page", "label": "推送记录", "key": "records"},
        {"endpoint": "status_page", "label": "系统状态", "key": "status"},
    ]
    context = {
        "app_name": "企业微信销售单推送后台",
        "page_title": page_title,
        "active_nav": active_nav,
        "nav_items": nav_items,
    }
    context.update(extra)
    return context


def _split_csv_text(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _match_mode_label(match_mode: str) -> str:
    return {"all": "鍏ㄩ儴婊¤冻", "any": "浠讳竴婊¤冻"}.get(match_mode, match_mode)


def _rule_status_label(is_enabled: bool) -> str:
    return "启用中" if is_enabled else "已停用"


def _push_status_label(status: str) -> str:
    return {"success": "推送成功", "failed": "推送失败"}.get(status, status)


def _run_status_label(status: str) -> str:
    return {"success": "鎵ц鎴愬姛", "failed": "鎵ц澶辫触"}.get(status, status)


def _summarize_conditions(conditions: list[RuleCondition]) -> list[str]:
    summary: list[str] = []
    for condition in conditions:
        if condition.field_name == "total_amount" and condition.operator == "gte":
            summary.append(f"金额不低于 {condition.value_json}")
        elif condition.field_name == "style_no" and condition.operator == "in":
            summary.append(f"\u6b3e\u53f7: {', '.join(_split_csv_text(condition.value_json))}")
        elif condition.field_name == "store_name" and condition.operator == "in":
            summary.append(f"\u95e8\u5e97: {', '.join(_split_csv_text(condition.value_json))}")
        elif condition.field_name == "sold_at" and condition.operator == "between_time":
            start_time, end_time = condition.value_json.split(",", maxsplit=1)
            summary.append(f"时段: {start_time}-{end_time}")
        elif condition.field_name == "brand" and condition.operator == "in":
            summary.append(f"\u54c1\u724c: {', '.join(_split_csv_text(condition.value_json))}")
        elif condition.field_name == "category" and condition.operator == "in":
            summary.append(f"\u54c1\u7c7b: {', '.join(_split_csv_text(condition.value_json))}")
    return summary


def _validate_rule_form(form) -> list[str]:
    errors: list[str] = []
    if not form.get("name", "").strip():
        errors.append("请填写规则名称")
    if form.get("match_mode") not in {"all", "any"}:
        errors.append("匹配方式不合法")
    start_text = form.get("order_date_start", "").strip()
    end_text = form.get("order_date_end", "").strip()
    try:
        start_date = datetime.strptime(start_text, "%Y-%m-%d").date() if start_text else None
        end_date = datetime.strptime(end_text, "%Y-%m-%d").date() if end_text else None
        if start_date and end_date and end_date < start_date:
            errors.append("结束日期不能早于开始日期")
    except ValueError:
        errors.append("订单日期必须使用 YYYY-MM-DD 格式")
    return errors


def _manual_test_defaults() -> dict[str, str]:
    return {
        "csv_path": "",
        "csv_encoding": "utf-8",
        "field_order_no": "销售单号",
        "field_sold_at": "销售日期",
        "field_store_name": "销售门店",
        "field_total_amount": "閿€鍞崟鎬婚",
        "field_barcode": "鍟嗗搧鏉＄爜",
        "field_style_no": "浜у搧娆惧彿",
        "field_unit_price": "浜у搧鍗曚环",
        "image_dir": "",
        "image_base_url": "http://127.0.0.1:8123",
        "amount_threshold": "1000",
        "style_whitelist": "",
        "max_images": "8",
    }


def _manual_test_form_data(form) -> dict[str, str]:
    defaults = _manual_test_defaults()
    return {key: str(form.get(key, defaults[key])) for key in defaults}


def _template_preset_options() -> list[dict[str, str]]:
    return [
        {"key": key, "label": value["label"]}
        for key, value in PRESET_TEMPLATES.items()
    ]


def _template_form_data(payload: dict | None = None) -> dict[str, str]:
    source = payload or {}
    preset_key = str(source.get("preset_key", "standard"))
    if preset_key not in PRESET_TEMPLATES:
        preset_key = "standard"
    template_id = str(source.get("template_id", source.get("id", "")))
    return {
        "template_id": template_id,
        "selected_template_id": str(
            source.get("selected_template_id", template_id)
        ),
        "preset_key": preset_key,
        "template_name": str(
            source.get("template_name", source.get("name", DEFAULT_TEMPLATE_NAME))
        ),
        "template_body": str(
            source.get("template_body", PRESET_TEMPLATES[preset_key]["body"])
        ),
    }


def _template_payload_from_form(form) -> dict[str, str]:
    preset_key = str(form.get("preset_key", "standard")).strip() or "standard"
    if preset_key not in PRESET_TEMPLATES:
        preset_key = "standard"
    return {
        "template_id": str(form.get("template_id", "")).strip(),
        "selected_template_id": str(form.get("selected_template_id", "")).strip(),
        "preset_key": preset_key,
        "template_name": str(form.get("template_name", "")).strip()
        or DEFAULT_TEMPLATE_NAME,
        "template_body": str(form.get("template_body", "")),
    }


def _template_list_options(store: dict) -> list[dict[str, str]]:
    active_id = store["active_template_id"]
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "is_active": item["id"] == active_id,
        }
        for item in store["templates"]
    ]


def _find_template(store: dict, template_id: str) -> dict | None:
    return next((item for item in store["templates"] if item["id"] == template_id), None)


def _render_template_preview(template_body: str) -> str:
    return render_message_template(
        template_body,
        build_preview_template_context(),
    ).text


def _template_workspace_context(
    *,
    store: dict,
    payload: dict[str, str],
    save_message: str | None,
    errors: list[str],
) -> dict[str, object]:
    preview = None
    display_errors = list(errors)
    if not display_errors:
        try:
            preview = _render_template_preview(payload["template_body"])
        except TemplateRenderError as exc:
            display_errors.append(f"妯℃澘棰勮澶辫触: {exc}")
    return _page_context(
        active_nav="format_settings",
        page_title="娑堟伅妯℃澘绠＄悊",
        template_form=payload,
        saved_templates=[],
        active_template_id=store.get("active_template_id", ""),
        preset_options=[],
        save_message=save_message,
        errors=display_errors,
        preview_text=preview,
        reference_variables=REFERENCE_VARIABLES,
    )

def _runtime_controls_defaults(app: Flask) -> RuntimeControls:
    defaults = app.config.get("RUNTIME_CONTROL_DEFAULTS", DEFAULT_RUNTIME_CONTROLS)
    if isinstance(defaults, RuntimeControls):
        return defaults
    return RuntimeControls(
        scan_interval_seconds=int(defaults.get("scan_interval_seconds", DEFAULT_RUNTIME_CONTROLS.scan_interval_seconds)),
        max_images_per_message=int(defaults.get("max_images_per_message", DEFAULT_RUNTIME_CONTROLS.max_images_per_message)),
        push_interval_seconds=int(defaults.get("push_interval_seconds", DEFAULT_RUNTIME_CONTROLS.push_interval_seconds)),
        push_window_start=str(defaults.get("push_window_start", DEFAULT_RUNTIME_CONTROLS.push_window_start)),
        push_window_end=str(defaults.get("push_window_end", DEFAULT_RUNTIME_CONTROLS.push_window_end)),
    )

def _runtime_controls_form_data(controls: RuntimeControls) -> dict[str, str]:
    return {
        "scan_interval_seconds": str(controls.scan_interval_seconds),
        "max_images_per_message": str(controls.max_images_per_message),
        "push_interval_seconds": str(controls.push_interval_seconds),
        "push_window_start": controls.push_window_start,
        "push_window_end": controls.push_window_end,
    }


def _runtime_controls_page_context(
    *,
    controls: RuntimeControls,
    save_message: str | None,
    errors: list[str],
) -> dict[str, object]:
    return _page_context(
        active_nav="runtime_settings",
        page_title="\u8fd0\u884c\u914d\u7f6e",
        form_data=_runtime_controls_form_data(controls),
        save_message=save_message,
        errors=errors,
    )

def _validate_manual_test_form(form) -> list[str]:
    errors: list[str] = []
    csv_path = form.get("csv_path", "").strip()
    image_dir = form.get("image_dir", "").strip()
    if not csv_path:
        errors.append("璇峰～鍐?CSV 鏂囦欢璺緞")
    elif not Path(csv_path).exists():
        errors.append("CSV 文件不存在")
    if not form.get("csv_encoding", "").strip():
        errors.append("璇峰～鍐?CSV 缂栫爜")
    if not form.get("field_order_no", "").strip():
        errors.append("璇峰～鍐欓攢鍞崟鍙峰瓧娈靛悕")
    if not form.get("field_sold_at", "").strip():
        errors.append("璇峰～鍐欓攢鍞棩鏈熷瓧娈靛悕")
    if not form.get("field_store_name", "").strip():
        errors.append("璇峰～鍐欓攢鍞棬搴楀瓧娈靛悕")
    if not form.get("field_total_amount", "").strip():
        errors.append("请填写销售单总额字段名")
    if not form.get("field_barcode", "").strip():
        errors.append("璇峰～鍐欏晢鍝佹潯鐮佸瓧娈靛悕")
    if not form.get("field_style_no", "").strip():
        errors.append("璇峰～鍐欎骇鍝佹鍙峰瓧娈靛悕")
    if not form.get("field_unit_price", "").strip():
        errors.append("璇峰～鍐欎骇鍝佸崟浠峰瓧娈靛悕")
    if not image_dir:
        errors.append("请填写图片目录")
    elif not Path(image_dir).exists():
        errors.append("图片目录不存在")
    if not form.get("image_base_url", "").strip():
        errors.append("璇峰～鍐欏浘鐗囪闂墠缂€")
    if not form.get("amount_threshold", "").strip():
        errors.append("请填写金额阈值")
    else:
        try:
            float(form["amount_threshold"])
        except ValueError:
            errors.append("閲戦闃堝€煎繀椤绘槸鏁板瓧")
    if not form.get("max_images", "").strip():
        errors.append("璇峰～鍐欐渶澶у浘鐗囨暟")
    else:
        try:
            max_images = int(form["max_images"])
            if max_images < 0:
                raise ValueError
        except ValueError:
            errors.append("最大图片数必须是大于等于 0 的整数")
    return errors


def _run_manual_test(
    form,
    project_root: Path,
    template_body: str | None = None,
) -> dict[str, object]:
    csv_path = Path(form["csv_path"])
    if not csv_path.is_absolute():
        csv_path = (project_root / csv_path).resolve()
    image_dir = Path(form["image_dir"])
    if not image_dir.is_absolute():
        image_dir = (project_root / image_dir).resolve()

    csv_config = CsvConfig(
        path=csv_path,
        encoding=form["csv_encoding"].strip(),
        field_mapping={
            "order_no": form["field_order_no"].strip(),
            "sold_at": form["field_sold_at"].strip(),
            "store_name": form["field_store_name"].strip(),
            "total_amount": form["field_total_amount"].strip(),
            "barcode": form["field_barcode"].strip(),
            "style_no": form["field_style_no"].strip(),
            "unit_price": form["field_unit_price"].strip(),
        },
    )
    data_source = CsvSalesDataSource(csv_config, base_dir=project_root)
    sales_filter = SalesFilter(
        amount_threshold=float(form["amount_threshold"]),
        style_whitelist=set(_split_csv_text(form.get("style_whitelist", ""))),
    )
    image_provider = LocalImageUrlProvider(
        image_dir=image_dir,
        base_url=form["image_base_url"].strip(),
    )
    webhook_client = _PreviewWebhookClient()
    with TemporaryDirectory() as temp_dir:
        state_file = Path(temp_dir) / "manual-test-state.json"
        sent_orders = run_once(
            data_source=data_source,
            sales_filter=sales_filter,
            image_provider=image_provider,
            state_file=state_file,
            webhook_client=webhook_client,
            max_images=int(form["max_images"]),
            dry_run=False,
            template_body=template_body,
        )
    return {
        "completed": True,
        "sent_count": len(sent_orders),
        "sent_orders": sent_orders,
        "messages": webhook_client.messages,
    }


def create_app(config: dict) -> Flask:
    app = Flask(__name__)
    app.config.update(config)
    app.config.setdefault("RUNTIME_CONTROL_DEFAULTS", DEFAULT_RUNTIME_CONTROLS)
    session_factory = create_session_factory(app.config["DATABASE_URL"])
    app.config["SESSION_FACTORY"] = session_factory
    initialize_database(session_factory)

    login_manager = LoginManager()
    login_manager.login_view = "login_page"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str):
        with session_factory() as session:
            user = session.get(UserAccount, int(user_id))
            if user is None or not user.is_active:
                return None
            return LoginUser(user.id)

    with session_factory() as session:
        if session.query(UserAccount).count() == 0:
            seed = app.config["BOOTSTRAP_ADMIN"]
            session.add(
                UserAccount(
                    username=seed["username"],
                    password_hash=hash_password(seed["password"]),
                    role="admin",
                    is_active=True,
                )
            )
            session.commit()

    @app.get("/")
    def home_page():
        return redirect(url_for("login_page"))

    @app.get("/login")
    def login_page():
        return render_template(
            "login.html",
            **_page_context(active_nav="", page_title="鐧诲綍", error_message=None),
        )

    @app.post("/login")
    def login_submit():
        with session_factory() as session:
            user = (
                session.query(UserAccount)
                .filter_by(username=request.form["username"])
                .one_or_none()
            )
            if user is not None and verify_password(
                user.password_hash, request.form["password"]
            ):
                login_user(LoginUser(user.id))
                return redirect(url_for("rules_page"))
        return render_template(
            "login.html",
            **_page_context(
                active_nav="",
                page_title="鐧诲綍",
                error_message="鐢ㄦ埛鍚嶆垨瀵嗙爜閿欒",
            ),
        )

    @app.get("/rules")
    @login_required
    def rules_page():
        with session_factory() as session:
            rules = session.query(RuleGroup).order_by(RuleGroup.updated_at.desc()).all()
            conditions = session.query(RuleCondition).all()
        grouped: dict[int, list[RuleCondition]] = defaultdict(list)
        for condition in conditions:
            grouped[condition.rule_group_id].append(condition)
        rule_cards = [
            {
                "id": rule.id,
                "name": rule.name,
                "is_enabled": rule.is_enabled,
                "status_label": _rule_status_label(rule.is_enabled),
                "match_mode_label": _match_mode_label(rule.match_mode),
                "updated_by": rule.updated_by,
                "updated_at": rule.updated_at.strftime("%Y-%m-%d %H:%M"),
                "condition_summary": _summarize_conditions(grouped[rule.id]),
            }
            for rule in rules
        ]
        return render_template(
            "rules.html",
            **_page_context(
                active_nav="rules",
                page_title="瑙勫垯绠＄悊",
                rules=rule_cards,
            ),
        )

    @app.get("/rules/new")
    @login_required
    def rule_new_page():
        return render_template(
            "rule_edit.html",
            **_page_context(
                active_nav="rule_new",
                page_title="鏂板缓瑙勫垯",
                errors=[],
                form_data={},
            ),
        )

    @app.post("/rules/new")
    @login_required
    def rule_new_submit():
        errors = _validate_rule_form(request.form)
        if errors:
            return render_template(
                "rule_edit.html",
                **_page_context(
                    active_nav="rule_new",
                    page_title="鏂板缓瑙勫垯",
                    errors=errors,
                    form_data=request.form,
                ),
            )

        with session_factory() as session:
            rule = RuleGroup(
                name=request.form["name"].strip(),
                is_enabled=request.form.get("is_enabled") == "on",
                match_mode=request.form["match_mode"],
                updated_by="admin",
            )
            session.add(rule)
            session.flush()

            def add_condition(field_name: str, operator: str, value_json: str) -> None:
                if value_json.strip():
                    session.add(
                        RuleCondition(
                            rule_group_id=rule.id,
                            field_name=field_name,
                            operator=operator,
                            value_json=value_json.strip(),
                        )
                    )

            add_condition("total_amount", "gte", request.form["amount_threshold"])
            add_condition("style_no", "in", request.form["style_list"])
            add_condition("store_name", "in", request.form["store_list"])
            add_condition(
                "sold_at",
                "date_range",
                f"{request.form.get('order_date_start', '').strip()},{request.form.get('order_date_end', '').strip()}",
            )
            add_condition("brand", "in", request.form["brand_list"])
            add_condition("category", "in", request.form["category_list"])
            session.commit()
        return redirect(url_for("rules_page"))

    @app.post("/rules/<int:rule_id>/disable")
    @login_required
    def rule_disable(rule_id: int):
        with session_factory() as session:
            rule = session.get(RuleGroup, rule_id)
            if rule is not None:
                rule.is_enabled = False
                session.commit()
        return redirect(url_for("rules_page"))

    @app.post("/rules/<int:rule_id>/enable")
    @login_required
    def rule_enable(rule_id: int):
        with session_factory() as session:
            rule = session.get(RuleGroup, rule_id)
            if rule is not None:
                rule.is_enabled = True
                session.commit()
        return redirect(url_for("rules_page"))

    @app.post("/rules/<int:rule_id>/delete")
    @login_required
    def rule_delete(rule_id: int):
        with session_factory() as session:
            session.query(RuleCondition).filter_by(rule_group_id=rule_id).delete()
            rule = session.get(RuleGroup, rule_id)
            if rule is not None:
                session.delete(rule)
            session.commit()
        return redirect(url_for("rules_page"))

    @app.get("/format-settings")
    @login_required
    def format_settings_page():
        with session_factory() as session:
            store = load_or_initialize_message_template_store(session)
            active = _find_template(store, store["active_template_id"]) or store["templates"][0]
        return render_template(
            "format_settings.html",
            **_template_workspace_context(
                store=store,
                payload={"template_body": active["template_body"]},
                save_message=None,
                errors=[],
            ),
        )

    @app.post("/format-settings")
    @login_required
    def format_settings_submit():
        template_body = str(request.form.get("template_body", ""))
        errors = [f"妯℃澘鏍￠獙澶辫触: {item}" for item in validate_message_template(template_body)]
        save_message = None
        with session_factory() as session:
            store = load_or_initialize_message_template_store(session)
            active = _find_template(store, store["active_template_id"]) or store["templates"][0]
            if not errors:
                save_message_template(
                    session,
                    template_id=active["id"],
                    template_name=active["name"],
                    template_body=template_body,
                    preset_key=active["preset_key"],
                    activate=True,
                )
                store = load_or_initialize_message_template_store(session)
                save_message = "模板已保存"
        return render_template(
            "format_settings.html",
            **_template_workspace_context(
                store=store,
                payload={"template_body": template_body},
                save_message=save_message,
                errors=errors,
            ),
        )
    @app.get("/runtime-settings")
    @login_required
    def runtime_settings_page():
        defaults = _runtime_controls_defaults(app)
        with session_factory() as session:
            controls = load_or_initialize_runtime_controls(session, defaults)
        return render_template(
            "runtime_settings.html",
            **_runtime_controls_page_context(
                controls=controls,
                save_message=None,
                errors=[],
            ),
        )

    @app.post("/runtime-settings")
    @login_required
    def runtime_settings_submit():
        defaults = _runtime_controls_defaults(app)
        errors: list[str] = []
        save_message = None
        try:
            scan_interval_seconds = int(request.form.get("scan_interval_seconds", "").strip())
            max_images_per_message = int(request.form.get("max_images_per_message", "").strip())
            push_interval_seconds = int(request.form.get("push_interval_seconds", "").strip())
            push_window_start = request.form.get("push_window_start", defaults.push_window_start).strip()
            push_window_end = request.form.get("push_window_end", defaults.push_window_end).strip()
            with session_factory() as session:
                controls = save_runtime_controls(
                    session,
                    scan_interval_seconds=scan_interval_seconds,
                    max_images_per_message=max_images_per_message,
                    push_interval_seconds=push_interval_seconds,
                    push_window_start=push_window_start,
                    push_window_end=push_window_end,
                    defaults=defaults,
                )
            save_message = "\u8fd0\u884c\u914d\u7f6e\u5df2\u4fdd\u5b58"
        except ValueError as exc:
            controls = defaults
            errors.append(f"\u8fd0\u884c\u914d\u7f6e\u4fdd\u5b58\u5931\u8d25: {exc}")
        return render_template(
            "runtime_settings.html",
            **_runtime_controls_page_context(
                controls=controls,
                save_message=save_message,
                errors=errors,
            ),
        )

    @app.get("/manual-test")
    @login_required
    def manual_test_page():
        return render_template(
            "manual_test.html",
            **_page_context(
                active_nav="manual_test",
                page_title="鎵嬪姩娴嬭瘯",
                errors=[],
                form_data=_manual_test_defaults(),
                manual_result=None,
            ),
        )

    @app.post("/manual-test")
    @login_required
    def manual_test_submit():
        form_data = _manual_test_form_data(request.form)
        errors = _validate_manual_test_form(request.form)
        result = None
        if not errors:
            try:
                project_root = Path(app.config.get("PROJECT_ROOT", Path.cwd()))
                with session_factory() as session:
                    message_template = load_or_initialize_message_template(session)
                result = _run_manual_test(
                    request.form,
                    project_root,
                    template_body=message_template["template_body"],
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"鎵嬪姩娴嬭瘯鎵ц澶辫触: {exc}")
        return render_template(
            "manual_test.html",
            **_page_context(
                active_nav="manual_test",
                page_title="鎵嬪姩娴嬭瘯",
                errors=errors,
                form_data=form_data,
                manual_result=result,
            ),
        )

    @app.get("/records")
    @login_required
    def records_page():
        with session_factory() as session:
            records = (
                session.query(PushRecord)
                .order_by(PushRecord.created_at.desc())
                .limit(50)
                .all()
            )
        record_rows = [
            {
                "order_no": record.order_no,
                "store_name": record.store_name,
                "total_amount": f"{record.total_amount:.2f}",
                "rule_name": record.rule_name,
                "status_label": _push_status_label(record.status),
                "error_message": record.error_message,
                "created_at": record.created_at.strftime("%Y-%m-%d %H:%M"),
            }
            for record in records
        ]
        return render_template(
            "push_records.html",
            **_page_context(
                active_nav="records",
                page_title="推送记录",
                records=record_rows,
            ),
        )

    @app.get("/status")
    @login_required
    def status_page():
        with session_factory() as session:
            last_run = session.query(JobRun).order_by(JobRun.created_at.desc()).first()
        run_view = None
        if last_run is not None:
            run_view = {
                "created_at": last_run.created_at.strftime("%Y-%m-%d %H:%M"),
                "window_start": last_run.window_start,
                "window_end": last_run.window_end,
                "status_label": _run_status_label(last_run.status),
                "success_count": last_run.success_count,
                "failed_count": last_run.failed_count,
                "error_summary": last_run.error_summary,
            }
        return render_template(
            "system_status.html",
            **_page_context(
                active_nav="status",
                page_title="系统状态",
                last_run=run_view,
            ),
        )

    return app



