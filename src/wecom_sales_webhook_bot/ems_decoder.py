from __future__ import annotations

import json
import struct
import re
from datetime import datetime

from .models import SalesLineItem, SalesOrder


class EmsDecodeError(ValueError):
    pass


def _decode_text(raw: bytes) -> str:
    value = raw.decode("utf-8", "replace")
    return raw.decode("gb18030", "replace") if "\ufffd" in value else value


def extract_sale_detail_records(payload: bytes) -> list[list[dict[str, object]]]:
    """Split a query response into records using the stable XSG order marker.

    The response contains an outer method/header followed by repeated detail
    records. In the authorized sample each record starts with TLV string field
    id=2 whose value begins with ``XSG``. This function intentionally returns
    raw fields; business-field mapping remains explicit in the next layer.
    """
    fields = scan_tlv_fields(payload)
    starts = [i for i, item in enumerate(fields) if item.get("field_id") == 2 and isinstance(item.get("value"), str) and str(item["value"]).strip().startswith("XSG")]
    records: list[list[dict[str, object]]] = []
    for index, start in enumerate(starts):
        records.append(fields[start:starts[index + 1] if index + 1 < len(starts) else len(fields)])
    return records


def extract_sale_detail_records_raw(payload: bytes) -> list[bytes]:
    """Split raw response bytes at encoded ``XSG`` order-number values.

    This fallback is intentionally byte-oriented and preserves every source
    byte, including records whose nested container confuses the generic TLV
    scanner. It is useful for fixture analysis and never treats arbitrary
    printable text as an order unless it is preceded by the TLV string marker.
    """
    markers: list[int] = []
    for index in range(0, len(payload) - 7):
        if payload[index:index + 3] != b"\x0b\x00\x02":
            continue
        length = int.from_bytes(payload[index + 3:index + 7], "big")
        value = payload[index + 7:index + 7 + length]
        if value.startswith(b"XSG"):
            markers.append(index)
    return [payload[start:markers[index + 1] if index + 1 < len(markers) else len(payload)] for index, start in enumerate(markers)]


def decode_sale_detail_tlv(payload: bytes) -> list[dict[str, object]]:
    """Decode the stable order/item identifiers from an EMS TLV response.

    This is deliberately an intermediate representation. Numeric amount and
    discount fields are not guessed until their wire types are confirmed.
    """
    output: list[dict[str, object]] = []
    for fields in (scan_tlv_fields(record) for record in extract_sale_detail_records_raw(payload)):
        strings = [item for item in fields if isinstance(item.get("value"), str)]
        order_no = next((str(item["value"]).strip() for item in strings if str(item["value"]).strip().startswith("XSG")), None)
        if not order_no:
            continue
        dates = [str(item["value"]) for item in strings if len(str(item["value"])) in (8, 14) and str(item["value"]).isdigit()]
        product_codes = [str(item["value"]).strip() for item in strings if str(item["value"]).strip().startswith("G") and len(str(item["value"]).strip()) >= 8]
        output.append({
            "order_no": order_no,
            "sold_date": dates[0] if dates else None,
            "created_at": dates[-1] if dates else None,
            "string_fields": strings,
            "product_codes": product_codes,
            "numeric_fields": [item for item in fields if isinstance(item.get("value"), int)],
        })
    return output


