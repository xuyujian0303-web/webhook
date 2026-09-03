# WeCom Sales Webhook Bot Admin Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-process admin backend that lets internal users log in, maintain live push rules in a web UI, poll IT sales APIs on a schedule, and push matching sales orders to Enterprise WeChat webhook messages.

**Architecture:** Evolve the current CSV prototype into a Flask application that embeds four runtime concerns in one process: web admin UI, database persistence, scheduled scanning, and webhook pushing. Preserve the existing message rendering core where it still fits, but replace CSV and local image serving with database-backed rule/state storage and an IT API adapter that returns image URLs directly.

**Tech Stack:** Python 3.12, Flask, Flask-Login, SQLAlchemy, APScheduler, requests, PyYAML, pytest

---

## Planned File Structure

**Create**

- `src/wecom_sales_webhook_bot/db.py`
- `src/wecom_sales_webhook_bot/rule_models.py`
- `src/wecom_sales_webhook_bot/rule_service.py`
- `src/wecom_sales_webhook_bot/api_source.py`
- `src/wecom_sales_webhook_bot/auth.py`
- `src/wecom_sales_webhook_bot/web_app.py`
- `src/wecom_sales_webhook_bot/job_runner.py`
- `src/wecom_sales_webhook_bot/templates/base.html`
- `src/wecom_sales_webhook_bot/templates/login.html`
- `src/wecom_sales_webhook_bot/templates/rules.html`
- `src/wecom_sales_webhook_bot/templates/rule_edit.html`
- `src/wecom_sales_webhook_bot/templates/push_records.html`
- `src/wecom_sales_webhook_bot/templates/system_status.html`
- `tests/test_db_models.py`
- `tests/test_rule_service.py`
- `tests/test_api_source.py`
- `tests/test_auth.py`
- `tests/test_web_app.py`
- `tests/test_job_runner.py`

**Modify**

- `pyproject.toml`
- `README.md`
- `config.example.yaml`
- `src/wecom_sales_webhook_bot/config.py`
- `src/wecom_sales_webhook_bot/models.py`
- `src/wecom_sales_webhook_bot/message_builder.py`
- `src/wecom_sales_webhook_bot/wecom_client.py`
- `src/wecom_sales_webhook_bot/cli.py`

**Responsibilities**

- `config.py`: load both prototype config and formal backend config
- `models.py`: extend domain objects for brand, category, and remote image URL
- `db.py`: SQLAlchemy engine and session factory bootstrap
- `rule_models.py`: ORM models for users, rules, conditions, push records, and job runs
- `rule_service.py`: rule validation, persistence DTO conversion, and `any` / `all` matching
- `api_source.py`: IT sales API client and row-to-order grouping
- `auth.py`: password hashing and login user loading helpers
- `web_app.py`: Flask app factory, login routes, rule CRUD, records page, and status page
- `job_runner.py`: one scan cycle, DB-backed de-duplication, push logging, and APScheduler wiring
- `message_builder.py`: keep existing markdown_v2 layout but accept remote image URLs from data items
- `cli.py`: add backend server startup command

### Task 1: Add Backend Dependencies And Config Surface

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/wecom_sales_webhook_bot/config.py`
- Modify: `config.example.yaml`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from wecom_sales_webhook_bot.config import load_config


def test_load_config_reads_backend_database_auth_and_api_settings(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
wecom:
  webhook_url: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test
  timeout_seconds: 5
  retry_times: 2
runtime:
  scan_interval_seconds: 1200
  max_images_per_message: 8
  dry_run: false
backend:
  database_url: sqlite:///./var/app.db
  secret_key: test-secret
  host: 127.0.0.1
  port: 5000
  bootstrap_admin_username: admin
  bootstrap_admin_password: admin123
api:
  sales_base_url: https://internal.example.com
  sales_token: test-token
  sales_path: /sales/query
  timeout_seconds: 10
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.backend.database_url == "sqlite:///./var/app.db"
    assert config.backend.secret_key == "test-secret"
    assert config.backend.bootstrap_admin_username == "admin"
    assert config.api.sales_base_url == "https://internal.example.com"
    assert config.api.sales_path == "/sales/query"
    assert config.api.timeout_seconds == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py::test_load_config_reads_backend_database_auth_and_api_settings -v`
