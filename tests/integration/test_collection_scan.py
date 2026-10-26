from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest
from alp_ui.components import Alert, Card, DataTable, HelpHint, ProgressBar, Text
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QBoxLayout, QMessageBox

from biocall_studio_train.application.collection_scan import (
    inputs_match_scan,
    scan_collection,
)
from biocall_studio_train.application.workspace import WorkspaceController
from biocall_studio_train.domain.collection import ScanResult
from biocall_studio_train.gui.collection import PagedRecordingModel
from biocall_studio_train.gui.window import MainWindow
from biocall_studio_train.persistence.collection_metadata import (
    load_collection_metadata,
    publish_collection_metadata,
)

pytestmark = [pytest.mark.integration]


def _wait_for_scan(qtbot, controller: WorkspaceController) -> ScanResult:
    qtbot.waitUntil(lambda: controller.scan_result is not None or bool(controller.error_message))
    assert not controller.error_message
    assert controller.scan_result is not None
    return controller.scan_result


@pytest.mark.qt
def test_real_folder_scan_is_nonblocking_and_renders_progress_and_mapping(
    qapp, qtbot, tmp_path, collection_factory
):
    """Case: IT-COL-001."""
    root = collection_factory(tmp_path / "Wetland-dusk")
    controller = WorkspaceController(tmp_path / "settings", scan_step_delay_seconds=0.03)
    window = MainWindow(controller)
    qtbot.addWidget(window)
    window.show()

    window.select_page.folder_picker.setFolderPath(str(root))
    qtbot.waitUntil(lambda: window.current_route == "scan")
    assert window.scan_page.findChild(ProgressBar).isVisible()
    assert window.scan_page.cancel_button.isEnabled()
    assert window.scan_page.narrow.width() >= 700
    result = _wait_for_scan(qtbot, controller)

    assert window.current_route == "collection"
    assert result.valid
    assert result.recording_count == 2
    assert result.positive_count == 2
    assert result.duration_seconds == 4.0
    assert [record.positive_count for record in result.records] == [1, 1]
    assert window.collection_page.recording_model.rowCount() == 2
    assert (
        window.collection_page.recording_model.data(
            window.collection_page.recording_model.index(0, 2)
        )
        == 1
    )


