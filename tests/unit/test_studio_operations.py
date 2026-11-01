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