Expected: FAIL because backend and api config sections do not exist.

- [ ] **Step 3: Write minimal implementation**

```toml
[project]
dependencies = [
  "APScheduler>=3.10.4",
  "Flask>=3.0.3",
  "Flask-Login>=0.6.3",
  "PyYAML>=6.0.1",
  "SQLAlchemy>=2.0.36",
  "requests>=2.32.0",
]
```

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class BackendConfig:
    database_url: str
    secret_key: str
    host: str
    port: int
    bootstrap_admin_username: str
    bootstrap_admin_password: str


@dataclass(frozen=True)
class ApiConfig:
    sales_base_url: str
    sales_token: str
    sales_path: str
    timeout_seconds: int
```

```python
return AppConfig(
    wecom=WeComConfig(...),
    runtime=RuntimeConfig(...),
    backend=BackendConfig(
        database_url=raw["backend"]["database_url"],
        secret_key=raw["backend"]["secret_key"],
        host=raw["backend"]["host"],
        port=int(raw["backend"]["port"]),
        bootstrap_admin_username=raw["backend"]["bootstrap_admin_username"],
        bootstrap_admin_password=raw["backend"]["bootstrap_admin_password"],
    ),
    api=ApiConfig(
        sales_base_url=raw["api"]["sales_base_url"],
        sales_token=raw["api"]["sales_token"],
        sales_path=raw["api"]["sales_path"],
        timeout_seconds=int(raw["api"]["timeout_seconds"]),
    ),
)
```

```yaml
backend:
  database_url: sqlite:///./var/app.db
  secret_key: replace-me
  host: 0.0.0.0
  port: 5000
  bootstrap_admin_username: admin
  bootstrap_admin_password: change-me

api:
  sales_base_url: https://internal.example.com
  sales_token: replace-me
  sales_path: /sales/query
  timeout_seconds: 10
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py::test_load_config_reads_backend_database_auth_and_api_settings -v`
Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/wecom_sales_webhook_bot/config.py config.example.yaml tests/test_config.py
git commit -m "feat: add backend and api config"
```

### Task 2: Extend Domain Models For API Data And Remote Images

**Files:**
- Modify: `src/wecom_sales_webhook_bot/models.py`
- Modify: `src/wecom_sales_webhook_bot/message_builder.py`
- Test: `tests/test_message_builder.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime

from wecom_sales_webhook_bot.message_builder import build_markdown_v2_message
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder


def test_build_markdown_v2_message_uses_remote_image_urls_from_items() -> None:
    order = SalesOrder(
        order_no="SO-100",
        sold_at=datetime(2026, 4, 22, 11, 0, 0),
        store_name="G621",
        total_amount=19250,
        items=[
            SalesLineItem(
                barcode="GPA17047BCNY0B5420001",
                style_no="PA17047BNY0",
                unit_price=5850,
                brand="Brand-A",
                category="外套",
                image_url="https://img.example.com/p1.jpg",
            )
        ],
    )

    message = build_markdown_v2_message(order=order, max_images=8)

    assert "https://img.example.com/p1.jpg" in message
    assert "Brand-A" in message
    assert "外套" in message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_message_builder.py::test_build_markdown_v2_message_uses_remote_image_urls_from_items -v`
Expected: FAIL because `SalesLineItem` does not expose brand, category, or image_url.

- [ ] **Step 3: Write minimal implementation**

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SalesLineItem:
    barcode: str
    style_no: str
    unit_price: float
    quantity: int = 1
    brand: str | None = None
    category: str | None = None
    image_url: str | None = None
```

```python
def build_markdown_v2_message(order: SalesOrder, max_images: int) -> str:
    lines = [
        order.sold_at.strftime("%Y-%m-%d %H:%M"),
        f"店铺号：{order.store_name}",
        f"总单金额：{order.total_amount:.2f}",
        "",
        "商品清单：",
    ]
    image_count = 0
    for item in order.items:
        lines.append(f"- 款号：{item.style_no} | 吊牌价：{item.unit_price:.2f}")
        if item.brand:
            lines.append(f"  品牌：{item.brand}")
        if item.category:
            lines.append(f"  类别：{item.category}")
        if item.image_url and image_count < max_images:
            lines.append(item.image_url)
            image_count += 1
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_message_builder.py::test_build_markdown_v2_message_uses_remote_image_urls_from_items -v`
Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/wecom_sales_webhook_bot/models.py src/wecom_sales_webhook_bot/message_builder.py tests/test_message_builder.py
git commit -m "feat: add remote image fields to sales items"
```

