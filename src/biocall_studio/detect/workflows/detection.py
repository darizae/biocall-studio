"""Scientific QProcess Worker for real CNN first-pass candidate detection."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from biocall_studio.detect.application.discovery import (
    InventoryScanCancelled,
    validate_recording_source,
)
from biocall_studio.detect.application.model_intake import recheck_model_reference
from biocall_studio.detect.application.owner_lifetime import DetectWorkerOwnerGuard
from biocall_studio.detect.domain.detection import (
    DetectionSettings,
    merge_candidate_windows,
    predict_recording_windows,
)
from biocall_studio.detect.domain.results import (
    CandidateInterval,
    DetectionResult,
    FileOutcomeStatus,
    RecordingOutcome,
    candidate_identity,
    recording_identity,
)
from biocall_studio.detect.domain.runs import canonical_digest, utc_now
from biocall_studio.detect.persistence import DetectWorkspaceStore
from biocall_studio.detect.persistence.diagnostics import (
    BoundedJsonlLog,
    encode_diagnostic_record,
    resolve_run_log_path,
)
from biocall_studio.detect.persistence.publication import (
    discard_staging,
    publish_staged_artifact,
    stage_detection_result,
)
from biocall_studio.detect.persistence.runs import DetectRunRepository


class DetectionCancelled(InterruptedError):
    pass


class FrozenInputChanged(RuntimeError):
    pass


class FrozenModelChanged(RuntimeError):
    pass


def _emit(event: str, **values: object) -> None:
    payload = {"schema_version": 1, "event": event, **values}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode()) > 4_096:
        raise ValueError("Detection Worker event exceeds 4 KiB.")
    print(encoded, flush=True)


def _log(
    sink: BoundedJsonlLog,
    event: str,
    message: str,
    *,
    level: str = "INFO",
    context: dict[str, object] | None = None,
) -> None:
    sink.write(
        encode_diagnostic_record(
            component="detect.worker",
            event=event,
            message=message,
            level=level,
            context=context,
        )
    )


def _cancelled(
    repository: DetectRunRepository,
    run_id: str,
    guard: DetectWorkerOwnerGuard,
) -> bool:
    return repository.cancellation_requested(run_id) or not guard.owner_alive()


def _check_cancelled(
    repository: DetectRunRepository,
    run_id: str,
    guard: DetectWorkerOwnerGuard,
) -> None:
    if _cancelled(repository, run_id, guard):
        raise DetectionCancelled("Detection stopped before Result publication.")


def _validate_source(
    root: Path,
    row,
    repository: DetectRunRepository,
    run_id: str,
    guard: DetectWorkerOwnerGuard,
) -> Path:
    try:
        return validate_recording_source(
            root,
            row,
            cancel=lambda: _cancelled(repository, run_id, guard),
        )
    except InventoryScanCancelled as exc:
        raise DetectionCancelled("Detection stopped during input validation.") from exc
    except (OSError, RuntimeError, ValueError) as exc:
        raise FrozenInputChanged("A frozen recording changed or became unavailable.") from exc


def _recheck_model(reference):
    try:
        return recheck_model_reference(reference)
    except (OSError, RuntimeError, ValueError) as exc:
        raise FrozenModelChanged("The frozen Model changed or became unavailable.") from exc


def _file_error_code(exc: Exception) -> str:
    message = str(exc).casefold()
    if any(
        fragment in message
        for fragment in ("audio file", "nonempty mono", "unable to read", "sound file")
    ):
        return "audio_decode_failed"
    if any(fragment in message for fragment in ("output", "logits", "probabilities")):
        return "unsupported_output"
    return "inference_failed"


def run_detection(
    request_path: Path,
    owner_lease: Path,
    *,
    step_delay_seconds: float,
    owner_guard: DetectWorkerOwnerGuard | None = None,
) -> int:
    if not 0 <= step_delay_seconds <= 5:
        raise ValueError("Detection Worker delay is outside its bounded range.")
    repository = DetectRunRepository.from_request_path(request_path)
    request = repository.load_request(request_path.parent.name)
    guard = owner_guard or DetectWorkerOwnerGuard(owner_lease)
    if owner_guard is None:
        guard.start_watchdog()
    log = BoundedJsonlLog(
        resolve_run_log_path(repository.collection_root, request.run_id, "worker", create=True)
    )
    context = {
        "run_id": request.run_id,
        "request_id": request.request_id,
        "launch_id": request.launch_id,
    }
    try:
        if not guard.owner_alive():
            return 70
        _emit("started")
        _log(log, "worker_started", "CNN first-pass Detection Worker started", context=context)
        settings = DetectionSettings.from_mapping(dict(request.settings))
        if step_delay_seconds:
            time.sleep(step_delay_seconds)
        _check_cancelled(repository, request.run_id, guard)

        store = DetectWorkspaceStore(repository.application_data_root)
        try:
            collection = store.load_collection(request.collection_id)
            snapshot = store.load_inventory(request.collection_id, request.inventory_id)
        except (OSError, RuntimeError, ValueError) as exc:
            raise FrozenInputChanged("Frozen Detect inputs cannot be reopened.") from exc
        if (
            collection.ref.binding_revision != request.binding_revision
            or snapshot.binding_revision != request.binding_revision
            or snapshot.inventory_id != request.inventory_id
            or snapshot.digest != request.inventory_digest
            or snapshot.included_keys != request.selected_recording_keys
        ):
            raise FrozenInputChanged("Frozen inventory identity no longer matches the Run.")
        reference = store.load_model_reference()
        if reference is None:
            raise FrozenModelChanged("The selected Model is unavailable.")
        if (
            reference.snapshot.snapshot_id != request.model_snapshot_id
            or canonical_digest(reference.snapshot.to_dict()) != request.model_digest
        ):
            raise FrozenModelChanged("The selected ModelSnapshot no longer matches the Run.")
        reference = _recheck_model(reference)
        row_by_key = {row.recording_key: row for row in snapshot.recordings}
        rows = tuple(row_by_key[key] for key in request.selected_recording_keys)

        # Validate every frozen source before decoding any audio. A stale input is a
        # Run-level failure, never a per-file zero-candidate outcome.
        for row in rows:
            _check_cancelled(repository, request.run_id, guard)
            _validate_source(
                collection.source_root, row, repository, request.run_id, guard
            )
        _emit(
            "progress",
            progress=10,
            stage_index=0,
            message="Frozen inputs validated",
        )

        scientific_identity = canonical_digest(
            {
                "model_snapshot_id": reference.snapshot.snapshot_id,
                "settings": settings.to_mapping(),
            }
        )
        outcomes: list[RecordingOutcome] = []
        for index, row in enumerate(rows):
            _check_cancelled(repository, request.run_id, guard)
            if step_delay_seconds:
                time.sleep(step_delay_seconds)
            path = _validate_source(
                collection.source_root, row, repository, request.run_id, guard
            )
            wav = row.wav
            if wav is None or row.content_sha256 is None:
                raise FrozenInputChanged("Frozen inventory row lacks verified WAV facts.")
            recording_ref = recording_identity(
                snapshot.inventory_id, row.recording_key, row.content_sha256
            )
            try:
                windows = predict_recording_windows(reference, path, settings)
                merged = merge_candidate_windows(
                    windows,
                    settings=settings,
                    model_sample_rate_hz=reference.snapshot.sample_rate_hz,
                    source_sample_rate_hz=wav.sample_rate_hz,
                    source_frame_count=wav.frame_count,
                )
                candidates = tuple(
                    CandidateInterval.create(
                        candidate_id=candidate_identity(
                            recording_ref, start, end, scientific_identity
                        ),
                        recording_ref=recording_ref,
                        start_frame=start,
                        end_frame=end,
                        sample_rate_hz=wav.sample_rate_hz,
                        max_target_score=score,
                        contributing_windows=window_count,
                    )
                    for start, end, score, window_count in merged
                )
            except (OSError, RuntimeError, ValueError) as exc:
                outcomes.append(
                    RecordingOutcome.failed(
                        recording_ref=recording_ref,
                        recording_key=row.recording_key,
                        source_sha256=row.content_sha256,
                        sample_rate_hz=wav.sample_rate_hz,
                        frame_count=wav.frame_count,
                        channels=wav.channels,
                        error_code=_file_error_code(exc),
                    )
                )
            else:
                outcomes.append(
                    RecordingOutcome.succeeded(
                        recording_ref=recording_ref,
                        recording_key=row.recording_key,
                        source_sha256=row.content_sha256,
                        sample_rate_hz=wav.sample_rate_hz,
                        frame_count=wav.frame_count,
                        channels=wav.channels,
                        candidates=candidates,
                    )
                )
            # Detect replacement during decode/inference before accepting this outcome.
            _validate_source(
                collection.source_root, row, repository, request.run_id, guard
            )
            progress = 10 + round(((index + 1) / len(rows)) * 78)
            _emit(
                "progress",
                progress=min(progress, 88),
                stage_index=1,
                message="Analyzing recordings",
            )

        reference = _recheck_model(reference)
        if not any(item.status is FileOutcomeStatus.SUCCEEDED for item in outcomes):
            _emit("error", error_code="no_successful_files")
            return 7
        snapshot_model = reference.snapshot
        if snapshot_model.window_length_samples is None:
            raise FrozenModelChanged("CNN Model window metadata is unavailable.")
        result = DetectionResult.create(
            result_id=request.artifact_id,
            run_id=request.run_id,
            request_id=request.request_id,
            collection_id=request.collection_id,
            binding_revision=request.binding_revision,
            inventory_id=request.inventory_id,
            inventory_digest=request.inventory_digest,
            model_id=snapshot_model.model_id,
            model_snapshot_id=snapshot_model.snapshot_id,
            model_manifest_sha256=snapshot_model.manifest_sha256,
            model_artifact_sha256=snapshot_model.artifact_sha256,
            model_snapshot_digest=request.model_digest,
            settings=settings,
            window_length_samples=snapshot_model.window_length_samples,
            hop_samples=settings.hop_samples(snapshot_model.window_length_samples),
            model_sample_rate_hz=snapshot_model.sample_rate_hz,
            backend_distribution=snapshot_model.loader_distribution,
            backend_version=snapshot_model.loader_version,
            backend_revision=snapshot_model.source_revision,
            completed_at=utc_now(),
            recordings=tuple(outcomes),
        )
        _check_cancelled(repository, request.run_id, guard)
        receipt_path = repository.run_directory(request.run_id) / "receipt.json"
        if receipt_path.exists() or receipt_path.is_symlink():
            raise FileExistsError("Run receipt publication target already exists.")
        stage = repository.staging_path(request.launch_id)
        stage_detection_result(repository.collection_root, stage, request, result)
        _emit(
            "progress",
            progress=96,
            stage_index=2,
            message="Verifying immutable Result",
        )
        _check_cancelled(repository, request.run_id, guard)
        identity = publish_staged_artifact(repository.collection_root, stage, request)
        repository.write_receipt(identity.receipt())
        _log(
            log,
            "worker_completed",
            "CNN first-pass Result publication completed",
            context={**context, "status": "completed", "count": result.candidate_count},
        )
        _emit("completed")
        return 0
    except DetectionCancelled:
        discard_staging(repository.collection_root, request.launch_id)
        _log(
            log,
            "worker_cancelled",
            "CNN first-pass Detection Worker cancelled before publication",
            level="WARNING",
            context=context,
        )
        _emit("cancelled")
        return 2
    except FrozenInputChanged:
        discard_staging(repository.collection_root, request.launch_id)
        _log(
            log,
            "input_changed",
            "Frozen recording input validation failed",
            level="ERROR",
            context=context,
        )
        _emit("error", error_code="input_changed")
        return 5
    except FrozenModelChanged:
        discard_staging(repository.collection_root, request.launch_id)
        _log(
            log,
            "model_changed",
            "Frozen Model validation failed",
            level="ERROR",
            context=context,
        )
        _emit("error", error_code="model_changed")
        return 6
    except Exception:
        try:
            discard_staging(repository.collection_root, request.launch_id)
        except Exception:
            pass
        _log(
            log,
            "publication_failed",
            "CNN first-pass Result could not be published safely",
            level="ERROR",
            context=context,
        )
        _emit("error", error_code="publication_failed")
        return 4
    finally:
        guard.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--owner-lease", required=True, type=Path)
    parser.add_argument("--step-delay", required=True, type=float)
    args = parser.parse_args(argv)
    return run_detection(
        args.request,
        args.owner_lease,
        step_delay_seconds=args.step_delay,
    )


if __name__ == "__main__":
    raise SystemExit(main())