def decode_sale_detail_orders(payload: bytes) -> list[SalesOrder]:
    """Convert the verified EMS response subset into project order models.

    The sample protocol exposes monetary values as integer thousandths (field
    13 on the order header and field 7 on an item). Unknown fields remain ignored
    until their wire definition is confirmed.
    """
    orders: list[SalesOrder] = []
    for record in extract_sale_detail_records_raw(payload):
        fields = scan_tlv_fields(record)
        strings = [str(x["value"]).strip() for x in fields if isinstance(x.get("value"), str)]
        order_no = next((x for x in strings if x.startswith("XSG")), None)
        date_text = next((x for x in strings if len(x) == 8 and x.isdigit()), None)
        created_text = next((x for x in strings if len(x) == 14 and x.isdigit()), None)
        if not order_no or not date_text:
            continue
        try:
            sold_at = datetime.strptime(created_text or date_text, "%Y%m%d%H%M%S" if created_text else "%Y%m%d")
        except ValueError:
            continue
        # Header values precede the first product-code string.
        product_indexes = [i for i, x in enumerate(strings) if len(x) >= 18 and x.startswith("G")]
        first_product = product_indexes[0] if product_indexes else len(strings)
        header_strings = strings[:first_product]
        store_name = next((x for x in header_strings if x.startswith("G") and len(x) <= 8), "")
        org_codes = [x for x in header_strings if x.startswith("G") and len(x) <= 8]
        performance_org = org_codes[1] if len(org_codes) > 1 else store_name
        # The order metadata container (field 19) contains three length-
        # prefixed UTF-8 strings: customer source, activity type and
        # promotion material.  Parse that container locally so values such as
        # ``KOS（上身、挂拍、二创）`` are not truncated by global text matching.
        utf8_texts: list[str] = []
        meta_start = record.find(b"\x0d\x00\x13\x08")
        meta_end = record.find(b"\x0c\x00\x14", meta_start + 7) if meta_start >= 0 else -1
        if meta_start >= 0:
            segment = record[meta_start + 4:meta_end if meta_end > meta_start else len(record)]
            for pos in range(len(segment) - 4):
                n = int.from_bytes(segment[pos:pos + 4], "big")
                if 1 <= n <= 512 and pos + 4 + n <= len(segment):
                    raw = segment[pos + 4:pos + 4 + n]
                    # A valid metadata value must not contain embedded NULs;
                    # this filters the container's bookkeeping integers when
                    # scanning for its length-prefixed strings.
                    if b"\x00" in raw:
                        continue
                    try:
                        text = raw.decode("utf-8").strip()
                    except UnicodeDecodeError:
                        continue
                    if text and (any(ord(ch) > 127 for ch in text) or text in {"KOS", "无", "其他"}):
                        if text not in utf8_texts:
                            utf8_texts.append(text)
        amount_values = [x["value"] for x in fields[: max(0, first_product)] if x.get("field_id") == 13 and isinstance(x.get("value"), int)]
        if not amount_values:
            marker = b"\x0a\x00\x0d"
            amount_values = [int.from_bytes(record[pos + 3:pos + 11], "big")
                             for pos in range(len(record) - 11)
                             if record.startswith(marker, pos)]
        if amount_values:
            raw_amount = amount_values[0]
            if raw_amount >= (1 << 63):
                raw_amount -= (1 << 64)
            total_amount = raw_amount / 1000
        else:
            total_amount = 0.0
        items: list[SalesLineItem] = []
        for item_pos, index in enumerate(product_indexes):
            next_index = product_indexes[item_pos + 1] if item_pos + 1 < len(product_indexes) else len(strings)
            barcode = strings[index]
            style_no = next((x for x in strings[index + 1:next_index] if len(x) >= 8 and x.startswith("G")), barcode)
            price = 0.0
            # The first field-7 value after this product marker belongs to it.
            product_seen = False
            for field in fields:
                if field.get("value") == barcode:
                    product_seen = True
                elif product_seen and field.get("field_id") == 7 and isinstance(field.get("value"), int):
                    raw_price = int(field["value"])
                    if raw_price >= (1 << 63):
                        raw_price -= (1 << 64)
                    price = raw_price / 1000
                    break
            items.append(SalesLineItem(barcode=barcode, style_no=style_no, unit_price=price, image_url=f"http://giada-erp.redstone.com.cn/giada/images/{style_no}_01.jpg"))
        salesperson = next((str(x.get("value")).strip() for x in fields
                            if x.get("field_id") == 17 and isinstance(x.get("value"), str)
                            and str(x.get("value")).strip()), None)
        card_type = next((str(x.get("value")).strip() for x in fields
                          if x.get("field_id") == 14 and isinstance(x.get("value"), str)
                          and str(x.get("value")).strip()), None)
        # Header field 11 is a compact numeric card-type code (tag 0x03),
        # not a normal string TLV.  The initialization response
        # ``getOrgAllCardTypeList`` in ems_login_query.pcapng defines these
        # codes: 1=专家, 3=藏家, 4=名家, 31=访者, 33=行家.
        card_code_match = re.search(rb"\x03\x00\x0b(?P<code>.{1})", record[:record.find(b"\x0d\x00\x13") if record.find(b"\x0d\x00\x13") > 0 else len(record)], re.S)
        if card_code_match:
            card_code = card_code_match.group("code")[0]
            card_type = {1: "专家", 3: "藏家", 4: "名家", 31: "访者", 33: "行家"}.get(card_code)
        # Header card number is a field-12 string before the metadata
        # container; item field-12 values are product codes and must be ignored.
        card_no = None
        header_end = record.find(b"\x0d\x00\x13")
        for m in re.finditer(rb"\x0b\x00\x0c(?P<len>.{4})(?P<value>[^\x00]{1,32})", record[:header_end if header_end > 0 else len(record)], re.S):
            raw = m.group("value")[:int.from_bytes(m.group("len"), "big")]
            if raw.isdigit():
                card_no = raw.decode("ascii")
                break
        # EMS does not expose a readable customer-type label in the binary
        # response. Card-number prefixes match the exported EMS semantics:
        # 80xxxxx = VIP, 60xxxxx = 积分卡, blank = 普通顾客.
        customer_type = ("VIP顾客" if card_no and card_no.startswith("8") else
                         "积分卡顾客" if card_no and card_no.startswith("6") else "普通顾客")
        orders.append(SalesOrder(order_no=order_no, sold_at=sold_at,
                                 store_name=store_name, performance_org=performance_org,
                                 total_amount=total_amount,
                                 salesperson=salesperson,
                                 customer_source=customer_type,
                                 activity_type=utf8_texts[1] if len(utf8_texts) > 1 else None,
                                 promotion_material=utf8_texts[2] if len(utf8_texts) > 2 else None,
                                 card_type=card_type,
                                 customer_type=customer_type,
                                 total_quantity=len(items), items=items))
    return orders


