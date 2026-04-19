# WeCom Sales Webhook Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows-first Python prototype that reads a fixed CSV file, groups and filters sales orders, resolves local barcode images to URLs, and sends one Enterprise WeChat `markdown_v2` webhook message per qualifying order.

**Architecture:** Use a small Python package with focused modules for configuration, CSV parsing, filtering, state persistence, image URL resolution, message building, webhook delivery, and orchestration. Keep scheduling and HTTP image serving thin so the core business logic stays easy to test and later swap to database/API and EMS-backed image URLs.

**Tech Stack:** Python 3.12, pytest, PyYAML, requests, standard-library `http.server`, standard-library `argparse`

---

## Planned File Structure

**Create**

- `pyproject.toml`
- `README.md`
- `config.example.yaml`
- `src/wecom_sales_webhook_bot/__init__.py`
- `src/wecom_sales_webhook_bot/models.py`
- `src/wecom_sales_webhook_bot/config.py`
- `src/wecom_sales_webhook_bot/csv_source.py`
- `src/wecom_sales_webhook_bot/filters.py`
- `src/wecom_sales_webhook_bot/state_store.py`
- `src/wecom_sales_webhook_bot/image_service.py`
- `src/wecom_sales_webhook_bot/message_builder.py`
- `src/wecom_sales_webhook_bot/wecom_client.py`
- `src/wecom_sales_webhook_bot/orchestrator.py`
- `src/wecom_sales_webhook_bot/cli.py`
- `tests/conftest.py`
- `tests/test_config.py`
- `tests/test_csv_source.py`
- `tests/test_filters_and_state.py`
- `tests/test_image_service.py`
- `tests/test_message_builder.py`
- `tests/test_orchestrator.py`

**Responsibilities**

- `models.py`: shared dataclasses for product lines, grouped sales orders, filter results, and runtime state.
- `config.py`: YAML loading, field mapping validation, and typed runtime config.
- `csv_source.py`: CSV parsing and grouping by sales order number.
- `filters.py`: amount threshold and style whitelist evaluation.
- `state_store.py`: local JSON-backed push state.
- `image_service.py`: barcode image lookup plus local HTTP file serving helpers.
- `message_builder.py`: `markdown_v2` message rendering and image truncation rules.
- `wecom_client.py`: webhook POST with retry behavior.
- `orchestrator.py`: run-once workflow that ties scanning, filtering, pushing, and state updates together.
- `cli.py`: `run-once`, `serve-images`, `schedule`, and `clear-state` commands.

### Task 1: Bootstrap The Python Project

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/wecom_sales_webhook_bot/__init__.py`
- Create: `tests/conftest.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from pathlib import Path

from wecom_sales_webhook_bot.config import load_config


