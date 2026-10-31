from __future__ import annotations

from dataclasses import replace

import pytest

from biocall_studio.detect.domain.runs import (
    DetectRunRequest,
    DetectRunStatus,
    PublicationReceipt,
    RunConflictError,
    RunTransitionError,
    assert_run_start_allowed,
    complete_run,
    new_run_record,
    recover_run,
    transition_run,
    update_run_progress,
)


def _request(**changes) -> DetectRunRequest:
    values = {
        "run_id": "drun_0123456789abcdef0123456789abcdef",
        "request_id": "dreq_0123456789abcdef0123456789abcdef",
        "launch_id": "launch_0123456789abcdef0123456789abcdef",
        "reservation_owner_id": "owner_0123456789abcdef0123456789abcdef",
        "collection_id": "det_0123456789abcdef0123456789abcdef",
        "binding_revision": 3,
        "inventory_id": "inv_0123456789abcdef0123456789abcdef",
        "inventory_digest": "a" * 64,
        "selected_recording_keys": (
            "recordings/dawn-a.wav",
            "recordings/dawn-b.wav",
        ),
        "model_snapshot_id": "mdl_0123456789abcdef0123456789abcdef",
        "model_digest": "b" * 64,
        "settings": {"fixture_contract": "lifecycle-v1", "worker_limit": 2},
        "artifact_id": "pub_0123456789abcdef0123456789abcdef",
        "created_at": "2026-10-28T08:00:00.000Z",
    }
    values.update(changes)
    return DetectRunRequest.create(**values)


def _record():
    return new_run_record(
        _request(),
        title="Rainforest dawn",
        stages=("Validate frozen inputs", "Exercise Worker", "Publish artifact"),
        now="2026-10-28T08:00:00.000Z",
    )


def _receipt(record=None) -> PublicationReceipt:
    record = record or _record()
    return PublicationReceipt(
        schema_version=1,
        run_id=record.run_id,
        request_id=record.request_id,
        launch_id=record.launch_id,
        artifact_id=record.artifact_id,
        artifact_kind="lifecycle_fixture",
        artifact_digest="c" * 64,
        published_at="2026-10-28T08:00:05.000Z",
    )


def test_run_input_freeze_state_machine_and_single_active_reservation():
    """Case: UT-DET-010."""
    settings = {"fixture_contract": "lifecycle-v1", "worker_limit": 2}
    request = _request(settings=settings)
    settings["worker_limit"] = 99

    assert request.setting("worker_limit") == 2
    assert request.selected_recording_keys == tuple(sorted(request.selected_recording_keys))
    assert DetectRunRequest.from_dict(request.to_dict()) == request
    assert "/" not in request.model_digest
    assert "source_root" not in request.to_dict()

    record = new_run_record(
        request,
        title="Rainforest dawn",
        stages=("Validate frozen inputs", "Exercise Worker", "Publish artifact"),
        now=request.created_at,
    )
    assert record.status is DetectRunStatus.PREPARING
    assert record.active and not record.terminal
    assert_run_start_allowed([record], request)

    other = _request(
        run_id="drun_1123456789abcdef0123456789abcdef",
        request_id="dreq_1123456789abcdef0123456789abcdef",
        launch_id="launch_1123456789abcdef0123456789abcdef",
        artifact_id="pub_1123456789abcdef0123456789abcdef",
    )
    with pytest.raises(RunConflictError, match="one Active Detect Run"):
        assert_run_start_allowed([record], other)

    running = transition_run(
        record,
        DetectRunStatus.RUNNING,
        now="2026-10-28T08:00:01.000Z",
        process_id=4321,
        message="Worker started",
    )
    progressed = update_run_progress(
        running,
        progress=45,
        stage_index=1,
        now="2026-10-28T08:00:02.000Z",
        message="Lifecycle boundary active",
    )
    cancelling = transition_run(
        progressed,
        DetectRunStatus.CANCELLING,
        now="2026-10-28T08:00:03.000Z",
        message="Cancellation requested",
    )
    cancelled = transition_run(
        cancelling,
        DetectRunStatus.CANCELLED,
        now="2026-10-28T08:00:04.000Z",
        message="Cancelled",
    )
    assert cancelled.terminal and not cancelled.active
    assert cancelled.process_id == 4321
    assert cancelled.published_artifact_id is None

    with pytest.raises(RunTransitionError):
        transition_run(
            cancelled,
            DetectRunStatus.RUNNING,
            now="2026-10-28T08:00:05.000Z",
        )
    with pytest.raises(RunTransitionError, match="monotonic"):
        update_run_progress(
            progressed,
            progress=20,
            stage_index=0,
            now="2026-10-28T08:00:03.000Z",
        )
    with pytest.raises(ValueError, match="non-finite"):
        _request(settings={"fixture_contract": "lifecycle-v1", "threshold": float("nan")})


def test_receipt_matching_completion_and_restart_recovery_are_conservative():
    """Case: UT-DET-011."""
    preparing = _record()
    running = transition_run(
        preparing,
        DetectRunStatus.RUNNING,
        now="2026-10-28T08:00:01.000Z",
        process_id=123,
    )
    receipt = _receipt(running)

    completed = complete_run(
        running,
        receipt,
        now="2026-10-28T08:00:06.000Z",
    )
    assert completed.status is DetectRunStatus.COMPLETED
    assert completed.progress == 100
    assert completed.stage_index == len(completed.stages)
    assert completed.published_artifact_id == running.artifact_id
    assert completed.published_artifact_digest == receipt.artifact_digest

    with pytest.raises(RunTransitionError, match="receipt"):
        complete_run(
            running,
            replace(receipt, launch_id="launch_ffffffffffffffffffffffffffffffff"),
            now="2026-10-28T08:00:06.000Z",
        )

    recovered = recover_run(
        running,
        receipt=receipt,
        publication_valid=True,
        now="2026-10-28T08:00:07.000Z",
    )
    assert recovered.status is DetectRunStatus.COMPLETED

    missing_receipt = recover_run(
        running,
        receipt=None,
        publication_valid=True,
        now="2026-10-28T08:00:07.000Z",
    )
    assert missing_receipt.status is DetectRunStatus.INTERRUPTED

    missing_artifact = recover_run(
        running,
        receipt=receipt,
        publication_valid=False,
        now="2026-10-28T08:00:07.000Z",
    )
    assert missing_artifact.status is DetectRunStatus.INTERRUPTED
    assert missing_artifact.published_artifact_id is None

    cancelling = transition_run(
        running,
        DetectRunStatus.CANCELLING,
        now="2026-10-28T08:00:02.000Z",
    )
    recovered_cancel = recover_run(
        cancelling,
        receipt=None,
        publication_valid=False,
        now="2026-10-28T08:00:07.000Z",
    )
    assert recovered_cancel.status is DetectRunStatus.CANCELLED

    invalid_completed = recover_run(
        completed,
        receipt=None,
        publication_valid=False,
        now="2026-10-28T08:00:08.000Z",
    )
    assert invalid_completed.status is DetectRunStatus.FAILED
    assert invalid_completed.published_artifact_id is None
