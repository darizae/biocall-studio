"""Command-line configuration, kept independent of GUI imports."""

import argparse
import json
import sys
import time
from importlib.metadata import version
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="alpaca Desktop Trainer")
    parser.add_argument("--version", action="version", version=version("alpaca-desktop"))
    parser.add_argument(
        "--settings-dir",
        type=Path,
        help="Isolate Application Settings in this directory instead of the Qt standard location.",
    )
    parser.add_argument(
        "--worker", choices=("dataset-build", "cnn-training"), help=argparse.SUPPRESS
    )
    parser.add_argument("--request", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--worker-step-delay", type=float, default=0.0, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.worker == "dataset-build":
        if args.request is None:
            parser.error("--request is required for the Dataset Build Worker")
        if not 0 <= args.worker_step_delay <= 5:
            parser.error("--worker-step-delay must be between 0 and 5 seconds")
        return _run_dataset_build_worker(args.request, args.worker_step_delay)
    if args.worker == "cnn-training":
        if args.request is None:
            parser.error("--request is required for the CNN Training Worker")
        if not 0 <= args.worker_step_delay <= 5:
            parser.error("--worker-step-delay must be between 0 and 5 seconds")
        return _run_cnn_training_worker(args.request, args.worker_step_delay)

    from alpaca_desktop.gui.app import run

    return run(args.settings_dir)


def _run_dataset_build_worker(request_path: Path, step_delay_seconds: float = 0.0) -> int:
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
    try:
        if request_path.stat().st_size > 1_000_000:
            raise ValueError("Dataset Build request exceeds 1 MiB.")
        with request_path.open(encoding="utf-8") as stream:
            request = DatasetBuildRequest.from_dict(json.load(stream))
        root = Path(request.collection_root)
        scan = load_collection_metadata(root)
        if scan.collection_id != request.collection_id:
            raise ValueError("Dataset Build request Collection binding no longer matches.")
        emit("started", message="Dataset Build Worker started")
        artifact = build_dataset(
            root,
            scan,
            request.config,
            dataset_id=request.dataset_id,
            cancelled=lambda: cancellation_requested(request_path),
            progress=lambda stage_index, progress, message: emit(
                "progress",
                stage_index=stage_index,
                progress=progress,
                message=message,
            ),
            run_id=request.run_id,
            request_id=request.request_id,
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
        return 2
    except Exception as exc:
        message = str(exc)
        if root is not None:
            message = message.replace(str(root), "<Collection>")
        emit("error", message=message)
        print(message, file=sys.stderr)
        return 1
    emit("completed", output_id=artifact.dataset_id, message="Output verified and published")
    return 0


def _run_cnn_training_worker(request_path: Path, step_delay_seconds: float = 0.0) -> int:
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
    try:
        if request_path.stat().st_size > 1_000_000:
            raise ValueError("CNN Training request exceeds 1 MiB.")
        with request_path.open(encoding="utf-8") as stream:
            request = CnnTrainingRequest.from_dict(json.load(stream))
        root = Path(request.collection_root)
        metadata = load_collection_metadata(root)
        if metadata.collection_id != request.collection_id:
            raise ValueError("CNN Training request Collection binding no longer matches.")
        emit("started", message="CNN Training Worker started")
        artifact = train_cnn_model(
            root,
            request,
            cancelled=lambda: cancellation_requested(request_path),
            progress=lambda stage_index, progress, message: emit(
                "progress",
                stage_index=stage_index,
                progress=progress,
                message=message,
            ),
            measurement=lambda row: emit("measurement", **row),
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
        return 2
    except Exception as exc:
        message = str(exc)
        if root is not None:
            message = message.replace(str(root), "<Collection>")
        emit("error", message=message)
        print(message, file=sys.stderr)
        return 1
    emit("completed", output_id=artifact.model_id, message="Output verified and published")
    return 0
