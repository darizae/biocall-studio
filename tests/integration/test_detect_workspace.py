from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QPushButton

from biocall_studio.detect.application.controller import DetectWorkspaceController
from biocall_studio.detect.domain import RootBindingDecision
from biocall_studio.detect.gui.workspace import DetectWorkspacePage
from biocall_studio.detect.persistence import (
    DetectWorkspaceStore,
    WorkspaceMetadataError,
)
from biocall_studio.studio.application.app import create_application, default_suite_data_root
from biocall_studio.studio.application.storage import SuiteDataPaths

pytestmark = [pytest.mark.integration, pytest.mark.qt]


def _source_tree(path: Path) -> dict[Path, bytes]:
    recording = path / "recordings" / "dawn.wav"
    recording.parent.mkdir(parents=True)
    recording.write_bytes(b"source-recording-bytes")
    train_metadata = path / ".alpaca" / "collection.json"
    train_metadata.parent.mkdir()
    train_metadata.write_bytes(b"train-owned-metadata")
    return {
        recording: recording.read_bytes(),
        train_metadata: train_metadata.read_bytes(),
    }


def _assert_source_bytes(expected: dict[Path, bytes], old_root: Path, new_root: Path) -> None:
    for old_path, payload in expected.items():
        assert (new_root / old_path.relative_to(old_root)).read_bytes() == payload


def test_native_create_reopen_move_confirm_relink_cancel_and_denied_access(
    qapp, qtbot, tmp_path, monkeypatch
):
    """Case: IT-DET-001."""
    source = tmp_path / "Rainforest_2026"
    source_bytes = _source_tree(source)
    application_data = tmp_path / "application-data"
    controller = DetectWorkspaceController(application_data)
    page = DetectWorkspacePage(controller)
    qtbot.addWidget(page)
    page.resize(1180, 790)
    page.show()

    assert page.current_route == "setup"
    assert page.setup_button.isChecked()
    assert not page.recordings_button.isEnabled()
    page.folder_picker.folderChanged.emit(str(source))
    collection_id = controller.active_collection.ref.collection_id
    assert controller.root_decision is RootBindingDecision.VALID
    assert page.collection_title.text() == "Rainforest_2026"
    assert page.status_badge.text() == "Available"
    assert page.recordings_button.isEnabled()

    reopened = DetectWorkspaceController(application_data)
    assert reopened.active_collection.ref.collection_id == collection_id
    assert reopened.active_collection.source_root == source.resolve()

    moved = tmp_path / "Archive" / source.name
    moved.parent.mkdir()
    source.rename(moved)
    reopened.refresh()
    assert reopened.root_decision is RootBindingDecision.MISSING

    moved_page = DetectWorkspacePage(reopened)
    qtbot.addWidget(moved_page)
    moved_page.show()
    assert moved_page.current_route == "recordings"
    assert moved_page.recordings_button.isChecked()
    moved_page.relink_picker.folderChanged.emit(str(moved))
    assert reopened.proposal.decision is RootBindingDecision.AWAITING_CONFIRMATION
    assert moved_page.relink_card.isVisible()
    assert not moved_page.confirm_relink_button.isEnabled()
    qtbot.mouseClick(moved_page.relink_confirm, Qt.MouseButton.LeftButton)
    assert moved_page.confirm_relink_button.isEnabled()
    qtbot.mouseClick(moved_page.confirm_relink_button, Qt.MouseButton.LeftButton)
    assert reopened.root_decision is RootBindingDecision.VALID
    assert reopened.active_collection.source_root == moved.resolve()
    assert reopened.active_collection.ref.binding_revision == 2
    _assert_source_bytes(source_bytes, source, moved)

    moved_again = tmp_path / "Archive" / "Relocated_again"
    moved.rename(moved_again)
    reopened.refresh()
    moved_page.relink_picker.folderChanged.emit(str(moved_again))
    assert reopened.proposal is not None
    qtbot.mouseClick(moved_page.cancel_relink_button, Qt.MouseButton.LeftButton)
    assert reopened.proposal is None
    assert reopened.active_collection.source_root == moved.resolve()

    moved.mkdir()
    reopened.refresh()
    assert reopened.root_decision is RootBindingDecision.CHANGED

    before_cancel = reopened.active_collection
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    browse = next(
        button
        for button in moved_page.relink_picker.findChildren(QPushButton)
        if button.accessibleName() == "Choose Relink recordings folder"
    )
    qtbot.mouseClick(browse, Qt.MouseButton.LeftButton)
    assert reopened.active_collection == before_cancel

    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    moved_page.relink_picker.folderChanged.emit(str(unrelated))
    assert reopened.proposal.decision is RootBindingDecision.CHANGED
    assert moved_page.different_card.isVisible()
    assert reopened.active_collection == before_cancel
    qtbot.mouseClick(moved_page.cancel_different_button, Qt.MouseButton.LeftButton)

    denied = tmp_path / "denied"
    denied.mkdir()
    denied.chmod(0)
    try:
        moved_page.relink_picker.folderChanged.emit(str(denied))
        assert reopened.active_collection == before_cancel
        assert reopened.proposal is None
        assert "cannot be read" in moved_page.selection_error.text().lower()
    finally:
        denied.chmod(stat.S_IRWXU)
    moved.rmdir()
    _assert_source_bytes(source_bytes, source, moved_again)