def test_invalid_inputs_report_relative_paths_corrections_and_never_mutate_sources(
    tmp_path, collection_factory, wav_factory
):
    """Case: IT-COL-002."""
    root = collection_factory(tmp_path / "Broken", source_count=1)
    source = root / "recordings" / "REC_A.wav"
    before = source.read_bytes()
    (root / "positives" / "notes.mp3").write_bytes(b"not audio")
    (root / "positives" / "nested").mkdir()
    (root / "positives" / "nested" / "clip.wav").write_bytes(b"nested")
    wav_named_folder = root / "positives" / "REC_A__start-00000ms__end-00500ms__folder.wav"
    wav_named_folder.mkdir()
    (root / "positives" / "REC_A__call2.wav").write_bytes(b"bad header")
    wav_factory(
        root / "positives" / "UNKNOWN__start-00000ms__end-00500ms__call.wav",
        frames=8_000,
    )
    wav_factory(
        root / "positives" / "REC_A__start-00500ms__end-01000ms__duplicate.wav",
        frames=8_000,
    )
    wav_factory(
        root / "positives" / "REC_A__start-01500ms__end-02500ms__outside.wav",
        frames=16_000,
    )
    wav_factory(
        root / "positives" / "REC_A__start-01000ms__end-01500ms__wrong-length.wav",
        frames=4_000,
    )
    wav_factory(
        root / "positives" / "REC_A__start-01000ms__end-01000ms__empty-span.wav",
        frames=1,
    )
    wav_factory(
        root / "positives" / "REC_A__start-00000ms__end-9223372036854775808ms__overflow.wav",
        frames=8_000,
    )
    unsupported = wav_factory(root / "recordings" / "UNSUPPORTED.wav", frames=16_000)
    unsupported_bytes = bytearray(unsupported.read_bytes())
    unsupported_bytes[20:22] = (3).to_bytes(2, "little")
    unsupported.write_bytes(unsupported_bytes)

    result = scan_collection(root)
    issues = {(issue.code, issue.relative_path): issue.correction for issue in result.issues}
    issue_messages = {(issue.code, issue.relative_path): issue.message for issue in result.issues}
    assert ("unexpected_entry", "positives/nested") in issues
    assert ("unexpected_entry", wav_named_folder.relative_to(root).as_posix()) in issues
    assert ("unsupported_file", "positives/notes.mp3") in issues
    assert ("malformed_positive_name", "positives/REC_A__call2.wav") in issues
    assert (
        issue_messages[("malformed_positive_name", "positives/REC_A__call2.wav")]
        == "Positive has no timestamps."
    )
    assert ("invalid_wav", "positives/REC_A__call2.wav") in issues
    assert ("invalid_wav", "recordings/UNSUPPORTED.wav") in issues
    assert (
        "unknown_source",
        "positives/UNKNOWN__start-00000ms__end-00500ms__call.wav",
    ) in issues
    assert (
        "duplicate_interval",
        "positives/REC_A__start-00500ms__end-01000ms__duplicate.wav",
    ) in issues
    assert (
        "interval_out_of_bounds",
        "positives/REC_A__start-01500ms__end-02500ms__outside.wav",
    ) in issues
    assert (
        "duration_mismatch",
        "positives/REC_A__start-01000ms__end-01500ms__wrong-length.wav",
    ) in issues
    assert (
        "invalid_interval",
        "positives/REC_A__start-01000ms__end-01000ms__empty-span.wav",
    ) in issues
    assert (
        "malformed_positive_name",
        "positives/REC_A__start-00000ms__end-9223372036854775808ms__overflow.wav",
    ) in issues
    assert all(correction for correction in issues.values())
    assert wav_named_folder.relative_to(root).as_posix() not in {
        positive.relative_path for positive in result.positives
    }
    assert not result.valid
    assert source.read_bytes() == before
    assert not (root / ".alpaca").exists()

    missing = tmp_path / "MissingFolders"
    missing.mkdir()
    missing_result = scan_collection(missing)
    assert {(issue.code, issue.relative_path) for issue in missing_result.issues} >= {
        ("missing_folder", "recordings/"),
        ("missing_folder", "positives/"),
    }


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX special-file coverage")
def test_special_input_file_is_rejected_without_opening_it(tmp_path, collection_factory):
    """Case: IT-COL-002."""
    root = collection_factory(tmp_path / "SpecialInput", source_count=1)
    special_path = root / "positives" / "fifo.wav"
    os.mkfifo(special_path)

    result = scan_collection(root)

    assert any(
        issue.code == "unexpected_entry"
        and issue.relative_path == special_path.relative_to(root).as_posix()
        for issue in result.issues
    )
    assert special_path.relative_to(root).as_posix() not in {
        positive.relative_path for positive in result.positives
    }


