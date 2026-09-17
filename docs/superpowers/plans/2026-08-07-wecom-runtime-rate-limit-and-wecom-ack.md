# WeCom Runtime Rate Limit And Ack Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable push pacing and strict WeCom webhook acknowledgement validation so scheduled scans can send matched orders safely without silently dropping messages.

**Architecture:** Keep runtime controls in the existing app database and admin page, extend them with `push_interval_seconds`, and let the scheduler honor the value between successful sends. Tighten the webhook client so only HTTP success plus `errcode == 0` counts as a successful push; otherwise the order must not be written into push state.

**Tech Stack:** Python, Flask, SQLAlchemy, pytest, requests

---

### Task 1: Extend Runtime Controls Persistence

**Files:**
- Modify: `src/wecom_sales_webhook_bot/runtime_settings.py`
- Test: `tests/test_runtime_settings.py`

- [ ] **Step 1: Write the failing test**

```python
def test_save_runtime_controls_persists_push_interval_seconds(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    session_factory = create_session_factory(database_url)
    initialize_database(session_factory)

    with session_factory() as session:
        save_runtime_controls(
            session,
            scan_interval_seconds=300,
            max_images_per_message=5,
            push_interval_seconds=10,
        )

    loaded = load_runtime_controls(
        database_url,
        RuntimeControls(
            scan_interval_seconds=1200,
            max_images_per_message=8,
            push_interval_seconds=0,
        ),
    )

    assert loaded.push_interval_seconds == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_runtime_settings.py::test_save_runtime_controls_persists_push_interval_seconds -v`
Expected: FAIL because `RuntimeControls` and `save_runtime_controls` do not support `push_interval_seconds` yet.

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass(frozen=True)
class RuntimeControls:
    scan_interval_seconds: int
    max_images_per_message: int
    push_interval_seconds: int
```

```python
push_interval_seconds = int(
    payload.get("push_interval_seconds", defaults.push_interval_seconds)
)
if push_interval_seconds < 0:
    raise ValueError("push_interval_seconds must be >= 0")
