from __future__ import annotations

import json
import os
import shutil
import struct
import wave
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import joblib
import librosa
import numpy as np
import pytest
from alp_ui.components import DataTable, HelpHint
from bioacoustics_dl_toolbox.audio import load_audio_file
from bioacoustics_dl_toolbox.prediction import predict_windows
from bioacoustics_dl_toolbox.rf import compute_rf_features
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QBoxLayout, QFileDialog, QMessageBox, QPushButton

from biocall_studio.detect.application.controller import DetectWorkspaceController, ModelIntakeState
from biocall_studio.detect.application.model_intake import inspect_model_directory
from biocall_studio.detect.application.navigation import DetectRoute
from biocall_studio.detect.domain.detection import (
    DetectionSettings,
    merge_candidate_windows,
    predict_recording_windows,
)
from biocall_studio.detect.domain.inventory import InclusionDecision
from biocall_studio.detect.domain.models import ModelFamily
from biocall_studio.detect.domain.result_views import (
    CandidateViewRow,
    RecordingViewRow,
    ResultContentState,
    ResultSourceState,
)
from biocall_studio.detect.domain.results import FileOutcomeStatus
from biocall_studio.detect.domain.rf_refinement import (
    RefinementStatus,
    extract_candidate_features,
)
from biocall_studio.detect.domain.runs import DetectRunStatus
from biocall_studio.detect.gui.results import CandidateResultModel
from biocall_studio.detect.gui.workspace import DetectWorkspacePage
from biocall_studio.detect.persistence.runs import DetectRunRepository
from biocall_studio.shared.storage import (
    CapacityObservation,
    StorageDecision,
    StoragePreflightError,
    query_filesystem_capacity,
)
from biocall_studio.train.application.collection_scan import scan_collection
from biocall_studio.train.domain.dataset import BuildConfig
from biocall_studio.train.domain.training import (
    DeviceCapabilities,
    TrainingDataset,
    TrainingDraft,
    freeze_training_config,
)
from biocall_studio.train.persistence.collection_metadata import publish_collection_metadata
from biocall_studio.train.persistence.datasets import load_dataset
from biocall_studio.train.persistence.models import ModelArtifact
from biocall_studio.train.workflows.cnn_training import CnnTrainingRequest, train_cnn_model
from biocall_studio.train.workflows.dataset_build import build_dataset
from biocall_studio.train.workflows.rf_training import RfTrainingRequest, train_rf_model

pytestmark = pytest.mark.integration


