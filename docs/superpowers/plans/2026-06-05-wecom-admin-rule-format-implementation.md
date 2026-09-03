# WeCom Admin Rule Actions And Global Format Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reversible rule enable or disable actions, permanent rule deletion, and a global format management page that controls message field visibility, labels, and preset templates.

**Architecture:** Extend the existing Flask admin backend in place. Use the current `RuleGroup.is_enabled` field for active vs disabled state, add one database-backed global settings row for message format configuration, and parameterize `message_builder.py` with a normalized format config plus preset selection. Keep the manual test preview and the formal push message on the same rendering path so the global format settings affect both consistently.

**Tech Stack:** Python 3.12, Flask, Flask-Login, SQLAlchemy, Jinja2, pytest

---

## Planned File Structure

**Create**

- `src/wecom_sales_webhook_bot/format_settings.py`
- `src/wecom_sales_webhook_bot/templates/format_settings.html`

**Modify**

- `src/wecom_sales_webhook_bot/rule_models.py`
- `src/wecom_sales_webhook_bot/web_app.py`
- `src/wecom_sales_webhook_bot/message_builder.py`
- `src/wecom_sales_webhook_bot/templates/base.html`
- `src/wecom_sales_webhook_bot/templates/rules.html`
- `tests/test_web_app.py`
- `tests/test_message_builder.py`
- `tests/test_db_models.py`

**Responsibilities**

- `rule_models.py`: add one global settings model for persisted message format config
- `format_settings.py`: define default format config, supported presets, normalization, and field metadata
- `web_app.py`: load and save format settings, expose the format management page, add rule disable/restore/delete routes, and make manual test previews use the saved global format config
- `message_builder.py`: render summary and item blocks according to enabled fields, custom labels, and preset style
- `base.html`: add navigation entry for `格式管理`
- `rules.html`: add `停用` / `恢复` / `删除` actions with confirmation for delete
- `format_settings.html`: render preset selector, field toggles, and label inputs
- `tests/test_web_app.py`: verify rule actions and format management UI behavior
- `tests/test_message_builder.py`: verify field hiding, label overrides, and preset-driven output differences
- `tests/test_db_models.py`: verify the new global settings table persists format config

### Task 1: Add Persistence And Helpers For Global Format Settings

**Files:**
- Modify: `src/wecom_sales_webhook_bot/rule_models.py`
- Create: `src/wecom_sales_webhook_bot/format_settings.py`
- Modify: `tests/test_db_models.py`

- [ ] **Step 1: Write the failing tests**

```python
from wecom_sales_webhook_bot.db import create_session_factory, initialize_database
from wecom_sales_webhook_bot.format_settings import (
    DEFAULT_FORMAT_SETTINGS,
    normalize_format_settings,
)
from wecom_sales_webhook_bot.rule_models import GlobalSetting


def test_initialize_database_creates_global_settings_table(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    session_factory = create_session_factory(database_url)

    initialize_database(session_factory)

    with session_factory() as session:
        session.add(
            GlobalSetting(
                setting_key="message_format",
                setting_json='{"preset":"compact"}',
            )
        )
        session.commit()

    with session_factory() as session:
        row = session.query(GlobalSetting).filter_by(setting_key="message_format").one()
        assert row.setting_key == "message_format"


def test_normalize_format_settings_fills_defaults_and_rejects_unknown_preset() -> None:
    normalized = normalize_format_settings(
        {
            "preset": "compact",
            "fields": {
                "match_reason": {"enabled": False, "label": ""},
                "total_amount": {"enabled": True, "label": "成交金额"},
            },
        }
    )

    assert normalized["preset"] == "compact"
    assert normalized["fields"]["match_reason"]["enabled"] is False
    assert normalized["fields"]["match_reason"]["label"] == DEFAULT_FORMAT_SETTINGS["fields"]["match_reason"]["label"]
    assert normalized["fields"]["total_amount"]["label"] == "成交金额"
    assert normalized["fields"]["store_name"]["enabled"] is True

    try:
        normalize_format_settings({"preset": "unknown", "fields": {}})
    except ValueError as exc:
        assert "preset" in str(exc)
    else:
        raise AssertionError("expected invalid preset to raise ValueError")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_db_models.py::test_initialize_database_creates_global_settings_table tests/test_db_models.py::test_normalize_format_settings_fills_defaults_and_rejects_unknown_preset -v
```

