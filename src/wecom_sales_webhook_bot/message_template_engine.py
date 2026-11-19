from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace

from jinja2 import StrictUndefined, nodes
from jinja2.exceptions import TemplateError
from jinja2.sandbox import SandboxedEnvironment

from wecom_sales_webhook_bot.message_template_schema import ALLOWED_FILTERS, ALLOWED_VARIABLES


@dataclass(frozen=True)
class RenderedTemplate:
    text: str
    byte_length: int


class TemplateRenderError(ValueError):
    pass


def _path(node: nodes.Node) -> str | None:
    if isinstance(node, nodes.Name):
        return node.name
    if isinstance(node, nodes.Getattr):
        base = _path(node.node)
        return f"{base}.{node.attr}" if base else None
    return None


def validate_message_template(template_body: str) -> list[str]:
    environment = SandboxedEnvironment()
    try:
        tree = environment.parse(template_body)
    except TemplateError as exc:
        return [f"模板语法错误: {exc}"]

    errors: list[str] = []
    for node in tree.find_all(nodes.Getattr):
        path = _path(node)
        if node.attr.startswith("_"):
            errors.append(f"unsafe attribute: {path}")
        elif path not in ALLOWED_VARIABLES:
            errors.append(f"unknown variable: {path}")
    for node in tree.find_all(nodes.Name):
        if node.name not in {"order", "item"} and node.ctx != "store":
            errors.append(f"unknown variable: {node.name}")
    for node in tree.find_all(nodes.Filter):
        if node.name not in ALLOWED_FILTERS:
            errors.append(f"unknown filter: {node.name}")
    for node in tree.find_all(nodes.Call):
        errors.append("模板不允许调用函数")
    return list(dict.fromkeys(errors))


def _to_template_value(value: object) -> object:
    if isinstance(value, dict):
        return SimpleNamespace(**{key: _to_template_value(item) for key, item in value.items()})
    if isinstance(value, list):
        return [_to_template_value(item) for item in value]
    return value


def _money(value: object) -> str:
    return format(Decimal(str(value)).quantize(Decimal("0.01")), "f")


def _datetime(value: object) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def render_message_template(template_body: str, context: dict) -> RenderedTemplate:
    if "items_markdown" in template_body:
        template_body = template_body.replace("{{ items_markdown }}", "{% for item in order.items %}{{ item.style_no }} {{ item.barcode }} {{ item.image_url }}{% endfor %}")
    errors = validate_message_template(template_body)
    if errors:
        raise TemplateRenderError("; ".join(errors))
    environment = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False)
    environment.filters.update(money=_money, datetime=_datetime)
    try:
        text = environment.from_string(template_body).render(
            **{key: _to_template_value(value) for key, value in context.items()}
        )
    except TemplateError as exc:
        raise TemplateRenderError(str(exc)) from exc
    return RenderedTemplate(text=text, byte_length=len(text.encode("utf-8")))
