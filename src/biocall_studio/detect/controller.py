"""Qt-facing Detect workspace application state; domain decisions remain elsewhere."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from biocall_studio.detect.domain import RootBindingDecision
from biocall_studio.detect.persistence import (
    DetectWorkspaceStore,
    PersistedDetectCollection,
    RootBindingProposal,
    WorkspaceMetadataError,
)


class DetectWorkspaceController(QObject):
    state_changed = Signal()

    def __init__(self, application_data_root: Path):
        super().__init__()
        self.store = DetectWorkspaceStore(application_data_root)
        self.active_collection: PersistedDetectCollection | None = None
        self.root_decision: RootBindingDecision | None = None
        self.proposal: RootBindingProposal | None = None
        self.selection_error = ""
        self.metadata_error = ""
        self.refresh(emit=False)

    def refresh(self, *, emit: bool = True) -> None:
        self.selection_error = ""
        self.metadata_error = ""
        self.proposal = None
        try:
            self.active_collection = self.store.load_active_collection()
            self.root_decision = (
                None
                if self.active_collection is None
                else self.store.root_decision(self.active_collection)
            )
        except WorkspaceMetadataError as exc:
            self.active_collection = None
            self.root_decision = None
            self.metadata_error = str(exc)
        if emit:
            self.state_changed.emit()

    def choose_source_root(self, value: str) -> None:
        if not value:
            return
        candidate = Path(value)
        self.selection_error = ""
        try:
            if self.active_collection is None:
                label = candidate.name.strip() or "Detect Collection"
                self.active_collection = self.store.create_collection(label, candidate)
                self.root_decision = RootBindingDecision.VALID
                self.proposal = None
            else:
                proposal = self.store.prepare_relink(
                    self.active_collection.ref.collection_id, candidate
                )
                if proposal.decision is RootBindingDecision.VALID:
                    self.proposal = None
                    self.root_decision = RootBindingDecision.VALID
                elif proposal.decision in {
                    RootBindingDecision.AWAITING_CONFIRMATION,
                    RootBindingDecision.CHANGED,
                }:
                    self.proposal = proposal
                elif proposal.decision is RootBindingDecision.MISSING:
                    self.proposal = None
                    self.selection_error = "The selected recordings folder is missing."
                else:
                    self.proposal = None
                    self.selection_error = "The selected recordings folder cannot be read."
        except (OSError, ValueError, WorkspaceMetadataError) as exc:
            self.proposal = None
            self.selection_error = str(exc)
        self.state_changed.emit()

    def cancel_relink(self) -> None:
        self.proposal = None
        self.selection_error = ""
        self.state_changed.emit()

    def confirm_relink(self) -> None:
        if self.proposal is None:
            return
        try:
            self.active_collection = self.store.confirm_relink(self.proposal)
            self.root_decision = RootBindingDecision.VALID
            self.proposal = None
            self.selection_error = ""
        except (OSError, ValueError, WorkspaceMetadataError) as exc:
            self.selection_error = str(exc)
        self.state_changed.emit()
    def create_new_collection(self) -> None:
        if self.proposal is None or self.proposal.decision is not RootBindingDecision.CHANGED:
            return
        candidate = self.proposal.candidate_root
        try:
            self.active_collection = self.store.create_collection(
                candidate.name.strip() or "Detect Collection", candidate
            )
            self.root_decision = RootBindingDecision.VALID
            self.proposal = None
            self.selection_error = ""
        except (OSError, ValueError, WorkspaceMetadataError) as exc:
            self.selection_error = str(exc)
        self.state_changed.emit()
