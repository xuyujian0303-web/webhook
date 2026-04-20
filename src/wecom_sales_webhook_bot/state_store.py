from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class PushStateStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text(
                '{"last_scan_at": null, "pushed_orders": {}}', encoding="utf-8"
            )

    def _read(self) -> dict:
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, payload: dict) -> None:
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

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
