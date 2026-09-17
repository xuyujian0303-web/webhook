from __future__ import annotations

import hashlib
import socket
import struct

from .ems_protocol import frame, recv_frame


def _field_string(index: int, value: str) -> bytes:
    raw = value.encode("utf-8")
    return b"\x0b" + struct.pack(">H", index) + struct.pack(">I", len(raw)) + raw


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
                            document_types: set[str] | None = None) -> bytes:
    """Build the currently verified read-only query shape (YYYYMMDD dates)."""
    hex_template = (
        "000000748001000100000013717565727953616c6544657461696c4c697374"
        "0000000b0f00010c00000003080001000027120b0002000000083230323330393034"
        "00080001000000030b0002000000083230323630393034"
        "000800010000001d0b0002000000013000080002004c55bf0800030000000100"
    )
    raw = bytes.fromhex(hex_template)
    first = bytes.fromhex("3230323330393034")
    second = bytes.fromhex("3230323630393034")
    sentinel = b"__EMS_DATE__"
    raw = raw.replace(first, sentinel, 1)
    raw = raw.replace(second, end_date.encode("ascii"), 1)
    raw = raw.replace(sentinel, start_date.encode("ascii"), 1)
    if store_names or amount_threshold is not None:
        stores = sorted(x.strip() for x in (store_names or set()) if x.strip())
        if len(stores) == 1:
            expression = " = '" + stores[0] + "'"
        elif stores:
            expression = " in (" + ",".join("'" + x + "'" for x in stores) + ")"
        else:
            expression = ""
        def field(value: str) -> bytes:
            encoded = value.encode("utf-8")
            return b"\x0b\x00\x02" + struct.pack(">I", len(encoded)) + encoded
        if document_types and stores:
            # Official EMS frame captured for the "sale" document filter.
            raw = bytes.fromhex("000000c98001000100000013717565727953616c6544657461696c4c697374000006210f00010c00000007080001000027120b000200000008323032333039303500080001000000050b000200000009203d2027473838392700080001000000060b000200000004203d203000080001000000030b000200000008323032363039303100080001000000040b000200000008323032363039303500080001000000090b00020000000431303030000800010000001d0b0002000000013000080002004c55bf0800030000000100")
            old_store = b" in ('G899','G820','G889')"
            expression = (" = '" + stores[0] + "'") if len(stores) == 1 else " in (" + ",".join("'" + x + "'" for x in stores) + ")"
            raw = raw.replace(old_store, expression.encode(), 1)
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
        if stores or document_types:
            container_len = 6 if document_types or amount_threshold is not None or len(stores) == 1 else 5
            filtered_hex = ("000000b78001000100000013717565727953616c6544657461696c4c697374000004de0f00010c"
                            f"000000{container_len:02x}080001000027120b00020000000832303233303930350008000100000005")
            type_codes = {"sale": "0", "preorder": "1", "return": "2", "exchange": "3"}
            codes = [type_codes[x] for x in sorted(document_types or set()) if x in type_codes]
            type_expr = (" = " + codes[0]) if len(codes) == 1 else (" in (" + ",".join(codes) + ")" if codes else "")
            filtered_hex += (field(expression).hex() + ("0008000100000006" + field(type_expr).hex() if type_expr else "")
                             + "0008000100000003" + field(end_date).hex()
                             + "0008000100000004" + field(end_date).hex()
                             + (("0008000100000009" + field(str(int(amount_threshold))).hex()) if amount_threshold is not None else "")
                             + "000800010000001d0b0002000000013000080002004c55bf0800030000000100")
            raw = bytes.fromhex(filtered_hex)
            raw = raw.replace(b"20230905", start_date.encode("ascii"), 1)
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
            prefix = raw[:pos]
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
                          document_types: set[str] | None = None) -> bytes:
        with socket.create_connection((self.data_host, self.data_port), timeout=self.timeout_seconds) as sock:
            sock.settimeout(self.timeout_seconds)
            for request in self._INITIALIZATION_FRAMES:
                sock.sendall(request)
                recv_frame(sock)
            sock.sendall(build_sale_detail_frame(start_date, end_date, store_names, amount_threshold, document_types))
            result = recv_frame(sock)
            return result