def test_load_config_reads_threshold_and_style_whitelist(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
csv:
  path: ./data/sales.csv
  encoding: utf-8-sig
  field_mapping:
    order_no: 销售单号
    sold_at: 销售日期（时间）
    store_name: 销售门店
    total_amount: 销售单总额
    barcode: 商品条码
    style_no: 产品款号
    unit_price: 产品单价
image_service:
  host: 127.0.0.1
  port: 8123
  image_dir: ./images
wecom:
  webhook_url: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test
  timeout_seconds: 5
  retry_times: 2
rules:
  amount_threshold: 1000
  style_whitelist: ["A1001", "B2002"]
runtime:
  scan_interval_seconds: 600
  max_images_per_message: 8
  state_file: ./var/push-state.json
  dry_run: false
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.rules.amount_threshold == 1000
    assert config.rules.style_whitelist == {"A1001", "B2002"}
    assert config.runtime.max_images_per_message == 8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError` because the package and config loader do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "wecom-sales-webhook-bot"
version = "0.1.0"
description = "Enterprise WeChat sales webhook bot prototype"
requires-python = ">=3.12"
dependencies = [
  "PyYAML>=6.0.1",
  "requests>=2.32.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.1.0"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

```python
# src/wecom_sales_webhook_bot/__init__.py
__all__ = ["__version__"]

__version__ = "0.1.0"
```

```python
# src/wecom_sales_webhook_bot/config.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class CsvConfig:
    path: Path
    encoding: str
    field_mapping: dict[str, str]


@dataclass(frozen=True)
class ImageServiceConfig:
    host: str
    port: int
    image_dir: Path


@dataclass(frozen=True)
class WeComConfig:
    webhook_url: str
    timeout_seconds: int
    retry_times: int


@dataclass(frozen=True)
class RulesConfig:
    amount_threshold: float
    style_whitelist: set[str]


@dataclass(frozen=True)
class RuntimeConfig:
    scan_interval_seconds: int
    max_images_per_message: int
    state_file: Path
    dry_run: bool


@dataclass(frozen=True)
class AppConfig:
    csv: CsvConfig
    image_service: ImageServiceConfig
    wecom: WeComConfig
    rules: RulesConfig
    runtime: RuntimeConfig


def load_config(path: Path) -> AppConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return AppConfig(
        csv=CsvConfig(
            path=Path(raw["csv"]["path"]),
            encoding=raw["csv"]["encoding"],
            field_mapping=dict(raw["csv"]["field_mapping"]),
        ),
        image_service=ImageServiceConfig(
            host=raw["image_service"]["host"],
            port=int(raw["image_service"]["port"]),
            image_dir=Path(raw["image_service"]["image_dir"]),
        ),
        wecom=WeComConfig(
            webhook_url=raw["wecom"]["webhook_url"],
            timeout_seconds=int(raw["wecom"]["timeout_seconds"]),
            retry_times=int(raw["wecom"]["retry_times"]),
        ),
        rules=RulesConfig(
            amount_threshold=float(raw["rules"]["amount_threshold"]),
            style_whitelist=set(raw["rules"]["style_whitelist"]),
        ),
        runtime=RuntimeConfig(
            scan_interval_seconds=int(raw["runtime"]["scan_interval_seconds"]),
            max_images_per_message=int(raw["runtime"]["max_images_per_message"]),
            state_file=Path(raw["runtime"]["state_file"]),
            dry_run=bool(raw["runtime"]["dry_run"]),
        ),
    )
```

```python
# tests/conftest.py
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
```

```markdown
# README.md

## WeCom Sales Webhook Bot

Prototype bot for reading a sales CSV, resolving product images, and sending Enterprise WeChat webhook messages.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml README.md src/wecom_sales_webhook_bot/__init__.py src/wecom_sales_webhook_bot/config.py tests/conftest.py tests/test_config.py
git commit -m "feat: bootstrap python project config loading"
```

### Task 2: Add Typed Domain Models And CSV Parsing

**Files:**
- Create: `src/wecom_sales_webhook_bot/models.py`
- Create: `src/wecom_sales_webhook_bot/csv_source.py`
- Test: `tests/test_csv_source.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_csv_source.py
from pathlib import Path

from wecom_sales_webhook_bot.config import load_config
from wecom_sales_webhook_bot.csv_source import CsvSalesDataSource


def test_csv_source_groups_rows_by_order_number(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
csv:
  path: ./sales.csv
  encoding: utf-8-sig
  field_mapping:
    order_no: 销售单号
    sold_at: 销售日期（时间）
    store_name: 销售门店
    total_amount: 销售单总额
    barcode: 商品条码
    style_no: 产品款号
    unit_price: 产品单价
image_service:
  host: 127.0.0.1
  port: 8123
  image_dir: ./images
wecom:
  webhook_url: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test
  timeout_seconds: 5
  retry_times: 2
rules:
  amount_threshold: 1000
  style_whitelist: []
runtime:
  scan_interval_seconds: 600
  max_images_per_message: 8
  state_file: ./var/push-state.json
  dry_run: false
""".strip(),
        encoding="utf-8",
    )
    sales_file = tmp_path / "sales.csv"
    sales_file.write_text(
        "\n".join(
            [
                "销售单号,销售日期（时间）,销售门店,销售单总额,商品条码,产品款号,产品单价",
                "SO-001,2026-04-20 10:00:00,上海一店,1200,6901111111111,A1001,699",
                "SO-001,2026-04-20 10:00:00,上海一店,1200,6902222222222,B2002,501",
            ]
        ),
        encoding="utf-8-sig",
    )

    config = load_config(config_file)
    data_source = CsvSalesDataSource(config.csv, base_dir=tmp_path)

    orders = data_source.load_orders()

    assert len(orders) == 1
    assert orders[0].order_no == "SO-001"
    assert orders[0].store_name == "上海一店"
    assert [item.barcode for item in orders[0].items] == ["6901111111111", "6902222222222"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_csv_source.py -v`
Expected: FAIL with `ModuleNotFoundError` for `csv_source` or missing `CsvSalesDataSource`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/wecom_sales_webhook_bot/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class SalesLineItem:
    barcode: str
    style_no: str
    unit_price: float
    quantity: int = 1


@dataclass(frozen=True)
class SalesOrder:
    order_no: str
    sold_at: datetime
    store_name: str
    total_amount: float
    items: list[SalesLineItem] = field(default_factory=list)
```

```python
# src/wecom_sales_webhook_bot/csv_source.py
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from wecom_sales_webhook_bot.config import CsvConfig
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder


class CsvSalesDataSource:
    def __init__(self, config: CsvConfig, base_dir: Path) -> None:
        self._config = config
        self._base_dir = base_dir

    def load_orders(self) -> list[SalesOrder]:
        csv_path = (self._base_dir / self._config.path).resolve()
        mapping = self._config.field_mapping
        grouped: dict[str, dict] = {}

        with csv_path.open("r", encoding=self._config.encoding, newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                order_no = row[mapping["order_no"]]
                item = SalesLineItem(
                    barcode=row[mapping["barcode"]],
                    style_no=row[mapping["style_no"]],
                    unit_price=float(row[mapping["unit_price"]]),
                    quantity=int(row.get(mapping.get("quantity", ""), "1") or "1"),
                )
                if order_no not in grouped:
                    grouped[order_no] = {
                        "order_no": order_no,
                        "sold_at": datetime.strptime(row[mapping["sold_at"]], "%Y-%m-%d %H:%M:%S"),
                        "store_name": row[mapping["store_name"]],
                        "total_amount": float(row[mapping["total_amount"]]),
                        "items": [],
                    }
                grouped[order_no]["items"].append(item)

        return [SalesOrder(**payload) for payload in grouped.values()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_csv_source.py -v`
Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/wecom_sales_webhook_bot/models.py src/wecom_sales_webhook_bot/csv_source.py tests/test_csv_source.py
git commit -m "feat: parse csv sales orders"
```

### Task 3: Implement Filtering And Persistent Push State

**Files:**
- Create: `src/wecom_sales_webhook_bot/filters.py`
- Create: `src/wecom_sales_webhook_bot/state_store.py`
- Test: `tests/test_filters_and_state.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_filters_and_state.py
from datetime import datetime
from pathlib import Path

from wecom_sales_webhook_bot.filters import SalesFilter
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder
from wecom_sales_webhook_bot.state_store import PushStateStore


def test_filter_matches_amount_or_style_and_state_blocks_duplicates(tmp_path: Path) -> None:
    order = SalesOrder(
        order_no="SO-900",
        sold_at=datetime(2026, 4, 20, 10, 0, 0),
        store_name="上海一店",
        total_amount=800,
        items=[SalesLineItem(barcode="6901111111111", style_no="VIP-001", unit_price=800)],
    )

    sales_filter = SalesFilter(amount_threshold=1000, style_whitelist={"VIP-001"})
    result = sales_filter.evaluate(order)

    assert result.matched is True
    assert result.reason == "style_whitelist"

    state_store = PushStateStore(tmp_path / "push-state.json")
    assert state_store.has_pushed("SO-900") is False
    state_store.mark_pushed("SO-900", sold_at=order.sold_at)
    assert state_store.has_pushed("SO-900") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_filters_and_state.py -v`
Expected: FAIL because `SalesFilter` and `PushStateStore` do not exist.

- [ ] **Step 3: Write minimal implementation**

```python
# src/wecom_sales_webhook_bot/filters.py
from __future__ import annotations

from dataclasses import dataclass

from wecom_sales_webhook_bot.models import SalesOrder


@dataclass(frozen=True)
class FilterResult:
    matched: bool
    reason: str | None


class SalesFilter:
    def __init__(self, amount_threshold: float, style_whitelist: set[str]) -> None:
        self._amount_threshold = amount_threshold
        self._style_whitelist = style_whitelist

    def evaluate(self, order: SalesOrder) -> FilterResult:
        if order.total_amount >= self._amount_threshold:
            return FilterResult(matched=True, reason="amount_threshold")
        if any(item.style_no in self._style_whitelist for item in order.items):
            return FilterResult(matched=True, reason="style_whitelist")
        return FilterResult(matched=False, reason=None)
```

```python
# src/wecom_sales_webhook_bot/state_store.py
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class PushStateStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text('{"last_scan_at": null, "pushed_orders": {}}', encoding="utf-8")

    def _read(self) -> dict:
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, payload: dict) -> None:
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def has_pushed(self, order_no: str) -> bool:
        return order_no in self._read()["pushed_orders"]

    def mark_pushed(self, order_no: str, sold_at: datetime) -> None:
        payload = self._read()
        payload["pushed_orders"][order_no] = sold_at.isoformat()
        self._write(payload)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_filters_and_state.py -v`
Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/wecom_sales_webhook_bot/filters.py src/wecom_sales_webhook_bot/state_store.py tests/test_filters_and_state.py
git commit -m "feat: add filtering and push state persistence"
```

### Task 4: Add Local Image Resolution And HTTP Serving

**Files:**
- Create: `src/wecom_sales_webhook_bot/image_service.py`
- Test: `tests/test_image_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_image_service.py
from pathlib import Path

from wecom_sales_webhook_bot.image_service import LocalImageUrlProvider


def test_local_image_provider_returns_url_for_existing_barcode(tmp_path: Path) -> None:
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    (image_dir / "6901111111111.jpg").write_bytes(b"fake-jpg")

    provider = LocalImageUrlProvider(
        image_dir=image_dir,
        base_url="http://127.0.0.1:8123",
    )

    assert provider.get_url("6901111111111") == "http://127.0.0.1:8123/6901111111111.jpg"
    assert provider.get_url("6909999999999") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_image_service.py -v`
Expected: FAIL because `LocalImageUrlProvider` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
# src/wecom_sales_webhook_bot/image_service.py
from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread


class LocalImageUrlProvider:
    def __init__(self, image_dir: Path, base_url: str) -> None:
        self._image_dir = image_dir
        self._base_url = base_url.rstrip("/")

    def get_url(self, barcode: str) -> str | None:
        for extension in (".jpg", ".png", ".jpeg"):
            candidate = self._image_dir / f"{barcode}{extension}"
            if candidate.exists():
                return f"{self._base_url}/{candidate.name}"
        return None


def start_image_server(image_dir: Path, host: str, port: int) -> ThreadingHTTPServer:
    handler = partial(SimpleHTTPRequestHandler, directory=str(image_dir))
    server = ThreadingHTTPServer((host, port), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_image_service.py -v`
Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/wecom_sales_webhook_bot/image_service.py tests/test_image_service.py
git commit -m "feat: add local image url provider"
```

### Task 5: Build Markdown Message Rendering

**Files:**
- Create: `src/wecom_sales_webhook_bot/message_builder.py`
- Test: `tests/test_message_builder.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_message_builder.py
from datetime import datetime

from wecom_sales_webhook_bot.filters import FilterResult
from wecom_sales_webhook_bot.message_builder import build_markdown_v2_message
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder


def test_message_builder_renders_order_details_and_limits_images() -> None:
    order = SalesOrder(
        order_no="SO-001",
        sold_at=datetime(2026, 4, 20, 10, 0, 0),
        store_name="上海一店",
        total_amount=1200,
        items=[
            SalesLineItem(barcode="6901111111111", style_no="A1001", unit_price=699),
            SalesLineItem(barcode="6902222222222", style_no="B2002", unit_price=501),
        ],
    )

    message = build_markdown_v2_message(
        order=order,
        filter_result=FilterResult(matched=True, reason="amount_threshold"),
        image_urls={
            "6901111111111": "http://127.0.0.1:8123/6901111111111.jpg",
            "6902222222222": "http://127.0.0.1:8123/6902222222222.jpg",
        },
        max_images=1,
    )

    assert "SO-001" in message
    assert "amount_threshold" in message
    assert "6901111111111" in message
    assert "![](http://127.0.0.1:8123/6901111111111.jpg)" in message
    assert "还有 1 张图片未展示" in message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_message_builder.py -v`
Expected: FAIL because the message builder does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
# src/wecom_sales_webhook_bot/message_builder.py
from __future__ import annotations

from wecom_sales_webhook_bot.filters import FilterResult
from wecom_sales_webhook_bot.models import SalesOrder


def build_markdown_v2_message(
    order: SalesOrder,
    filter_result: FilterResult,
    image_urls: dict[str, str],
    max_images: int,
) -> str:
    lines = [
        f"# 销售晒单",
        f"> 销售单号：`{order.order_no}`",
        f"> 销售时间：`{order.sold_at:%Y-%m-%d %H:%M:%S}`",
        f"> 门店：`{order.store_name}`",
        f"> 总额：`{order.total_amount:.2f}`",
        f"> 命中原因：`{filter_result.reason}`",
        "",
        "## 商品明细",
    ]

    for item in order.items:
        lines.append(
            f"- 条码：`{item.barcode}` 款号：`{item.style_no}` 单价：`{item.unit_price:.2f}` 数量：`{item.quantity}`"
        )

    lines.append("")
    lines.append("## 商品图片")

    unique_barcodes = []
    for item in order.items:
        if item.barcode in image_urls and item.barcode not in unique_barcodes:
            unique_barcodes.append(item.barcode)

    displayed = unique_barcodes[:max_images]
    for barcode in displayed:
        lines.append(f"![]({image_urls[barcode]})")

    omitted = len(unique_barcodes) - len(displayed)
    if omitted > 0:
        lines.append(f"> 还有 {omitted} 张图片未展示")

    missing = [item.barcode for item in order.items if item.barcode not in image_urls]
    if missing:
        lines.append(f"> 缺失图片条码：{', '.join(missing)}")

    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_message_builder.py -v`
Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/wecom_sales_webhook_bot/message_builder.py tests/test_message_builder.py
git commit -m "feat: render markdown v2 sales messages"
```

### Task 6: Add Webhook Delivery And Dry-Run Support

**Files:**
- Create: `src/wecom_sales_webhook_bot/wecom_client.py`
- Modify: `src/wecom_sales_webhook_bot/config.py`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_orchestrator.py
from wecom_sales_webhook_bot.wecom_client import WeComWebhookClient


class FakeSession:
    def __init__(self) -> None:
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append({"url": url, "json": json, "timeout": timeout})

        class Response:
            status_code = 200

            @staticmethod
            def raise_for_status() -> None:
                return None

        return Response()


def test_wecom_client_posts_markdown_message() -> None:
    session = FakeSession()
    client = WeComWebhookClient(
        webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
        timeout_seconds=5,
        retry_times=2,
        session=session,
    )

    client.send_markdown_v2("hello")

    assert session.calls == [
        {
            "url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
            "json": {"msgtype": "markdown_v2", "markdown_v2": {"content": "hello"}},
            "timeout": 5,
        }
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_orchestrator.py::test_wecom_client_posts_markdown_message -v`
Expected: FAIL because the webhook client does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
# src/wecom_sales_webhook_bot/wecom_client.py
from __future__ import annotations

import time
from typing import Protocol

import requests


class HttpSession(Protocol):
    def post(self, url: str, json: dict, timeout: int): ...


class WeComWebhookClient:
    def __init__(
        self,
        webhook_url: str,
        timeout_seconds: int,
        retry_times: int,
        session: HttpSession | None = None,
    ) -> None:
        self._webhook_url = webhook_url
        self._timeout_seconds = timeout_seconds
        self._retry_times = retry_times
        self._session = session or requests.Session()

    def send_markdown_v2(self, content: str) -> None:
        payload = {"msgtype": "markdown_v2", "markdown_v2": {"content": content}}
        last_error: Exception | None = None
        for attempt in range(self._retry_times + 1):
            try:
                response = self._session.post(
                    self._webhook_url,
                    json=payload,
                    timeout=self._timeout_seconds,
                )
                response.raise_for_status()
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < self._retry_times:
                    time.sleep(1)
        if last_error is not None:
            raise last_error
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_orchestrator.py::test_wecom_client_posts_markdown_message -v`
Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/wecom_sales_webhook_bot/wecom_client.py tests/test_orchestrator.py
git commit -m "feat: add wecom webhook delivery client"
```

### Task 7: Wire The Run-Once Workflow

**Files:**
- Create: `src/wecom_sales_webhook_bot/orchestrator.py`
- Modify: `src/wecom_sales_webhook_bot/state_store.py`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_orchestrator.py
from datetime import datetime
from pathlib import Path

from wecom_sales_webhook_bot.filters import FilterResult
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder
from wecom_sales_webhook_bot.orchestrator import run_once


class FakeDataSource:
    def load_orders(self):
        return [
            SalesOrder(
                order_no="SO-001",
                sold_at=datetime(2026, 4, 20, 10, 0, 0),
                store_name="上海一店",
                total_amount=1200,
                items=[SalesLineItem(barcode="6901111111111", style_no="A1001", unit_price=699)],
            )
        ]


class FakeFilter:
    def evaluate(self, order):
        return FilterResult(matched=True, reason="amount_threshold")


class FakeImageProvider:
    def get_url(self, barcode):
        return f"http://127.0.0.1:8123/{barcode}.jpg"


class FakeClient:
    def __init__(self):
        self.messages = []

    def send_markdown_v2(self, content):
        self.messages.append(content)


def test_run_once_sends_only_new_matching_orders(tmp_path: Path) -> None:
    client = FakeClient()
    state_file = tmp_path / "state.json"

    sent = run_once(
        data_source=FakeDataSource(),
        sales_filter=FakeFilter(),
        image_provider=FakeImageProvider(),
        state_file=state_file,
        webhook_client=client,
        max_images=8,
        dry_run=False,
    )

    assert sent == ["SO-001"]
    assert len(client.messages) == 1

    sent_again = run_once(
        data_source=FakeDataSource(),
        sales_filter=FakeFilter(),
        image_provider=FakeImageProvider(),
        state_file=state_file,
        webhook_client=client,
        max_images=8,
        dry_run=False,
    )

    assert sent_again == []
    assert len(client.messages) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_orchestrator.py::test_run_once_sends_only_new_matching_orders -v`
Expected: FAIL because `run_once` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
# src/wecom_sales_webhook_bot/state_store.py
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class PushStateStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text('{"last_scan_at": null, "pushed_orders": {}}', encoding="utf-8")

    def _read(self) -> dict:
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, payload: dict) -> None:
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def has_pushed(self, order_no: str) -> bool:
        return order_no in self._read()["pushed_orders"]

    def mark_pushed(self, order_no: str, sold_at: datetime) -> None:
        payload = self._read()
        payload["pushed_orders"][order_no] = sold_at.isoformat()
        self._write(payload)

    def get_last_scan_at(self) -> datetime | None:
        raw = self._read()["last_scan_at"]
        return datetime.fromisoformat(raw) if raw else None

    def set_last_scan_at(self, scanned_at: datetime) -> None:
        payload = self._read()
        payload["last_scan_at"] = scanned_at.isoformat()
        self._write(payload)

    def clear(self) -> None:
        self._write({"last_scan_at": None, "pushed_orders": {}})
```

```python
# src/wecom_sales_webhook_bot/orchestrator.py
from __future__ import annotations

from datetime import datetime

from wecom_sales_webhook_bot.message_builder import build_markdown_v2_message
from wecom_sales_webhook_bot.state_store import PushStateStore


def run_once(
    data_source,
    sales_filter,
    image_provider,
    state_file,
    webhook_client,
    max_images: int,
    dry_run: bool,
) -> list[str]:
    state_store = PushStateStore(state_file)
    last_scan_at = state_store.get_last_scan_at()
    sent_orders: list[str] = []

    for order in data_source.load_orders():
        if last_scan_at and order.sold_at <= last_scan_at:
            continue
        if state_store.has_pushed(order.order_no):
            continue

        filter_result = sales_filter.evaluate(order)
        if not filter_result.matched:
            continue

        image_urls = {}
        for item in order.items:
            url = image_provider.get_url(item.barcode)
            if url:
                image_urls[item.barcode] = url

        content = build_markdown_v2_message(
            order=order,
            filter_result=filter_result,
            image_urls=image_urls,
            max_images=max_images,
        )
        if not dry_run:
            webhook_client.send_markdown_v2(content)
        state_store.mark_pushed(order.order_no, order.sold_at)
        sent_orders.append(order.order_no)

    state_store.set_last_scan_at(datetime.now())
    return sent_orders
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_orchestrator.py::test_run_once_sends_only_new_matching_orders -v`
Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/wecom_sales_webhook_bot/state_store.py src/wecom_sales_webhook_bot/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: orchestrate one-shot webhook run"
```

### Task 8: Add CLI Commands, Sample Config, And End-To-End Verification

**Files:**
- Create: `src/wecom_sales_webhook_bot/cli.py`
- Create: `config.example.yaml`
- Modify: `README.md`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_orchestrator.py
from pathlib import Path

from wecom_sales_webhook_bot.cli import build_parser


def test_cli_exposes_run_once_schedule_and_clear_state_commands() -> None:
    parser = build_parser()

    run_once_args = parser.parse_args(["run-once", "--config", "config.yaml"])
    clear_state_args = parser.parse_args(["clear-state", "--config", "config.yaml"])
    schedule_args = parser.parse_args(["schedule", "--config", "config.yaml"])

    assert run_once_args.command == "run-once"
    assert clear_state_args.command == "clear-state"
    assert schedule_args.command == "schedule"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_orchestrator.py::test_cli_exposes_run_once_schedule_and_clear_state_commands -v`
Expected: FAIL because the CLI module does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
# src/wecom_sales_webhook_bot/cli.py
from __future__ import annotations

import argparse
import time
from pathlib import Path

from wecom_sales_webhook_bot.config import load_config
from wecom_sales_webhook_bot.csv_source import CsvSalesDataSource
from wecom_sales_webhook_bot.filters import SalesFilter
from wecom_sales_webhook_bot.image_service import LocalImageUrlProvider, start_image_server
from wecom_sales_webhook_bot.orchestrator import run_once
from wecom_sales_webhook_bot.state_store import PushStateStore
from wecom_sales_webhook_bot.wecom_client import WeComWebhookClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("run-once", "schedule", "serve-images", "clear-state"):
        command = subparsers.add_parser(name)
        command.add_argument("--config", required=True)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = load_config(Path(args.config))

    if args.command == "serve-images":
        start_image_server(
            image_dir=config.image_service.image_dir,
            host=config.image_service.host,
            port=config.image_service.port,
        )
        while True:
            time.sleep(3600)

    if args.command == "clear-state":
        PushStateStore(config.runtime.state_file).clear()
        return

    data_source = CsvSalesDataSource(config.csv, base_dir=Path(args.config).resolve().parent)
    sales_filter = SalesFilter(
        amount_threshold=config.rules.amount_threshold,
        style_whitelist=config.rules.style_whitelist,
    )
    image_provider = LocalImageUrlProvider(
        image_dir=config.image_service.image_dir,
        base_url=f"http://{config.image_service.host}:{config.image_service.port}",
    )
    webhook_client = WeComWebhookClient(
        webhook_url=config.wecom.webhook_url,
        timeout_seconds=config.wecom.timeout_seconds,
        retry_times=config.wecom.retry_times,
    )

    if args.command == "run-once":
        run_once(
            data_source=data_source,
            sales_filter=sales_filter,
            image_provider=image_provider,
            state_file=config.runtime.state_file,
            webhook_client=webhook_client,
            max_images=config.runtime.max_images_per_message,
            dry_run=config.runtime.dry_run,
        )
        return

    if args.command == "schedule":
        while True:
            run_once(
                data_source=data_source,
                sales_filter=sales_filter,
                image_provider=image_provider,
                state_file=config.runtime.state_file,
                webhook_client=webhook_client,
                max_images=config.runtime.max_images_per_message,
                dry_run=config.runtime.dry_run,
            )
            time.sleep(config.runtime.scan_interval_seconds)
```

```yaml
# config.example.yaml
csv:
  path: ./data/sales.csv
  encoding: utf-8-sig
  field_mapping:
    order_no: 销售单号
    sold_at: 销售日期（时间）
    store_name: 销售门店
    total_amount: 销售单总额
    barcode: 商品条码
    style_no: 产品款号
    unit_price: 产品单价
image_service:
  host: 127.0.0.1
  port: 8123
  image_dir: ./images
wecom:
  webhook_url: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=replace-me
  timeout_seconds: 5
  retry_times: 2
rules:
  amount_threshold: 1000
  style_whitelist: []
runtime:
  scan_interval_seconds: 600
  max_images_per_message: 8
  state_file: ./var/push-state.json
  dry_run: true
```

```markdown
# README.md

## WeCom Sales Webhook Bot

### Setup

1. `python -m venv .venv`
2. `.venv\\Scripts\\activate`
3. `python -m pip install -e .[dev]`
4. Copy `config.example.yaml` to `config.yaml`

### Useful Commands

- `python -m wecom_sales_webhook_bot.cli run-once --config config.yaml`
- `python -m wecom_sales_webhook_bot.cli schedule --config config.yaml`
- `python -m wecom_sales_webhook_bot.cli serve-images --config config.yaml`
- `python -m wecom_sales_webhook_bot.cli clear-state --config config.yaml`
```

- [ ] **Step 4: Run test and smoke verification**

Run: `python -m pytest tests/test_orchestrator.py::test_cli_exposes_run_once_schedule_and_clear_state_commands -v`
Expected: PASS with `1 passed`

Run: `python -m pytest -v`
Expected: PASS with all tests green

Run: `python -m wecom_sales_webhook_bot.cli run-once --config config.example.yaml`
Expected: No crash. In `dry_run: true` mode it should process matching orders without sending a real webhook.

- [ ] **Step 5: Commit**

```bash
git add src/wecom_sales_webhook_bot/cli.py config.example.yaml README.md tests/test_orchestrator.py
git commit -m "feat: add cli commands and usage docs"
```

### Task 9: Harden Edge Cases And Logging

**Files:**
- Modify: `src/wecom_sales_webhook_bot/csv_source.py`
- Modify: `src/wecom_sales_webhook_bot/message_builder.py`
- Modify: `src/wecom_sales_webhook_bot/orchestrator.py`
- Modify: `tests/test_csv_source.py`
- Modify: `tests/test_message_builder.py`
- Modify: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_csv_source.py
from pathlib import Path

from wecom_sales_webhook_bot.config import load_config
from wecom_sales_webhook_bot.csv_source import CsvSalesDataSource


def test_csv_source_skips_rows_missing_required_fields(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
csv:
  path: ./sales.csv
  encoding: utf-8-sig
  field_mapping:
    order_no: 销售单号
    sold_at: 销售日期（时间）
    store_name: 销售门店
    total_amount: 销售单总额
    barcode: 商品条码
    style_no: 产品款号
    unit_price: 产品单价
image_service:
  host: 127.0.0.1
  port: 8123
  image_dir: ./images
wecom:
  webhook_url: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test
  timeout_seconds: 5
  retry_times: 2
rules:
  amount_threshold: 1000
  style_whitelist: []
runtime:
  scan_interval_seconds: 600
  max_images_per_message: 8
  state_file: ./var/push-state.json
  dry_run: false
""".strip(),
        encoding="utf-8",
    )
    sales_file = tmp_path / "sales.csv"
    sales_file.write_text(
        "\n".join(
            [
                "销售单号,销售日期（时间）,销售门店,销售单总额,商品条码,产品款号,产品单价",
                "SO-001,2026-04-20 10:00:00,上海一店,1200,6901111111111,A1001,699",
                "SO-002,2026-04-20 10:05:00,上海一店,1300,,B2002,1300",
            ]
        ),
        encoding="utf-8-sig",
    )

    config = load_config(config_file)
    orders = CsvSalesDataSource(config.csv, base_dir=tmp_path).load_orders()

    assert [order.order_no for order in orders] == ["SO-001"]
```

```python
# tests/test_message_builder.py
from datetime import datetime

from wecom_sales_webhook_bot.filters import FilterResult
from wecom_sales_webhook_bot.message_builder import build_markdown_v2_message
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder


def test_message_builder_truncates_when_content_exceeds_limit() -> None:
    order = SalesOrder(
        order_no="SO-LONG",
        sold_at=datetime(2026, 4, 20, 10, 0, 0),
        store_name="上海一店",
        total_amount=9999,
        items=[
            SalesLineItem(barcode=f"690{i:010d}", style_no=f"STYLE-{i}", unit_price=100 + i)
            for i in range(20)
        ],
    )

    image_urls = {item.barcode: f"http://127.0.0.1:8123/{item.barcode}.jpg" for item in order.items}

    message = build_markdown_v2_message(
        order=order,
        filter_result=FilterResult(matched=True, reason="amount_threshold"),
        image_urls=image_urls,
        max_images=8,
        max_bytes=1200,
    )

    assert len(message.encode("utf-8")) <= 1200
    assert "商品明细已截断" in message
```

```python
# tests/test_orchestrator.py
from pathlib import Path

from wecom_sales_webhook_bot.orchestrator import run_once


class BrokenDataSource:
    def load_orders(self):
        raise RuntimeError("csv unavailable")


class DummyFilter:
    def evaluate(self, order):
        raise AssertionError("should not be called")


class DummyImageProvider:
    def get_url(self, barcode):
        raise AssertionError("should not be called")


class DummyClient:
    def send_markdown_v2(self, content):
        raise AssertionError("should not be called")


def test_run_once_does_not_advance_state_when_csv_read_fails(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"

    sent = run_once(
        data_source=BrokenDataSource(),
        sales_filter=DummyFilter(),
        image_provider=DummyImageProvider(),
        state_file=state_file,
        webhook_client=DummyClient(),
        max_images=8,
        dry_run=False,
    )

    assert sent == []
    assert state_file.exists()
    assert '"last_scan_at": null' in state_file.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_csv_source.py::test_csv_source_skips_rows_missing_required_fields -v`
Expected: FAIL because the current CSV parser does not skip malformed rows.

Run: `python -m pytest tests/test_message_builder.py::test_message_builder_truncates_when_content_exceeds_limit -v`
Expected: FAIL because the current message builder has no byte-limit handling.

Run: `python -m pytest tests/test_orchestrator.py::test_run_once_does_not_advance_state_when_csv_read_fails -v`
Expected: FAIL because the current orchestrator does not catch CSV read errors.

- [ ] **Step 3: Write minimal implementation**

```python
# src/wecom_sales_webhook_bot/csv_source.py
from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path

from wecom_sales_webhook_bot.config import CsvConfig
from wecom_sales_webhook_bot.models import SalesLineItem, SalesOrder


LOGGER = logging.getLogger(__name__)


class CsvSalesDataSource:
    def __init__(self, config: CsvConfig, base_dir: Path) -> None:
        self._config = config
        self._base_dir = base_dir

    def load_orders(self) -> list[SalesOrder]:
        csv_path = (self._base_dir / self._config.path).resolve()
        mapping = self._config.field_mapping
        grouped: dict[str, dict] = {}

        with csv_path.open("r", encoding=self._config.encoding, newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                try:
                    required = {
                        "order_no": row[mapping["order_no"]].strip(),
                        "sold_at": row[mapping["sold_at"]].strip(),
                        "store_name": row[mapping["store_name"]].strip(),
                        "total_amount": row[mapping["total_amount"]].strip(),
                        "barcode": row[mapping["barcode"]].strip(),
                        "style_no": row[mapping["style_no"]].strip(),
                        "unit_price": row[mapping["unit_price"]].strip(),
                    }
                    if any(value == "" for value in required.values()):
                        raise ValueError("required csv field is empty")
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning("skip malformed csv row: %s", exc)
                    continue

                order_no = required["order_no"]
                item = SalesLineItem(
                    barcode=required["barcode"],
                    style_no=required["style_no"],
                    unit_price=float(required["unit_price"]),
                    quantity=int(row.get(mapping.get("quantity", ""), "1") or "1"),
                )
                if order_no not in grouped:
                    grouped[order_no] = {
                        "order_no": order_no,
                        "sold_at": datetime.strptime(required["sold_at"], "%Y-%m-%d %H:%M:%S"),
                        "store_name": required["store_name"],
                        "total_amount": float(required["total_amount"]),
                        "items": [],
                    }
                grouped[order_no]["items"].append(item)

        return [SalesOrder(**payload) for payload in grouped.values()]
```

```python
# src/wecom_sales_webhook_bot/message_builder.py
from __future__ import annotations

from wecom_sales_webhook_bot.filters import FilterResult
from wecom_sales_webhook_bot.models import SalesOrder


def build_markdown_v2_message(
    order: SalesOrder,
    filter_result: FilterResult,
    image_urls: dict[str, str],
    max_images: int,
    max_bytes: int = 4096,
) -> str:
    header = [
        "# 销售晒单",
        f"> 销售单号：`{order.order_no}`",
        f"> 销售时间：`{order.sold_at:%Y-%m-%d %H:%M:%S}`",
        f"> 门店：`{order.store_name}`",
        f"> 总额：`{order.total_amount:.2f}`",
        f"> 命中原因：`{filter_result.reason}`",
        "",
        "## 商品明细",
    ]

    detail_lines = [
        f"- 条码：`{item.barcode}` 款号：`{item.style_no}` 单价：`{item.unit_price:.2f}` 数量：`{item.quantity}`"
        for item in order.items
    ]

    unique_barcodes = []
    for item in order.items:
        if item.barcode in image_urls and item.barcode not in unique_barcodes:
            unique_barcodes.append(item.barcode)

    image_lines = ["", "## 商品图片"] + [f"![]({image_urls[barcode]})" for barcode in unique_barcodes[:max_images]]

    omitted_images = len(unique_barcodes) - min(len(unique_barcodes), max_images)
    if omitted_images > 0:
        image_lines.append(f"> 还有 {omitted_images} 张图片未展示")

    missing = [item.barcode for item in order.items if item.barcode not in image_urls]
    if missing:
        image_lines.append(f"> 缺失图片条码：{', '.join(missing)}")

    lines = header + detail_lines + image_lines
    while len("\n".join(lines).encode("utf-8")) > max_bytes and len(detail_lines) > 1:
        detail_lines.pop()
        lines = header + detail_lines + ["> 商品明细已截断"] + image_lines

    return "\n".join(lines)
```

```python
# src/wecom_sales_webhook_bot/orchestrator.py
from __future__ import annotations

import logging
from datetime import datetime

from wecom_sales_webhook_bot.message_builder import build_markdown_v2_message
from wecom_sales_webhook_bot.state_store import PushStateStore


LOGGER = logging.getLogger(__name__)


def run_once(
    data_source,
    sales_filter,
    image_provider,
    state_file,
    webhook_client,
    max_images: int,
    dry_run: bool,
) -> list[str]:
    state_store = PushStateStore(state_file)
    last_scan_at = state_store.get_last_scan_at()
    sent_orders: list[str] = []

    try:
        orders = data_source.load_orders()
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("failed to load csv orders: %s", exc)
        return []

    for order in orders:
        if last_scan_at and order.sold_at <= last_scan_at:
            continue
        if state_store.has_pushed(order.order_no):
            continue

        filter_result = sales_filter.evaluate(order)
        if not filter_result.matched:
            continue

        image_urls = {}
        for item in order.items:
            url = image_provider.get_url(item.barcode)
            if url:
                image_urls[item.barcode] = url

        content = build_markdown_v2_message(
            order=order,
            filter_result=filter_result,
            image_urls=image_urls,
            max_images=max_images,
        )
        if not dry_run:
            webhook_client.send_markdown_v2(content)
        state_store.mark_pushed(order.order_no, order.sold_at)
        sent_orders.append(order.order_no)

    state_store.set_last_scan_at(datetime.now())
    return sent_orders
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_csv_source.py::test_csv_source_skips_rows_missing_required_fields -v`
Expected: PASS with `1 passed`

Run: `python -m pytest tests/test_message_builder.py::test_message_builder_truncates_when_content_exceeds_limit -v`
Expected: PASS with `1 passed`

Run: `python -m pytest tests/test_orchestrator.py::test_run_once_does_not_advance_state_when_csv_read_fails -v`
Expected: PASS with `1 passed`

- [ ] **Step 5: Commit**

```bash
git add src/wecom_sales_webhook_bot/csv_source.py src/wecom_sales_webhook_bot/message_builder.py src/wecom_sales_webhook_bot/orchestrator.py tests/test_csv_source.py tests/test_message_builder.py tests/test_orchestrator.py
git commit -m "feat: harden csv parsing and message truncation"
```
