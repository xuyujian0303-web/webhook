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
    image_map_csv: Optional[Path]


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
    push_interval_seconds: int
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
class DataSourceRefConfig:
    kind: str
    config_path: Path


@dataclass(frozen=True)
class AppConfig:
    csv: Optional[CsvConfig]
    image_service: Optional[ImageServiceConfig]
    wecom: WeComConfig
    rules: Optional[RulesConfig]
    runtime: RuntimeConfig
    backend: Optional[BackendConfig]
    api: Optional[ApiConfig]
    data_source: Optional[DataSourceRefConfig]
    store_mapping: dict[str, str]


def load_config(path: Path) -> AppConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    csv_section = raw.get("csv")
    if csv_section is not None:
        try:
            path_val = csv_section["path"]
            encoding_val = csv_section["encoding"]
            mapping_val = csv_section["field_mapping"]
        except KeyError as e:
            raise ValueError(f"Missing required key in csv section: {e.args[0]!r}")
        csv_cfg = CsvConfig(
            path=Path(path_val),
            encoding=encoding_val,
            field_mapping=dict(mapping_val),
        )
    else:
        csv_cfg = None

    img_section = raw.get("image_service")
    if img_section is not None:
        try:
            host_val = img_section["host"]
            port_val = img_section["port"]
            dir_val = img_section["image_dir"]
        except KeyError as e:
            raise ValueError(f"Missing required key in image_service section: {e.args[0]!r}")
        map_csv_val = img_section.get("image_map_csv")
        img_cfg = ImageServiceConfig(
            host=host_val,
            port=int(port_val),
            image_dir=Path(dir_val),
            image_map_csv=Path(map_csv_val) if map_csv_val else None,
        )
    else:
        img_cfg = None

    rules_section = raw.get("rules")
    if rules_section is not None:
        try:
            amt_val = rules_section["amount_threshold"]
            whitelist_val = rules_section["style_whitelist"]
        except KeyError as e:
            raise ValueError(f"Missing required key in rules section: {e.args[0]!r}")
        rules_cfg = RulesConfig(
            amount_threshold=float(amt_val),
            style_whitelist=set(whitelist_val),
        )
    else:
        rules_cfg = None

    rt = raw.get("runtime", {})
    state_file = Path(rt["state_file"]) if "state_file" in rt else None
    runtime_cfg = RuntimeConfig(
        scan_interval_seconds=int(rt["scan_interval_seconds"]),
        max_images_per_message=int(rt["max_images_per_message"]),
        push_interval_seconds=int(rt.get("push_interval_seconds", 10)),
        state_file=state_file,
        dry_run=bool(rt.get("dry_run", False)),
    )

    backend_section = raw.get("backend")
    if backend_section is not None:
        try:
            db_url = backend_section["database_url"]
            secret_val = backend_section["secret_key"]
            host_b = backend_section["host"]
            port_b = backend_section["port"]
            admin_u = backend_section["bootstrap_admin_username"]
            admin_p = backend_section["bootstrap_admin_password"]
        except KeyError as e:
            raise ValueError(f"Missing required key in backend section: {e.args[0]!r}")
        backend_cfg = BackendConfig(
            database_url=db_url,
            secret_key=secret_val,
            host=host_b,
            port=int(port_b),
            bootstrap_admin_username=admin_u,
            bootstrap_admin_password=admin_p,
        )
    else:
        backend_cfg = None

    api_section = raw.get("api")
    if api_section is not None:
        try:
            base_val = api_section["sales_base_url"]
            token_val = api_section["sales_token"]
            path_s = api_section["sales_path"]
            timeout_val = api_section["timeout_seconds"]
        except KeyError as e:
            raise ValueError(f"Missing required key in api section: {e.args[0]!r}")
        api_cfg = ApiConfig(
            sales_base_url=base_val,
            sales_token=token_val,
            sales_path=path_s,
            timeout_seconds=int(timeout_val),
        )
    else:
        api_cfg = None

    data_source_section = raw.get("data_source")
    if data_source_section is not None:
        try:
            kind_val = data_source_section["kind"]
            config_path_val = data_source_section["config_path"]
        except KeyError as e:
            raise ValueError(f"Missing required key in data_source section: {e.args[0]!r}")
        data_source_cfg = DataSourceRefConfig(
            kind=str(kind_val),
            config_path=Path(config_path_val),
        )
    else:
        data_source_cfg = None

    store_mapping = {str(key).strip(): str(value).strip() for key, value in (raw.get("store_mapping") or {}).items() if str(key).strip() and str(value).strip()}

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
        data_source=data_source_cfg,
        store_mapping=store_mapping,
    )