def scan_tlv_fields(payload: bytes) -> list[dict[str, object]]:
    """Return safely framed primitive TLV values from an EMS response.

    EMS uses several container records in addition to primitive fields. This
    scanner deliberately reports only self-describing values (string ``0x0b``
    and fixed-width numeric ``0x08``/``0x0a``) so callers can inspect samples
    without treating guessed offsets as production mappings.
    """
    fields: list[dict[str, object]] = []
    i = 0
    while i + 7 <= len(payload):
        tag = payload[i]
        if tag in (0x0b, 0x0c):
            field_id = int.from_bytes(payload[i + 1:i + 3], "big")
            length = int.from_bytes(payload[i + 3:i + 7], "big")
            end = i + 7 + length
            if 0 <= length <= len(payload) and end <= len(payload):
                raw = payload[i + 7:end]
                if tag == 0x0b:
                    fields.append({"tag": tag, "field_id": field_id, "value": _decode_text(raw)})
                # Do not skip over containers: nested RDS records are part
                # of the same order and may contain the next primitive.
                if tag == 0x0b:
                    i += 1
                    continue
        # Numeric RDS values in the captured response are encoded as
        # ``tag + field-id(2) + value(8)`` (there is no length word). Keep
        # this separate from the length-prefixed string/container form above.
        if tag in (0x08, 0x0a) and i + 11 <= len(payload):
            field_id = int.from_bytes(payload[i + 1:i + 3], "big")
            raw = payload[i + 3:i + 11]
            if len(raw) == 8:
                end = i + 11
                fields.append({"tag": tag, "field_id": field_id, "value": int.from_bytes(raw, "big", signed=False)})
                i = end
                continue
        i += 1
    return fields


def decode_sale_detail(payload: bytes) -> list[SalesOrder]:
    """Decode a normalized JSON response when available.

    EMS production responses are TLV/RDS binary. Until a representative response
    fixture is supplied, fail explicitly instead of guessing field offsets.
    """
    try:
        raw = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EmsDecodeError("EMS TLV/RDS response decoder needs an approved sample response") from exc
    rows = raw.get("items", raw) if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise EmsDecodeError("EMS response does not contain an items list")
    grouped: dict[str, dict] = {}
    for row in rows:
        try:
            order_no = str(row["order_no"])
            grouped.setdefault(order_no, {
                "order_no": order_no,
                "sold_at": datetime.fromisoformat(str(row["sold_at"])),
                "store_name": str(row.get("store_name", row.get("organization", ""))),
                "total_amount": float(row.get("total_amount", row.get("actual_amount", 0))),
                "items": [],
            })["items"].append(SalesLineItem(
                barcode=str(row.get("barcode", "")), style_no=str(row.get("style_no", row.get("product_code", ""))),
                unit_price=float(row.get("unit_price", row.get("price", 0))), quantity=int(row.get("quantity", 1)),
                brand=row.get("brand"), category=row.get("category"), image_url=row.get("image_url"),
            ))
        except (KeyError, TypeError, ValueError) as exc:
            raise EmsDecodeError(f"invalid normalized EMS row: {row!r}") from exc
    return [SalesOrder(**value) for value in grouped.values()]
