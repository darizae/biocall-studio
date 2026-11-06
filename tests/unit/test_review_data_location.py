from __future__ import annotations

import threading
from pathlib import Path

import pytest

from biocall_studio.review.application.controller import (
    ReviewSessionController,
    default_spectrogram_snapshot,
)
from biocall_studio.review.application.data_location import (
    ReviewDataLocationError,
    ReviewDataLocationManager,
)


def test_review_data_folder_move_is_versioned_atomic_and_restartable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Case: UT-REVW-014."""
    suite_root = tmp_path / "suite"
    manager = ReviewDataLocationManager(suite_root)
    source = suite_root / "review" / "v1"
    assert manager.current_root() == source
    assert not manager.preference_path.exists()

    controller = ReviewSessionController(suite_root, review_data_root=source)
    settings = default_spectrogram_snapshot()
    controller.ensure_default_preset(settings, saved_at="2026-11-06T10:00:00.000Z")
    controller.shutdown()
    database_before = (source / "sessions.sqlite3").read_bytes()

    target = tmp_path / "review-data"
    plan = manager.plan_move(target)
    assert plan.source_root == source
    assert plan.target_root == target
    assert plan.total_bytes >= len(database_before)
    assert plan.storage_estimate.can_start

    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(ReviewDataLocationError, match="cancelled"):
        manager.move(plan, cancel_requested=cancelled)
    assert manager.current_root() == source
    assert (source / "sessions.sqlite3").read_bytes() == database_before
    assert not target.exists()

    original_write = manager._write_preference
    monkeypatch.setattr(
        manager,
        "_write_preference",
        lambda _root: (_ for _ in ()).throw(OSError("injected preference failure")),
    )
    with pytest.raises(ReviewDataLocationError, match="original folder is unchanged"):
        manager.move(plan)
    assert manager.current_root() == source
    assert (source / "sessions.sqlite3").read_bytes() == database_before
    assert not target.exists()
    monkeypatch.setattr(manager, "_write_preference", original_write)

    manager.move(manager.plan_move(target))
    assert manager.current_root() == target
    assert not source.exists()
    reopened = ReviewSessionController(suite_root, review_data_root=manager.current_root())
    assert reopened.list_presets() == (settings,)
    reopened.shutdown()


def test_review_data_folder_rejects_symlinks_overlap_and_nonempty_destination(
    tmp_path: Path,
) -> None:
    """Case: UT-REVW-014."""
    suite_root = tmp_path / "suite"
    manager = ReviewDataLocationManager(suite_root)
    controller = ReviewSessionController(suite_root)
    controller.ensure_default_preset(
        default_spectrogram_snapshot(), saved_at="2026-11-06T10:00:00.000Z"
    )
    controller.shutdown()

    with pytest.raises(ReviewDataLocationError, match="Train or Detect"):
        manager.plan_move(suite_root / "detect" / "v1" / "review")

    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "linked-review"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ReviewDataLocationError, match="symbolic"):
        manager.plan_move(link)

    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "unrelated.txt").write_text("not Review data", encoding="utf-8")
    with pytest.raises(ReviewDataLocationError, match="already contains"):
        manager.plan_move(occupied)
