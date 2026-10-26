from __future__ import annotations

import json

import pytest
from alp_ui.components import Switch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from biocall_studio_train.application.collection_scan import scan_collection
from biocall_studio_train.application.power import PowerInhibitionUnavailable
from biocall_studio_train.application.workspace import WorkspaceController
from biocall_studio_train.domain.dataset import BuildConfig
from biocall_studio_train.domain.run import RunStatus
from biocall_studio_train.domain.training import (
    DeviceCapabilities,
    TrainingDataset,
    TrainingDraft,
    freeze_training_config,
)
from biocall_studio_train.gui.app import create_application
from biocall_studio_train.gui.window import KEEP_AWAKE_HELP, MainWindow
from biocall_studio_train.persistence.collection_metadata import publish_collection_metadata
from biocall_studio_train.persistence.datasets import load_dataset
from biocall_studio_train.persistence.models import list_models
from biocall_studio_train.persistence.runs import load_run
from biocall_studio_train.workflows.dataset_build import build_dataset

pytestmark = [pytest.mark.integration, pytest.mark.qt]


@pytest.fixture(autouse=True)
def _initialize_native_application(qapp):
    create_application()


class RecordingPowerAdapter:
    def __init__(self, *, acquire_error: Exception | None = None):
        self.acquire_error = acquire_error
        self.acquire_calls = 0
        self.release_calls = 0

    def acquire(self) -> None:
        self.acquire_calls += 1
        if self.acquire_error is not None:
            raise self.acquire_error

    def release(self) -> None:
        self.release_calls += 1


