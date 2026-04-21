from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
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
    state_file: Optional[Path]
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
    csv: Optional[CsvConfig]
    image_service: Optional[ImageServiceConfig]
    wecom: WeComConfig
    rules: Optional[RulesConfig]
    runtime: RuntimeConfig
    backend: Optional[BackendConfig]
    api: Optional[ApiConfig]


def load_config(path: Path) -> AppConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    csv_section = raw.get("csv")
    csv_cfg = CsvConfig(
        path=Path(csv_section["path"]),
        encoding=csv_section["encoding"],
        field_mapping=dict(csv_section["field_mapping"]),
    ) if csv_section else None

    img_section = raw.get("image_service")
    img_cfg = ImageServiceConfig(
        host=img_section["host"],
        port=int(img_section["port"]),
        image_dir=Path(img_section["image_dir"]),
    ) if img_section else None

    rules_section = raw.get("rules")
    rules_cfg = RulesConfig(
        amount_threshold=float(rules_section["amount_threshold"]),
        style_whitelist=set(rules_section["style_whitelist"]),
    ) if rules_section else None

    rt = raw.get("runtime", {})
    state_file = Path(rt["state_file"]) if "state_file" in rt else None
    runtime_cfg = RuntimeConfig(
        scan_interval_seconds=int(rt["scan_interval_seconds"]),
        max_images_per_message=int(rt["max_images_per_message"]),
        state_file=state_file,
        dry_run=bool(rt.get("dry_run", False)),
    )

    backend_section = raw.get("backend")
    backend_cfg = BackendConfig(
        database_url=backend_section["database_url"],
        secret_key=backend_section["secret_key"],
        host=backend_section["host"],
        port=int(backend_section["port"]),
        bootstrap_admin_username=backend_section["bootstrap_admin_username"],
        bootstrap_admin_password=backend_section["bootstrap_admin_password"],
    ) if backend_section else None

    api_section = raw.get("api")
    api_cfg = ApiConfig(
        sales_base_url=api_section["sales_base_url"],
        sales_token=api_section["sales_token"],
        sales_path=api_section["sales_path"],
        timeout_seconds=int(api_section["timeout_seconds"]),
    ) if api_section else None

    return AppConfig(
        csv=csv_cfg,
        image_service=img_cfg,
        wecom=WeComConfig(
            webhook_url=raw["wecom"]["webhook_url"],
            timeout_seconds=int(raw["wecom"]["timeout_seconds"]),
            retry_times=int(raw["wecom"]["retry_times"]),
        ),
        rules=rules_cfg,
        runtime=runtime_cfg,
        backend=backend_cfg,
        api=api_cfg,
    )