@pytest.mark.qt
def test_valid_metadata_publishes_partitions_and_reopens_with_identical_facts(
    qapp, qtbot, tmp_path, collection_factory
):
    """Case: IT-COL-003."""
    root = collection_factory(tmp_path / "Reopen")
    before = {path: path.read_bytes() for path in root.glob("*/*.wav")}
    published = publish_collection_metadata(root, scan_collection(root))
    reopened = load_collection_metadata(root)

    assert (root / ".alpaca" / "collection.json").is_file()
    assert reopened.collection_id == published.collection_id
    assert reopened.records == published.records
    assert reopened.positives == published.positives
    assert all("/" in path for path in reopened.relative_paths)
    assert all(not Path(path).is_absolute() for path in reopened.relative_paths)
    assert {path: path.read_bytes() for path in root.glob("*/*.wav")} == before

    settings = tmp_path / "settings"
    first_controller = WorkspaceController(settings)
    first_controller.bind_verified_collection(root, published.collection_id)
    reopened_controller = WorkspaceController(settings)
    window = MainWindow(reopened_controller)
    qtbot.addWidget(window)
    window.show()
    reopened_from_controller = _wait_for_scan(qtbot, reopened_controller)
    assert reopened_from_controller.collection_id == published.collection_id
    assert reopened_from_controller.header_reads == 0
    assert reopened_from_controller.records == published.records

    manifest = json.loads((root / ".alpaca" / "collection.json").read_text())
    record_partition = root / ".alpaca" / manifest["record_partitions"][0]
    rows = record_partition.read_text()
    corrupted_rows = rows.replace('"positive_count":1', '"positive_count":0')
    assert corrupted_rows != rows
    record_partition.write_text(corrupted_rows)
    with pytest.raises(ValueError, match="Invalid Collection metadata"):
        load_collection_metadata(root)
    rebuilt = publish_collection_metadata(root, scan_collection(root))
    assert rebuilt.collection_id == published.collection_id
    assert rebuilt.header_reads == 4


