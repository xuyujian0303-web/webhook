# WeCom Global Markdown Template Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current field-toggle format management with one global `markdown_v2` template editor, built-in preset templates, fixed sample preview, and one shared rendering path for preview and real delivery.

**Architecture:** Introduce a small template subsystem with four focused modules: preset defaults, schema allowlist, rendering engine, and persistence or preview service. Keep `web_app.py` responsible for routes and form handling, and convert `message_builder.py` from hardcoded markdown assembly into a context-preparation layer that delegates to the template engine.

**Tech Stack:** Python 3.12, Flask, Jinja2, SQLAlchemy, pytest

---

## Planned File Structure

**Create**

- `src/wecom_sales_webhook_bot/message_template_defaults.py`
- `src/wecom_sales_webhook_bot/message_template_schema.py`
- `src/wecom_sales_webhook_bot/message_template_engine.py`
- `src/wecom_sales_webhook_bot/message_template_service.py`
- `tests/test_message_template_engine.py`
- `tests/test_message_template_service.py`

**Modify**

- `src/wecom_sales_webhook_bot/message_builder.py`
- `src/wecom_sales_webhook_bot/orchestrator.py`
- `src/wecom_sales_webhook_bot/job_runner.py`
- `src/wecom_sales_webhook_bot/web_app.py`
- `src/wecom_sales_webhook_bot/templates/format_settings.html`
- `tests/test_web_app.py`
- `tests/test_message_builder.py`
- `tests/test_orchestrator.py`

**Responsibilities**

- `message_template_defaults.py`: built-in preset names, labels, and template bodies
- `message_template_schema.py`: allowed variables, filters, and workspace reference metadata
- `message_template_engine.py`: parse placeholders, validate template syntax, apply filters, render output, report byte length
- `message_template_service.py`: load or initialize the saved global template, save validated template payload, build fixed preview sample data
- `message_builder.py`: prepare order context and `items_markdown`, then call the template engine
- `web_app.py`: replace the old field-toggle page with the template workspace, handle preset load, save, restore, and preview
- `format_settings.html`: render the new template editor workspace instead of field toggles
- tests: cover engine behavior, service persistence, page workflow, and push pipeline integration

### Task 1: Add Template Defaults, Schema, And Rendering Engine

**Files:**
- Create: `src/wecom_sales_webhook_bot/message_template_defaults.py`
- Create: `src/wecom_sales_webhook_bot/message_template_schema.py`
- Create: `src/wecom_sales_webhook_bot/message_template_engine.py`
- Create: `tests/test_message_template_engine.py`

- [ ] **Step 1: Write the failing tests**

```python
from datetime import datetime

import pytest

from wecom_sales_webhook_bot.message_template_engine import (
    TemplateRenderError,
    render_message_template,
    validate_message_template,
)


def _sample_context() -> dict:
    return {
        "order": {
            "order_no": "SO-100",
            "store_name": "G609",
            "sold_at": datetime(2026, 6, 5, 10, 50, 0),
            "total_amount": 21500,
            "match_reason": "高金额命中",
        },
        "items_markdown": "- **款号**：`DRCH042ABK0`",
    }


def test_render_message_template_applies_allowed_filters() -> None:
    rendered = render_message_template(
        "# 零售晒单\n> {{ order.sold_at | datetime }}\n> {{ order.total_amount | money }}",
        _sample_context(),
    )

    assert "2026-06-05 10:50:00" in rendered.text
    assert "21500.00" in rendered.text
    assert rendered.byte_length == len(rendered.text.encode("utf-8"))


def test_render_message_template_inserts_items_markdown() -> None:
    rendered = render_message_template("{{ items_markdown }}", _sample_context())

    assert rendered.text == "- **款号**：`DRCH042ABK0`"


def test_validate_message_template_rejects_unknown_variable() -> None:
    errors = validate_message_template("{{ order.unknown_field }}")

    assert errors == ["unknown variable: order.unknown_field"]


def test_validate_message_template_rejects_unknown_filter() -> None:
    errors = validate_message_template("{{ order.total_amount | weird }}")

    assert errors == ["unknown filter: weird"]


def test_render_message_template_raises_on_invalid_template() -> None:
    with pytest.raises(TemplateRenderError) as exc_info:
        render_message_template("{{ order.total_amount | weird }}", _sample_context())

    assert "unknown filter" in str(exc_info.value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_message_template_engine.py -v
```

