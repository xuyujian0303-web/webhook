from __future__ import annotations

import hashlib
import socket
import struct

from .ems_protocol import frame, recv_frame
from .rule_service import normalize_document_type


def _document_type_codes(document_types: set[str] | None) -> list[str]:
    code_by_type = {"sale": "0", "return": "1", "exchange": "2", "preorder": "3"}
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
    number = float(value)
    return str(int(number)) if number.is_integer() else format(number, "g")


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
) -> bytes:
    type_codes = {
        "sale": "0", "0": "0", "销售": "0",
        "return": "1", "1": "1", "退货": "1",
        "exchange": "2", "2": "2", "换货": "2",
        "preorder": "3", "3": "3", "预购": "3",
    }
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
                            unit_discount_range: tuple[float | None, float | None] | None = None) -> bytes:
    """Build the currently verified read-only query shape (YYYYMMDD dates)."""
    amount_range = amount_range or ((amount_threshold, None) if amount_threshold is not None else None)
    unit_price_range = unit_price_range or ((unit_price_threshold, None) if unit_price_threshold is not None else None)
    unit_discount_range = unit_discount_range or ((unit_discount_threshold, None) if unit_discount_threshold is not None else None)
    if any(value is not None for value in (
        amount_range, unit_price_range, unit_discount_range,
    )) or style_numbers is not None or seasons is not None or shipment_groups is not None:
        return _build_captured_filter_frame(
            start_date, end_date, store_names, document_types, amount_range,
            unit_price_range, unit_discount_range, seasons, shipment_groups,
            style_numbers, return_whole_order,
        )
    hex_template = (
        "000000748001000100000013717565727953616c6544657461696c4c697374"
        "0000000b0f00010c00000003080001000027120b0002000000083230323330393034"
        "00080001000000030b0002000000083230323630393034"
        "000800010000001d0b0002000000013000080002004c55bf0800030000000100"
    )
    raw = bytes.fromhex(hex_template)
    first = bytes.fromhex('3230323330393034')
    second = bytes.fromhex('3230323630393034')
    # EMS uses 0x2712 as a fixed protocol baseline. Field 3 is the
    # inclusive start date; the server supplies the upper bound (today).
    raw = raw.replace(first, b'20230920', 1)
    raw = raw.replace(second, start_date.encode('ascii'), 1)
    advanced = (style_numbers or seasons or shipment_groups or unit_price_threshold is not None or unit_discount_threshold is not None or not return_whole_order)
    if (store_names or amount_threshold is not None or document_types or advanced):
        pass
    if (seasons and shipment_groups and unit_discount_threshold is not None
            and amount_threshold is not None and not store_names and not document_types
            and unit_price_threshold is None):
        def captured_entry(index: int, value: str, first: bool = False) -> bytes:
            prefix = b"\x08\x00\x01" if first else b"\x00\x08\x00\x01"
            return prefix + struct.pack(">I", index) + _field_string(2, value)
        entries = [captured_entry(0x2712, "20230920", True), captured_entry(3, start_date),
                   captured_entry(22, str(int(amount_threshold))), captured_entry(24, str(unit_discount_threshold)),
                   captured_entry(20, ",".join(sorted(seasons))),
                   captured_entry(28, ",".join(sorted(shipment_groups))), captured_entry(29, "1" if return_whole_order else "0")]
        container = b"\x0f\x00\x01\x0c" + struct.pack(">I", len(entries)) + b"".join(entries)
        method = b"querySaleDetailList"
        body = (b"\x80\x01\x00\x01" + struct.pack(">I", len(method)) + method
                + struct.pack(">I", 0x2978) + container
                + b"\x00\x08\x00\x02\x00L\x55\xbf\x08\x00\x03\x00\x00\x00\x01\x00")
        return frame(body)
    if advanced:
        # Exact captured querySaleDetailList container shape. The values are
        # wrapped as parameter entries; they must not be appended to the old
        # short template because EMS validates the nested item count.
        stores = _normalized_store_names(store_names)
        store_expr = (" = '" + stores[0] + "'") if len(stores) == 1 else (" in (" + ",".join("'" + x + "'" for x in stores) + ")" if stores else "")
        codes = _document_type_codes(document_types)
        type_expr = (" = " + codes[0]) if len(codes) == 1 else (" in (" + ",".join(codes) + ")" if codes else "")
        def entry(index: int, value: str) -> bytes:
            return b"\x00\x08\x00\x01" + struct.pack(">I", index) + _field_string(2, value)
        entries = [entry(0x2712, "20230920"), entry(5, store_expr), entry(2, "")]
        if type_expr:
            entries.append(entry(6, type_expr))
        entries.append(entry(3, start_date))
        if amount_threshold is not None:
            entries.append(entry(9, str(int(amount_threshold))))
        if unit_price_threshold is not None:
            entries.append(entry(22, str(unit_price_threshold)))
        if unit_discount_threshold is not None:
            entries.append(entry(24, str(unit_discount_threshold)))
        if style_numbers:
            entries.append(entry(15, ",".join(sorted(style_numbers))))
        if seasons:
            entries.append(entry(20, ",".join(sorted(seasons))))
        if shipment_groups:
            entries.append(entry(28, ",".join(sorted(shipment_groups))))
        entries.append(entry(29, "1" if return_whole_order else "0"))
        container = b"\x0f\x00\x01\x0c" + struct.pack(">I", len(entries)) + b"".join(entries)
        method = b"querySaleDetailList"
        body = (b"\x80\x01\x00\x01" + struct.pack(">I", len(method)) + method
                + struct.pack(">I", 0x2978) + container
                + b"\x00\x08\x00\x02\x00L\x55\xbf\x08\x00\x03\x00\x00\x00\x01\x00")
        return frame(body)
    if not advanced and (store_names or amount_threshold is not None or document_types):
        stores = _normalized_store_names(store_names)
        if len(stores) == 1:
            expression = " = '" + stores[0] + "'"
        elif stores:
            expression = " in (" + ",".join("'" + x + "'" for x in stores) + ")"
        else:
            expression = ""
        def field(value: str) -> bytes:
            encoded = value.encode("utf-8")
            return b"\x0b\x00\x02" + struct.pack(">I", len(encoded)) + encoded
        if document_types and stores and not (style_numbers or seasons or shipment_groups or unit_price_threshold is not None or unit_discount_threshold is not None or not return_whole_order):
            # Keep the captured simple-filter layout while substituting the
            # requested store and document type.
            raw = bytes.fromhex("000000c98001000100000013717565727953616c6544657461696c4c697374000006210f00010c00000007080001000027120b000200000008323032333039303500080001000000050b000200000009203d2027473838392700080001000000060b000200000004203d203000080001000000030b000200000008323032363039303100080001000000040b000200000008323032363039303500080001000000090b00020000000431303030000800010000001d0b0002000000013000080002004c55bf0800030000000100")
            expression = (" = '" + stores[0] + "'") if len(stores) == 1 else " in (" + ",".join("'" + x + "'" for x in stores) + ")"
            old_store = (
                b"\x00\x08\x00\x01" + struct.pack(">I", 5)
                + field(" = 'G889'")
            )
            new_store = (
                b"\x00\x08\x00\x01" + struct.pack(">I", 5)
                + field(expression)
            )
            raw = raw.replace(old_store, new_store, 1)
            codes = _document_type_codes(document_types)
            type_expression = (
                " in ( " + ",".join(codes) + " ) " if len(codes) != 1
                else " = " + codes[0]
            )
            old_type = (
                b"\x00\x08\x00\x01" + struct.pack(">I", 6)
                + field(" = 0")
            )
            new_type = (
                b"\x00\x08\x00\x01" + struct.pack(">I", 6)
                + field(type_expression)
            )
            raw = raw.replace(old_type, new_type, 1)
            # The first date in the official frame is a fixed protocol
            # baseline (20230905), not the requested start date. Replace only
            # the two actual range fields that follow it.
            dates = [start_date.encode("ascii"), end_date.encode("ascii")]
            date_offsets = [m for m in range(len(raw)) if raw.startswith(b"20260901", m) or raw.startswith(b"20260905", m)]
            if len(date_offsets) >= 2:
                raw = raw[:date_offsets[0]] + dates[0] + raw[date_offsets[0] + 8:]
                second = date_offsets[1] - 8 + len(dates[0])
                raw = raw[:second] + dates[1] + raw[second + 8:]
            if amount_threshold is not None:
                raw = raw.replace(b"1000", str(int(amount_threshold)).encode(), 1)
            return struct.pack(">I", len(raw) - 4) + raw[4:]
        # Use the complete captured filter frame shape. The small container
        # length differs between single- and multi-store selections.
        if stores or document_types or style_numbers or seasons or shipment_groups or unit_price_threshold is not None or unit_discount_threshold is not None or not return_whole_order:
            container_len = 6 if document_types or amount_threshold is not None or len(stores) == 1 else 5
            filtered_hex = ("000000b78001000100000013717565727953616c6544657461696c4c697374000004de0f00010c"
                            f"000000{container_len:02x}080001000027120b00020000000832303233303930350008000100000005")
            codes = _document_type_codes(document_types)
            type_expr = (" = " + codes[0]) if len(codes) == 1 else (" in (" + ",".join(codes) + ")" if codes else "")
            filtered_hex += (field(expression).hex() + ("0008000100000006" + field(type_expr).hex() if type_expr else "")
                             + "0008000100000003" + field(start_date).hex()
                             + "0008000100000004" + field(end_date).hex()
                             + (("0008000100000009" + field(str(int(amount_threshold))).hex()) if amount_threshold is not None else "")
                             + (("000800010000000f" + field(",".join(sorted(style_numbers))).hex()) if style_numbers else "")
                             + (("0008000100000014" + field(",".join(sorted(seasons))).hex()) if seasons else "")
                             + (("0008000100000016" + field(str(unit_price_threshold)).hex()) if unit_price_threshold is not None else "")
                             + (("0008000100000018" + field(str(unit_discount_threshold)).hex()) if unit_discount_threshold is not None else "")
                             + (("000800010000001c" + field(",".join(sorted(shipment_groups))).hex()) if shipment_groups else "")
                             + "000800010000001d0b000200000001" + ("31" if return_whole_order else "30")
                             + "00080002004c55bf0800030000000100")
            raw = bytes.fromhex(filtered_hex)
            raw = raw.replace(b"20230905", b"20230920", 1)
            method_end = raw.find(b"querySaleDetailList") + len(b"querySaleDetailList")
            # EMS includes a fixed query descriptor length for this captured
            # filter shape; the server rejects a recomputed short descriptor.
            descriptor_len = 0x5D3 if document_types else 0x4DE
            raw = raw[:method_end] + struct.pack(">I", descriptor_len) + raw[method_end + 4:]
            return struct.pack(">I", len(raw) - 4) + raw[4:]

        # Replace the complete captured filter parameter block, including the
        # original second date parameter.
        marker = bytes.fromhex("0008000100000003")
        pos = raw.find(marker)
        if pos >= 0:
            tail = raw[pos:]
            prefix = b"\x08\x00\x01" if first else b"\x00\x08\x00\x01"
            replacement = b"\x00\x08\x00\x01" + struct.pack(">I", 5) + field(expression)
            replacement += b"\x00\x08\x00\x01" + struct.pack(">I", 3) + field(end_date)
            replacement += b"\x00\x08\x00\x01" + struct.pack(">I", 4) + field(end_date)
            replacement += b"\x00\x08\x00\x01" + struct.pack(">I", 9) + field(str(int(amount_threshold or 0)))
            # tail begins with the old end-date outer field; skip it and keep
            # the final zero parameter from the verified frame.
            zero_marker = bytes.fromhex("000800010000001d")
            zero_pos = tail.find(zero_marker)
            replacement += tail[zero_pos:] if zero_pos >= 0 else tail
            raw = prefix + replacement
    # The captured template's length prefix was produced for one date shape;
    # recompute it after substitution so the server receives a valid frame.
    return struct.pack(">I", len(raw) - 4) + raw[4:]


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
                            unit_discount_range: tuple[float | None, float | None] | None = None) -> bytes:
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
            ))
            result = recv_frame(sock)
            return result
