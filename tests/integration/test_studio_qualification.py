from __future__ import annotations

import hashlib
import shutil
import wave
from pathlib import Path

import joblib
import librosa
import numpy as np
import pytest
from bioacoustics_dl_toolbox.audio import load_audio_file
from bioacoustics_dl_toolbox.rf import compute_rf_features
from PySide6.QtCore import QProcess

from biocall_studio.detect.application.controller import ModelIntakeState
from biocall_studio.detect.application.model_intake import inspect_model_directory
from biocall_studio.detect.application.navigation import DetectRoute
from biocall_studio.detect.domain import RootBindingDecision
from biocall_studio.detect.domain.detection import (
    DetectionSettings,
    merge_candidate_windows,
    predict_recording_windows,
)
from biocall_studio.detect.domain.exports import ExportMode, ExportState, frame_seconds
from biocall_studio.detect.domain.result_views import ResultSourceState
from biocall_studio.detect.domain.rf_refinement import (
    RefinementStatus,
    extract_candidate_features,
)
from biocall_studio.detect.domain.runs import DetectRunRequest, DetectRunStatus
from biocall_studio.detect.persistence.runs import DetectRunRepository
from biocall_studio.detect.workflows.exports import verify_export_directory
from biocall_studio.studio.application.coordinator import StudioCoordinator
from biocall_studio.studio.application.navigation import WorkspaceRoute
from biocall_studio.train.application.collection_scan import scan_collection
from biocall_studio.train.application.workspace import WorkspaceController
from biocall_studio.train.domain.dataset import BuildConfig
from biocall_studio.train.domain.run import RunStatus
from biocall_studio.train.domain.training import (
    DeviceCapabilities,
    TrainingDataset,
    TrainingDraft,
    freeze_training_config,
)
from biocall_studio.train.persistence.collection_metadata import publish_collection_metadata
from biocall_studio.train.persistence.datasets import load_dataset
from biocall_studio.train.persistence.models import load_model

pytestmark = [pytest.mark.integration, pytest.mark.qt]


def _build_config(scan) -> BuildConfig:
    return BuildConfig(
        selected_recording_ids=tuple(record.id for record in scan.records),
        negative_mode="ratio",
        negative_ratio=1.0,
        negative_count=0,
        allocation="proportional",
        train_percent=80,
        balance_classes=True,
        seed=42,
        margin_ms=100,
    )


def _detect_request(controller, token: str) -> DetectRunRequest:
    snapshot = controller.snapshot
    collection = controller.active_collection
    assert snapshot is not None and collection is not None
    return DetectRunRequest.create(
        run_id=f"drun_{token}",
        request_id=f"dreq_{token}",
        launch_id=f"launch_{token}",
        reservation_owner_id=controller.reservation_owner_id,
        collection_id=collection.ref.collection_id,
        binding_revision=collection.ref.binding_revision,
        inventory_id=snapshot.inventory_id,
        inventory_digest=snapshot.digest,
        selected_recording_keys=snapshot.included_keys,
        model_snapshot_id="mdl_0123456789abcdef0123456789abcdef",
        model_digest="b" * 64,
        settings={"fixture_contract": "lifecycle-v1"},
        artifact_id=f"pub_{token}",
    )


def _fast_cnn_draft() -> TrainingDraft:
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


def _fast_rf_draft() -> TrainingDraft:
    draft = TrainingDraft.defaults("rf")
    for key, value in {
        "n_estimators": 12,
        "min_samples_leaf": 1,
        "rf_threshold": 0.55,
        "random_state": 42,
        "n_jobs": 1,
        "feature_config.sample_rate_hz": 8_000,
        "feature_config.min_duration_s": 0.25,
        "feature_config.pad_short_segments": False,
        "feature_config.n_fft": 256,
        "feature_config.hop_length": 64,
        "feature_config.n_mfcc": 4,
        "feature_config.fmin_hz": 100.0,
        "feature_config.fmax_hz": 3_500.0,
    }.items():
        draft.set(key, value)
    return draft


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


