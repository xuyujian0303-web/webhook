from __future__ import annotations

import struct

import pytest

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
        (5, " in ( 'G889','G899' )"),
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


@pytest.mark.parametrize(
    ("filters", "expected_values"),
    [
        ({"document_types": {"sale"}}, [(6, " in ( 0 ) ")]),
        ({"document_types": {"预购"}}, [(6, " in ( 3 ) ")]),
        (
            {"store_names": {"G899", "G889"}, "document_types": {"exchange", "preorder"}},
            [(5, " in ( 'G889','G899' )"), (6, " in ( 1,3 ) ")],
        ),
        ({"store_names": {"g899"}}, [(5, " in ( 'G899' )")]),
    ],
)
def test_simple_server_filters_use_captured_frame_layout(
    filters: dict[str, set[str]],
    expected_values: list[tuple[int, str]],
) -> None:
    request = build_sale_detail_frame("20260922", "20260923", **filters)
    assert request[:4] == struct.pack(">I", len(request) - 4)
    assert b"querySaleDetailList" in request
    assert b"20260922" in request
    assert b"20260923" in request
    for field_id, value in expected_values:
        parameter = (
            struct.pack(">I", field_id)
            + b"\x0b\x00\x02"
            + struct.pack(">I", len(value))
            + value.encode()
        )
        assert parameter in request


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


def test_compact_filter_frame_omits_empty_optional_parameters() -> None:
    request = build_sale_detail_frame(
        "20260922",
        "20260923",
        store_names={"G899", "G889"},
        document_types={"sale", "preorder"},
        amount_range=(20000, None),
        omit_empty_parameters=True,
    )
    assert b"20000" in request
    assert struct.pack(">I", 10) not in request
    assert struct.pack(">I", 22) not in request
    assert struct.pack(">I", 24) not in request
    assert struct.pack(">I", 20) not in request
    assert struct.pack(">I", 28) not in request
    assert struct.pack(">I", 32) not in request


@pytest.mark.parametrize(
    ("type_codes", "expected_expression"),
    [
        ({"0", "1", "2"}, " in ( 0,1,2 ) "),
        ({"1", "3"}, " in ( 1,3 ) "),
    ],
)
def test_mixed_document_type_filters_match_live_query_combinations(
    type_codes: set[str],
    expected_expression: str,
) -> None:
    request = build_sale_detail_frame(
        "20260922",
        "20260923",
        document_types=type_codes,
        amount_range=(10000, 20000),
        unit_price_range=(0, 50000),
        unit_discount_range=(0, 100),
        seasons={"26FW"},
        shipment_groups={"26FWG6"},
        style_numbers={"JACH619CNY0"},
    )
    expected_parameter = (
        struct.pack(">I", 6)
        + b"\x0b\x00\x02"
        + struct.pack(">I", len(expected_expression))
        + expected_expression.encode()
    )

    assert expected_parameter in request


def _order_payload(type_code: int, *, amount: int = 12_600_000) -> bytes:
    def integer(tag, field_id, value, size):
        return bytes([tag]) + struct.pack(">h", field_id) + value.to_bytes(size, "big", signed=True)

    def structure(field_id, content):
        return b"\x0c" + struct.pack(">h", field_id) + content + b"\x00"

    org = integer(10, 1, 1, 8) + _field_string(2, "G00J") + _field_string(3, "G00J")
    header = (_field_string(2, "SOGTEST0001") + _field_string(3, "20260922")
              + structure(4, org) + integer(3, 5, type_code, 1)
              + _field_string(6, "CNY") + integer(3, 7, 0, 1)
              + integer(3, 9, 1, 1) + integer(3, 10, 12, 1)
              + integer(3, 11, 3, 1) + _field_string(12, "600000001")
              + integer(10, 13, amount, 8) + _field_string(16, "20260923001820")
              + integer(8, 18, -1, 4))
    metadata = b"\x0d\x00\x13\x08\x0b" + struct.pack(">i", 2)
    for key, value in ((2, "无"), (4, "其他")):
        encoded = value.encode()
        metadata += struct.pack(">ii", key, len(encoded)) + encoded
    header += metadata + structure(20, org.replace(b"G00J", b"G899"))
    item = (integer(10, 1, 1234567, 8) + _field_string(2, "GJACH619CCNY0C638")
            + integer(3, 3, 0, 1) + integer(2, 4, 1, 1)
            + integer(3, 5, 1, 1) + integer(3, 6, 1, 1)
            + integer(10, 7, 12600000, 8) + integer(3, 8, 12, 1)
            + integer(10, 9, -11088000, 8) + integer(8, 10, 1200, 4)
            + _field_string(11, "JA") + _field_string(12, "GJACH619CCNY0C6")
            + _field_string(13, "JACH619CNY0") + b"\x00")
    record = structure(1, header) + b"\x0f\x00\x02\x0c" + struct.pack(">i", 1) + item + b"\x00"
    body = (b"\x80\x01\x00\x02" + struct.pack(">i", 19) + b"querySaleDetailList"
            + struct.pack(">i", 1) + b"\x0f\x00\x00\x0c" + struct.pack(">i", 1) + record + b"\x00")
    return struct.pack(">i", len(body)) + body


