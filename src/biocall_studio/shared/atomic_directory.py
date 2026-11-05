"""Durable same-volume directory publication without replacement."""

from __future__ import annotations

import ctypes
import errno
import os
import sys
from pathlib import Path


def atomic_publish_directory_no_replace(staging: Path, final: Path) -> None:
    """Atomically rename one staged directory and refuse an existing target."""
    if sys.platform == "darwin":
        library = ctypes.CDLL(None, use_errno=True)
        renamex = library.renamex_np
        renamex.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex.restype = ctypes.c_int
        if renamex(os.fsencode(staging), os.fsencode(final), 0x00000004) != 0:
            code = ctypes.get_errno()
            if code in {errno.EEXIST, errno.ENOTEMPTY}:
                raise FileExistsError(code, os.strerror(code), str(final))
            raise OSError(code, os.strerror(code), str(final))
        return
    if sys.platform.startswith("linux"):
        library = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(library, "renameat2", None)
        if renameat2 is None:
            raise OSError(errno.ENOSYS, "atomic no-replace publication is unavailable")
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        if renameat2(-100, os.fsencode(staging), -100, os.fsencode(final), 1) != 0:
            code = ctypes.get_errno()
            if code in {errno.EEXIST, errno.ENOTEMPTY}:
                raise FileExistsError(code, os.strerror(code), str(final))
            raise OSError(code, os.strerror(code), str(final))
        return
    if os.name == "nt":
        os.rename(staging, final)
        return
    raise OSError(errno.ENOSYS, "atomic no-replace publication is unavailable")


def fsync_directory_tree(root: Path) -> None:
    """Flush regular files and contained directories before publication."""
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
    for directory in sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        fsync_directory(directory)
    fsync_directory(root)


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "atomic_publish_directory_no_replace",
    "fsync_directory",
    "fsync_directory_tree",
]
