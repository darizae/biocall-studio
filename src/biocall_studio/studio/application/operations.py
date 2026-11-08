"""Pure whole-Studio scientific admission and application-exit decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkflowOwner(StrEnum):
    TRAIN = "Train"
    DETECT = "Detect"
    REVIEW = "Review"


@dataclass(frozen=True, slots=True)
class OwnedOperation:
    owner: WorkflowOwner
    run_id: str
    label: str

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("An owned operation requires a Run ID.")
        if not self.label.strip():
            raise ValueError("An owned operation requires a label.")


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    allowed: bool
    reason: str = ""
    blocking_operation: OwnedOperation | None = None


class ExitAction(StrEnum):
    EXIT_NOW = "exit_now"
    CONFIRM_STOP = "confirm_stop"
    CONFIRM_SAVE_REVIEW = "confirm_save_review"


@dataclass(frozen=True, slots=True)
class ExitDecision:
    action: ExitAction
    operations: tuple[OwnedOperation, ...]
    summary: str


def decide_scientific_admission(
    requested: OwnedOperation,
    active_operations: tuple[OwnedOperation, ...],
) -> AdmissionDecision:
    """Admit one scientific worker globally without taking workflow ownership."""
    for active in active_operations:
        if active.run_id == requested.run_id:
            return AdmissionDecision(
                False,
                f"Run ID {requested.run_id} is already owned by {active.owner.value}.",
                active,
            )
    if active_operations:
        active = active_operations[0]
        return AdmissionDecision(
            False,
            f"{active.label} is active in {active.owner.value}. Stop it before starting "
            f"{requested.label} in {requested.owner.value}.",
            active,
        )
    return AdmissionDecision(True)


def decide_application_exit(
    active_operations: tuple[OwnedOperation, ...],
    *,
    review_session_open: bool = False,
) -> ExitDecision:
    """Require one confirmation for all explicitly owned active scientific work."""
    operations = tuple(active_operations)
    if review_session_open:
        return ExitDecision(
            ExitAction.CONFIRM_SAVE_REVIEW,
            operations,
            "A Review session is still open. Save and exit?",
        )
    if not operations:
        return ExitDecision(ExitAction.EXIT_NOW, (), "")
    summary = (
        "Active work: "
        + "; ".join(f"{operation.label} in {operation.owner.value}" for operation in operations)
        + "."
    )
    return ExitDecision(ExitAction.CONFIRM_STOP, operations, summary)
