from __future__ import annotations

import json

import pytest
from alp_ui.components import HelpHint, NumberInput, SelectInput
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QInputDialog, QMessageBox

from alpaca_desktop.application.collection_scan import scan_collection
from alpaca_desktop.application.workspace import WorkspaceController
from alpaca_desktop.domain.dataset import BuildConfig
from alpaca_desktop.domain.training import fields_for_family
from alpaca_desktop.gui.app import create_application
from alpaca_desktop.gui.training import TrainingPage
from alpaca_desktop.gui.window import MainWindow
from alpaca_desktop.persistence.collection_metadata import publish_collection_metadata
from alpaca_desktop.workflows.dataset_build import build_dataset

pytestmark = pytest.mark.integration


def _published_dataset(root, wav_factory):
    for index in range(3):
        stem = f"REC_{chr(ord('A') + index)}"
        wav_factory(root / "recordings" / f"{stem}.wav", frames=48_000)
        wav_factory(
            root / "positives" / f"{stem}__start-00500ms__end-01000ms__call{index}.wav",
            frames=8_000,
        )
    scan = publish_collection_metadata(root, scan_collection(root))
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
    return scan, build_dataset(root, scan, config, dataset_id="dataset-training-ui")


def _window(qtbot, tmp_path, wav_factory):
    create_application()
    root = tmp_path / "collection"
    scan, dataset = _published_dataset(root, wav_factory)
    controller = WorkspaceController(tmp_path / "settings")
    controller.bind_verified_collection(root, scan.collection_id)
    window = MainWindow(controller)
    qtbot.addWidget(window)
    window.show()
    window.open_dataset(dataset.dataset_id)
    window.dataset_detail_page.train_button.click()
    return window, dataset


@pytest.mark.qt
def test_native_training_page_primary_disclosure_family_drafts_and_wiki(
    qapp, qtbot, tmp_path, wav_factory
):
    """Case: IT-TRAIN-010."""
    window, dataset = _window(qtbot, tmp_path, wav_factory)
    page = window.training_page

    assert window.current_route == "training"
    assert isinstance(page, TrainingPage)
    assert page.dataset_id == dataset.dataset_id
    assert isinstance(page.family_input, SelectInput)
    assert page.start_button.text() == "Start Training"
    assert page.visible_field_keys() == {
        "run_name",
        "sequence_length_ms",
        "training.max_epochs",
        "training.batch_size",
        "training.learning_rate",
        "device",
    }
    assert not page.more_settings.isChecked()

    page.set_field_value("training.batch_size", 32)
    page.more_settings.setFocus()
    qtbot.keyClick(page.more_settings, Qt.Key.Key_Space)
    assert page.more_settings.isChecked()
    assert page.detail_sections() == {
        "Spectrogram",
        "Normalization",
        "Augmentation",
        "Architecture",
        "Optimization & validation",
        "Execution",
    }
    cnn_details = {field.key for field in fields_for_family("cnn") if field.ui_tier == "details"}
    assert cnn_details <= page.field_widgets.keys()
    assert all(
        field.wiki_anchor in page.help_hints[field.key].accessibleDescription()
        for field in fields_for_family("cnn")
    )
    page.open_detail_section("Spectrogram")
    assert page.field_widgets["spectrogram.n_fft"].isVisible()
    assert (
        "Default / suggested starting value: 4096"
        in page.field_captions["spectrogram.n_fft"].text()
    )
    hint = page.help_hints["spectrogram.n_fft"]
    assert isinstance(hint, HelpHint)
    hint.setFocus()
    qtbot.keyClick(hint, Qt.Key.Key_Space)
    assert "Wiki: training-configuration#spectrogram-n-fft" in hint.accessibleDescription()
    page.wiki_buttons["spectrogram.n_fft"].click()
    assert window.current_route == "training-wiki"
    assert window.training_wiki_page.anchor == "training-configuration#spectrogram-n-fft"
    window.training_wiki_page.back_button.click()
    assert window.current_route == "training"

    page.family_input.setCurrentIndex(1)
    assert page.visible_field_keys() == {
        "run_name",
        "n_estimators",
        "max_depth",
        "min_samples_leaf",
    }
    rf_details = {field.key for field in fields_for_family("rf") if field.ui_tier == "details"}
    assert rf_details <= page.field_widgets.keys()
    assert page.field_controls["feature_family"].isReadOnly()
    assert page.field_captions["feature_family"].text() == "Automatically determined"
    page.set_field_value("n_estimators", 1200)
    page.family_input.setCurrentIndex(0)
    assert page.field_value("training.batch_size") == 32
    page.family_input.setCurrentIndex(1)
    assert page.field_value("n_estimators") == 1200


