from __future__ import annotations

import json
import struct
from datetime import datetime

from .models import SalesLineItem, SalesOrder


class EmsDecodeError(ValueError):
    pass


def infer_document_type(total_amount: float, raw_type: object = None) -> str:
    """Normalize the verified EMS code; retain amount-sign fallback if absent."""
    text = "" if raw_type is None else str(raw_type).strip().casefold()
    aliases = {
        "0": "sale", "sale": "sale", "销售": "sale",
        "2": "return", "return": "return", "退货": "return",
        "1": "exchange", "exchange": "exchange", "换货": "exchange",
        "3": "preorder", "preorder": "preorder", "预购": "preorder",
    }
    if text in aliases:
        return aliases[text]
    return "return" if total_amount < 0 else "unknown"


def _is_order_number(value: object) -> bool:
    text = str(value).strip()
    return text.startswith(("XSG", "SOG"))


def _decode_text(raw: bytes) -> str:
    value = raw.decode("utf-8", "replace")
    return raw.decode("gb18030", "replace") if "\ufffd" in value else value


def build_ems_image_url(product_code: str) -> str:
    """Build the EMS image URL from the full product code.

    EMS product codes include the trailing colour/variant segment required by
    the image service, for example ``GJA14344PIBL0B6_01.jpg``. The shorter
    style/colour display code is not a valid image filename.
    """
    code = str(product_code).strip()
    if not code:
        return ""
    return f"http://giada-erp.redstone.com.cn/giada/images/{code}_01.jpg"


def category_from_style_no(style_no: object) -> str | None:
    """Return the business category encoded by a style code's first two letters."""
    value = str(style_no or "").strip()
    return value[:2].upper() if len(value) >= 2 else None


def extract_sale_detail_records(payload: bytes) -> list[list[dict[str, object]]]:
    """Return structurally separated primitive fields for diagnostic callers."""
    records, _ = _read_sale_detail_response(payload)
    def flatten(value):
        output = []
        if isinstance(value, dict):
            for field_id, item in value.items():
                if isinstance(item, (dict, list)):
                    output.extend(flatten(item))
                else:
                    output.append({"field_id": field_id, "value": item})
        elif isinstance(value, list):
            for item in value:
                output.extend(flatten(item))
        return output
    return [flatten(record) for record in records]


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
        if value.startswith((b"XSG", b"SOG")):
            markers.append(index)
    return [payload[start:markers[index + 1] if index + 1 < len(markers) else len(payload)] for index, start in enumerate(markers)]


def decode_sale_detail_tlv(payload: bytes) -> list[dict[str, object]]:
    """Expose verified header fields and primitives for protocol diagnostics."""
    records, _ = _read_sale_detail_response(payload)
    output = []
    for record, fields in zip(records, extract_sale_detail_records(payload)):
        header = record[1]
        output.append({
            "order_no": header[2].strip(), "sold_date": header.get(3),
            "created_at": header.get(16),
            "string_fields": [field for field in fields if isinstance(field["value"], str)],
            "product_codes": [line[12].strip() for line in record[2]],
            "numeric_fields": [field for field in fields if isinstance(field["value"], (int, float))],
        })
    return output


class _BinaryReader:
    """Read bounded Thrift binary values without scanning inside string bytes."""

    def __init__(self, payload: bytes):
        self.payload = payload
        self.offset = 0
        self.fields: list[dict[str, object]] = []

    def take(self, size: int) -> bytes:
        if size < 0 or self.offset + size > len(self.payload):
            raise EmsDecodeError("truncated EMS binary response")
        value = self.payload[self.offset:self.offset + size]
        self.offset += size
        return value

    def integer(self, size: int) -> int:
        return int.from_bytes(self.take(size), "big", signed=True)

    def value(self, tag: int, depth: int = 0):
        if depth > 64:
            raise EmsDecodeError("EMS binary nesting exceeds limit")
        if tag in {2, 3, 6, 8, 10}:
            value = self.integer({2: 1, 3: 1, 6: 2, 8: 4, 10: 8}[tag])
            return bool(value) if tag == 2 else value
        if tag == 4:
            return struct.unpack(">d", self.take(8))[0]
        if tag == 11:
            return _decode_text(self.take(self.integer(4)))
        if tag == 12:
            result = {}
            while True:
                kind = self.integer(1)
                if kind == 0:
                    return result
                field_id = self.integer(2)
                value = self.value(kind, depth + 1)
                if field_id in result:
                    raise EmsDecodeError("duplicate EMS struct field")
                result[field_id] = value
                if kind not in {12, 13, 14, 15}:
                    self.fields.append({"tag": kind, "field_id": field_id, "value": value})
        if tag in {13, 14, 15}:
            key_type = self.integer(1)
            value_type = self.integer(1) if tag == 13 else key_type
            count = self.integer(4)
            if not 0 <= count <= len(self.payload):
                raise EmsDecodeError("invalid EMS collection size")
            if tag == 13:
                return {self.value(key_type, depth + 1): self.value(value_type, depth + 1)
                        for _ in range(count)}
            return [self.value(value_type, depth + 1) for _ in range(count)]
        raise EmsDecodeError(f"unsupported EMS binary tag {tag}")