Expected:

- FAIL because the template modules and render functions do not exist yet

- [ ] **Step 3: Write the minimal preset defaults**

```python
STANDARD_TEMPLATE = """# 零售晒单
## 成交摘要
> **销售单号**：`{{ order.order_no }}`
> **门店**：`{{ order.store_name }}`
> **时间**：`{{ order.sold_at | datetime }}`
> **总金额**：`{{ order.total_amount | money }}`
> **命中原因**：`{{ order.match_reason }}`

{{ items_markdown }}
"""

COMPACT_TEMPLATE = """# 零售晒单
> **销售单号**：`{{ order.order_no }}`
> **门店**：`{{ order.store_name }}`
> **总金额**：`{{ order.total_amount | money }}`

{{ items_markdown }}
"""

DETAILED_TEMPLATE = """# 零售晒单
## 订单摘要
> **销售单号**：`{{ order.order_no }}`
> **门店**：`{{ order.store_name }}`
> **时间**：`{{ order.sold_at | datetime }}`
> **总金额**：`{{ order.total_amount | money }}`
> **命中原因**：`{{ order.match_reason }}`

## 商品明细
{{ items_markdown }}
"""

PRESET_TEMPLATES = {
    "standard": {"label": "标准版", "body": STANDARD_TEMPLATE},
    "compact": {"label": "精简版", "body": COMPACT_TEMPLATE},
    "detailed": {"label": "明细版", "body": DETAILED_TEMPLATE},
}
```

- [ ] **Step 4: Write the minimal schema allowlist**

```python
ALLOWED_VARIABLES = {
    "order.order_no",
    "order.store_name",
    "order.sold_at",
    "order.total_amount",
    "order.match_reason",
    "items_markdown",
}

ALLOWED_FILTERS = {"money", "datetime"}

REFERENCE_VARIABLES = [
    {"token": "order.order_no", "label": "销售单号"},
    {"token": "order.store_name", "label": "门店"},
    {"token": "order.sold_at", "label": "成交时间"},
    {"token": "order.total_amount", "label": "总金额"},
    {"token": "order.match_reason", "label": "命中原因"},
    {"token": "items_markdown", "label": "商品明细块"},
]
```

- [ ] **Step 5: Write the minimal template engine**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

from wecom_sales_webhook_bot.message_template_schema import ALLOWED_FILTERS, ALLOWED_VARIABLES


TOKEN_RE = re.compile(r"\{\{\s*(.+?)\s*\}\}")


@dataclass(frozen=True)
class RenderedTemplate:
    text: str
    byte_length: int


class TemplateRenderError(ValueError):
    pass


def validate_message_template(template_body: str) -> list[str]:
    errors: list[str] = []
    for raw_token in TOKEN_RE.findall(template_body):
        parts = [part.strip() for part in raw_token.split("|")]
        variable = parts[0]
        if variable not in ALLOWED_VARIABLES:
            errors.append(f"unknown variable: {variable}")
            continue
        for filter_name in parts[1:]:
            if filter_name not in ALLOWED_FILTERS:
                errors.append(f"unknown filter: {filter_name}")
    return errors


def _resolve_variable(token: str, context: dict) -> object:
    if token == "items_markdown":
        return context["items_markdown"]
    _, field_name = token.split(".", 1)
    return context["order"][field_name]


def _apply_filter(value: object, filter_name: str) -> str:
    if filter_name == "money":
        return f"{float(value):.2f}"
    if filter_name == "datetime":
        return value.strftime("%Y-%m-%d %H:%M:%S")
    raise TemplateRenderError(f"unknown filter: {filter_name}")


def render_message_template(template_body: str, context: dict) -> RenderedTemplate:
    errors = validate_message_template(template_body)
    if errors:
        raise TemplateRenderError("; ".join(errors))

    def replace(match: re.Match[str]) -> str:
        parts = [part.strip() for part in match.group(1).split("|")]
        value = _resolve_variable(parts[0], context)
        rendered = value
        for filter_name in parts[1:]:
            rendered = _apply_filter(rendered, filter_name)
        return str(rendered)

    text = TOKEN_RE.sub(replace, template_body)
    return RenderedTemplate(text=text, byte_length=len(text.encode("utf-8")))
