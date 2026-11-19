from __future__ import annotations

import hashlib
import json
import logging
import re
import tempfile
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from PIL import Image

from wecom_sales_webhook_bot.models import SalesOrder


LOGGER = logging.getLogger(__name__)
MAX_IMAGE_BYTES = 2 * 1024 * 1024
DEFAULT_CONTENT_FIELDS = (
    "order_no", "sold_at", "document_type", "store_name", "store_name_display",
    "store_region", "performance_org", "performance_org_display", "performance_region", "region",
    "salesperson", "total_amount", "currency", "customer_type", "card_no", "items",
)
CONTENT_FIELD_LABELS = {
    "order_no": "销售单号",
    "sold_at": "销售日期",
    "document_type": "单据类型",
    "store_name": "销售机构号",
    "store_name_display": "销售店铺中文名",
    "store_region": "销售机构区域",
    "performance_org": "业绩机构号",
    "performance_org_display": "业绩机构店铺中文名",
    "performance_region": "业绩机构区域",
    "region": "区域（业绩机构优先）",
    "salesperson": "销售人员",
    "total_amount": "单据金额",
    "currency": "币种",
    "customer_type": "顾客类型",
    "card_no": "卡号",
    "items": "商品款号与数量",
}
DOCUMENT_TYPE_LABELS = {"sale": "销售", "exchange": "换货", "return": "退货", "preorder": "预购"}
PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


def webhook_target_id(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:16]


def _decimal_amount(value: object) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("单据金额不是有效数值") from exc
    if not amount.is_finite():
        raise ValueError("单据金额必须是有限数值")
    return amount


def qualifies_for_celebration(order: SalesOrder, threshold: object) -> bool:
    """Use a strict signed amount comparison; returns and zero exchanges do not qualify."""
    return _decimal_amount(order.total_amount) > _decimal_amount(threshold)


def _display_salesperson(value: object) -> str:
    """Keep the consultant name and omit the employee-number suffix."""
    text = str(value or "").strip()
    return re.split(r"[\(\uff08]", text, maxsplit=1)[0].strip()


def celebration_values(order: SalesOrder) -> dict[str, str]:
    attrs = order.attributes or {}
    amount = _decimal_amount(order.total_amount)
    items = [f"{item.style_no or item.barcode} × {item.quantity}" for item in order.items]
    sold_at = order.sold_at.strftime("%Y-%m-%d %H:%M:%S")
    return {
        "order_no": order.order_no or "",
        "sold_at": sold_at,
        "document_type": DOCUMENT_TYPE_LABELS.get(order.document_type, order.document_type or ""),
        "store_name": order.store_name or "",
        "store_name_display": order.store_name_display or order.store_name or "",
        "store_region": str(attrs.get("store_region") or ""),
        "performance_org": order.performance_org or "",
        "performance_org_display": order.performance_org_display or order.performance_org or "",
        "performance_region": str(attrs.get("performance_region") or ""),
        # The headline region follows the performance organization when known.
        "region": str(attrs.get("performance_region") or attrs.get("region") or attrs.get("store_region") or ""),
        "salesperson": _display_salesperson(order.salesperson),
        "total_amount": f"{amount:,.0f}",
        "currency": str(attrs.get("currency") or ""),
        "customer_type": order.customer_type or "",
        "card_no": str(attrs.get("card_no") or ""),
        "items": "\n".join(items),
    }


def _replace_in_shapes(shapes, values: dict[str, str], selected_fields: set[str]) -> None:
    for shape in shapes:
        if getattr(shape, "Type", None) == 6:  # msoGroup
            _replace_in_shapes(shape.GroupItems, values, selected_fields)
            continue
        if getattr(shape, "HasTable", False):
            table = shape.Table
            for row in range(1, table.Rows.Count + 1):
                for col in range(1, table.Columns.Count + 1):
                    _replace_text_range(table.Cell(row, col).Shape.TextFrame.TextRange, values, selected_fields)
        try:
            has_text = bool(shape.HasTextFrame and shape.TextFrame.HasText)
        except Exception:  # Shapes such as media can lack a usable text frame.
            continue
        if has_text:
            _replace_text_range(shape.TextFrame.TextRange, values, selected_fields)


