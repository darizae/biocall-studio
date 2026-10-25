from __future__ import annotations

import csv
import json
import wave
from dataclasses import replace
from pathlib import Path

import pytest
from alp_ui.components import DataTable, HelpHint, NumberInput, ProgressBar, SelectInput
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from alpaca_desktop.application.collection_scan import scan_collection
from alpaca_desktop.application.workspace import WorkspaceController
from alpaca_desktop.domain.dataset import BuildConfig, Interval, protected_intervals
from alpaca_desktop.gui.app import create_application
from alpaca_desktop.gui.dataset import DatasetBuilderPage, DatasetDetailPage
from alpaca_desktop.gui.window import MainWindow
from alpaca_desktop.persistence.collection_metadata import publish_collection_metadata
from alpaca_desktop.persistence.datasets import delete_dataset, list_datasets, load_dataset
from alpaca_desktop.workflows.dataset_build import (
    DatasetBuildCancelled,
    DatasetBuildError,
    DatasetBuildUnderfill,
    build_dataset,
)

pytestmark = pytest.mark.integration


def _collection(root: Path, wav_factory, *, source_count: int = 3) -> Path:
    for index in range(source_count):
        stem = f"REC_{chr(ord('A') + index)}"
        wav_factory(root / "recordings" / f"{stem}.wav", frames=64_000)
        wav_factory(
            root / "positives" / f"{stem}__start-00500ms__end-01000ms__call{index + 1}.wav",
            frames=8_000,
        )
    return root


def _published(root: Path):
    result = scan_collection(root)
    assert result.valid
    return publish_collection_metadata(root, result)


def _config(result, **changes) -> BuildConfig:
    config = BuildConfig(
        selected_recording_ids=tuple(record.id for record in result.records),
        negative_mode="ratio",
        negative_ratio=1.0,
        negative_count=0,
        allocation="proportional",
        train_percent=80,
        balance_classes=True,
        seed=42,
        margin_ms=250,
    )
    return replace(config, **changes)


def _wav_frames(path: Path) -> bytes:
    with wave.open(str(path), "rb") as stream:
        return stream.readframes(stream.getnframes())


