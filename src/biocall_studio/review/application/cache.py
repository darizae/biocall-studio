"""Guarded session/cache coordination without Qt or researcher-facing UI."""

from __future__ import annotations

from dataclasses import dataclass

from biocall_studio.review.application.controller import ReviewSessionController
from biocall_studio.review.application.generation import (
    GenerationToken,
    SpectrogramGenerationSupervisor,
)
from biocall_studio.review.application.storage import (
    ReviewCacheSizePlan,
    assess_review_cache_storage,
)
from biocall_studio.review.domain.sessions import SpectrogramSettingsSnapshot
from biocall_studio.review.persistence.sessions import ReviewSession
from biocall_studio.shared.storage import (
    CapacityObservation,
    StorageEstimate,
    require_storage_admission,
)


@dataclass(frozen=True, slots=True)
class SettingsChangeResult:
    session: ReviewSession
    storage_estimate: StorageEstimate


def session_token_is_current(
    controller: ReviewSessionController,
    token: GenerationToken,
) -> bool:
    """Reject late publication after a session epoch/settings transaction."""
    try:
        session = controller.store.get_session(token.session_id)
        settings = controller.store.load_settings(token.session_id)
    except (KeyError, OSError, ValueError):
        return False
    return (
        session.settings_epoch == token.settings_epoch
        and settings.settings_digest == token.settings_digest
    )


def change_session_settings_with_preflight(
    controller: ReviewSessionController,
    supervisor: SpectrogramGenerationSupervisor,
    session_id: str,
    settings: SpectrogramSettingsSnapshot,
    size_plan: ReviewCacheSizePlan,
    *,
    expected_revision: int,
    expected_settings_epoch: int,
    changed_at: str,
    confirmed_change: bool,
    confirmed_storage: bool = False,
    capacity: CapacityObservation | None = None,
) -> SettingsChangeResult:
    """Recheck capacity, commit one settings epoch, then stale old work.

    The UI-owned confirmation copy is intentionally outside this Qt-free seam.
    A failed recheck or session transaction leaves the old epoch and workers
    untouched. Cache objects are global/content-addressed and are never deleted.
    """
    if not isinstance(controller, ReviewSessionController) or not isinstance(
        supervisor, SpectrogramGenerationSupervisor
    ):
        raise TypeError("Review settings coordinator dependencies are invalid.")
    if not confirmed_change:
        raise ValueError("Changing session spectrogram settings requires confirmation.")
    if settings.settings_digest != size_plan.settings_digest:
        raise ValueError("Storage plan does not match the selected spectrogram settings.")
    assessment = assess_review_cache_storage(
        size_plan,
        cache_root=supervisor.cache.root,
        capacity=capacity,
        expected_input_digest=size_plan.input_digest,
    )
    require_storage_admission(assessment, confirmed=confirmed_storage)
    changed = controller.change_settings(
        session_id,
        settings,
        expected_revision=expected_revision,
        expected_settings_epoch=expected_settings_epoch,
        changed_at=changed_at,
    )
    supervisor.invalidate_session_epoch(session_id, expected_settings_epoch)
    return SettingsChangeResult(changed, assessment)


__all__ = [
    "SettingsChangeResult",
    "change_session_settings_with_preflight",
    "session_token_is_current",
]
