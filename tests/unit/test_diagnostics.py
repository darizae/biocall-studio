from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

import pytest

from biocall_studio_train.persistence.diagnostics import (
    BoundedJsonlSink,
    BoundedStderrCapture,
    DiagnosticJsonlHandler,
    encode_diagnostic_record,
    export_diagnostics_bundle,
    prune_app_logs,
    read_diagnostic_records,
    sanitize_diagnostic_text,
    worker_log_path,
)


def _record(**overrides) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": 1,
        "timestamp_utc": "2026-10-26T08:09:10.123Z",
        "level": "INFO",
        "component": "biocall_studio_train.test",
        "event": "test_event",
        "message": "Safe diagnostic summary",
        "session_id": "session-a1b2",
        "pid": 123,
        "run_id": "run-a1b2",
        "request_id": "request-a1b2",
    }
    values.update(overrides)
    return values


def _run_root(tmp_path: Path, run_id: str = "run-safe") -> Path:
    root = tmp_path / "Collection"
    (root / ".alpaca" / "runs" / run_id).mkdir(parents=True)
    return root


def test_versioned_record_schema_levels_correlation_and_context_allowlist(tmp_path):
    """Case: UT-LOG-001."""
    encoded = encode_diagnostic_record(
        component="biocall_studio_train.worker.cnn",
        event="training_started",
        message="CNN training started",
        level="INFO",
        session_id="session-a1b2",
        context={
            "run_id": "run-a1b2",
            "request_id": "request-a1b2",
            "training_family": "cnn",
            "count": 4,
            "unknown": "must not survive",
            "collection_path": "/Users/person/private",
        },
        timestamp=datetime(2026, 10, 26, 8, 9, 10, 123456, tzinfo=UTC),
        pid=456,
    )
    assert encoded.endswith(b"\n")
    record = json.loads(encoded)
    assert record == {
        "schema_version": 1,
        "timestamp_utc": "2026-10-26T08:09:10.123Z",
        "level": "INFO",
        "component": "biocall_studio_train.worker.cnn",
        "event": "training_started",
        "message": "CNN training started",
        "session_id": "session-a1b2",
        "pid": 456,
        "run_id": "run-a1b2",
        "request_id": "request-a1b2",
        "training_family": "cnn",
        "count": 4,
    }

    path = tmp_path / "worker.jsonl"
    handler = DiagnosticJsonlHandler(
        BoundedJsonlSink(path, max_bytes=4_096, backup_count=1),
        session_id="session-a1b2",
        level=logging.INFO,
    )
    logger = logging.Logger("biocall_studio_train.test", logging.DEBUG)
    logger.addHandler(handler)
    logger.debug(
        "debug is filtered",
        extra={"diagnostic_event": "filtered", "diagnostic_context": {}},
    )
    logger.info(
        "visible",
        extra={
            "diagnostic_event": "visible_event",
            "diagnostic_context": {"run_id": "run-a1b2"},
        },
    )
    handler.close()
    records, notices = read_diagnostic_records(path)
    assert notices == ()
    assert [item["event"] for item in records] == ["visible_event"]


@pytest.mark.parametrize(
    ("secret", "message"),
    [
        ("/Users/alice/private/call.wav", "failed at /Users/alice/private/call.wav"),
        ("/home/alice/hpc/job.wav", "failed at /home/alice/hpc/job.wav"),
        (r"C:\\Users\\Alice\\bird.wav", r"failed at C:\\Users\\Alice\\bird.wav"),
        (r"\\\\server\\share\\bird.wav", r"failed at \\\\server\\share\\bird.wav"),
        ("bird-secret.wav", "recordings/bird-secret.wav could not be decoded"),
        ("hunter2", "password=hunter2"),
        ("abc123", "API_TOKEN: abc123"),
    ],
)
def test_sensitive_text_variants_are_removed(secret, message):
    """Case: UT-LOG-002."""
    sanitized = sanitize_diagnostic_text(message + "\nsecond\tline\x00")
    assert secret not in sanitized
    assert "\n" not in sanitized
    assert "\t" not in sanitized
    assert "\x00" not in sanitized
    assert len(sanitized) <= 2_000

    encoded = encode_diagnostic_record(
        component="biocall_studio_train.test",
        event="failure",
        message=message,
        level="ERROR",
        context={"exception_type": "RuntimeError"},
    )
    assert secret.encode() not in encoded


