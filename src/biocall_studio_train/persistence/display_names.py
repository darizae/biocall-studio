"""Mutable display names kept separate from immutable scientific manifests."""

from __future__ import annotations

import json
import os
import tempfile
import unicodedata
from pathlib import Path

from biocall_studio_train.domain.paths import validate_relative_path

_KINDS = ("datasets", "models")
_SCHEMA_VERSION = 1


def validate_display_name(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Display name must be text.")
    value = unicodedata.normalize("NFC", value.strip())
    if not value:
        raise ValueError("Display name cannot be empty.")
    if len(value) > 80 or any(ord(character) < 32 for character in value):
        raise ValueError("Display name must be at most 80 printable characters.")
    return value


class DisplayNameStore:
    """Atomically store presentation-only names under one validated Collection."""

    def __init__(self, collection_root: Path):
        collection = collection_root.resolve(strict=True)
        alpaca = collection / ".alpaca"
        if alpaca.is_symlink() or not alpaca.is_dir():
            raise ValueError("Validated Collection metadata folder is missing or unsafe.")
        if not alpaca.resolve(strict=True).is_relative_to(collection):
            raise ValueError("Display-name storage escapes the selected Collection.")
        self._alpaca = alpaca
        self.path = alpaca / "display-names.json"

    def name(self, kind: str, artifact_id: str, fallback: str) -> str:
        kind, artifact_id = self._artifact(kind, artifact_id, require=False)
        return self._read()[kind].get(artifact_id, fallback)

    def names(self, kind: str) -> dict[str, str]:
        kind = self._kind(kind)
        return dict(self._read()[kind])

    def rename(self, kind: str, artifact_id: str, name: str) -> str:
        kind, artifact_id = self._artifact(kind, artifact_id, require=True)
        name = validate_display_name(name)
        payload = self._read()
        payload[kind][artifact_id] = name
        self._write(payload)
        return name

    def forget(self, kind: str, artifact_id: str) -> None:
        kind, artifact_id = self._artifact(kind, artifact_id, require=False)
        payload = self._read()
        if payload[kind].pop(artifact_id, None) is not None:
            self._write(payload)

    def _artifact(self, kind: str, artifact_id: str, *, require: bool) -> tuple[str, str]:
        kind = self._kind(kind)
        safe = validate_relative_path(artifact_id)
        if "/" in safe:
            raise ValueError("Artifact ID must be one portable path segment.")
        artifact = self._alpaca / kind / safe
        if artifact.is_symlink():
            raise ValueError("Artifact directory cannot be a symlink.")
        if require and not artifact.is_dir():
            raise ValueError(f"{kind[:-1].capitalize()} does not exist: {safe}")
        return kind, safe

    @staticmethod
    def _kind(kind: str) -> str:
        if kind not in _KINDS:
            raise ValueError("Display names support datasets and models only.")
        return kind

    def _read(self) -> dict[str, dict[str, str]]:
        try:
            if self.path.is_symlink():
                raise ValueError("Display-name storage cannot be a symlink.")
            with self.path.open(encoding="utf-8") as stream:
                raw = json.load(stream)
        except FileNotFoundError:
            return {"datasets": {}, "models": {}}
        except json.JSONDecodeError as exc:
            raise ValueError("Display-name storage is invalid JSON.") from exc
        if (
            not isinstance(raw, dict)
            or raw.get("schema_version") != _SCHEMA_VERSION
            or set(raw) != {"schema_version", *_KINDS}
        ):
            raise ValueError("Display-name storage has an unsupported schema.")
        result: dict[str, dict[str, str]] = {}
        for kind in _KINDS:
            values = raw[kind]
            if not isinstance(values, dict):
                raise ValueError("Display-name entries must be objects.")
            result[kind] = {
                validate_relative_path(identifier): validate_display_name(name)
                for identifier, name in values.items()
            }
            if any("/" in identifier for identifier in result[kind]):
                raise ValueError("Display-name IDs must be portable path segments.")
        return result

    def _write(self, names: dict[str, dict[str, str]]) -> None:
        payload = {"schema_version": _SCHEMA_VERSION, **names}
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._alpaca,
                prefix=".display-names.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            descriptor = os.open(self._alpaca, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
