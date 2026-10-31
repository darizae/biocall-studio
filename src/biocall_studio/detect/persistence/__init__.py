"""Contained, versioned, application-owned Detect Collection persistence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
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
from biocall_studio.detect.domain.inventory import (
    INVENTORY_SCHEMA_VERSION,
    InventoryRecording,
    InventorySnapshot,
)
from biocall_studio.detect.domain.models import ModelSnapshot, VerifiedModelReference

_MAX_METADATA_BYTES = 1_048_576
_SETTINGS_SCHEMA_VERSION = 1
_MAX_INVENTORY_ROWS = 100_000
_MAX_INVENTORY_PARTITIONS = 1_000
_MAX_JSONL_LINE_BYTES = 65_536
_MAX_JSONL_PARTITION_BYTES = 1_048_576
_MAX_JSONL_PARTITION_ROWS = 1_000
_INVENTORY_ID = re.compile(r"inv_[0-9a-f]{32}")
_PARTITION_NAME = re.compile(r"records-[0-9]{5}\.jsonl")
_MODEL_SNAPSHOT_ID = re.compile(r"mdl_[0-9a-f]{32}")
_MODEL_SELECTION_SCHEMA_VERSION = 1


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
    inventories_directory: Path


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
        self.model_snapshots_root = self.workspace_root / "model-snapshots"
        self.model_selection_path = self.workspace_root / "model-selection.json"
        self.refinement_model_selection_path = (
            self.workspace_root / "refinement-model-selection.json"
        )

    def _ensure_storage(self) -> None:
        self.application_data_root.mkdir(parents=True, exist_ok=True)
        if self.application_data_root.is_symlink() or not self.application_data_root.is_dir():
            raise WorkspaceMetadataError("Application data root must be a real directory.")
        for path in (
            self.application_data_root / "detect",
            self.workspace_root,
            self.collections_root,
            self.model_snapshots_root,
        ):
            _ensure_directory(path)

    def _save_model_reference(
        self, reference: VerifiedModelReference, selection_path: Path
    ) -> None:
        self._ensure_storage()
        snapshot_path = self.model_snapshots_root / f"{reference.snapshot.snapshot_id}.json"
        if snapshot_path.is_symlink():
            raise WorkspaceMetadataError("ModelSnapshot path cannot be a symlink.")
        if snapshot_path.exists():
            try:
                existing = ModelSnapshot.from_dict(
                    _read_json(snapshot_path, label="ModelSnapshot")
                )
            except ValueError as exc:
                raise WorkspaceMetadataError(f"Stored ModelSnapshot is invalid: {exc}") from exc
            if existing != reference.snapshot:
                raise WorkspaceMetadataError(
                    "Stored ModelSnapshot identifier refers to different compatibility evidence."
                )
        else:
            _write_json_atomic(snapshot_path, reference.snapshot.to_dict())
        _write_json_atomic(
            selection_path,
            {
                "schema_version": _MODEL_SELECTION_SCHEMA_VERSION,
                "model_root_uri": reference.root.as_uri(),
                "snapshot_id": reference.snapshot.snapshot_id,
            },
        )

    def save_model_reference(self, reference: VerifiedModelReference) -> None:
        """Persist the primary CNN selection and immutable path-free snapshot."""
        self._save_model_reference(reference, self.model_selection_path)

    def save_refinement_model_reference(self, reference: VerifiedModelReference) -> None:
        """Persist the independent optional RF refinement Model selection."""
        self._save_model_reference(reference, self.refinement_model_selection_path)

    def _load_model_reference(
        self, selection_path: Path, *, label: str
    ) -> VerifiedModelReference | None:
        if not selection_path.exists() and not selection_path.is_symlink():
            return None
        raw = _read_json(selection_path, label=label)
        expected = {"schema_version", "model_root_uri", "snapshot_id"}
        if (
            not isinstance(raw, dict)
            or raw.get("schema_version") != _MODEL_SELECTION_SCHEMA_VERSION
            or set(raw) != expected
            or not isinstance(raw.get("snapshot_id"), str)
            or _MODEL_SNAPSHOT_ID.fullmatch(raw["snapshot_id"]) is None
            or not isinstance(raw.get("model_root_uri"), str)
        ):
            raise WorkspaceMetadataError(f"{label} is unsupported or invalid.")
        try:
            root = path_from_file_uri(raw["model_root_uri"])
            snapshot = ModelSnapshot.from_dict(
                _read_json(
                    self.model_snapshots_root / f"{raw['snapshot_id']}.json",
                    label="ModelSnapshot",
                )
            )
        except (ValueError, WorkspaceMetadataError) as exc:
            raise WorkspaceMetadataError(f"{label} is invalid: {exc}") from exc
        if snapshot.snapshot_id != raw["snapshot_id"]:
            raise WorkspaceMetadataError(f"{label} and ModelSnapshot disagree.")
        return VerifiedModelReference(root, snapshot)

    def load_model_reference(self) -> VerifiedModelReference | None:
        return self._load_model_reference(
            self.model_selection_path, label="Detect Model selection"
        )

    def load_refinement_model_reference(self) -> VerifiedModelReference | None:
        return self._load_model_reference(
            self.refinement_model_selection_path,
            label="RF refinement Model selection",
        )

    def clear_model_reference(self) -> None:
        if self.model_selection_path.is_symlink():
            raise WorkspaceMetadataError("Detect Model selection cannot be a symlink.")
        self.model_selection_path.unlink(missing_ok=True)

    def clear_refinement_model_reference(self) -> None:
        if self.refinement_model_selection_path.is_symlink():
            raise WorkspaceMetadataError("RF refinement Model selection cannot be a symlink.")
        self.refinement_model_selection_path.unlink(missing_ok=True)

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
            inventories_directory=directory / "inventories",
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
        for namespace in ("runs", "results", "exports", "inventories"):
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

    def _inventory_directory(self, paths: CollectionPaths, inventory_id: str) -> Path:
        if not isinstance(inventory_id, str) or _INVENTORY_ID.fullmatch(inventory_id) is None:
            raise WorkspaceMetadataError("Inventory identifier is invalid.")
        return paths.inventories_directory / inventory_id

    def _publish_snapshot_directory(
        self, paths: CollectionPaths, snapshot: InventorySnapshot
    ) -> None:
        if len(snapshot.recordings) > _MAX_INVENTORY_ROWS:
            raise WorkspaceMetadataError(
                f"Inventory exceeds the {_MAX_INVENTORY_ROWS:,}-row limit."
            )
        _ensure_directory(paths.inventories_directory)
        destination = self._inventory_directory(paths, snapshot.inventory_id)
        if destination.is_symlink():
            raise WorkspaceMetadataError("Inventory directory cannot be a symlink.")
        if destination.exists():
            if self._load_inventory_id(paths, snapshot.inventory_id) != snapshot:
                raise WorkspaceMetadataError(
                    "An immutable inventory identifier already contains different data."
                )
            return

        temporary = Path(
            tempfile.mkdtemp(
                prefix=f".{snapshot.inventory_id}.",
                suffix=".tmp",
                dir=paths.inventories_directory,
            )
        )
        temporary.chmod(0o700)
        partitions: list[dict[str, object]] = []
        try:
            pending: list[bytes] = []
            pending_bytes = 0

            def flush_partition() -> None:
                nonlocal pending, pending_bytes
                if not pending:
                    return
                index = len(partitions) + 1
                if index > _MAX_INVENTORY_PARTITIONS:
                    raise WorkspaceMetadataError("Inventory has too many JSONL partitions.")
                name = f"records-{index:05d}.jsonl"
                payload = b"".join(pending)
                path = temporary / name
                with path.open("xb") as stream:
                    os.chmod(path, 0o600)
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                partitions.append(
                    {
                        "path": name,
                        "rows": len(pending),
                        "bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                )
                pending = []
                pending_bytes = 0

            for row in snapshot.recordings:
                line = (
                    json.dumps(
                        row.to_dict(),
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ).encode("utf-8")
                    + b"\n"
                )
                if len(line) > _MAX_JSONL_LINE_BYTES:
                    raise WorkspaceMetadataError("Inventory JSONL row exceeds the 64 KiB limit.")
                if pending and (
                    len(pending) >= _MAX_JSONL_PARTITION_ROWS
                    or pending_bytes + len(line) > _MAX_JSONL_PARTITION_BYTES
                ):
                    flush_partition()
                pending.append(line)
                pending_bytes += len(line)
            flush_partition()

            manifest = {
                "schema_version": snapshot.schema_version,
                "collection_id": snapshot.collection_id,
                "binding_revision": snapshot.binding_revision,
                "inventory_id": snapshot.inventory_id,
                "digest": snapshot.digest,
                "scanned_at": snapshot.scanned_at,
                "freshness_strategy": snapshot.freshness_strategy,
                "conflict_policy": snapshot.conflict_policy,
                "decision_rules": [
                    rule.to_dict() for rule in snapshot.decision_rules
                ],
                "issues": [issue.to_dict() for issue in snapshot.issues],
                "counts": snapshot.counts.to_dict(),
                "partitions": partitions,
            }
            serialized_manifest = (
                json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False).encode(
                    "utf-8"
                )
                + b"\n"
            )
            if len(serialized_manifest) > _MAX_METADATA_BYTES:
                raise WorkspaceMetadataError("Inventory manifest exceeds the 1 MiB limit.")
            _write_json_atomic(temporary / "inventory.json", manifest)
            os.rename(temporary, destination)
            destination.chmod(0o700)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def _load_inventory_id(
        self, paths: CollectionPaths, inventory_id: str
    ) -> InventorySnapshot:
        directory = self._inventory_directory(paths, inventory_id)
        if (
            paths.inventories_directory.is_symlink()
            or directory.is_symlink()
            or not directory.is_dir()
        ):
            raise WorkspaceMetadataError("Inventory snapshot is missing or unsafe.")
        manifest = _read_json(directory / "inventory.json", label="Inventory manifest")
        expected = {
            "schema_version",
            "collection_id",
            "binding_revision",
            "inventory_id",
            "digest",
            "scanned_at",
            "freshness_strategy",
            "conflict_policy",
            "decision_rules",
            "issues",
            "counts",
            "partitions",
        }
        if not isinstance(manifest, dict) or set(manifest) != expected:
            raise WorkspaceMetadataError("Inventory manifest is unsupported or invalid.")
        if manifest.get("schema_version") != INVENTORY_SCHEMA_VERSION:
            raise WorkspaceMetadataError("Inventory manifest schema is unsupported.")
        partitions = manifest["partitions"]
        if not isinstance(partitions, list) or len(partitions) > _MAX_INVENTORY_PARTITIONS:
            raise WorkspaceMetadataError("Inventory partition index is invalid.")

        recordings: list[dict[str, object]] = []
        total_rows = 0
        for expected_index, part in enumerate(partitions, 1):
            if not isinstance(part, dict) or set(part) != {
                "path",
                "rows",
                "bytes",
                "sha256",
            }:
                raise WorkspaceMetadataError("Inventory partition entry is invalid.")
            name = part["path"]
            if (
                not isinstance(name, str)
                or _PARTITION_NAME.fullmatch(name) is None
                or name != f"records-{expected_index:05d}.jsonl"
                or type(part["rows"]) is not int
                or not 0 < part["rows"] <= _MAX_JSONL_PARTITION_ROWS
                or type(part["bytes"]) is not int
                or not 0 < part["bytes"] <= _MAX_JSONL_PARTITION_BYTES
                or not isinstance(part["sha256"], str)
            ):
                raise WorkspaceMetadataError("Inventory partition entry is invalid.")
            path = directory / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size != part["bytes"]:
                raise WorkspaceMetadataError("Inventory partition is missing or changed.")
            payload = path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != part["sha256"]:
                raise WorkspaceMetadataError("Inventory partition checksum does not match.")
            lines = payload.splitlines(keepends=True)
            if len(lines) != part["rows"]:
                raise WorkspaceMetadataError("Inventory partition row count does not match.")
            for line in lines:
                if len(line) > _MAX_JSONL_LINE_BYTES or not line.endswith(b"\n"):
                    raise WorkspaceMetadataError("Inventory JSONL row is invalid.")
                try:
                    raw_row = json.loads(line)
                    InventoryRecording.from_dict(raw_row)
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                    raise WorkspaceMetadataError("Inventory JSONL row is invalid.") from exc
                recordings.append(raw_row)
            total_rows += len(lines)
            if total_rows > _MAX_INVENTORY_ROWS:
                raise WorkspaceMetadataError("Inventory exceeds the bounded row limit.")

        complete = dict(manifest)
        complete.pop("partitions")
        complete["recordings"] = recordings
        try:
            snapshot = InventorySnapshot.from_dict(complete)
        except ValueError as exc:
            raise WorkspaceMetadataError(f"Inventory snapshot is invalid: {exc}") from exc
        if snapshot.inventory_id != inventory_id:
            raise WorkspaceMetadataError("Inventory identifier does not match its directory.")
        return snapshot

    def load_inventory(
        self, collection_id: str, inventory_id: str | None = None
    ) -> InventorySnapshot:
        current = self.load_collection(collection_id)
        selected_id = inventory_id or current.ref.inventory_revision
        if selected_id is None:
            raise FileNotFoundError("This Detect Collection has no published inventory.")
        snapshot = self._load_inventory_id(self.paths_for(collection_id), selected_id)
        if snapshot.collection_id != collection_id:
            raise WorkspaceMetadataError("Inventory belongs to a different Detect Collection.")
        return snapshot

    def publish_inventory(
        self, collection_id: str, snapshot: InventorySnapshot
    ) -> PersistedDetectCollection:
        current = self.load_collection(collection_id)
        if snapshot.collection_id != collection_id:
            raise ValueError("Inventory belongs to a different Detect Collection.")
        if snapshot.binding_revision != current.ref.binding_revision:
            raise ValueError("Inventory was scanned from an outdated root binding.")
        if self.root_decision(current) is not RootBindingDecision.VALID:
            raise ValueError("The recordings folder changed before inventory publication.")
        from biocall_studio.detect.application.discovery import snapshot_is_quickly_current

        if not snapshot_is_quickly_current(current.source_root, snapshot):
            raise ValueError("Recordings changed before inventory publication; rescan them.")
        paths = self.paths_for(collection_id)
        self._publish_snapshot_directory(paths, snapshot)
        ref = replace(
            current.ref,
            updated_at=snapshot.scanned_at,
            inventory_revision=snapshot.inventory_id,
            inventory_binding_revision=snapshot.binding_revision,
        )
        self._write_pair(
            paths,
            ref,
            current.binding,
            update_last_good=True,
            previous=current,
        )
        return PersistedDetectCollection(ref, current.binding)