def test_containment_and_export_revalidate_instead_of_copying_bytes(tmp_path):
    """Case: UT-LOG-003."""
    root = _run_root(tmp_path)
    path = worker_log_path(root, "run-safe", create=True)
    assert path == root / ".alpaca" / "runs" / "run-safe" / "logs" / "worker.jsonl"
    with pytest.raises(ValueError):
        worker_log_path(root, "../escape", create=True)

    unsafe_run = root / ".alpaca" / "runs" / "run-link"
    unsafe_run.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink|contained|unsafe"):
        worker_log_path(root, "run-link", create=True)

    app_logs = tmp_path / "settings" / "logs"
    app_logs.mkdir(parents=True)
    app_path = app_logs / "session-2026-10-26-a1b2.jsonl"
    app_path.write_text(
        json.dumps(_record(message="safe"))
        + "\nnot-json\n"
        + json.dumps({**_record(event="second"), "unknown": "/Users/alice/leak"})
        + "\n",
        encoding="utf-8",
    )
    path.write_text(
        json.dumps(_record(message="recordings/private-bird.wav", event="worker")) + "\n",
        encoding="utf-8",
    )
    destination = tmp_path / "diagnostics.zip"
    result = export_diagnostics_bundle(
        destination,
        app_log_dir=app_logs,
        selected_run=(root, "run-safe"),
        inventory={"session_id": "session-a1b2", "run_id": "run-safe"},
    )
    assert result.path == destination
    assert result.skipped_records == 1
    with ZipFile(destination) as archive:
        names = set(archive.namelist())
        assert "diagnostics.json" in names
        assert any(name.startswith("app/") for name in names)
        assert "runs/run-safe/worker.jsonl" in names
        combined = b"".join(archive.read(name) for name in names)
    assert b"not-json" not in combined
    assert b"unknown" not in combined
    assert b"private-bird.wav" not in combined
    assert str(root).encode() not in combined
    assert b"run-safe" in combined

    with pytest.raises(FileExistsError):
        export_diagnostics_bundle(destination, app_log_dir=app_logs)
    unsafe_destination = tmp_path / "diagnostics-link.zip"
    unsafe_destination.symlink_to(destination)
    with pytest.raises(ValueError, match="unsafe"):
        export_diagnostics_bundle(
            unsafe_destination,
            app_log_dir=app_logs,
            overwrite=True,
        )


def test_rotation_pruning_stderr_bounds_and_degraded_sink(tmp_path, monkeypatch):
    """Case: UT-LOG-004."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    active = log_dir / "session-2026-10-26-active.jsonl"
    sink = BoundedJsonlSink(active, max_bytes=220, backup_count=2)
    for index in range(20):
        sink.write((json.dumps(_record(message=f"message {index}")) + "\n").encode())
    sink.close()
    assert active.stat().st_size <= 220
    assert (log_dir / f"{active.name}.1").stat().st_size <= 220
    assert (log_dir / f"{active.name}.2").stat().st_size <= 220
    assert not (log_dir / f"{active.name}.3").exists()

    old = log_dir / "session-2026-09-01-old0.jsonl"
    old.write_bytes(b"x" * 40)
    stale_time = (datetime.now(UTC) - timedelta(days=30)).timestamp()
    os.utime(old, (stale_time, stale_time))
    unrelated = log_dir / "keep-me.txt"
    unrelated.write_text("owned by somebody else")
    pruned = prune_app_logs(log_dir, active_path=active, max_age_days=14, total_max_bytes=500)
    assert old in pruned
    assert not old.exists()
    assert unrelated.exists()
    assert active.exists()

    capture = BoundedStderrCapture(max_bytes=64, max_lines=3)
    capture.feed((b"/Users/alice/private.wav secret\n" * 50) + b"last line\n")
    capture.finish()
    assert capture.dropped_bytes > 0
    assert len(capture.lines) <= 3
    assert "alice" not in capture.summary

    broken = tmp_path / "broken.jsonl"
    degraded = BoundedJsonlSink(broken, max_bytes=200, backup_count=1)
    monkeypatch.setattr(degraded, "_append", lambda _payload: (_ for _ in ()).throw(OSError()))
    degraded.write(b"{}\n")
    degraded.write(b"{}\n")
    assert degraded.failed
    assert degraded.failure_count == 1
