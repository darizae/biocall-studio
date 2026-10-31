"""Kernel-released owner leases for supervised workflow processes."""

from __future__ import annotations

import os
import sys
import threading
import uuid
from pathlib import Path


def _lock(descriptor: int) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(descriptor: int) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_UN)


def _lock_is_held(exc: OSError) -> bool:
    return isinstance(exc, (BlockingIOError, PermissionError)) or (
        sys.platform == "win32" and exc.errno in {13, 36}
    )


class OwnerLease:
    """A unique lock held by a supervisor and released by the kernel on death."""

    def __init__(self, path: Path, descriptor: int, owner_id: str):
        self.path = path
        self.owner_id = owner_id
        self._descriptor = descriptor

    @classmethod
    def create(cls, directory: Path, *, prefix: str = "owner") -> OwnerLease:
        directory = Path(directory)
        directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("Owner lease storage is unsafe.")
        cls._cleanup_stale(directory, prefix=prefix)
        owner_id = f"{prefix}_{uuid.uuid4().hex}"
        path = directory / f"{owner_id}.lease"
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        descriptor = os.open(path, flags, 0o600)
        try:
            os.write(descriptor, b"1")
            os.fsync(descriptor)
            _lock(descriptor)
        except Exception:
            os.close(descriptor)
            path.unlink(missing_ok=True)
            raise
        return cls(path, descriptor, owner_id)

    @staticmethod
    def _cleanup_stale(directory: Path, *, prefix: str) -> None:
        for path in directory.glob(f"{prefix}_*.lease"):
            if path.is_symlink() or not path.is_file():
                continue
            flags = os.O_RDWR | (os.O_CLOEXEC if hasattr(os, "O_CLOEXEC") else 0)
            try:
                descriptor = os.open(path, flags)
            except OSError:
                continue
            stale = False
            try:
                try:
                    _lock(descriptor)
                except OSError as exc:
                    if _lock_is_held(exc):
                        continue
                else:
                    stale = True
                    _unlock(descriptor)
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
            _unlock(descriptor)
        finally:
            os.close(descriptor)
            self.path.unlink(missing_ok=True)


class WorkerOwnerGuard:
    """Worker-side view of a supervisor lease with an optional hard-stop watcher."""

    def __init__(self, path: Path, *, watchdog_name: str = "biocall-studio-owner-watchdog"):
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            raise ValueError("Worker owner lease is missing or unsafe.")
        flags = os.O_RDWR | (os.O_CLOEXEC if hasattr(os, "O_CLOEXEC") else 0)
        self._descriptor = os.open(path, flags)
        self._stop = threading.Event()
        self._watchdog_name = watchdog_name

    def owner_alive(self) -> bool:
        if self._descriptor < 0:
            return False
        try:
            _lock(self._descriptor)
        except OSError as exc:
            return _lock_is_held(exc)
        else:
            _unlock(self._descriptor)
            return False

    def start_watchdog(self, *, interval_seconds: float = 0.2) -> None:
        def watch() -> None:
            while not self._stop.wait(interval_seconds):
                if not self.owner_alive():
                    os._exit(70)

        threading.Thread(target=watch, name=self._watchdog_name, daemon=True).start()

    def close(self) -> None:
        self._stop.set()
        if self._descriptor >= 0:
            os.close(self._descriptor)
            self._descriptor = -1
