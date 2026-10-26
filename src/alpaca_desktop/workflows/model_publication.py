"""Exclusive, durable publication primitives shared by both Model families."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def write_model_manifest(path: Path, payload: dict[str, Any]) -> None:
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def publish_model_directory(stage: Path, final: Path) -> None:
    final.parent.mkdir(parents=True, exist_ok=True)
    lock = final.parent / ".publish.lock"
    descriptor: int | None = None
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.write(descriptor, f"{os.getpid()}\n".encode())
        os.fsync(descriptor)
        if final.exists():
            raise FileExistsError(f"Model already exists: {final.name}")
        os.rename(stage, final)
        try:
            directory = os.open(final.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            pass
    finally:
        if descriptor is not None:
            os.close(descriptor)
            lock.unlink(missing_ok=True)
