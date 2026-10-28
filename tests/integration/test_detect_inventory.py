from __future__ import annotations

import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread

import pytest
from alp_ui.components import DataTable, HelpHint
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QPushButton

from biocall_studio.detect.controller import DetectWorkspaceController
from biocall_studio.detect.discovery import (
    InventoryScanCancelled,
    InventoryScanProgress,
    discover_wavs,
)
from biocall_studio.detect.inventory import (
    ChangeKind,
    InclusionDecision,
    RecordingStatus,
)
from biocall_studio.detect.persistence import DetectWorkspaceStore
from biocall_studio.gui.detect import DetectWorkspacePage, InventoryTableModel

pytestmark = [pytest.mark.integration]


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def test_recursive_real_wav_discovery_policy_conflicts_and_read_only_publication(
    tmp_path, wav_factory
):
    """Case: IT-DET-003."""
    source = tmp_path / "Rainforest_2026"
    mono = wav_factory(source / "recordings" / "dawn" / "mono.wav", frames=1_600)
    stereo = wav_factory(
        source / "recordings" / "night" / "stereo.WAV",
        frames=4_800,
        rate=48_000,
        channels=2,
    )
    wav_factory(source / "positives" / "call.wav", frames=800)
    wav_factory(
        source / ".alpaca" / "datasets" / "dataset-1" / "snippets" / "call.wav",
        frames=400,
    )
    wav_factory(source / "incoming" / "unknown.wav", frames=200)
    hardlink = source / "recordings" / "night" / "stereo-hardlink.wav"
    os.link(stereo, hardlink)
    outside = wav_factory(tmp_path / "outside.wav", frames=200)
    (source / "escape.wav").symlink_to(outside)
    (source / "recordings" / "loop").symlink_to(source / "recordings", target_is_directory=True)
    before = _tree_bytes(source)

    store = DetectWorkspaceStore(tmp_path / "application-data")
    collection = store.create_collection("Rainforest dawn", source)
    scanned_at = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
    snapshot = discover_wavs(
        source,
        collection_id=collection.ref.collection_id,
        binding_revision=collection.ref.binding_revision,
        scanned_at=scanned_at,
    )

    by_key = {row.recording_key: row for row in snapshot.recordings}
    assert by_key["recordings/dawn/mono.wav"].decision is InclusionDecision.INCLUDED
    assert by_key["recordings/dawn/mono.wav"].wav.frame_count == 1_600
    assert by_key["recordings/night/stereo.WAV"].wav.channels == 2
    assert by_key["recordings/night/stereo.WAV"].wav.sample_rate_hz == 48_000
    assert by_key["positives/call.wav"].decision is InclusionDecision.EXCLUDED
    assert by_key[".alpaca/datasets/dataset-1/snippets/call.wav"].decision is (
        InclusionDecision.EXCLUDED
    )
    assert by_key["incoming/unknown.wav"].decision is InclusionDecision.UNDECIDED
    assert by_key["recordings/night/stereo.WAV"].status is RecordingStatus.INVALID
    assert by_key["recordings/night/stereo-hardlink.wav"].status is RecordingStatus.INVALID
    assert {issue.code for issue in snapshot.issues} >= {"symlink_skipped", "hardlink_conflict"}
    assert snapshot.included_keys == ("recordings/dawn/mono.wav",)
    assert _tree_bytes(source) == before

    published = store.publish_inventory(collection.ref.collection_id, snapshot)
    reopened = store.load_inventory(collection.ref.collection_id)
    assert reopened == snapshot
    assert published.ref.inventory_revision == snapshot.inventory_id
    assert published.ref.inventory_binding_revision == published.ref.binding_revision
    paths = store.paths_for(collection.ref.collection_id)
    manifest_text = (
        paths.inventories_directory / snapshot.inventory_id / "inventory.json"
    ).read_text(encoding="utf-8")
    assert str(source) not in manifest_text
    manifest = json.loads(manifest_text)
    assert manifest["partitions"]
    assert all(part["rows"] <= 1_000 for part in manifest["partitions"])
    assert all(part["bytes"] <= 1_048_576 for part in manifest["partitions"])
    assert mono.read_bytes() == before["recordings/dawn/mono.wav"]