def test_real_source_audio_is_materialized_with_protected_windows_and_grouped_splits(
    tmp_path, wav_factory
):
    """Case: IT-DB-001."""
    root = _collection(tmp_path / "collection", wav_factory)
    result = _published(root)
    source_bytes = {path: path.read_bytes() for path in root.glob("recordings/*.wav")}
    positive_bytes = {path: path.read_bytes() for path in root.glob("positives/*.wav")}

    artifact = build_dataset(root, result, _config(result), dataset_id="dataset-real-a")

    assert artifact.root == root / ".alpaca" / "datasets" / "dataset-real-a"
    assert artifact.manifest["counts"] == {
        "target": 3,
        "noise": 3,
        "total": 6,
        "train": {"target": 2, "noise": 2, "total": 4},
        "val": {"target": 1, "noise": 1, "total": 2},
    }
    source_split = artifact.manifest["source_groups"]
    assert set(source_split.values()) == {"train", "val"}
    assert all(
        snippet["split"] == source_split[snippet["source_recording_id"]]
        for snippet in artifact.snippets
    )

    for snippet in artifact.snippets:
        output = artifact.root / snippet["relative_path"]
        assert output.is_file()
        assert _wav_frames(output)
        if snippet["label"] == "target":
            assert snippet["producing_positive_ref"].startswith("positives/")
        else:
            assert snippet["producing_positive_ref"] is None
            source = next(
                record for record in result.records if record.id == snippet["source_recording_id"]
            )
            annotations = tuple(
                Interval(positive.start_ms, positive.end_ms)
                for positive in result.positives
                if positive.source_recording_id == source.id
            )
            blocked = protected_intervals(
                annotations,
                duration_ms=round(source.fingerprint.header.duration_seconds * 1_000),
                margin_ms=250,
            )
            assert all(
                snippet["end_ms"] <= interval.start_ms or snippet["start_ms"] >= interval.end_ms
                for interval in blocked
            )

    target = next(snippet for snippet in artifact.snippets if snippet["label"] == "target")
    source_path = root / target["source_ref"]
    with wave.open(str(source_path), "rb") as source:
        source.setpos(target["transform"]["start_frame"])
        expected = source.readframes(
            target["transform"]["end_frame"] - target["transform"]["start_frame"]
        )
    assert _wav_frames(artifact.root / target["relative_path"]) == expected

    for split in ("train", "val"):
        with (artifact.root / "splits" / f"{split}.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert rows
        assert {row["source_recording_id"] for row in rows} == {
            source_id for source_id, assigned in source_split.items() if assigned == split
        }
    assert {path: path.read_bytes() for path in source_bytes} == source_bytes
    assert {path: path.read_bytes() for path in positive_bytes} == positive_bytes


def test_repeat_build_is_equivalent_and_changed_config_publishes_independently(
    tmp_path, wav_factory
):
    """Case: IT-DB-002."""
    root = _collection(tmp_path / "collection", wav_factory)
    result = _published(root)
    first = build_dataset(root, result, _config(result), dataset_id="dataset-repeat-a")
    first_manifest = (first.root / "dataset.json").read_bytes()
    second = build_dataset(root, result, _config(result), dataset_id="dataset-repeat-b")
    changed = build_dataset(
        root,
        result,
        _config(result, seed=99, margin_ms=0),
        dataset_id="dataset-changed",
    )

    def comparable(artifact):
        return [
            {
                key: snippet[key]
                for key in (
                    "snippet_id",
                    "label",
                    "source_recording_id",
                    "start_ms",
                    "end_ms",
                    "sha256",
                    "split",
                )
            }
            for snippet in artifact.snippets
        ]

    assert comparable(first) == comparable(second)
    assert changed.manifest["config"] != first.manifest["config"]
    assert changed.root != first.root
    assert (first.root / "dataset.json").read_bytes() == first_manifest


def test_underfill_changed_source_and_collision_publish_no_partial_dataset(tmp_path, wav_factory):
    """Case: IT-DB-003."""
    root = _collection(tmp_path / "collection", wav_factory)
    result = _published(root)
    source = root / "recordings" / "REC_A.wav"
    source_before = source.read_bytes()

    with pytest.raises(DatasetBuildUnderfill, match="[Ee]ligible source-time"):
        build_dataset(
            root,
            result,
            _config(result, margin_ms=4_000),
            dataset_id="dataset-underfill",
        )
    assert not (root / ".alpaca" / "datasets" / "dataset-underfill").exists()
    assert not any((root / ".alpaca" / ".staging").iterdir())

    source.write_bytes(source.read_bytes() + b"changed")
    with pytest.raises(DatasetBuildError, match="changed"):
        build_dataset(root, result, _config(result), dataset_id="dataset-stale")
    assert not (root / ".alpaca" / "datasets" / "dataset-stale").exists()
    source.write_bytes(source_before)
    result = _published(root)

    missing = root / "recordings" / "REC_B.wav"
    parked = root / "REC_B.parked"
    missing.rename(parked)
    try:
        with pytest.raises(DatasetBuildError, match="missing or changed"):
            build_dataset(root, result, _config(result), dataset_id="dataset-missing")
    finally:
        parked.rename(missing)
    assert not (root / ".alpaca" / "datasets" / "dataset-missing").exists()
    assert not any((root / ".alpaca" / ".staging").iterdir())

    result = _published(root)
    unknown_config = replace(
        _config(result), selected_recording_ids=(result.records[0].id, "source-missing")
    )
    with pytest.raises(DatasetBuildError, match="no longer exists"):
        build_dataset(root, result, unknown_config, dataset_id="dataset-invalid")
    with pytest.raises(DatasetBuildCancelled, match="cancelled"):
        build_dataset(
            root,
            result,
            _config(result),
            dataset_id="dataset-cancelled",
            cancelled=lambda: True,
        )
    assert not (root / ".alpaca" / "datasets" / "dataset-invalid").exists()
    assert not (root / ".alpaca" / "datasets" / "dataset-cancelled").exists()
    assert not any((root / ".alpaca" / ".staging").iterdir())

    published = build_dataset(root, result, _config(result), dataset_id="dataset-collision")
    before = (published.root / "dataset.json").read_bytes()
    with pytest.raises(FileExistsError, match="already exists"):
        build_dataset(root, result, _config(result), dataset_id="dataset-collision")
    assert (published.root / "dataset.json").read_bytes() == before


def test_dataset_reopens_and_explicit_delete_preserves_models_and_inputs(tmp_path, wav_factory):
    """Case: IT-DB-004."""
    root = _collection(tmp_path / "collection", wav_factory)
    result = _published(root)
    inputs_before = {path: path.read_bytes() for path in root.glob("*/*.wav")}
    built = build_dataset(root, result, _config(result), dataset_id="dataset-delete")
    reopened = load_dataset(root, built.dataset_id)
    assert reopened.manifest == built.manifest
    assert reopened.snippets == built.snippets
    assert [item.dataset_id for item in list_datasets(root)] == ["dataset-delete"]

    model = root / ".alpaca" / "models" / "model-kept"
    model.mkdir(parents=True)
    (model / "model.json").write_text(
        json.dumps({"schema_version": 1, "model_id": "model-kept", "dataset_id": built.dataset_id})
    )
    with pytest.raises(ValueError, match="Active Run"):
        delete_dataset(root, built.dataset_id, reserved_dataset_ids={built.dataset_id})
    deletion = delete_dataset(root, built.dataset_id)
    assert deletion.dependent_model_ids == ("model-kept",)
    assert not built.root.exists()
    assert (model / "model.json").exists()
    assert {path: path.read_bytes() for path in inputs_before} == inputs_before


@pytest.mark.qt
def test_native_builder_controls_states_worker_and_dataset_navigation(
    qapp, qtbot, tmp_path, wav_factory, monkeypatch
):
    """Case: IT-DB-005."""
    create_application()
    root = _collection(tmp_path / "collection", wav_factory)
    result = _published(root)
    controller = WorkspaceController(tmp_path / "settings")
    controller.bind_verified_collection(root, result.collection_id)
    window = MainWindow(controller)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(
        lambda: controller.scan_result is not None and not controller.is_scanning,
        timeout=10_000,
    )
    assert window.current_route == "collection"
    window.collection_page.build_button.click()

    assert window.current_route == "builder"
    builder = window.builder_page
    assert isinstance(builder, DatasetBuilderPage)
    assert isinstance(builder.sources_table, DataTable)
    assert isinstance(builder.negative_amount, NumberInput)
    assert isinstance(builder.negative_mode, SelectInput)
    assert isinstance(builder.margin, SelectInput)
    assert isinstance(builder.class_mix, ProgressBar)
    assert builder.sources_table.accessibleName() == "Participating Source Recordings"
    assert builder.build_button.text() == "Build Dataset"
    assert builder.source_model.selected_count == 3
    assert builder.build_button.isEnabled()

    hint = builder.findChild(HelpHint)
    assert hint is not None
    hint.setFocus()
    qtbot.keyClick(hint, Qt.Key.Key_Space)
    assert hint.accessibleDescription()

    builder.source_model.setData(
        builder.source_model.index(0, 0), Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole
    )
    builder.source_model.setData(
        builder.source_model.index(1, 0), Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole
    )
    assert builder.source_model.selected_count == 1
    assert not builder.build_button.isEnabled()
    assert "at least two" in builder.preview_alert.text_widget.text().lower()
    builder.select_all.setChecked(True)

    builder.negative_amount.setValue(20)
    builder.margin.setCurrentIndex(builder.margin.count() - 1)
    assert builder.preview_alert.isVisible()
    assert "underfill" in builder.preview_alert.title_widget.text().lower()
    assert not builder.build_button.isEnabled()
    builder.negative_amount.setValue(2)
    builder.margin.setCurrentIndex(0)
    assert builder.build_button.isEnabled()

    builder.build_button.click()
    assert controller.is_building
    assert builder.build_button.isLoading()
    assert window.current_route == "run-detail"
    assert window.active_run_label.text().startswith("Build ·")
    assert window.working_run_badge.isVisible()
    qtbot.waitUntil(lambda: controller.active_run is None, timeout=20_000)
    assert window.current_route == "run-detail"
    assert window.run_detail_page.status_badge.text() == "completed"
    window.run_detail_page.open_output_button.click()
    assert window.current_route == "dataset-detail"
    detail = window.dataset_detail_page
    assert isinstance(detail, DatasetDetailPage)
    assert detail.dataset is not None
    assert detail.train_button.text() == "Train Model"
    assert not detail.train_button.isEnabled()
    assert detail.delete_button.text() == "Delete"
    assert len(detail.findChildren(ProgressBar)) == 2
    assert window.active_run_label.text() == "No Active Run"
    assert window.idle_run_badge.isVisible()

    window.navigate("datasets")
    assert window.dataset_list_page.model.rowCount() == 1
    index = window.dataset_list_page.model.index(0, 0)
    window.dataset_list_page.table.clicked.emit(index)
    assert window.current_route == "dataset-detail"

    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    detail.delete_button.click()
    assert window.current_route == "datasets"
    assert window.dataset_list_page.model.rowCount() == 0

    window.open_builder()
    window.resize(700, 780)
    qtbot.waitUntil(lambda: window.is_compact and window.builder_page.is_compact)
    assert builder.horizontalScrollBar().maximum() == 0
    assert builder.build_button.focusPolicy() != Qt.FocusPolicy.NoFocus
    screenshot = tmp_path / "builder-narrow.png"
    assert window.grab().save(str(screenshot))
    assert screenshot.stat().st_size > 0
