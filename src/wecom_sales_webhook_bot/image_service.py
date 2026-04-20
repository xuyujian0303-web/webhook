from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread


class LocalImageUrlProvider:
    def __init__(self, image_dir: Path, base_url: str) -> None:
        self._image_dir = image_dir
        self._base_url = base_url.rstrip("/")

    def get_url(self, barcode: str) -> str | None:
        for extension in (".jpg", ".png", ".jpeg"):
            candidate = self._image_dir / f"{barcode}{extension}"
            if candidate.exists():
                return f"{self._base_url}/{candidate.name}"
        return None


def start_image_server(image_dir: Path, host: str, port: int) -> ThreadingHTTPServer:
    handler = partial(SimpleHTTPRequestHandler, directory=str(image_dir))
    server = ThreadingHTTPServer((host, port), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