def test_cache_refresh_reads_only_changed_headers_and_removed_entries_disappear(
    tmp_path, collection_factory, wav_factory
):
    """Case: IT-COL-004."""
    root = collection_factory(tmp_path / "Refresh")
    first = publish_collection_metadata(root, scan_collection(root))
    assert first.header_reads == 4
    positive = root / "positives" / "REC_A__start-00500ms__end-01000ms__call1.wav"
    wav_factory(positive, frames=8_000)
    os.utime(positive, ns=(positive.stat().st_atime_ns, positive.stat().st_mtime_ns + 1_000_000))
    refreshed = scan_collection(root, cached=load_collection_metadata(root))
    assert refreshed.header_reads == 1

    removed = root / "positives" / "REC_B__start-00500ms__end-01000ms__call2.wav"
    removed.unlink()
    assert not inputs_match_scan(root, refreshed)
    after_remove = scan_collection(root, cached=refreshed)
    assert after_remove.header_reads == 0
    removed_relative = "positives/REC_B__start-00500ms__end-01000ms__call2.wav"
    assert removed_relative not in after_remove.relative_paths

    source_b = root / "recordings" / "REC_B.wav"
    source_b.unlink()
    assert not inputs_match_scan(root, after_remove)
    after_source_remove = scan_collection(root, cached=after_remove)
    assert after_source_remove.header_reads == 0
    assert "recordings/REC_B.wav" not in after_source_remove.relative_paths

    added = wav_factory(root / "recordings" / "REC_C.wav", frames=32_000)
    assert not inputs_match_scan(root, after_source_remove)
    after_add = scan_collection(root, cached=after_source_remove)
    assert after_add.header_reads == 1
    assert added.relative_to(root).as_posix() in after_add.relative_paths

    source_a = root / "recordings" / "REC_A.wav"
    source_stat = source_a.stat()
    wav_factory(source_a, frames=32_000)
    os.utime(source_a, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns + 1_000_000))
    assert not inputs_match_scan(root, after_add)
    after_recording_change = scan_collection(root, cached=after_add)
    assert after_recording_change.header_reads == 1

    # Cheap size+mtime freshness is intentionally not proof of byte identity.
    original_stat = positive.stat()
    payload = bytearray(positive.read_bytes())
    payload[-1] ^= 1
    positive.write_bytes(payload)
    os.utime(positive, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    assert inputs_match_scan(root, after_recording_change)


@pytest.mark.qt
def test_cancel_and_interrupted_publication_keep_old_cache_valid_and_inputs_unchanged(
    qapp, qtbot, tmp_path, collection_factory, monkeypatch
):
    """Case: IT-COL-005."""
    root = collection_factory(tmp_path / "Cancel", source_count=3)
    before = {path: path.read_bytes() for path in root.glob("*/*.wav")}
    old = publish_collection_metadata(root, scan_collection(root))
    old_manifest = (root / ".alpaca" / "collection.json").read_bytes()

    controller = WorkspaceController(tmp_path / "settings", scan_step_delay_seconds=0.04)
    cancelled = []
    controller.scan_cancelled.connect(lambda: cancelled.append(True))
    controller.request_collection(str(root))
    qtbot.waitUntil(lambda: controller.is_scanning)
    controller.cancel_scan()
    qtbot.waitUntil(lambda: bool(cancelled))
    assert controller.scan_result is None
    assert (root / ".alpaca" / "collection.json").read_bytes() == old_manifest

    real_replace = os.replace

    def fail_manifest(source, target):
        if Path(target).name == "collection.json":
            raise PermissionError("injected manifest replacement failure")
        return real_replace(source, target)

    monkeypatch.setattr(os, "replace", fail_manifest)
    with pytest.raises(PermissionError, match="injected"):
        publish_collection_metadata(root, replace(old, scanned_at="2026-10-25T11:00:00+00:00"))
    assert (root / ".alpaca" / "collection.json").read_bytes() == old_manifest
    assert {path: path.read_bytes() for path in root.glob("*/*.wav")} == before

    monkeypatch.undo()
    recovered = publish_collection_metadata(
        root, replace(old, scanned_at="2026-10-25T12:00:00+00:00")
    )
    assert load_collection_metadata(root).collection_id == recovered.collection_id


def test_stale_scan_cannot_publish_a_valid_cache(tmp_path, collection_factory):
    """Case: IT-COL-005."""
    root = collection_factory(tmp_path / "ChangedDuringPublication", source_count=1)
    result = scan_collection(root)
    source = root / "recordings" / "REC_A.wav"
    source.write_bytes(source.read_bytes() + b"changed")

    with pytest.raises(ValueError, match="changed after the Collection Scan"):
        publish_collection_metadata(root, result)

    assert not (root / ".alpaca" / "collection.json").exists()


@pytest.mark.qt
def test_new_folder_choice_replaces_an_active_scan(qapp, qtbot, tmp_path, collection_factory):
    """Case: IT-COL-005."""
    first = collection_factory(tmp_path / "FirstChoice", source_count=3)
    second = collection_factory(tmp_path / "SecondChoice", source_count=1)
    controller = WorkspaceController(tmp_path / "settings", scan_step_delay_seconds=0.04)

    controller.request_collection(str(first))
    qtbot.waitUntil(lambda: controller.is_scanning)
    controller.request_collection(str(second))
    qtbot.waitUntil(
        lambda: (
            controller.scan_result is not None
            and controller.collection_path == second.resolve()
            and not controller.is_scanning
        )
    )

    assert controller.scan_result.root_name == second.name
    assert controller.scan_result.recording_count == 1
    qtbot.waitUntil(lambda: controller._scan_thread is None)


def test_symlink_escape_and_wrong_collection_identity_cannot_rebind(
    qapp, tmp_path, collection_factory
):
    """Case: IT-COL-006."""
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"outside")
    escaped = collection_factory(tmp_path / "Escaped", source_count=1)
    (escaped / "recordings" / "escape.wav").symlink_to(outside)
    result = scan_collection(escaped)
    assert any(
        issue.code == "symlink_escape" and issue.relative_path == "recordings/escape.wav"
        for issue in result.issues
    )
    cached_root = collection_factory(tmp_path / "CachedEscape", source_count=1)
    cached = publish_collection_metadata(cached_root, scan_collection(cached_root))
    cached_source = cached_root / "recordings" / "REC_A.wav"
    cached_source.unlink()
    cached_source.symlink_to(outside)
    cached_escape = scan_collection(cached_root, cached=cached)
    assert any(
        issue.code == "symlink_escape" and issue.relative_path == "recordings/REC_A.wav"
        for issue in cached_escape.issues
    )
    assert all(record.relative_path != "recordings/REC_A.wav" for record in cached_escape.records)
    outside_folder = tmp_path / "outside-recordings"
    outside_folder.mkdir()
    escaped_folder = tmp_path / "EscapedFolder"
    escaped_folder.mkdir()
    (escaped_folder / "positives").mkdir()
    (escaped_folder / "recordings").symlink_to(outside_folder, target_is_directory=True)
    folder_result = scan_collection(escaped_folder)
    assert any(
        issue.code == "symlink_escape" and issue.relative_path == "recordings/"
        for issue in folder_result.issues
    )

    metadata_escape = collection_factory(tmp_path / "MetadataEscape", source_count=1)
    outside_metadata = tmp_path / "outside-metadata"
    outside_metadata.mkdir()
    (metadata_escape / ".alpaca").symlink_to(outside_metadata, target_is_directory=True)
    with pytest.raises(ValueError, match="cannot be a symlink"):
        publish_collection_metadata(metadata_escape, scan_collection(metadata_escape))
    assert list(outside_metadata.iterdir()) == []

    first_root = collection_factory(tmp_path / "First", source_count=1)
    second_root = collection_factory(tmp_path / "Second", source_count=1)
    first = publish_collection_metadata(first_root, scan_collection(first_root))
    second = publish_collection_metadata(second_root, scan_collection(second_root))
    controller = WorkspaceController(tmp_path / "settings")
    controller.bind_verified_collection(first_root, first.collection_id)
    with pytest.raises(ValueError, match="identity"):
        controller.bind_verified_collection(second_root, first.collection_id)
    assert second.collection_id != first.collection_id
    assert controller.collection_path == first_root
    moved_root = tmp_path / "MovedFirst"
    first_root.rename(moved_root)
    assert any(issue.code == "missing_collection" for issue in scan_collection(first_root).issues)
    controller.bind_verified_collection(moved_root, first.collection_id)
    assert controller.collection_path == moved_root.resolve()


