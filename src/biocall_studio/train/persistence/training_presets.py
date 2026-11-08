"""Atomic user-level persistence for versioned training configuration presets."""

from __future__ import annotations

import json
import os
import tempfile
import unicodedata
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType

from biocall_studio.train.domain.training import TrainingDraft

PRESET_STORE_SCHEMA_VERSION = 1
CATALOG_REVISION = "training-fields-v1"
TOOLBOX_SCHEMA_REVISION = "bioacoustics-dl-toolbox-0.3.0"
PIPELINE_SCHEMA_REVISION = "alpaca-pipelines-training-spec-v1"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _normalized_name(label: str) -> str:
    return unicodedata.normalize("NFC", label.strip()).casefold()


def _validate_name(label: str) -> str:
    if not isinstance(label, str):
        raise ValueError("Preset name must be text.")
    cleaned = unicodedata.normalize("NFC", label.strip())
    if (
        not cleaned
        or len(cleaned) > 80
        or cleaned in {".", ".."}
        or "/" in cleaned
        or "\\" in cleaned
        or any(ord(character) < 32 for character in cleaned)
    ):
        raise ValueError("Preset name must be 1–80 safe printable characters without slashes.")
    return cleaned


@dataclass(frozen=True)
class PresetRecord:
    preset_id: str
    label: str
    family: str
    values: Mapping[str, object]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class LoadedPreset:
    record: PresetRecord
    draft: TrainingDraft


class PresetStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.path = self.directory / "presets.json"

    def list(self) -> tuple[PresetRecord, ...]:
        records = self._read()
        return tuple(sorted(records, key=lambda item: (item.family, item.label.casefold())))

    def create(self, label: str, draft: TrainingDraft) -> PresetRecord:
        records = list(self._read())
        label = _validate_name(label)
        self._assert_unique(records, label)
        timestamp = _now()
        record = PresetRecord(
            preset_id=uuid.uuid4().hex,
            label=label,
            family=draft.family,
            values=MappingProxyType(dict(draft.values)),
            created_at=timestamp,
            updated_at=timestamp,
        )
        records.append(record)
        self._write(records)
        return record

    def load(self, preset_id: str) -> LoadedPreset:
        record = self._find(self._read(), preset_id)
        return LoadedPreset(record, TrainingDraft(record.family, record.values))

    def rename(self, preset_id: str, label: str) -> PresetRecord:
        records = list(self._read())
        current = self._find(records, preset_id)
        label = _validate_name(label)
        self._assert_unique(records, label, excluding=preset_id)
        changed = PresetRecord(
            current.preset_id,
            label,
            current.family,
            current.values,
            current.created_at,
            _now(),
        )
        self._replace_record(records, changed)
        self._write(records)
        return changed

    def duplicate(self, preset_id: str, label: str) -> PresetRecord:
        current = self._find(self._read(), preset_id)
        return self.create(label, TrainingDraft(current.family, current.values))

    def overwrite(self, preset_id: str, draft: TrainingDraft) -> PresetRecord:
        records = list(self._read())
        current = self._find(records, preset_id)
        if current.family != draft.family:
            raise ValueError("A preset can only be overwritten by its own model family.")
        changed = PresetRecord(
            current.preset_id,
            current.label,
            current.family,
            MappingProxyType(dict(draft.values)),
            current.created_at,
            _now(),
        )
        self._replace_record(records, changed)
        self._write(records)
        return changed

    def delete(self, preset_id: str) -> None:
        records = list(self._read())
        self._find(records, preset_id)
        self._write([record for record in records if record.preset_id != preset_id])

    @staticmethod
    def _find(
        records: list[PresetRecord] | tuple[PresetRecord, ...], preset_id: str
    ) -> PresetRecord:
        found = next((record for record in records if record.preset_id == preset_id), None)
        if found is None:
            raise KeyError(f"Unknown preset: {preset_id}")
        return found

    @staticmethod
    def _replace_record(records: list[PresetRecord], changed: PresetRecord) -> None:
        index = records.index(next(item for item in records if item.preset_id == changed.preset_id))
        records[index] = changed

    @staticmethod
    def _assert_unique(
        records: list[PresetRecord], label: str, *, excluding: str | None = None
    ) -> None:
        normalized = _normalized_name(label)
        if any(
            record.preset_id != excluding and _normalized_name(record.label) == normalized
            for record in records
        ):
            raise ValueError("A preset with this name already exists.")

    def _read(self) -> tuple[PresetRecord, ...]:
        if not self.path.exists():
            return ()
        if self.path.is_symlink() or not self.path.is_file():
            raise ValueError("Preset storage must be a regular application file.")
        try:
            with self.path.open(encoding="utf-8") as stream:
                raw = json.load(stream)
        except json.JSONDecodeError as exc:
            raise ValueError("Preset store contains invalid JSON.") from exc
        if not isinstance(raw, dict) or raw.get("schema_version") != PRESET_STORE_SCHEMA_VERSION:
            raise ValueError("Unsupported preset store schema.")
        expected = {
            "schema_version",
            "catalog_revision",
            "toolbox_schema_revision",
            "pipeline_schema_revision",
            "presets",
        }
        if set(raw) != expected:
            raise ValueError("Preset store contains unsupported fields.")
        if raw["catalog_revision"] != CATALOG_REVISION:
            raise ValueError("Preset catalog revision is incompatible with this Trainer.")
        if raw["toolbox_schema_revision"] != TOOLBOX_SCHEMA_REVISION:
            raise ValueError("Preset toolbox revision is incompatible with this Trainer.")
        if raw["pipeline_schema_revision"] != PIPELINE_SCHEMA_REVISION:
            raise ValueError("Preset pipeline revision is incompatible with this Trainer.")
        if not isinstance(raw["presets"], list):
            raise ValueError("Preset entries must be a list.")
        records: list[PresetRecord] = []
        ids: set[str] = set()
        names: set[str] = set()
        for item in raw["presets"]:
            record = self._parse_record(item)
            normalized = _normalized_name(record.label)
            if record.preset_id in ids or normalized in names:
                raise ValueError("Preset IDs and normalized names must be unique.")
            ids.add(record.preset_id)
            names.add(normalized)
            records.append(record)
        return tuple(records)

    @staticmethod
    def _parse_record(raw: object) -> PresetRecord:
        expected = {"preset_id", "label", "family", "values", "created_at", "updated_at"}
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError("Preset record contains missing or unsupported fields.")
        preset_id = raw["preset_id"]
        if not isinstance(preset_id, str) or len(preset_id) != 32:
            raise ValueError("Preset ID is invalid.")
        try:
            int(preset_id, 16)
        except ValueError as exc:
            raise ValueError("Preset ID is invalid.") from exc
        label = _validate_name(raw["label"])
        if not isinstance(raw["values"], dict):
            raise ValueError("Preset values must be an object.")
        draft = TrainingDraft(raw["family"], raw["values"])
        for key in ("created_at", "updated_at"):
            if not isinstance(raw[key], str):
                raise ValueError("Preset timestamps must be strings.")
            try:
                datetime.fromisoformat(raw[key])
            except ValueError as exc:
                raise ValueError("Preset timestamp is invalid.") from exc
        return PresetRecord(
            preset_id,
            label,
            draft.family,
            MappingProxyType(dict(draft.values)),
            raw["created_at"],
            raw["updated_at"],
        )

    def _write(self, records: list[PresetRecord]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.directory.is_symlink() or not self.directory.is_dir():
            raise OSError("Preset storage directory is unsafe.")
        self.directory.chmod(0o700)
        payload = {
            "schema_version": PRESET_STORE_SCHEMA_VERSION,
            "catalog_revision": CATALOG_REVISION,
            "toolbox_schema_revision": TOOLBOX_SCHEMA_REVISION,
            "pipeline_schema_revision": PIPELINE_SCHEMA_REVISION,
            "presets": [
                {
                    "preset_id": record.preset_id,
                    "label": record.label,
                    "family": record.family,
                    "values": dict(record.values),
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                }
                for record in records
            ],
        }
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.directory,
                prefix=".presets-",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(0o600)
            os.replace(temporary, self.path)
            temporary = None
            try:
                descriptor = os.open(self.directory, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            except OSError:
                pass
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
