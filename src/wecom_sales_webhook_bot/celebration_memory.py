from __future__ import annotations

import io
import logging
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageGrab

from wecom_sales_webhook_bot.celebration import (
    DEFAULT_CONTENT_FIELDS,
    MAX_IMAGE_BYTES,
    _replace_in_shapes,
    celebration_values,
)
from wecom_sales_webhook_bot.models import SalesOrder


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CelebrationImage:
    path: Path
    data: bytes
    suffix: str


def _copy_slide_to_memory(
    template_path: Path,
    slide_number: int,
    values: dict[str, str],
    selected_fields: set[str],
):
    try:
        import win32clipboard
        import win32com.client
    except ImportError as exc:
        raise RuntimeError("喜报图片生成需要安装 pywin32 并在 Windows PowerPoint 环境运行") from exc
    app = None
    presentation = None
    try:
        app = win32com.client.DispatchEx("PowerPoint.Application")
        # SVG templates use the headless browser path; PPTX remains a legacy fallback.
        app.Visible = True
        app.DisplayAlerts = 0
        app.AutomationSecurity = 3
        presentation = app.Presentations.Open(
            str(template_path), ReadOnly=True, Untitled=False, WithWindow=True,
        )
        if slide_number < 1 or slide_number > presentation.Slides.Count:
            raise ValueError(f"PPT模板只有 {presentation.Slides.Count} 页，所选页码无效")
        slide = presentation.Slides(slide_number)
        _replace_in_shapes(slide.Shapes, values, selected_fields)
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
        finally:
            win32clipboard.CloseClipboard()
        slide.Copy()
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            image = ImageGrab.grabclipboard()
            if image is not None and getattr(image, "width", 0) and getattr(image, "height", 0):
                return image.convert("RGB")
            time.sleep(0.05)
        raise RuntimeError("PowerPoint未能把喜报复制为内存图片")
    finally:
        if presentation is not None:
            presentation.Saved = True
            presentation.Close()
        if app is not None:
            app.Quit()


def _encode_limited_image(image, destination_stem: Path) -> CelebrationImage:
    image = image.convert("RGB")
    for factor in (1.0, 0.9, 0.8, 0.7, 0.6):
        # Keep both axes on the same scale so portrait templates cannot be widened.
        width = max(1, round(image.width * factor))
        height = max(1, round(image.height * factor))
        resized = image.resize((width, height), Image.Resampling.LANCZOS) if (width, height) != image.size else image
        buffer = io.BytesIO()
        resized.save(buffer, format="PNG", optimize=True)
        data = buffer.getvalue()
        if len(data) <= MAX_IMAGE_BYTES:
            path = destination_stem.with_suffix(".png")
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            except OSError:
                LOGGER.warning("unable to persist celebration image: %s", path, exc_info=True)
            return CelebrationImage(path=path, data=data, suffix=".png")
    raise ValueError("渲染图片压缩后仍超过企业微信 2 MB 限制")


def generate_celebration_image_memory(
    order: SalesOrder,
    template_path: Path,
    output_dir: Path,
    slide_number: int = 1,
    content_fields: list[str] | tuple[str, ...] = DEFAULT_CONTENT_FIELDS,
    *,
    filename_prefix: str | None = None,
) -> CelebrationImage:
    template_path = Path(template_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    if template_path.suffix.casefold() in {".svg", ".html", ".htm"}:
        from wecom_sales_webhook_bot.celebration_svg import render_svg_template

        safe_order_no = re.sub(r"[^A-Za-z0-9_-]+", "_", order.order_no).strip("_") or "order"
        prefix = filename_prefix or f"{order.sold_at:%Y%m%d}_{safe_order_no}"
        output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="celebration-svg-output-") as temp_dir:
            raw_path = Path(temp_dir) / "render.png"
            render_svg_template(order, template_path, raw_path, content_fields)
            with Image.open(raw_path) as opened:
                image = opened.convert("RGB")
        return _encode_limited_image(image, output_dir / prefix)
    if template_path.suffix.casefold() != ".pptx" or not template_path.is_file():
        raise ValueError("请选择存在的 .pptx 格式喜报模板")
    selected = set(content_fields)
    invalid = selected - set(DEFAULT_CONTENT_FIELDS)
    if invalid:
        raise ValueError(f"未知喜报字段：{', '.join(sorted(invalid))}")
    values = celebration_values(order)
    safe_order_no = re.sub(r"[^A-Za-z0-9_-]+", "_", order.order_no).strip("_") or "order"
    prefix = filename_prefix or f"{order.sold_at:%Y%m%d}_{safe_order_no}"
    image = _copy_slide_to_memory(template_path, slide_number, values, selected)
    return _encode_limited_image(image, output_dir / prefix)