def _ready_controller(qtbot, tmp_path, collection_factory, adapter, *, delay=0.25):
    root = collection_factory(tmp_path / "collection", source_count=3)
    scan = publish_collection_metadata(root, scan_collection(root))
    controller = WorkspaceController(
        tmp_path / "settings",
        worker_step_delay_seconds=delay,
        cancel_grace_ms=500,
        kill_grace_ms=1_000,
        power_adapter=adapter,
    )
    controller.bind_verified_collection(root, scan.collection_id)
    config = BuildConfig(
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
    return root, controller, config


def test_keep_awake_controls_sync_persist_link_help_and_do_not_cancel_run(
    qapp, qtbot, tmp_path, collection_factory
):
    """Case: IT-POWER-001."""
    adapter = RecordingPowerAdapter()
    root, controller, config = _ready_controller(qtbot, tmp_path, collection_factory, adapter)
    window = MainWindow(controller)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(
        lambda: controller.scan_result is not None and not controller.is_scanning,
        timeout=10_000,
    )

    settings_toggle = window.settings_page.keep_awake_toggle
    training_toggle = window.training_page.keep_awake_toggle
    assert isinstance(settings_toggle, Switch)
    assert isinstance(training_toggle, Switch)
    assert not settings_toggle.isChecked()
    assert not training_toggle.isChecked()
    assert window.settings_page.keep_awake_status.text() == "Off"
    assert window.training_page.keep_awake_status.text() == "Off"
    assert window.settings_page.keep_awake_hint.accessibleDescription() == KEEP_AWAKE_HELP
    assert window.training_page.keep_awake_hint.accessibleDescription() == KEEP_AWAKE_HELP

    settings_toggle.setFocus()
    qtbot.keyClick(settings_toggle, Qt.Key.Key_Space)
    assert settings_toggle.isChecked()
    assert training_toggle.isChecked()
    assert controller.keep_awake_active
    assert adapter.acquire_calls == 1
    assert json.loads(controller.settings_file.read_text())["keep_computer_awake"] is True
    assert window.settings_page.keep_awake_status.text() == "On"

    run_id = controller.start_dataset_build(config, dataset_id="dataset-power-independent")
    qtbot.waitUntil(
        lambda: (
            controller.active_run is not None and controller.active_run.status is RunStatus.RUNNING
        ),
        timeout=10_000,
    )
    training_toggle.setFocus()
    qtbot.keyClick(training_toggle, Qt.Key.Key_Space)
    assert not settings_toggle.isChecked()
    assert not training_toggle.isChecked()
    assert controller.active_run is not None
    assert controller.active_run.run_id == run_id
    assert adapter.release_calls == 1

    window.settings_page.keep_awake_wiki_button.click()
    assert window.current_route == "wiki"
    assert window.focusWidget() is window.wiki_page.keep_awake_title
    assert KEEP_AWAKE_HELP in window.wiki_page.keep_awake_text.text()

    controller.cancel_active_run()
    qtbot.waitUntil(lambda: controller.active_run is None, timeout=10_000)
    assert load_run(root, run_id).status is RunStatus.CANCELLED

    reopened_adapter = RecordingPowerAdapter()
    reopened = WorkspaceController(controller.settings_file.parent, power_adapter=reopened_adapter)
    assert not reopened.keep_awake_requested
    assert reopened_adapter.acquire_calls == 0


def test_keep_awake_unavailable_is_not_presented_as_on(qtbot, tmp_path):
    """Case: IT-POWER-001."""
    adapter = RecordingPowerAdapter(
        acquire_error=PowerInhibitionUnavailable("This platform cannot prevent idle sleep.")
    )
    controller = WorkspaceController(tmp_path / "settings", power_adapter=adapter)
    window = MainWindow(controller)
    qtbot.addWidget(window)
    window.show()
    window.navigate("settings")

    window.settings_page.keep_awake_toggle.click()

    assert window.settings_page.keep_awake_toggle.isChecked()
    assert window.training_page.keep_awake_toggle.isChecked()
    assert not controller.keep_awake_active
    assert window.settings_page.keep_awake_status.text() == "Not active"
    assert "cannot prevent" in window.settings_page.keep_awake_error.text_widget.text()
    assert window.settings_page.keep_awake_retry_button.isVisible()


def test_keep_awake_reacquires_on_restart_and_failed_write_changes_nothing(
    qtbot, tmp_path, monkeypatch
):
    """Case: IT-POWER-001."""
    first_adapter = RecordingPowerAdapter()
    first = WorkspaceController(tmp_path / "settings", power_adapter=first_adapter)
    first.set_keep_awake(True)
    assert first.keep_awake_active
    first.shutdown()

    restart_adapter = RecordingPowerAdapter()
    restarted = WorkspaceController(tmp_path / "settings", power_adapter=restart_adapter)
    assert restarted.keep_awake_requested
    assert restarted.keep_awake_active
    assert restart_adapter.acquire_calls == 1
    restarted.set_keep_awake(False)
    assert restart_adapter.release_calls == 1

    window = MainWindow(restarted)
    qtbot.addWidget(window)
    window.show()
    monkeypatch.setattr(
        restarted._store,
        "save",
        lambda _settings: (_ for _ in ()).throw(OSError("settings disk is read-only")),
    )
    window.settings_page.keep_awake_toggle.click()

    assert not restarted.keep_awake_requested
    assert not restarted.keep_awake_active
    assert not window.settings_page.keep_awake_toggle.isChecked()
    assert restart_adapter.acquire_calls == 1
    assert "could not be saved" in window.settings_page.keep_awake_error.text_widget.text()


def test_active_close_dialog_defaults_to_keep_open_then_stops_once(
    qapp, qtbot, tmp_path, collection_factory
):
    """Case: IT-RUN-006 (real Dataset Build Worker)."""
    adapter = RecordingPowerAdapter()
    root, controller, config = _ready_controller(qtbot, tmp_path, collection_factory, adapter)
    window = MainWindow(controller)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(
        lambda: controller.scan_result is not None and not controller.is_scanning,
        timeout=10_000,
    )
    run_id = controller.start_dataset_build(config, dataset_id="dataset-close-decision")
    qtbot.waitUntil(
        lambda: (
            controller.active_run is not None and controller.active_run.status is RunStatus.RUNNING
        ),
        timeout=10_000,
    )
    progress_before = controller.active_run.progress

    window.close()
    dialog = window.close_dialog
    assert dialog is not None and dialog.isVisible()
    assert dialog.defaultButton().text() == "Keep app open"
    assert dialog.escapeButton().text() == "Keep app open"
    assert dialog.focusWidget() is dialog.defaultButton()
    assert "Dataset Build" in dialog.text()
    assert "work in progress will be lost" in dialog.informativeText()
    assert "no partially trained Dataset or Model" in dialog.informativeText()
    window.close()
    assert window.close_dialog is dialog
    assert len([item for item in qapp.topLevelWidgets() if isinstance(item, QMessageBox)]) == 1

    dialog.defaultButton().click()
    assert window.isVisible()
    assert controller.active_run is not None
    assert controller.active_run.run_id == run_id
    assert controller.active_run.progress >= progress_before
    assert not (root / ".alpaca" / "runs" / run_id / "cancel.requested").exists()

    window.close()
    dialog = window.close_dialog
    assert dialog is not None
    stop_button = next(
        button for button in dialog.buttons() if button.text() == "Stop Run and Exit"
    )
    stop_button.click()
    assert controller.active_run is not None
    assert controller.active_run.status is RunStatus.CANCELLING
    assert window.current_route == "run-detail"
    assert window.run_detail_page.status_badge.text() == "cancelling"
    assert (root / ".alpaca" / "runs" / run_id / "cancel.requested").read_text() == "cancel\n"
    window.close()
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=10_000)
    assert load_run(root, run_id).status in {RunStatus.CANCELLED, RunStatus.INTERRUPTED}


def test_idle_close_has_no_confirmation_and_releases_power(qtbot, tmp_path):
    """Case: IT-RUN-006; completed/idle close does not warn."""
    adapter = RecordingPowerAdapter()
    controller = WorkspaceController(tmp_path / "settings", power_adapter=adapter)
    controller.set_keep_awake(True)
    window = MainWindow(controller)
    qtbot.addWidget(window)
    window.show()

    window.close()

    assert not window.isVisible()
    assert window.close_dialog is None
    assert adapter.release_calls == 1


