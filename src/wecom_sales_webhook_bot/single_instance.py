from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass


@dataclass
class InstanceGuard:
    handle: object | None
    acquired: bool

    def close(self) -> None:
        if self.handle is None or os.name != "nt":
            return
        try:
            import ctypes
            ctypes.windll.kernel32.CloseHandle(self.handle)
        except Exception:  # noqa: BLE001
            pass
        self.handle = None


def instance_name(kind: str, identity: str) -> str:
    digest = hashlib.sha256(str(identity).lower().encode("utf-8")).hexdigest()[:24]
    return f"Local\\WeComSalesWebhook_{kind}_{digest}"


def acquire_instance(kind: str, identity: str) -> InstanceGuard:
    """Acquire a per-config Windows mutex and keep its handle alive."""
    if os.name != "nt":
        return InstanceGuard(None, True)
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, instance_name(kind, identity))
    if not handle:
        return InstanceGuard(None, False)
    already_exists = kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS
    return InstanceGuard(handle, not already_exists)
