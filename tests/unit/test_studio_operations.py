from biocall_studio.studio.application.operations import (
    ExitAction,
    OwnedOperation,
    WorkflowOwner,
    decide_application_exit,
    decide_scientific_admission,
)


def test_cross_workspace_admission_and_exit_are_owned_and_visibility_independent():
    """Case: UT-STU-002."""
    train = OwnedOperation(
        owner=WorkflowOwner.TRAIN,
        run_id="run-train-1",
        label="CNN Training",
    )
    detect = OwnedOperation(
        owner=WorkflowOwner.DETECT,
        run_id="drun_detect_1",
        label="Candidate detection",
    )

    admitted = decide_scientific_admission(detect, ())
    assert admitted.allowed
    assert admitted.reason == ""

    blocked = decide_scientific_admission(detect, (train,))
    assert not blocked.allowed
    assert blocked.blocking_operation == train
    assert blocked.reason == (
        "CNN Training is active in Train. Stop it before starting Candidate detection in Detect."
    )

    duplicate = decide_scientific_admission(
        OwnedOperation(WorkflowOwner.DETECT, train.run_id, "Candidate detection"),
        (train,),
    )
    assert not duplicate.allowed
    assert duplicate.reason == "Run ID run-train-1 is already owned by Train."

    plan = decide_application_exit((train, detect))
    assert plan.action is ExitAction.CONFIRM_STOP
    assert plan.operations == (train, detect)
    assert plan.summary == "Active work: CNN Training in Train; Candidate detection in Detect."
    assert decide_application_exit(()).action is ExitAction.EXIT_NOW

    # Decisions are values only: evaluating exit/admission cannot mutate either workflow.
    assert train.owner is WorkflowOwner.TRAIN
    assert detect.owner is WorkflowOwner.DETECT


def test_open_review_exit_policy_combines_save_and_worker_ownership_without_mutation():
    """Case: UT-REVW-012."""
    review = OwnedOperation(
        owner=WorkflowOwner.REVIEW,
        run_id="review-generation-1",
        label="Spectrogram generation",
    )
    train = OwnedOperation(
        owner=WorkflowOwner.TRAIN,
        run_id="run-train-1",
        label="CNN Training",
    )

    without_worker = decide_application_exit((), review_session_open=True)
    assert without_worker.action is ExitAction.CONFIRM_SAVE_REVIEW
    assert without_worker.operations == ()
    assert without_worker.summary == "A Review session is still open. Save and exit?"

    combined = decide_application_exit((review, train), review_session_open=True)
    assert combined.action is ExitAction.CONFIRM_SAVE_REVIEW
    assert combined.operations == (review, train)
    assert combined.summary == "A Review session is still open. Save and exit?"

    blocked = decide_scientific_admission(train, (review,))
    assert not blocked.allowed
    assert blocked.blocking_operation == review
    assert blocked.reason == (
        "Spectrogram generation is active in Review. Stop it before starting CNN Training in Train."
    )

    # Pure decisions cannot save, stop, close, or otherwise mutate owned work.
    assert review.owner is WorkflowOwner.REVIEW
    assert train.owner is WorkflowOwner.TRAIN
