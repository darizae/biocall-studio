"""Atomic app-owned Detect Run records, reservations, receipts, and restart recovery."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from biocall_studio.detect.domain import detect_workspace_path, validate_collection_id
from biocall_studio.detect.domain.results import DetectionResult
from biocall_studio.detect.domain.rf_refinement import DerivedResult, ResultArtifact
from biocall_studio.detect.domain.runs import (
    DetectRunRecord,
    DetectRunRequest,
    PublicationReceipt,
    RunConflictError,
    assert_run_start_allowed,
    new_run_record,
    recover_run,
    utc_now,
)
from biocall_studio.detect.persistence.publication import (
    discard_staging,
    load_derived_result,
    load_detection_result,
    load_result_artifact,
    publication_matches_request,
)

MAX_RUN_DOCUMENT_BYTES = 1_048_576
MAX_RUNS = 10_000
_RUN_ID = re.compile(r"drun_[0-9a-f]{32}")
_LAUNCH_ID = re.compile(r"launch_[0-9a-f]{32}")
_ARTIFACT_ID = re.compile(r"pub_[0-9a-f]{32}")


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        pass


def _ensure_directory(path: Path) -> None:
    if path.is_symlink():
        raise ValueError(f"Detect Run storage cannot use a symlink: {path.name}")
    if path.exists():
        if not path.is_dir():
            raise ValueError(f"Detect Run storage must be a directory: {path.name}")
    else:
        path.mkdir(mode=0o700)


def _write_json_atomic(path: Path, payload: dict[str, object], *, replace: bool) -> None:
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(encoded) > MAX_RUN_DOCUMENT_BYTES:
        raise ValueError("Detect Run document exceeds 1 MiB.")
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("Detect Run document path is unsafe.")
    if path.exists() and not replace:
        raise FileExistsError(f"Detect Run document already exists: {path.name}")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            os.chmod(temporary, 0o600)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists() and not replace:
            raise FileExistsError(f"Detect Run document already exists: {path.name}")
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _write_json_exclusive(path: Path, payload: dict[str, object]) -> None:
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _read_json(path: Path, *, label: str) -> object:
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError(f"{label} is missing or unsafe.")
    if path.stat().st_size > MAX_RUN_DOCUMENT_BYTES:
        raise ValueError(f"{label} exceeds 1 MiB.")
    try:
        return json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is corrupt.") from exc


class DetectRunRepository:
    """Persistence boundary for one Detect Collection's independent Run history."""

    def __init__(self, application_data_root: Path, collection_id: str):
        self.application_data_root = Path(application_data_root).expanduser().resolve(strict=True)
        if self.application_data_root.is_symlink():
            raise ValueError("Application data root cannot be a symlink.")
        self.collection_id = validate_collection_id(collection_id)
        self.workspace_root = detect_workspace_path(self.application_data_root)
        self.collections_root = self.workspace_root / "collections"
        self.collection_root = self.collections_root / self.collection_id
        if (
            self.collections_root.is_symlink()
            or self.collection_root.is_symlink()
            or not self.collection_root.is_dir()
            or not self.collection_root.resolve(strict=True).is_relative_to(
                self.collections_root.resolve(strict=True)
            )
        ):
            raise ValueError("Detect Collection Run storage is missing or unsafe.")
        self.runs_root = self.collection_root / "runs"
        self.results_root = self.collection_root / "results"
        self.publications_root = self.collection_root / "publications"
        self.staging_root = self.collection_root / ".staging"
        self.active_path = self.collection_root / "active-run.json"
        for path in (
            self.runs_root,
            self.results_root,
            self.publications_root,
            self.staging_root,
        ):
            _ensure_directory(path)

    @classmethod
    def from_request_path(cls, request_path: Path) -> DetectRunRepository:
        path = Path(request_path)
        if path.name != "request.json" or len(path.parents) < 7:
            raise ValueError("Detect Worker request path is invalid.")
        if path.parent.parent.name != "runs":
            raise ValueError("Detect Worker request is outside Run storage.")
        repository = cls(path.parents[6], path.parents[2].name)
        expected = repository.run_directory(path.parent.name) / "request.json"
        if path.resolve(strict=True) != expected.resolve(strict=True):
            raise ValueError("Detect Worker request path is not contained.")
        return repository

    def run_directory(self, run_id: str) -> Path:
        if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
            raise ValueError("Detect Run ID is invalid.")
        path = self.runs_root / run_id
        if path.is_symlink():
            raise ValueError("Detect Run directory cannot be a symlink.")
        if path.exists() and (
            not path.is_dir()
            or not path.resolve(strict=True).is_relative_to(self.runs_root.resolve(strict=True))
        ):
            raise ValueError("Detect Run directory is unsafe.")
        return path

    def request_path(self, run_id: str) -> Path:
        return self.run_directory(run_id) / "request.json"

    def cancellation_path(self, run_id: str) -> Path:
        return self.run_directory(run_id) / "cancel.requested"

    def staging_path(self, launch_id: str) -> Path:
        if not isinstance(launch_id, str) or _LAUNCH_ID.fullmatch(launch_id) is None:
            raise ValueError("Detect launch ID is invalid.")
        return self.staging_root / launch_id

    def publication_path(self, artifact_id: str) -> Path:
        if not isinstance(artifact_id, str) or _ARTIFACT_ID.fullmatch(artifact_id) is None:
            raise ValueError("Detect publication ID is invalid.")
        return self.publications_root / artifact_id

    def result_path(self, artifact_id: str) -> Path:
        if not isinstance(artifact_id, str) or _ARTIFACT_ID.fullmatch(artifact_id) is None:
            raise ValueError("Detection Result ID is invalid.")
        return self.results_root / artifact_id

    def staging_directories(self) -> tuple[Path, ...]:
        return tuple(
            sorted(
                (
                    path
                    for path in self.staging_root.iterdir()
                    if path.is_dir() and not path.is_symlink()
                ),
                key=lambda item: item.name,
            )
        )

    def create(
        self,
        request: DetectRunRequest,
        *,
        title: str,
        stages: tuple[str, ...] = (
            "Validate frozen inputs",
            "Exercise Worker lifecycle",
            "Verify immutable publication",
        ),
    ) -> DetectRunRecord:
        if request.collection_id != self.collection_id:
            raise ValueError("Detect Run request belongs to a different Collection.")
        records = self.list_records()
        assert_run_start_allowed(records, request)
        directory = self.run_directory(request.run_id)
        if directory.exists():
            raise FileExistsError("Detect Run already exists.")
        reservation = {
            "schema_version": 1,
            "run_id": request.run_id,
            "request_id": request.request_id,
            "launch_id": request.launch_id,
            "reservation_owner_id": request.reservation_owner_id,
        }
        try:
            _write_json_exclusive(self.active_path, reservation)
        except FileExistsError as exc:
            raise RunConflictError("Only one Active Detect Run is allowed.") from exc
        try:
            directory.mkdir(mode=0o700)
            _write_json_atomic(
                directory / "request.json", request.to_dict(), replace=False
            )
            record = new_run_record(
                request,
                title=title,
                stages=stages,
                now=request.created_at,
            )
            _write_json_atomic(
                directory / "run.json", record.to_dict(), replace=False
            )
        except Exception:
            if directory.exists() and not directory.is_symlink():
                shutil.rmtree(directory)
            self.active_path.unlink(missing_ok=True)
            raise
        return record

    def load_request(self, run_id: str) -> DetectRunRequest:
        return DetectRunRequest.from_dict(
            _read_json(self.request_path(run_id), label="DetectRunRequest")
        )

    def load_record(self, run_id: str) -> DetectRunRecord:
        return DetectRunRecord.from_dict(
            _read_json(self.run_directory(run_id) / "run.json", label="DetectRunRecord")
        )

    def list_records(self) -> tuple[DetectRunRecord, ...]:
        paths = [
            path
            for path in self.runs_root.iterdir()
            if path.is_dir() and not path.is_symlink() and _RUN_ID.fullmatch(path.name)
        ]
        if len(paths) > MAX_RUNS:
            raise ValueError("Detect Run history exceeds its bounded size.")
        records = [self.load_record(path.name) for path in paths]
        records.sort(key=lambda item: (item.created_at, item.run_id), reverse=True)
        return tuple(records)

    def save_record(self, record: DetectRunRecord) -> None:
        request = self.load_request(record.run_id)
        if (
            request.request_id != record.request_id
            or request.launch_id != record.launch_id
            or request.reservation_owner_id != record.reservation_owner_id
            or request.collection_id != record.collection_id
            or request.inventory_id != record.inventory_id
            or request.model_snapshot_id != record.model_snapshot_id
            or request.artifact_id != record.artifact_id
        ):
            raise ValueError("Detect Run record does not match its immutable request.")
        _write_json_atomic(
            self.run_directory(record.run_id) / "run.json",
            record.to_dict(),
            replace=True,
        )
        if record.terminal:
            self._release_reservation(record)

    def _release_reservation(self, record: DetectRunRecord) -> None:
        if not self.active_path.exists() and not self.active_path.is_symlink():
            return
        try:
            raw = _read_json(self.active_path, label="Active Detect Run reservation")
        except (FileNotFoundError, ValueError):
            return
        if isinstance(raw, dict) and raw.get("run_id") == record.run_id:
            self.active_path.unlink(missing_ok=True)
            _fsync_directory(self.collection_root)

    def request_cancellation(self, run_id: str) -> None:
        path = self.cancellation_path(run_id)
        if path.is_symlink():
            raise ValueError("Detect cancellation marker is unsafe.")
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return
        try:
            os.write(descriptor, b"cancel\n")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def cancellation_requested(self, run_id: str) -> bool:
        path = self.cancellation_path(run_id)
        return path.is_file() and not path.is_symlink()

    def write_receipt(self, receipt: PublicationReceipt) -> Path:
        path = self.run_directory(receipt.run_id) / "receipt.json"
        if path.exists():
            existing = PublicationReceipt.from_dict(
                _read_json(path, label="PublicationReceipt")
            )
            if existing != receipt:
                raise FileExistsError("A different PublicationReceipt already exists.")
            return path
        _write_json_atomic(path, receipt.to_dict(), replace=False)
        return path

    def _receipt_document(self, record: DetectRunRecord) -> PublicationReceipt:
        receipt = PublicationReceipt.from_dict(
            _read_json(
                self.run_directory(record.run_id) / "receipt.json",
                label="PublicationReceipt",
            )
        )
        if (
            receipt.run_id != record.run_id
            or receipt.request_id != record.request_id
            or receipt.launch_id != record.launch_id
            or receipt.artifact_id != record.artifact_id
        ):
            raise ValueError("PublicationReceipt does not match its Detect Run.")
        return receipt

    def verified_receipt(
        self,
        record: DetectRunRecord,
        *,
        recover_missing: bool = False,
    ) -> PublicationReceipt | None:
        receipt_path = self.run_directory(record.run_id) / "receipt.json"
        request = self.load_request(record.run_id)
        try:
            receipt = self._receipt_document(record)
        except FileNotFoundError:
            if not recover_missing:
                return None
            identity = publication_matches_request(self.collection_root, request)
            if identity is None:
                return None
            receipt = identity.receipt()
            self.write_receipt(receipt)
        except (OSError, ValueError):
            return None
        identity = publication_matches_request(self.collection_root, request)
        if identity is None or receipt.artifact_digest != identity.artifact_digest:
            return None
        if not receipt_path.exists():
            return None
        return receipt

    def load_receipt(self, record: DetectRunRecord) -> PublicationReceipt:
        receipt = self.verified_receipt(record)
        if receipt is None:
            raise ValueError("Detect Run publication receipt or artifact is invalid.")
        return receipt

    def load_detection_result(self, record: DetectRunRecord) -> DetectionResult:
        """Independently reopen the completed receipt and metadata-only Result."""
        receipt = self.load_receipt(record)
        if receipt.artifact_kind != "detection_result":
            raise ValueError("The completed Run did not publish a Detection Result.")
        result = load_detection_result(self.collection_root, receipt.artifact_id)
        request = self.load_request(record.run_id)
        if (
            result.run_id != request.run_id
            or result.request_id != request.request_id
            or result.collection_id != request.collection_id
            or result.binding_revision != request.binding_revision
            or result.inventory_id != request.inventory_id
            or result.inventory_digest != request.inventory_digest
            or result.model_snapshot_id != request.model_snapshot_id
            or result.model_snapshot_digest != request.model_digest
        ):
            raise ValueError("Detection Result does not match its immutable Run request.")
        return result

    def load_derived_result(self, record: DetectRunRecord) -> DerivedResult:
        """Independently reopen a child Result and its checksum-valid parent lineage."""
        receipt = self.load_receipt(record)
        if receipt.artifact_kind != "derived_result":
            raise ValueError("The completed Run did not publish a Derived Result.")
        result = load_derived_result(self.collection_root, receipt.artifact_id)
        request = self.load_request(record.run_id)
        if (
            result.run_id != request.run_id
            or result.request_id != request.request_id
            or result.collection_id != request.collection_id
            or result.binding_revision != request.binding_revision
            or result.inventory_id != request.inventory_id
            or result.inventory_digest != request.inventory_digest
            or result.rf_model_snapshot_id != request.model_snapshot_id
            or result.rf_model_snapshot_digest != request.model_digest
            or dict(request.settings)
            != {
                "parent_result_digest": result.parent_result_digest,
                "parent_result_id": result.parent_result_id,
                "run_kind": "rf_refinement",
            }
        ):
            raise ValueError("Derived Result does not match its immutable Run request.")
        return result

    def load_result(self, record: DetectRunRecord) -> ResultArtifact:
        receipt = self.load_receipt(record)
        result = load_result_artifact(self.collection_root, receipt.artifact_id)
        if result.run_id != record.run_id:
            raise ValueError("Scientific Result does not match its completed Run.")
        return result

    def cleanup_staging(self, record: DetectRunRecord) -> None:
        discard_staging(self.collection_root, record.launch_id)

    def reconcile(self) -> tuple[DetectRunRecord, ...]:
        reconciled: list[DetectRunRecord] = []
        for record in self.list_records():
            receipt = self.verified_receipt(record, recover_missing=record.active)
            publication_valid = receipt is not None
            updated = recover_run(
                record,
                receipt=receipt,
                publication_valid=publication_valid,
                now=utc_now(),
            )
            if updated != record:
                self.save_record(updated)
            if updated.terminal and not publication_valid:
                self.cleanup_staging(updated)
            reconciled.append(updated)
        active = [record for record in reconciled if record.active]
        if len(active) > 1:
            raise RunConflictError("Persisted Detect Run history has multiple Active Runs.")
        if not active and self.active_path.exists() and not self.active_path.is_symlink():
            self.active_path.unlink()
            _fsync_directory(self.collection_root)
        reconciled.sort(key=lambda item: (item.created_at, item.run_id), reverse=True)
        return tuple(reconciled)