```

- [ ] **Step 6: Run tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_message_template_engine.py -v
```

Expected:

- PASS with `5 passed`

- [ ] **Step 7: Commit**

```bash
git add src/wecom_sales_webhook_bot/message_template_defaults.py src/wecom_sales_webhook_bot/message_template_schema.py src/wecom_sales_webhook_bot/message_template_engine.py tests/test_message_template_engine.py
git commit -m "feat: add markdown message template engine"
```

### Task 2: Add Template Persistence And Preview Sample Service

**Files:**
- Create: `src/wecom_sales_webhook_bot/message_template_service.py`
- Create: `tests/test_message_template_service.py`
- Modify: `src/wecom_sales_webhook_bot/rule_models.py`

- [ ] **Step 1: Write the failing tests**

```python
from datetime import datetime

from wecom_sales_webhook_bot.db import create_session_factory, initialize_database
from wecom_sales_webhook_bot.message_template_service import (
    DEFAULT_TEMPLATE_NAME,
    build_preview_template_context,
    load_or_initialize_message_template,
    save_message_template,
)


def test_load_or_initialize_message_template_creates_default_row(tmp_path) -> None:
    session_factory = create_session_factory(f"sqlite:///{tmp_path / 'app.db'}")
    initialize_database(session_factory)

    with session_factory() as session:
        template = load_or_initialize_message_template(session)

    assert template["template_name"] == DEFAULT_TEMPLATE_NAME
    assert template["preset_key"] == "standard"
    assert "{{ order.order_no }}" in template["template_body"]


def test_save_message_template_updates_existing_row(tmp_path) -> None:
    session_factory = create_session_factory(f"sqlite:///{tmp_path / 'app.db'}")
    initialize_database(session_factory)

    with session_factory() as session:
        load_or_initialize_message_template(session)
        saved = save_message_template(
            session,
            template_name="自定义模板",
            template_body="# 标题\n{{ items_markdown }}",
            preset_key="compact",
        )

    assert saved["template_name"] == "自定义模板"
    assert saved["preset_key"] == "compact"


def test_build_preview_template_context_returns_fixed_sample_data() -> None:
    context = build_preview_template_context()

    assert context["order"]["order_no"] == "SOG609260605001"
    assert "DRCH042ABK0" in context["items_markdown"]
    assert "http://127.0.0.1:8123/DRCH042ABK0.png" in context["items_markdown"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_message_template_service.py -v
```

Expected:

- FAIL because the template service does not exist yet

- [ ] **Step 3: Write the minimal service implementation**

```python
from __future__ import annotations

import json

from wecom_sales_webhook_bot.message_template_defaults import PRESET_TEMPLATES
from wecom_sales_webhook_bot.rule_models import GlobalSetting


DEFAULT_TEMPLATE_NAME = "自定义模板"
TEMPLATE_SETTING_KEY = "message_template"


def _default_template_payload() -> dict:
    return {
        "template_name": DEFAULT_TEMPLATE_NAME,
        "template_body": PRESET_TEMPLATES["standard"]["body"],
        "preset_key": "standard",
    }


def load_or_initialize_message_template(session) -> dict:
    row = session.query(GlobalSetting).filter_by(setting_key=TEMPLATE_SETTING_KEY).one_or_none()
    if row is None:
        payload = _default_template_payload()
        session.add(
            GlobalSetting(
                setting_key=TEMPLATE_SETTING_KEY,
                setting_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            )
        )
        session.commit()
        return payload
    return json.loads(row.setting_json)


def save_message_template(session, *, template_name: str, template_body: str, preset_key: str) -> dict:
    payload = {
        "template_name": template_name.strip() or DEFAULT_TEMPLATE_NAME,
        "template_body": template_body,
        "preset_key": preset_key,
    }
    row = session.query(GlobalSetting).filter_by(setting_key=TEMPLATE_SETTING_KEY).one_or_none()
    if row is None:
        session.add(
            GlobalSetting(
                setting_key=TEMPLATE_SETTING_KEY,
                setting_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            )
        )
    else:
        row.setting_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    session.commit()
    return payload


def build_preview_template_context() -> dict:
    return {
        "order": {
            "order_no": "SOG609260605001",
            "store_name": "G609",
            "sold_at": datetime(2026, 6, 5, 10, 50, 0),
            "total_amount": 21500,
            "match_reason": "高金额命中",
        },
        "items_markdown": "\n".join(
            [
                "- **款号**：`DRCH042ABK0`",
                "  单价：`14500.00`",
                "  条码：`GDRCH042ACBK0B6360009`",
                "  ![](http://127.0.0.1:8123/DRCH042ABK0.png)",
            ]
        ),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_message_template_service.py -v
```

