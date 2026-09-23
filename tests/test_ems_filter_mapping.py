from __future__ import annotations

import struct

from wecom_sales_webhook_bot.ems_client import build_sale_detail_frame
from wecom_sales_webhook_bot.ems_decoder import decode_sale_detail_orders, infer_document_type


def _field_string(field_id: int, value: str) -> bytes:
    raw = value.encode("utf-8")
    return b"\x0b" + struct.pack(">H", field_id) + struct.pack(">I", len(raw)) + raw


def _captured_example_frame() -> bytes:
    return build_sale_detail_frame(
        "20260922",
        "20260923",
        store_names={"G899", "G889"},
        document_types={"sale", "exchange", "return", "preorder"},
        amount_range=(10000, 20000),
        unit_price_range=(0, 50000),
        unit_discount_range=(0, 100),
        seasons={"26FW"},
        shipment_groups={"26FWG6"},
        style_numbers={"JACH619CNY0"},
        return_whole_order=False,
    )


def test_filter_frame_has_all_captured_parameter_ids_and_values() -> None:
    request = _captured_example_frame()
    assert request[:4] == struct.pack(">I", len(request) - 4)
    assert b"querySaleDetailList" in request
    assert struct.pack(">I", 0x172F) in request

    expected = {
        (0x2712, "20230923"),
        (5, " in ( 'G889','G899' ) "),
        (6, " in ( 0,1,2,3 ) "),
        (3, "20260922"),
        (4, "20260923"),
        (9, "10000"),
        (10, "20000"),
        (22, "0"),
        (23, "50000"),
        (24, "0"),
        (25, "100"),
        (20, "26FW"),
        (28, "26FWG6"),
        (29, "0"),
        (32, "jach619cny0"),
    }
    for field_id, value in expected:
        encoded = (
            struct.pack(">I", field_id)
            + b"\x0b\x00\x02"
            + struct.pack(">I", len(value))
            + value.encode()
        )
        assert encoded in request


def test_open_ended_range_keeps_both_captured_parameter_slots() -> None:
    request = build_sale_detail_frame(
        "20260922",
        "20260923",
        amount_range=(10000, None),
    )
    for field_id, value in ((9, "10000"), (10, "")):
        encoded = (
            struct.pack(">I", field_id)
            + b"\x0b\x00\x02"
            + struct.pack(">I", len(value))
            + value.encode()
        )
        assert encoded in request


def _order_payload(type_code: int, *, amount: int = 12_600_000) -> bytes:
    record = bytearray()
    record.extend(_field_string(2, "SOG899260922002"))
    record.extend(_field_string(3, "20260922"))
    record.extend(b"\x03\x00\x05" + bytes([type_code]))
    record.extend(b"\x0a\x00\x0d" + amount.to_bytes(8, "big"))
    record.extend(_field_string(2, "GJACH619CCNY0C638"))
    record.extend(_field_string(12, "GJACH619CCNY0C6"))
    record.extend(_field_string(13, "JACH619CNY0"))
    return bytes(record)


def test_response_type_code_overrides_amount_sign_for_exchange_and_preorder() -> None:
    exchange = decode_sale_detail_orders(_order_payload(2))[0]
    preorder = decode_sale_detail_orders(_order_payload(3))[0]
    returned = decode_sale_detail_orders(_order_payload(1, amount=0))[0]

    assert exchange.total_amount > 0
    assert exchange.document_type == "exchange"
    assert preorder.document_type == "preorder"
    assert returned.document_type == "return"
    assert infer_document_type(12600) == "unknown"