### Task 3: Add Database Models And Bootstrap

**Files:**
- Create: `src/wecom_sales_webhook_bot/db.py`
- Create: `src/wecom_sales_webhook_bot/rule_models.py`
- Test: `tests/test_db_models.py`

- [ ] **Step 1: Write the failing test**

```python
from wecom_sales_webhook_bot.db import create_session_factory, initialize_database
from wecom_sales_webhook_bot.rule_models import JobRun, PushRecord, RuleCondition, RuleGroup, UserAccount


def test_initialize_database_creates_core_tables(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    session_factory = create_session_factory(database_url)

    initialize_database(session_factory)

    with session_factory() as session:
        session.add(UserAccount(username="admin", password_hash="hash", role="admin", is_active=True))
        session.add(RuleGroup(name="金额规则", is_enabled=True, match_mode="any", updated_by="admin"))
        session.add(JobRun(status="success", window_start="2026-04-22T10:00:00", window_end="2026-04-22T10:20:00"))
        session.add(PushRecord(order_no="SO-1", store_name="G621", total_amount=19250, rule_name="金额规则", status="success"))
        session.commit()

    with session_factory() as session:
        assert session.query(UserAccount).count() == 1
        assert session.query(RuleGroup).count() == 1
        assert session.query(PushRecord).count() == 1
        assert session.query(JobRun).count() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_db_models.py -v`
Expected: FAIL because DB helpers and ORM models do not exist.

- [ ] **Step 3: Write minimal implementation**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from wecom_sales_webhook_bot.rule_models import Base


def create_session_factory(database_url: str) -> sessionmaker:
    engine = create_engine(database_url, future=True)
    return sessionmaker(bind=engine, future=True)


def initialize_database(session_factory: sessionmaker) -> None:
    Base.metadata.create_all(session_factory.kw["bind"])
```

```python
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserAccount(Base):
    __tablename__ = "user_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RuleGroup(Base):
    __tablename__ = "rule_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    match_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class RuleCondition(Base):
    __tablename__ = "rule_conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_group_id: Mapped[int] = mapped_column(Integer, nullable=False)
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    operator: Mapped[str] = mapped_column(String(16), nullable=False)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)


class PushRecord(Base):
    __tablename__ = "push_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_no: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    store_name: Mapped[str] = mapped_column(String(64), nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    rule_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    window_start: Mapped[str] = mapped_column(String(32), nullable=False)
    window_end: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_db_models.py -v`
Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/wecom_sales_webhook_bot/db.py src/wecom_sales_webhook_bot/rule_models.py tests/test_db_models.py
git commit -m "feat: add backend database schema"
```

### Task 4: Add Rule Condition DTOs, Validation, And Matching

**Files:**
- Create: `src/wecom_sales_webhook_bot/rule_service.py`
- Test: `tests/test_rule_service.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime

from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder
from wecom_sales_webhook_bot.rule_service import RuleConditionDTO, RuleGroupDTO, evaluate_rule_group


def test_evaluate_rule_group_supports_amount_style_store_time_brand_category() -> None:
    order = SalesOrder(
        order_no="SO-2",
        sold_at=datetime(2026, 4, 22, 10, 30, 0),
        store_name="G621",
        total_amount=19250,
        items=[
            SalesLineItem(
                barcode="b1",
                style_no="PA17047BNY0",
                unit_price=5850,
                brand="Brand-A",
                category="外套",
            )
        ],
    )

    any_group = RuleGroupDTO(
        name="任一命中",
        match_mode="any",
        conditions=[
            RuleConditionDTO(field_name="store_name", operator="in", value=["G999"]),
            RuleConditionDTO(field_name="brand", operator="in", value=["Brand-A"]),
        ],
    )
    all_group = RuleGroupDTO(
        name="全部命中",
        match_mode="all",
        conditions=[
            RuleConditionDTO(field_name="total_amount", operator="gte", value=10000),
            RuleConditionDTO(field_name="style_no", operator="in", value=["PA17047BNY0"]),
            RuleConditionDTO(field_name="category", operator="in", value=["外套"]),
            RuleConditionDTO(field_name="sold_at", operator="between_time", value=["10:00", "11:00"]),
        ],
    )

    assert evaluate_rule_group(order, any_group) is True
    assert evaluate_rule_group(order, all_group) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_rule_service.py -v`
