"""Qt-free orchestration for verified Review sessions."""

from __future__ import annotations

from pathlib import Path

from biocall_studio.review.application.owner_lifetime import (
    ReviewOwnerLease,
    review_owner_alive,
)
from biocall_studio.review.domain.sessions import (
    ReviewLabel,
    SpectrogramSettingsSnapshot,
    propose_session_name,
)
from biocall_studio.review.persistence.intake import (
    IntakeAvailability,
    ReviewResultIntake,
)
from biocall_studio.review.persistence.sessions import (
    ReviewPosition,
    ReviewSession,
    ReviewSessionConflict,
    ReviewSessionStore,
    SessionMutation,
)


class ReviewSessionController:
    """Own one process lease and coordinate Result validation with session writes."""

    def __init__(
        self,
        suite_data_root: Path,
        *,
        intake: ReviewResultIntake | None = None,
        store: ReviewSessionStore | None = None,
        owner_lease: ReviewOwnerLease | None = None,
    ):
        requested = Path(suite_data_root).expanduser()
        if requested.is_symlink():
            raise ValueError("Suite application-data root cannot be a symlink.")
        self.suite_data_root = requested.resolve(strict=False)
        self.intake = intake or ReviewResultIntake(self.suite_data_root)
        self.store = store or ReviewSessionStore(self.suite_data_root / "review" / "v1")
        self._owner_lease = owner_lease or ReviewOwnerLease.create(self.suite_data_root)
        self._closed = False

    @property
    def owner_id(self) -> str:
        return self._owner_lease.owner_id

    def ensure_default_preset(
        self, settings: SpectrogramSettingsSnapshot, *, saved_at: str
    ) -> SpectrogramSettingsSnapshot:
        return self.store.ensure_default_preset(settings, saved_at=saved_at)

    def start_session(
        self,
        collection_id: str,
        result_id: str,
        *,
        name: str | None,
        settings: SpectrogramSettingsSnapshot,
        created_at: str,
        session_id: str | None = None,
    ) -> ReviewSession:
        prepared = self.intake.prepare_session(collection_id, result_id)
        return self.store.create_session(
            name=name or propose_session_name(prepared.source.manifest.result_kind),
            source=prepared.source,
            candidates=prepared.candidates,
            settings=settings,
            owner_id=self.owner_id,
            created_at=created_at,
            session_id=session_id,
        )

    def recover_open_session(self, *, recovered_at: str) -> ReviewSession | None:
        session = self.store.open_session()
        if session is None or session.owner_id == self.owner_id:
            return session
        if session.owner_id is None:
            raise ReviewSessionConflict("Open Review session has invalid ownership.")
        if review_owner_alive(self.suite_data_root, session.owner_id):
            raise ReviewSessionConflict(
                "The Open Review session belongs to another running Studio instance."
            )
        return self.store.claim_orphaned_open_session(
            session.session_id,
            previous_owner_id=session.owner_id,
            owner_id=self.owner_id,
            expected_revision=session.revision,
            claimed_at=recovered_at,
        )

    def _validate_resume_source(self, session: ReviewSession) -> IntakeAvailability:
        source = self.store.load_source(session.session_id)
        inspection = self.intake.reopen(
            source.manifest.collection_id,
            source.manifest.result_id,
        )
        if inspection.availability not in {
            IntakeAvailability.READY,
            IntakeAvailability.RELINK_NEEDED,
        }:
            raise ReviewSessionConflict(inspection.message)
        return inspection.availability

    def resume_session(
        self, session_id: str, *, expected_revision: int, resumed_at: str
    ) -> tuple[ReviewSession, IntakeAvailability]:
        existing = self.store.get_session(session_id)
        availability = self._validate_resume_source(existing)
        resumed = self.store.resume_session(
            session_id,
            owner_id=self.owner_id,
            expected_revision=expected_revision,
            resumed_at=resumed_at,
        )
        return resumed, availability

    def close_session(
        self, session_id: str, *, expected_revision: int, closed_at: str
    ) -> ReviewSession:
        return self.store.close_session(
            session_id,
            owner_id=self.owner_id,
            expected_revision=expected_revision,
            closed_at=closed_at,
        )

    def set_label(
        self,
        session_id: str,
        candidate_id: str,
        label: ReviewLabel,
        *,
        expected_revision: int,
        modified_at: str,
    ) -> SessionMutation:
        return self.store.set_label(
            session_id,
            candidate_id,
            label,
            owner_id=self.owner_id,
            expected_revision=expected_revision,
            modified_at=modified_at,
        )

    def accept_all(
        self, session_id: str, *, expected_revision: int, modified_at: str
    ) -> SessionMutation:
        return self.store.accept_all(
            session_id,
            owner_id=self.owner_id,
            expected_revision=expected_revision,
            modified_at=modified_at,
        )

    def undo(self, session_id: str, *, expected_revision: int, modified_at: str) -> SessionMutation:
        return self.store.undo(
            session_id,
            owner_id=self.owner_id,
            expected_revision=expected_revision,
            modified_at=modified_at,
        )

    def redo(self, session_id: str, *, expected_revision: int, modified_at: str) -> SessionMutation:
        return self.store.redo(
            session_id,
            owner_id=self.owner_id,
            expected_revision=expected_revision,
            modified_at=modified_at,
        )

    def change_settings(
        self,
        session_id: str,
        settings: SpectrogramSettingsSnapshot,
        *,
        expected_revision: int,
        expected_settings_epoch: int,
        changed_at: str,
    ) -> ReviewSession:
        return self.store.change_settings(
            session_id,
            settings,
            owner_id=self.owner_id,
            expected_revision=expected_revision,
            expected_settings_epoch=expected_settings_epoch,
            changed_at=changed_at,
        )

    def rename_session(
        self,
        session_id: str,
        name: str,
        *,
        expected_revision: int,
        renamed_at: str,
    ) -> ReviewSession:
        return self.store.rename_session(
            session_id,
            name,
            owner_id=self.owner_id,
            expected_revision=expected_revision,
            renamed_at=renamed_at,
        )

    def finalize_session(
        self, session_id: str, *, expected_revision: int, finalized_at: str
    ) -> ReviewSession:
        return self.store.finalize_session(
            session_id,
            owner_id=self.owner_id,
            expected_revision=expected_revision,
            finalized_at=finalized_at,
        )

    def save_position(
        self,
        session_id: str,
        *,
        candidate_id: str | None,
        view: str,
        filter_name: str,
        scroll_offset: int,
        selected_candidate_ids: tuple[str, ...],
        expected_view_revision: int,
    ) -> ReviewPosition:
        return self.store.save_position(
            session_id,
            candidate_id=candidate_id,
            view=view,
            filter_name=filter_name,
            scroll_offset=scroll_offset,
            selected_candidate_ids=selected_candidate_ids,
            owner_id=self.owner_id,
            expected_view_revision=expected_view_revision,
        )

    def continue_in_new_session(
        self,
        parent_session_id: str,
        *,
        name: str,
        created_at: str,
        session_id: str | None = None,
    ) -> tuple[ReviewSession, IntakeAvailability]:
        parent = self.store.get_session(parent_session_id)
        availability = self._validate_resume_source(parent)
        child = self.store.continue_in_new_session(
            parent_session_id,
            name=name,
            owner_id=self.owner_id,
            created_at=created_at,
            session_id=session_id,
        )
        return child, availability

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._owner_lease.close()


__all__ = ["ReviewSessionController"]