@pytest.mark.qt
def test_large_metadata_partitions_and_live_qt_window_stay_responsive(
    qapp, tmp_path, qtbot, wav_factory
):
    """Case: IT-COL-007."""
    root = tmp_path / "Large"
    recordings = root / "recordings"
    positives = root / "positives"
    recordings.mkdir(parents=True)
    positives.mkdir()
    template_path = wav_factory(tmp_path / "one-frame.wav", frames=1, rate=1_000)
    template = template_path.read_bytes()
    for index in range(10_001):
        (recordings / f"REC_{index:05d}.wav").write_bytes(template)
    (positives / "REC_00000__start-0ms__end-1ms__call.wav").write_bytes(template)

    result = scan_collection(root)
    assert result.valid
    assert result.header_reads == 10_002
    published = publish_collection_metadata(root, result)
    manifest = json.loads((root / ".alpaca" / "collection.json").read_text())
    assert len(manifest["record_partitions"]) == 2
    assert published.recording_count == 10_001

    controller = WorkspaceController(tmp_path / "settings")
    window = MainWindow(controller)
    qtbot.addWidget(window)
    window.show()
    window.collection_page.set_result(published)
    window.navigate("collection")
    model = window.collection_page.recording_model
    assert isinstance(model, PagedRecordingModel)
    assert window.collection_page.recordings_table.isVisible()
    assert model.rowCount() == 200
    assert model.canFetchMore()

    sentinel_ticks = []
    sentinel = QTimer(window)
    sentinel.setInterval(0)
    sentinel.timeout.connect(lambda: sentinel_ticks.append(model.rowCount()))
    sentinel.start()
    model.fetchMore()
    assert model.rowCount() == 400
    pages = 2
    while model.canFetchMore():
        before_page = model.rowCount()
        model.fetchMore()
        assert 0 < model.rowCount() - before_page <= 200
        pages += 1
        qapp.processEvents()
        if pages == 10:
            window.navigate("wiki")
            assert window.current_route == "wiki"
            window.navigate("collection")
            assert window.current_route == "collection"
    sentinel.stop()
    assert model.rowCount() == 10_001
    assert pages == 51
    assert len(sentinel_ticks) >= pages - 2

    filtered = window.collection_page.recording_filter_model
    filtered.setFilterFixedString("REC_09999")
    qapp.processEvents()
    assert filtered.rowCount() == 1
    assert filtered.index(0, 0).data() == "REC_09999.wav"
    filtered.setFilterFixedString("")
    assert filtered.rowCount() == 10_001
    assert published.header_reads == 10_002