def _write_wav(
    path: Path,
    *,
    frames: int,
    rate: int = 16_000,
    channels: int = 1,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = bytearray()
    for frame in range(frames):
        for channel in range(channels):
            value = ((frame * 97 + channel * 701) % 20_000) - 10_000
            payload.extend(struct.pack("<h", value))
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(payload)
    return path


def _cnn_draft() -> TrainingDraft:
    draft = TrainingDraft.defaults("cnn")
    for key, value in {
        "sequence_length_ms": 250,
        "training.max_epochs": 1,
        "training.batch_size": 2,
        "training.learning_rate": 0.0001,
        "device": "cpu",
        "spectrogram.sample_rate": 16_000,
        "spectrogram.n_fft": 256,
        "spectrogram.hop_length": 64,
        "spectrogram.n_freq_bins": 64,
        "spectrogram.f_min": 100,
        "spectrogram.f_max": 7_000,
        "training.num_workers": 0,
        "training.early_stopping_patience_epochs": 2,
        "training.epochs_per_eval": 1,
        "training.pin_memory": False,
    }.items():
        draft.set(key, value)
    return draft


def _rf_draft() -> TrainingDraft:
    draft = TrainingDraft.defaults("rf")
    for key, value in {
        "n_estimators": 12,
        "min_samples_leaf": 1,
        "rf_threshold": 0.55,
        "random_state": 42,
        "n_jobs": 1,
        "feature_config.sample_rate_hz": 8_000,
        "feature_config.min_duration_s": 0.5,
        "feature_config.pad_short_segments": False,
        "feature_config.n_fft": 256,
        "feature_config.hop_length": 64,
        "feature_config.n_mfcc": 4,
        "feature_config.fmin_hz": 100.0,
        "feature_config.fmax_hz": 3_500.0,
    }.items():
        draft.set(key, value)
    return draft


@dataclass(frozen=True)
class _GenuineCnn:
    root: Path
    model: ModelArtifact
    parity_wav: Path


@pytest.fixture(scope="module")
def genuine_cnn(tmp_path_factory) -> _GenuineCnn:
    root = tmp_path_factory.mktemp("st07-genuine-cnn") / "collection"
    for index in range(3):
        stem = f"REC_{chr(ord('A') + index)}"
        _write_wav(root / "recordings" / f"{stem}.wav", frames=32_000)
        _write_wav(
            root / "positives" / f"{stem}__start-00500ms__end-01000ms__call{index}.wav",
            frames=8_000,
        )
    scan = publish_collection_metadata(root, scan_collection(root))
    dataset = build_dataset(
        root,
        scan,
        BuildConfig(
            selected_recording_ids=tuple(record.id for record in scan.records),
            negative_mode="ratio",
            negative_ratio=1.0,
            negative_count=0,
            allocation="proportional",
            train_percent=80,
            balance_classes=True,
            seed=42,
            margin_ms=100,
        ),
        dataset_id="dataset-st07-cnn",
    )
    config = freeze_training_config(
        _cnn_draft(),
        TrainingDataset.from_artifact(dataset),
        DeviceCapabilities(cuda=False, mps=False, cpu_count=8),
    )
    model = train_cnn_model(
        root,
        CnnTrainingRequest(
            run_id="run-st07-cnn",
            request_id="request-st07-cnn",
            collection_root=str(root),
            collection_id=scan.collection_id,
            config=config,
            model_id="model-st07-cnn",
            model_label="Genuine ST-07 CNN",
        ),
    )
    parity_wav = _write_wav(
        root / "recordings" / "STEREO_8K.wav",
        frames=6_125,
        rate=8_000,
        channels=2,
    )
    # The inventory contract can verify this integer PCM header and payload, while
    # libsndfile explicitly rejects the extreme channel count at the decode boundary.
    _write_wav(root / "recordings" / "BROKEN.wav", frames=1, channels=2_048)
    return _GenuineCnn(root, model, parity_wav)


@pytest.fixture(scope="module")
def genuine_rf(genuine_cnn) -> ModelArtifact:
    dataset = load_dataset(genuine_cnn.root, "dataset-st07-cnn")
    config = freeze_training_config(
        _rf_draft(),
        TrainingDataset.from_artifact(dataset),
        DeviceCapabilities(cuda=False, mps=False, cpu_count=8),
    )
    return train_rf_model(
        genuine_cnn.root,
        RfTrainingRequest(
            run_id="run-st09-rf",
            request_id="request-st09-rf",
            collection_root=str(genuine_cnn.root),
            collection_id=dataset.manifest["collection_id"],
            config=config,
            model_id="model-st09-rf",
            model_label="Genuine ST-09 RF",
        ),
    )


def _select_inputs(
    qtbot, controller: DetectWorkspaceController, model_root: Path, source_root: Path
):
    controller.choose_model_root(str(model_root))
    qtbot.waitUntil(
        lambda: controller.model_state is ModelIntakeState.COMPATIBLE,
        timeout=30_000,
    )
    controller.choose_source_root(str(source_root))
    qtbot.waitUntil(lambda: controller.inputs_ready, timeout=30_000)


def _wait_terminal(qtbot, controller: DetectWorkspaceController, timeout=120_000):
    qtbot.waitUntil(
        lambda: controller.current_run is not None and controller.current_run.terminal,
        timeout=timeout,
    )
    return controller.current_run


@pytest.mark.qt
def test_guided_detect_routes_bulk_badges_run_and_selection_free_export(
    qapp, qtbot, genuine_cnn, genuine_rf, tmp_path, monkeypatch
):
    """Cases: IT-DET-023, IT-DET-025."""
    source = tmp_path / "guided-source"
    shutil.copytree(genuine_cnn.root / "recordings", source / "recordings")
    app_data = tmp_path / "application-data"
    controller = DetectWorkspaceController(app_data, model_step_delay_seconds=0.05)
    page = DetectWorkspacePage(controller)
    qtbot.addWidget(page)
    page.resize(1180, 790)
    page.show()

    assert [button.text() for button in page._navigation.values()] == [
        "New detection",
        "Recordings",
        "Models",
        "Runs",
        "Results",
        "Exports",
    ]
    assert not hasattr(page, "step_chevrons")
    assert all(not button.toolTip() for button in page._navigation.values())
    assert page.current_route is DetectRoute.MODELS
    assert page._navigation[DetectRoute.MODELS].isChecked()
    assert page.settings_card.parent() is page.new_detection_view

    exports_button = page._navigation[DetectRoute.EXPORTS]
    exports_button.setFocus()
    qtbot.keyClick(exports_button, Qt.Key.Key_Space)
    assert page.current_route is DetectRoute.EXPORTS
    assert not hasattr(page.export_history_page, "new_button")
    assert not page.export_history_page.open_button.isEnabled()
    page._navigation[DetectRoute.RESULTS].click()
    assert page.current_route is DetectRoute.RESULTS
    assert not hasattr(page.result_explorer, "export_button")

    page._navigation[DetectRoute.MODELS].click()
    assert page.current_route is DetectRoute.MODELS
    assert page.model_status_badge.intent == "neutral"
    page.model_picker.folderChanged.emit(str(genuine_cnn.model.root))
    assert page.model_status_badge.text() == "Checking"
    assert page.model_status_badge.intent == "warning"
    assert not page.model_picker.isEnabled()
    qtbot.waitUntil(lambda: controller.model_state is ModelIntakeState.COMPATIBLE, timeout=30_000)
    assert page.model_status_badge.intent == "success"
    assert page.model_name.text() == genuine_cnn.model.label

    page._navigation[DetectRoute.NEW_DETECTION].click()
    assert page.current_route is DetectRoute.RECORDINGS
    page._navigation[DetectRoute.MODELS].click()
    page.models_continue_button.click()
    assert page.current_route is DetectRoute.RECORDINGS
    page.folder_picker.folderChanged.emit(str(source))
    qtbot.waitUntil(lambda: controller.snapshot is not None, timeout=30_000)
    assert page.current_route is DetectRoute.RECORDINGS
    bound = controller.active_collection
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    browse = next(
        button
        for button in page.relink_picker.findChildren(QPushButton)
        if button.accessibleName() == "Choose Relink recordings folder"
    )
    browse.click()
    assert page.current_route is DetectRoute.RECORDINGS
    assert controller.active_collection == bound

    excluded_key = next(
        row.recording_key for row in controller.snapshot.recordings if row.status.value == "valid"
    )
    controller.set_inventory_decision(
        excluded_key,
        is_folder=False,
        decision=InclusionDecision.EXCLUDED,
    )
    prior_snapshot = controller.snapshot
    prior_document = prior_snapshot.to_dict()
    collection_id = controller.active_collection.ref.collection_id
    observed_dialogs = []

    def cancel_confirmation(dialog):
        observed_dialogs.append(dialog)
        assert dialog.defaultButton() is dialog.button(QMessageBox.StandardButton.Cancel)
        assert "1 explicitly excluded recording" in dialog.text()
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "exec", cancel_confirmation)
    page.include_all_button.click()
    assert observed_dialogs
    assert controller.snapshot.to_dict() == prior_document
    assert controller.store.load_inventory(collection_id).to_dict() == prior_document

    original_publish = controller.store.publish_inventory

    def fail_publish(*_args, **_kwargs):
        raise OSError("simulated atomic write failure")

    monkeypatch.setattr(controller.store, "publish_inventory", fail_publish)
    controller.include_all_valid_recordings(
        expected_inventory_id=prior_snapshot.inventory_id,
        exclusions_confirmed=True,
    )
    assert controller.snapshot.to_dict() == prior_document
    assert controller.store.load_inventory(collection_id).to_dict() == prior_document
    assert "simulated atomic write failure" in controller.inventory_error
    monkeypatch.setattr(controller.store, "publish_inventory", original_publish)

    monkeypatch.setattr(
        QMessageBox,
        "exec",
        lambda dialog: QMessageBox.StandardButton.Yes,
    )
    page.include_all_button.click()
    assert controller.snapshot.inventory_id != prior_snapshot.inventory_id
    assert all(
        row.decision is InclusionDecision.INCLUDED
        for row in controller.snapshot.recordings
        if row.status.value == "valid"
    )

    page.recordings_continue_button.setFocus()
    qtbot.keyClick(page.recordings_continue_button, Qt.Key.Key_Space)
    assert page.current_route is DetectRoute.NEW_DETECTION
    qtbot.waitUntil(lambda: page.focusWidget() is page.start_detection_button)
    assert page.minimum_score.isVisible()
    assert page.run_summary_model.text() == genuine_cnn.model.label
    assert page.run_summary_recordings.text().startswith(str(controller.snapshot.counts.included))
    assert page.run_blocker.text() == "Ready to start detection."
    page.minimum_score.setValue(1.0)
    page.start_detection_button.click()
    assert page.current_route is DetectRoute.RUN_DETAIL
    assert controller.current_run is not None
    assert page.active_run_label.text() == controller.current_run.title
    assert page.active_run_badge.text() in {"Preparing", "Running"}
    record = _wait_terminal(qtbot, controller)
    assert record.status is DetectRunStatus.COMPLETED
    page._navigation[DetectRoute.RUNS].click()
    assert page.run_history_page.model.rowCount() == 1
    assert page.run_history_page.model.record_at(0).run_id == record.run_id
    page.run_history_page.open_button.click()
    assert page.current_route is DetectRoute.RUN_DETAIL
    assert page.open_run_result_button.isEnabled()
    page.open_run_result_button.click()
    assert page.current_route is DetectRoute.RESULTS

    explorer = page.result_explorer
    page._navigation[DetectRoute.MODELS].click()
    page.refinement_model_picker.folderChanged.emit(str(genuine_cnn.model.root))
    qtbot.waitUntil(
        lambda: controller.refinement_model_state is ModelIntakeState.INCOMPATIBLE,
        timeout=30_000,
    )
    assert page.refinement_model_status_badge.intent == "danger"
    page.refinement_model_picker.folderChanged.emit(str(genuine_rf.root))
    qtbot.waitUntil(
        lambda: controller.refinement_model_state is ModelIntakeState.COMPATIBLE,
        timeout=30_000,
    )
    assert page.refinement_model_status_badge.intent == "success"
    page._navigation[DetectRoute.RESULTS].click()
    assert explorer.refinement_status_badge.intent == "success"
    assert not hasattr(explorer, "export_button")

    for width in (1180, 700):
        page.resize(width, 790)
        qtbot.waitUntil(lambda width=width: page.is_compact == (width < 820))
        assert page.content_scroll.horizontalScrollBar().maximum() == 0
        assert page.navigation_layout.direction() is (
            QBoxLayout.Direction.LeftToRight if width < 820 else QBoxLayout.Direction.TopToBottom
        )

    evidence_value = os.environ.get("BIOCALL_REV04_EVIDENCE_DIR")
    if evidence_value:
        evidence = Path(evidence_value)
        evidence.mkdir(parents=True, exist_ok=True)
        controller.select_run(record.run_id)
        for width, size_label in ((1180, "normal"), (700, "compact")):
            page.resize(width, 790)
            qtbot.waitUntil(lambda width=width: page.is_compact == (width < 820))
            qtbot.wait(50)
            for route, label in (
                (DetectRoute.NEW_DETECTION, "new-detection"),
                (DetectRoute.MODELS, "models"),
                (DetectRoute.RUNS, "runs-list"),
                (DetectRoute.RUN_DETAIL, "run-detail"),
            ):
                page._set_route(route)
                qtbot.wait(100)
                assert page.slim_header.isVisibleTo(page)
                assert page.slim_header.height() >= page.slim_header.minimumSizeHint().height(), (
                    page.slim_header.geometry(),
                    page.slim_header.minimumSizeHint(),
                    page.body.geometry(),
                )
                assert page.slim_header.y() >= 0, (
                    page.slim_header.geometry(),
                    page.body.geometry(),
                )
                assert page.slim_header.geometry().bottom() < page.body.height(), (
                    page.slim_header.geometry(),
                    page.body.geometry(),
                )
                assert page.content_scroll.y() > page.slim_header.geometry().bottom(), (
                    page.slim_header.geometry(),
                    page.content_scroll.geometry(),
                    page.body.geometry(),
                )
                assert page.sidebar_brand.isVisibleTo(page) is (width >= 820)
                if width >= 820:
                    assert page.sidebar_brand.y() >= 0, (
                        page.sidebar_brand.geometry(),
                        page.sidebar.geometry(),
                    )
                    assert page.nav_scroll.y() > page.sidebar_brand.geometry().bottom(), (
                        page.sidebar_brand.geometry(),
                        page.nav_scroll.geometry(),
                        page.sidebar.geometry(),
                    )
                path = evidence / f"{label}-{size_label}.png"
                assert page.grab().save(str(path), "PNG")
                assert path.stat().st_size > 10_000

    controller.shutdown()