def _source_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*.wav"))
        if path.relative_to(root).parts[0] in {"recordings", "positives"}
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_cross_workspace_admission_crash_recovery_and_one_safe_exit_dialog(
    qapp, qtbot, tmp_path: Path, collection_factory, wav_factory
):
    """Case: IT-STU-008."""
    train_root = collection_factory(tmp_path / "train-collection", source_count=2)
    train_scan = publish_collection_metadata(train_root, scan_collection(train_root))
    train = WorkspaceController(
        tmp_path / "settings",
        worker_step_delay_seconds=0.1,
        cancel_grace_ms=150,
        kill_grace_ms=600,
    )
    train.bind_verified_collection(train_root, train_scan.collection_id)
    coordinator = StudioCoordinator(train, detect_data_dir=tmp_path / "application-data")
    qtbot.addWidget(coordinator.shell_window)
    qtbot.addWidget(coordinator.train_window)
    coordinator.start()
    qtbot.waitUntil(lambda: train.scan_result is not None, timeout=10_000)

    detect_root = tmp_path / "detect-source"
    source = wav_factory(detect_root / "recordings" / "dawn.wav", frames=8_000)
    source_bytes = source.read_bytes()
    detect = coordinator.detect_controller
    detect._worker_step_delay_seconds = 0.04
    detect._cancel_grace_ms = 150
    detect._kill_grace_ms = 600
    detect.choose_source_root(str(detect_root))
    qtbot.waitUntil(lambda: detect.snapshot is not None, timeout=10_000)

    first = _detect_request(detect, "1" * 32)
    detect.start_lifecycle_fixture(first, behavior="stubborn")
    qtbot.waitUntil(
        lambda: detect.current_run is not None
        and detect.current_run.status is DetectRunStatus.RUNNING,
        timeout=5_000,
    )
    process = detect.run_process
    assert process is not None and process.state() is not QProcess.ProcessState.NotRunning

    with pytest.raises(ValueError, match="active in Detect"):
        train.start_dataset_build(_build_config(train_scan), dataset_id="must-not-exist")
    assert train.active_run is None
    assert not (train_root / ".alpaca" / "datasets" / "must-not-exist").exists()

    coordinator.open_workspace(WorkspaceRoute.TRAIN)
    coordinator.train_window.close()
    dialog = coordinator.exit_dialog
    assert dialog is not None and dialog.isVisible()
    assert coordinator.train_window.close_dialog is None
    assert dialog.defaultButton().text() == "Keep app open"
    assert len(
        [widget for widget in qapp.topLevelWidgets() if widget.objectName() == "studioExitDialog"]
    ) == 1
    dialog.defaultButton().click()
    assert detect.current_run is not None and detect.current_run.run_id == first.run_id
    assert detect.run_process is process
    assert not detect._shutdown_requested
    assert not train._shutdown_requested

    process.kill()
    qtbot.waitUntil(
        lambda: detect.current_run is not None
        and detect.current_run.status is DetectRunStatus.INTERRUPTED,
        timeout=10_000,
    )
    assert detect.run_process is None

    second = _detect_request(detect, "2" * 32)
    detect.start_lifecycle_fixture(second, behavior="stubborn")
    qtbot.waitUntil(
        lambda: detect.current_run is not None
        and detect.current_run.status is DetectRunStatus.RUNNING,
        timeout=5_000,
    )
    coordinator.show_studio()
    coordinator.shell_window.close()
    dialog = coordinator.exit_dialog
    assert dialog is not None and dialog.isVisible()
    stop = next(button for button in dialog.buttons() if button.text() == "Stop work and Exit")
    stop.click()

    qtbot.waitUntil(lambda: detect._shutdown_finished, timeout=15_000)
    qtbot.waitUntil(lambda: train._shutdown_finished, timeout=15_000)
    assert detect.run_process is None
    assert detect.current_run is not None
    assert detect.current_run.status is DetectRunStatus.CANCELLED
    assert source.read_bytes() == source_bytes
    qtbot.waitUntil(
        lambda: not coordinator.shell_window.isVisible()
        and not coordinator.train_window.isVisible(),
        timeout=5_000,
    )
    assert not coordinator.shell_window.isVisible()
    assert not coordinator.train_window.isVisible()