def test_response_type_code_overrides_amount_sign_for_exchange_and_preorder() -> None:
    exchange = decode_sale_detail_orders(_order_payload(1))[0]
    preorder = decode_sale_detail_orders(_order_payload(3))[0]
    returned = decode_sale_detail_orders(_order_payload(2, amount=0))[0]

    assert exchange.total_amount > 0
    assert exchange.document_type == "exchange"
    assert preorder.document_type == "preorder"
    assert returned.document_type == "return"
    assert infer_document_type(12600) == "unknown"


def test_response_derives_category_from_the_first_two_style_code_characters() -> None:
    order = decode_sale_detail_orders(_order_payload(3))[0]

    assert order.items[0].style_no == "JACH619CNY0"
    assert order.items[0].category == "JA"


def test_nested_fields_signed_quantities_and_missing_metadata_do_not_shift() -> None:
    from datetime import datetime
    from wecom_sales_webhook_bot.sales_fields import order_field_values

    order = decode_sale_detail_orders(_order_payload(1, amount=0))[0]
    item = order.items[0]
    assert order.store_name == "G00J"
    assert order.performance_org == "G899"
    assert order.sold_at == datetime(2026, 9, 22)
    assert order.attributes["created_at"] == datetime(2026, 9, 23, 0, 18, 20)
    assert order.total_quantity == -1 and item.quantity == -1
    assert order.customer_type == "VIP顾客"  # not inferred from 60-prefixed card
    assert order.customer_source is None
    assert order.activity_type == "无" and order.promotion_material == "其他"
    assert item.attributes["item_id"] == "1234567"
    assert item.attributes["actual_amount"] == -11088
    assert item.attributes["actual_discount"] == 12
    assert item.attributes["discount"] == 12
    assert item.attributes["special_sale"] is True
    assert item.attributes["product_status"] == "已被退货"
    assert order_field_values(order, "currency") == ["CNY"]
    assert order_field_values(order, "quantity") == ["-1"]


def test_truncated_binary_response_is_rejected_instead_of_partial_orders() -> None:
    from wecom_sales_webhook_bot.ems_decoder import EmsDecodeError

    with pytest.raises(EmsDecodeError):
        decode_sale_detail_orders(_order_payload(3)[:-3])


@pytest.mark.parametrize("value,expected", [(12345.67, "12345.67"), (-12345.67, "-12345.67"), (0.0001, "0.0001"), (1e8, "100000000")])
def test_numeric_bounds_preserve_precision_without_scientific_rounding(value,expected):
    request = build_sale_detail_frame("20261115","20261115",amount_range=(value,value))
    for index in (9,10):
        assert struct.pack(">I",index)+b"\x0b\x00\x02"+struct.pack(">I",len(expected))+expected.encode() in request


def test_unfiltered_request_has_no_implicit_amount_threshold_and_keeps_end_date():
    request = build_sale_detail_frame("20261113","20261115",omit_empty_parameters=True)
    assert struct.pack(">I",9)+b"\x0b\x00\x02" not in request
    assert struct.pack(">I",4)+b"\x0b\x00\x02"+struct.pack(">I",8)+b"20261115" in request
