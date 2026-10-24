"""Small, versioned machine-local settings; no scientific artifacts live here."""

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT_LABELS = {
    "collection_root": "Collection Root",
    "datasets_root": "Datasets Root",
    "runs_root": "Runs Root",
}


@dataclass
class WorkspaceSettings:
    """Facts persisted in one Application Settings document."""

    roots: dict[str, Path] = field(default_factory=dict)
    source_bindings: dict[str, Path] = field(default_factory=dict)


class SettingsStore:
    """Read one JSON document; atomically replace it only after successful writing."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> WorkspaceSettings:
        try:
            with self.path.open(encoding="utf-8") as stream:
                raw = json.load(stream)
        except FileNotFoundError:
            return WorkspaceSettings()
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid Application Settings at {self.path}: {exc}") from exc
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise ValueError(f"Unsupported Application Settings at {self.path}")
        mappings = []
        for name in ("roots", "source_bindings"):
            values = raw.get(name)
            if not isinstance(values, dict) or any(
                not isinstance(key, str)
                or not key.strip()
                or not isinstance(value, str)
                or not Path(value).is_absolute()
                for key, value in values.items()
            ):
                raise ValueError(f"Invalid {name} in Application Settings at {self.path}")
            mappings.append({key: Path(value) for key, value in values.items()})
        if mappings[0].keys() - ROOT_LABELS.keys():
            raise ValueError(f"Unknown Workspace root in Application Settings at {self.path}")
        return WorkspaceSettings(*mappings)

    def save(self, settings: WorkspaceSettings) -> None:
        raw = {
            "schema_version": 1,
            "roots": {key: str(value) for key, value in settings.roots.items()},
            "source_bindings": {key: str(value) for key, value in settings.source_bindings.items()},
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