def test_real_wav_cpu_cnn_matches_verified_upstream_reference(genuine_cnn):
    """Case: IT-DET-012."""
    reference = inspect_model_directory(genuine_cnn.model.root)
    settings = DetectionSettings(0.5, 50, 0, 2)
    observed = predict_recording_windows(reference, genuine_cnn.parity_wav, settings)
    expected = predict_windows(
        genuine_cnn.model.root / reference.snapshot.artifact_relative_path,
        genuine_cnn.parity_wav,
        hop_samples=settings.hop_samples(reference.snapshot.window_length_samples),
        batch_size=settings.batch_size,
        device="cpu",
    )
    assert len(observed) == len(expected) > 1
    assert [item.index for item in observed] == [item.index for item in expected]
    assert [item.start_sample for item in observed] == [item.start_sample for item in expected]
    assert [item.end_sample for item in observed] == [item.end_sample for item in expected]
    assert all(list(item.probabilities) == ["noise", "target"] for item in expected)
    for actual, upstream in zip(observed, expected, strict=True):
        assert actual.target_score == pytest.approx(
            upstream.probabilities["target"], rel=0, abs=1e-7
        )
    # The final upstream interval is in the resampled 16 kHz time base and is clamped.
    assert expected[-1].end_sample == round(6_125 * 16_000 / 8_000)
    source_intervals = merge_candidate_windows(
        observed,
        settings=DetectionSettings(0.0, 50, 0, 2),
        model_sample_rate_hz=16_000,
        source_sample_rate_hz=8_000,
        source_frame_count=6_125,
    )
    assert len(source_intervals) == 1
    assert source_intervals[0][:2] == (0, 6_125)


@pytest.mark.qt
def test_real_run_publishes_reopenable_metadata_result_and_native_controls(
    qapp, qtbot, genuine_cnn, tmp_path
):
    """Cases: IT-DET-013, IT-STU-009."""
    app_data = tmp_path / "application-data"
    controller = DetectWorkspaceController(app_data)
    page = DetectWorkspacePage(controller)
    qtbot.addWidget(page)
    page.resize(1180, 790)
    page.show()
    page.model_picker.folderChanged.emit(str(genuine_cnn.model.root))
    qtbot.waitUntil(lambda: controller.model_state is ModelIntakeState.COMPATIBLE, timeout=30_000)
    page.folder_picker.folderChanged.emit(str(genuine_cnn.root))
    qtbot.waitUntil(lambda: controller.inputs_ready, timeout=30_000)

    source_bytes = {
        path.relative_to(genuine_cnn.root).as_posix(): path.read_bytes()
        for path in (genuine_cnn.root / "recordings").glob("*.wav")
    }
    assert page.minimum_score.value() == 0.5
    assert page.start_detection_button.isEnabled()
    assert {hint.accessibleName() for hint in page.findChildren(HelpHint)} >= {
        "More about Minimum detection score",
        "More about Window overlap",
        "More about Combine nearby candidates",
    }
    page.content_scroll.verticalScrollBar().setValue(
        page.content_scroll.verticalScrollBar().maximum()
    )
    page.resize(700, 780)
    qtbot.waitUntil(lambda: page.is_compact)
    qtbot.waitUntil(lambda: page.content_scroll.horizontalScrollBar().maximum() == 0)
    assert page.content_scroll.horizontalScrollBar().maximum() == 0
    assert page.content.minimumSizeHint().width() <= page.width()
    assert page.settings_layout.getItemPosition(
        page.settings_layout.indexOf(page.minimum_score_row)
    )[:2] == (0, 0)
    page.resize(1180, 790)
    qtbot.waitUntil(lambda: not page.is_compact)
    page.minimum_score.setValue(1.0)
    page.start_detection_button.click()
    assert page.current_route is DetectRoute.RUN_DETAIL
    record = _wait_terminal(qtbot, controller)
    assert record.status is DetectRunStatus.COMPLETED
    assert record.progress == 100

    repository = DetectRunRepository(app_data, controller.active_collection.ref.collection_id)
    result = repository.load_detection_result(record)
    assert result.result_id == record.published_artifact_id
    assert result.result_digest
    assert result.candidate_count == 0
    zero = [item for item in result.recordings if item.status.value == "succeeded"]
    failed = [item for item in result.recordings if item.status.value == "failed"]
    assert zero and all(item.candidates == () for item in zero)
    assert [item.recording_key for item in failed] == ["recordings/BROKEN.wav"]
    assert failed[0].error_code == "audio_decode_failed"
    assert controller.current_result == result
    result_path = repository.result_path(record.artifact_id) / "result.json"
    assert result_path.is_file()
    assert str(genuine_cnn.root) not in result_path.read_text()
    assert source_bytes == {
        path.relative_to(genuine_cnn.root).as_posix(): path.read_bytes()
        for path in (genuine_cnn.root / "recordings").glob("*.wav")
    }
    assert page.run_guidance.text() == (
        "Detection finished: 0 possible calls across 4 recordings; 1 file failed."
    )
    reopened = DetectWorkspaceController(app_data)
    assert reopened.current_run.status is DetectRunStatus.COMPLETED
    assert reopened.current_result == result
    assert reopened.wait_for_model(30_000)
    reopened.shutdown()
    controller.shutdown()