Expected:

- FAIL because `GlobalSetting` and `format_settings.py` do not exist yet

- [ ] **Step 3: Write the minimal implementation**

```python
class GlobalSetting(Base):
    __tablename__ = "global_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    setting_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    setting_json: Mapped[str] = mapped_column(Text, nullable=False)
```

```python
from __future__ import annotations

import copy


SUPPORTED_PRESETS = {
    "standard": {
        "display_name": "标准版",
        "summary_heading": "成交摘要",
        "show_summary_heading": True,
        "item_heading": "商品信息",
    },
    "compact": {
        "display_name": "精简版",
        "summary_heading": "核心信息",
        "show_summary_heading": False,
        "item_heading": "商品",
    },
    "detailed": {
        "display_name": "明细版",
        "summary_heading": "订单摘要",
        "show_summary_heading": True,
        "item_heading": "商品明细",
    },
}

DEFAULT_FORMAT_SETTINGS = {
    "preset": "standard",
    "fields": {
        "order_no": {"enabled": True, "label": "销售单号"},
        "store_name": {"enabled": True, "label": "门店"},
        "sold_at": {"enabled": True, "label": "时间"},
        "total_amount": {"enabled": True, "label": "总金额"},
        "match_reason": {"enabled": True, "label": "命中原因"},
        "style_no": {"enabled": True, "label": "款号"},
        "unit_price": {"enabled": True, "label": "单价"},
        "barcode": {"enabled": True, "label": "条码"},
        "brand": {"enabled": True, "label": "品牌"},
        "category": {"enabled": True, "label": "品类"},
        "image": {"enabled": True, "label": "图片"},
    },
}


def normalize_format_settings(raw: dict | None) -> dict:
    normalized = copy.deepcopy(DEFAULT_FORMAT_SETTINGS)
    if raw is None:
        return normalized

    preset = raw.get("preset", normalized["preset"])
    if preset not in SUPPORTED_PRESETS:
        raise ValueError(f"Unsupported preset: {preset}")
    normalized["preset"] = preset

    raw_fields = raw.get("fields", {})
    for field_key, defaults in normalized["fields"].items():
        incoming = raw_fields.get(field_key, {})
        normalized["fields"][field_key]["enabled"] = bool(
            incoming.get("enabled", defaults["enabled"])
        )
        label = str(incoming.get("label", defaults["label"])).strip()
        normalized["fields"][field_key]["label"] = label or defaults["label"]
    return normalized
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_db_models.py::test_initialize_database_creates_global_settings_table tests/test_db_models.py::test_normalize_format_settings_fills_defaults_and_rejects_unknown_preset -v
```

Expected:

- PASS with `2 passed`

- [ ] **Step 5: Commit**

```bash
git add src/wecom_sales_webhook_bot/rule_models.py src/wecom_sales_webhook_bot/format_settings.py tests/test_db_models.py
git commit -m "feat: add global format settings model"
```

### Task 2: Add Rule Disable, Restore, And Permanent Delete Actions

