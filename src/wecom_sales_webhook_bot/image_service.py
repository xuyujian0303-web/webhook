from __future__ import annotations

import csv
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread


class LocalImageUrlProvider:
    def __init__(
        self,
        image_dir: Path,
        base_url: str,
        image_map_csv: Path | None = None,
    ) -> None:
        self._image_dir = image_dir
        self._base_url = base_url.rstrip("/")
        self._image_map = self._load_image_map(image_map_csv)

    def _candidate_keys(self, key: str) -> list[str]:
        candidates = [key]
        if len(key) > 6:
            trimmed = key[:-6]
            if trimmed and trimmed not in candidates:
                candidates.append(trimmed)
        lowered = []
        for candidate in candidates:
            lower = candidate.lower()
            if lower not in lowered:
                lowered.append(lower)
        return lowered

    def _load_image_map(self, image_map_csv: Path | None) -> dict[str, str]:
        if image_map_csv is None or not image_map_csv.exists():
            return {}

        with image_map_csv.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            mapping: dict[str, str] = {}
            for row in reader:
                raw_key = str(row.get("image_key", "")).strip()
                raw_url = str(row.get("image_url", "")).strip()
                if raw_key and raw_url:
                    mapping[raw_key.lower()] = raw_url
            return mapping

    def get_url(self, key: str) -> str | None:
        for candidate_key in self._candidate_keys(key):
            mapped = self._image_map.get(candidate_key)
            if mapped:
                return mapped

        if not self._image_dir.exists():
            return None

        files_by_stem: dict[str, Path] = {}
        for candidate in self._image_dir.iterdir():
            if not candidate.is_file():
                continue
            if candidate.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                continue
            files_by_stem.setdefault(candidate.stem.lower(), candidate)

        for candidate_key in self._candidate_keys(key):
            matched = files_by_stem.get(candidate_key)
            if matched is not None:
                return f"{self._base_url}/{matched.name}"
        return None


def start_image_server(image_dir: Path, host: str, port: int) -> ThreadingHTTPServer:
    handler = partial(SimpleHTTPRequestHandler, directory=str(image_dir))
    server = ThreadingHTTPServer((host, port), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