Expected: FAIL because rule DTOs and evaluator do not exist.

- [ ] **Step 3: Write minimal implementation**

```python
from dataclasses import dataclass
from datetime import time

from wecom_sales_webhook_bot.models import SalesOrder


@dataclass(frozen=True)
class RuleConditionDTO:
    field_name: str
    operator: str
    value: list[str] | float


@dataclass(frozen=True)
class RuleGroupDTO:
    name: str
    match_mode: str
    conditions: list[RuleConditionDTO]
```

```python
def _match_condition(order: SalesOrder, condition: RuleConditionDTO) -> bool:
    if condition.field_name == "total_amount" and condition.operator == "gte":
        return order.total_amount >= float(condition.value)
    if condition.field_name == "store_name" and condition.operator == "in":
        return order.store_name in condition.value
    if condition.field_name == "style_no" and condition.operator == "in":
        return any(item.style_no in condition.value for item in order.items)
    if condition.field_name == "brand" and condition.operator == "in":
        return any((item.brand or "") in condition.value for item in order.items)
    if condition.field_name == "category" and condition.operator == "in":
        return any((item.category or "") in condition.value for item in order.items)
    if condition.field_name == "sold_at" and condition.operator == "between_time":
        start_text, end_text = condition.value
        start_hour, start_minute = map(int, start_text.split(":"))
        end_hour, end_minute = map(int, end_text.split(":"))
        current = order.sold_at.time()
        return time(start_hour, start_minute) <= current <= time(end_hour, end_minute)
    return False


def evaluate_rule_group(order: SalesOrder, rule_group: RuleGroupDTO) -> bool:
    results = [_match_condition(order, item) for item in rule_group.conditions]
    if rule_group.match_mode == "all":
        return all(results)
    return any(results)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_rule_service.py -v`
Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/wecom_sales_webhook_bot/rule_service.py tests/test_rule_service.py
git commit -m "feat: add rule evaluation service"
```

### Task 5: Add IT Sales API Adapter

**Files:**
- Create: `src/wecom_sales_webhook_bot/api_source.py`
- Test: `tests/test_api_source.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime

from wecom_sales_webhook_bot.api_source import SalesApiDataSource


class FakeSession:
    def get(self, url, headers, params, timeout):
        class Response:
            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def json():
                return {
                    "items": [
                        {
                            "order_no": "SO-API-1",
                            "sold_at": "2026-04-22T10:00:00",
                            "store_name": "G621",
                            "total_amount": 19250,
                            "barcode": "b1",
                            "style_no": "PA17047BNY0",
                            "unit_price": 5850,
                            "brand": "Brand-A",
                            "category": "外套",
                            "image_url": "https://img.example.com/p1.jpg",
                        },
                        {
                            "order_no": "SO-API-1",
                            "sold_at": "2026-04-22T10:00:00",
                            "store_name": "G621",
                            "total_amount": 19250,
                            "barcode": "b2",
                            "style_no": "PA15161ENY0",
                            "unit_price": 7550,
                            "brand": "Brand-B",
                            "category": "连衣裙",
                            "image_url": "https://img.example.com/p2.jpg",
                        },
                    ]
                }

        return Response()


