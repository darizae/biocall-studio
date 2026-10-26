"""GUI-lifetime automatic idle-sleep inhibition behind a small OS adapter."""

from __future__ import annotations

import ctypes
import sys
import threading
from dataclasses import dataclass
from typing import Protocol


class PowerInhibitionUnavailable(OSError):
    """The current operating system cannot provide the requested inhibition."""


class PowerAdapter(Protocol):
    def acquire(self) -> None: ...

    def release(self) -> None: ...


@dataclass(frozen=True)
class KeepAwakeState:
    requested: bool = False
    active: bool = False
    available: bool = True
    error: str = ""


class KeepAwakeManager:
    """Apply one persisted choice without conflating it with effective OS state."""

    def __init__(self, adapter: PowerAdapter):
        self._adapter = adapter
        self._state = KeepAwakeState()

    @property
    def state(self) -> KeepAwakeState:
        return self._state

    def apply_requested(self, requested: bool) -> KeepAwakeState:
        if not isinstance(requested, bool):
            raise TypeError("Keep-awake preference must be boolean.")
        if requested and self._state.active:
            self._state = KeepAwakeState(True, True, self._state.available, "")
            return self._state
        if not requested and not self._state.active:
            self._state = KeepAwakeState(False, False, self._state.available, "")
            return self._state
        try:
            if requested:
                self._adapter.acquire()
            else:
                self._adapter.release()
        except PowerInhibitionUnavailable as exc:
            self._state = KeepAwakeState(requested, False, False, str(exc))
        except OSError as exc:
            self._state = KeepAwakeState(
                requested,
                self._state.active,
                True,
                str(exc) or "The operating system rejected the keep-awake request.",
            )
        else:
            self._state = KeepAwakeState(requested, requested, True, "")
        return self._state

    def release_for_shutdown(self) -> KeepAwakeState:
        return self.apply_requested(False)


class UnsupportedPowerAdapter:
    def acquire(self) -> None:
        raise PowerInhibitionUnavailable(
            "Keep computer awake is unavailable on this operating system."
        )

    def release(self) -> None:
        return


class MacOSPowerAdapter:
    """Own one PreventUserIdleSystemSleep assertion in the GUI process."""

    _ASSERTION_TYPE = b"PreventUserIdleSystemSleep"
    _REASON = b"alpaca Desktop Trainer long-running local work"
    _UTF8 = 0x08000100
    _LEVEL_ON = 255

    def __init__(self):
        self._assertion_id: int | None = None
        self._iokit = ctypes.CDLL("/System/Library/Frameworks/IOKit.framework/IOKit")
        self._core_foundation = ctypes.CDLL(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )
        self._core_foundation.CFStringCreateWithCString.restype = ctypes.c_void_p
        self._core_foundation.CFStringCreateWithCString.argtypes = (
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_uint32,
        )
        self._core_foundation.CFRelease.argtypes = (ctypes.c_void_p,)
        self._iokit.IOPMAssertionCreateWithName.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
        )
        self._iokit.IOPMAssertionCreateWithName.restype = ctypes.c_int32
        self._iokit.IOPMAssertionRelease.argtypes = (ctypes.c_uint32,)
        self._iokit.IOPMAssertionRelease.restype = ctypes.c_int32

    def _cf_string(self, value: bytes) -> int:
        result = self._core_foundation.CFStringCreateWithCString(None, value, self._UTF8)
        if not result:
            raise OSError("macOS could not prepare the idle-sleep assertion.")
        return result

    def acquire(self) -> None:
        if self._assertion_id is not None:
            return
        assertion_type = self._cf_string(self._ASSERTION_TYPE)
        reason = self._cf_string(self._REASON)
        assertion_id = ctypes.c_uint32()
        try:
            result = self._iokit.IOPMAssertionCreateWithName(
                assertion_type,
                self._LEVEL_ON,
                reason,
                ctypes.byref(assertion_id),
            )
        finally:
            self._core_foundation.CFRelease(assertion_type)
            self._core_foundation.CFRelease(reason)
        if result != 0:
            raise OSError(f"macOS rejected the idle-sleep assertion ({result}).")
        self._assertion_id = int(assertion_id.value)

    def release(self) -> None:
        if self._assertion_id is None:
            return
        assertion_id = self._assertion_id
        result = self._iokit.IOPMAssertionRelease(assertion_id)
        if result != 0:
            raise OSError(f"macOS could not release the idle-sleep assertion ({result}).")
        self._assertion_id = None


class WindowsPowerAdapter:
    """Use SetThreadExecutionState only from the thread which acquired it."""

    _ES_SYSTEM_REQUIRED = 0x00000001
    _ES_CONTINUOUS = 0x80000000

    def __init__(self):
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.SetThreadExecutionState.argtypes = (ctypes.c_uint32,)
        self._kernel32.SetThreadExecutionState.restype = ctypes.c_uint32
        self._owner_thread: int | None = None

    def acquire(self) -> None:
        owner = threading.get_ident()
        if self._owner_thread is not None:
            if self._owner_thread != owner:
                raise OSError("Keep-awake state belongs to a different GUI thread.")
            return
        result = self._kernel32.SetThreadExecutionState(
            self._ES_CONTINUOUS | self._ES_SYSTEM_REQUIRED
        )
        if result == 0:
            raise OSError(f"Windows rejected the idle-sleep request ({ctypes.get_last_error()}).")
        self._owner_thread = owner

    def release(self) -> None:
        if self._owner_thread is None:
            return
        if self._owner_thread != threading.get_ident():
            raise OSError("Keep-awake state must be released on its owning GUI thread.")
        result = self._kernel32.SetThreadExecutionState(self._ES_CONTINUOUS)
        if result == 0:
            raise OSError(
                f"Windows could not release the idle-sleep request ({ctypes.get_last_error()})."
            )
        self._owner_thread = None


def native_power_adapter() -> PowerAdapter:
    if sys.platform == "darwin":
        return MacOSPowerAdapter()
    if sys.platform == "win32":
        return WindowsPowerAdapter()
    return UnsupportedPowerAdapter()