Expected:

- PASS with `3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/wecom_sales_webhook_bot/message_template_service.py tests/test_message_template_service.py
git commit -m "feat: add global message template persistence"
```

### Task 3: Refactor Message Builder To Use The Template Engine

**Files:**
- Modify: `src/wecom_sales_webhook_bot/message_builder.py`
- Modify: `src/wecom_sales_webhook_bot/orchestrator.py`
- Modify: `src/wecom_sales_webhook_bot/job_runner.py`
- Modify: `tests/test_message_builder.py`
- Modify: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing tests**

```python
from datetime import datetime

from wecom_sales_webhook_bot.filters import FilterResult
from wecom_sales_webhook_bot.message_builder import build_markdown_v2_message
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder


def test_message_builder_renders_saved_template_body() -> None:
    order = SalesOrder(
        order_no="SO-300",
        sold_at=datetime(2026, 6, 5, 10, 50, 0),
        store_name="G609",
        total_amount=21500,
        items=[SalesLineItem(barcode="B1", style_no="S1", unit_price=21500)],
    )

    message = build_markdown_v2_message(
        order=order,
        filter_result=FilterResult(matched=True, reason="amount_threshold"),
        image_urls={},
        max_images=8,
        template_body="# 模板测试\n> {{ order.order_no }}\n{{ items_markdown }}",
    )

    assert "# 模板测试" in message
    assert "> SO-300" in message
    assert "S1" in message


def test_run_once_uses_saved_template_body(tmp_path) -> None:
    ...
    assert webhook_client.messages[0].startswith("# 模板测试")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_message_builder.py tests/test_orchestrator.py -k template -v
```

Expected:

- FAIL because `build_markdown_v2_message` does not accept `template_body`

- [ ] **Step 3: Write the minimal message-builder refactor**

```python
def _build_items_markdown(order: SalesOrder, image_urls: dict[str, str], max_images: int) -> str:
    ...


def build_markdown_v2_message(
    order: SalesOrder,
    filter_result: FilterResult,
    image_urls: dict[str, str],
    max_images: int,
    max_bytes: int = 4096,
    template_body: str | None = None,
) -> str:
    if max_images < 0:
        raise ValueError("max_images must be >= 0")
    if max_bytes < 0:
        raise ValueError("max_bytes must be >= 0")

    if template_body is None:
        template_body = PRESET_TEMPLATES["standard"]["body"]

    context = {
        "order": {
            "order_no": order.order_no,
            "store_name": order.store_name,
            "sold_at": order.sold_at,
            "total_amount": order.total_amount,
            "match_reason": _format_reason(filter_result.reason),
        },
        "items_markdown": _build_items_markdown(order, image_urls, max_images),
    }
    rendered = render_message_template(template_body, context)
    if rendered.byte_length <= max_bytes:
        return rendered.text
    return _trim_lines_to_max_bytes(rendered.text.splitlines(), max_bytes)
```

- [ ] **Step 4: Thread the template body through orchestrator and job runner**

```python
def run_once(..., template_body: str | None = None) -> list[str]:
    ...
    content = build_markdown_v2_message(
        order=order,
        filter_result=filter_result,
        image_urls=image_urls,
        max_images=max_images,
        template_body=template_body,
    )
```

```python
message = build_markdown_v2_message(
    order=order,
    filter_result=FilterResult(matched=True, reason="rule_group"),
    image_urls={},
    max_images=max_images,
    template_body=template_body,
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_message_builder.py tests/test_orchestrator.py -k template -v
```

Expected:

- PASS for the new template-focused tests

- [ ] **Step 6: Commit**

```bash
git add src/wecom_sales_webhook_bot/message_builder.py src/wecom_sales_webhook_bot/orchestrator.py src/wecom_sales_webhook_bot/job_runner.py tests/test_message_builder.py tests/test_orchestrator.py
git commit -m "refactor: route message generation through template engine"
```

### Task 4: Replace Format Management With Template Workspace

