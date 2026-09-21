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