@pytest.mark.qt
def test_native_result_history_recording_candidates_selection_and_keyboard_navigation(
    qapp, qtbot, genuine_cnn, tmp_path, monkeypatch
):
    """Cases: IT-DET-015, IT-SIZE-002, IT-SIZE-003."""
    source = tmp_path / "result-source"
    shutil.copytree(genuine_cnn.root / "recordings", source / "recordings")
    app_data = tmp_path / "application-data"
    controller = DetectWorkspaceController(app_data)
    _select_inputs(qtbot, controller, genuine_cnn.model.root, source)
    page = DetectWorkspacePage(controller)
    qtbot.addWidget(page)
    page.resize(1180, 790)
    page.show()
    qtbot.waitExposed(page)
    page.raise_()
    page.activateWindow()

    settings = DetectionSettings(0.0, 50, 0, 4)
    estimate = controller.estimate_detection_storage(settings)
    assert estimate.expected_final.kind == "range"
    assert page.storage_section.isVisible()
    assert page.storage_section.note.text() == (
        "Output size varies with the recording and settings."
    )
    first_digest = estimate.input_digest
    changed = controller.estimate_detection_storage(DetectionSettings(0.0, 25, 0, 4))
    assert changed.input_digest != first_digest
    stale = controller.estimate_detection_storage(
        DetectionSettings(0.0, 25, 0, 4), expected_digest=first_digest
    )
    assert stale.decision is StorageDecision.STALE
    controller._capacity_probe = lambda path, label: CapacityObservation(
        label,
        "tight-detect-volume",
        700 * 1024**2,
        datetime(2026, 11, 3, tzinfo=UTC),
    )
    tight = controller.estimate_detection_storage(settings)
    assert tight.decision is StorageDecision.TIGHT
    before_runs = controller.runs
    with pytest.raises(StoragePreflightError, match="confirmation"):
        controller.start_detection(settings, storage_digest=tight.input_digest)
    assert controller.runs == before_runs
    assert controller.run_process is None
    controller._capacity_probe = query_filesystem_capacity
    page.resize(700, 790)
    qtbot.waitUntil(lambda: page.is_compact)
    assert page.storage_section.isVisible()

    controller.start_detection(settings)
    first_run = _wait_terminal(qtbot, controller)
    assert first_run.status is DetectRunStatus.COMPLETED
    assert controller.current_result is not None
    assert controller.current_result.candidate_count >= 2
    first_result = controller.current_result
    result_path = (
        DetectRunRepository(app_data, controller.active_collection.ref.collection_id).result_path(
            first_result.result_id
        )
        / "result.json"
    )
    immutable_bytes = result_path.read_bytes()

    assert page._navigation[DetectRoute.RESULTS].isEnabled()
    page._navigation[DetectRoute.RESULTS].click()
    assert page.current_route is DetectRoute.RESULTS
    explorer = page.result_explorer
    page.focus_initial()
    qtbot.waitUntil(lambda: page.focusWidget() is explorer.history_select.control)
    assert {hint.accessibleName() for hint in explorer.findChildren(HelpHint)} == {
        "More about Estimated output",
        "More about Space while running",
    }
    assert isinstance(explorer.recording_table, DataTable)
    assert isinstance(explorer.candidate_table, DataTable)
    assert explorer.history_select.count() == 1
    assert explorer.recording_model.rowCount() == len(first_result.recordings)

    successful_rows = [
        index
        for index, recording in enumerate(controller.selected_result_projection.recordings)
        if recording.candidates
    ]
    assert len(successful_rows) >= 2
    first_recording_row, second_recording_row = successful_rows[:2]
    explorer.recording_table.setCurrentIndex(explorer.recording_model.index(first_recording_row, 0))
    first_recording_id = explorer.selected_recording_id
    assert explorer.candidate_model.rowCount() > 0
    opened_urls = []
    monkeypatch.setattr(
        "biocall_studio.detect.gui.results.QDesktopServices.openUrl",
        lambda url: opened_urls.append(url) or True,
    )
    explorer.show_source_button.click()
    assert Path(opened_urls[0].toLocalFile()) == source / "recordings"
    first_candidate_id = explorer.candidate_model.candidate_at(0).candidate_id
    explorer.candidate_table.setCurrentIndex(explorer.candidate_model.index(0, 0))
    assert explorer.candidate_detail_id.text() == first_candidate_id

    explorer.recording_table.setFocus()
    assert second_recording_row == first_recording_row + 1
    qtbot.keyClick(explorer.recording_table, Qt.Key.Key_Down)
    assert explorer.recording_table.currentIndex().row() == second_recording_row
    assert explorer.selected_recording_id != first_recording_id
    assert all(
        candidate.recording_id == explorer.selected_recording_id
        for candidate in explorer.candidate_model.visible_candidates
    )
    explorer.recording_table.setCurrentIndex(explorer.recording_model.index(first_recording_row, 0))
    first_index = explorer.candidate_model.index(0, 0)
    assert explorer.candidate_model.data(first_index, Qt.ItemDataRole.CheckStateRole) is None
    assert not explorer.candidate_model.flags(first_index) & Qt.ItemFlag.ItemIsUserCheckable

    controller.start_detection(DetectionSettings(1.0, 50, 0, 4))
    second_run = _wait_terminal(qtbot, controller)
    assert second_run.status is DetectRunStatus.COMPLETED
    assert controller.current_result.candidate_count == 0
    assert len(controller.result_history) == 2
    assert explorer.history_select.count() == 2
    controller.select_result(first_result.result_id)
    assert result_path.read_bytes() == immutable_bytes
    controller.shutdown()


@pytest.mark.qt
def test_large_candidate_model_is_paged_without_source_audio_access(qapp):
    """Case: IT-DET-015."""
    recording_id = "rec_" + "1" * 32
    candidates = tuple(
        CandidateViewRow(
            candidate_id=f"cand_{index:032x}",
            recording_id=recording_id,
            start_frame=index * 32,
            end_frame=index * 32 + 16,
            start_time_ns=index * 2_000_000,
            end_time_ns=index * 2_000_000 + 1_000_000,
            max_target_score=0.75,
            contributing_windows=1,
        )
        for index in range(10_050)
    )
    recording = RecordingViewRow(
        recording_id=recording_id,
        source_relative_name="recordings/scale.wav",
        source_sha256="2" * 64,
        sample_rate_hz=16_000,
        frame_count=400_000,
        channels=1,
        outcome=FileOutcomeStatus.SUCCEEDED,
        error_code="",
        candidates=candidates,
    )
    model = CandidateResultModel()
    model.set_recording(recording)
    assert model.rowCount() == 200
    assert len(model.visible_candidates) == 200
    assert model.canFetchMore()
    model.fetchMore()
    assert model.rowCount() == 400
    assert model.candidate_at(399).candidate_id == candidates[399].candidate_id


