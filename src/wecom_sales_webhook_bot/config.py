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
class BackendConfig:
    database_url: str
    secret_key: str
    host: str
    port: int
    bootstrap_admin_username: str
    bootstrap_admin_password: str


@dataclass(frozen=True)
class ApiConfig:
    sales_base_url: str
    sales_token: str
    sales_path: str
    timeout_seconds: int


@dataclass(frozen=True)
class AppConfig:
    csv: CsvConfig
    image_service: ImageServiceConfig
    wecom: WeComConfig
    rules: RulesConfig
    runtime: RuntimeConfig
    backend: BackendConfig
    api: ApiConfig


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
        backend=BackendConfig(
            database_url=raw["backend"]["database_url"],
            secret_key=raw["backend"]["secret_key"],
            host=raw["backend"]["host"],
            port=int(raw["backend"]["port"]),
            bootstrap_admin_username=raw["backend"]["bootstrap_admin_username"],
            bootstrap_admin_password=raw["backend"]["bootstrap_admin_password"],
        ),
        api=ApiConfig(
            sales_base_url=raw["api"]["sales_base_url"],
            sales_token=raw["api"]["sales_token"],
            sales_path=raw["api"]["sales_path"],
            timeout_seconds=int(raw["api"]["timeout_seconds"]),
        ),
    )
