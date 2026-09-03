# WeCom Admin UI Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the existing Flask admin backend into a usable Chinese management console with better navigation, rule visibility, feedback states, and a manual test page shell.

**Architecture:** Keep the current server-rendered Flask structure and improve it in place. Add small view-model helpers inside `web_app.py` to prepare navigation, page metadata, summaries, and error states, then rebuild the Jinja templates around that richer context. Do not modify the local compatibility edits in `src/wecom_sales_webhook_bot/cli.py`, `src/wecom_sales_webhook_bot/csv_source.py`, or `src/wecom_sales_webhook_bot/orchestrator.py`.

**Tech Stack:** Python 3.12, Flask, Flask-Login, SQLAlchemy, Jinja2, pytest

---

## Planned File Structure

**Create**

- `src/wecom_sales_webhook_bot/templates/manual_test.html`

**Modify**

- `src/wecom_sales_webhook_bot/web_app.py`
- `src/wecom_sales_webhook_bot/templates/base.html`
- `src/wecom_sales_webhook_bot/templates/login.html`
- `src/wecom_sales_webhook_bot/templates/rules.html`
- `src/wecom_sales_webhook_bot/templates/rule_edit.html`
- `src/wecom_sales_webhook_bot/templates/push_records.html`
- `src/wecom_sales_webhook_bot/templates/system_status.html`
- `tests/test_web_app.py`

**Responsibilities**

- `web_app.py`: prepare shared navigation context, login feedback, rule summaries, simple form validation, and the manual test route
- `base.html`: shared page shell, embedded CSS, top navigation, status badge styles, and flash/error blocks
- `login.html`: focused login layout with inline failure feedback
- `rules.html`: dashboard-style rule list with summaries and empty state
- `rule_edit.html`: grouped form sections, helper text, and validation messages
- `push_records.html`: richer record list with status and empty state
- `system_status.html`: latest job summary with populated and empty-state rendering
- `manual_test.html`: placeholder page for the later CSV + local image URL workflow
- `tests/test_web_app.py`: regression coverage for UI behavior and route accessibility

### Task 1: Add Web App Regression Tests For The New Admin UX

**Files:**
- Modify: `tests/test_web_app.py`
- Read for context: `src/wecom_sales_webhook_bot/web_app.py`

- [ ] **Step 1: Write the failing tests**

```python
from wecom_sales_webhook_bot.cli import build_parser
from wecom_sales_webhook_bot.rule_models import JobRun, PushRecord
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
    assert "金额 >= 10000" in page
    assert "门店: G621, G609" in page
    assert "时段: 10:00-18:00" in page


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_web_app.py -v
```

Expected:

- FAIL because `/manual-test` does not exist
- FAIL because failed login currently redirects without an inline error
- FAIL because rule summaries, validation messages, and empty states are not rendered
- `test_cli_exposes_run_server_command` still passes

- [ ] **Step 3: Commit the failing-test scaffold**

```bash
git add tests/test_web_app.py
git commit -m "test: define admin ui behavior coverage"
```

### Task 2: Add Shared Page Context, Rule Summaries, Validation, And Manual Test Route

**Files:**
- Modify: `src/wecom_sales_webhook_bot/web_app.py`
- Verify against: `src/wecom_sales_webhook_bot/rule_models.py`
- Reuse tests: `tests/test_web_app.py`

- [ ] **Step 1: Write the minimal route and helper implementation**

