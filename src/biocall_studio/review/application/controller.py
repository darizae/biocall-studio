"""Qt-free orchestration for verified Review sessions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from biocall_studio.review.application.owner_lifetime import (
    ReviewOwnerLease,
    review_owner_alive,
)
from biocall_studio.review.application.storage import assess_review_export_storage
from biocall_studio.review.domain.exports import (
    ReviewExportHistoryRecord,
    ReviewExportMode,
    ReviewExportPlan,
    ReviewExportReceipt,
)
from biocall_studio.review.domain.sessions import (
    DEFAULT_PRESET_ID,
    ReviewLabel,
    SpectrogramSettingsSnapshot,
    propose_session_name,
)
from biocall_studio.review.domain.spectrograms import (
    SPECTROGRAM_ALGORITHM_VERSION,
    SPECTROGRAM_RENDER_VERSION,
    SpectrogramSettings,
)
from biocall_studio.review.persistence.export_history import ReviewExportHistoryStore
from biocall_studio.review.persistence.intake import (
    IntakeAvailability,
    ReviewIntakeStore,
    ReviewResultIntake,
)
from biocall_studio.review.persistence.sessions import (
    ReviewPosition,
    ReviewSession,
    ReviewSessionConflict,
    ReviewSessionStore,
    SessionMutation,
)
from biocall_studio.review.workflows.exports import (
    history_record_for_directory,
    plan_review_export,
    publish_review_export,
    verify_review_export_directory,
)
from biocall_studio.shared.storage import StorageEstimate, require_storage_admission


@dataclass(frozen=True, slots=True)
class ReviewExportOutcome:
    receipt: ReviewExportReceipt
    history_saved: bool
    message: str


class ReviewSessionController:
    """Own one process lease and coordinate Result validation with session writes."""

    def __init__(
        self,
        suite_data_root: Path,
        *,
        review_data_root: Path | None = None,
        intake: ReviewResultIntake | None = None,
        store: ReviewSessionStore | None = None,
        owner_lease: ReviewOwnerLease | None = None,
        export_history: ReviewExportHistoryStore | None = None,
    ):
        requested = Path(suite_data_root).expanduser()
        if requested.is_symlink():
            raise ValueError("Suite application-data root cannot be a symlink.")
        self.suite_data_root = requested.resolve(strict=False)
        selected_root = (
            self.suite_data_root / "review" / "v1"
            if review_data_root is None
            else Path(review_data_root).expanduser()
        )
        if selected_root.is_symlink():
            raise ValueError("Review application-data root cannot be a symlink.")
        self.review_data_root = selected_root.resolve(strict=False)
        self.intake = intake or ReviewResultIntake(
            self.suite_data_root,
            store=ReviewIntakeStore(self.review_data_root),
        )
        self.store = store or ReviewSessionStore(self.review_data_root)
        self.export_history = export_history or ReviewExportHistoryStore(self.store.root)
        self._owner_lease = owner_lease or ReviewOwnerLease.create(self.store.root)
        self._closed = False

    @property
    def owner_id(self) -> str:
        return self._owner_lease.owner_id

    def ensure_default_preset(
        self, settings: SpectrogramSettingsSnapshot, *, saved_at: str
    ) -> SpectrogramSettingsSnapshot:
        return self.store.ensure_default_preset(settings, saved_at=saved_at)

    def list_presets(self) -> tuple[SpectrogramSettingsSnapshot, ...]:
        return self.store.list_presets()

    def create_preset(
        self,
        *,
        name: str,
        effective_settings: object,
        saved_at: str,
    ) -> SpectrogramSettingsSnapshot:
        return self.store.create_preset(
            name=name,
            algorithm_version=SPECTROGRAM_ALGORITHM_VERSION,
            render_version=SPECTROGRAM_RENDER_VERSION,
            effective_settings=effective_settings,
            saved_at=saved_at,
        )

    def update_preset(
        self,
        preset_id: str,
        *,
        expected_revision: int,
        name: str,
        effective_settings: object,
        saved_at: str,
    ) -> SpectrogramSettingsSnapshot:
        return self.store.update_preset(
            preset_id,
            expected_revision=expected_revision,
            name=name,
            algorithm_version=SPECTROGRAM_ALGORITHM_VERSION,
            render_version=SPECTROGRAM_RENDER_VERSION,
            effective_settings=effective_settings,
            saved_at=saved_at,
        )

    def delete_preset(self, preset_id: str, *, expected_revision: int, deleted_at: str) -> None:
        self.store.delete_preset(
            preset_id,
            expected_revision=expected_revision,
            deleted_at=deleted_at,
        )

    def list_sessions(self) -> tuple[ReviewSession, ...]:
        return self.store.list_sessions()

    def delete_session(
        self,
        session_id: str,
        *,
        expected_revision: int,
        cancel_requested=None,
    ) -> ReviewSession:
        return self.store.delete_session(
            session_id,
            expected_revision=expected_revision,
            owner_id=self.owner_id,
            cancel_requested=cancel_requested,
        )

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
        if review_owner_alive(self.store.root, session.owner_id):
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

    def plan_export(
        self,
        session_id: str,
        *,
        source_root: Path,
        destination_parent: Path,
        mode: ReviewExportMode,
        export_id: str | None = None,
        created_at: str | None = None,
        cancel_requested: Callable[[], bool] | object | None = None,
    ) -> ReviewExportPlan:
        return plan_review_export(
            self.store,
            session_id,
            source_root=source_root,
            destination_parent=destination_parent,
            mode=mode,
            export_id=export_id,
            created_at=created_at,
            cancel_requested=cancel_requested,
        )

    def estimate_export_storage(
        self,
        plan: ReviewExportPlan,
        *,
        expected_input_digest: str | None = None,
    ) -> StorageEstimate:
        return assess_review_export_storage(
            plan,
            expected_input_digest=expected_input_digest,
        )

    def publish_export(
        self,
        plan: ReviewExportPlan,
        *,
        source_root: Path,
        storage_input_digest: str | None = None,
        confirm_storage: bool = False,
        cancel_requested: Callable[[], bool] | object | None = None,
        completed_at: str | None = None,
    ) -> ReviewExportOutcome:
        latest = self.estimate_export_storage(
            plan,
            expected_input_digest=storage_input_digest,
        )
        require_storage_admission(latest, confirmed=confirm_storage)
        receipt = publish_review_export(
            plan,
            self.store,
            source_root=source_root,
            cancel_requested=cancel_requested,
            completed_at=completed_at,
        )
        record = ReviewExportHistoryRecord.from_plan_receipt(plan, receipt)
        try:
            self.export_history.save(record)
        except (OSError, ValueError):
            return ReviewExportOutcome(
                receipt,
                False,
                (
                    "The verified export is safe, but its history entry could not be saved. "
                    "Reconnect this folder to history instead of exporting it again."
                ),
            )
        return ReviewExportOutcome(receipt, True, receipt.final_destination)

    def list_export_history(self) -> tuple[ReviewExportHistoryRecord, ...]:
        return self.export_history.load().records

    def recover_export_history(self, export_directory: Path) -> ReviewExportHistoryRecord:
        record = history_record_for_directory(Path(export_directory))
        self.export_history.save(record)
        return record

    def verify_export_history(self, record: ReviewExportHistoryRecord) -> ReviewExportReceipt:
        receipt = verify_review_export_directory(Path(record.final_destination))
        if (
            receipt.export_id != record.export_id
            or receipt.receipt_digest != record.receipt_digest
            or receipt.session_id != record.session_id
            or receipt.finalization_digest != record.finalization_digest
        ):
            raise ValueError("Saved export history no longer matches its verified receipt.")
        return receipt

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
        sort_name: str = "source_time",
        search_text: str = "",
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
            sort_name=sort_name,
            search_text=search_text,
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


def default_spectrogram_snapshot() -> SpectrogramSettingsSnapshot:
    return SpectrogramSettingsSnapshot.create(
        preset_id=DEFAULT_PRESET_ID,
        preset_name="Default",
        preset_revision=1,
        algorithm_version=SPECTROGRAM_ALGORITHM_VERSION,
        render_version=SPECTROGRAM_RENDER_VERSION,
        effective_settings=SpectrogramSettings().to_mapping(),
    )


__all__ = [
    "ReviewExportOutcome",
    "ReviewSessionController",
    "default_spectrogram_snapshot",
]
