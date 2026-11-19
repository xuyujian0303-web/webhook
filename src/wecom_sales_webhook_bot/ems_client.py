from __future__ import annotations

import hashlib
import socket
import struct
from decimal import Decimal

from .ems_protocol import frame, recv_frame
from .rule_service import normalize_document_type


def _document_type_codes(document_types: set[str] | None) -> list[str]:
    code_by_type = {"sale": "0", "return": "2", "exchange": "1", "preorder": "3"}
    return sorted({
        code_by_type[normalized]
        for value in document_types or set()
        if (normalized := normalize_document_type(value)) in code_by_type
    })


def _normalized_store_names(store_names: set[str] | None) -> list[str]:
    return sorted({
        str(value).strip().upper()
        for value in store_names or set()
        if str(value).strip()
    })


def _field_string(index: int, value: str) -> bytes:
    raw = value.encode("utf-8")
    return b"\x0b" + struct.pack(">H", index) + struct.pack(">I", len(raw)) + raw


def _format_query_number(value: float) -> str:
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("EMS numeric query bounds must be finite")
    return format(number.normalize(), "f")


def _build_captured_filter_frame(
    start_date: str,
    end_date: str,
    store_names: set[str] | None,
    document_types: set[str] | None,
    amount_range: tuple[float | None, float | None] | None,
    unit_price_range: tuple[float | None, float | None] | None,
    unit_discount_range: tuple[float | None, float | None] | None,
    seasons: set[str] | None,
    shipment_groups: set[str] | None,
    style_numbers: set[str] | None,
    return_whole_order: bool,
    omit_empty_parameters: bool = False,
) -> bytes:
    codes = _document_type_codes(document_types)
    stores = _normalized_store_names(store_names)
    if any("'" in store for store in stores):
        raise ValueError("EMS store filter contains an unsupported quote")

    parameters: list[tuple[int, str]] = [
        (0x2712, "20230923"),
        (5, " in ( " + ",".join(f"'{store}'" for store in stores) + " )" if stores else ""),
        (6, " in ( " + ",".join(codes) + " ) " if codes else ""),
        (3, start_date),
        (4, end_date),
    ]
    for bounds, low_index, high_index in (
        (amount_range, 9, 10),
        (unit_price_range, 22, 23),
        (unit_discount_range, 24, 25),
    ):
        if bounds is not None:
            low, high = bounds
            parameters.extend(
                (index, _format_query_number(value) if value is not None else "")
                for index, value in ((low_index, low), (high_index, high))
            )
        else:
            # This 15-entry request layout was captured with all range slots
            # present. Empty slots preserve the server-validated structure.
            parameters.extend(((low_index, ""), (high_index, "")))
    parameters.extend((
        (20, ",".join(sorted(seasons or set()))),
        (28, ",".join(sorted(shipment_groups or set()))),
        (29, "1" if return_whole_order else "0"),
        (32, ",".join(sorted(style_numbers or set())).casefold()),
    ))
    if omit_empty_parameters:
        required = {0x2712, 3, 4, 29}
        parameters = [
            (index, value)
            for index, value in parameters
            if index in required or value
        ]

    entries = bytearray()
    for position, (index, value) in enumerate(parameters):
        entries.extend(b"\x08\x00\x01" if position == 0 else b"\x00\x08\x00\x01")
        entries.extend(struct.pack(">I", index))
        entries.extend(_field_string(2, value))
    container = b"\x0f\x00\x01\x0c" + struct.pack(">I", len(parameters)) + entries
    method = b"querySaleDetailList"
    body = (
        b"\x80\x01\x00\x01" + struct.pack(">I", len(method)) + method
        + struct.pack(">I", 0x172F) + container
        + b"\x00\x08\x00\x02\x00L\x55\xbf\x08\x00\x03\x00\x00\x00\x01\x00"
    )
    return frame(body)


def build_login_frame(username: str, password: str) -> bytes:
    digest = hashlib.md5(password.encode("utf-8")).hexdigest().upper().encode("ascii")
    body = (
        b"\x80\x01\x00\x01" + struct.pack(">I", len(b"userLogin")) + b"userLogin"
        + struct.pack(">I", 1) + _field_string(1, username)
        + b"\x0b\x00\x02" + struct.pack(">I", len(digest)) + digest + b"\x00"
    )
    return frame(body)