```python
from __future__ import annotations

from collections import defaultdict

from flask import Flask, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, login_required, login_user

from wecom_sales_webhook_bot.auth import hash_password, verify_password
from wecom_sales_webhook_bot.db import create_session_factory, initialize_database
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


def _page_context(*, active_nav: str, page_title: str, **extra: object) -> dict[str, object]:
    nav_items = [
        {"endpoint": "rules_page", "label": "规则管理", "key": "rules"},
        {"endpoint": "rule_new_page", "label": "新建规则", "key": "rule_new"},
        {"endpoint": "manual_test_page", "label": "手动测试", "key": "manual_test"},
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
    return {"all": "全部满足", "any": "任一满足"}.get(match_mode, match_mode)


def _rule_status_label(is_enabled: bool) -> str:
    return "启用中" if is_enabled else "已停用"


def _push_status_label(status: str) -> str:
    return {"success": "推送成功", "failed": "推送失败"}.get(status, status)


def _run_status_label(status: str) -> str:
    return {"success": "执行成功", "failed": "执行失败"}.get(status, status)


def _summarize_conditions(conditions: list[RuleCondition]) -> list[str]:
    summary: list[str] = []
    for condition in conditions:
        if condition.field_name == "total_amount" and condition.operator == "gte":
            summary.append(f"金额 >= {condition.value_json}")
        elif condition.field_name == "style_no" and condition.operator == "in":
            summary.append(f"款号: {', '.join(_split_csv_text(condition.value_json))}")
        elif condition.field_name == "store_name" and condition.operator == "in":
            summary.append(f"门店: {', '.join(_split_csv_text(condition.value_json))}")
        elif condition.field_name == "sold_at" and condition.operator == "between_time":
            start_time, end_time = condition.value_json.split(",", maxsplit=1)
            summary.append(f"时段: {start_time}-{end_time}")
        elif condition.field_name == "brand" and condition.operator == "in":
            summary.append(f"品牌: {', '.join(_split_csv_text(condition.value_json))}")
        elif condition.field_name == "category" and condition.operator == "in":
            summary.append(f"品类: {', '.join(_split_csv_text(condition.value_json))}")
    return summary


def _validate_rule_form(form) -> list[str]:
    errors: list[str] = []
    if not form.get("name", "").strip():
        errors.append("请填写规则名称")
    if form.get("match_mode") not in {"all", "any"}:
        errors.append("匹配方式不合法")
    has_start = bool(form.get("time_start", "").strip())
    has_end = bool(form.get("time_end", "").strip())
    if has_start != has_end:
        errors.append("时间段必须同时填写开始和结束时间")
    return errors


def create_app(config: dict) -> Flask:
    app = Flask(__name__)
    app.config.update(config)
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

    @app.get("/login")
    def login_page():
        return render_template(
            "login.html",
            **_page_context(active_nav="", page_title="登录", error_message=None),
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
                page_title="登录",
                error_message="用户名或密码错误",
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
                "name": rule.name,
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
                page_title="规则管理",
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
                page_title="新建规则",
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
                    page_title="新建规则",
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
            if request.form["time_start"] and request.form["time_end"]:
                add_condition(
                    "sold_at",
                    "between_time",
                    f"{request.form['time_start']},{request.form['time_end']}",
                )
            add_condition("brand", "in", request.form["brand_list"])
            add_condition("category", "in", request.form["category_list"])
            session.commit()
        return redirect(url_for("rules_page"))

    @app.get("/manual-test")
    @login_required
    def manual_test_page():
        return render_template(
            "manual_test.html",
            **_page_context(active_nav="manual_test", page_title="手动测试"),
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
```

