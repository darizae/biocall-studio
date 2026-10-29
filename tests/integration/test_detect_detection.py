from __future__ import annotations

import json
import shutil
import struct
import wave
from dataclasses import dataclass
from pathlib import Path

import pytest
from alp_ui.components import HelpHint
from bioacoustics_dl_toolbox.prediction import predict_windows

from biocall_studio.detect.controller import DetectWorkspaceController, ModelIntakeState
from biocall_studio.detect.detection import (
    DetectionSettings,
    merge_candidate_windows,
    predict_recording_windows,
)
from biocall_studio.detect.models import inspect_model_directory
from biocall_studio.detect.run_persistence import DetectRunRepository
from biocall_studio.detect.runs import DetectRunStatus
from biocall_studio.gui.detect import DetectWorkspacePage
from biocall_studio_train.application.collection_scan import scan_collection
from biocall_studio_train.domain.dataset import BuildConfig
from biocall_studio_train.domain.training import (
    DeviceCapabilities,
    TrainingDataset,
    TrainingDraft,
    freeze_training_config,
)
from biocall_studio_train.persistence.collection_metadata import publish_collection_metadata
from biocall_studio_train.persistence.models import ModelArtifact
from biocall_studio_train.workflows.cnn_training import CnnTrainingRequest, train_cnn_model
from biocall_studio_train.workflows.dataset_build import build_dataset

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
    """Case: IT-DET-013."""
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
    assert {
        hint.accessibleName() for hint in page.findChildren(HelpHint)
    } >= {
        "More about Minimum detection score",
        "More about Window overlap",
        "More about Combine nearby candidates",
    }
    page.verticalScrollBar().setValue(page.verticalScrollBar().maximum())
    page.resize(700, 780)
    qtbot.waitUntil(lambda: page.is_compact)
    qtbot.waitUntil(lambda: page.horizontalScrollBar().maximum() == 0)
    assert page.horizontalScrollBar().maximum() == 0
    assert page.content.minimumSizeHint().width() <= page.width()
    assert page.settings_layout.getItemPosition(
        page.settings_layout.indexOf(page.minimum_score_row)
    )[:2] == (0, 0)
    page.resize(1180, 790)
    qtbot.waitUntil(lambda: not page.is_compact)
    page.minimum_score.setValue(1.0)
    page.start_detection_button.click()
    assert page.current_route == "run"
    record = _wait_terminal(qtbot, controller)
    assert record.status is DetectRunStatus.COMPLETED
    assert record.progress == 100

    repository = DetectRunRepository(
        app_data, controller.active_collection.ref.collection_id
    )
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
    assert "metadata-only Result" in page.run_guidance.text()
    reopened = DetectWorkspaceController(app_data)
    assert reopened.current_run.status is DetectRunStatus.COMPLETED
    assert reopened.current_result == result
    assert reopened.wait_for_model(30_000)
    reopened.shutdown()
    controller.shutdown()