**Files:**
- Modify: `src/wecom_sales_webhook_bot/web_app.py`
- Modify: `src/wecom_sales_webhook_bot/templates/rules.html`
- Modify: `tests/test_web_app.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_rules_page_shows_disable_and_delete_actions_for_enabled_rule() -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)

    client.post(
        "/rules/new",
        data={
            "name": "金额规则",
            "is_enabled": "on",
            "match_mode": "all",
            "amount_threshold": "10000",
            "style_list": "",
            "store_list": "",
            "time_start": "",
            "time_end": "",
            "brand_list": "",
            "category_list": "",
        },
    )

    page = client.get("/rules").get_data(as_text=True)
    assert "停用" in page
    assert "删除" in page


def test_rule_can_be_disabled_restored_and_deleted() -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)

    client.post(
        "/rules/new",
        data={
            "name": "款号规则",
            "is_enabled": "on",
            "match_mode": "any",
            "amount_threshold": "",
            "style_list": "STYLE-1",
            "store_list": "",
            "time_start": "",
            "time_end": "",
            "brand_list": "",
            "category_list": "",
        },
    )

    session_factory = app.config["SESSION_FACTORY"]
    with session_factory() as session:
        rule_id = session.query(RuleGroup).filter_by(name="款号规则").one().id

    disabled = client.post(f"/rules/{rule_id}/disable", follow_redirects=True)
    assert "已停用" in disabled.get_data(as_text=True)
    assert "恢复" in disabled.get_data(as_text=True)

    restored = client.post(f"/rules/{rule_id}/enable", follow_redirects=True)
    assert "启用中" in restored.get_data(as_text=True)

    deleted = client.post(f"/rules/{rule_id}/delete", follow_redirects=True)
    page = deleted.get_data(as_text=True)
    assert "款号规则" not in page

    with session_factory() as session:
        assert session.query(RuleGroup).filter_by(id=rule_id).count() == 0
        assert session.query(RuleCondition).filter_by(rule_group_id=rule_id).count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_web_app.py::test_rules_page_shows_disable_and_delete_actions_for_enabled_rule tests/test_web_app.py::test_rule_can_be_disabled_restored_and_deleted -v
```

Expected:

- FAIL because action buttons and routes do not exist yet

- [ ] **Step 3: Write the minimal implementation**

```python
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
```

```python
rule_cards = [
    {
        "id": rule.id,
        "name": rule.name,
        "status_label": _rule_status_label(rule.is_enabled),
        "match_mode_label": _match_mode_label(rule.match_mode),
        "updated_by": rule.updated_by,
        "updated_at": rule.updated_at.strftime("%Y-%m-%d %H:%M"),
        "condition_summary": _summarize_conditions(grouped[rule.id]),
        "is_enabled": rule.is_enabled,
    }
    for rule in rules
]
```

```html
<div class="action-row">
  <h2>{{ rule.name }}</h2>
  <div style="display: flex; gap: 8px; align-items: center;">
    <span class="badge {% if rule.status_label == '启用中' %}ok{% else %}neutral{% endif %}">
      {{ rule.status_label }}
    </span>
    {% if rule.is_enabled %}
    <form method="post" action="/rules/{{ rule.id }}/disable">
      <button class="button secondary" type="submit">停用</button>
    </form>
    {% else %}
    <form method="post" action="/rules/{{ rule.id }}/enable">
      <button class="button secondary" type="submit">恢复</button>
    </form>
    {% endif %}
    <form method="post" action="/rules/{{ rule.id }}/delete" onsubmit="return confirm('确认删除这条规则吗？');">
      <button class="button secondary" type="submit">删除</button>
    </form>
  </div>
</div>
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_web_app.py::test_rules_page_shows_disable_and_delete_actions_for_enabled_rule tests/test_web_app.py::test_rule_can_be_disabled_restored_and_deleted -v
```

Expected:

- PASS with `2 passed`

- [ ] **Step 5: Commit**

```bash
git add src/wecom_sales_webhook_bot/web_app.py src/wecom_sales_webhook_bot/templates/rules.html tests/test_web_app.py
git commit -m "feat: add rule disable and delete actions"
```

### Task 3: Add Global Format Management Page And Persistence

