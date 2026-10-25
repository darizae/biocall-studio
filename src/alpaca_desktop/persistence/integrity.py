"""Streaming integrity primitives owned by the Trainer persistence layer."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

IO_CHUNK_BYTES = 64 * 1024


def sha256_file(path: Path, *, cancelled: Callable[[], bool] | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(IO_CHUNK_BYTES):
            if cancelled is not None and cancelled():
                raise InterruptedError("Dataset Build cancelled.")
            digest.update(chunk)
    return digest.hexdigest()