def test_sales_api_data_source_groups_api_rows_into_orders() -> None:
    source = SalesApiDataSource(
        base_url="https://internal.example.com",
        path="/sales/query",
        token="token-1",
        timeout_seconds=10,
        session=FakeSession(),
    )

    orders = source.load_orders(
        start_at=datetime(2026, 4, 22, 10, 0, 0),
        end_at=datetime(2026, 4, 22, 10, 20, 0),
    )

    assert len(orders) == 1
    assert orders[0].order_no == "SO-API-1"
    assert len(orders[0].items) == 2
    assert orders[0].items[1].image_url == "https://img.example.com/p2.jpg"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_source.py -v`
Expected: FAIL because the API data source does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
from datetime import datetime

import requests

from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder


class SalesApiDataSource:
    def __init__(self, base_url: str, path: str, token: str, timeout_seconds: int, session=None) -> None:
        self._base_url = base_url.rstrip("/")
        self._path = path
        self._token = token
        self._timeout_seconds = timeout_seconds
        self._session = session or requests.Session()
```

```python
    def load_orders(self, start_at: datetime, end_at: datetime) -> list[SalesOrder]:
        response = self._session.get(
            f"{self._base_url}{self._path}",
            headers={"Authorization": f"Bearer {self._token}"},
            params={"start_at": start_at.isoformat(), "end_at": end_at.isoformat()},
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        grouped: dict[str, dict] = {}
        for row in response.json()["items"]:
            order_no = row["order_no"]
            grouped.setdefault(
                order_no,
                {
                    "order_no": order_no,
                    "sold_at": datetime.fromisoformat(row["sold_at"]),
                    "store_name": row["store_name"],
                    "total_amount": float(row["total_amount"]),
                    "items": [],
                },
            )
            grouped[order_no]["items"].append(
                SalesLineItem(
                    barcode=row["barcode"],
                    style_no=row["style_no"],
                    unit_price=float(row["unit_price"]),
                    brand=row.get("brand"),
                    category=row.get("category"),
                    image_url=row.get("image_url"),
                )
            )
        return [SalesOrder(**payload) for payload in grouped.values()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_source.py -v`
Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/wecom_sales_webhook_bot/api_source.py tests/test_api_source.py
git commit -m "feat: add sales api adapter"
```

### Task 6: Add Login And App Factory

**Files:**
- Create: `src/wecom_sales_webhook_bot/auth.py`
- Create: `src/wecom_sales_webhook_bot/web_app.py`
- Create: `src/wecom_sales_webhook_bot/templates/base.html`
- Create: `src/wecom_sales_webhook_bot/templates/login.html`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_auth.py -v`
Expected: FAIL because login app factory does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    return check_password_hash(password_hash, password)
```

```python
from flask import Flask, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, login_required, login_user

from wecom_sales_webhook_bot.auth import hash_password, verify_password
from wecom_sales_webhook_bot.db import create_session_factory, initialize_database
from wecom_sales_webhook_bot.rule_models import UserAccount


class LoginUser(UserMixin):
    def __init__(self, user_id: int) -> None:
        self.id = str(user_id)


def create_app(config: dict) -> Flask:
    app = Flask(__name__)
    app.config.update(config)
    session_factory = create_session_factory(app.config["DATABASE_URL"])
    initialize_database(session_factory)
    login_manager = LoginManager()
    login_manager.login_view = "login_page"
    login_manager.init_app(app)

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
        return render_template("login.html")

    @app.post("/login")
    def login_submit():
        with session_factory() as session:
            user = session.query(UserAccount).filter_by(username=request.form["username"]).one()
            if verify_password(user.password_hash, request.form["password"]):
                login_user(LoginUser(user.id))
                return redirect(url_for("rules_page"))
        return redirect(url_for("login_page"))

    @app.get("/rules")
    @login_required
    def rules_page():
        return "rules"

    return app
```

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <title>销售推送后台</title>
  </head>
  <body>
    {% block body %}{% endblock %}
  </body>
</html>
```

```html
{% extends "base.html" %}
{% block body %}
<form method="post" action="/login">
  <label>用户名<input name="username" /></label>
  <label>密码<input name="password" type="password" /></label>
  <button type="submit">登录</button>
</form>
{% endblock %}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_auth.py -v`
Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/wecom_sales_webhook_bot/auth.py src/wecom_sales_webhook_bot/web_app.py src/wecom_sales_webhook_bot/templates/base.html src/wecom_sales_webhook_bot/templates/login.html tests/test_auth.py
git commit -m "feat: add backend login flow"
```

### Task 7: Add Rule Management Pages And Persistence

**Files:**
- Modify: `src/wecom_sales_webhook_bot/web_app.py`
- Modify: `src/wecom_sales_webhook_bot/rule_models.py`
- Create: `src/wecom_sales_webhook_bot/templates/rules.html`
- Create: `src/wecom_sales_webhook_bot/templates/rule_edit.html`
- Test: `tests/test_web_app.py`

- [ ] **Step 1: Write the failing test**

```python
from wecom_sales_webhook_bot.web_app import create_app