**Files:**
- Modify: `src/wecom_sales_webhook_bot/web_app.py`
- Modify: `src/wecom_sales_webhook_bot/templates/base.html`
- Create: `src/wecom_sales_webhook_bot/templates/format_settings.html`
- Modify: `tests/test_web_app.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_format_settings_page_loads_defaults_after_login() -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)

    response = client.get("/format-settings")

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "格式管理" in page
    assert "标准版" in page
    assert "命中原因" in page


def test_format_settings_page_saves_preset_visibility_and_labels() -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)

    response = client.post(
        "/format-settings",
        data={
            "preset": "compact",
            "enabled_order_no": "on",
            "enabled_store_name": "on",
            "enabled_sold_at": "on",
            "enabled_total_amount": "on",
            "enabled_match_reason": "",
            "enabled_style_no": "on",
            "enabled_unit_price": "on",
            "enabled_barcode": "on",
            "enabled_brand": "on",
            "enabled_category": "on",
            "enabled_image": "on",
            "label_order_no": "销售单号",
            "label_store_name": "店铺",
            "label_sold_at": "成交时间",
            "label_total_amount": "成交金额",
            "label_match_reason": "命中原因",
            "label_style_no": "款号",
            "label_unit_price": "单价",
            "label_barcode": "条码",
            "label_brand": "品牌",
            "label_category": "品类",
            "label_image": "图片",
        },
        follow_redirects=True,
    )

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "格式设置已保存" in page
    assert "精简版" in page
    assert "店铺" in page

    session_factory = app.config["SESSION_FACTORY"]
    with session_factory() as session:
        row = session.query(GlobalSetting).filter_by(setting_key="message_format").one()
        assert '"preset": "compact"' in row.setting_json
        assert '"match_reason"' in row.setting_json
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_web_app.py::test_format_settings_page_loads_defaults_after_login tests/test_web_app.py::test_format_settings_page_saves_preset_visibility_and_labels -v
```

Expected:

- FAIL because the route, template, and persistence path do not exist yet

- [ ] **Step 3: Write the minimal implementation**

```python
import json

from wecom_sales_webhook_bot.format_settings import (
    DEFAULT_FORMAT_SETTINGS,
    SUPPORTED_PRESETS,
    normalize_format_settings,
)
from wecom_sales_webhook_bot.rule_models import GlobalSetting
```

```python
def _load_message_format_settings(session) -> dict:
    row = session.query(GlobalSetting).filter_by(setting_key="message_format").one_or_none()
    if row is None:
        return normalize_format_settings(None)
    return normalize_format_settings(json.loads(row.setting_json))


def _format_settings_from_form(form) -> dict:
    field_keys = list(DEFAULT_FORMAT_SETTINGS["fields"].keys())
    return normalize_format_settings(
        {
            "preset": form.get("preset", DEFAULT_FORMAT_SETTINGS["preset"]),
            "fields": {
                key: {
                    "enabled": form.get(f"enabled_{key}") == "on",
                    "label": form.get(f"label_{key}", ""),
                }
                for key in field_keys
            },
        }
    )
```

```python
@app.get("/format-settings")
@login_required
def format_settings_page():
    with session_factory() as session:
        settings = _load_message_format_settings(session)
    return render_template(
        "format_settings.html",
        **_page_context(
            active_nav="format_settings",
            page_title="格式管理",
            format_settings=settings,
            preset_options=SUPPORTED_PRESETS,
            save_message=None,
            errors=[],
        ),
    )


@app.post("/format-settings")
@login_required
def format_settings_submit():
    errors: list[str] = []
    try:
        settings = _format_settings_from_form(request.form)
    except ValueError as exc:
        settings = normalize_format_settings(None)
        errors.append(str(exc))
    else:
        with session_factory() as session:
            row = session.query(GlobalSetting).filter_by(setting_key="message_format").one_or_none()
            payload = json.dumps(settings, ensure_ascii=False, sort_keys=True)
            if row is None:
                session.add(GlobalSetting(setting_key="message_format", setting_json=payload))
            else:
                row.setting_json = payload
            session.commit()
    return render_template(
        "format_settings.html",
        **_page_context(
            active_nav="format_settings",
            page_title="格式管理",
            format_settings=settings,
            preset_options=SUPPORTED_PRESETS,
            save_message="格式设置已保存" if not errors else None,
            errors=errors,
        ),
    )
```