- [ ] **Step 2: Run tests to verify the route behavior passes and template-related assertions still fail**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_web_app.py -v
```

Expected:

- Some tests still FAIL because the templates do not yet render the new context fields
- Route-level failures for `/manual-test`, failed login, and validation should be resolved

- [ ] **Step 3: Commit the route and helper layer**

```bash
git add src/wecom_sales_webhook_bot/web_app.py
git commit -m "feat: add admin ui page context and manual test route"
```

### Task 3: Rebuild The Shared Layout, Login Page, And Rule Pages

**Files:**
- Modify: `src/wecom_sales_webhook_bot/templates/base.html`
- Modify: `src/wecom_sales_webhook_bot/templates/login.html`
- Modify: `src/wecom_sales_webhook_bot/templates/rules.html`
- Modify: `src/wecom_sales_webhook_bot/templates/rule_edit.html`
- Create: `src/wecom_sales_webhook_bot/templates/manual_test.html`
- Reuse tests: `tests/test_web_app.py`

- [ ] **Step 1: Write the minimal template implementation**

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{{ page_title }} - {{ app_name }}</title>
    <style>
      :root {
        --bg: #f3f1ea;
        --panel: #fffdfa;
        --panel-strong: #f7f0dd;
        --text: #1f2520;
        --muted: #677067;
        --line: #d9d0be;
        --accent: #285943;
        --accent-soft: #e1efe6;
        --danger: #9f2f2f;
        --danger-soft: #f8e6e3;
        --ok: #2f6b3d;
        --ok-soft: #e4f2e8;
        --shadow: 0 18px 40px rgba(61, 60, 45, 0.08);
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
        color: var(--text);
        background:
          radial-gradient(circle at top left, rgba(224, 204, 156, 0.35), transparent 30%),
          linear-gradient(180deg, #f8f6ef 0%, var(--bg) 100%);
      }
      a { color: inherit; text-decoration: none; }
      .shell { width: min(1120px, calc(100% - 32px)); margin: 0 auto; padding: 24px 0 48px; }
      .topbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
        padding: 18px 22px;
        margin-bottom: 20px;
        background: rgba(255, 253, 250, 0.88);
        border: 1px solid rgba(217, 208, 190, 0.8);
        border-radius: 20px;
        box-shadow: var(--shadow);
        backdrop-filter: blur(10px);
      }
      .brand-title { margin: 0; font-size: 22px; font-weight: 700; }
      .brand-subtitle { margin: 6px 0 0; color: var(--muted); font-size: 14px; }
      .nav { display: flex; flex-wrap: wrap; gap: 10px; }
      .nav-link {
        padding: 10px 14px;
        border-radius: 999px;
        color: var(--muted);
        background: transparent;
        border: 1px solid transparent;
      }
      .nav-link.active {
        color: #ffffff;
        background: var(--accent);
      }
      .panel {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 24px;
        box-shadow: var(--shadow);
      }
      .page-header { padding: 28px 28px 12px; }
      .page-title { margin: 0; font-size: 28px; }
      .page-copy { margin: 8px 0 0; color: var(--muted); }
      .content { padding: 0 28px 28px; }
      .alert {
        padding: 14px 16px;
        margin-bottom: 16px;
        border-radius: 16px;
        border: 1px solid transparent;
      }
      .alert.error {
        color: var(--danger);
        background: var(--danger-soft);
        border-color: rgba(159, 47, 47, 0.16);
      }
      .badge {
        display: inline-flex;
        align-items: center;
        padding: 6px 10px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 700;
      }
      .badge.ok { color: var(--ok); background: var(--ok-soft); }
      .badge.neutral { color: var(--accent); background: var(--accent-soft); }
      .badge.danger { color: var(--danger); background: var(--danger-soft); }
      .grid { display: grid; gap: 18px; }
      .rule-card, .record-card, .status-card, .test-card {
        padding: 20px;
        border: 1px solid var(--line);
        border-radius: 20px;
        background: #fffefb;
      }
      .rule-meta, .record-meta, .status-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 10px 12px;
        color: var(--muted);
        font-size: 14px;
      }
      .summary-list {
        margin: 14px 0 0;
        padding-left: 18px;
        color: var(--text);
      }
      .summary-list li { margin: 6px 0; }
      .empty-state {
        padding: 32px 20px;
        text-align: center;
        color: var(--muted);
        border: 1px dashed var(--line);
        border-radius: 18px;
        background: #fffdfa;
      }
      .action-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
        margin-bottom: 18px;
      }
      .button {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 12px 18px;
        border: 0;
        border-radius: 14px;
        background: var(--accent);
        color: #ffffff;
        font-weight: 700;
        cursor: pointer;
      }
      .button.secondary {
        background: var(--panel-strong);
        color: var(--text);
      }
      .form-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 16px;
      }
      .form-section {
        padding: 20px;
        border-radius: 20px;
        background: #fffefb;
        border: 1px solid var(--line);
      }
      .field { display: grid; gap: 8px; margin-bottom: 14px; }
      .field input, .field select {
        width: 100%;
        padding: 12px 14px;
        border: 1px solid var(--line);
        border-radius: 12px;
        background: #fffdfa;
        font: inherit;
      }
      .hint { color: var(--muted); font-size: 13px; }
      .single-column { width: min(520px, calc(100% - 32px)); margin: 48px auto; }
      @media (max-width: 760px) {
        .topbar { flex-direction: column; align-items: flex-start; }
        .form-grid { grid-template-columns: 1fr; }
        .action-row { flex-direction: column; align-items: stretch; }
      }
    </style>
  </head>
  <body>
    {% block layout %}
    <div class="shell">
      {% if active_nav %}
      <header class="topbar">
        <div>
          <h1 class="brand-title">{{ app_name }}</h1>
          <p class="brand-subtitle">规则管理、推送记录与手动验证入口</p>
        </div>
        <nav class="nav">
          {% for item in nav_items %}
          <a
            class="nav-link{% if item.key == active_nav %} active{% endif %}"
            href="{{ url_for(item.endpoint) }}"
          >
            {{ item.label }}
          </a>
          {% endfor %}
        </nav>
      </header>
      {% endif %}
      {% block body %}{% endblock %}
    </div>
    {% endblock %}
  </body>
</html>
```