def build_sale_detail_frame(start_date: str, end_date: str, store_names: set[str] | None = None,
                            amount_threshold: float | None = None,
                            document_types: set[str] | None = None,
                            style_numbers: set[str] | None = None, seasons: set[str] | None = None,
                            shipment_groups: set[str] | None = None, unit_price_threshold: float | None = None,
                            unit_discount_threshold: float | None = None, return_whole_order: bool = True,
                            amount_range: tuple[float | None, float | None] | None = None,
                            unit_price_range: tuple[float | None, float | None] | None = None,
                            unit_discount_range: tuple[float | None, float | None] | None = None,
                            omit_empty_parameters: bool = False) -> bytes:
    """Build the currently verified read-only query shape (YYYYMMDD dates)."""
    amount_range = amount_range or ((amount_threshold, None) if amount_threshold is not None else None)
    unit_price_range = unit_price_range or ((unit_price_threshold, None) if unit_price_threshold is not None else None)
    unit_discount_range = unit_discount_range or ((unit_discount_threshold, None) if unit_discount_threshold is not None else None)
    # One server-verified layout for all queries, including unfiltered ranges.
    # Old branches silently injected amount>=1000 or ignored the end date.
    return _build_captured_filter_frame(
        start_date, end_date, store_names, document_types, amount_range,
        unit_price_range, unit_discount_range, seasons, shipment_groups,
        style_numbers, return_whole_order, omit_empty_parameters,
    )



class EmsTcpClient:
    def __init__(self, auth_host: str, auth_port: int, data_host: str, data_port: int, timeout_seconds: int = 15):
        self.auth_host, self.auth_port = auth_host, auth_port
        self.data_host, self.data_port = data_host, data_port
        self.timeout_seconds = timeout_seconds
        self.initialized = False

    _INITIALIZATION_FRAMES = tuple(bytes.fromhex(value) for value in (
        "00000018800100010000000b67657453616c65446174650000000100",
        "0000001a800100010000000d67657453657276657254696d650000000200",
        "00000023800100010000000f676574417070537973446566696e65000000030800010000000100",
        "000000248001000100000010676574436f6d6d6f6e4f72674c697374000000040800010000000100",
        "00000023800100010000000f67657443617465676f72794c697374000000050800010000000100",
        "0000001f800100010000000b6765744c696e654c697374000000060800010000000100",
        "00000023800100010000000f6765744d61696e436f6d704c697374000000070800010000000100",
        "0000002d800100010000000e6765745061794d6f64654c697374000000080a0001ffffffffffffffff0800020000000100",
        "0000002880010001000000147175657279436f6d70616e79436172644c697374000000090800010000000100",
        "00000026800100010000001267657453616c654c626c4b696e644c6973740000000a0800010000000100",
    ))
    _ORG_CARD_TYPES_FRAME = bytes.fromhex("0000002980010001000000156765744f7267416c6c43617264547970654c6973740000000c0800010000000100")

    def login(self, username: str, password: str) -> bytes:
        with socket.create_connection((self.auth_host, self.auth_port), timeout=self.timeout_seconds) as sock:
            sock.sendall(build_login_frame(username, password))
            return recv_frame(sock)

    def query_sale_detail(self, start_date: str, end_date: str, store_names: set[str] | None = None,
                          amount_threshold: float | None = None,
                          document_types: set[str] | None = None,
                            style_numbers: set[str] | None = None, seasons: set[str] | None = None,
                            shipment_groups: set[str] | None = None, unit_price_threshold: float | None = None,
                            unit_discount_threshold: float | None = None, return_whole_order: bool = True,
                            amount_range: tuple[float | None, float | None] | None = None,
                            unit_price_range: tuple[float | None, float | None] | None = None,
                            unit_discount_range: tuple[float | None, float | None] | None = None,
                            _omit_empty_parameters: bool = False) -> bytes:
        with socket.create_connection((self.data_host, self.data_port), timeout=self.timeout_seconds) as sock:
            sock.settimeout(self.timeout_seconds)
            for request in self._INITIALIZATION_FRAMES:
                sock.sendall(request)
                recv_frame(sock)
            sock.sendall(build_sale_detail_frame(
                start_date, end_date, store_names, amount_threshold, document_types,
                style_numbers, seasons, shipment_groups, unit_price_threshold,
                unit_discount_threshold, return_whole_order, amount_range,
                unit_price_range, unit_discount_range,
                omit_empty_parameters=_omit_empty_parameters,
            ))
            result = recv_frame(sock)
            return result