def test_rule_save_persists_match_mode_and_supported_conditions() -> None:
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE_URL": "sqlite:///:memory:",
            "BOOTSTRAP_ADMIN": {"username": "admin", "password": "pass123"},
        }
    )
    client = app.test_client()
    client.post("/login", data={"username": "admin", "password": "pass123"})

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
    assert "all" in page
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_app.py::test_rule_save_persists_match_mode_and_supported_conditions -v`
Expected: FAIL because rule pages and persistence do not exist.

- [ ] **Step 3: Write minimal implementation**

```python
class RuleCondition(Base):
    __tablename__ = "rule_conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_group_id: Mapped[int] = mapped_column(Integer, nullable=False)
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    operator: Mapped[str] = mapped_column(String(16), nullable=False)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
```

```python
@app.get("/rules")
@login_required
def rules_page():
    with session_factory() as session:
        rules = session.query(RuleGroup).order_by(RuleGroup.updated_at.desc()).all()
    return render_template("rules.html", rules=rules)


@app.get("/rules/new")
@login_required
def rule_new_page():
    return render_template("rule_edit.html")
```

```python
@app.post("/rules/new")
@login_required
def rule_new_submit():
    with session_factory() as session:
        rule = RuleGroup(
            name=request.form["name"],
            is_enabled=request.form.get("is_enabled") == "on",
            match_mode=request.form["match_mode"],
            updated_by="admin",
        )
        session.add(rule)
        session.flush()

        def add_condition(field_name: str, operator: str, value_json: str) -> None:
            if value_json:
                session.add(
                    RuleCondition(
                        rule_group_id=rule.id,
                        field_name=field_name,
                        operator=operator,
                        value_json=value_json,
                    )
                )

        add_condition("total_amount", "gte", request.form["amount_threshold"])
        add_condition("style_no", "in", request.form["style_list"])
        add_condition("store_name", "in", request.form["store_list"])
        if request.form["time_start"] and request.form["time_end"]:
            add_condition("sold_at", "between_time", f"{request.form['time_start']},{request.form['time_end']}")
        add_condition("brand", "in", request.form["brand_list"])
        add_condition("category", "in", request.form["category_list"])

        session.commit()
    return redirect(url_for("rules_page"))
```

```html
{% extends "base.html" %}
{% block body %}
<h1>规则列表</h1>
{% for rule in rules %}
<div>{{ rule.name }} | {{ rule.match_mode }}</div>
{% endfor %}
{% endblock %}
```

```html
{% extends "base.html" %}
{% block body %}
<form method="post" action="/rules/new">
  <input name="name" />
  <input name="is_enabled" type="checkbox" checked />
  <select name="match_mode">
    <option value="any">any</option>
    <option value="all">all</option>
  </select>
  <input name="amount_threshold" />
  <input name="style_list" />
  <input name="store_list" />
  <input name="time_start" />
  <input name="time_end" />
  <input name="brand_list" />
  <input name="category_list" />
  <button type="submit">保存</button>
</form>
{% endblock %}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_app.py::test_rule_save_persists_match_mode_and_supported_conditions -v`
Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/wecom_sales_webhook_bot/web_app.py src/wecom_sales_webhook_bot/rule_models.py src/wecom_sales_webhook_bot/templates/rules.html src/wecom_sales_webhook_bot/templates/rule_edit.html tests/test_web_app.py
git commit -m "feat: add rule management pages"
```

### Task 8: Add Scheduled Scan Runner, De-Duplication, And Push Logging

