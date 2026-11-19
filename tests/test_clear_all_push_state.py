from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from wecom_sales_webhook_bot.celebration import CelebrationStateStore
from wecom_sales_webhook_bot.desktop_gui import DesktopApp
from wecom_sales_webhook_bot.state_store import PushStateStore


class _Session:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def query(self, _model):
        return self

    def delete(self):
        return None

    def commit(self):
        return None


class _Status:
    value = ""

    def set(self, value: str) -> None:
        self.value = value


def test_clear_all_push_state_clears_ordinary_and_celebration_dedup(tmp_path: Path, monkeypatch) -> None:
    state_file = tmp_path / "push-state.json"
    ordinary = PushStateStore(state_file)
    ordinary.mark_pushed("SO-1", datetime(2026, 4, 20, 12))
    celebration = CelebrationStateStore(state_file.with_name("celebration-state.json"))
    celebration.record_image("SO-1", tmp_path / "SO-1.png")
    celebration.mark_target_sent("SO-1", "group-a")

    monkeypatch.setattr("wecom_sales_webhook_bot.desktop_gui.messagebox.askyesno", lambda *_args: True)
    app = SimpleNamespace(
        _rescan_from=lambda: datetime(2026, 4, 20),
        _factory=lambda: _Session(),
        _state_file=lambda: state_file,
        refresh_history=lambda: None,
        history_status=_Status(),
    )

    DesktopApp.clear_all_push_state(app)

    assert not PushStateStore(state_file).has_pushed("SO-1")
    assert CelebrationStateStore(state_file.with_name("celebration-state.json")).sent_targets("SO-1") == set()
    assert "已清空全部推送状态" in app.history_status.value
