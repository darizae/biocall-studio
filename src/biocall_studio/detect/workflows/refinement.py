"""Scientific QProcess Worker for optional RF assessment of CNN candidates."""

from __future__ import annotations

import argparse
import json
import time
from importlib.metadata import version
from pathlib import Path

import joblib
from sklearn.ensemble import RandomForestClassifier

from biocall_studio.detect.application.discovery import (
    InventoryScanCancelled,
    validate_recording_source,
)
from biocall_studio.detect.application.model_intake import recheck_model_reference
from biocall_studio.detect.application.owner_lifetime import DetectWorkerOwnerGuard
from biocall_studio.detect.domain.rf_refinement import (
    DerivedResult,
    RefinementDecision,
    RfFeatureSchemaError,
    RfNonFiniteFeatureError,
    RfSourceMismatchError,
    extract_candidate_features,
    ordered_feature_vector,
    target_probability_score,
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
    load_detection_result,
    publish_staged_artifact,
    stage_derived_result,
)
from biocall_studio.detect.persistence.runs import DetectRunRepository
from biocall_studio.train.persistence.models import structurally_reload_rf_directory


class RefinementCancelled(InterruptedError):
    pass


class FrozenInputChanged(RuntimeError):
    pass


class FrozenModelChanged(RuntimeError):
    pass


class ParentResultChanged(RuntimeError):
    pass


def _emit(event: str, **values: object) -> None:
    payload = {"schema_version": 1, "event": event, **values}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode()) > 4_096:
        raise ValueError("RF refinement Worker event exceeds 4 KiB.")
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
            component="detect.rf_worker",
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
        raise RefinementCancelled("RF refinement stopped before child Result publication.")


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
        raise RefinementCancelled("RF refinement stopped during input validation.") from exc
    except (OSError, RuntimeError, ValueError) as exc:
        raise FrozenInputChanged("A parent recording changed or became unavailable.") from exc


def _recheck_model(reference):
    try:
        return recheck_model_reference(reference)
    except (OSError, RuntimeError, ValueError) as exc:
        raise FrozenModelChanged("The frozen RF Model changed or became unavailable.") from exc