@pytest.mark.qt
def test_result_empty_partial_missing_corrupt_persistence_and_native_screenshots(
    qapp, qtbot, genuine_cnn, tmp_path
):
    """Case: IT-DET-016."""
    source = tmp_path / "result-source"
    shutil.copytree(genuine_cnn.root / "recordings", source / "recordings")
    app_data = tmp_path / "application-data"
    controller = DetectWorkspaceController(app_data)
    _select_inputs(qtbot, controller, genuine_cnn.model.root, source)

    controller.start_detection(DetectionSettings(0.0, 50, 0, 4))
    partial_run = _wait_terminal(qtbot, controller)
    partial_result = controller.current_result
    assert partial_result.failed_files == 1
    assert controller.selected_result_projection.content_state is ResultContentState.PARTIAL
    partial_path = (
        DetectRunRepository(app_data, controller.active_collection.ref.collection_id).result_path(
            partial_run.artifact_id
        )
        / "result.json"
    )
    partial_bytes = partial_path.read_bytes()

    controller.set_inventory_decision(
        "recordings/BROKEN.wav",
        is_folder=False,
        decision=InclusionDecision.EXCLUDED,
    )
    assert controller.inputs_ready
    controller.start_detection(DetectionSettings(1.0, 50, 0, 4))
    empty_run = _wait_terminal(qtbot, controller)
    empty_result = controller.current_result
    assert empty_result.failed_files == 0
    assert empty_result.candidate_count == 0
    assert controller.selected_result_projection.content_state is ResultContentState.EMPTY

    controller.select_result(partial_result.result_id)
    controller.shutdown()

    missing = tmp_path / "source-offline"
    source.rename(missing)
    reopened = DetectWorkspaceController(app_data)
    assert reopened.selected_result_projection.source_state is ResultSourceState.UNAVAILABLE
    reopened.select_result(partial_result.result_id)
    page = DetectWorkspacePage(reopened)
    qtbot.addWidget(page)
    page.resize(1180, 790)
    page.show()
    page._set_route("results")
    qtbot.waitUntil(lambda: page.result_explorer.current_state_key == "source-unavailable")
    assert page.result_explorer.provenance_card.isVisible()
    candidate_recording_row = next(
        index
        for index, recording in enumerate(reopened.selected_result_projection.recordings)
        if recording.candidates
    )
    page.result_explorer.recording_table.setCurrentIndex(
        page.result_explorer.recording_model.index(candidate_recording_row, 0)
    )
    assert page.result_explorer.candidate_model.rowCount() > 0
    assert not page.result_explorer.show_source_button.isEnabled()
    normal = tmp_path / "results-unavailable-normal.png"
    assert page.grab().save(str(normal), "PNG") and normal.stat().st_size > 10_000
    page.resize(700, 780)
    qtbot.waitUntil(lambda: page.is_compact)
    qtbot.waitUntil(lambda: page.content_scroll.horizontalScrollBar().maximum() == 0)
    compact = tmp_path / "results-unavailable-compact.png"
    assert page.grab().save(str(compact), "PNG") and compact.stat().st_size > 10_000
    assert partial_path.read_bytes() == partial_bytes

    empty_path = (
        DetectRunRepository(app_data, reopened.active_collection.ref.collection_id).result_path(
            empty_run.artifact_id
        )
        / "result.json"
    )
    empty_path.write_bytes(b"{corrupt")
    reopened.refresh()
    reopened.select_result(empty_result.result_id)
    page._set_route("results")
    assert page.result_explorer.current_state_key == "result-error"
    assert "unavailable" in page.result_explorer.state_title.text().casefold()
    assert page.result_explorer.result_error_state.title_widget.isVisible()
    assert reopened.current_run.error_code == "publication_invalid"
    assert partial_path.read_bytes() == partial_bytes
    assert reopened.wait_for_model(30_000)
    reopened.shutdown()


@contextmanager
def _detection_failure_case(qtbot, genuine_cnn, app_data: Path, *, delay: float = 0):
    controller = DetectWorkspaceController(app_data, worker_step_delay_seconds=delay)
    _select_inputs(qtbot, controller, genuine_cnn.model.root, genuine_cnn.root)
    repository = DetectRunRepository(app_data, controller.active_collection.ref.collection_id)
    try:
        yield controller, repository
    finally:
        controller.shutdown()


@pytest.mark.qt
def test_changed_wav_after_detection_freeze_publishes_no_result(qtbot, genuine_cnn, tmp_path):
    """Case: IT-DET-014."""
    with _detection_failure_case(qtbot, genuine_cnn, tmp_path / "stale-data", delay=0.05) as (
        controller,
        repository,
    ):
        controller.start_detection(DetectionSettings(0.5, 50, 0, 1))
        stale_path = genuine_cnn.root / "recordings" / "REC_A.wav"
        original = stale_path.read_bytes()
        stale_path.write_bytes(original + b"changed")
        try:
            record = _wait_terminal(qtbot, controller)
            assert record.status is DetectRunStatus.FAILED
            assert record.error_code == "input_changed"
            assert not repository.result_path(record.artifact_id).exists()
        finally:
            stale_path.write_bytes(original)


@pytest.mark.qt
def test_cancelled_detection_publishes_no_result(qtbot, genuine_cnn, tmp_path):
    """Case: IT-DET-014."""
    with _detection_failure_case(qtbot, genuine_cnn, tmp_path / "cancel-data", delay=0.2) as (
        controller,
        repository,
    ):
        controller.start_detection(DetectionSettings(0.5, 50, 0, 1))
        qtbot.waitUntil(lambda: controller.is_run_active, timeout=10_000)
        controller.cancel_active_run()
        record = _wait_terminal(qtbot, controller)
        assert record.status is DetectRunStatus.CANCELLED
        assert not repository.result_path(record.artifact_id).exists()


@pytest.mark.qt
def test_detection_publication_collision_preserves_existing_output(qtbot, genuine_cnn, tmp_path):
    """Case: IT-DET-014."""
    with _detection_failure_case(qtbot, genuine_cnn, tmp_path / "collision-data") as (
        controller,
        repository,
    ):
        request = controller.freeze_detection_request(DetectionSettings(0.5, 50, 0, 1))
        collision = repository.result_path(request.artifact_id)
        collision.mkdir()
        marker = collision / "existing.txt"
        marker.write_text("existing\n")
        controller.start_detection_request(request)
        record = _wait_terminal(qtbot, controller)
        assert record.status is DetectRunStatus.FAILED
        assert record.error_code == "publication_failed"
        assert marker.read_text() == "existing\n"
        assert not (repository.run_directory(record.run_id) / "receipt.json").exists()
        assert not repository.staging_path(record.launch_id).exists()