def _read_sale_detail_response(payload: bytes):
    if len(payload) >= 4 and payload[:4] != b"\x80\x01\x00\x02" and payload[:4] != b"\x80\x01\x00\x03":
        if int.from_bytes(payload[:4], "big") == len(payload) - 4:
            payload = payload[4:]
    reader = _BinaryReader(payload)
    version = reader.take(4)
    if version not in {b"\x80\x01\x00\x02", b"\x80\x01\x00\x03"}:
        raise EmsDecodeError("invalid EMS response envelope")
    method = reader.value(11)
    reader.integer(4)  # sequence id
    if method != "querySaleDetailList":
        raise EmsDecodeError("unexpected EMS response method")
    result = reader.value(12)
    if reader.offset != len(payload):
        raise EmsDecodeError("trailing bytes in EMS response")
    if version[-1] == 3 or 0 not in result or not isinstance(result[0], list):
        raise EmsDecodeError("EMS sale-detail query returned an error")
    return result[0], reader.fields


def _enum_label(value: object, labels: dict[int, str]) -> str | None:
    if value is None:
        return None
    return labels.get(value, f"unknown:{value}")


def decode_sale_detail_orders(payload: bytes) -> list[SalesOrder]:
    """Decode verified EMS structs (2026-11-13--15: 510 orders, 750 items).

    Header and item IDs live in separate nested structs. I32 and I64 are
    signed, money uses thousandths, actual discount uses hundredths.
    Each physical ItemID is one piece; operation 1 is a returned piece.
    """
    records, _ = _read_sale_detail_response(payload)
    orders: list[SalesOrder] = []
    try:
        for record in records:
            header = record[1]
            order_no = header[2].strip()
            if not _is_order_number(order_no):
                raise EmsDecodeError("invalid EMS order number")
            sold_at = datetime.strptime(header[3], "%Y%m%d")
            created_at = datetime.strptime(header[16], "%Y%m%d%H%M%S") if header.get(16) else None
            sales_org = header[4]
            performance_org = header.get(20, sales_org)
            metadata = header.get(19, {})
            items = []
            for line in record[2]:
                operation = line.get(6)
                if operation not in {0, 1}:
                    raise EmsDecodeError("unknown EMS item operation")
                product_code = line[12].strip()
                style_no = line[13].strip()
                items.append(SalesLineItem(
                    barcode=line[2].strip(), style_no=style_no,
                    unit_price=line[7] / 1000,
                    quantity=-1 if operation == 1 else 1,
                    category=line.get(11) or category_from_style_no(style_no),
                    image_url=build_ems_image_url(product_code),
                    attributes={
                        "product_code": product_code, "item_id": str(line[1]),
                        "product_type": _enum_label(line.get(3), {0: "商品"}),
                        "special_sale": bool(line[4]) if 4 in line else None,
                        "product_status": _enum_label(line.get(5), {0: "正常销售", 1: "已被退货", 2: "已被换货"}),
                        "operation_type": {0: "销售", 1: "退回"}[operation],
                        "discount": line.get(8),
                        "actual_amount": line[9] / 1000 if 9 in line else None,
                        "actual_discount": line[10] / 100 if 10 in line else None,
                    },
                ))
            total_amount = header[13] / 1000
            orders.append(SalesOrder(
                order_no=order_no, sold_at=sold_at,
                store_name=sales_org[2].strip(),
                performance_org=performance_org[2].strip(),
                store_name_display=sales_org.get(3),
                performance_org_display=performance_org.get(3),
                total_amount=total_amount,
                document_type=infer_document_type(total_amount, header.get(5)),
                salesperson=header.get(17), total_quantity=header.get(18),
                customer_type=_enum_label(header.get(7), {0: "VIP顾客", 1: "积分卡顾客", 2: "普通顾客"}),
                card_type=_enum_label(header.get(11), {0: "", 1: "专家", 3: "藏家", 4: "名家", 31: "访者", 33: "行家"}),
                customer_source=metadata.get(1), activity_type=metadata.get(2),
                promotion_material=metadata.get(4),
                attributes={
                    "currency": header.get(6), "card_no": header.get(12),
                    "customer_discount_type": _enum_label(header.get(9), {0: "无折扣", 1: "VIP折扣", 4: "GFriend折扣"}),
                    "customer_discount": header.get(10), "created_at": created_at,
                }, items=items,
            ))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        if isinstance(exc, EmsDecodeError):
            raise
        raise EmsDecodeError("invalid EMS sale-detail record") from exc
    return orders


def scan_tlv_fields(payload: bytes) -> list[dict[str, object]]:
    """Inspect primitive fields of a complete, structurally valid response."""
    return _read_sale_detail_response(payload)[1]


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
                "document_type": infer_document_type(
                    float(row.get("total_amount", row.get("actual_amount", 0))),
                    row.get("document_type", row.get("document_type_code")),
                ),
                "items": [],
            })["items"].append(SalesLineItem(
                barcode=str(row.get("barcode", "")), style_no=(style_no := str(row.get("style_no", row.get("product_code", "")))),
                unit_price=float(row.get("unit_price", row.get("price", 0))), quantity=int(row.get("quantity", 1)),
                brand=row.get("brand"), category=category_from_style_no(style_no), image_url=row.get("image_url"),
            ))
        except (KeyError, TypeError, ValueError) as exc:
            raise EmsDecodeError(f"invalid normalized EMS row: {row!r}") from exc
    return [SalesOrder(**value) for value in grouped.values()]
