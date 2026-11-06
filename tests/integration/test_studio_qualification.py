from __future__ import annotations

import hashlib
import shutil
from dataclasses import replace
from pathlib import Path

import joblib
import librosa
import numpy as np
import pytest
from bioacoustics_dl_toolbox.audio import load_audio_file
from bioacoustics_dl_toolbox.rf import compute_rf_features
from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

from biocall_studio.detect.application.controller import ModelIntakeState
from biocall_studio.detect.application.model_intake import inspect_model_directory
from biocall_studio.detect.application.navigation import DetectRoute
from biocall_studio.detect.domain import RootBindingDecision
from biocall_studio.detect.domain.detection import (
    DetectionSettings,
    merge_candidate_windows,
    predict_recording_windows,
)
from biocall_studio.detect.domain.result_views import ResultSourceState
from biocall_studio.detect.domain.rf_refinement import (
    RefinementStatus,
    extract_candidate_features,
)
from biocall_studio.detect.domain.runs import DetectRunRequest, DetectRunStatus
from biocall_studio.detect.persistence.runs import DetectRunRepository
from biocall_studio.review.application.controller import default_spectrogram_snapshot
from biocall_studio.review.domain.exports import ReviewExportMode
from biocall_studio.review.domain.intake import (
    REVIEW_INTAKE_SCHEMA_VERSION,
    EligibleCandidate,
    ReviewIntakeManifest,
    ReviewIntakeProjection,
    ReviewRecording,
    ReviewResultKind,
    projection_digest,
)
from biocall_studio.review.domain.sessions import (
    ReviewLabel,
    ReviewSessionSource,
    ReviewSessionState,
)
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


def _button(widget, text: str) -> QPushButton:
    return next(button for button in widget.findChildren(QPushButton) if button.text() == text)


def _click_active_message_button(text: str) -> None:
    dialog = QApplication.activeModalWidget()
    assert isinstance(dialog, QMessageBox)
    _button(dialog, text).click()


