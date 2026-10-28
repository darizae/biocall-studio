"""Non-scientific QProcess fixture for ST-06 lifecycle boundary verification only."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from biocall_studio.detect.diagnostics import (
    BoundedJsonlLog,
    encode_diagnostic_record,
    resolve_run_log_path,
)
from biocall_studio.detect.owner_lifetime import DetectWorkerOwnerGuard
from biocall_studio.detect.publication import (
    discard_staging,
    publish_staged_artifact,
    stage_lifecycle_artifact,
)
from biocall_studio.detect.run_persistence import DetectRunRepository

_BEHAVIORS = {
    "success",
    "slow",
    "stubborn",
    "fail",
    "crash",
    "stderr_storm",
    "commit_then_crash",
}


def _emit(event: str, **values: object) -> None:
    payload = {"schema_version": 1, "event": event, **values}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode()) > 4_096:
        raise ValueError("Fixture Worker event exceeds 4 KiB.")
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


def run_fixture(
    request_path: Path,
    owner_lease: Path,
    *,
    behavior: str,
    step_delay_seconds: float,
) -> int:
    if behavior not in _BEHAVIORS:
        raise ValueError("Unsupported lifecycle fixture behavior.")
    if not 0 <= step_delay_seconds <= 5:
        raise ValueError("Lifecycle fixture delay is outside its bounded range.")
    repository = DetectRunRepository.from_request_path(request_path)
    request = repository.load_request(request_path.parent.name)
    guard = DetectWorkerOwnerGuard(owner_lease)
    guard.start_watchdog()
    log_path = resolve_run_log_path(
        repository.collection_root, request.run_id, "worker", create=True
    )
    log = BoundedJsonlLog(log_path)
    context = {
        "run_id": request.run_id,
        "request_id": request.request_id,
        "launch_id": request.launch_id,
    }
    try:
        if not guard.owner_alive():
            return 70
        _log(log, "worker_started", "Lifecycle fixture Worker started", context=context)
        _emit("started")
        if behavior == "crash":
            os.abort()
        if behavior == "fail":
            _log(
                log,
                "worker_failed",
                "Lifecycle fixture requested a controlled failure",
                level="ERROR",
                context=context,
            )
            _emit("error", error_code="fixture_failed")
            return 3
        if behavior == "stderr_storm":
            line = (
                b"RuntimeError(/Users/field-biologist/private-recording.wav) "
                b"api_token=secret-value C:\\Field\\private-recording.wav\n"
            )
            for _index in range(8_000):
                sys.stderr.buffer.write(line)
            sys.stderr.buffer.flush()

        steps = 80 if behavior in {"slow", "stubborn"} else 5
        for index in range(steps):
            if behavior != "stubborn" and repository.cancellation_requested(request.run_id):
                _log(
                    log,
                    "worker_cancelled",
                    "Lifecycle fixture observed cancellation",
                    level="WARNING",
                    context=context,
                )
                _emit("cancelled")
                return 2
            if not guard.owner_alive():
                return 70
            if step_delay_seconds:
                time.sleep(step_delay_seconds)
            progress = min(90, int(((index + 1) / steps) * 90))
            stage_index = min(1, int(progress >= 35))
            _emit(
                "progress",
                progress=progress,
                stage_index=stage_index,
                message=(
                    "Worker lifecycle active" if stage_index else "Frozen inputs accepted"
                ),
            )

        if repository.cancellation_requested(request.run_id) or not guard.owner_alive():
            _emit("cancelled")
            return 2
        stage = repository.staging_path(request.launch_id)
        stage_lifecycle_artifact(repository.collection_root, stage, request)
        _emit(
            "progress",
            progress=96,
            stage_index=2,
            message="Verifying immutable publication",
        )
        if not guard.owner_alive():
            discard_staging(repository.collection_root, request.launch_id)
            return 70
        identity = publish_staged_artifact(repository.collection_root, stage, request)
        if behavior == "commit_then_crash":
            os._exit(76)
        repository.write_receipt(identity.receipt())
        _log(
            log,
            "worker_completed",
            "Lifecycle fixture publication completed",
            context={**context, "status": "completed"},
        )
        _emit("completed")
        return 0
    except Exception:
        try:
            discard_staging(repository.collection_root, request.launch_id)
        except Exception:
            pass
        _log(
            log,
            "publication_failed",
            "Lifecycle fixture publication failed",
            level="ERROR",
            context={**context, "status": "failed"},
        )
        _emit("error", error_code="publication_failed")
        return 4
    finally:
        guard.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--owner-lease", required=True, type=Path)
    parser.add_argument("--behavior", required=True, choices=sorted(_BEHAVIORS))
    parser.add_argument("--step-delay", required=True, type=float)
    args = parser.parse_args(argv)
    return run_fixture(
        args.request,
        args.owner_lease,
        behavior=args.behavior,
        step_delay_seconds=args.step_delay,
    )


if __name__ == "__main__":
    raise SystemExit(main())
