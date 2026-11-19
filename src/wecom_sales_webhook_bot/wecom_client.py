from __future__ import annotations

import time
import base64
import hashlib
from typing import Protocol
from pathlib import Path

import requests


class HttpSession(Protocol):
    def post(self, url: str, json: dict, timeout: int): ...


class WeComWebhookClient:
    _MIN_SEND_INTERVAL_SECONDS = 3.1
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
        self._last_send_at: float | None = None

    def _send_payload(self, payload: dict) -> None:
        last_error: Exception | None = None
        for attempt in range(self._retry_times + 1):
            if self._last_send_at is not None:
                wait = self._MIN_SEND_INTERVAL_SECONDS - (time.monotonic() - self._last_send_at)
                if wait > 0:
                    time.sleep(wait)
            self._last_send_at = time.monotonic()
            try:
                response = self._session.post(
                    self._webhook_url,
                    json=payload,
                    timeout=self._timeout_seconds,
                )
                response.raise_for_status()
                response_payload = response.json()
                errcode = response_payload.get("errcode")
                if errcode != 0:
                    errmsg = response_payload.get("errmsg", "")
                    raise RuntimeError(
                        f"WeCom webhook rejected message: errcode={errcode} errmsg={errmsg}"
                    )
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < self._retry_times:
                    time.sleep(1)
        if last_error is not None:
            raise last_error

    def send_markdown_v2(self, content: str) -> None:
        payload = {"msgtype": "markdown_v2", "markdown_v2": {"content": content}}
        self._send_payload(payload)

    @staticmethod
    def _image_payload(image_bytes: bytes, suffix: str) -> dict:
        suffix = suffix.casefold()
        if suffix not in {".jpg", ".jpeg", ".png"}:
            raise ValueError("企业微信图片消息仅支持 JPG 或 PNG")
        if not image_bytes or len(image_bytes) > 2 * 1024 * 1024:
            raise ValueError("企业微信图片原始文件必须大于 0 且不超过 2 MB")
        is_png = image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        is_jpeg = image_bytes.startswith(b"\xff\xd8\xff")
        if (suffix == ".png" and not is_png) or (suffix in {".jpg", ".jpeg"} and not is_jpeg):
            raise ValueError("图片扩展名与实际文件格式不一致")
        return {"msgtype": "image", "image": {
            "base64": base64.b64encode(image_bytes).decode("ascii"),
            "md5": hashlib.md5(image_bytes).hexdigest(),
        }}

    def send_image_bytes(self, image_bytes: bytes, suffix: str = ".png") -> None:
        self._send_payload(self._image_payload(image_bytes, suffix))

    def send_image(self, image_path: Path) -> None:
        image_path = Path(image_path)
        self.send_image_bytes(image_path.read_bytes(), image_path.suffix)



class MultiWeComWebhookClient:
    """Fan out one message to every configured group webhook.

    A send is successful only when every target acknowledges it.  The caller
    then keeps the order unmarked when any group failed, avoiding silent gaps.
    """
    def __init__(self, clients: list[WeComWebhookClient]) -> None:
        if not clients:
            raise ValueError("at least one WeCom webhook URL is required")
        self._clients = clients

    def send_markdown_v2(self, content: str) -> None:
        errors: list[str] = []
        for index, client in enumerate(self._clients, 1):
            try:
                client.send_markdown_v2(content)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"webhook #{index}: {exc}")
        if errors:
            raise RuntimeError("; ".join(errors))

    def send_image_bytes(self, image_bytes: bytes, suffix: str = ".png") -> None:
        errors: list[str] = []
        for index, client in enumerate(self._clients, 1):
            try:
                client.send_image_bytes(image_bytes, suffix)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"webhook #{index}: {exc}")
        if errors:
            raise RuntimeError("; ".join(errors))

    def send_image(self, image_path: Path) -> None:
        image_path = Path(image_path)
        self.send_image_bytes(image_path.read_bytes(), image_path.suffix)
