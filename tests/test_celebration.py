from datetime import datetime
import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from wecom_sales_webhook_bot.celebration import (
    CelebrationStateStore,
    qualifies_for_celebration,
    webhook_target_id,
)
from wecom_sales_webhook_bot.desktop_gui import DesktopApp
from wecom_sales_webhook_bot.models import SalesOrder
from wecom_sales_webhook_bot.orchestrator import run_once
from wecom_sales_webhook_bot.runtime_settings import RuntimeControls
from wecom_sales_webhook_bot.rule_service import RuleConditionDTO, RuleGroupDTO
from wecom_sales_webhook_bot.wecom_client import WeComWebhookClient


def order(amount: float, kind: str = "sale") -> SalesOrder:
    return SalesOrder(
        order_no=f"SO-{kind}-{amount}",
        sold_at=datetime(2026, 4, 20, 12),
        store_name="G00J",
        total_amount=amount,
        document_type=kind,
    )


@pytest.mark.parametrize(
    ("amount", "expected"),
    [(100000, False), (100000.01, True), (0, False), (-1, False)],
)
def test_celebration_uses_strict_positive_threshold(amount, expected) -> None:
    assert qualifies_for_celebration(order(amount), "100000") is expected


def test_zero_exchange_and_negative_return_do_not_qualify() -> None:
    assert not qualifies_for_celebration(order(0, "exchange"), "100000")
    assert not qualifies_for_celebration(order(-500, "return"), "100000")


def test_state_store_tracks_success_per_webhook(tmp_path: Path) -> None:
    store = CelebrationStateStore(tmp_path / "celebration-state.json")
    store.record_image("SO-1", tmp_path / "SO-1.png")
    store.mark_target_sent("SO-1", "group-a")
    assert store.sent_targets("SO-1") == {"group-a"}
    assert store.get("SO-1")["image_path"].endswith("SO-1.png")


def test_wecom_image_payload_uses_base64_and_raw_md5(tmp_path: Path) -> None:
    image = tmp_path / "notice.png"
    data = b"\x89PNG\r\n\x1a\nminimal test bytes"
    image.write_bytes(data)

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"errcode": 0}

    class Session:
        def __init__(self):
            self.payload = None

        def post(self, url, json, timeout):
            self.payload = json
            return Response()

    session = Session()
    client = WeComWebhookClient("https://example.invalid", 5, 0, session=session)
    client.send_image(image)
    assert session.payload == {
        "msgtype": "image",
        "image": {
            "base64": base64.b64encode(data).decode("ascii"),
            "md5": hashlib.md5(data).hexdigest(),
        },
    }


