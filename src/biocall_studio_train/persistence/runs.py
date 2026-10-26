"""Atomic persisted Run State, Worker receipts, and restart reconciliation."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from biocall_studio_train.domain.paths import validate_relative_path
from biocall_studio_train.domain.run import RunState, RunStatus, reconcile_run
from biocall_studio_train.persistence.datasets import load_dataset
from biocall_studio_train.persistence.models import discard_uncommitted_model, load_model

MAX_RUN_JSON_BYTES = 1_000_000
WORKER_RESULT_SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _fsync_directory(directory: Path) -> None:
    try:
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        pass


def _alpaca_root(collection_root: Path) -> Path:
    collection = collection_root.resolve(strict=True)
    alpaca = collection / ".alpaca"
    if alpaca.is_symlink() or not alpaca.is_dir():
        raise ValueError("Validated Collection metadata folder is missing or unsafe.")
    if not alpaca.resolve(strict=True).is_relative_to(collection):
        raise ValueError("Run storage escapes the selected Collection.")
    return alpaca


def _runs_root(collection_root: Path, *, create: bool) -> Path:
    root = _alpaca_root(collection_root) / "runs"
    if root.is_symlink():
        raise ValueError("Run storage cannot use symlinks.")
    if create:
        root.mkdir(exist_ok=True)
    if root.exists() and (
        not root.is_dir()
        or not root.resolve(strict=True).is_relative_to(_alpaca_root(collection_root))
    ):
        raise ValueError("Run storage must be a contained directory.")
    return root


def _portable_segment(value: str, label: str) -> str:
    safe = validate_relative_path(value)
    if "/" in safe:
        raise ValueError(f"{label} must be one portable path segment.")
    return safe


def _run_directory(collection_root: Path, run_id: str, *, require: bool) -> Path:
    candidate = _runs_root(collection_root, create=not require) / _portable_segment(
        run_id, "Run ID"
    )
    if candidate.is_symlink():
        raise ValueError("Run directory cannot be a symlink.")
    if require and not candidate.is_dir():
        raise FileNotFoundError(f"Run does not exist: {run_id}")
    if candidate.exists() and not candidate.resolve(strict=True).is_relative_to(
        _runs_root(collection_root, create=False).resolve(strict=True)
    ):
        raise ValueError("Run directory escapes Run storage.")
    return candidate


def _write_json_atomic(path: Path, payload: dict, *, replace_existing: bool) -> None:
    if path.exists() and not replace_existing:
        raise FileExistsError(f"Run file already exists: {path.name}")
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(encoded) > MAX_RUN_JSON_BYTES:
        raise ValueError("Run JSON exceeds 1 MiB.")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        if not replace_existing and path.exists():
            raise FileExistsError(f"Run file already exists: {path.name}")
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json(path: Path) -> object:
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError(f"Run file is missing or unsafe: {path.name}")
    if path.stat().st_size > MAX_RUN_JSON_BYTES:
        raise ValueError(f"Run file exceeds 1 MiB: {path.name}")
    try:
        with path.open(encoding="utf-8") as stream:
            return json.load(stream)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Run file is invalid JSON: {path.name}") from exc


def create_run(collection_root: Path, state: RunState) -> Path:
    runs = _runs_root(collection_root, create=True)
    directory = runs / _portable_segment(state.run_id, "Run ID")
    directory.mkdir()
    try:
        _write_json_atomic(directory / "run_state.json", state.to_dict(), replace_existing=False)
    except Exception:
        directory.rmdir()
        raise
    _fsync_directory(runs)
    return directory


def save_run(collection_root: Path, state: RunState) -> None:
    directory = _run_directory(collection_root, state.run_id, require=True)
    _write_json_atomic(directory / "run_state.json", state.to_dict(), replace_existing=True)


def load_run(collection_root: Path, run_id: str) -> RunState:
    directory = _run_directory(collection_root, run_id, require=True)
    return RunState.from_dict(_read_json(directory / "run_state.json"))


def list_runs(collection_root: Path) -> tuple[RunState, ...]:
    root = _runs_root(collection_root, create=False)
    if not root.exists():
        return ()
    states = [
        load_run(collection_root, path.name)
        for path in root.iterdir()
        if path.is_dir() and not path.is_symlink()
    ]
    states.sort(key=lambda state: (state.created_at, state.run_id), reverse=True)
    return tuple(states)


def delete_run(collection_root: Path, run_id: str) -> None:
    """Delete one terminal Run record without deleting its published output."""
    state = load_run(collection_root, run_id)
    if state.active:
        raise ValueError("An Active Run cannot be deleted.")
    directory = _run_directory(collection_root, run_id, require=True)
    parent = directory.parent
    shutil.rmtree(directory)
    _fsync_directory(parent)


def write_run_request(collection_root: Path, run_id: str, payload: dict) -> Path:
    directory = _run_directory(collection_root, run_id, require=True)
    path = directory / "request.json"
    _write_json_atomic(path, payload, replace_existing=False)
    return path


def cancellation_path(collection_root: Path, run_id: str) -> Path:
    return _run_directory(collection_root, run_id, require=True) / "cancel.requested"


def request_cancellation(collection_root: Path, run_id: str) -> None:
    path = cancellation_path(collection_root, run_id)
    try:
        with path.open("x", encoding="ascii") as stream:
            stream.write("cancel\n")
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        return
    _fsync_directory(path.parent)


def cancellation_requested(request_path: Path) -> bool:
    return request_path.resolve(strict=True).parent.joinpath("cancel.requested").exists()


def write_completion_receipt(request_path: Path, payload: dict) -> Path:
    request = request_path.resolve(strict=True)
    if request.name != "request.json" or request.parent.is_symlink():
        raise ValueError("Worker request path is not a contained Run request.")
    path = request.parent / "result.json"
    _write_json_atomic(path, payload, replace_existing=False)
    return path


def completion_receipt_payload(state: RunState) -> dict:
    return {
        "schema_version": WORKER_RESULT_SCHEMA_VERSION,
        "run_id": state.run_id,
        "request_id": state.request_id,
        "output_kind": state.output_kind,
        "output_id": state.output_id,
    }


def load_completion_receipt(collection_root: Path, state: RunState) -> dict:
    directory = _run_directory(collection_root, state.run_id, require=True)
    raw = _read_json(directory / "result.json")
    expected = completion_receipt_payload(state)
    if raw != expected:
        raise ValueError("Worker completion receipt does not match its Run reservation.")
    return raw


def _valid_output(collection_root: Path, state: RunState) -> tuple[bool, bool]:
    """Return structural validity and matching durable Run provenance."""
    try:
        if state.output_kind == "dataset":
            artifact = load_dataset(collection_root, state.output_id)
            provenance = artifact.manifest.get("run")
            return True, provenance == {
                "run_id": state.run_id,
                "request_id": state.request_id,
            }
        if state.output_kind == "model":
            artifact = load_model(collection_root, state.output_id)
            return True, (
                artifact.manifest.get("run_id") == state.run_id
                and artifact.manifest.get("request_id") == state.request_id
            )
    except (OSError, ValueError):
        return False, False
    return False, False


def _cleanup_staging(collection_root: Path, state: RunState) -> None:
    staging = _alpaca_root(collection_root) / ".staging"
    if not staging.exists() or staging.is_symlink() or not staging.is_dir():
        return
    prefix = f"{_portable_segment(state.output_id, 'output ID')}-"
    for path in staging.iterdir():
        if not path.name.startswith(prefix):
            continue
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir() and path.resolve(strict=True).is_relative_to(
            staging.resolve(strict=True)
        ):
            shutil.rmtree(path)
    _fsync_directory(staging)


def reconcile_runs(collection_root: Path) -> tuple[RunState, ...]:
    reconciled: list[RunState] = []
    for state in list_runs(collection_root):
        try:
            load_completion_receipt(collection_root, state)
        except (FileNotFoundError, OSError, ValueError):
            receipt = False
        else:
            receipt = True
        output_valid, durable_publication = _valid_output(collection_root, state)
        completion_evidence = receipt or durable_publication
        if (
            state.output_kind == "model"
            and output_valid
            and (
                not completion_evidence
                or (state.terminal and state.status is not RunStatus.COMPLETED)
            )
        ):
            discard_uncommitted_model(
                collection_root,
                state.output_id,
                run_id=state.run_id,
                request_id=state.request_id,
            )
            output_valid = False
        updated = reconcile_run(
            state,
            now=utc_now(),
            completion_receipt=completion_evidence,
            published_output_valid=output_valid,
        )
        if updated != state:
            save_run(collection_root, updated)
        if updated.status in {
            RunStatus.CANCELLED,
            RunStatus.FAILED,
            RunStatus.INTERRUPTED,
        }:
            _cleanup_staging(collection_root, updated)
        reconciled.append(updated)
    reconciled.sort(key=lambda state: (state.created_at, state.run_id), reverse=True)
    return tuple(reconciled)
