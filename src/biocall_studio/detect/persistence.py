"""Contained, versioned, application-owned Detect Collection persistence."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from biocall_studio.detect.domain import (
    DetectCollectionRef,
    DetectRootBinding,
    RootBindingDecision,
    RootEvidence,
    RootObservation,
    apply_confirmed_relink,
    decide_root_binding,
    detect_workspace_path,
    validate_collection_id,
    validate_display_label,
)

_MAX_METADATA_BYTES = 1_048_576
_SETTINGS_SCHEMA_VERSION = 1


class WorkspaceMetadataError(ValueError):
    """Detect metadata is unsafe, corrupt, unsupported, or internally inconsistent."""


@dataclass(frozen=True, slots=True)
class CollectionPaths:
    workspace_root: Path
    collection_directory: Path
    public_manifest: Path
    private_binding: Path
    last_good_manifest: Path
    last_good_binding: Path


@dataclass(frozen=True, slots=True)
class PersistedDetectCollection:
    ref: DetectCollectionRef
    binding: DetectRootBinding

    @property
    def source_root(self) -> Path:
        return path_from_file_uri(self.binding.source_root_uri)


@dataclass(frozen=True, slots=True)
class RootBindingProposal:
    collection_id: str
    binding_revision: int
    previous_root: Path
    candidate_root: Path
    candidate_evidence: RootEvidence | None
    decision: RootBindingDecision

    @property
    def can_confirm(self) -> bool:
        return self.decision is RootBindingDecision.AWAITING_CONFIRMATION


def path_from_file_uri(value: str) -> Path:
    parsed = urlparse(value)
    if parsed.scheme != "file" or parsed.params or parsed.query or parsed.fragment:
        raise ValueError("Detect root binding contains an unsupported URI.")
    if parsed.netloc not in {"", "localhost"}:
        raise ValueError("Detect root binding must refer to a local folder.")
    decoded = url2pathname(unquote(parsed.path))
    if os.name == "nt" and decoded.startswith("/") and len(decoded) > 2 and decoded[2] == ":":
        decoded = decoded[1:]
    path = Path(decoded)
    if not path.is_absolute():
        raise ValueError("Detect root binding must contain an absolute folder URI.")
    return path


def _inspect_root(path: Path) -> tuple[RootObservation, Path]:
    requested = Path(path).expanduser()
    try:
        resolved = requested.resolve(strict=True)
    except FileNotFoundError:
        return RootObservation.missing(), requested.resolve(strict=False)
    except (OSError, RuntimeError):
        return RootObservation.inaccessible(), requested.resolve(strict=False)
    if not resolved.is_dir() or not os.access(resolved, os.R_OK | os.X_OK):
        return RootObservation.inaccessible(), resolved
    try:
        with os.scandir(resolved):
            pass
        info = resolved.stat()
        evidence = RootEvidence(filesystem_id=info.st_dev, file_id=info.st_ino)
    except (OSError, ValueError):
        return RootObservation.inaccessible(), resolved
    return RootObservation.available(evidence), resolved


def _ensure_directory(path: Path) -> None:
    if path.is_symlink():
        raise WorkspaceMetadataError(f"Application-owned path cannot be a symlink: {path.name}")
    if path.exists():
        if not path.is_dir():
            raise WorkspaceMetadataError(
                f"Application-owned path must be a directory: {path.name}"
            )
    else:
        path.mkdir(mode=0o700)
    path.chmod(0o700)


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise WorkspaceMetadataError(f"Metadata path is not a contained regular file: {path.name}")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            os.chmod(temporary, 0o600)
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _read_json(path: Path, *, label: str) -> object:
    if path.is_symlink() or not path.is_file():
        raise WorkspaceMetadataError(f"{label} is missing or is a symlink.")
    try:
        if path.stat().st_size > _MAX_METADATA_BYTES:
            raise WorkspaceMetadataError(f"{label} exceeds the 1 MiB limit.")
        with path.open(encoding="utf-8") as stream:
            return json.load(stream)
    except json.JSONDecodeError as exc:
        raise WorkspaceMetadataError(f"{label} is corrupt.") from exc
    except OSError as exc:
        raise WorkspaceMetadataError(f"{label} cannot be read.") from exc


class DetectWorkspaceStore:
    """Own Detect metadata below one per-user application-data root."""

    def __init__(self, application_data_root: Path):
        root = Path(application_data_root).expanduser()
        if root.is_symlink():
            raise WorkspaceMetadataError("Application data root cannot be a symlink.")
        self.application_data_root = root.resolve(strict=False)
        self.workspace_root = detect_workspace_path(self.application_data_root)
        self.collections_root = self.workspace_root / "collections"
        self.settings_path = self.workspace_root / "settings.json"

    def _ensure_storage(self) -> None:
        self.application_data_root.mkdir(parents=True, exist_ok=True)
        if self.application_data_root.is_symlink() or not self.application_data_root.is_dir():
            raise WorkspaceMetadataError("Application data root must be a real directory.")
        for path in (
            self.application_data_root / "detect",
            self.workspace_root,
            self.collections_root,
        ):
            _ensure_directory(path)

    def paths_for(self, collection_id: str) -> CollectionPaths:
        safe_id = validate_collection_id(collection_id)
        directory = self.collections_root / safe_id
        last_good = directory / ".last-good"
        return CollectionPaths(
            workspace_root=self.workspace_root,
            collection_directory=directory,
            public_manifest=directory / "collection.json",
            private_binding=directory / "binding.json",
            last_good_manifest=last_good / "collection.json",
            last_good_binding=last_good / "binding.json",
        )

    def _validate_source_separation(self, source_root: Path) -> None:
        workspace = self.workspace_root.resolve(strict=False)
        if (
            source_root == workspace
            or source_root.is_relative_to(workspace)
            or workspace.is_relative_to(source_root)
        ):
            raise ValueError(
                "The recordings folder and Detect application-data folder must be separate."
            )

    def create_collection(
        self, display_label: str, source_root: Path
    ) -> PersistedDetectCollection:
        observation, resolved = _inspect_root(source_root)
        if observation.evidence is None:
            state = "missing" if observation.kind.value == "missing" else "cannot be read"
            raise ValueError(f"The selected recordings folder is {state}.")
        self._validate_source_separation(resolved)
        ref = DetectCollectionRef.create(
            validate_display_label(display_label), observation.evidence
        )
        binding = DetectRootBinding(
            collection_id=ref.collection_id,
            binding_revision=ref.binding_revision,
            source_root_uri=resolved.as_uri(),
        )
        self._ensure_storage()
        paths = self.paths_for(ref.collection_id)
        paths.collection_directory.mkdir(mode=0o700)
        paths.collection_directory.chmod(0o700)
        for namespace in ("runs", "results", "exports"):
            _ensure_directory(paths.collection_directory / namespace)
        _ensure_directory(paths.last_good_manifest.parent)
        try:
            self._write_pair(paths, ref, binding, update_last_good=True)
            self._save_active_collection_id(ref.collection_id)
        except Exception:
            # An incomplete, unreferenced directory is intentionally retained for diagnosis.
            raise
        return PersistedDetectCollection(ref, binding)

    def _write_pair(
        self,
        paths: CollectionPaths,
        ref: DetectCollectionRef,
        binding: DetectRootBinding,
        *,
        update_last_good: bool,
        previous: PersistedDetectCollection | None = None,
    ) -> None:
        binding_written = False
        manifest_written = False
        try:
            _write_json_atomic(paths.private_binding, binding.to_private_dict())
            binding_written = True
            _write_json_atomic(paths.public_manifest, ref.to_public_dict())
            manifest_written = True
        except Exception:
            if previous is not None:
                if binding_written:
                    _write_json_atomic(
                        paths.private_binding, previous.binding.to_private_dict()
                    )
                if manifest_written:
                    _write_json_atomic(paths.public_manifest, previous.ref.to_public_dict())
            raise
        if update_last_good:
            last_good_binding_written = False
            last_good_manifest_written = False
            try:
                _write_json_atomic(paths.last_good_binding, binding.to_private_dict())
                last_good_binding_written = True
                _write_json_atomic(paths.last_good_manifest, ref.to_public_dict())
                last_good_manifest_written = True
            except Exception:
                if previous is not None:
                    if last_good_binding_written:
                        _write_json_atomic(
                            paths.last_good_binding, previous.binding.to_private_dict()
                        )
                    if last_good_manifest_written:
                        _write_json_atomic(
                            paths.last_good_manifest, previous.ref.to_public_dict()
                        )
                raise

    def _load_pair(
        self, manifest_path: Path, binding_path: Path, *, collection_id: str
    ) -> PersistedDetectCollection:
        try:
            ref = DetectCollectionRef.from_public_dict(
                _read_json(manifest_path, label="Detect Collection metadata")
            )
            binding = DetectRootBinding.from_private_dict(
                _read_json(binding_path, label="Detect root binding")
            )
        except WorkspaceMetadataError:
            raise
        except ValueError as exc:
            category = "unsupported" if "Unsupported" in str(exc) else "invalid"
            raise WorkspaceMetadataError(f"Detect workspace metadata is {category}: {exc}") from exc
        if (
            ref.collection_id != collection_id
            or binding.collection_id != collection_id
            or binding.binding_revision != ref.binding_revision
        ):
            raise WorkspaceMetadataError("Detect workspace metadata is internally inconsistent.")
        try:
            path_from_file_uri(binding.source_root_uri)
        except ValueError as exc:
            raise WorkspaceMetadataError("Detect root binding is invalid.") from exc
        return PersistedDetectCollection(ref, binding)

    def load_collection(self, collection_id: str) -> PersistedDetectCollection:
        paths = self.paths_for(collection_id)
        if paths.collection_directory.is_symlink():
            raise WorkspaceMetadataError("Detect Collection directory cannot be a symlink.")
        if not paths.collection_directory.is_dir():
            raise WorkspaceMetadataError("Detect Collection metadata is missing.")
        return self._load_pair(
            paths.public_manifest,
            paths.private_binding,
            collection_id=collection_id,
        )

    def load_last_good(self, collection_id: str) -> PersistedDetectCollection:
        paths = self.paths_for(collection_id)
        if paths.last_good_manifest.parent.is_symlink():
            raise WorkspaceMetadataError("Last-good metadata directory cannot be a symlink.")
        return self._load_pair(
            paths.last_good_manifest,
            paths.last_good_binding,
            collection_id=collection_id,
        )

    def _save_active_collection_id(self, collection_id: str) -> None:
        self._ensure_storage()
        _write_json_atomic(
            self.settings_path,
            {
                "schema_version": _SETTINGS_SCHEMA_VERSION,
                "active_collection_id": validate_collection_id(collection_id),
            },
        )

    def active_collection_id(self) -> str | None:
        if not self.settings_path.exists() and not self.settings_path.is_symlink():
            return None
        raw = _read_json(self.settings_path, label="Detect application settings")
        if (
            not isinstance(raw, dict)
            or raw.get("schema_version") != _SETTINGS_SCHEMA_VERSION
            or set(raw) != {"schema_version", "active_collection_id"}
        ):
            raise WorkspaceMetadataError("Detect application settings are unsupported or invalid.")
        try:
            return validate_collection_id(raw["active_collection_id"])
        except ValueError as exc:
            raise WorkspaceMetadataError("Detect application settings are invalid.") from exc

    def load_active_collection(self) -> PersistedDetectCollection | None:
        collection_id = self.active_collection_id()
        return None if collection_id is None else self.load_collection(collection_id)

    def root_decision(self, collection: PersistedDetectCollection) -> RootBindingDecision:
        observation, _ = _inspect_root(collection.source_root)
        return decide_root_binding(collection.ref.root_evidence, observation)

    def prepare_relink(
        self, collection_id: str, candidate_root: Path
    ) -> RootBindingProposal:
        current = self.load_collection(collection_id)
        observation, resolved = _inspect_root(candidate_root)
        evidence = observation.evidence
        if evidence is None:
            decision = decide_root_binding(current.ref.root_evidence, observation)
        else:
            self._validate_source_separation(resolved)
            root_decision = decide_root_binding(current.ref.root_evidence, observation)
            if root_decision is RootBindingDecision.VALID:
                decision = (
                    RootBindingDecision.VALID
                    if resolved == current.source_root
                    else RootBindingDecision.AWAITING_CONFIRMATION
                )
            else:
                decision = root_decision
        return RootBindingProposal(
            collection_id=collection_id,
            binding_revision=current.ref.binding_revision,
            previous_root=current.source_root,
            candidate_root=resolved,
            candidate_evidence=evidence,
            decision=decision,
        )

    def confirm_relink(self, proposal: RootBindingProposal) -> PersistedDetectCollection:
        if not proposal.can_confirm or proposal.candidate_evidence is None:
            raise ValueError("This relink proposal cannot be confirmed.")
        current = self.load_collection(proposal.collection_id)
        if current.ref.binding_revision != proposal.binding_revision:
            raise ValueError("The Detect Collection changed; review the relink again.")
        observation, resolved = _inspect_root(proposal.candidate_root)
        if (
            observation.evidence != proposal.candidate_evidence
            or resolved != proposal.candidate_root
        ):
            raise ValueError("The selected recordings folder changed; review the relink again.")
        ref = apply_confirmed_relink(current.ref, proposal.candidate_evidence)
        binding = DetectRootBinding(
            collection_id=ref.collection_id,
            binding_revision=ref.binding_revision,
            source_root_uri=resolved.as_uri(),
        )
        paths = self.paths_for(ref.collection_id)
        self._write_pair(
            paths,
            ref,
            binding,
            update_last_good=True,
            previous=current,
        )
        return PersistedDetectCollection(ref, binding)

    def rename_collection(
        self, collection_id: str, display_label: str
    ) -> PersistedDetectCollection:
        current = self.load_collection(collection_id)
        ref = replace(
            current.ref,
            display_label=validate_display_label(display_label),
            updated_at=datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        )
        paths = self.paths_for(collection_id)
        public_written = False
        last_good_written = False
        try:
            _write_json_atomic(paths.public_manifest, ref.to_public_dict())
            public_written = True
            _write_json_atomic(paths.last_good_manifest, ref.to_public_dict())
            last_good_written = True
        except Exception:
            if public_written:
                _write_json_atomic(paths.public_manifest, current.ref.to_public_dict())
            if last_good_written:
                _write_json_atomic(paths.last_good_manifest, current.ref.to_public_dict())
            raise
        return PersistedDetectCollection(ref, current.binding)