def test_genuine_studio_train_detect_rf_export_restart_relink_round_trip(
    qtbot, tmp_path: Path, collection_factory
):
    """Cases: IT-STU-007, IT-DET-022."""
    train_root = collection_factory(tmp_path / "qualification-collection", source_count=3)
    train_source_bytes = _source_bytes(train_root)
    scan = publish_collection_metadata(train_root, scan_collection(train_root))
    settings_root = tmp_path / "suite-data" / "train" / "v1"
    suite_root = tmp_path / "suite-data"
    train = WorkspaceController(settings_root)
    train.bind_verified_collection(train_root, scan.collection_id)
    coordinator = StudioCoordinator(train, detect_data_dir=suite_root)
    qtbot.addWidget(coordinator.shell_window)
    qtbot.addWidget(coordinator.train_window)
    coordinator.start()
    coordinator.open_workspace(WorkspaceRoute.TRAIN)
    qtbot.waitUntil(lambda: train.scan_result is not None, timeout=10_000)
    assert coordinator.train_window.isVisible()

    dataset_id = "dataset-st11-qualified"
    dataset_run_id = train.start_dataset_build(_build_config(scan), dataset_id=dataset_id)
    qtbot.waitUntil(
        lambda: any(run.run_id == dataset_run_id and run.terminal for run in train.runs),
        timeout=60_000,
    )
    dataset_run = next(run for run in train.runs if run.run_id == dataset_run_id)
    assert dataset_run.status is RunStatus.COMPLETED
    dataset = load_dataset(train_root, dataset_id)
    training_dataset = TrainingDataset.from_artifact(dataset)
    capabilities = DeviceCapabilities(cuda=False, mps=False, cpu_count=8)

    cnn_config = freeze_training_config(
        _fast_cnn_draft(), training_dataset, capabilities
    )
    cnn_run_id = train.start_training(
        cnn_config,
        model_label="ST-11 qualification CNN",
        model_id="model-st11-cnn",
    )
    qtbot.waitUntil(
        lambda: any(run.run_id == cnn_run_id and run.terminal for run in train.runs),
        timeout=180_000,
    )
    cnn_run = next(run for run in train.runs if run.run_id == cnn_run_id)
    assert cnn_run.status is RunStatus.COMPLETED
    cnn_model = load_model(train_root, "model-st11-cnn")

    rf_config = freeze_training_config(_fast_rf_draft(), training_dataset, capabilities)
    rf_run_id = train.start_training(
        rf_config,
        model_label="ST-11 qualification RF",
        model_id="model-st11-rf",
    )
    qtbot.waitUntil(
        lambda: any(run.run_id == rf_run_id and run.terminal for run in train.runs),
        timeout=180_000,
    )
    rf_run = next(run for run in train.runs if run.run_id == rf_run_id)
    assert rf_run.status is RunStatus.COMPLETED
    rf_model = load_model(train_root, "model-st11-rf")
    assert len({dataset_run_id, cnn_run_id, rf_run_id}) == 3
    assert _source_bytes(train_root) == train_source_bytes

    detect_root = tmp_path / "qualification-detect-source"
    shutil.copytree(train_root / "recordings", detect_root / "recordings")
    detect_source_bytes = _source_bytes(detect_root)
    retained_train_controller = coordinator.controller
    retained_train_window = coordinator.train_window
    coordinator.show_studio()
    coordinator.open_workspace(WorkspaceRoute.DETECT)
    assert coordinator.controller is retained_train_controller
    assert coordinator.train_window is retained_train_window
    detect = coordinator.detect_controller
    detect.choose_model_root(str(cnn_model.root))
    qtbot.waitUntil(
        lambda: detect.model_state is ModelIntakeState.COMPATIBLE,
        timeout=30_000,
    )
    detect.choose_source_root(str(detect_root))
    qtbot.waitUntil(lambda: detect.inputs_ready, timeout=30_000)

    detection_settings = DetectionSettings(0.0, 0, 0, 4)
    detection_run_id = detect.start_detection(detection_settings)
    qtbot.waitUntil(
        lambda: detect.current_run is not None and detect.current_run.terminal,
        timeout=180_000,
    )
    parent_run = detect.current_run
    parent = detect.current_result
    assert parent_run is not None and parent_run.run_id == detection_run_id
    assert parent_run.status is DetectRunStatus.COMPLETED
    assert parent is not None and parent.candidate_count > 0

    cnn_reference = inspect_model_directory(cnn_model.root)
    for recording in parent.recordings:
        assert recording.source_sha256 == _sha256(detect_root / recording.recording_key)
        windows = predict_recording_windows(
            cnn_reference,
            detect_root / recording.recording_key,
            detection_settings,
        )
        expected = merge_candidate_windows(
            windows,
            settings=detection_settings,
            model_sample_rate_hz=cnn_reference.snapshot.sample_rate_hz,
            source_sample_rate_hz=recording.sample_rate_hz,
            source_frame_count=recording.frame_count,
        )
        assert [
            (item.start_frame, item.end_frame, item.contributing_windows)
            for item in recording.candidates
        ] == [(start, end, count) for start, end, _score, count in expected]
        assert [item.max_target_score for item in recording.candidates] == pytest.approx(
            [score for _start, _end, score, _count in expected], rel=0, abs=1e-12
        )

    repository = DetectRunRepository(suite_root, parent.collection_id)
    parent_path = repository.result_path(parent.result_id) / "result.json"
    parent_bytes = parent_path.read_bytes()
    detect.choose_refinement_model_root(str(rf_model.root))
    qtbot.waitUntil(
        lambda: detect.refinement_model_state is ModelIntakeState.COMPATIBLE,
        timeout=30_000,
    )
    refinement_run_id = detect.start_refinement()
    qtbot.waitUntil(
        lambda: detect.current_run is not None
        and detect.current_run.run_id == refinement_run_id
        and detect.current_run.terminal,
        timeout=180_000,
    )
    refinement_run = detect.current_run
    assert refinement_run is not None
    assert refinement_run.status is DetectRunStatus.COMPLETED
    child = repository.load_derived_result(refinement_run)
    child.verify_parent(parent)
    assert child.result_id != parent.result_id
    assert child.parent_result_digest == parent.result_digest
    assert parent_path.read_bytes() == parent_bytes

    scored = next(
        candidate
        for recording in child.recordings
        for candidate in recording.candidates
        if candidate.status is not RefinementStatus.UNSCORED
    )
    source_recording = next(
        recording
        for recording in parent.recordings
        if recording.recording_ref == scored.recording_ref
    )
    rf_reference = detect.refinement_model_reference
    assert rf_reference is not None
    feature_config = dict(rf_reference.snapshot.rf_feature_config)
    source_path = detect_root / source_recording.recording_key
    observed_features = extract_candidate_features(
        source_path,
        source_sample_rate_hz=source_recording.sample_rate_hz,
        source_frame_count=source_recording.frame_count,
        start_frame=scored.start_frame,
        end_frame=scored.end_frame,
        snapshot=rf_reference.snapshot,
    )
    assert observed_features is not None
    signal = np.asarray(load_audio_file(str(source_path), sample_rate=None, mono=True)[0])
    target_rate = int(feature_config["sample_rate_hz"])
    if source_recording.sample_rate_hz != target_rate:
        signal = np.asarray(
            librosa.resample(
                signal,
                orig_sr=source_recording.sample_rate_hz,
                target_sr=target_rate,
                res_type="soxr_hq",
                fix=True,
                scale=False,
            ),
            dtype=np.float32,
        )
        signal = signal[
            : round(
                source_recording.frame_count
                * target_rate
                / source_recording.sample_rate_hz
            )
        ]
    start = round(scored.start_frame * target_rate / source_recording.sample_rate_hz)
    end = round(scored.end_frame * target_rate / source_recording.sample_rate_hz)
    segment = signal[start:end]
    raw_features = compute_rf_features(
        segment,
        target_rate,
        0.0,
        segment.shape[0] / target_rate,
        low_hz=float(feature_config["fmin_hz"]),
        high_hz=float(feature_config["fmax_hz"]),
        n_fft=int(feature_config["n_fft"]),
        hop_length=int(feature_config["hop_length"]),
        n_mfcc=int(feature_config["n_mfcc"]),
        include_deltas=bool(feature_config["include_deltas"]),
        window="hann",
        center=True,
    )
    expected_features = _canonical_rf_reference(
        raw_features, n_mfcc=int(feature_config["n_mfcc"])
    )
    assert tuple(expected_features) == rf_reference.snapshot.rf_feature_names
    assert observed_features == pytest.approx(expected_features, rel=0, abs=1e-10)
    estimator = joblib.load(
        rf_reference.root / rf_reference.snapshot.artifact_relative_path
    )
    classes = tuple(map(int, estimator.classes_))
    assert classes == tuple(rf_model.manifest["random_forest"]["estimator"]["classes"])
    target_column = classes.index(1)
    assert target_column == rf_reference.snapshot.rf_probability_column
    vector = np.asarray(
        [[expected_features[name] for name in expected_features]], dtype=np.float64
    )
    reference_score = float(estimator.predict_proba(vector)[0, target_column])
    assert scored.rf_target_score == pytest.approx(reference_score, rel=0, abs=1e-12)

    detect.select_result(child.result_id)
    detect.set_candidate_selected(scored.candidate_id, True)
    frozen = detect.prepare_export_plan()
    assert frozen is not None and frozen.candidate_ids == (scored.candidate_id,)
    destination = tmp_path / "qualification-export"
    destination.mkdir()
    detect.start_export(ExportMode.BOTH, destination)
    qtbot.waitUntil(
        lambda: not detect.is_export_active and detect.export_state is ExportState.SUCCESS,
        timeout=30_000,
    )
    snapshot = detect.export_snapshot
    receipt = detect.export_receipt
    assert snapshot is not None and receipt is not None
    assert receipt == verify_export_directory(Path(receipt.final_destination))
    assert receipt.result_id == child.result_id
    assert receipt.parent_result_id == parent.result_id
    assert receipt.snapshot_digest == snapshot.snapshot_digest
    mapping = receipt.snippets[0]
    concat = receipt.concat_mappings[0]
    raven = receipt.raven_rows[0]
    assert (mapping.source_start_frame, mapping.source_end_frame) == (
        scored.start_frame,
        scored.end_frame,
    )
    assert (concat.source_start_frame, concat.source_end_frame) == (
        scored.start_frame,
        scored.end_frame,
    )
    assert (raven.source_start_frame, raven.source_end_frame) == (
        scored.start_frame,
        scored.end_frame,
    )
    assert raven.begin_seconds == frame_seconds(raven.begin_frame, mapping.sample_rate_hz)
    assert raven.end_seconds == frame_seconds(raven.end_frame, mapping.sample_rate_hz)
    final = Path(receipt.final_destination)
    with wave.open(str(source_path), "rb") as source_stream:
        source_stream.setpos(scored.start_frame)
        expected_pcm = source_stream.readframes(scored.end_frame - scored.start_frame)
    with wave.open(str(final / mapping.output_relative_path), "rb") as output_stream:
        assert output_stream.readframes(output_stream.getnframes()) == expected_pcm
    assert mapping.pcm_sha256 == hashlib.sha256(expected_pcm).hexdigest()
    for file_record in receipt.files:
        assert _sha256(final / file_record.relative_path) == file_record.sha256
    tsv = (final / "corpus.Table.1.selections.txt").read_text().splitlines()
    assert len(tsv) == 2
    assert tsv[1].split("\t")[3:5] == [raven.begin_seconds, raven.end_seconds]
    assert tsv[1].split("\t")[7:] == [
        scored.candidate_id,
        source_recording.recording_key,
        str(scored.start_frame),
        str(scored.end_frame),
    ]
    assert _source_bytes(train_root) == train_source_bytes
    assert _source_bytes(detect_root) == detect_source_bytes
    assert len(
        {
            dataset_run_id,
            cnn_run_id,
            rf_run_id,
            detection_run_id,
            refinement_run_id,
            parent.result_id,
            child.result_id,
            receipt.export_id,
        }
    ) == 8

    page = coordinator.shell_window.detect_page
    page._set_route(DetectRoute.EXPORT_NEW)
    assert page.export_page.status_title.text() == "Export completed"
    for width in (1180, 700):
        coordinator.shell_window.resize(width, 790)
        qtbot.waitUntil(lambda width=width: page.is_compact == (width < 820))
        assert coordinator.shell_window.grab().size().width() > 0

    child_path = repository.result_path(child.result_id) / "result.json"
    child_bytes = child_path.read_bytes()
    coordinator.request_application_exit()
    qtbot.waitUntil(lambda: train._shutdown_finished, timeout=10_000)
    qtbot.waitUntil(lambda: detect._shutdown_finished, timeout=10_000)
    qtbot.waitUntil(lambda: not coordinator.shell_window.isVisible(), timeout=5_000)

    relocated = tmp_path / "relocated-detect-source"
    detect_root.rename(relocated)
    reopened_train = WorkspaceController(settings_root)
    reopened = StudioCoordinator(reopened_train, detect_data_dir=suite_root)
    qtbot.addWidget(reopened.shell_window)
    qtbot.addWidget(reopened.train_window)
    reopened.start()
    reopened_detect = reopened.detect_controller
    assert reopened_detect.root_decision is RootBindingDecision.MISSING
    assert {item.result_id for item in reopened_detect.result_history} == {
        parent.result_id,
        child.result_id,
    }
    reopened_detect.choose_source_root(str(relocated))
    assert reopened_detect.proposal is not None
    assert reopened_detect.proposal.decision is RootBindingDecision.AWAITING_CONFIRMATION
    reopened_detect.confirm_relink()
    qtbot.waitUntil(
        lambda: reopened_detect.snapshot is not None
        and reopened_detect.snapshot.binding_revision == 2
        and not reopened_detect.is_scanning,
        timeout=30_000,
    )
    reopened_detect.select_result(child.result_id)
    assert reopened_detect.selected_result_projection is not None
    assert reopened_detect.selected_result_projection.source_state is ResultSourceState.STALE
    assert parent_path.read_bytes() == parent_bytes
    assert child_path.read_bytes() == child_bytes
    assert _source_bytes(relocated) == detect_source_bytes
    assert _source_bytes(train_root) == train_source_bytes
    assert verify_export_directory(final) == receipt
    assert any(item.export_id == receipt.export_id for item in reopened_detect.export_history)
    reopened.request_application_exit()
    qtbot.waitUntil(lambda: reopened_train._shutdown_finished, timeout=10_000)
    qtbot.waitUntil(lambda: reopened_detect._shutdown_finished, timeout=10_000)