**Files:**
- Modify: `src/wecom_sales_webhook_bot/web_app.py`
- Modify: `src/wecom_sales_webhook_bot/templates/format_settings.html`
- Modify: `tests/test_web_app.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_template_workspace_loads_saved_template_after_login() -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)

    response = client.get("/format-settings")

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "消息模板管理" in page
    assert "加载预设" in page
    assert "保存模板" in page
    assert "{{ order.order_no }}" in page


def test_template_workspace_can_load_preset_without_persisting() -> None:
    ...
    assert "## 商品明细" in page
    with session_factory() as session:
        row = session.query(GlobalSetting).filter_by(setting_key="message_template").one()
        assert "## 商品明细" not in row.setting_json


def test_template_workspace_save_persists_template_and_preview() -> None:
    ...
    assert "# 新模板" in page
    assert "SO-100" in page or "SOG609260605001" in page
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_web_app.py -k template_workspace -v
```

Expected:

- FAIL because the page still renders field toggles instead of a template workspace

- [ ] **Step 3: Write the minimal route and form helpers**

```python
def _preset_options() -> list[dict[str, str]]:
    return [
        {"key": key, "label": config["label"]}
        for key, config in PRESET_TEMPLATES.items()
    ]


def _template_form_payload(form) -> dict[str, str]:
    return {
        "template_name": form.get("template_name", "").strip(),
        "template_body": form.get("template_body", ""),
        "preset_key": form.get("preset_key", "standard"),
    }
```

```python
@app.get("/format-settings")
@login_required
def format_settings_page():
    with session_factory() as session:
        saved = load_or_initialize_message_template(session)
    preview = render_message_template(saved["template_body"], build_preview_template_context())
    return render_template(
        "format_settings.html",
        **_page_context(
            active_nav="format_settings",
            page_title="消息模板管理",
            template_state=saved,
            preset_options=_preset_options(),
            preview_text=preview.text,
            preview_bytes=preview.byte_length,
            save_message=None,
            errors=[],
            reference_variables=REFERENCE_VARIABLES,
        ),
    )
```

- [ ] **Step 4: Add POST actions for preset load, save, and restore**

```python
@app.post("/format-settings")
@login_required
def format_settings_submit():
    action = request.form.get("action", "preview")
    payload = _template_form_payload(request.form)

    with session_factory() as session:
        saved = load_or_initialize_message_template(session)

        if action == "load_preset":
            preset = PRESET_TEMPLATES[payload["preset_key"]]
            payload["template_body"] = preset["body"]
            payload["template_name"] = preset["label"]
        elif action == "restore":
            payload = saved
        elif action == "save":
            errors = validate_message_template(payload["template_body"])
            if not errors:
                payload = save_message_template(session, **payload)

    preview = render_message_template(payload["template_body"], build_preview_template_context())
    return render_template(...)
```

- [ ] **Step 5: Replace the template file with the workspace layout**

```html
<section class="panel">
  <div class="page-header">
    <h1 class="page-title">消息模板管理</h1>
    <p class="page-copy">编辑一份全局 markdown_v2 模板，预览与正式推送共用同一渲染链路。</p>
  </div>
  <form method="post" action="/format-settings">
    <div class="action-row">
      <select name="preset_key">...</select>
      <button name="action" value="load_preset" type="submit">加载预设</button>
      <button name="action" value="save" type="submit">保存模板</button>
      <button name="action" value="restore" type="submit">恢复已保存版本</button>
    </div>
    <div class="form-grid">
      <section class="form-section">
        <label for="template_name">模板名称</label>
        <input id="template_name" name="template_name" value="{{ template_state.template_name }}" />
        <label for="template_body">模板正文</label>
        <textarea id="template_body" name="template_body">{{ template_state.template_body }}</textarea>
      </section>
      <section class="form-section">
        <h2>预览</h2>
        <pre>{{ preview_text }}</pre>
        <p>字节数：{{ preview_bytes }}</p>
      </section>
    </div>
  </form>
</section>
```