def test_close_cancels_collection_scan_before_window_exits(qtbot, tmp_path, collection_factory):
    """Case: IT-RUN-006; non-Run scan ownership is also stopped safely."""
    root = collection_factory(tmp_path / "collection", source_count=6)
    controller = WorkspaceController(
        tmp_path / "settings",
        scan_step_delay_seconds=0.2,
        power_adapter=RecordingPowerAdapter(),
    )
    window = MainWindow(controller)
    qtbot.addWidget(window)
    window.show()
    controller.request_collection(str(root))
    qtbot.waitUntil(lambda: controller.is_scanning, timeout=5_000)

    window.close()

    assert window.close_dialog is None
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=10_000)
    assert controller._scan_thread is None
    assert not controller.is_scanning


def _training_config(family: str, dataset):
    draft = TrainingDraft.defaults(family)
    values = (
        {
            "sequence_length_ms": 250,
            "training.max_epochs": 20,
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
            "training.pin_memory": False,
        }
        if family == "cnn"
        else {
            "n_estimators": 100,
            "min_samples_leaf": 1,
            "n_jobs": 1,
            "feature_config.sample_rate_hz": 8_000,
            "feature_config.min_duration_s": 0.25,
            "feature_config.n_fft": 256,
            "feature_config.hop_length": 64,
            "feature_config.n_mfcc": 4,
            "feature_config.fmin_hz": 100.0,
            "feature_config.fmax_hz": 3_500.0,
        }
    )
    for key, value in values.items():
        draft.set(key, value)
    return freeze_training_config(
        draft,
        TrainingDataset.from_artifact(dataset),
        DeviceCapabilities(cuda=False, mps=False, cpu_count=4),
    )


@pytest.mark.parametrize("family", ["dataset", "cnn", "rf"])
def test_confirmed_exit_cleans_each_real_output_family(qtbot, tmp_path, collection_factory, family):
    """Case: IT-RUN-007; Dataset/CNN/RF close is honest and all-or-nothing."""
    root = collection_factory(tmp_path / "collection", source_count=3)
    scan = publish_collection_metadata(root, scan_collection(root))
    build_config = BuildConfig(
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
    prior_dataset = None
    if family != "dataset":
        prior_dataset = build_dataset(
            root,
            scan,
            build_config,
            dataset_id=f"dataset-prior-{family}",
        )
    source_before = {
        path.relative_to(root): path.read_bytes()
        for folder in ("recordings", "positives")
        for path in (root / folder).iterdir()
    }
    adapter = RecordingPowerAdapter()
    controller = WorkspaceController(
        tmp_path / "settings",
        worker_step_delay_seconds=0.75,
        cancel_grace_ms=750,
        kill_grace_ms=1_500,
        power_adapter=adapter,
    )
    controller.bind_verified_collection(root, scan.collection_id)
    window = MainWindow(controller)
    qtbot.addWidget(window)
    window.show()
    if family == "dataset":
        qtbot.waitUntil(
            lambda: controller.scan_result is not None and not controller.is_scanning,
            timeout=10_000,
        )
        output_id = "dataset-exit-incomplete"
        run_id = controller.start_dataset_build(build_config, dataset_id=output_id)
        output_path = root / ".alpaca" / "datasets" / output_id
    else:
        assert prior_dataset is not None
        output_id = f"model-exit-incomplete-{family}"
        run_id = controller.start_training(
            _training_config(family, prior_dataset),
            model_label=f"Interrupted {family}",
            model_id=output_id,
        )
        output_path = root / ".alpaca" / "models" / output_id
    qtbot.waitUntil(
        lambda: (
            controller.active_run is not None and controller.active_run.status is RunStatus.RUNNING
        ),
        timeout=20_000,
    )

    window.close()
    assert window.close_dialog is not None
    expected_family = {
        "dataset": "Dataset Build",
        "cnn": "CNN Training",
        "rf": "Random Forest Training",
    }[family]
    assert expected_family in window.close_dialog.text()
    next(
        button for button in window.close_dialog.buttons() if button.text() == "Stop Run and Exit"
    ).click()
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=30_000)

    state = load_run(root, run_id)
    assert state.status in {RunStatus.CANCELLED, RunStatus.INTERRUPTED}
    assert state.published_artifact_id is None
    assert not output_path.exists()
    staging = root / ".alpaca" / ".staging"
    assert not staging.exists() or not any(staging.iterdir())
    assert {relative: (root / relative).read_bytes() for relative in source_before} == source_before
    if prior_dataset is not None:
        assert load_dataset(root, prior_dataset.dataset_id).root.is_dir()
    assert list_models(root) == ()

    reopened = WorkspaceController(controller.settings_file.parent, power_adapter=adapter)
    assert reopened.active_run is None
    reopened.finalize_shutdown()
