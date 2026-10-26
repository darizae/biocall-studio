"""Command-line configuration, kept independent of GUI imports."""

import argparse
import json
import logging
import re
import sys
import time
from importlib.metadata import version
from pathlib import Path

from alpaca_desktop.persistence.diagnostics import (
    WorkerDiagnosticSession,
    sanitize_diagnostic_text,
)


def _diagnostic_session_id(value: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{32}", value):
        raise argparse.ArgumentTypeError("invalid diagnostic session identifier")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="alpaca Desktop Trainer")
    parser.add_argument("--version", action="version", version=version("alpaca-desktop"))
    parser.add_argument(
        "--settings-dir",
        type=Path,
        help="Isolate Application Settings in this directory instead of the Qt standard location.",
    )
    parser.add_argument(
        "--worker",
        choices=("dataset-build", "cnn-training", "rf-training"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--request", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--worker-step-delay", type=float, default=0.0, help=argparse.SUPPRESS)
    parser.add_argument(
        "--diagnostic-session-id",
        type=_diagnostic_session_id,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--owner-lease", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--diagnostic-debug", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.worker == "dataset-build":
        if args.request is None:
            parser.error("--request is required for the Dataset Build Worker")
        if not 0 <= args.worker_step_delay <= 5:
            parser.error("--worker-step-delay must be between 0 and 5 seconds")
        guard = _worker_owner_guard(parser, args.owner_lease)
        return _run_dataset_build_worker(
            args.request, args.worker_step_delay, args.diagnostic_session_id, guard
        )
    if args.worker == "cnn-training":
        if args.request is None:
            parser.error("--request is required for the CNN Training Worker")
        if not 0 <= args.worker_step_delay <= 5:
            parser.error("--worker-step-delay must be between 0 and 5 seconds")
        guard = _worker_owner_guard(parser, args.owner_lease)
        return _run_cnn_training_worker(
            args.request, args.worker_step_delay, args.diagnostic_session_id, guard
        )
    if args.worker == "rf-training":
        if args.request is None:
            parser.error("--request is required for the RF Training Worker")
        if not 0 <= args.worker_step_delay <= 5:
            parser.error("--worker-step-delay must be between 0 and 5 seconds")
        guard = _worker_owner_guard(parser, args.owner_lease)
        return _run_rf_training_worker(
            args.request, args.worker_step_delay, args.diagnostic_session_id, guard
        )

    from alpaca_desktop.gui.app import run

    return run(args.settings_dir, diagnostic_debug=args.diagnostic_debug)


def _worker_owner_guard(parser, lease_path: Path | None):
    from alpaca_desktop.application.owner_lifetime import WorkerOwnerGuard

    if lease_path is None:
        parser.error("--owner-lease is required for a supervised Worker")
    try:
        guard = WorkerOwnerGuard(lease_path)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if not guard.owner_alive():
        parser.error("The Worker owner is no longer alive.")
    guard.start_watchdog()
    return guard


def _run_dataset_build_worker(
    request_path: Path,
    step_delay_seconds: float = 0.0,
    diagnostic_session_id: str | None = None,
    owner_guard=None,
) -> int:
    from alpaca_desktop.persistence.collection_metadata import load_collection_metadata
    from alpaca_desktop.persistence.runs import (
        WORKER_RESULT_SCHEMA_VERSION,
        cancellation_requested,
        write_completion_receipt,
    )
    from alpaca_desktop.workflows.dataset_build import (
        DatasetBuildCancelled,
        DatasetBuildRequest,
        build_dataset,
    )

    def emit(event: str, **payload) -> None:
        print(json.dumps({"schema_version": 1, "event": event, **payload}), flush=True)
        if step_delay_seconds:
            time.sleep(step_delay_seconds)

    root: Path | None = None
    diagnostics: WorkerDiagnosticSession | None = None
    try:
        if request_path.stat().st_size > 1_000_000:
            raise ValueError("Dataset Build request exceeds 1 MiB.")
        with request_path.open(encoding="utf-8") as stream:
            request = DatasetBuildRequest.from_dict(json.load(stream))
        root = Path(request.collection_root)
        scan = load_collection_metadata(root)
        if scan.collection_id != request.collection_id:
            raise ValueError("Dataset Build request Collection binding no longer matches.")
        try:
            diagnostics = WorkerDiagnosticSession(
                root,
                request.run_id,
                request.request_id,
                session_id=diagnostic_session_id,
                debug=False,
                request_path=request_path,
                component="alpaca_desktop.worker.dataset",
            )
        except (OSError, ValueError):
            print("Worker diagnostics unavailable", file=sys.stderr)
        if diagnostics is not None:
            diagnostics.emit(
                "worker_started",
                "Dataset Build Worker started",
                context={"run_kind": "dataset_build", "operation": "dataset_build"},
            )
        emit("started", message="Dataset Build Worker started")
        last_diagnostic_progress = (-1, -1)

        def progress(stage_index: int, progress: int, message: str) -> None:
            nonlocal last_diagnostic_progress
            emit("progress", stage_index=stage_index, progress=progress, message=message)
            bucket = progress // 10
            if diagnostics is not None and (stage_index, bucket) != last_diagnostic_progress:
                last_diagnostic_progress = (stage_index, bucket)
                diagnostics.emit(
                    "worker_stage",
                    "Dataset Build stage updated",
                    context={"stage": f"stage-{stage_index}", "count": progress},
                )

        artifact = build_dataset(
            root,
            scan,
            request.config,
            dataset_id=request.dataset_id,
            cancelled=lambda: (
                cancellation_requested(request_path)
                or (owner_guard is not None and not owner_guard.owner_alive())
            ),
            progress=progress,
            run_id=request.run_id,
            request_id=request.request_id,
            publication_allowed=(None if owner_guard is None else owner_guard.owner_alive),
        )
        receipt = {
            "schema_version": WORKER_RESULT_SCHEMA_VERSION,
            "run_id": request.run_id,
            "request_id": request.request_id,
            "output_kind": "dataset",
            "output_id": artifact.dataset_id,
        }
        write_completion_receipt(request_path, receipt)
    except DatasetBuildCancelled as exc:
        emit("cancelled", message=str(exc))
        if diagnostics is not None:
            diagnostics.emit(
                "worker_cancelled",
                "Dataset Build Worker cancelled before publication",
                level=logging.WARNING,
                context={"status": "cancelled"},
            )
        return 2
    except Exception as exc:
        message = sanitize_diagnostic_text(str(exc))
        if diagnostics is not None:
            diagnostics.emit(
                "worker_failed",
                "Dataset Build Worker failed",
                level=logging.ERROR,
                context={"status": "failed", "exception_type": type(exc).__name__},
            )
        emit("error", message=message)
        print(message, file=sys.stderr)
        return 1
    else:
        if diagnostics is not None:
            diagnostics.emit(
                "worker_completed",
                "Dataset output verified and published",
                context={"status": "completed", "run_kind": "dataset_build"},
            )
        emit("completed", output_id=artifact.dataset_id, message="Output verified and published")
        return 0
    finally:
        if diagnostics is not None:
            diagnostics.close()
        if owner_guard is not None:
            owner_guard.close()


def _run_cnn_training_worker(
    request_path: Path,
    step_delay_seconds: float = 0.0,
    diagnostic_session_id: str | None = None,
    owner_guard=None,
) -> int:
    from alpaca_desktop.persistence.collection_metadata import load_collection_metadata
    from alpaca_desktop.persistence.runs import (
        WORKER_RESULT_SCHEMA_VERSION,
        cancellation_requested,
        write_completion_receipt,
    )
    from alpaca_desktop.workflows.cnn_training import (
        CnnTrainingCancelled,
        CnnTrainingRequest,
        train_cnn_model,
    )

    def emit(event: str, **payload) -> None:
        print(json.dumps({"schema_version": 1, "event": event, **payload}), flush=True)
        if step_delay_seconds:
            time.sleep(step_delay_seconds)

    root: Path | None = None
    diagnostics: WorkerDiagnosticSession | None = None
    try:
        if request_path.stat().st_size > 1_000_000:
            raise ValueError("CNN Training request exceeds 1 MiB.")
        with request_path.open(encoding="utf-8") as stream:
            request = CnnTrainingRequest.from_dict(json.load(stream))
        root = Path(request.collection_root)
        metadata = load_collection_metadata(root)
        if metadata.collection_id != request.collection_id:
            raise ValueError("CNN Training request Collection binding no longer matches.")
        try:
            diagnostics = WorkerDiagnosticSession(
                root,
                request.run_id,
                request.request_id,
                session_id=diagnostic_session_id,
                debug=request.config.effective_values["logging_level"] == "debug",
                request_path=request_path,
                component="alpaca_desktop.worker.cnn",
            )
        except (OSError, ValueError):
            print("Worker diagnostics unavailable", file=sys.stderr)
        if diagnostics is not None:
            diagnostics.emit(
                "worker_started",
                "CNN Training Worker started",
                context={"run_kind": "training", "training_family": "cnn"},
            )
        emit("started", message="CNN Training Worker started")
        last_diagnostic_progress = (-1, -1)

        def progress(stage_index: int, progress: int, message: str) -> None:
            nonlocal last_diagnostic_progress
            emit("progress", stage_index=stage_index, progress=progress, message=message)
            bucket = progress // 10
            if diagnostics is not None and (stage_index, bucket) != last_diagnostic_progress:
                last_diagnostic_progress = (stage_index, bucket)
                diagnostics.emit(
                    "training_stage",
                    "CNN Training stage updated",
                    context={
                        "stage": f"stage-{stage_index}",
                        "count": progress,
                        "training_family": "cnn",
                    },
                )

        measurement_count = 0

        def measurement(row: dict) -> None:
            nonlocal measurement_count
            measurement_count += 1
            emit("measurement", **row)
            if diagnostics is not None:
                diagnostics.emit(
                    "measurement_available",
                    "CNN measurement became available",
                    level=logging.DEBUG,
                    context={"training_family": "cnn", "count": measurement_count},
                )

        artifact = train_cnn_model(
            root,
            request,
            cancelled=lambda: (
                cancellation_requested(request_path)
                or (owner_guard is not None and not owner_guard.owner_alive())
            ),
            progress=progress,
            measurement=measurement,
            publication_allowed=(None if owner_guard is None else owner_guard.owner_alive),
        )
        write_completion_receipt(
            request_path,
            {
                "schema_version": WORKER_RESULT_SCHEMA_VERSION,
                "run_id": request.run_id,
                "request_id": request.request_id,
                "output_kind": "model",
                "output_id": artifact.model_id,
            },
        )
    except CnnTrainingCancelled as exc:
        emit("cancelled", message=str(exc))
        if diagnostics is not None:
            diagnostics.emit(
                "worker_cancelled",
                "CNN Training Worker cancelled before publication",
                level=logging.WARNING,
                context={"status": "cancelled", "training_family": "cnn"},
            )
        return 2
    except Exception as exc:
        message = sanitize_diagnostic_text(str(exc))
        if diagnostics is not None:
            diagnostics.emit(
                "worker_failed",
                "CNN Training Worker failed",
                level=logging.ERROR,
                context={
                    "status": "failed",
                    "training_family": "cnn",
                    "exception_type": type(exc).__name__,
                },
            )
        emit("error", message=message)
        print(message, file=sys.stderr)
        return 1
    else:
        if diagnostics is not None:
            diagnostics.emit(
                "worker_completed",
                "CNN Model verified and published",
                context={"status": "completed", "training_family": "cnn"},
            )
        emit("completed", output_id=artifact.model_id, message="Output verified and published")
        return 0
    finally:
        if diagnostics is not None:
            diagnostics.close()
        if owner_guard is not None:
            owner_guard.close()


def _run_rf_training_worker(
    request_path: Path,
    step_delay_seconds: float = 0.0,
    diagnostic_session_id: str | None = None,
    owner_guard=None,
) -> int:
    from alpaca_desktop.persistence.collection_metadata import load_collection_metadata
    from alpaca_desktop.persistence.runs import (
        WORKER_RESULT_SCHEMA_VERSION,
        cancellation_requested,
        write_completion_receipt,
    )
    from alpaca_desktop.workflows.rf_training import (
        RfTrainingCancelled,
        RfTrainingRequest,
        train_rf_model,
    )

    def emit(event: str, **payload) -> None:
        print(json.dumps({"schema_version": 1, "event": event, **payload}), flush=True)
        if step_delay_seconds:
            time.sleep(step_delay_seconds)

    root: Path | None = None
    diagnostics: WorkerDiagnosticSession | None = None
    try:
        if request_path.stat().st_size > 1_000_000:
            raise ValueError("RF Training request exceeds 1 MiB.")
        with request_path.open(encoding="utf-8") as stream:
            request = RfTrainingRequest.from_dict(json.load(stream))
        root = Path(request.collection_root)
        metadata = load_collection_metadata(root)
        if metadata.collection_id != request.collection_id:
            raise ValueError("RF Training request Collection binding no longer matches.")
        try:
            diagnostics = WorkerDiagnosticSession(
                root,
                request.run_id,
                request.request_id,
                session_id=diagnostic_session_id,
                debug=request.config.effective_values["logging_level"] == "debug",
                request_path=request_path,
                component="alpaca_desktop.worker.rf",
            )
        except (OSError, ValueError):
            print("Worker diagnostics unavailable", file=sys.stderr)
        if diagnostics is not None:
            diagnostics.emit(
                "worker_started",
                "RF Training Worker started",
                context={"run_kind": "training", "training_family": "rf"},
            )
        emit("started", message="RF Training Worker started")
        last_diagnostic_progress = (-1, -1)

        def progress(stage_index: int, progress: int, message: str) -> None:
            nonlocal last_diagnostic_progress
            emit("progress", stage_index=stage_index, progress=progress, message=message)
            bucket = progress // 10
            if diagnostics is not None and (stage_index, bucket) != last_diagnostic_progress:
                last_diagnostic_progress = (stage_index, bucket)
                diagnostics.emit(
                    "training_stage",
                    "RF Training stage updated",
                    context={
                        "stage": f"stage-{stage_index}",
                        "count": progress,
                        "training_family": "rf",
                    },
                )

        measurement_count = 0

        def measurement(row: dict) -> None:
            nonlocal measurement_count
            measurement_count += 1
            emit("measurement", **row)
            if diagnostics is not None:
                diagnostics.emit(
                    "measurement_available",
                    "RF measurement became available",
                    level=logging.DEBUG,
                    context={"training_family": "rf", "count": measurement_count},
                )

        artifact = train_rf_model(
            root,
            request,
            cancelled=lambda: (
                cancellation_requested(request_path)
                or (owner_guard is not None and not owner_guard.owner_alive())
            ),
            progress=progress,
            measurement=measurement,
            publication_allowed=(None if owner_guard is None else owner_guard.owner_alive),
        )
        write_completion_receipt(
            request_path,
            {
                "schema_version": WORKER_RESULT_SCHEMA_VERSION,
                "run_id": request.run_id,
                "request_id": request.request_id,
                "output_kind": "model",
                "output_id": artifact.model_id,
            },
        )
    except RfTrainingCancelled as exc:
        emit("cancelled", message=str(exc))
        if diagnostics is not None:
            diagnostics.emit(
                "worker_cancelled",
                "RF Training Worker cancelled before publication",
                level=logging.WARNING,
                context={"status": "cancelled", "training_family": "rf"},
            )
        return 2
    except Exception as exc:
        message = sanitize_diagnostic_text(str(exc))
        if diagnostics is not None:
            diagnostics.emit(
                "worker_failed",
                "RF Training Worker failed",
                level=logging.ERROR,
                context={
                    "status": "failed",
                    "training_family": "rf",
                    "exception_type": type(exc).__name__,
                },
            )
        emit("error", message=message)
        print(message, file=sys.stderr)
        return 1
    else:
        if diagnostics is not None:
            diagnostics.emit(
                "worker_completed",
                "RF Model verified and published",
                context={"status": "completed", "training_family": "rf"},
            )
        emit("completed", output_id=artifact.model_id, message="Output verified and published")
        return 0
    finally:
        if diagnostics is not None:
            diagnostics.close()
        if owner_guard is not None:
            owner_guard.close()