class CelebrationDataSource:
    def __init__(self, candidate):
        self.candidate = candidate
        self.calls = 0

    def load_orders(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("ordinary rule query failed")
        return [self.candidate]


class ImageClient:
    def __init__(self):
        self.images = []

    def send_image(self, path):
        self.images.append(Path(path))


class OrdinaryClient:
    def send_markdown_v2(self, content):
        raise AssertionError("ordinary push should have no queried orders")


def test_celebration_does_not_run_when_ordinary_query_fails(tmp_path: Path) -> None:
    candidate = order(120000)
    source = CelebrationDataSource(candidate)
    target = ImageClient()
    group = RuleGroupDTO(
        name="ordinary",
        match_mode="all",
        conditions=[RuleConditionDTO(field_name="total_amount", operator="gte", value=1)],
    )
    controls = RuntimeControls(1200, 8, 0, "00:00", "23:59")
    sent = run_once(
        data_source=source,
        sales_filter=None,
        image_provider=None,
        state_file=tmp_path / "push-state.json",
        webhook_client=OrdinaryClient(),
        max_images=8,
        dry_run=False,
        database_rule_groups=[group],
        runtime_controls=controls,
        service_started_at=datetime(2026, 4, 20),
        now_func=lambda: datetime(2026, 4, 20, 12),
        celebration_settings={
            "enabled": True,
            "threshold": "100000",
            "template_path": tmp_path / "template.pptx",
            "output_dir": tmp_path / "images",
            "content_fields": [],
        },
        celebration_targets={"group": target},
        celebration_generator=lambda *args: tmp_path / "images" / "notice.png",
    )
    assert sent == []
    assert target.images == []
    assert source.calls == 1


def test_celebration_requires_ordinary_rule_match_and_deduplicates(tmp_path: Path) -> None:
    from wecom_sales_webhook_bot.filters import SalesFilter

    matched = SalesOrder(
        order_no="SO-G00J-TEST-002",
        sold_at=datetime(2026, 4, 20, 12),
        store_name="G00J",
        performance_org="G876",
        total_amount=120000,
        document_type="sale",
        items=[],
    )
    outside_rule = SalesOrder(
        order_no="SO-OUTSIDE-RULE",
        sold_at=matched.sold_at,
        store_name="G002",
        total_amount=130000,
        document_type="sale",
        items=[],
    )

    class DataSource:
        def load_orders(self, **kwargs):
            return [matched, outside_rule]

    class MarkdownClient:
        def __init__(self):
            self.messages = []

        def send_markdown_v2(self, content):
            self.messages.append(content)

    class ImageClient:
        def __init__(self):
            self.images = []

        def send_image(self, path):
            self.images.append(Path(path))

    ordinary = MarkdownClient()
    target = ImageClient()
    generated_for = []
    generated_regions = []
    group = RuleGroupDTO(
        name="only G00J",
        match_mode="all",
        conditions=[RuleConditionDTO(field_name="store_name", operator="equals", value="G00J")],
    )

    def generate(order_arg, *_args):
        from PIL import Image

        generated_for.append(order_arg.order_no)
        generated_regions.append(dict(order_arg.attributes or {}))
        image_path = tmp_path / "images" / f"{order_arg.order_no}.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1, 1), "red").save(image_path)
        return image_path

    kwargs = dict(
        data_source=DataSource(),
        sales_filter=SalesFilter(0, set()),
        image_provider=None,
        state_file=tmp_path / "push-state.json",
        webhook_client=ordinary,
        max_images=8,
        dry_run=False,
        database_rule_groups=[group],
        runtime_controls=RuntimeControls(1200, 8, 0, "00:00", "23:59"),
        service_started_at=datetime(2026, 4, 20),
        now_func=lambda: datetime(2026, 4, 20, 12),
        celebration_settings={
            "enabled": True,
            "threshold": "100000",
            "template_path": tmp_path / "template.svg",
            "output_dir": tmp_path / "images",
            "content_fields": [],
            "region_mapping": {"G00J": "华南区", "G876": "华东区"},
        },
        celebration_targets={"group": target},
        celebration_generator=generate,
    )

    assert run_once(**kwargs) == ["SO-G00J-TEST-002"]
    # A second scan finds the already-pushed order, but its celebration is sent
    # only once to each selected webhook target.
    assert run_once(**kwargs) == []
    assert len(ordinary.messages) == 1
    assert target.images == [tmp_path / "images" / "SO-G00J-TEST-002.png"]
    assert generated_for == ["SO-G00J-TEST-002"]
    assert generated_regions[0]["store_region"] == "华南区"
    assert generated_regions[0]["performance_region"] == "华东区"
    assert generated_regions[0]["region"] == "华东区"


def test_history_celebration_status_reads_per_order_sent_state(tmp_path: Path) -> None:
    state_path = tmp_path / "push-state.json"
    celebration_path = state_path.with_name("celebration-state.json")
    celebration_path.write_text(json.dumps({"orders": {
        "SO-SENT": {"sent_targets": {"group": "2026-04-20T12:00:00"}},
        "SO-FAILED": {"sent_targets": {}},
    }}), encoding="utf-8")
    app_stub = SimpleNamespace(_state_file=lambda: state_path)
    assert DesktopApp._celebration_sent_orders(app_stub) == {"SO-SENT"}


def test_webhook_target_ids_do_not_expose_webhook_urls() -> None:
    value = webhook_target_id("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=secret")
    assert len(value) == 16
    assert "secret" not in value