@pytest.mark.qt
def test_stale_input_cancellation_crash_and_publication_collision_are_atomic(
    qapp, qtbot, genuine_cnn, tmp_path
):
    """Case: IT-DET-014."""
    settings = DetectionSettings(0.5, 50, 0, 1)

    stale_data = tmp_path / "stale-data"
    stale_controller = DetectWorkspaceController(stale_data, worker_step_delay_seconds=0.05)
    _select_inputs(qtbot, stale_controller, genuine_cnn.model.root, genuine_cnn.root)
    stale_controller.start_detection(settings)
    stale_path = genuine_cnn.root / "recordings" / "REC_A.wav"
    original = stale_path.read_bytes()
    stale_path.write_bytes(original + b"changed")
    stale_record = _wait_terminal(qtbot, stale_controller)
    assert stale_record.status is DetectRunStatus.FAILED
    assert stale_record.error_code == "input_changed"
    stale_repository = DetectRunRepository(
        stale_data, stale_controller.active_collection.ref.collection_id
    )
    assert not stale_repository.result_path(stale_record.artifact_id).exists()
    stale_path.write_bytes(original)
    stale_controller.shutdown()

    cancel_data = tmp_path / "cancel-data"
    cancel_controller = DetectWorkspaceController(cancel_data, worker_step_delay_seconds=0.2)
    _select_inputs(qtbot, cancel_controller, genuine_cnn.model.root, genuine_cnn.root)
    cancel_controller.start_detection(settings)
    qtbot.waitUntil(lambda: cancel_controller.is_run_active, timeout=10_000)
    cancel_controller.cancel_active_run()
    cancelled = _wait_terminal(qtbot, cancel_controller)
    assert cancelled.status is DetectRunStatus.CANCELLED
    cancel_repository = DetectRunRepository(
        cancel_data, cancel_controller.active_collection.ref.collection_id
    )
    assert not cancel_repository.result_path(cancelled.artifact_id).exists()
    cancel_controller.shutdown()

    collision_data = tmp_path / "collision-data"
    collision_controller = DetectWorkspaceController(collision_data)
    _select_inputs(qtbot, collision_controller, genuine_cnn.model.root, genuine_cnn.root)
    request = collision_controller.freeze_detection_request(settings)
    collision_repository = DetectRunRepository(
        collision_data, collision_controller.active_collection.ref.collection_id
    )
    collision = collision_repository.result_path(request.artifact_id)
    collision.mkdir()
    marker = collision / "existing.txt"
    marker.write_text("existing\n")
    collision_controller.start_detection_request(request)
    failed = _wait_terminal(qtbot, collision_controller)
    assert failed.status is DetectRunStatus.FAILED
    assert failed.error_code == "publication_failed"
    assert marker.read_text() == "existing\n"
    assert not (collision_repository.run_directory(failed.run_id) / "receipt.json").exists()
    assert not collision_repository.staging_path(failed.launch_id).exists()
    collision_controller.shutdown()

    receipt_data = tmp_path / "receipt-data"
    receipt_controller = DetectWorkspaceController(
        receipt_data, worker_step_delay_seconds=0.2
    )
    _select_inputs(qtbot, receipt_controller, genuine_cnn.model.root, genuine_cnn.root)
    receipt_controller.start_detection(settings)
    qtbot.waitUntil(lambda: receipt_controller.current_run is not None, timeout=10_000)
    receipt_repository = DetectRunRepository(
        receipt_data, receipt_controller.active_collection.ref.collection_id
    )
    receipt_path = receipt_repository.run_directory(
        receipt_controller.current_run.run_id
    ) / "receipt.json"
    receipt_path.write_text("{}\n")
    receipt_failed = _wait_terminal(qtbot, receipt_controller)
    assert receipt_failed.status is DetectRunStatus.FAILED
    assert receipt_failed.error_code == "publication_failed"
    assert receipt_path.read_text() == "{}\n"
    assert not receipt_repository.result_path(receipt_failed.artifact_id).exists()
    assert not receipt_repository.staging_path(receipt_failed.launch_id).exists()
    receipt_controller.shutdown()

    crash_data = tmp_path / "crash-data"
    crash_controller = DetectWorkspaceController(crash_data, worker_step_delay_seconds=0.2)
    _select_inputs(qtbot, crash_controller, genuine_cnn.model.root, genuine_cnn.root)
    crash_controller.start_detection(settings)
    qtbot.waitUntil(
        lambda: crash_controller.run_process is not None
        and crash_controller.run_process.processId() > 0,
        timeout=10_000,
    )
    crash_controller.run_process.kill()
    crashed = _wait_terminal(qtbot, crash_controller)
    assert crashed.status is DetectRunStatus.INTERRUPTED
    crash_repository = DetectRunRepository(
        crash_data, crash_controller.active_collection.ref.collection_id
    )
    assert not crash_repository.result_path(crashed.artifact_id).exists()
    crash_controller.shutdown()


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