**Files:**
- Create: `src/wecom_sales_webhook_bot/job_runner.py`
- Modify: `src/wecom_sales_webhook_bot/wecom_client.py`
- Test: `tests/test_job_runner.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime

from wecom_sales_webhook_bot.job_runner import run_scan_cycle
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder
from wecom_sales_webhook_bot.rule_service import RuleConditionDTO, RuleGroupDTO


class FakeSource:
    def load_orders(self, start_at, end_at):
        return [
            SalesOrder(
                order_no="SO-API-1",
                sold_at=datetime(2026, 4, 22, 10, 0, 0),
                store_name="G621",
                total_amount=19250,
                items=[
                    SalesLineItem(
                        barcode="b1",
                        style_no="s1",
                        unit_price=5850,
                        image_url="https://img/1.jpg",
                    )
                ],
            )
        ]


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def send_markdown_v2(self, content: str) -> None:
        self.calls.append(content)


def test_run_scan_cycle_pushes_matching_orders_once_and_logs_record(tmp_path) -> None:
    sent = run_scan_cycle(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        source=FakeSource(),
        rule_groups=[
            RuleGroupDTO(
                name="门店规则",
                match_mode="any",
                conditions=[RuleConditionDTO(field_name="store_name", operator="in", value=["G621"])],
            )
        ],
        webhook_client=FakeClient(),
        start_at=datetime(2026, 4, 22, 10, 0, 0),
        end_at=datetime(2026, 4, 22, 10, 20, 0),
        max_images=8,
    )

    assert sent == ["SO-API-1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_job_runner.py -v`
Expected: FAIL because the scheduled scan runner does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
from wecom_sales_webhook_bot.db import create_session_factory, initialize_database
from wecom_sales_webhook_bot.message_builder import build_markdown_v2_message
from wecom_sales_webhook_bot.rule_models import JobRun, PushRecord
from wecom_sales_webhook_bot.rule_service import evaluate_rule_group


def run_scan_cycle(database_url: str, source, rule_groups, webhook_client, start_at, end_at, max_images: int) -> list[str]:
    session_factory = create_session_factory(database_url)
    initialize_database(session_factory)
    sent_orders: list[str] = []
    with session_factory() as session:
        for order in source.load_orders(start_at=start_at, end_at=end_at):
            exists = session.query(PushRecord).filter_by(order_no=order.order_no, status="success").first()
            if exists:
                continue

            matched_group = next((group for group in rule_groups if evaluate_rule_group(order, group)), None)
            if matched_group is None:
                continue

            message = build_markdown_v2_message(order=order, max_images=max_images)
            webhook_client.send_markdown_v2(message)
            session.add(
                PushRecord(
                    order_no=order.order_no,
                    store_name=order.store_name,
                    total_amount=order.total_amount,
                    rule_name=matched_group.name,
                    status="success",
                )
            )
            sent_orders.append(order.order_no)

        session.add(
            JobRun(
                window_start=start_at.isoformat(),
                window_end=end_at.isoformat(),
                status="success",
                success_count=len(sent_orders),
                failed_count=0,
            )
        )
        session.commit()
    return sent_orders
```

```python
def send_markdown_v2(self, content: str) -> None:
    self.send_markdown(content)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_job_runner.py -v`
Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/wecom_sales_webhook_bot/job_runner.py src/wecom_sales_webhook_bot/wecom_client.py tests/test_job_runner.py
git commit -m "feat: add scheduled scan runner"
```

### Task 9: Add Status Pages, Scheduler Startup, And Docs

**Files:**
- Modify: `src/wecom_sales_webhook_bot/web_app.py`
- Create: `src/wecom_sales_webhook_bot/templates/push_records.html`
- Create: `src/wecom_sales_webhook_bot/templates/system_status.html`
- Modify: `src/wecom_sales_webhook_bot/cli.py`
- Modify: `README.md`
- Test: `tests/test_web_app.py`

- [ ] **Step 1: Write the failing test**

```python
from wecom_sales_webhook_bot.cli import build_parser
from wecom_sales_webhook_bot.web_app import create_app


def test_cli_exposes_run_server_command() -> None:
    parser = build_parser()
    args = parser.parse_args(["run-server", "--config", "config.yaml"])
    assert args.command == "run-server"


def test_status_page_loads_after_login() -> None:
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE_URL": "sqlite:///:memory:",
            "BOOTSTRAP_ADMIN": {"username": "admin", "password": "pass123"},
        }
    )
    client = app.test_client()
    client.post("/login", data={"username": "admin", "password": "pass123"})

    response = client.get("/status")

    assert response.status_code == 200
    assert "最近一次扫描" in response.get_data(as_text=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_app.py::test_cli_exposes_run_server_command tests/test_web_app.py::test_status_page_loads_after_login -v`