def test_invalid_missing_replaced_many_row_cancel_and_restart_keep_last_good(
    tmp_path, wav_factory, monkeypatch
):
    """Case: IT-DET-004."""
    source = tmp_path / "source"
    valid = wav_factory(source / "recordings" / "valid.wav", frames=80)
    removed = wav_factory(source / "recordings" / "removed.wav", frames=40)
    replaced = wav_factory(source / "recordings" / "replaced.wav", frames=40)
    (source / "recordings" / "truncated.wav").write_bytes(b"RIFF\x00\x00")
    unsupported = wav_factory(source / "recordings" / "unsupported.wav", frames=20)
    payload = bytearray(unsupported.read_bytes())
    payload[20:22] = (3).to_bytes(2, "little")
    unsupported.write_bytes(payload)
    unreadable = wav_factory(source / "recordings" / "unreadable.wav", frames=20)
    unreadable.chmod(0)
    template = valid.read_bytes()
    for index in range(425):
        (source / "incoming" / f"candidate-{index:04d}.wav").parent.mkdir(
            parents=True, exist_ok=True
        )
        (source / "incoming" / f"candidate-{index:04d}.wav").write_bytes(template)

    store = DetectWorkspaceStore(tmp_path / "application-data")
    collection = store.create_collection("Field", source)
    try:
        first = discover_wavs(
            source,
            collection_id=collection.ref.collection_id,
            binding_revision=1,
        )
    finally:
        unreadable.chmod(stat.S_IRUSR | stat.S_IWUSR)
    first_by_key = {row.recording_key: row for row in first.recordings}
    assert first_by_key["recordings/truncated.wav"].status is RecordingStatus.INVALID
    assert first_by_key["recordings/unsupported.wav"].status is RecordingStatus.INVALID
    assert first_by_key["recordings/unreadable.wav"].status is RecordingStatus.INVALID
    assert len(first.recordings) == 431
    store.publish_inventory(collection.ref.collection_id, first)

    cancel = Event()
    observed: list[InventoryScanProgress] = []
    outcome: list[BaseException] = []

    def run_cancelled() -> None:
        try:
            discover_wavs(
                source,
                collection_id=collection.ref.collection_id,
                binding_revision=1,
                cancel=cancel,
                progress=lambda value: (observed.append(value), cancel.set()),
                step_delay_seconds=0.001,
            )
        except BaseException as exc:  # captured from the test-owned thread
            outcome.append(exc)

    worker = Thread(target=run_cancelled)
    worker.start()
    worker.join(timeout=10)
    assert observed
    assert len(outcome) == 1 and isinstance(outcome[0], InventoryScanCancelled)
    assert store.load_inventory(collection.ref.collection_id) == first

    removed.unlink()
    original = replaced.stat()
    changed = bytearray(replaced.read_bytes())
    changed[-1] ^= 1
    replaced.write_bytes(changed)
    os.utime(replaced, ns=(original.st_atime_ns, original.st_mtime_ns))
    added = wav_factory(source / "recordings" / "added.wav", frames=10)
    second = discover_wavs(
        source,
        collection_id=collection.ref.collection_id,
        binding_revision=1,
        previous=first,
    )
    second_by_key = {row.recording_key: row for row in second.recordings}
    assert second_by_key["recordings/removed.wav"].status is RecordingStatus.MISSING
    assert second_by_key["recordings/replaced.wav"].change is ChangeKind.REPLACED
    assert second_by_key["recordings/added.wav"].change is ChangeKind.ADDED
    assert added.is_file()

    added_payload = added.read_bytes()
    added_stat = added.stat()
    added.write_bytes(added_payload + b"changed-after-scan")
    with pytest.raises(ValueError, match="changed before inventory publication"):
        store.publish_inventory(collection.ref.collection_id, second)
    assert store.load_inventory(collection.ref.collection_id) == first
    added.write_bytes(added_payload)
    os.utime(added, ns=(added_stat.st_atime_ns, added_stat.st_mtime_ns))

    real_publish = store._publish_snapshot_directory
    monkeypatch.setattr(
        store,
        "_publish_snapshot_directory",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("injected publication failure")),
    )
    with pytest.raises(OSError, match="injected"):
        store.publish_inventory(collection.ref.collection_id, second)
    assert store.load_inventory(collection.ref.collection_id) == first
    monkeypatch.setattr(store, "_publish_snapshot_directory", real_publish)
    store.publish_inventory(collection.ref.collection_id, second)
    assert store.load_inventory(collection.ref.collection_id) == second