def test_app_owned_atomic_metadata_recovery_containment_and_source_nonmutation(
    qapp, tmp_path, monkeypatch
):
    """Case: IT-DET-002."""
    source = tmp_path / "source"
    source_bytes = _source_tree(source)
    application_data = tmp_path / "application-data"
    store = DetectWorkspaceStore(application_data)
    collection = store.create_collection("Field source", source)
    paths = store.paths_for(collection.ref.collection_id)

    create_application()
    suite_paths = SuiteDataPaths.from_root(default_suite_data_root())
    assert suite_paths.root.name == "biocall-studio"
    assert suite_paths.train == suite_paths.root / "train" / "v1"
    assert suite_paths.detect == suite_paths.root / "detect" / "v1"
    assert paths.workspace_root == application_data / "detect" / "v1"
    assert paths.collection_directory.is_relative_to(paths.workspace_root)
    assert store.settings_path.parent == paths.workspace_root
    assert not store.settings_path.is_relative_to(paths.collection_directory)
    assert (source / ".alpaca" / "collection.json").read_bytes() == b"train-owned-metadata"
    assert stat.S_IMODE(paths.collection_directory.stat().st_mode) == 0o700
    assert {path.name for path in paths.collection_directory.iterdir() if path.is_dir()} == {
        "runs",
        "results",
        "exports",
        "inventories",
        ".last-good",
    }
    for path in (paths.public_manifest, paths.private_binding, paths.last_good_manifest):
        assert path.is_file() and not path.is_symlink()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert str(source.resolve()) not in paths.public_manifest.read_text(encoding="utf-8")

    interrupted = paths.collection_directory / ".collection.json.interrupted.tmp"
    interrupted.write_text("partial", encoding="utf-8")
    assert store.load_collection(collection.ref.collection_id) == collection

    paths.public_manifest.write_text("{", encoding="utf-8")
    with pytest.raises(WorkspaceMetadataError, match="corrupt"):
        store.load_collection(collection.ref.collection_id)
    assert store.load_last_good(collection.ref.collection_id) == collection
    assert paths.public_manifest.read_text(encoding="utf-8") == "{"

    second = store.create_collection("Second source", source)
    second_paths = store.paths_for(second.ref.collection_id)
    unsupported = json.loads(second_paths.public_manifest.read_text(encoding="utf-8"))
    unsupported["schema_version"] += 1
    second_paths.public_manifest.write_text(json.dumps(unsupported), encoding="utf-8")
    with pytest.raises(WorkspaceMetadataError, match="unsupported"):
        store.load_collection(second.ref.collection_id)
    assert store.load_last_good(second.ref.collection_id) == second

    third = store.create_collection("Atomic source", source)
    original_replace = os.replace

    def fail_manifest_replace(source_path, destination_path):
        if Path(destination_path).name == "collection.json":
            raise OSError("injected atomic publication failure")
        original_replace(source_path, destination_path)

    monkeypatch.setattr("biocall_studio.detect.persistence.os.replace", fail_manifest_replace)
    with pytest.raises(OSError, match="injected atomic"):
        store.rename_collection(third.ref.collection_id, "Must not publish")
    monkeypatch.setattr("biocall_studio.detect.persistence.os.replace", original_replace)
    assert store.load_collection(third.ref.collection_id).ref.display_label == "Atomic source"

    relocation_source = tmp_path / "relocation-source"
    relocation_bytes = _source_tree(relocation_source)
    relocation = store.create_collection("Relocation source", relocation_source)
    relocation_paths = store.paths_for(relocation.ref.collection_id)
    relocated = tmp_path / "relocated-source"
    relocation_source.rename(relocated)
    proposal = store.prepare_relink(relocation.ref.collection_id, relocated)

    def fail_relink_manifest(source_path, destination_path):
        if Path(destination_path) == relocation_paths.public_manifest:
            raise OSError("injected relink publication failure")
        original_replace(source_path, destination_path)

    monkeypatch.setattr("biocall_studio.detect.persistence.os.replace", fail_relink_manifest)
    with pytest.raises(OSError, match="injected relink"):
        store.confirm_relink(proposal)
    monkeypatch.setattr("biocall_studio.detect.persistence.os.replace", original_replace)
    assert store.load_collection(relocation.ref.collection_id) == relocation
    assert store.root_decision(relocation) is RootBindingDecision.MISSING
    _assert_source_bytes(relocation_bytes, relocation_source, relocated)

    escape_id = "det_ffffffffffffffffffffffffffffffff"
    outside = tmp_path / "outside"
    outside.mkdir()
    (paths.workspace_root / "collections" / escape_id).symlink_to(outside, target_is_directory=True)
    with pytest.raises(WorkspaceMetadataError, match="symlink"):
        store.load_collection(escape_id)
    with pytest.raises(ValueError):
        store.load_collection("../../outside")

    _assert_source_bytes(source_bytes, source, source)