```html
<a class="nav-link{% if item.key == active_nav %} active{% endif %}" href="{{ url_for(item.endpoint) }}">
  {{ item.label }}
</a>
```

```python
{"endpoint": "format_settings_page", "label": "格式管理", "key": "format_settings"},
```

```html
{% extends "base.html" %}
{% block body %}
<section class="panel">
  <div class="page-header">
    <h1 class="page-title">格式管理</h1>
    <p class="page-copy">控制全局消息字段开关、显示名称和模板预设。</p>
  </div>
  <div class="content">
    {% if save_message %}
    <div class="badge ok" style="margin-bottom: 16px;">{{ save_message }}</div>
    {% endif %}
    {% if errors %}
    <div class="alert error">
      {% for item in errors %}
      <div>{{ item }}</div>
      {% endfor %}
    </div>
    {% endif %}
    <form method="post" action="/format-settings">
      <div class="form-section" style="margin-bottom: 18px;">
        <h2>模板预设</h2>
        <div class="field">
          <label for="preset">选择预设</label>
          <select id="preset" name="preset">
            {% for key, preset in preset_options.items() %}
            <option value="{{ key }}" {% if format_settings.preset == key %}selected{% endif %}>
              {{ preset.display_name }}
            </option>
            {% endfor %}
          </select>
        </div>
      </div>
      <div class="grid">
        {% for key, config in format_settings.fields.items() %}
        <section class="form-section">
          <h2>{{ key }}</h2>
          <div class="field">
            <label>
              <input type="checkbox" name="enabled_{{ key }}" {% if config.enabled %}checked{% endif %} />
              显示此词条
            </label>
          </div>
          <div class="field">
            <label for="label_{{ key }}">显示名称</label>
            <input id="label_{{ key }}" name="label_{{ key }}" value="{{ config.label }}" />
          </div>
        </section>
        {% endfor %}
      </div>
      <div class="action-row" style="margin-top: 18px;">
        <button class="button" type="submit">保存格式设置</button>
      </div>
    </form>
  </div>
</section>
{% endblock %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_web_app.py::test_format_settings_page_loads_defaults_after_login tests/test_web_app.py::test_format_settings_page_saves_preset_visibility_and_labels -v
```

Expected:

- PASS with `2 passed`

- [ ] **Step 5: Commit**

```bash
git add src/wecom_sales_webhook_bot/web_app.py src/wecom_sales_webhook_bot/templates/base.html src/wecom_sales_webhook_bot/templates/format_settings.html tests/test_web_app.py
git commit -m "feat: add global format management page"
```

### Task 4: Make The Message Builder Honor Global Field Toggles, Labels, And Presets

**Files:**
- Modify: `src/wecom_sales_webhook_bot/message_builder.py`
- Modify: `src/wecom_sales_webhook_bot/web_app.py`
- Modify: `tests/test_message_builder.py`
- Modify: `tests/test_web_app.py`

- [ ] **Step 1: Write the failing tests**

```python
from wecom_sales_webhook_bot.format_settings import normalize_format_settings
```