@pytest.mark.qt
def test_invalid_detection_receipt_publishes_no_result(qtbot, genuine_cnn, tmp_path):
    """Case: IT-DET-014."""
    with _detection_failure_case(qtbot, genuine_cnn, tmp_path / "receipt-data", delay=0.2) as (
        controller,
        repository,
    ):
        controller.start_detection(DetectionSettings(0.5, 50, 0, 1))
        qtbot.waitUntil(lambda: controller.current_run is not None, timeout=10_000)
        receipt_path = repository.run_directory(controller.current_run.run_id) / "receipt.json"
        receipt_path.write_text("{}\n")
        record = _wait_terminal(qtbot, controller)
        assert record.status is DetectRunStatus.FAILED
        assert record.error_code == "publication_failed"
        assert receipt_path.read_text() == "{}\n"
        assert not repository.result_path(record.artifact_id).exists()
        assert not repository.staging_path(record.launch_id).exists()


@pytest.mark.qt
def test_crashed_detection_publishes_no_result(qtbot, genuine_cnn, tmp_path):
    """Case: IT-DET-014."""
    with _detection_failure_case(qtbot, genuine_cnn, tmp_path / "crash-data", delay=0.2) as (
        controller,
        repository,
    ):
        controller.start_detection(DetectionSettings(0.5, 50, 0, 1))
        qtbot.waitUntil(
            lambda: controller.run_process is not None and controller.run_process.processId() > 0,
            timeout=10_000,
        )
        controller.run_process.kill()
        record = _wait_terminal(qtbot, controller)
        assert record.status is DetectRunStatus.INTERRUPTED
        assert not repository.result_path(record.artifact_id).exists()


@pytest.mark.qt
def test_model_replacement_after_freeze_is_rejected_before_result(
    qapp, qtbot, genuine_cnn, tmp_path
):
    """Case: IT-DET-014."""
    copied = tmp_path / "copied-collection"
    shutil.copytree(genuine_cnn.root, copied)
    model_root = copied / ".alpaca" / "models" / genuine_cnn.model.model_id
    app_data = tmp_path / "model-stale-data"
    controller = DetectWorkspaceController(app_data, worker_step_delay_seconds=0.1)
    _select_inputs(qtbot, controller, model_root, copied)
    controller.start_detection(DetectionSettings(0.5, 50, 0, 1))
    manifest = json.loads((model_root / "model.json").read_text())
    artifact = model_root / manifest["artifact"]["path"]
    original = artifact.read_bytes()
    artifact.write_bytes(bytes([original[0] ^ 0xFF]) + original[1:])
    record = _wait_terminal(qtbot, controller)
    assert record.status is DetectRunStatus.FAILED
    assert record.error_code == "model_changed"
    repository = DetectRunRepository(app_data, controller.active_collection.ref.collection_id)
    assert not repository.result_path(record.artifact_id).exists()
    controller.shutdown()


def _canonical_rf_reference(raw: dict[str, float], *, n_mfcc: int) -> dict[str, float]:
    robust = (
        "Dur 90% (s)",
        "Dur 50% (s)",
        "Center Freq (Hz)",
        "Freq 5% (Hz)",
        "Freq 25% (Hz)",
        "Freq 75% (Hz)",
        "Freq 95% (Hz)",
        "BW 50% (Hz)",
        "BW 90% (Hz)",
        "Avg Entropy (bits)",
        "Agg Entropy (bits)",
    )
    mapped = {name: raw[name] for name in robust}
    for toolbox_prefix, canonical_prefix in (
        ("MFCC", "mfcc"),
        ("ΔMFCC", "d_mfcc"),
        ("ΔΔMFCC", "dd_mfcc"),
    ):
        for coefficient in range(1, n_mfcc + 1):
            mapped[f"{canonical_prefix}{coefficient}_mean"] = raw[
                f"{toolbox_prefix} {coefficient:02d} mean"
            ]
            mapped[f"{canonical_prefix}{coefficient}_std"] = raw[
                f"{toolbox_prefix} {coefficient:02d} std"
            ]
    return mapped