@pytest.mark.qt
def test_native_inventory_selection_decisions_paging_keyboard_cancel_and_layout(
    qapp, qtbot, tmp_path, wav_factory, monkeypatch
):
    """Case: IT-DET-005."""
    source = tmp_path / "Rainforest_2026"
    wav_factory(source / "recordings" / "dawn.wav", frames=1_600)
    template = (source / "recordings" / "dawn.wav").read_bytes()
    (source / "positives").mkdir(parents=True)
    (source / "positives" / "labeled-call.wav").write_bytes(template)
    for index in range(225):
        path = source / "incoming" / f"candidate-{index:04d}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(template)

    controller = DetectWorkspaceController(
        tmp_path / "application-data", scan_step_delay_seconds=0.0005
    )
    page = DetectWorkspacePage(controller)
    qtbot.addWidget(page)
    page.resize(1180, 790)
    page.show()
    page.folder_picker.folderChanged.emit(str(source))
    qtbot.waitUntil(lambda: controller.is_scanning)
    assert page.scan_card.isVisible()
    assert page.cancel_scan_button.isEnabled()
    controller.cancel_scan()
    qtbot.waitUntil(lambda: not controller.is_scanning)
    assert controller.inventory_state.value == "cancelled"
    assert controller.snapshot is None

    page.rescan_button.click()
    qtbot.waitUntil(lambda: controller.snapshot is not None, timeout=15_000)
    assert controller.inventory_state.value == "ready"
    assert isinstance(page.inventory_table, DataTable)
    assert isinstance(page.inventory_model, InventoryTableModel)
    assert page.inventory_model.rowCount() == 200
    assert page.inventory_model.canFetchMore()
    page.inventory_model.fetchMore()
    assert page.inventory_model.rowCount() > 200

    policy_row = page.inventory_model.row_for_key("positives/")
    policy_index = page.inventory_model.index(policy_row, 0)
    page.inventory_table.setCurrentIndex(policy_index)
    assert not page.include_selection_button.isEnabled()

    folder_row = page.inventory_model.row_for_key("incoming/")
    index = page.inventory_model.index(folder_row, 0)
    page.inventory_table.setCurrentIndex(index)
    page.inventory_table.setFocus()
    qtbot.keyClick(page.inventory_table, Qt.Key.Key_Down)
    qtbot.keyClick(page.inventory_table, Qt.Key.Key_Up)
    page.inventory_table.setCurrentIndex(index)
    page.include_selection_button.setFocus()
    qtbot.keyClick(page.include_selection_button, Qt.Key.Key_Space)
    assert controller.snapshot.counts.included == 226
    assert page.detail_decision.text() == "Included"

    stable_key = "incoming/candidate-0005.wav"
    stable_row = page.inventory_model.row_for_key(stable_key)
    page.inventory_table.setCurrentIndex(page.inventory_model.index(stable_row, 0))
    page.exclude_selection_button.click()
    assert controller.snapshot.counts.included == 225
    assert page.detail_decision.text() == "Excluded"
    page.rescan_button.click()
    qtbot.waitUntil(lambda: not controller.is_scanning, timeout=15_000)
    assert page.selected_key == stable_key

    last_good_id = controller.snapshot.inventory_id
    page.rescan_button.click()
    qtbot.waitUntil(lambda: controller.is_scanning)
    controller.cancel_scan()
    qtbot.waitUntil(lambda: not controller.is_scanning)
    assert controller.inventory_state.value == "cancelled"
    assert controller.snapshot.inventory_id == last_good_id
    assert page.selected_key == stable_key

    hints = page.findChildren(HelpHint)
    assert any(hint.accessibleName() == "More about Recording inclusion" for hint in hints)
    inclusion_hint = next(
        hint for hint in hints if hint.accessibleName() == "More about Recording inclusion"
    )
    inclusion_hint.setFocus()
    qtbot.keyClick(inclusion_hint, Qt.Key.Key_Space)
    assert inclusion_hint.accessibleDescription()

    before_picker = controller.active_collection
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    browse = next(
        button
        for button in page.relink_picker.findChildren(QPushButton)
        if button.accessibleName() == "Choose Relink recordings folder"
    )
    qtbot.mouseClick(browse, Qt.MouseButton.LeftButton)
    assert controller.active_collection == before_picker

    page.resize(700, 780)
    qtbot.waitUntil(lambda: page.is_compact)
    detail_index = page.inventory_layout.indexOf(page.inventory_detail_card)
    assert page.inventory_layout.getItemPosition(detail_index)[:2] == (1, 0)