def run_refinement(
    request_path: Path,
    owner_lease: Path,
    *,
    step_delay_seconds: float,
    owner_guard: DetectWorkerOwnerGuard | None = None,
) -> int:
    if not 0 <= step_delay_seconds <= 5:
        raise ValueError("RF refinement Worker delay is outside its bounded range.")
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
        _log(log, "worker_started", "RF candidate refinement Worker started", context=context)
        settings = dict(request.settings)
        if (
            set(settings) != {"run_kind", "parent_result_id", "parent_result_digest"}
            or settings["run_kind"] != "rf_refinement"
        ):
            raise ParentResultChanged("RF refinement request contract is invalid.")
        if step_delay_seconds:
            time.sleep(step_delay_seconds)
        _check_cancelled(repository, request.run_id, guard)

        try:
            parent = load_detection_result(
                repository.collection_root, str(settings["parent_result_id"])
            )
        except (OSError, RuntimeError, ValueError) as exc:
            raise ParentResultChanged("The immutable parent Result cannot be reopened.") from exc
        if (
            parent.result_digest != settings["parent_result_digest"]
            or parent.collection_id != request.collection_id
            or parent.binding_revision != request.binding_revision
            or parent.inventory_id != request.inventory_id
            or parent.inventory_digest != request.inventory_digest
        ):
            raise ParentResultChanged("The parent Result lineage no longer matches the Run.")

        store = DetectWorkspaceStore(repository.application_data_root)
        try:
            collection = store.load_collection(request.collection_id)
            snapshot = store.load_inventory(request.collection_id, request.inventory_id)
        except (OSError, RuntimeError, ValueError) as exc:
            raise FrozenInputChanged("Frozen Detect inputs cannot be reopened.") from exc
        candidate_keys = tuple(
            sorted(
                recording.recording_key for recording in parent.recordings if recording.candidates
            )
        )
        if (
            collection.ref.binding_revision != request.binding_revision
            or snapshot.binding_revision != request.binding_revision
            or snapshot.inventory_id != request.inventory_id
            or snapshot.digest != request.inventory_digest
            or request.selected_recording_keys != candidate_keys
        ):
            raise FrozenInputChanged("Frozen parent recording inventory no longer matches.")
        row_by_key = {row.recording_key: row for row in snapshot.recordings}
        parent_by_key = {row.recording_key: row for row in parent.recordings}
        for key in candidate_keys:
            _check_cancelled(repository, request.run_id, guard)
            row = row_by_key[key]
            parent_recording = parent_by_key[key]
            if (
                row.content_sha256 != parent_recording.source_sha256
                or row.wav is None
                or row.wav.sample_rate_hz != parent_recording.sample_rate_hz
                or row.wav.frame_count != parent_recording.frame_count
                or row.wav.channels != parent_recording.channels
            ):
                raise FrozenInputChanged("A recording fingerprint differs from the parent Result.")
            _validate_source(
                collection.source_root,
                row,
                repository,
                request.run_id,
                guard,
            )

        reference = store.load_refinement_model_reference()
        if reference is None:
            raise FrozenModelChanged("The selected RF Model is unavailable.")
        if (
            reference.snapshot.snapshot_id != request.model_snapshot_id
            or canonical_digest(reference.snapshot.to_dict()) != request.model_digest
        ):
            raise FrozenModelChanged("The selected RF ModelSnapshot no longer matches.")
        reference = _recheck_model(reference)
        structure = structurally_reload_rf_directory(reference.root, reference.snapshot.model_id)
        if (
            structure.feature_names != reference.snapshot.rf_feature_names
            or structure.feature_config != dict(reference.snapshot.rf_feature_config)
            or structure.target_probability_column != reference.snapshot.rf_probability_column
        ):
            raise FrozenModelChanged("RF Model structure disagrees with its ModelSnapshot.")
        estimator = joblib.load(reference.root / reference.snapshot.artifact_relative_path)
        if not isinstance(estimator, RandomForestClassifier):
            raise FrozenModelChanged("RF artifact is not a supported RandomForestClassifier.")
        probability_class_order = tuple(int(value) for value in estimator.classes_)
        if probability_class_order != structure.classes:
            raise FrozenModelChanged("RF estimator class order changed after verification.")
        _emit(
            "progress",
            progress=10,
            stage_index=0,
            message="Parent, recordings, and RF Model verified",
        )

        decisions: dict[str, RefinementDecision] = {}
        total = parent.candidate_count
        completed = 0
        for parent_recording in parent.recordings:
            if not parent_recording.candidates:
                continue
            row = row_by_key[parent_recording.recording_key]
            path = _validate_source(
                collection.source_root,
                row,
                repository,
                request.run_id,
                guard,
            )
            for candidate in parent_recording.candidates:
                _check_cancelled(repository, request.run_id, guard)
                if step_delay_seconds:
                    time.sleep(step_delay_seconds)
                try:
                    features = extract_candidate_features(
                        path,
                        source_sample_rate_hz=parent_recording.sample_rate_hz,
                        source_frame_count=parent_recording.frame_count,
                        start_frame=candidate.start_frame,
                        end_frame=candidate.end_frame,
                        snapshot=reference.snapshot,
                    )
                    if features is None:
                        decision = RefinementDecision.unscored("short_segment")
                    else:
                        vector = ordered_feature_vector(
                            features, reference.snapshot.rf_feature_names
                        )
                        probability = target_probability_score(
                            estimator.predict_proba(vector),
                            estimator_classes=estimator.classes_,
                            probability_class_order=probability_class_order,
                            target_probability_column=structure.target_probability_column,
                        )
                        decision = RefinementDecision.scored(
                            probability, threshold=structure.threshold
                        )
                except RfNonFiniteFeatureError:
                    decision = RefinementDecision.unscored("non_finite_features")
                except RfSourceMismatchError as exc:
                    raise FrozenInputChanged(str(exc)) from exc
                except RfFeatureSchemaError as exc:
                    raise FrozenModelChanged(str(exc)) from exc
                except (OSError, RuntimeError, ValueError):
                    decision = RefinementDecision.unscored("feature_extraction_failed")
                decisions[candidate.candidate_id] = decision
                completed += 1
                _emit(
                    "progress",
                    progress=min(88, 10 + round(completed / total * 78)),
                    stage_index=1,
                    message="Assessing candidate intervals",
                )
            _validate_source(
                collection.source_root,
                row,
                repository,
                request.run_id,
                guard,
            )

        reference = _recheck_model(reference)
        reopened_parent = load_detection_result(repository.collection_root, parent.result_id)
        if reopened_parent != parent:
            raise ParentResultChanged("The parent Result changed during RF refinement.")
        result = DerivedResult.create(
            result_id=request.artifact_id,
            run_id=request.run_id,
            request_id=request.request_id,
            parent=parent,
            rf_model_id=reference.snapshot.model_id,
            rf_model_snapshot_id=reference.snapshot.snapshot_id,
            rf_model_manifest_sha256=reference.snapshot.manifest_sha256,
            rf_model_artifact_sha256=reference.snapshot.artifact_sha256,
            rf_model_snapshot_digest=request.model_digest,
            threshold=structure.threshold,
            probability_class_order=probability_class_order,
            target_probability_column=structure.target_probability_column,
            feature_family=str(reference.snapshot.rf_feature_family),
            feature_names=reference.snapshot.rf_feature_names,
            feature_config=reference.snapshot.rf_feature_config,
            preprocessing_order=reference.snapshot.preprocessing_order,
            backend_distribution="scikit-learn",
            backend_version=version("scikit-learn"),
            backend_revision=reference.snapshot.source_revision,
            completed_at=utc_now(),
            decisions=decisions,
        )
        _check_cancelled(repository, request.run_id, guard)
        receipt_path = repository.run_directory(request.run_id) / "receipt.json"
        if receipt_path.exists() or receipt_path.is_symlink():
            raise FileExistsError("Run receipt publication target already exists.")
        stage = repository.staging_path(request.launch_id)
        stage_derived_result(repository.collection_root, stage, request, result)
        _emit(
            "progress",
            progress=96,
            stage_index=2,
            message="Verifying immutable child Result",
        )
        _check_cancelled(repository, request.run_id, guard)
        identity = publish_staged_artifact(repository.collection_root, stage, request)
        repository.write_receipt(identity.receipt())
        _log(
            log,
            "worker_completed",
            "RF child Result publication completed",
            context={
                **context,
                "status": "completed",
                "accepted": result.accepted_count,
                "rejected": result.rejected_count,
                "unscored": result.unscored_count,
            },
        )
        _emit("completed")
        return 0
    except RefinementCancelled:
        discard_staging(repository.collection_root, request.launch_id)
        _log(
            log,
            "worker_cancelled",
            "RF candidate refinement cancelled before child publication",
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
            "Parent recording fingerprint validation failed",
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
            "Frozen RF Model validation failed",
            level="ERROR",
            context=context,
        )
        _emit("error", error_code="model_changed")
        return 6
    except ParentResultChanged:
        discard_staging(repository.collection_root, request.launch_id)
        _log(
            log,
            "parent_changed",
            "Immutable parent Result validation failed",
            level="ERROR",
            context=context,
        )
        _emit("error", error_code="parent_changed")
        return 7
    except Exception:
        try:
            discard_staging(repository.collection_root, request.launch_id)
        except Exception:
            pass
        _log(
            log,
            "publication_failed",
            "RF child Result could not be published safely",
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
    return run_refinement(
        args.request,
        args.owner_lease,
        step_delay_seconds=args.step_delay,
    )


if __name__ == "__main__":
    raise SystemExit(main())