```html
{% extends "base.html" %}
{% block layout %}
<div class="single-column">
  <section class="panel">
    <div class="page-header">
      <h1 class="page-title">{{ app_name }}</h1>
      <p class="page-copy">内部规则维护与推送状态查看入口。</p>
    </div>
    <div class="content">
      {% if error_message %}
      <div class="alert error">{{ error_message }}</div>
      {% endif %}
      <form method="post" action="/login">
        <div class="field">
          <label for="username">用户名</label>
          <input id="username" name="username" autocomplete="username" />
        </div>
        <div class="field">
          <label for="password">密码</label>
          <input id="password" name="password" type="password" autocomplete="current-password" />
        </div>
        <button class="button" type="submit">登录后台</button>
      </form>
    </div>
  </section>
</div>
{% endblock %}
```

```html
{% extends "base.html" %}
{% block body %}
<section class="panel">
  <div class="page-header">
    <div class="action-row">
      <div>
        <h1 class="page-title">规则管理</h1>
        <p class="page-copy">在这里快速查看启用状态、匹配方式与筛选摘要。</p>
      </div>
      <a class="button" href="{{ url_for('rule_new_page') }}">新建规则</a>
    </div>
  </div>
  <div class="content">
    {% if not rules %}
    <div class="empty-state">
      <p>还没有规则。</p>
      <p>先创建第一条规则，后续再从手动测试页验证 CSV 与本地图片链路。</p>
    </div>
    {% else %}
    <div class="grid">
      {% for rule in rules %}
      <article class="rule-card">
        <div class="action-row">
          <h2>{{ rule.name }}</h2>
          <span class="badge {% if rule.status_label == '启用中' %}ok{% else %}neutral{% endif %}">
            {{ rule.status_label }}
          </span>
        </div>
        <div class="rule-meta">
          <span>匹配方式: {{ rule.match_mode_label }}</span>
          <span>更新人: {{ rule.updated_by }}</span>
          <span>更新时间: {{ rule.updated_at }}</span>
        </div>
        {% if rule.condition_summary %}
        <ul class="summary-list">
          {% for line in rule.condition_summary %}
          <li>{{ line }}</li>
          {% endfor %}
        </ul>
        {% else %}
        <p class="page-copy">当前没有筛选条件。</p>
        {% endif %}
      </article>
      {% endfor %}
    </div>
    {% endif %}
  </div>
</section>
{% endblock %}
```

