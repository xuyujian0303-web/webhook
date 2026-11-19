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


def test_local_image_provider_accepts_uppercase_extension_for_style_number(
    tmp_path: Path,
) -> None:
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    (image_dir / "CO15107HBK0.JPG").write_bytes(b"fake-jpg")

    provider = LocalImageUrlProvider(
        image_dir=image_dir,
        base_url="http://127.0.0.1:8123",
    )

    assert provider.get_url("CO15107HBK0") == "http://127.0.0.1:8123/CO15107HBK0.JPG"


def test_local_image_provider_matches_trimmed_barcode_prefix(
    tmp_path: Path,
) -> None:
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    (image_dir / "GCO15107HIBK0B6.JPG").write_bytes(b"fake-jpg")

    provider = LocalImageUrlProvider(
        image_dir=image_dir,
        base_url="http://127.0.0.1:8123",
    )

    assert (
        provider.get_url("GCO15107HIBK0B6440040")
        == "http://127.0.0.1:8123/GCO15107HIBK0B6.JPG"
    )


def test_local_image_provider_matches_case_insensitive_filename_stem(
    tmp_path: Path,
) -> None:
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    (image_dir / "co15107hbk0.jpg").write_bytes(b"fake-jpg")

    provider = LocalImageUrlProvider(
        image_dir=image_dir,
        base_url="http://127.0.0.1:8123",
    )

    assert provider.get_url("CO15107HBK0") == "http://127.0.0.1:8123/co15107hbk0.jpg"


def test_local_image_provider_prefers_csv_mapping_over_local_file(
    tmp_path: Path,
) -> None:
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    (image_dir / "CO11101TBK0.jpg").write_bytes(b"fake-jpg")
    image_map_csv = tmp_path / "images.csv"
    image_map_csv.write_text(
        "image_key,image_url\nCO11101TBK0,https://cdn.example.com/custom.jpg\n",
        encoding="utf-8",
    )

    provider = LocalImageUrlProvider(
        image_dir=image_dir,
        base_url="http://127.0.0.1:8123",
        image_map_csv=image_map_csv,
    )

    assert provider.get_url("CO11101TBK0") == "https://cdn.example.com/custom.jpg"


def test_local_image_provider_falls_back_to_local_when_csv_has_no_match(
    tmp_path: Path,
) -> None:
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    (image_dir / "SKCH561ABU0.JPG").write_bytes(b"fake-jpg")
    image_map_csv = tmp_path / "images.csv"
    image_map_csv.write_text(
        "image_key,image_url\nOTHER_KEY,https://cdn.example.com/custom.jpg\n",
        encoding="utf-8",
    )

    provider = LocalImageUrlProvider(
        image_dir=image_dir,
        base_url="http://127.0.0.1:8123",
        image_map_csv=image_map_csv,
    )

    assert provider.get_url("SKCH561ABU0") == "http://127.0.0.1:8123/SKCH561ABU0.JPG"
