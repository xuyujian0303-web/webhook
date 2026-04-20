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