```html
{% extends "base.html" %}
{% block body %}
<section class="panel">
  <div class="page-header">
    <h1 class="page-title">新建规则</h1>
    <p class="page-copy">先定义基础信息，再补充门店、款号、品牌、品类与时段条件。</p>
  </div>
  <div class="content">
    {% if errors %}
    <div class="alert error">
      {% for item in errors %}
      <div>{{ item }}</div>
      {% endfor %}
    </div>
    {% endif %}
    <form method="post" action="/rules/new">
      <div class="form-grid">
        <section class="form-section">
          <h2>基础信息</h2>
          <div class="field">
            <label for="name">规则名称</label>
            <input id="name" name="name" value="{{ form_data.get('name', '') }}" />
          </div>
          <div class="field">
            <label for="match_mode">匹配方式</label>
            <select id="match_mode" name="match_mode">
              <option value="any" {% if form_data.get('match_mode') == 'any' %}selected{% endif %}>任一满足</option>
              <option value="all" {% if form_data.get('match_mode', 'all') == 'all' %}selected{% endif %}>全部满足</option>
            </select>
          </div>
          <div class="field">
            <label>
              <input
                type="checkbox"
                name="is_enabled"
                {% if form_data.get('is_enabled', 'on') == 'on' %}checked{% endif %}
              />
              启用这条规则
            </label>
          </div>
        </section>
        <section class="form-section">
          <h2>筛选条件</h2>
          <div class="field">
            <label for="amount_threshold">金额阈值</label>
            <input id="amount_threshold" name="amount_threshold" value="{{ form_data.get('amount_threshold', '') }}" />
            <div class="hint">示例: 10000</div>
          </div>
          <div class="field">
            <label for="style_list">款号列表</label>
            <input id="style_list" name="style_list" value="{{ form_data.get('style_list', '') }}" />
            <div class="hint">多个值用英文逗号分隔。</div>
          </div>
          <div class="field">
            <label for="store_list">门店列表</label>
            <input id="store_list" name="store_list" value="{{ form_data.get('store_list', '') }}" />
          </div>
          <div class="field">
            <label for="brand_list">品牌列表</label>
            <input id="brand_list" name="brand_list" value="{{ form_data.get('brand_list', '') }}" />
          </div>
          <div class="field">
            <label for="category_list">品类列表</label>
            <input id="category_list" name="category_list" value="{{ form_data.get('category_list', '') }}" />
          </div>
          <div class="form-grid">
            <div class="field">
              <label for="time_start">开始时间</label>
              <input id="time_start" name="time_start" value="{{ form_data.get('time_start', '') }}" />
            </div>
            <div class="field">
              <label for="time_end">结束时间</label>
              <input id="time_end" name="time_end" value="{{ form_data.get('time_end', '') }}" />
            </div>
          </div>
        </section>
      </div>
      <div class="action-row" style="margin-top: 18px;">
        <a class="button secondary" href="{{ url_for('rules_page') }}">返回规则列表</a>
        <button class="button" type="submit">保存规则</button>
      </div>
    </form>
  </div>
</section>
{% endblock %}
```

```html
{% extends "base.html" %}
{% block body %}
<section class="panel">
  <div class="page-header">
    <h1 class="page-title">手动测试</h1>
    <p class="page-copy">此页面将用于手动验证流程，下一步会接入 CSV + 本地图片 URL。</p>
  </div>
  <div class="content">
    <div class="grid">
      <article class="test-card">
        <h2>验证范围</h2>
        <p>当前版本只提供入口与页面骨架，不接真实 IT API。</p>
      </article>
      <article class="test-card">
        <h2>后续输入区</h2>
        <p>这里将放置 CSV 文件选择、时间窗口与本地图片 URL 校验配置。</p>
      </article>
      <article class="test-card">
        <h2>后续结果区</h2>
        <p>这里将展示命中规则、消息预览、图片链接检查与执行结果摘要。</p>
      </article>
    </div>
  </div>
</section>
{% endblock %}
```

- [ ] **Step 2: Run tests to verify the login, rules, and manual test assertions pass**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_web_app.py::test_login_page_shows_error_message_after_failed_login tests/test_web_app.py::test_rule_save_persists_match_mode_and_shows_condition_summary tests/test_web_app.py::test_rules_page_shows_empty_state_and_manual_test_navigation tests/test_web_app.py::test_manual_test_page_loads_after_login tests/test_web_app.py::test_rule_create_page_renders_validation_errors -v
```

Expected:

- PASS with `5 passed`

- [ ] **Step 3: Commit the layout and rule-page templates**

```bash
git add src/wecom_sales_webhook_bot/templates/base.html src/wecom_sales_webhook_bot/templates/login.html src/wecom_sales_webhook_bot/templates/rules.html src/wecom_sales_webhook_bot/templates/rule_edit.html src/wecom_sales_webhook_bot/templates/manual_test.html
git commit -m "feat: refresh admin rules ui"
```

### Task 4: Rebuild Records And Status Pages And Verify The Whole Web UI Slice

**Files:**
- Modify: `src/wecom_sales_webhook_bot/templates/push_records.html`
- Modify: `src/wecom_sales_webhook_bot/templates/system_status.html`
- Reuse: `tests/test_web_app.py`

- [ ] **Step 1: Write the minimal template implementation**

```html
{% extends "base.html" %}
{% block body %}
<section class="panel">
  <div class="page-header">
    <h1 class="page-title">推送记录</h1>
    <p class="page-copy">按时间倒序展示最近 50 条推送结果。</p>
  </div>
  <div class="content">
    {% if not records %}
    <div class="empty-state">
      <p>暂无推送记录。</p>
      <p>后续在手动测试或定时扫描跑通后，这里会出现历史结果。</p>
    </div>
    {% else %}
    <div class="grid">
      {% for record in records %}
      <article class="record-card">
        <div class="action-row">
          <h2>{{ record.order_no }}</h2>
          <span class="badge {% if record.status_label == '推送成功' %}ok{% else %}danger{% endif %}">
            {{ record.status_label }}
          </span>
        </div>
        <div class="record-meta">
          <span>门店: {{ record.store_name }}</span>
          <span>金额: {{ record.total_amount }}</span>
          <span>命中规则: {{ record.rule_name }}</span>
          <span>时间: {{ record.created_at }}</span>
        </div>
        {% if record.error_message %}
        <div class="alert error" style="margin-top: 14px;">{{ record.error_message }}</div>
        {% endif %}
      </article>
      {% endfor %}
    </div>
    {% endif %}
  </div>