```

```python
save_runtime_controls(
    session,
    scan_interval_seconds=scan_interval_seconds,
    max_images_per_message=max_images_per_message,
    push_interval_seconds=push_interval_seconds,
    defaults=defaults,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_runtime_settings.py::test_save_runtime_controls_persists_push_interval_seconds -v`
Expected: PASS

### Task 2: Expose Push Interval In Admin Runtime Settings

**Files:**
- Modify: `src/wecom_sales_webhook_bot/web_app.py`
- Modify: `src/wecom_sales_webhook_bot/templates/runtime_settings.html`
- Test: `tests/test_web_app.py`

- [ ] **Step 1: Write the failing test**

```python
def test_runtime_settings_page_saves_push_interval_seconds(client, session_factory) -> None:
    response = client.post(
        "/runtime-settings",
        data={
            "scan_interval_seconds": "3600",
            "max_images_per_message": "8",
            "push_interval_seconds": "10",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    with session_factory() as session:
        controls = load_or_initialize_runtime_controls(
            session,
            RuntimeControls(
                scan_interval_seconds=1200,
                max_images_per_message=8,
                push_interval_seconds=0,
            ),
        )
    assert controls.push_interval_seconds == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_app.py::test_runtime_settings_page_saves_push_interval_seconds -v`
Expected: FAIL because the form and handler do not read or persist `push_interval_seconds`.

- [ ] **Step 3: Write minimal implementation**

```python
def _runtime_controls_form_data(controls: RuntimeControls) -> dict[str, str]:
    return {
        "scan_interval_seconds": str(controls.scan_interval_seconds),
        "max_images_per_message": str(controls.max_images_per_message),
        "push_interval_seconds": str(controls.push_interval_seconds),
    }
```

```python
push_interval_seconds = int(request.form.get("push_interval_seconds", "").strip())
controls = save_runtime_controls(
    session,
    scan_interval_seconds=scan_interval_seconds,
    max_images_per_message=max_images_per_message,
    push_interval_seconds=push_interval_seconds,
    defaults=defaults,
)
```

```html
<label for="push_interval_seconds">推送间隔（秒）</label>
<input id="push_interval_seconds" name="push_interval_seconds" type="number" min="0" value="{{ form_data.push_interval_seconds }}" />
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_app.py::test_runtime_settings_page_saves_push_interval_seconds -v`
Expected: PASS

### Task 3: Pace Sends Between Matched Orders

**Files:**
- Modify: `src/wecom_sales_webhook_bot/orchestrator.py`
- Modify: `src/wecom_sales_webhook_bot/cli.py`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

```python
def test_run_once_waits_between_multiple_messages(tmp_path: Path) -> None:
    sleep_calls: list[int] = []
    client = FakeClient()

    sent = run_once(
        data_source=TwoOrderDataSource(),
        sales_filter=FakeFilter(),
        image_provider=FakeImageProvider(),
        state_file=tmp_path / "state.json",
        webhook_client=client,
        max_images=8,
        dry_run=False,
        push_interval_seconds=10,
        sleep_func=sleep_calls.append,
    )

    assert sent == ["SO-001", "SO-002"]
    assert sleep_calls == [10]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_orchestrator.py::test_run_once_waits_between_multiple_messages -v`
Expected: FAIL because `run_once` does not accept pacing parameters and never sleeps between sends.

- [ ] **Step 3: Write minimal implementation**

```python
def run_once(..., push_interval_seconds: int = 0, sleep_func=time.sleep) -> list[str]:
    ...
    if not dry_run:
        webhook_client.send_markdown_v2(content)
    state_store.mark_pushed(order.order_no, order.sold_at)
    sent_orders.append(order.order_no)
    if push_interval_seconds > 0 and index < len(orders_to_send) - 1:
        sleep_func(push_interval_seconds)
```

```python
run_once(
    ...,
    push_interval_seconds=runtime_controls.push_interval_seconds,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_orchestrator.py::test_run_once_waits_between_multiple_messages -v`
Expected: PASS

### Task 4: Validate WeCom JSON Ack Before Marking Success

**Files:**
- Modify: `src/wecom_sales_webhook_bot/wecom_client.py`
- Modify: `src/wecom_sales_webhook_bot/orchestrator.py`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_wecom_client_raises_when_errcode_is_non_zero() -> None:
    session = FakeSession(payload={"errcode": 93000, "errmsg": "rate limited"})
    client = WeComWebhookClient(
        webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_WEBHOOK_KEY",
        timeout_seconds=5,
        retry_times=0,
        session=session,
    )

    with pytest.raises(RuntimeError, match="93000"):
        client.send_markdown_v2("hello")
```

```python
def test_run_once_does_not_mark_state_when_send_fails(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"

    with pytest.raises(RuntimeError):
        run_once(
            data_source=FakeDataSource(),
            sales_filter=FakeFilter(),
            image_provider=FakeImageProvider(),
            state_file=state_file,
            webhook_client=FailingClient(),
            max_images=8,
            dry_run=False,
        )

    assert '"SO-001"' not in state_file.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_orchestrator.py::test_wecom_client_raises_when_errcode_is_non_zero tests/test_orchestrator.py::test_run_once_does_not_mark_state_when_send_fails -v`
Expected: FAIL because the client only checks HTTP status and the orchestrator currently assumes any non-exception send is success.

- [ ] **Step 3: Write minimal implementation**

```python
payload = response.json()
if payload.get("errcode") != 0:
    raise RuntimeError(
        f"WeCom webhook rejected message: errcode={payload.get('errcode')} errmsg={payload.get('errmsg')}"
    )
```

```python
if not dry_run:
    webhook_client.send_markdown_v2(content)
state_store.mark_pushed(order.order_no, order.sold_at)
```

Keep `mark_pushed` after the webhook call so failed sends never write state.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_orchestrator.py::test_wecom_client_raises_when_errcode_is_non_zero tests/test_orchestrator.py::test_run_once_does_not_mark_state_when_send_fails -v`
Expected: PASS

### Task 5: Run Focused Regression Verification

**Files:**
- Test: `tests/test_runtime_settings.py`
- Test: `tests/test_orchestrator.py`
- Test: `tests/test_web_app.py`

- [ ] **Step 1: Run focused runtime and orchestrator coverage**

Run: `pytest tests/test_runtime_settings.py tests/test_orchestrator.py tests/test_web_app.py -v`
Expected: PASS

- [ ] **Step 2: Run any directly affected additional slice if needed**

Run: `pytest tests/test_config.py -v`
Expected: PASS
