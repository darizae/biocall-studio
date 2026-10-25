"""Small, versioned machine-local settings; no scientific artifacts live here."""

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ApplicationSettings:
    """Only a verified Collection binding belongs in machine-local settings."""

    collection_path: Path | None = None
    collection_id: str | None = None


class SettingsStore:
    """Read one JSON document; atomically replace it only after successful writing."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> ApplicationSettings:
        try:
            with self.path.open(encoding="utf-8") as stream:
                raw = json.load(stream)
        except FileNotFoundError:
            return ApplicationSettings()
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid Application Settings at {self.path}: {exc}") from exc
        if not isinstance(raw, dict) or set(raw) != {
            "schema_version",
            "collection_path",
            "collection_id",
        }:
            raise ValueError(f"Unsupported Application Settings at {self.path}")
        collection_path = raw.get("collection_path")
        collection_id = raw.get("collection_id")
        if (
            raw.get("schema_version") != 2
            or (
                collection_path is not None
                and (
                    not isinstance(collection_path, str) or not Path(collection_path).is_absolute()
                )
            )
            or (
                collection_id is not None
                and (not isinstance(collection_id, str) or not collection_id)
            )
        ):
            raise ValueError(f"Invalid Application Settings at {self.path}")
        if (collection_path is None) != (collection_id is None):
            raise ValueError(f"Incomplete Collection binding at {self.path}")
        return ApplicationSettings(
            Path(collection_path) if collection_path else None,
            collection_id,
        )

    def save(self, settings: ApplicationSettings) -> None:
        raw = {
            "schema_version": 2,
            "collection_path": str(settings.collection_path) if settings.collection_path else None,
            "collection_id": settings.collection_id,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, delete=False, suffix=".tmp"
            ) as stream:
                temporary = Path(stream.name)
                json.dump(raw, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
