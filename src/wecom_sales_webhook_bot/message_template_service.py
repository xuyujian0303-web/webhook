from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from wecom_sales_webhook_bot.message_template_defaults import PRESET_TEMPLATES
from wecom_sales_webhook_bot.rule_models import GlobalSetting


DEFAULT_TEMPLATE_NAME = "自定义模板"
TEMPLATE_SETTING_KEY = "message_template"


class TemplateDeleteError(ValueError):
    pass


def _new_template_id() -> str:
    return uuid4().hex


def _default_template_payload() -> dict:
    template_id = _new_template_id()
    return {
        "active_template_id": template_id,
        "templates": [
            {
                "id": template_id,
                "name": DEFAULT_TEMPLATE_NAME,
                "template_body": PRESET_TEMPLATES["standard"]["body"],
                "preset_key": "standard",
            }
        ],
    }


def _normalize_template(template: dict) -> dict:
    preset_key = str(template.get("preset_key", "standard"))
    if preset_key not in PRESET_TEMPLATES:
        preset_key = "standard"
    body = str(template.get("template_body", PRESET_TEMPLATES[preset_key]["body"]))
    if "items_markdown" in body:
        body = body.replace("{{ items_markdown }}", "{% for item in order.items %}{{ item.style_no }} {{ item.barcode }} {{ item.image_url }}{% endfor %}")
    return {
        "id": str(template.get("id") or _new_template_id()),
        "name": str(template.get("name") or template.get("template_name") or DEFAULT_TEMPLATE_NAME),
        "template_body": body,
        "preset_key": preset_key,
    }

def _normalize_store(payload: dict | None) -> dict:
    if not payload:
        return _default_template_payload()

    if "templates" not in payload:
        template = _normalize_template(payload)
        return {
            "active_template_id": template["id"],
            "templates": [template],
        }

    templates = [_normalize_template(item) for item in payload.get("templates", [])]
    if not templates:
        return _default_template_payload()

    active_template_id = str(payload.get("active_template_id") or templates[0]["id"])
    if not any(item["id"] == active_template_id for item in templates):
        active_template_id = templates[0]["id"]
    return {
        "active_template_id": active_template_id,
        "templates": templates,
    }


def _dump_store(store: dict) -> str:
    return json.dumps(store, ensure_ascii=False, sort_keys=True)


def _upsert_store(session, store: dict) -> dict:
    normalized = _normalize_store(store)
    payload = _dump_store(normalized)
    row = session.query(GlobalSetting).filter_by(setting_key=TEMPLATE_SETTING_KEY).one_or_none()
    if row is None:
        session.add(
            GlobalSetting(
                setting_key=TEMPLATE_SETTING_KEY,
                setting_json=payload,
            )
        )
    else:
        row.setting_json = payload
    session.commit()
    return normalized


def load_or_initialize_message_template_store(session) -> dict:
    row = session.query(GlobalSetting).filter_by(setting_key=TEMPLATE_SETTING_KEY).one_or_none()
    if row is None:
        return _upsert_store(session, _default_template_payload())

    normalized = _normalize_store(json.loads(row.setting_json))
    if normalized != json.loads(row.setting_json):
        return _upsert_store(session, normalized)
    return normalized


def load_or_initialize_message_template(session) -> dict:
    store = load_or_initialize_message_template_store(session)
    active_id = store["active_template_id"]
    active = next(item for item in store["templates"] if item["id"] == active_id)
    return {
        "template_id": active["id"],
        "template_name": active["name"],
        "template_body": active["template_body"],
        "preset_key": active["preset_key"],
    }


def save_message_template(
    session,
    *,
    template_id: str | None,
    template_name: str,
    template_body: str,
    preset_key: str,
    activate: bool,
) -> dict:
    store = load_or_initialize_message_template_store(session)
    normalized_preset = preset_key if preset_key in PRESET_TEMPLATES else "standard"
    normalized_name = template_name.strip() or DEFAULT_TEMPLATE_NAME

    if template_id:
        template = next(
            (item for item in store["templates"] if item["id"] == template_id),
            None,
        )
        if template is None:
            template = {
                "id": template_id,
                "name": normalized_name,
                "template_body": template_body,
                "preset_key": normalized_preset,
            }
            store["templates"].append(template)
        else:
            template["name"] = normalized_name
            template["template_body"] = template_body
            template["preset_key"] = normalized_preset
    else:
        template = {
            "id": _new_template_id(),
            "name": normalized_name,
            "template_body": template_body,
            "preset_key": normalized_preset,
        }
        store["templates"].append(template)

    if activate:
        store["active_template_id"] = template["id"]

    _upsert_store(session, store)
    return template


def activate_message_template(session, template_id: str) -> dict:
    store = load_or_initialize_message_template_store(session)
    if not any(item["id"] == template_id for item in store["templates"]):
        raise ValueError(f"unknown template id: {template_id}")
    store["active_template_id"] = template_id
    return _upsert_store(session, store)


def delete_message_template(session, template_id: str) -> dict:
    store = load_or_initialize_message_template_store(session)
    if template_id == store["active_template_id"]:
        raise TemplateDeleteError("cannot delete active template")
    store["templates"] = [
        item for item in store["templates"] if item["id"] != template_id
    ]
    return _upsert_store(session, store)


def build_preview_template_context() -> dict:
    return {
        "order": {
            "order_no": "SOG609260605001",
            "store_name": "G609",
            "sold_at": datetime(2026, 6, 5, 10, 50, 0),
            "total_amount": 21500,
            "salesperson": "张三",
            "total_quantity": 2,
            "customer_source": "会员推荐",
            "promotion_material": "秋季画册",
            "card_type": "金卡",
            "match_reason": "金额命中",
            "items": [
                {
                    "barcode": "GDRCH042ACBK0B6360009",
                    "style_no": "DRCH042ABK0",
                    "unit_price": 14500,
                    "brand": "Brand-A",
                    "category": "Coat",
                    "image_url": "http://intranet.images/1.jpg",
                },
                {
                    "barcode": "GDRCH043ACBK0B6360010",
                    "style_no": "DRCH043ABK0",
                    "unit_price": 7000,
                    "brand": "Brand-A",
                    "category": "Coat",
                    "image_url": "http://intranet.images/2.jpg",
                },
            ],
        }
    }