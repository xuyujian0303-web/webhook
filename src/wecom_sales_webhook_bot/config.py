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