```python
def test_message_builder_hides_match_reason_and_renames_total_amount_label() -> None:
    order = SalesOrder(
        order_no="SO-010",
        sold_at=datetime(2026, 4, 20, 10, 0, 0),
        store_name="上海一店",
        total_amount=1200,
        items=[SalesLineItem(barcode="6901111111111", style_no="A1001", unit_price=699)],
    )

    settings = normalize_format_settings(
        {
            "preset": "standard",
            "fields": {
                "match_reason": {"enabled": False, "label": "命中原因"},
                "total_amount": {"enabled": True, "label": "成交金额"},
            },
        }
    )

    message = build_markdown_v2_message(
        order=order,
        filter_result=FilterResult(matched=True, reason="amount_threshold"),
        image_urls={},
        max_images=8,
        format_settings=settings,
    )

    assert "命中原因" not in message
    assert "成交金额" in message
    assert "总金额" not in message


def test_message_builder_uses_compact_preset_heading() -> None:
    order = SalesOrder(
        order_no="SO-011",
        sold_at=datetime(2026, 4, 20, 10, 0, 0),
        store_name="上海一店",
        total_amount=1200,
        items=[SalesLineItem(barcode="6901111111111", style_no="A1001", unit_price=699)],
    )

    settings = normalize_format_settings({"preset": "compact", "fields": {}})

    message = build_markdown_v2_message(
        order=order,
        filter_result=FilterResult(matched=True, reason="amount_threshold"),
        image_urls={},
        max_images=8,
        format_settings=settings,
    )

    assert "核心信息" in message or "商品" in message
```

```python
def test_manual_test_page_uses_saved_global_format_settings() -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)

    session_factory = app.config["SESSION_FACTORY"]
    with session_factory() as session:
        session.add(
            GlobalSetting(
                setting_key="message_format",
                setting_json='{"preset":"compact","fields":{"match_reason":{"enabled":false,"label":"命中原因"},"total_amount":{"enabled":true,"label":"成交金额"}}}',
            )
        )
        session.commit()

    csv_file = ...
    image_dir = ...

    response = client.post("/manual-test", data={...})
    page = response.get_data(as_text=True)
    assert "成交金额" in page
    assert "命中原因" not in page
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_message_builder.py::test_message_builder_hides_match_reason_and_renames_total_amount_label tests/test_message_builder.py::test_message_builder_uses_compact_preset_heading tests/test_web_app.py::test_manual_test_page_uses_saved_global_format_settings -v
```

Expected:

- FAIL because `build_markdown_v2_message` does not accept format settings yet

- [ ] **Step 3: Write the minimal implementation**

```python
from wecom_sales_webhook_bot.format_settings import DEFAULT_FORMAT_SETTINGS, SUPPORTED_PRESETS, normalize_format_settings
```

```python
def build_markdown_v2_message(
    order: SalesOrder,
    filter_result: FilterResult,
    image_urls: dict[str, str],
    max_images: int,
    max_bytes: int = 4096,
    format_settings: dict | None = None,
) -> str:
    settings = normalize_format_settings(format_settings)
    preset = SUPPORTED_PRESETS[settings["preset"]]
    fields = settings["fields"]
```

```python
summary_lines = []
if fields["order_no"]["enabled"]:
    summary_lines.append(f"> **{fields['order_no']['label']}**：`{order.order_no}`")
if fields["store_name"]["enabled"]:
    summary_lines.append(f"> **{fields['store_name']['label']}**：`{order.store_name}`")
if fields["sold_at"]["enabled"]:
    summary_lines.append(f"> **{fields['sold_at']['label']}**：`{order.sold_at:%Y-%m-%d %H:%M:%S}`")
if fields["total_amount"]["enabled"]:
    summary_lines.append(f"> **{fields['total_amount']['label']}**：`{order.total_amount:.2f}`")
if fields["match_reason"]["enabled"]:
    summary_lines.append(f"> **{fields['match_reason']['label']}**：`{_format_reason(filter_result.reason)}`")

header = ["# 零售晒单"]
if preset["show_summary_heading"]:
    header.append(f"## {preset['summary_heading']}")
header.extend(summary_lines)
header.extend(["", f"**{preset['item_heading']}**"])
```

