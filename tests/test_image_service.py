from pathlib import Path

from wecom_sales_webhook_bot.image_service import LocalImageUrlProvider


def test_local_image_provider_returns_url_for_existing_barcode(
    tmp_path: Path,
) -> None:
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    (image_dir / "6901111111111.jpg").write_bytes(b"fake-jpg")

    provider = LocalImageUrlProvider(
        image_dir=image_dir,
        base_url="http://127.0.0.1:8123",
    )

    assert provider.get_url("6901111111111") == "http://127.0.0.1:8123/6901111111111.jpg"
    assert provider.get_url("6909999999999") is None
