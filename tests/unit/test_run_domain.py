from dataclasses import replace

import pytest

from alpaca_desktop.domain.run import (
    RunConflictError,
    RunKind,
    RunReservation,
    RunStatus,
    RunTransitionError,
    assert_collection_rebind_allowed,
    assert_dataset_mutable,
    assert_run_start_allowed,
    new_run,
    reconcile_run,
    transition_run,
    update_run_progress,
)

NOW = "2026-10-25T08:00:00Z"
LATER = "2026-10-25T08:00:01Z"


def _run(*, kind: RunKind = RunKind.DATASET_BUILD, input_dataset_id: str | None = None):
    return new_run(
        run_id="run-001",
        request_id="request-001",
        kind=kind,
        title="Build · Dawn chorus",
        collection_id="collection-001",
        input_dataset_id=input_dataset_id,
        output_kind="dataset" if kind is RunKind.DATASET_BUILD else "model",
        output_id="dataset-001" if kind is RunKind.DATASET_BUILD else "model-001",
        stages=("Validate inputs", "Publish output"),
        now=NOW,
        training_family="cnn" if kind is RunKind.TRAINING else None,
    )


def test_single_active_run_transition_table_and_reservation_conflicts():
    """Case: UT-RUN-001."""
    created = _run()
    assert created.status is RunStatus.CREATED
    assert created.progress == 0

    starting = transition_run(created, RunStatus.STARTING, now=LATER)
    running = transition_run(starting, RunStatus.RUNNING, now=LATER)
    running = update_run_progress(
        running,
        progress=42,
        stage_index=1,
        message="Publishing output",
        now=LATER,
    )
    cancelling = transition_run(running, RunStatus.CANCELLING, now=LATER)
    cancelled = transition_run(cancelling, RunStatus.CANCELLED, now=LATER)
    assert cancelled.terminal
    assert cancelled.activity[-1] == "Publishing output"

    with pytest.raises(RunTransitionError, match="cancelled.*running"):
        transition_run(cancelled, RunStatus.RUNNING, now=LATER)
    with pytest.raises(RunTransitionError, match="monotonic"):
        update_run_progress(running, progress=20, stage_index=1, now=LATER)

    candidate = RunReservation(
        kind=RunKind.TRAINING,
        collection_id="collection-001",
        input_dataset_id="dataset-ready",
        output_kind="model",
        output_id="model-new",
    )
    with pytest.raises(RunConflictError, match="Only one Active Run"):
        assert_run_start_allowed((running,), candidate)
    with pytest.raises(RunConflictError, match="rebind.*Active Run"):
        assert_collection_rebind_allowed((running,), "collection-002")

    training = _run(kind=RunKind.TRAINING, input_dataset_id="dataset-ready")
    training = transition_run(training, RunStatus.STARTING, now=LATER)
    with pytest.raises(RunConflictError, match="reserved.*Active Run"):
        assert_dataset_mutable((training,), "dataset-ready")

    # Terminal Runs retain history but release their input reservations.
    failed = transition_run(training, RunStatus.FAILED, now=LATER, error="Worker failed")
    assert_run_start_allowed((failed,), candidate)
    assert_collection_rebind_allowed((failed,), "collection-002")
    assert_dataset_mutable((failed,), "dataset-ready")


def test_recovery_and_published_pointer_decisions_are_conservative():
    """Case: UT-RUN-002."""
    created = _run()
    created_orphan = reconcile_run(
        created,
        now=LATER,
        completion_receipt=False,
        published_output_valid=False,
    )
    assert created_orphan.status is RunStatus.INTERRUPTED

    running = transition_run(
        transition_run(_run(), RunStatus.STARTING, now=LATER),
        RunStatus.RUNNING,
        now=LATER,
    )

    interrupted = reconcile_run(
        running,
        now=LATER,
        completion_receipt=False,
        published_output_valid=False,
    )
    assert interrupted.status is RunStatus.INTERRUPTED
    assert interrupted.published_artifact_id is None

    recovered = reconcile_run(
        running,
        now=LATER,
        completion_receipt=True,
        published_output_valid=True,
    )
    assert recovered.status is RunStatus.COMPLETED
    assert recovered.published_artifact_id == running.output_id

    cancelling = transition_run(running, RunStatus.CANCELLING, now=LATER)
    cancelled = reconcile_run(
        cancelling,
        now=LATER,
        completion_receipt=False,
        published_output_valid=False,
    )
    assert cancelled.status is RunStatus.CANCELLED

    completed = transition_run(
        running,
        RunStatus.COMPLETED,
        now=LATER,
        published_artifact_id=running.output_id,
    )
    invalidated = reconcile_run(
        completed,
        now=LATER,
        completion_receipt=True,
        published_output_valid=False,
    )
    assert invalidated.status is RunStatus.FAILED
    assert invalidated.published_artifact_id is None
    assert "no longer validates" in invalidated.error

    # A completed flag may never acquire or retain an unrelated output pointer.
    with pytest.raises(RunTransitionError, match="prospective output"):
        transition_run(
            replace(running, output_id="dataset-expected"),
            RunStatus.COMPLETED,
            now=LATER,
            published_artifact_id="dataset-other",
        )
