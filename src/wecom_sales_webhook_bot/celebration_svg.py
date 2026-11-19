from __future__ import annotations

import html
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from wecom_sales_webhook_bot.celebration import DEFAULT_CONTENT_FIELDS, PLACEHOLDER, celebration_values
from wecom_sales_webhook_bot.models import SalesOrder


def _chrome_executable() -> str | None:
    candidates = [
        shutil.which("chrome"),
        shutil.which("msedge"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    return next((candidate for candidate in candidates if candidate and Path(candidate).is_file()), None)


def _replace_placeholders(source: str, values: dict[str, str], selected_fields: set[str]) -> str:
    tokens = set(PLACEHOLDER.findall(source))
    unknown = sorted(tokens - set(values))
    if unknown:
        raise ValueError(f"SVG模板包含不支持的占位符：{', '.join(unknown)}")

    def replace(match: re.Match[str]) -> str:
        field = match.group(1)
        return html.escape(values[field] if field in selected_fields else "")

    return PLACEHOLDER.sub(replace, source)


def render_svg_template(
    order: SalesOrder,
    template_path: Path,
    output_path: Path,
    content_fields: list[str] | tuple[str, ...] = DEFAULT_CONTENT_FIELDS,
) -> Path:
    """Render a self-contained SVG/HTML template with a headless browser."""
    template_path = Path(template_path).expanduser().resolve()
    if template_path.suffix.casefold() not in {".svg", ".html", ".htm"} or not template_path.is_file():
        raise ValueError("请选择存在的 SVG 或 HTML 喜报模板")
    chrome = _chrome_executable()
    if chrome is None:
        raise RuntimeError("未找到 Chrome 或 Edge，无法在无 PowerPoint 模式下生成喜报图片")
    selected_fields = set(content_fields)
    invalid = selected_fields - set(DEFAULT_CONTENT_FIELDS)
    if invalid:
        raise ValueError(f"未知喜报字段：{', '.join(sorted(invalid))}")
    source = template_path.read_text(encoding="utf-8")
    rendered = _replace_placeholders(source, celebration_values(order), selected_fields)
    output_path = Path(output_path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="celebration-svg-") as temp_dir:
        temp_dir = Path(temp_dir)
        rendered_path = temp_dir / "template.svg"
        screenshot_path = temp_dir / "render.png"
        rendered_path.write_text(rendered, encoding="utf-8")
        command = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-first-run",
            "--no-default-browser-check",
            "--allow-file-access-from-files",
            "--run-all-compositor-stages-before-draw",
            "--screenshot=" + str(screenshot_path),
            "--window-size=1534,3311",
            rendered_path.as_uri(),
        ]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(command, check=True, timeout=30, creationflags=flags, capture_output=True)
        if not screenshot_path.is_file() or screenshot_path.stat().st_size == 0:
            raise RuntimeError("浏览器没有生成可用的喜报图片")
        with Image.open(screenshot_path) as opened:
            opened.convert("RGB").save(output_path, format="PNG", optimize=True)
    return output_path