</section>
{% endblock %}
```

```html
{% extends "base.html" %}
{% block body %}
<section class="panel">
  <div class="page-header">
    <h1 class="page-title">系统状态</h1>
    <p class="page-copy">查看最近一次扫描任务的执行结果和时间窗口。</p>
  </div>
  <div class="content">
    {% if not last_run %}
    <div class="empty-state">
      <p>尚未执行扫描任务。</p>
      <p>后续完成手动测试与扫描联调后，这里会展示最新运行摘要。</p>
    </div>
    {% else %}
    <article class="status-card">
      <div class="action-row">
        <h2>最近一次扫描</h2>
        <span class="badge {% if last_run.status_label == '执行成功' %}ok{% else %}danger{% endif %}">
          {{ last_run.status_label }}
        </span>
      </div>
      <div class="status-meta">
        <span>记录时间: {{ last_run.created_at }}</span>
        <span>窗口开始: {{ last_run.window_start }}</span>
        <span>窗口结束: {{ last_run.window_end }}</span>
        <span>成功 {{ last_run.success_count }}</span>
        <span>失败 {{ last_run.failed_count }}</span>
      </div>
      {% if last_run.error_summary %}
      <div class="alert error" style="margin-top: 14px;">{{ last_run.error_summary }}</div>
      {% endif %}
    </article>
    {% endif %}
  </div>
</section>
{% endblock %}
```

- [ ] **Step 2: Run the full web-app test file**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_web_app.py -v
```

Expected:

- PASS with all tests in `tests/test_web_app.py` green

- [ ] **Step 3: Run the broader regression slice that this UI work should not break**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_auth.py tests/test_db_models.py tests/test_rule_service.py tests/test_web_app.py -v
```

Expected:

- PASS with all targeted backend UI tests green

- [ ] **Step 4: Commit the records and status UI**

```bash
git add src/wecom_sales_webhook_bot/templates/push_records.html src/wecom_sales_webhook_bot/templates/system_status.html tests/test_web_app.py
git commit -m "feat: polish admin records and status pages"
```

## Self-Review

### Spec Coverage

- 登录页错误反馈: covered by Tasks 1, 2, and 3
- 规则列表导航、状态、摘要、空态: covered by Tasks 1, 2, and 3
- 规则新建页分组表单与校验反馈: covered by Tasks 1, 2, and 3
- 手动测试页骨架与导航入口: covered by Tasks 1, 2, and 3
- 推送记录页增强与空态: covered by Tasks 1 and 4
- 系统状态页增强与空态: covered by Tasks 1 and 4
- 不接真实 API、避免触碰本地兼容文件: enforced in the architecture section and by the file list

### Placeholder Scan

- No `TODO`, `TBD`, or deferred implementation placeholders remain in the task steps.
- Each task includes concrete file paths, code snippets, commands, and expected outcomes.

### Type Consistency

- Navigation route names stay consistent as `rules_page`, `rule_new_page`, `manual_test_page`, `records_page`, and `status_page`.
- Template context names stay consistent as `app_name`, `page_title`, `active_nav`, `nav_items`, `rules`, `records`, `last_run`, `errors`, and `form_data`.
- Display label helpers use the same status vocabulary expected by the tests: `启用中`, `全部满足`, `推送成功`, `执行成功`.