Expected: FAIL because server startup command and status page do not exist.

- [ ] **Step 3: Write minimal implementation**

```python
@app.get("/records")
@login_required
def records_page():
    with session_factory() as session:
        records = session.query(PushRecord).order_by(PushRecord.created_at.desc()).limit(50).all()
    return render_template("push_records.html", records=records)


@app.get("/status")
@login_required
def status_page():
    with session_factory() as session:
        last_run = session.query(JobRun).order_by(JobRun.created_at.desc()).first()
    return render_template("system_status.html", last_run=last_run)
```

```html
{% extends "base.html" %}
{% block body %}
<h1>推送记录</h1>
{% for record in records %}
<div>{{ record.order_no }} | {{ record.store_name }} | {{ record.status }}</div>
{% endfor %}
{% endblock %}
```

```html
{% extends "base.html" %}
{% block body %}
<div>最近一次扫描：{{ last_run.created_at if last_run else "暂无" }}</div>
<div>最近成功数量：{{ last_run.success_count if last_run else 0 }}</div>
<div>最近失败数量：{{ last_run.failed_count if last_run else 0 }}</div>
{% endblock %}
```

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("run-once", "schedule", "serve-images", "clear-state", "run-server"):
        command = subparsers.add_parser(name)
        command.add_argument("--config", required=True)
    return parser
```

```python
if args.command == "run-server":
    app = create_app(
        {
            "SECRET_KEY": config.backend.secret_key,
            "DATABASE_URL": config.backend.database_url,
            "BOOTSTRAP_ADMIN": {
                "username": config.backend.bootstrap_admin_username,
                "password": config.backend.bootstrap_admin_password,
            },
        }
    )
    app.run(host=config.backend.host, port=config.backend.port)
    return
```

```markdown
## Admin Backend

- Start server: `python -m wecom_sales_webhook_bot.cli run-server --config config.yaml`
- Login URL: `http://127.0.0.1:5000/login`
- Backend stores users, rules, push records, and scan status in SQLite by default
```

- [ ] **Step 4: Run test and smoke verification**

Run: `python -m pytest tests/test_web_app.py::test_cli_exposes_run_server_command tests/test_web_app.py::test_status_page_loads_after_login -v`
Expected: PASS with `2 passed`.

Run: `python -m pytest -v`
Expected: PASS with all backend and prototype tests green.

- [ ] **Step 5: Commit**

```bash
git add src/wecom_sales_webhook_bot/web_app.py src/wecom_sales_webhook_bot/templates/push_records.html src/wecom_sales_webhook_bot/templates/system_status.html src/wecom_sales_webhook_bot/cli.py README.md tests/test_web_app.py
git commit -m "feat: wire admin backend startup and status pages"
```

## Self-Review

### Spec Coverage

- 登录页、规则列表页、规则编辑页、推送记录页、系统状态页: covered by Tasks 6, 7, 9
- 规则类型金额阈值、款号名单、门店名单、时间段、品牌、类别: covered by Task 4 and persisted in Task 7
- 匹配模式任意满足、全部满足: covered by Task 4
- IT 销售接口和图片 URL: covered by Tasks 2 and 5
- 定时查询、整单聚合、命中推送、运行记录、防重复推送: covered by Task 8
- 单体常驻服务和 CLI 启动: covered by Task 9

### Placeholder Scan

- No `TODO`, `TBD`, or "implement later" placeholders remain.
- Each task includes file paths, a concrete test, a concrete command, and concrete code snippets.

### Type Consistency

- `SalesLineItem` fields `brand`, `category`, and `image_url` are introduced in Task 2 and reused consistently in Tasks 4, 5, and 8.
- `RuleGroupDTO.name` is defined in Task 4 and reused consistently in Task 8 for push logging.
- DB-backed de-duplication uses `PushRecord.order_no` consistently instead of the old `state_file`.
