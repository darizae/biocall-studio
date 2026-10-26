"""Kernel-released owner lease used to stop orphaned scientific Workers."""

from __future__ import annotations

import os
import sys
import threading
import uuid
from pathlib import Path


def _acquire_lock(descriptor: int) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release_lock(descriptor: int) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_UN)


class OwnerLease:
    """A unique lock held by one GUI process and released by the kernel on death."""

    def __init__(self, path: Path, descriptor: int):
        self.path = path
        self._descriptor = descriptor

    @classmethod
    def create(cls, settings_dir: Path) -> OwnerLease:
        settings_dir.mkdir(parents=True, exist_ok=True)
        cls._cleanup_stale(settings_dir)
        path = settings_dir / f"owner-{uuid.uuid4().hex}.lease"
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        descriptor = os.open(path, flags, 0o600)
        try:
            os.write(descriptor, b"1")
            os.fsync(descriptor)
            _acquire_lock(descriptor)
        except Exception:
            os.close(descriptor)
            path.unlink(missing_ok=True)
            raise
        return cls(path, descriptor)

    @staticmethod
    def _cleanup_stale(settings_dir: Path) -> None:
        for path in settings_dir.glob("owner-*.lease"):
            if path.is_symlink() or not path.is_file():
                continue
            flags = os.O_RDWR
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            try:
                descriptor = os.open(path, flags)
            except OSError:
                continue
            stale = False
            try:
                try:
                    _acquire_lock(descriptor)
                except (BlockingIOError, PermissionError):
                    continue
                except OSError as exc:
                    if sys.platform == "win32" and exc.errno in {13, 36}:
                        continue
                    continue
                else:
                    stale = True
                    _release_lock(descriptor)
            finally:
                os.close(descriptor)
            if stale:
                path.unlink(missing_ok=True)

    def close(self) -> None:
        if self._descriptor < 0:
            return
        descriptor = self._descriptor
        self._descriptor = -1
        try:
            _release_lock(descriptor)
        finally:
            os.close(descriptor)
            self.path.unlink(missing_ok=True)


class WorkerOwnerGuard:
    """A Worker-side view of the GUI-owned lease with an optional hard-stop watcher."""

    def __init__(self, path: Path):
        if path.is_symlink() or not path.is_file():
            raise ValueError("Worker owner lease is missing or unsafe.")
        flags = os.O_RDWR
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        self._descriptor = os.open(path, flags)
        self._stop = threading.Event()

    def owner_alive(self) -> bool:
        if self._descriptor < 0:
            return False
        try:
            _acquire_lock(self._descriptor)
        except (BlockingIOError, PermissionError):
            return True
        except OSError as exc:
            if sys.platform == "win32" and exc.errno in {13, 36}:
                return True
            return False
        else:
            _release_lock(self._descriptor)
            return False

    def start_watchdog(self, *, interval_seconds: float = 0.2) -> None:
        def watch() -> None:
            while not self._stop.wait(interval_seconds):
                if not self.owner_alive():
                    os._exit(70)

        threading.Thread(target=watch, name="alpaca-owner-watchdog", daemon=True).start()

    def close(self) -> None:
        self._stop.set()
        if self._descriptor >= 0:
            os.close(self._descriptor)
            self._descriptor = -1