- [ ] **Step 6: Run tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_web_app.py -k template_workspace -v
```

Expected:

- PASS for the new template workspace tests

- [ ] **Step 7: Commit**

```bash
git add src/wecom_sales_webhook_bot/web_app.py src/wecom_sales_webhook_bot/templates/format_settings.html tests/test_web_app.py
git commit -m "feat: replace format settings with template workspace"
```

### Task 5: Switch Manual Test And Real Delivery To Saved Templates

**Files:**
- Modify: `src/wecom_sales_webhook_bot/web_app.py`
- Modify: `src/wecom_sales_webhook_bot/job_runner.py`
- Modify: `tests/test_web_app.py`
- Modify: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_manual_test_page_uses_saved_message_template(tmp_path: Path) -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)
    ...
    with session_factory() as session:
        save_message_template(
            session,
            template_name="手测模板",
            template_body="# 手测模板\n{{ items_markdown }}",
            preset_key="compact",
        )
    ...
    assert "# 手测模板" in page


def test_job_runner_uses_saved_message_template() -> None:
    ...
    assert webhook_client.messages[0].startswith("# 手测模板")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_web_app.py tests/test_orchestrator.py -k saved_message_template -v
```

Expected:

- FAIL because manual test and job runner still use old default behavior

- [ ] **Step 3: Read the saved template before manual test preview**

```python
with session_factory() as session:
    saved_template = load_or_initialize_message_template(session)

result = _run_manual_test(
    request.form,
    project_root,
    template_body=saved_template["template_body"],
)
```

```python
def _run_manual_test(form, project_root: Path, template_body: str | None = None) -> dict[str, object]:
    ...
    sent_orders = run_once(
        ...,
        template_body=template_body,
    )
```

- [ ] **Step 4: Thread the saved template into the real push path**

```python
with session_factory() as session:
    saved_template = load_or_initialize_message_template(session)

message = build_markdown_v2_message(
    order=order,
    filter_result=FilterResult(matched=True, reason="rule_group"),
    image_urls={},
    max_images=max_images,
    template_body=saved_template["template_body"],
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_web_app.py tests/test_orchestrator.py -k saved_message_template -v
```

Expected:

- PASS for the saved-template integration tests

- [ ] **Step 6: Commit**

```bash
git add src/wecom_sales_webhook_bot/web_app.py src/wecom_sales_webhook_bot/job_runner.py tests/test_web_app.py tests/test_orchestrator.py
git commit -m "feat: use saved markdown template in preview and push flows"
```

### Task 6: Regression, Cleanup, And Verification

**Files:**
- Modify: `tests/test_message_builder.py`
- Modify: `tests/test_web_app.py`
- Modify: `tests/test_orchestrator.py`
- Modify: `tests/test_db_models.py`

- [ ] **Step 1: Add regression coverage for backward-compatible default initialization**

```python
def test_format_page_initializes_standard_template_when_missing() -> None:
    app = _build_app()
    client = app.test_client()
    _login(client)

    response = client.get("/format-settings")

    page = response.get_data(as_text=True)
    assert "标准版" in page
    assert "{{ order.order_no }}" in page
```

- [ ] **Step 2: Run the full affected test suite**

Run:

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests/test_db_models.py tests/test_message_template_engine.py tests/test_message_template_service.py tests/test_message_builder.py tests/test_web_app.py tests/test_orchestrator.py tests/test_real_data_compat.py -v
```

Expected:

- PASS across the full affected suite

- [ ] **Step 3: Do a manual smoke check**

Run:

```powershell
cd C:\Users\x\wecom-sales-webhook-bot\.worktrees\wecom-bot-impl
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -u -m wecom_sales_webhook_bot.cli run-server --config config.yaml
```

Then verify:

- `http://127.0.0.1:5000/format-settings` opens the template workspace
- loading each preset updates the editor and preview
- saving a custom template persists after refresh
- manual test preview uses the saved template body

- [ ] **Step 4: Commit**

```bash
git add tests/test_db_models.py tests/test_message_builder.py tests/test_web_app.py tests/test_orchestrator.py
git commit -m "test: cover markdown template workflow regression"
```

## Self-Review

- Spec coverage: defaults, schema, engine, single saved template, preset loading, preview sample, workspace UI, shared rendering path, and migration-compatible initialization each have at least one dedicated task.
- Placeholder scan: each task includes concrete file paths, code snippets, commands, and expected outcomes; no `TODO` or deferred “handle appropriately” language remains.
- Type consistency: the plan uses one naming set consistently: `template_body`, `template_name`, `preset_key`, `render_message_template`, `validate_message_template`, `load_or_initialize_message_template`, and `save_message_template`.
