"""Canonical BioCall Studio launch and private supervised-Worker dispatch."""

from __future__ import annotations

import argparse
import re
from importlib.metadata import version as distribution_version
from pathlib import Path

WORKER_MODES = (
    "train-dataset-build",
    "train-cnn-training",
    "train-rf-training",
    "detect-cnn",
    "detect-rf-refinement",
)


def _diagnostic_session_id(value: str) -> str:
    if re.fullmatch(r"[a-f0-9]{32}", value) is None:
        raise argparse.ArgumentTypeError("invalid diagnostic session identifier")
    return value


def _bounded_delay(value: str) -> float:
    try:
        delay = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Worker test delay must be a number") from exc
    if not 0 <= delay <= 5:
        raise argparse.ArgumentTypeError("Worker test delay must be between 0 and 5 seconds")
    return delay


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BioCall Studio")
    parser.add_argument(
        "--version",
        action="version",
        version=distribution_version("biocall-studio"),
    )
    parser.add_argument(
        "--settings-dir",
        type=Path,
        help="Isolate BioCall Studio application data in this directory.",
    )
    parser.add_argument("--worker", choices=WORKER_MODES, help=argparse.SUPPRESS)
    parser.add_argument("--request", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--owner-lease", type=Path, help=argparse.SUPPRESS)
    parser.add_argument(
        "--worker-step-delay",
        type=_bounded_delay,
        default=0.0,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--diagnostic-session-id",
        type=_diagnostic_session_id,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--diagnostic-debug", action="store_true", help=argparse.SUPPRESS)
    return parser


def _validated_owner_guard(parser: argparse.ArgumentParser, lease_path: Path):
    from biocall_studio.shared.owner_lifetime import WorkerOwnerGuard

    try:
        guard = WorkerOwnerGuard(lease_path)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if not guard.owner_alive():
        guard.close()
        parser.error("The Worker owner is no longer alive.")
    guard.start_watchdog()
    return guard


def _dispatch_worker(args: argparse.Namespace, *, owner_guard=None) -> int:
    if owner_guard is None:
        from biocall_studio.shared.owner_lifetime import WorkerOwnerGuard

        owner_guard = WorkerOwnerGuard(args.owner_lease)
        if not owner_guard.owner_alive():
            owner_guard.close()
            raise ValueError("The Worker owner is no longer alive.")
        owner_guard.start_watchdog()

    if args.worker.startswith("train-"):
        from biocall_studio.train.workflows import worker_entry

        worker = {
            "train-dataset-build": worker_entry._run_dataset_build_worker,
            "train-cnn-training": worker_entry._run_cnn_training_worker,
            "train-rf-training": worker_entry._run_rf_training_worker,
        }[args.worker]
        return worker(
            args.request,
            args.worker_step_delay,
            args.diagnostic_session_id,
            owner_guard,
        )

    if args.worker == "detect-cnn":
        from biocall_studio.detect.workflows.detection import run_detection

        return run_detection(
            args.request,
            args.owner_lease,
            step_delay_seconds=args.worker_step_delay,
            owner_guard=owner_guard,
        )

    from biocall_studio.detect.workflows.refinement import run_refinement

    return run_refinement(
        args.request,
        args.owner_lease,
        step_delay_seconds=args.worker_step_delay,
        owner_guard=owner_guard,
    )


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    if args.worker is not None:
        if args.request is None:
            parser.error("--request is required for a supervised Worker")
        if args.owner_lease is None:
            parser.error("--owner-lease is required for a supervised Worker")
        if args.settings_dir is not None or args.diagnostic_debug:
            parser.error("GUI-only arguments cannot be used with --worker")
        guard = _validated_owner_guard(parser, args.owner_lease)
        try:
            return _dispatch_worker(args, owner_guard=guard)
        finally:
            guard.close()

    if (
        args.request is not None
        or args.owner_lease is not None
        or args.diagnostic_session_id is not None
        or args.worker_step_delay != 0
    ):
        parser.error("Worker-only arguments require --worker")

    from biocall_studio.studio.application.app import run

    return run(args.settings_dir, diagnostic_debug=args.diagnostic_debug)