def _replace_text_range(text_range, values: dict[str, str], selected_fields: set[str]) -> None:
    source = str(text_range.Text)
    tokens = PLACEHOLDER.findall(source)
    if not tokens:
        return
    unknown = sorted(set(tokens) - set(values))
    if unknown:
        raise ValueError(f"PPT模板包含不支持的占位符：{', '.join(unknown)}")
    if len(set(tokens)) == 1 and tokens[0] not in selected_fields:
        text_range.Text = ""
        return
    for field in set(tokens):
        source = re.sub(r"\{\{\s*" + re.escape(field) + r"\s*\}\}", values[field] if field in selected_fields else "", source)
    text_range.Text = source


def _export_dimensions(slide_width: float, slide_height: float, long_edge: int = 1920) -> tuple[int, int]:
    if slide_width <= 0 or slide_height <= 0 or long_edge < 1:
        raise ValueError("PPT模板页面尺寸无效")
    scale = long_edge / max(slide_width, slide_height)
    return max(1, round(slide_width * scale)), max(1, round(slide_height * scale))


def _export_slide(template_path: Path, slide_number: int, values: dict[str, str], selected_fields: set[str], output: Path) -> None:
    try:
        import win32com.client
    except ImportError as exc:
        raise RuntimeError("喜报图片生成需要安装 pywin32 并在 Windows PowerPoint 环境运行") from exc
    app = None
    presentation = None
    try:
        app = win32com.client.DispatchEx("PowerPoint.Application")
        app.Visible = True
        app.DisplayAlerts = 0
        app.AutomationSecurity = 3
        presentation = app.Presentations.Open(str(template_path), ReadOnly=True, Untitled=False, WithWindow=True)
        if slide_number < 1 or slide_number > presentation.Slides.Count:
            raise ValueError(f"PPT模板只有 {presentation.Slides.Count} 页，所选页码无效")
        slide = presentation.Slides(slide_number)
        _replace_in_shapes(slide.Shapes, values, selected_fields)
        output.parent.mkdir(parents=True, exist_ok=True)
        export_width, export_height = _export_dimensions(
            presentation.PageSetup.SlideWidth,
            presentation.PageSetup.SlideHeight,
        )
        slide.Export(str(output), "PNG", export_width, export_height)
        with output.open("rb") as exported:
            signature = exported.read(32)
        if signature.startswith(b"%TSD-Header-"):
            raise RuntimeError(
                "本机终端文件保护为 PowerPoint 导出的图片加了 TSD 加密头，"
                "当前进程无法读取该图片；请将喜报模板放到不受 Office 文件加密策略保护的位置，"
                "或联系管理员为喜报图片导出目录配置明文输出。"
            )
    finally:
        if presentation is not None:
            presentation.Saved = True
            presentation.Close()
        if app is not None:
            app.Quit()


def _save_limited_image(source: Path, destination_stem: Path) -> Path:
    with Image.open(source) as opened:
        image = opened.convert("RGB")
    for factor in (1.0, 0.9, 0.8, 0.7, 0.6):
        # Keep both axes on the same scale so portrait templates cannot be widened.
        width = max(1, round(image.width * factor))
        height = max(1, round(image.height * factor))
        resized = image.resize((width, height), Image.Resampling.LANCZOS) if (width, height) != image.size else image
        png_path = destination_stem.with_suffix(".png")
        resized.save(png_path, format="PNG", optimize=True)
        if png_path.stat().st_size <= MAX_IMAGE_BYTES:
            return png_path
        png_path.unlink(missing_ok=True)
    jpg_path = destination_stem.with_suffix(".jpg")
    for quality in (92, 88, 84, 80, 76, 72):
        image.save(jpg_path, format="JPEG", quality=quality, optimize=True, progressive=True)
        if jpg_path.stat().st_size <= MAX_IMAGE_BYTES:
            return jpg_path
    jpg_path.unlink(missing_ok=True)
    raise ValueError("渲染图片压缩后仍超过企业微信 2 MB 限制")