@pytest.mark.qt
def test_native_validation_preserves_values_blocks_launch_and_resets(
    qapp, qtbot, tmp_path, wav_factory, monkeypatch
):
    """Case: IT-TRAIN-011."""
    window, _dataset = _window(qtbot, tmp_path, wav_factory)
    page = window.training_page
    page.more_settings.click()
    page.open_detail_section("Spectrogram")
    assert isinstance(page.field_controls["spectrogram.n_fft"], NumberInput)

    page.set_field_value("training.learning_rate", 1e-10)
    assert page.field_controls["training.learning_rate"].value() == pytest.approx(1e-10)
    assert page.field_value("training.learning_rate") == pytest.approx(1e-10)

    device = page.field_controls["device"]
    mps_index = device.control.findData("mps")
    mps_item = device.model().item(mps_index)
    assert not mps_item.isEnabled()
    assert "MPS is unavailable in the verified training executor" in mps_item.toolTip()
    assert "MPS unsupported by verified executor" in device.control.accessibleDescription()
    assert "MPS unsupported by verified executor" in device.descriptionText()

    noise_source = page.field_controls["augmentation.noise_source"]
    collection_noise_index = noise_source.control.findData("collection-selected")
    collection_noise_item = noise_source.model().item(collection_noise_index)
    assert not collection_noise_item.isEnabled()
    assert "Collection-selected noise is unavailable" in collection_noise_item.toolTip()
    assert "collection-selected noise lacks verified executor support" in (
        noise_source.control.accessibleDescription()
    )
    assert "collection-selected noise lacks verified executor support" in (
        noise_source.descriptionText()
    )

    page.set_field_value("spectrogram.n_fft", 1024)
    page.set_field_value("spectrogram.hop_length", 2048)

    assert page.field_value("spectrogram.hop_length") == 2048
    assert not page.start_button.isEnabled()
    assert "FFT hop must not exceed" in page.error_alert.text_widget.text()
    page.reset_field("spectrogram.hop_length")
    assert page.field_value("spectrogram.hop_length") == 441
    assert page.start_button.isEnabled()
    assert (
        not {
            "src_dir",
            "data_dir",
            "model_dir",
            "noise_dir",
            "classifier.num_classes",
        }
        & page.editable_field_keys()
    )

    started: dict[str, object] = {}
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *_args, **_kwargs: ("UI verified CNN", True),
    )
    monkeypatch.setattr(
        window.controller,
        "start_training",
        lambda config, *, model_label: started.update(
            config=config,
            model_label=model_label,
        ),
    )
    page.start_button.click()
    assert page.last_frozen_config is not None
    assert page.last_frozen_config.dataset_id == "dataset-training-ui"
    assert started == {
        "config": page.last_frozen_config,
        "model_label": "UI verified CNN",
    }
    assert window.controller.active_run is None


@pytest.mark.qt
def test_native_preset_lifecycle_and_restart_persistence(
    qapp, qtbot, tmp_path, wav_factory, monkeypatch
):
    """Case: IT-TRAIN-013."""
    window, dataset = _window(qtbot, tmp_path, wav_factory)
    page = window.training_page
    page.set_field_value("training.batch_size", 32)
    page.set_field_value("spectrogram.n_fft", 2048)
    preset = page.save_preset_as("Laptop")
    page.set_field_value("training.batch_size", 64)
    assert page.preset_input.currentText() == "Unsaved changes"
    page.load_preset(preset.preset_id)
    assert page.field_value("training.batch_size") == 32
    duplicate = page.duplicate_preset(preset.preset_id, "Laptop copy")
    page.rename_preset(duplicate.preset_id, "Laptop field")
    page.set_field_value("training.batch_size", 48)
    page.overwrite_preset(preset.preset_id)

    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    page.delete_preset(duplicate.preset_id)
    assert {item.label for item in page.preset_store.list()} == {"Laptop"}

    preset_path = page.preset_store.path
    payload = json.loads(preset_path.read_text())
    assert str(tmp_path / "collection") not in json.dumps(payload)
    window.close()

    controller = WorkspaceController(tmp_path / "settings")
    reopened = MainWindow(controller)
    qtbot.addWidget(reopened)
    reopened.show()
    reopened.open_dataset(dataset.dataset_id)
    reopened.dataset_detail_page.train_button.click()
    reopened.training_page.load_preset(preset.preset_id)
    assert reopened.training_page.field_value("training.batch_size") == 48
    reopened.training_page.more_settings.click()
    reopened.training_page.open_detail_section("Spectrogram")
    assert reopened.training_page.field_value("spectrogram.n_fft") == 2048
    assert reopened.training_page.dataset_id == dataset.dataset_id
    reopened.close()

    payload["toolbox_schema_revision"] = "unsupported-toolbox-schema"
    preset_path.write_text(json.dumps(payload))
    incompatible = MainWindow(WorkspaceController(tmp_path / "settings"))
    qtbot.addWidget(incompatible)
    incompatible.show()
    assert not incompatible.training_page.preset_alert.isHidden()
    assert (
        "toolbox revision is incompatible"
        in incompatible.training_page.preset_alert.text_widget.text()
    )
    assert incompatible.training_page.preset_input.count() == 1
