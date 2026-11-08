from __future__ import annotations

import json
from pathlib import Path

import pytest

from biocall_studio.detect.persistence.diagnostics import (
    BoundedJsonlLog,
    BoundedStderrCapture,
    encode_diagnostic_record,
    read_diagnostic_records,
    resolve_run_log_path,
    sanitize_diagnostic_text,
)


def test_diagnostics_are_allowlisted_bounded_and_privacy_normalized():
    """Case: UT-DET-012."""
    hostile = (
        "failed /Users/researcher/private/Rainforest/Dawn_A.wav "
        "C:\\Field\\Secret\\Night_B.wav \\\\server\\share\\Third.wav "
        "api_token=secret-value RuntimeError(raw private details)"
    )
    safe = sanitize_diagnostic_text(hostile, limit=180)
    assert "researcher" not in safe
    assert "Dawn_A.wav" not in safe
    assert "Night_B.wav" not in safe
    assert "Third.wav" not in safe
    assert "secret-value" not in safe
    assert len(safe) <= 180

    encoded = encode_diagnostic_record(
        component="detect.worker",
        event="worker_failed",
        message=hostile,
        level="ERROR",
        context={
            "run_id": "drun_0123456789abcdef0123456789abcdef",
            "launch_id": "launch_0123456789abcdef0123456789abcdef",
            "status": "failed",
            "progress": 12,
            "raw_path": "/must/not/be/copied",
            "exception": hostile,
        },
    )
    record = json.loads(encoded)
    assert set(record) == {
        "schema_version",
        "timestamp_utc",
        "level",
        "component",
        "event",
        "message",
        "pid",
        "run_id",
        "launch_id",
        "status",
        "progress",
    }
    assert "raw_path" not in record and "exception" not in record


def test_diagnostic_rotation_reader_and_symlink_policy(tmp_path: Path):
    """Case: UT-DET-012."""
    collection = tmp_path / "collection"
    run = collection / "runs" / "drun_0123456789abcdef0123456789abcdef"
    run.mkdir(parents=True)
    path = resolve_run_log_path(collection, run.name, "supervisor", create=True)
    sink = BoundedJsonlLog(path, max_bytes=700, backup_count=2)
    for index in range(30):
        sink.write(
            encode_diagnostic_record(
                component="detect.supervisor",
                event="progress",
                message="bounded lifecycle progress " + ("x" * 80),
                level="INFO",
                context={"progress": index},
            )
        )
    assert path.stat().st_size <= 700
    assert path.with_name("supervisor.jsonl.1").is_file()
    assert not path.with_name("supervisor.jsonl.3").exists()

    records, notices = read_diagnostic_records(collection, path, max_bytes=700)
    assert records and not notices
    assert all(
        set(item)
        <= {
            "schema_version",
            "timestamp_utc",
            "level",
            "component",
            "event",
            "message",
            "pid",
            "run_id",
            "request_id",
            "launch_id",
            "status",
            "stage",
            "progress",
            "stage_index",
            "exit_code",
            "dropped_bytes",
            "count",
        }
        for item in records
    )

    outside = tmp_path / "outside.jsonl"
    outside.write_text("{}\n")
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(ValueError, match="symlink|unsafe"):
        resolve_run_log_path(collection, run.name, "supervisor")
    with pytest.raises(ValueError, match="contained|symlink|unsafe"):
        read_diagnostic_records(collection, path)

    capture = BoundedStderrCapture(max_bytes=256, max_lines=3)
    capture.feed(("/Users/name/private.wav token=secret\n" * 100).encode())
    capture.finish()
    assert len(capture.lines) <= 3
    assert capture.dropped_bytes > 0
    assert "private.wav" not in capture.summary
    assert "secret" not in capture.summary