def generate_celebration_image(
    order: SalesOrder,
    template_path: Path,
    output_dir: Path,
    slide_number: int = 1,
    content_fields: list[str] | tuple[str, ...] = DEFAULT_CONTENT_FIELDS,
    *,
    filename_prefix: str | None = None,
) -> Path:
    template_path = Path(template_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    if template_path.suffix.casefold() in {".svg", ".html", ".htm"}:
        from wecom_sales_webhook_bot.celebration_memory import generate_celebration_image_memory

        return generate_celebration_image_memory(
            order,
            template_path,
            output_dir,
            slide_number,
            content_fields,
            filename_prefix=filename_prefix,
        ).path
    if template_path.suffix.casefold() != ".pptx" or not template_path.is_file():
        raise ValueError("请选择存在的 .pptx 格式喜报模板")
    selected = set(content_fields)
    invalid = selected - set(DEFAULT_CONTENT_FIELDS)
    if invalid:
        raise ValueError(f"未知的喜报字段：{', '.join(sorted(invalid))}")
    values = celebration_values(order)
    safe_order_no = re.sub(r"[^A-Za-z0-9_-]+", "_", order.order_no).strip("_") or "order"
    prefix = filename_prefix or f"{order.sold_at:%Y%m%d}_{safe_order_no}"
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="celebration-") as temp_dir:
        render_path = Path(temp_dir) / "slide.png"
        _export_slide(template_path, slide_number, values, selected, render_path)
        if not render_path.is_file() or render_path.stat().st_size == 0:
            raise RuntimeError("PowerPoint没有生成可用的喜报图片")
        return _save_limited_image(render_path, output_dir / prefix)


def generate_preview_image(
    template_path: Path,
    output_dir: Path,
    slide_number: int,
    content_fields: list[str] | tuple[str, ...],
) -> Path:
    order = SalesOrder(
        order_no="XSG899261115001",
        sold_at=datetime(2026, 11, 15, 14, 30),
        store_name="G899",
        performance_org="G899",
        store_name_display="杭州示例店",
        performance_org_display="杭州示例中心",
        salesperson="张三（演示）",
        total_amount=128800.0,
        customer_type="VIP顾客",
        document_type="sale",
        attributes={"currency": "CNY", "card_no": "示例卡号", "store_region": "华北区", "region": "华北区"},
        items=[],
    )
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    from wecom_sales_webhook_bot.celebration_memory import generate_celebration_image_memory

    return generate_celebration_image_memory(
        order, template_path, output_dir, slide_number, content_fields,
        filename_prefix=f"喜报预览_{stamp}",
    ).path


class CelebrationStateStore:
    """Separate per-order/per-webhook progress so ordinary sales pushes do not suppress celebrations."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"orders": {}})

    def _read(self) -> dict:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"喜报发送状态文件无法读取：{self.path}") from exc
        payload.setdefault("orders", {})
        return payload

    def _write(self, payload: dict) -> None:
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def get(self, order_no: str) -> dict:
        return self._read()["orders"].get(order_no, {}).copy()

    def record_image(self, order_no: str, image_path: Path) -> None:
        payload = self._read()
        record = payload["orders"].setdefault(order_no, {"sent_targets": {}})
        record["image_path"] = str(Path(image_path).resolve())
        record.setdefault("sent_targets", {})
        record.setdefault("generated_at", datetime.now().isoformat(timespec="seconds"))
        self._write(payload)

    def mark_target_sent(self, order_no: str, target_id: str, sent_at: datetime | None = None) -> None:
        payload = self._read()
        record = payload["orders"].setdefault(order_no, {"sent_targets": {}})
        record.setdefault("sent_targets", {})[target_id] = (sent_at or datetime.now()).isoformat(timespec="seconds")
        self._write(payload)

    def sent_targets(self, order_no: str) -> set[str]:
        return set(self._read()["orders"].get(order_no, {}).get("sent_targets", {}))