def _open_retained_review_session(coordinator: StudioCoordinator, *, source_sha256: str) -> str:
    candidate = EligibleCandidate(
        ordinal=0,
        recording_ordinal=0,
        candidate_id="cand_" + "1" * 32,
        recording_ref="rec_" + "2" * 32,
        recording_key="recordings/dawn.wav",
        source_sha256=source_sha256,
        sample_rate_hz=8_000,
        frame_count=8_000,
        channels=1,
        start_frame=1_000,
        end_frame=2_000,
        start_time_ns=125_000_000,
        end_time_ns=250_000_000,
        cnn_target_score=0.9,
        rf_target_score=None,
        contributing_windows=1,
    )
    recording = ReviewRecording(
        ordinal=0,
        recording_ref=candidate.recording_ref,
        recording_key=candidate.recording_key,
        source_sha256=candidate.source_sha256,
        sample_rate_hz=candidate.sample_rate_hz,
        frame_count=candidate.frame_count,
        channels=candidate.channels,
        failed=False,
        error_code="",
        eligible_candidate_count=1,
    )
    manifest = ReviewIntakeManifest(
        schema_version=REVIEW_INTAKE_SCHEMA_VERSION,
        projection_digest="0" * 64,
        result_kind=ReviewResultKind.CNN,
        collection_id="det_" + "3" * 32,
        result_id="pub_" + "4" * 32,
        result_digest="5" * 64,
        publication_digest="6" * 64,
        parent_result_id=None,
        parent_result_digest=None,
        binding_revision=1,
        inventory_id="inv_" + "7" * 32,
        inventory_digest="8" * 64,
        source_time_semantics=(
            "zero_based_half_open_source_frames_with_integer_nanosecond_projection"
        ),
        recording_count=1,
        failed_recording_count=0,
        eligible_candidate_count=1,
    )
    manifest = replace(
        manifest,
        projection_digest=projection_digest(manifest, (recording,), (candidate,)),
    )
    projection = ReviewIntakeProjection(manifest, (recording,), (candidate,))
    settings = default_spectrogram_snapshot()
    session = coordinator.review_controller.store.create_session(
        name="Retained qualification review",
        source=ReviewSessionSource.from_projection(
            projection,
            score_semantics="binary_softmax_target_output_index_1; not_a_calibrated_probability",
            eligibility_threshold=0.5,
        ),
        candidates=(candidate,),
        settings=settings,
        owner_id=coordinator.review_controller.owner_id,
        created_at="2026-11-06T09:00:00.000Z",
        session_id="rsn_" + "a" * 32,
    )
    coordinator.review_page.open_session(session.session_id)
    return session.session_id


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
    review_session_id = _open_retained_review_session(
        coordinator,
        source_sha256=_sha256(source),
    )
    coordinator.open_workspace(WorkspaceRoute.DETECT)

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
    assert dialog.text() == "A Review session is still open. Save and exit?"
    assert "Lifecycle boundary check in Detect" in dialog.informativeText()
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
    assert dialog.text() == "A Review session is still open. Save and exit?"
    stop = next(button for button in dialog.buttons() if button.text() == "Save and Exit")
    stop.click()

    qtbot.waitUntil(lambda: detect._shutdown_finished, timeout=15_000)
    qtbot.waitUntil(lambda: train._shutdown_finished, timeout=15_000)
    assert detect.run_process is None
    assert detect.current_run is not None
    assert detect.current_run.status is DetectRunStatus.CANCELLED
    assert (
        coordinator.review_controller.store.get_session(review_session_id).state
        is ReviewSessionState.CLOSED
    )
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
    assert not hasattr(detect, "prepare_export_plan")
    assert not hasattr(detect, "start_export")
    assert not hasattr(detect, "set_candidate_selected")
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
        }
    ) == 7

    page = coordinator.shell_window.detect_page
    page._set_route(DetectRoute.RESULTS)
    assert not hasattr(page.result_explorer, "export_button")
    for width in (1180, 700):
        coordinator.shell_window.resize(width, 790)
        qtbot.waitUntil(lambda width=width: page.is_compact == (width < 820))
        assert coordinator.shell_window.grab().size().width() > 0

    child_path = repository.result_path(child.result_id) / "result.json"
    child_bytes = child_path.read_bytes()
    coordinator.open_workspace(WorkspaceRoute.REVIEW)
    review_page = coordinator.review_page
    review_page.show_landing()
    choices = coordinator._review_result_choices()
    assert {choice.result_id for choice in choices} == {parent.result_id, child.result_id}
    parent_choice = next(choice for choice in choices if choice.result_id == parent.result_id)
    child_choice = next(choice for choice in choices if choice.result_id == child.result_id)
    assert parent_choice.eligible_count == parent.candidate_count
    assert child_choice.eligible_count == sum(
        candidate.status is RefinementStatus.ACCEPTED
        for recording in child.recordings
        for candidate in recording.candidates
    )
    settings = coordinator.review_controller.list_presets()[0]
    review_page._start_session(parent_choice, settings)
    assert review_page.current_state is not None
    session_id = review_page.current_state.session.session_id
    assert review_page.current_state.session.eligible_candidate_count >= 3

    review_page._set_view("one_by_one")
    assert review_page.session_page.spectrogram.metadata is not None
    assert review_page.session_page.play_button.isEnabled()
    detail_keys = set(review_page.cache.valid_content_keys())
    assert len(detail_keys) == 1

    review_page.show_spectrograms()
    _button(review_page.cache_page, "Generate all").click()
    qtbot.waitUntil(
        lambda: isinstance(QApplication.activeModalWidget(), QMessageBox),
        timeout=10_000,
    )
    _button(QApplication.activeModalWidget(), "Continue").click()
    qtbot.waitUntil(
        lambda: len(review_page.cache.valid_content_keys())
        >= review_page.current_state.session.eligible_candidate_count + 1,
        timeout=30_000,
    )
    qtbot.waitUntil(lambda: review_page.active_operation is None, timeout=10_000)

    review_page.show_session()
    review_page._set_view("one_by_one")
    first_candidate_id = review_page.current_state.current_candidate_id
    review_page._set_label(ReviewLabel.CALL.value)
    second_candidate_id = review_page.current_state.current_candidate_id
    assert second_candidate_id != first_candidate_id
    review_page._set_label(ReviewLabel.NOT_CALL.value)
    assert review_page.current_state.current_candidate_id not in {
        first_candidate_id,
        second_candidate_id,
    }
    QTimer.singleShot(0, lambda: _click_active_message_button("Accept all"))
    review_page._accept_all()
    assert review_page.current_state.session.unreviewed_count == 0
    review_page._undo()
    assert review_page.current_state.session.unreviewed_count > 0
    assert review_page.current_state.session.call_count >= 1
    assert review_page.current_state.session.not_call_count == 1

    QTimer.singleShot(0, lambda: _click_active_message_button("Finalize"))
    review_page._finalize()
    finalized = review_page.current_state.session
    assert finalized.state is ReviewSessionState.FINALIZED
    assert finalized.final_snapshot_digest is not None
    finalization_document = coordinator.review_controller.store.finalization_document(session_id)

    export_parent = tmp_path / "review-exports"
    export_parent.mkdir()
    plan = coordinator.review_controller.plan_export(
        session_id,
        source_root=detect_root,
        destination_parent=export_parent,
        mode=ReviewExportMode.BOTH,
        export_id="rexp_" + "8" * 32,
        created_at="2026-11-06T12:00:00.000Z",
    )
    estimate = coordinator.review_controller.estimate_export_storage(plan)
    outcome = coordinator.review_controller.publish_export(
        plan,
        source_root=detect_root,
        storage_input_digest=estimate.input_digest,
        confirm_storage=estimate.requires_confirmation,
        completed_at="2026-11-06T12:01:00.000Z",
    )
    assert outcome.history_saved
    export_directory = Path(outcome.receipt.final_destination)
    assert (export_directory / "corpus.wav").is_file()
    assert (export_directory / "corpus.Table.1.selections.txt").is_file()
    assert tuple(export_directory.glob("snippets/*.wav"))
    history = coordinator.review_controller.list_export_history()
    assert len(history) == 1
    assert coordinator.review_controller.verify_export_history(history[0]) == outcome.receipt
    assert (
        coordinator.review_controller.store.finalization_document(session_id)
        == finalization_document
    )
    assert parent_path.read_bytes() == parent_bytes
    assert child_path.read_bytes() == child_bytes
    assert _source_bytes(detect_root) == detect_source_bytes

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
    assert not hasattr(reopened_detect, "start_export")
    reopened_review = reopened.review_controller.store.get_session(session_id)
    assert reopened_review.state is ReviewSessionState.FINALIZED
    assert reopened_review.final_snapshot_digest == finalized.final_snapshot_digest
    reopened_history = reopened.review_controller.list_export_history()
    assert len(reopened_history) == 1
    assert reopened.review_controller.verify_export_history(reopened_history[0]) == outcome.receipt
    reopened.request_application_exit()
    qtbot.waitUntil(lambda: reopened_train._shutdown_finished, timeout=10_000)
    qtbot.waitUntil(lambda: reopened_detect._shutdown_finished, timeout=10_000)