@pytest.mark.qt
def test_real_rf_reference_probability_persists_independent_native_derived_result(
    qapp, qtbot, genuine_cnn, genuine_rf, tmp_path
):
    """Cases: IT-DET-017, IT-STU-009, IT-SIZE-002."""
    source = tmp_path / "rf-result-source"
    shutil.copytree(genuine_cnn.root / "recordings", source / "recordings")
    app_data = tmp_path / "application-data"
    controller = DetectWorkspaceController(app_data)
    _select_inputs(qtbot, controller, genuine_cnn.model.root, source)
    controller.start_detection(DetectionSettings(0.0, 0, 0, 4))
    parent_run = _wait_terminal(qtbot, controller)
    assert parent_run.status is DetectRunStatus.COMPLETED
    parent = controller.current_result
    assert parent is not None and parent.candidate_count > 0
    repository = DetectRunRepository(app_data, parent.collection_id)
    parent_path = repository.result_path(parent.result_id) / "result.json"
    parent_bytes = parent_path.read_bytes()
    source_bytes = {
        path.relative_to(source).as_posix(): path.read_bytes()
        for path in (source / "recordings").glob("*.wav")
    }

    controller.choose_refinement_model_root(str(genuine_rf.root))
    qtbot.waitUntil(
        lambda: controller.refinement_model_state is ModelIntakeState.COMPATIBLE,
        timeout=30_000,
    )
    assert controller.refinement_model_reference is not None
    assert controller.refinement_model_reference.snapshot.family is ModelFamily.RANDOM_FOREST
    rf_reference = controller.refinement_model_reference

    rf_estimate = controller.estimate_refinement_storage()
    assert rf_estimate.expected_final.kind == "range"
    controller._capacity_probe = lambda path, label: CapacityObservation(
        label,
        "tight-rf-volume",
        700 * 1024**2,
        datetime(2026, 11, 3, tzinfo=UTC),
    )
    tight = controller.estimate_refinement_storage()
    before_runs = controller.runs
    with pytest.raises(StoragePreflightError, match="confirmation"):
        controller.start_refinement(storage_digest=tight.input_digest)
    assert controller.runs == before_runs
    assert controller.run_process is None
    controller._capacity_probe = query_filesystem_capacity
    controller.start_refinement()
    child_run = _wait_terminal(qtbot, controller)
    assert child_run.status is DetectRunStatus.COMPLETED
    child = repository.load_derived_result(child_run)
    child.verify_parent(parent)
    assert child.parent_result_id == parent.result_id
    assert child.parent_result_digest == parent.result_digest
    assert child.result_id != parent.result_id
    assert child.candidate_count == parent.candidate_count
    assert child.accepted_count + child.rejected_count + child.unscored_count == (
        parent.candidate_count
    )
    assert repository.load_detection_result(parent_run) == parent
    assert parent_path.read_bytes() == parent_bytes
    assert source_bytes == {
        path.relative_to(source).as_posix(): path.read_bytes()
        for path in (source / "recordings").glob("*.wav")
    }

    scored = next(
        candidate
        for recording in child.recordings
        for candidate in recording.candidates
        if candidate.status is not RefinementStatus.UNSCORED
    )
    parent_recording = next(
        recording
        for recording in parent.recordings
        if recording.recording_ref == scored.recording_ref
    )
    config = dict(rf_reference.snapshot.rf_feature_config)
    source_path = source / parent_recording.recording_key
    observed = extract_candidate_features(
        source_path,
        source_sample_rate_hz=parent_recording.sample_rate_hz,
        source_frame_count=parent_recording.frame_count,
        start_frame=scored.start_frame,
        end_frame=scored.end_frame,
        snapshot=rf_reference.snapshot,
    )
    assert observed is not None

    signal = np.asarray(load_audio_file(str(source_path), sample_rate=None, mono=True)[0])
    target_rate = int(config["sample_rate_hz"])
    if parent_recording.sample_rate_hz != target_rate:
        signal = np.asarray(
            librosa.resample(
                signal,
                orig_sr=parent_recording.sample_rate_hz,
                target_sr=target_rate,
                res_type="soxr_hq",
                fix=True,
                scale=False,
            ),
            dtype=np.float32,
        )
        signal = signal[
            : round(parent_recording.frame_count * target_rate / parent_recording.sample_rate_hz)
        ]
    start = round(scored.start_frame * target_rate / parent_recording.sample_rate_hz)
    end = round(scored.end_frame * target_rate / parent_recording.sample_rate_hz)
    segment = signal[start:end]
    minimum = round(target_rate * float(config["min_duration_s"]))
    assert segment.shape[0] >= minimum
    raw = compute_rf_features(
        segment,
        target_rate,
        0.0,
        segment.shape[0] / target_rate,
        low_hz=float(config["fmin_hz"]),
        high_hz=float(config["fmax_hz"]),
        n_fft=int(config["n_fft"]),
        hop_length=int(config["hop_length"]),
        n_mfcc=int(config["n_mfcc"]),
        include_deltas=bool(config["include_deltas"]),
        window="hann",
        center=True,
    )
    expected = _canonical_rf_reference(raw, n_mfcc=int(config["n_mfcc"]))
    assert tuple(expected) == rf_reference.snapshot.rf_feature_names
    assert observed == pytest.approx(expected, rel=0, abs=1e-10)
    estimator = joblib.load(rf_reference.root / rf_reference.snapshot.artifact_relative_path)
    vector = np.asarray([[expected[name] for name in expected]], dtype=np.float64)
    target_column = list(map(int, estimator.classes_)).index(1)
    reference_score = float(estimator.predict_proba(vector)[0, target_column])
    assert scored.rf_target_score == pytest.approx(reference_score, rel=0, abs=1e-12)
    evidence_value = os.environ.get("BIOCALL_ST09_EVIDENCE_DIR")
    if evidence_value:
        evidence = Path(evidence_value)
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "rf-reference.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "source_recording_key": parent_recording.recording_key,
                    "source_sha256": parent_recording.source_sha256,
                    "source_sample_rate_hz": parent_recording.sample_rate_hz,
                    "source_frame_count": parent_recording.frame_count,
                    "candidate_id": scored.candidate_id,
                    "candidate_start_frame": scored.start_frame,
                    "candidate_end_frame": scored.end_frame,
                    "toolbox_revision": rf_reference.snapshot.source_revision,
                    "feature_family": rf_reference.snapshot.rf_feature_family,
                    "feature_config": config,
                    "ordered_feature_names": list(expected),
                    "ordered_feature_values": list(expected.values()),
                    "estimator_classes": list(map(int, estimator.classes_)),
                    "target_probability_column": target_column,
                    "reference_target_probability": reference_score,
                    "derived_result_target_probability": scored.rf_target_score,
                    "saved_threshold": child.threshold,
                    "decision": scored.status.value,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    page = DetectWorkspacePage(controller)
    qtbot.addWidget(page)
    page.resize(1180, 790)
    page.show()
    page._set_route("results")
    explorer = page.result_explorer
    assert explorer.history_select.count() == 2
    assert {hint.accessibleName() for hint in page.findChildren(HelpHint)} >= {
        "More about RF refinement"
    }
    assert explorer.provenance_badge.text() == "Refined"
    assert explorer.lineage_label.text() == (
        "Calls from an original result checked with a Random Forest model."
    )
    assert explorer.candidate_model.refinement_visible
    explorer.history_select.control.setFocus()
    qtbot.keyClick(explorer.history_select.control, Qt.Key.Key_Down)
    assert controller.selected_result_id == parent.result_id
    assert not explorer.candidate_model.refinement_visible
    qtbot.keyClick(explorer.history_select.control, Qt.Key.Key_Up)
    assert controller.selected_result_id == child.result_id
    assert explorer.candidate_model.refinement_visible
    controller.select_result(parent.result_id)
    assert not explorer.candidate_model.refinement_visible
    controller.select_result(child.result_id)
    evidence_value = os.environ.get("BIOCALL_ST09_EVIDENCE_DIR")
    if evidence_value:
        evidence = Path(evidence_value)
        evidence.mkdir(parents=True, exist_ok=True)
        for result_id, label in (
            (parent.result_id, "results-original"),
            (child.result_id, "results-refined"),
        ):
            controller.select_result(result_id)
            candidate_row = next(
                index
                for index, recording in enumerate(controller.selected_result_projection.recordings)
                if recording.candidates
            )
            explorer.recording_table.setCurrentIndex(
                explorer.recording_model.index(candidate_row, 0)
            )
            page.resize(1180, 790)
            qtbot.waitUntil(lambda: not page.is_compact)
            page.content_scroll.verticalScrollBar().setValue(0)
            normal = evidence / f"{label}-normal.png"
            assert page.grab().save(str(normal), "PNG") and normal.stat().st_size > 10_000
            page.content_scroll.verticalScrollBar().setValue(
                page.content_scroll.verticalScrollBar().maximum()
            )
            normal_detail = evidence / f"{label}-detail-normal.png"
            assert (
                page.grab().save(str(normal_detail), "PNG")
                and normal_detail.stat().st_size > 10_000
            )
            page.content_scroll.verticalScrollBar().setValue(
                page.content_scroll.verticalScrollBar().maximum() * 3 // 5
            )
            normal_intervals = evidence / f"{label}-intervals-normal.png"
            assert (
                page.grab().save(str(normal_intervals), "PNG")
                and normal_intervals.stat().st_size > 10_000
            )
            page.resize(700, 780)
            qtbot.waitUntil(lambda: page.is_compact)
            qtbot.waitUntil(lambda: page.content_scroll.horizontalScrollBar().maximum() == 0)
            page.content_scroll.verticalScrollBar().setValue(0)
            compact = evidence / f"{label}-compact.png"
            assert page.grab().save(str(compact), "PNG") and compact.stat().st_size > 10_000
            page.content_scroll.verticalScrollBar().setValue(
                page.content_scroll.verticalScrollBar().maximum()
            )
            compact_detail = evidence / f"{label}-detail-compact.png"
            assert (
                page.grab().save(str(compact_detail), "PNG")
                and compact_detail.stat().st_size > 10_000
            )
            page.content_scroll.verticalScrollBar().setValue(
                page.content_scroll.verticalScrollBar().maximum() * 3 // 5
            )
            compact_intervals = evidence / f"{label}-intervals-compact.png"
            assert (
                page.grab().save(str(compact_intervals), "PNG")
                and compact_intervals.stat().st_size > 10_000
            )
    controller.shutdown()