@pytest.mark.qt
def test_collection_ui_repair_rescan_cta_focus_and_narrow_layout(
    qapp, qtbot, tmp_path, collection_factory, monkeypatch
):
    """Cases: IT-COL-008, IT-UI-005."""
    root = collection_factory(tmp_path / "Repair", source_count=1)
    positive = root / "positives" / "REC_A__start-00500ms__end-01000ms__call1.wav"
    broken = positive.with_name("REC_A__call1.wav")
    positive.rename(broken)
    controller = WorkspaceController(tmp_path / "settings")
    window = MainWindow(controller)
    qtbot.addWidget(window)
    window.show()
    window.select_page.folder_picker.setFolderPath(str(root))
    invalid = _wait_for_scan(qtbot, controller)

    assert not invalid.valid
    assert window.current_route == "collection"
    assert window.collection_page.build_button.isEnabled() is False
    assert window.collection_page.rescan_button.isVisible()
    assert isinstance(window.collection_page.summary_cards[0], Card)
    assert isinstance(window.collection_page.status_alert, Alert)
    assert isinstance(window.collection_page.recordings_table, DataTable)
    page_text = {label.text() for label in window.collection_page.findChildren(Text)}
    assert {
        "COLLECTION",
        root.name,
        "Recordings",
        "Validation details",
        "Folder",
    } <= page_text
    assert "Fast reopening" not in page_text
    matching_titles = [
        label for label in window.collection_page.findChildren(Text) if label.text() == root.name
    ]
    assert len(matching_titles) == 1
    assert window._navigation["collections"].isChecked()
    assert window._navigation["collections"].accessibleDescription() == "Current page"
    hints = window.collection_page.findChildren(HelpHint)
    assert {hint.accessibleName() for hint in hints} >= {
        "More about Source and positive mapping",
        "More about Collection storage",
    }
    hints[0].setFocus()
    qtbot.keyClick(hints[0], Qt.Key.Key_Space)
    assert hints[0].accessibleDescription()
    assert "positives/REC_A__call1.wav" in window.collection_page.issue_model.data(
        window.collection_page.issue_model.index(0, 1)
    )
    window.collection_page.rescan_button.setFocus()
    qtbot.keyClick(window.collection_page.rescan_button, Qt.Key.Key_Space)
    qtbot.waitUntil(lambda: controller.is_scanning)
    controller.cancel_scan()
    qtbot.waitUntil(lambda: not controller.is_scanning)
    assert window.current_route == "select"
    assert window.select_page.retry_scan_button.isVisible()

    broken.rename(positive)
    window.select_page.retry_scan_button.click()
    qtbot.waitUntil(lambda: controller.scan_result is not None and controller.scan_result.valid)
    assert window.collection_page.build_button.isEnabled()
    assert controller.collection_path == root.resolve()
    window.collection_page.build_button.click()
    assert window.current_route == "builder"
    assert window.builder_page.source_model.selected_count == 1

    window.resize(700, 780)
    window.navigate("collections")
    qtbot.waitUntil(lambda: window.is_compact and window.collection_page.is_compact)
    assert window.collection_page.header_layout.direction() == QBoxLayout.Direction.TopToBottom
    assert window.collection_page.content_layout.direction() == QBoxLayout.Direction.TopToBottom
    assert window.collection_page.build_button.focusPolicy() != Qt.FocusPolicy.NoFocus
    source_bytes = {path: path.read_bytes() for path in root.glob("*/*.wav")}
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    window.collection_page.unbind_button.click()
    assert window.current_route == "select"
    assert controller.collection_path is None
    assert {path: path.read_bytes() for path in source_bytes} == source_bytes