```python
block = []
if fields["style_no"]["enabled"]:
    block.append(f"- **{fields['style_no']['label']}**：`{item.style_no}`")
if fields["unit_price"]["enabled"]:
    block.append(f"  {fields['unit_price']['label']}：`{item.unit_price:.2f}`")
if fields["barcode"]["enabled"]:
    block.append(f"  {fields['barcode']['label']}：`{item.barcode}`")
if item.brand and fields["brand"]["enabled"]:
    block.append(f"  {fields['brand']['label']}：`{item.brand}`")
if item.category and fields["category"]["enabled"]:
    block.append(f"  {fields['category']['label']}：`{item.category}`")
if fields["image"]["enabled"]:
    ...
```

```python
with session_factory() as session:
    settings = _load_message_format_settings(session)
...
result = _run_manual_test(request.form, project_root, settings)
```

```python
def _run_manual_test(form, project_root: Path, format_settings: dict) -> dict[str, object]:
    ...
    return {
        "completed": True,
        "sent_count": len(sent_orders),
        "sent_orders": sent_orders,
        "messages": webhook_client.messages,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_message_builder.py::test_message_builder_hides_match_reason_and_renames_total_amount_label tests/test_message_builder.py::test_message_builder_uses_compact_preset_heading tests/test_web_app.py::test_manual_test_page_uses_saved_global_format_settings -v
```

Expected:

- PASS with `3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/wecom_sales_webhook_bot/message_builder.py src/wecom_sales_webhook_bot/web_app.py tests/test_message_builder.py tests/test_web_app.py
git commit -m "feat: apply global format settings to messages"
```

### Task 5: Run End-To-End Regression For Rule Actions And Format Management

**Files:**
- Verify existing implementation files from Tasks 1-4
- Reuse: `tests/test_db_models.py`
- Reuse: `tests/test_message_builder.py`
- Reuse: `tests/test_web_app.py`

- [ ] **Step 1: Run targeted regression tests**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_db_models.py tests/test_message_builder.py tests/test_web_app.py -v
```

Expected:

- PASS with all targeted tests green

- [ ] **Step 2: Run the broader CSV and orchestrator regression slice**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_csv_source.py tests/test_orchestrator.py tests/test_real_data_compat.py tests/test_web_app.py tests/test_message_builder.py -v
```

Expected:

- PASS with the UI, manual preview, CSV compatibility, and message rendering tests green

- [ ] **Step 3: Commit the verified integration state**

```bash
git add src/wecom_sales_webhook_bot/rule_models.py src/wecom_sales_webhook_bot/format_settings.py src/wecom_sales_webhook_bot/web_app.py src/wecom_sales_webhook_bot/message_builder.py src/wecom_sales_webhook_bot/templates/base.html src/wecom_sales_webhook_bot/templates/rules.html src/wecom_sales_webhook_bot/templates/format_settings.html tests/test_db_models.py tests/test_message_builder.py tests/test_web_app.py
git commit -m "feat: add rule actions and global message format management"
```

## Self-Review

### Spec Coverage

- 规则支持停用、恢复、硬删除: covered by Task 2
- 删除同时移除关联条件: covered by Task 2
- 新增全局格式管理页: covered by Task 3
- 格式管理支持词条开关、显示名称、模板预设: covered by Tasks 1, 3, and 4
- 正式推送和手动测试预览共用同一格式配置: covered by Task 4
- 不做自由模板编辑: enforced by `SUPPORTED_PRESETS` in Task 1 and structured rendering in Task 4

### Placeholder Scan

- No `TODO`, `TBD`, or deferred implementation placeholders remain in the tasks.
- Each task includes concrete file paths, test code, implementation snippets, commands, and expected outcomes.

### Type Consistency

- Global settings use one consistent model name: `GlobalSetting`
- Global format config uses one consistent loader/normalizer path: `normalize_format_settings`
- Preset ids stay consistent across plan steps: `standard`, `compact`, `detailed`
- Rule action routes stay consistent across plan steps: `/rules/<int:rule_id>/disable`, `/rules/<int:rule_id>/enable`, `/rules/<int:rule_id>/delete`
