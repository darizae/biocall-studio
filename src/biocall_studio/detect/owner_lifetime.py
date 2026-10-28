"""Detect-owned kernel lease that prevents orphaned Workers from publishing."""

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


class DetectOwnerLease:
    def __init__(self, path: Path, descriptor: int, owner_id: str):
        self.path = path
        self.owner_id = owner_id
        self._descriptor = descriptor

    @classmethod
    def create(cls, application_data_root: Path) -> DetectOwnerLease:
        leases = Path(application_data_root) / "detect" / "v1" / "leases"
        leases.mkdir(parents=True, mode=0o700, exist_ok=True)
        if leases.is_symlink() or not leases.is_dir():
            raise ValueError("Detect lease storage is unsafe.")
        cls._cleanup(leases)
        owner_id = f"owner_{uuid.uuid4().hex}"
        path = leases / f"{owner_id}.lease"
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
    def _cleanup(leases: Path) -> None:
        for path in leases.glob("owner_*.lease"):
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
                except (BlockingIOError, PermissionError):
                    continue
                except OSError:
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


class DetectWorkerOwnerGuard:
    def __init__(self, path: Path):
        if path.is_symlink() or not path.is_file():
            raise ValueError("Detect Worker owner lease is missing or unsafe.")
        flags = os.O_RDWR | (os.O_CLOEXEC if hasattr(os, "O_CLOEXEC") else 0)
        self._descriptor = os.open(path, flags)
        self._stop = threading.Event()

    def owner_alive(self) -> bool:
        if self._descriptor < 0:
            return False
        try:
            _lock(self._descriptor)
        except (BlockingIOError, PermissionError):
            return True
        except OSError:
            return False
        else:
            _unlock(self._descriptor)
            return False

    def start_watchdog(self, *, interval_seconds: float = 0.1) -> None:
        def watch() -> None:
            while not self._stop.wait(interval_seconds):
                if not self.owner_alive():
                    os._exit(70)

        threading.Thread(
            target=watch,
            name="biocall-studio-detect-owner-watchdog",
            daemon=True,
        ).start()

    def close(self) -> None:
        self._stop.set()
        if self._descriptor >= 0:
            os.close(self._descriptor)
            self._descriptor = -1
