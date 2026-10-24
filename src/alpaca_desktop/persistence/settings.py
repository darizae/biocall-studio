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
        if not isinstance(raw, dict) or set(raw) != {"schema_version", "collection_path"}:
            raise ValueError(f"Unsupported Application Settings at {self.path}")
        collection_path = raw.get("collection_path")
        if raw.get("schema_version") != 1 or (
            collection_path is not None
            and (not isinstance(collection_path, str) or not Path(collection_path).is_absolute())
        ):
            raise ValueError(f"Invalid Application Settings at {self.path}")
        return ApplicationSettings(Path(collection_path) if collection_path else None)

    def save(self, settings: ApplicationSettings) -> None:
        raw = {
            "schema_version": 1,
            "collection_path": str(settings.collection_path) if settings.collection_path else None,
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