@pytest.mark.qt
def test_rf_wrong_model_unscored_cancel_crash_stale_and_publication_are_atomic(
    qapp, qtbot, genuine_cnn, genuine_rf, tmp_path
):
    """Case: IT-DET-018."""
    source = tmp_path / "rf-failure-source"
    shutil.copytree(genuine_cnn.root / "recordings", source / "recordings")
    app_data = tmp_path / "application-data"
    controller = DetectWorkspaceController(app_data)
    _select_inputs(qtbot, controller, genuine_cnn.model.root, source)

    reference = inspect_model_directory(genuine_cnn.model.root)
    candidate_scores = []
    for path in sorted((source / "recordings").glob("*.wav")):
        if path.name == "BROKEN.wav":
            continue
        candidate_scores.extend(
            item.target_score
            for item in predict_recording_windows(reference, path, DetectionSettings(0.0, 0, 0, 4))
        )
    controller.start_detection(DetectionSettings(max(candidate_scores), 0, 0, 4))
    parent_run = _wait_terminal(qtbot, controller)
    assert parent_run.status is DetectRunStatus.COMPLETED
    parent = controller.current_result
    assert parent is not None and parent.candidate_count > 0
    repository = DetectRunRepository(app_data, parent.collection_id)
    parent_path = repository.result_path(parent.result_id) / "result.json"
    parent_bytes = parent_path.read_bytes()

    bad_train = tmp_path / "bad-train"
    bad_models = bad_train / ".alpaca" / "models"
    bad_models.mkdir(parents=True)
    shutil.copy2(genuine_cnn.root / ".alpaca" / "collection.json", bad_train / ".alpaca")
    bad_rf = bad_models / genuine_rf.model_id
    shutil.copytree(genuine_rf.root, bad_rf)
    manifest_path = bad_rf / "model.json"
    manifest = json.loads(manifest_path.read_text())
    names = manifest["random_forest"]["features"]["names"]
    names[0], names[1] = names[1], names[0]
    manifest_path.write_text(json.dumps(manifest, sort_keys=True))
    controller.choose_refinement_model_root(str(bad_rf))
    qtbot.waitUntil(
        lambda: controller.refinement_model_state is ModelIntakeState.INCOMPATIBLE,
        timeout=30_000,
    )
    assert "schema" in controller.refinement_model_reason.casefold()
    assert parent_path.read_bytes() == parent_bytes

    controller.choose_refinement_model_root(str(genuine_rf.root))
    qtbot.waitUntil(
        lambda: controller.refinement_model_state is ModelIntakeState.COMPATIBLE,
        timeout=30_000,
    )
    controller.start_refinement()
    unscored_run = _wait_terminal(qtbot, controller)
    assert unscored_run.status is DetectRunStatus.COMPLETED
    child = repository.load_derived_result(unscored_run)
    assert child.unscored_count > 0
    assert {
        candidate.unscored_reason
        for recording in child.recordings
        for candidate in recording.candidates
        if candidate.status is RefinementStatus.UNSCORED
    } == {"short_segment"}
    assert parent_path.read_bytes() == parent_bytes

    page = DetectWorkspacePage(controller)
    qtbot.addWidget(page)
    page.resize(1180, 790)
    page.show()
    page._set_route("results")
    explorer = page.result_explorer
    unscored_recording_id = next(
        recording.recording_ref
        for recording in child.recordings
        if any(candidate.status is RefinementStatus.UNSCORED for candidate in recording.candidates)
    )
    unscored_row = explorer.recording_model.row_for_id(unscored_recording_id)
    explorer.recording_table.setCurrentIndex(explorer.recording_model.index(unscored_row, 0))
    unscored_candidate_row = next(
        row
        for row, candidate in enumerate(explorer.candidate_model.visible_candidates)
        if candidate.refinement_status is RefinementStatus.UNSCORED
    )
    assert (
        explorer.candidate_model.data(explorer.candidate_model.index(unscored_candidate_row, 3))
        == "Could not assess"
    )
    explorer.candidate_table.setCurrentIndex(
        explorer.candidate_model.index(unscored_candidate_row, 0)
    )
    assert "shorter" in explorer.candidate_detail_refinement.text()
    evidence_value = os.environ.get("BIOCALL_ST09_EVIDENCE_DIR")
    if evidence_value:
        evidence = Path(evidence_value)
        evidence.mkdir(parents=True, exist_ok=True)
        page.content_scroll.verticalScrollBar().setValue(
            page.content_scroll.verticalScrollBar().maximum() * 3 // 5
        )
        unscored_image = evidence / "results-refined-unscored-normal.png"
        assert (
            page.grab().save(str(unscored_image), "PNG") and unscored_image.stat().st_size > 10_000
        )

    controller.select_result(parent.result_id)
    controller._worker_step_delay_seconds = 0.2
    controller.start_refinement()
    qtbot.waitUntil(lambda: controller.is_run_active, timeout=10_000)
    controller.cancel_active_run()
    cancelled = _wait_terminal(qtbot, controller)
    assert cancelled.status is DetectRunStatus.CANCELLED
    assert not repository.result_path(cancelled.artifact_id).exists()
    assert parent_path.read_bytes() == parent_bytes

    controller.start_refinement()
    qtbot.waitUntil(
        lambda: controller.run_process is not None and controller.run_process.processId() > 0,
        timeout=10_000,
    )
    controller.run_process.kill()
    crashed = _wait_terminal(qtbot, controller)
    assert crashed.status is DetectRunStatus.INTERRUPTED
    assert not repository.result_path(crashed.artifact_id).exists()
    assert parent_path.read_bytes() == parent_bytes

    request = controller.freeze_refinement_request()
    collision = repository.result_path(request.artifact_id)
    collision.mkdir()
    marker = collision / "existing.txt"
    marker.write_text("existing\n")
    controller.start_refinement_request(request)
    failed = _wait_terminal(qtbot, controller)
    assert failed.status is DetectRunStatus.FAILED
    assert failed.error_code == "publication_failed"
    assert marker.read_text() == "existing\n"
    assert not repository.staging_path(failed.launch_id).exists()
    assert parent_path.read_bytes() == parent_bytes

    changed_key = next(
        recording.recording_key for recording in parent.recordings if recording.candidates
    )
    changed_path = source / changed_key
    unchanged = changed_path.read_bytes()
    original_stat = changed_path.stat()
    controller.start_refinement()
    changed_path.unlink()
    missing = _wait_terminal(qtbot, controller)
    assert missing.status is DetectRunStatus.FAILED
    assert missing.error_code == "input_changed"
    assert not repository.result_path(missing.artifact_id).exists()
    assert parent_path.read_bytes() == parent_bytes
    changed_path.write_bytes(unchanged)
    os.utime(
        changed_path,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )

    controller.start_refinement()
    changed_path.write_bytes(unchanged + b"changed")
    stale = _wait_terminal(qtbot, controller)
    assert stale.status is DetectRunStatus.FAILED
    assert stale.error_code == "input_changed"
    assert not repository.result_path(stale.artifact_id).exists()
    assert parent_path.read_bytes() == parent_bytes
    changed_path.write_bytes(unchanged)
    controller.shutdown()
