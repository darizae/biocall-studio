# ruff: noqa: E501 -- approved interface copy is asserted verbatim.
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from html import unescape

import pytest
from alp_ui.components import HelpHint, NumberInput, SelectInput, Text
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractButton, QInputDialog, QLabel, QMessageBox, QWidget

from biocall_studio.shared.storage import CapacityObservation, StorageDecision
from biocall_studio.studio.application.app import create_application
from biocall_studio.train.application.collection_scan import scan_collection
from biocall_studio.train.application.workspace import WorkspaceController
from biocall_studio.train.domain.dataset import BuildConfig
from biocall_studio.train.domain.training import field_definitions, fields_for_family
from biocall_studio.train.gui.storage import confirm_storage
from biocall_studio.train.gui.training import TrainingPage
from biocall_studio.train.gui.window import MainWindow
from biocall_studio.train.persistence.collection_metadata import publish_collection_metadata
from biocall_studio.train.workflows.dataset_build import build_dataset

pytestmark = pytest.mark.integration


APPROVED_CONFIGURATION_COPY = {
    "run_name": (
        "Run name",
        "A name to help you recognize this training run. You can rename the finished model later.",
    ),
    "logging_level": (
        "Log detail",
        "Controls how much information is saved in the run log. It does not change training results.",
    ),
    "spectrogram_cache": (
        "Spectrogram cache",
        "Reuses spectrograms from an earlier compatible run to shorten setup time.",
    ),
    "sequence_length_ms": (
        "Sequence length (ms)",
        "Length of each audio example used for training, in milliseconds. Use a length that can contain the call.",
    ),
    "training.max_epochs": (
        "Maximum epochs",
        "Maximum number of times the model sees the training data. Training may stop earlier when it stops improving.",
    ),
    "training.batch_size": (
        "Batch size",
        "Number of audio examples processed together. Larger batches use more memory.",
    ),
    "training.learning_rate": (
        "Learning rate",
        "Controls how quickly the model changes while learning. Values that are too high can make training unstable.",
    ),
    "device": (
        "Training device",
        "Chooses the processor used for training. Unavailable options are disabled.",
    ),
    "spectrogram.sample_rate": (
        "Sampling rate (Hz)",
        "Sample rate used to create spectrograms. Audio is converted to this rate for training.",
    ),
    "spectrogram.preemphasis": (
        "Pre-emphasis",
        "Boosts higher frequencies before creating the spectrogram. The same value is saved with the model.",
    ),
    "spectrogram.n_fft": (
        "FFT window (samples)",
        "Number of audio samples in each spectral window. Larger windows show frequency more precisely but time less precisely.",
    ),
    "spectrogram.hop_length": (
        "FFT hop (samples)",
        "Number of audio samples between spectrogram frames. Smaller values show changes over time more closely.",
    ),
    "spectrogram.n_freq_bins": (
        "Frequency bins",
        "Number of frequency bands kept in the spectrogram.",
    ),
    "spectrogram.f_min": (
        "Minimum frequency (Hz)",
        "Lowest frequency included in the spectrogram.",
    ),
    "spectrogram.f_max": (
        "Maximum frequency (Hz)",
        "Highest frequency included in the spectrogram. It cannot be above half the sampling rate.",
    ),
    "spectrogram.freq_compression": (
        "Frequency compression",
        "Chooses how frequencies are represented: linear, mel, or MFCC.",
    ),
    "spectrogram.min_level_db": (
        "Spectrogram minimum dB",
        "Quietest level retained when scaling the spectrogram. Lower values keep a wider volume range.",
    ),
    "spectrogram.ref_level_db": (
        "Spectrogram reference dB",
        "Reference level used when converting the spectrogram to decibels.",
    ),
    "normalization.mode": (
        "Normalization mode",
        "Chooses how spectrogram values are scaled before training. The choice is saved with the model.",
    ),
    "normalization.min_level_db": (
        "Normalization minimum dB",
        "Quietest decibel value used during spectrogram normalization.",
    ),
    "normalization.ref_level_db": (
        "Normalization reference dB",
        "Reference decibel value used during spectrogram normalization.",
    ),
    "augmentation.enabled": (
        "Enable augmentation",
        "Randomly changes training examples to add variety. Validation examples are not changed.",
    ),
    "augmentation.amplitude_increase_db": (
        "Maximum gain (dB)",
        "Largest increase in volume applied during augmentation.",
    ),
    "augmentation.amplitude_decrease_db": (
        "Maximum attenuation (dB)",
        "Largest decrease in volume applied during augmentation.",
    ),
    "augmentation.time_stretch_from": (
        "Time stretch minimum",
        "Slowest playback-speed change used during augmentation.",
    ),
    "augmentation.time_stretch_to": (
        "Time stretch maximum",
        "Fastest playback-speed change used during augmentation.",
    ),
    "augmentation.pitch_shift_from": (
        "Pitch shift minimum",
        "Lowest pitch change used during augmentation.",
    ),
    "augmentation.pitch_shift_to": (
        "Pitch shift maximum",
        "Highest pitch change used during augmentation.",
    ),
    "augmentation.noise_min_snr": (
        "Noise mix minimum SNR (dB)",
        "Lowest signal-to-noise ratio used when mixing background noise. Lower values make the added noise stronger.",
    ),
    "augmentation.noise_max_snr": (
        "Noise mix maximum SNR (dB)",
        "Highest signal-to-noise ratio used when mixing background noise. Higher values make the added noise quieter.",
    ),
    "augmentation.noise_source": (
        "Noise augmentation source",
        "Chooses the background sound mixed into training examples. Only available sources are listed.",
    ),
    "encoder.resnet_size": (
        "ResNet depth",
        "Size of the ResNet model. Deeper models usually take more memory and time to train.",
    ),
    "encoder.conv_kernel_size": (
        "First convolution kernel",
        "Size of the first pattern-detection window in the CNN.",
    ),
    "encoder.max_pool": (
        "Initial max-pooling mode",
        "Controls early downsampling in the CNN. Keep the preset value unless you are changing the model architecture.",
    ),
    "encoder.input_channels": (
        "Input channels",
        "Number of spectrogram channels supplied to the model. Set automatically for mono audio.",
    ),
    "classifier.pooling": (
        "Classifier pooling",
        "Chooses whether the classifier summarizes learned features by their average or maximum value.",
    ),
    "classifier.num_classes": (
        "Number of output classes",
        "Number of classes the model predicts. Set automatically from the dataset.",
    ),
    "classifier.input_channels": (
        "Classifier input channels",
        "Number of learned features sent to the classifier. Set automatically from the selected CNN.",
    ),
    "training.num_workers": (
        "Data-loader workers",
        "Number of background processes that load training audio. Zero loads audio in the main process.",
    ),
    "training.beta1": (
        "Adam β1",
        "Controls how strongly Adam smooths recent gradient changes. Keep the default unless tuning the optimizer.",
    ),
    "training.lr_patience_epochs": (
        "LR scheduler patience",
        "Number of validation checks without improvement before the learning rate is reduced.",
    ),
    "training.lr_decay_factor": (
        "LR decay factor",
        "Amount the learning rate is multiplied by when validation stops improving.",
    ),
    "training.early_stopping_patience_epochs": (
        "Early-stopping patience",
        "Number of validation checks without improvement before training stops.",
    ),
    "training.epochs_per_eval": (
        "Evaluate every N epochs",
        "Number of training epochs between validation checks.",
    ),
    "training.val_metric": (
        "Validation metric",
        "Measurement used to choose the best saved model and decide whether training is improving.",
    ),
    "training.val_metric_mode": (
        "Validation metric direction",
        "Tells training whether a higher or lower value is better for the selected validation metric.",
    ),
    "training.pin_memory": (
        "Pin data-loader memory",
        "Can speed up transfers to a supported GPU, while using additional system memory.",
    ),
    "n_estimators": (
        "Trees",
        "Number of decision trees in the forest. More trees take more time and memory.",
    ),
    "min_samples_leaf": (
        "Minimum samples per leaf",
        "Smallest number of examples allowed in a final tree group. Larger values make the model less specific.",
    ),
    "max_depth": (
        "Maximum tree depth",
        "Maximum number of levels in each tree. Choose Unlimited to let trees grow without this limit.",
    ),
    "rf_threshold": (
        "Validation decision threshold",
        "Minimum validation score counted as a target call. The value is saved with the model.",
    ),
    "random_state": (
        "Random seed",
        "Use the same seed with the same data and settings to train the same forest again.",
    ),
    "min_samples_split": (
        "Minimum samples to split",
        "Smallest number of examples a tree group needs before it can divide.",
    ),
    "max_features": (
        "Features per split",
        "Number of sound features each tree considers when making a split.",
    ),
    "class_weight": (
        "Class weighting",
        "Adjusts how strongly the forest learns from target calls and background examples when their counts differ.",
    ),
    "n_jobs": (
        "Training CPU workers",
        "Number of CPU workers used to train the forest. −1 requests all safely available CPUs.",
    ),
    "feature_family": (
        "Acoustic feature family",
        "Set of calculated sound measurements used by the Random Forest.",
    ),
    "feature_config.sample_rate_hz": (
        "Feature sample rate (Hz)",
        "Sample rate used when calculating Random Forest sound features.",
    ),
    "feature_config.min_duration_s": (
        "Minimum feature segment (s)",
        "Shortest audio segment accepted for feature calculation. Shorter segments follow the padding setting.",
    ),
    "feature_config.pad_short_segments": (
        "Pad short segments",
        "Adds silence to segments that are shorter than the minimum feature length.",
    ),
    "feature_config.pad_mode": (
        "Padding mode",
        "Chooses how extra audio is filled when a segment is too short.",
    ),
    "feature_config.n_fft": (
        "Feature FFT window",
        "Number of audio samples in each spectral window used to calculate Random Forest features.",
    ),
    "feature_config.hop_length": (
        "Feature FFT hop",
        "Number of audio samples between feature-analysis frames.",
    ),
    "feature_config.n_mfcc": (
        "MFCC coefficients",
        "Number of MFCC sound-shape measurements calculated for each segment.",
    ),
    "feature_config.include_deltas": (
        "Include MFCC deltas",
        "Adds measurements of how MFCC values change over time.",
    ),
    "feature_config.fmin_hz": (
        "Feature minimum frequency (Hz)",
        "Lowest frequency used when calculating Random Forest sound features.",
    ),
    "feature_config.fmax_hz": (
        "Feature maximum frequency (Hz)",
        "Highest frequency used when calculating Random Forest sound features. It cannot be above half the feature sample rate.",
    ),
}


APPROVED_TRAIN_CONTEXT_HELP = {
    "Source and positive mapping": "Each labeled clip name identifies its full recording and the clip's start and end times.",
    "Collection storage": "BioCall Studio stores datasets and models in this folder. It does not copy or change your WAV files.",
    "1 · Choose positive examples": "Choose which recordings to use. Turning one off also removes its labeled clips and background examples.",
    "2 · Negative Mining": "Creates background examples from parts of the selected recordings that do not overlap labeled calls.",
    "Negative amount": "Choose a number for each labeled call or one total number for the dataset.",
    "By Source Recording": "Choose whether recordings with more labeled calls supply more background examples, or each recording supplies about the same number.",
    "Training Split": "Keeps every clip from one recording in the same group, so training and validation do not share a recording.",
    "Seed": "Use the same seed with the same inputs and settings to build the same dataset again.",
    "Positive exclusion margin": "Keeps background examples this far away from each labeled call.",
    "train / val Splits": "Every clip from one recording stays in the same group.",
    "Keep computer awake": "Prevents inactivity sleep while BioCall Studio is open. The display can still turn off, and closing the lid or choosing Sleep still works.",
    "Training Dataset": "The dataset supplies the labeled call and background examples used to train this model.",
    "Model families": "CNN learns from spectrograms. Random Forest learns from calculated sound features.",
    "Collection folders": "Choose a folder containing `recordings/` and `positives/`. BioCall Studio reads the WAV files in place and does not copy them.",
    "Clip times": "Write start and end times in whole milliseconds. 1,000 ms equals 1 second.",
    "Estimated output": "Approximate space the finished files will use.",
    "Space while running": "Includes temporary files. Some are removed when the task finishes.",
}

APPROVED_TRAIN_CONTEXT_IDS = {
    "CTX-11": "Source and positive mapping",
    "CTX-12": "Collection storage",
    "CTX-13": "1 · Choose positive examples",
    "CTX-14": None,
    "CTX-15": "2 · Negative Mining",
    "CTX-16": "Negative amount",
    "CTX-17": "By Source Recording",
    "CTX-18": "Training Split",
    "CTX-19": "Seed",
    "CTX-20": "Positive exclusion margin",
    "CTX-21": "train / val Splits",
    "CTX-22": "Keep computer awake",
    "CTX-23": "Training Dataset",
    "CTX-24": "Model families",
    "CTX-25": None,
    "CTX-26": "Collection folders",
    "CTX-27": "Clip times",
    "CTX-28": None,
    "REV05-ESTIMATED-OUTPUT": "Estimated output",
    "REV05-SPACE-WHILE-RUNNING": "Space while running",
}


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


def _interact_with_alternative(qtbot, page, field):
    """Change one real native control and return its observable value, if supported."""
    control = page.field_controls[field.key]
    native = getattr(control, "control", control)
    if field.kind == "text":
        native.setFocus()
        native.clear()
        qtbot.keyClicks(native, "Spec 05f")
        return "Spec 05f"
    if field.kind in {"int", "nullable_int"}:
        value = 1 if field.default is None else int(field.default) + 1
        native.setFocus()
        native.setValue(value)
        return value
    if field.kind == "float":
        value = float(field.default) + 0.01
        native.setFocus()
        native.setValue(value)
        return value
    if field.kind == "bool":
        native.setFocus()
        qtbot.keyClick(native, Qt.Key.Key_Space)
        return not bool(field.default)
    if field.kind == "select":
        alternatives = [
            index
            for index in range(native.count())
            if native.itemData(index) != field.default and native.model().item(index).isEnabled()
        ]
        if not alternatives:
            assert any(
                not native.model().item(index).isEnabled() for index in range(native.count())
            )
            return None
        native.setFocus()
        native.setCurrentIndex(alternatives[0])
        return native.currentData()
    raise AssertionError(f"unhandled field kind: {field.kind}")


@pytest.mark.qt
def test_all_approved_train_help_copy_and_removed_hints_are_complete(
    qapp, qtbot, tmp_path, wav_factory
):
    """Case: IT-TRAIN-015."""
    fields = field_definitions()
    assert len(fields) == len(APPROVED_CONFIGURATION_COPY) == 67
    assert {f"CFG-{index:02d}": field.key for index, field in enumerate(fields, start=1)} == {
        f"CFG-{index:02d}": key for index, key in enumerate(APPROVED_CONFIGURATION_COPY, start=1)
    }
    assert {field.key: (field.label, field.help) for field in fields} == (
        APPROVED_CONFIGURATION_COPY
    )

    window, _dataset = _window(qtbot, tmp_path, wav_factory)
    qtbot.waitUntil(lambda: window.controller.scan_result is not None, timeout=10_000)
    qapp.processEvents()
    contextual: dict[str, set[str]] = {}
    context_ids: dict[str, tuple[str, str]] = {}
    for hint in window.findChildren(HelpHint):
        subject = hint.accessibleName().removeprefix("More about ")
        copy_id = hint.objectName()
        if copy_id.startswith("CFG-"):
            continue
        contextual.setdefault(subject, set()).add(unescape(hint.toolTip()))
        if copy_id:
            value = (subject, unescape(hint.toolTip()))
            assert context_ids.get(copy_id, value) == value
            context_ids[copy_id] = value
        assert hint.focusPolicy() != Qt.FocusPolicy.NoFocus
        assert hint.accessibleDescription() == unescape(hint.toolTip())
    for subject, approved in APPROVED_TRAIN_CONTEXT_HELP.items():
        assert contextual[subject] == {approved}
    assert set(context_ids) == {
        copy_id for copy_id, subject in APPROVED_TRAIN_CONTEXT_IDS.items() if subject is not None
    }
    for copy_id, subject in APPROVED_TRAIN_CONTEXT_IDS.items():
        if subject is None:
            assert copy_id not in context_ids
        else:
            assert context_ids[copy_id] == (
                subject,
                APPROVED_TRAIN_CONTEXT_HELP[subject],
            )

    builder_subjects = {
        hint.accessibleName() for hint in window.builder_page.findChildren(HelpHint)
    }
    training_subjects = {
        hint.accessibleName() for hint in window.training_page.findChildren(HelpHint)
    }
    settings_subjects = {
        hint.accessibleName() for hint in window.settings_page.findChildren(HelpHint)
    }
    assert "More about 3 · Dataset preview" not in builder_subjects
    assert "More about Start Training" not in training_subjects
    assert "More about Collection folders" not in settings_subjects

    device = window.training_page.field_controls["device"]
    cuda_item = device.model().item(device.control.findData("cuda"))
    mps_item = device.model().item(device.control.findData("mps"))
    assert cuda_item.toolTip() == "CUDA is not available on this computer."
    assert mps_item.toolTip() == "Apple GPU training is not available in this version."
    window.training_page.more_settings.click()
    window.training_page.open_detail_section("Augmentation")
    noise_source = window.training_page.field_controls["augmentation.noise_source"]
    noise_item = noise_source.model().item(noise_source.control.findData("collection-selected"))
    assert noise_item.toolTip() == (
        "Using Collection audio as augmentation noise is not available in this version."
    )

    interface_copy: list[str] = []
    for widget in window.findChildren(QWidget):
        interface_copy.extend(
            text
            for text in (
                widget.accessibleName(),
                widget.accessibleDescription(),
                widget.toolTip(),
                widget.whatsThis(),
            )
            if text
        )
        if isinstance(widget, (QAbstractButton, QLabel)):
            interface_copy.append(widget.text())
    joined_copy = "\n".join(interface_copy)
    for rejected in (
        "manifest",
        "checksum",
        "runtime structure",
        "schema",
        "digest",
        "publication",
        "immutable",
        "provenance",
        "source-time",
        "inventory",
        "published",
    ):
        assert rejected.casefold() not in joined_copy.casefold()
    assert re.search(r"\bworker\b", joined_copy, flags=re.IGNORECASE) is None

    hint = next(
        item
        for item in window.select_page.findChildren(HelpHint)
        if item.accessibleName() == "More about Collection folders"
    )
    hint.setFocus()
    qtbot.keyClick(hint, Qt.Key.Key_Space)
    assert hint.accessibleDescription() == APPROVED_TRAIN_CONTEXT_HELP["Collection folders"]


@pytest.mark.qt
@pytest.mark.parametrize("family_index,family", [(0, "cnn"), (1, "rf")])
def test_every_detailed_native_training_field_is_interactive_and_described(
    qapp, qtbot, tmp_path, wav_factory, monkeypatch, family_index, family
):
    """Cases: IT-TRAIN-010, IT-TRAIN-011, IT-UI-005."""
    window, _dataset = _window(qtbot, tmp_path, wav_factory)
    page = window.training_page
    page.family_input.setCurrentIndex(family_index)
    page.more_settings.setFocus()
    qtbot.keyClick(page.more_settings, Qt.Key.Key_Space)
    assert page.more_settings.isChecked()
    for section in page.detail_sections():
        page.open_detail_section(section)
    qapp.processEvents()

    fields = [field for field in fields_for_family(family) if field.ui_tier == "details"]
    assert fields
    edited = []
    for field in fields:
        widget = page.field_widgets[field.key]
        hint = page.help_hints[field.key]
        control = page.field_controls[field.key]
        owning_sections = [
            name for name, content in page.section_contents.items() if content.isAncestorOf(widget)
        ]
        assert len(owning_sections) == 1
        assert page.section_buttons[owning_sections[0]].isChecked()
        assert not page.section_contents[owning_sections[0]].isHidden()
        assert not widget.isHidden()
        assert hint.focusPolicy() != Qt.FocusPolicy.NoFocus
        assert hint.accessibleDescription() == field.help
        assert hint.toolTip() == field.help
        native_control = getattr(control, "control", control)
        assert field.help in native_control.accessibleDescription()
        if field.mode == "derived":
            assert control.isReadOnly()
            continue

        assert page.field_value(field.key) == field.default
        assert field.recommended_starting_value == field.default
        assert field.recommendation_basis == "backend_default_baseline"
        changed_to = _interact_with_alternative(qtbot, page, field)
        if changed_to is None:
            continue
        qapp.processEvents()
        if field.kind == "float":
            assert page.field_value(field.key) == pytest.approx(changed_to)
        else:
            assert page.field_value(field.key) == changed_to
        assert field.key in page.draft.modified_keys()
        assert not page.reset_buttons[field.key].isHidden()
        edited.append(field.key)
        page.reset_buttons[field.key].click()
        assert page.field_value(field.key) == field.default

    assert edited
    preserved_key = edited[0]
    preserved_field = next(field for field in fields if field.key == preserved_key)
    preserved_value = _interact_with_alternative(qtbot, page, preserved_field)
    page.more_settings.click()
    page.more_settings.click()
    assert page.field_value(preserved_key) == preserved_value
    assert page.modified_badge.text() == "1 modified"

    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    page.reset_details_button.click()
    assert page.field_value(preserved_key) == preserved_field.default
    assert page.modified_badge.text() == "Defaults"


@pytest.mark.qt
def test_native_training_page_primary_disclosure_family_drafts_and_wiki(
    qapp, qtbot, tmp_path, wav_factory
):
    """Cases: IT-TRAIN-010, IT-UI-005."""
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
    visible_text = {label.text().lower() for label in page.findChildren(Text)}
    assert all("backend default" not in text for text in visible_text)
    assert page.cards.getItemPosition(page.cards.indexOf(page.dataset_card))[:2] == (0, 0)
    assert page.cards.getItemPosition(page.cards.indexOf(page.config_card))[:2] == (1, 0)
    assert page.cards.getItemPosition(page.cards.indexOf(page.start_card))[:2] == (2, 0)
    assert window.open_draft_button.isVisible()

    page.set_field_value("training.batch_size", 32)
    window.navigate("settings")
    window.open_draft_button.click()
    assert window.current_route == "training"
    assert page.field_value("training.batch_size") == 32
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
        page.help_hints[field.key].accessibleDescription() == field.help
        for field in fields_for_family("cnn")
    )
    page.open_detail_section("Spectrogram")
    assert page.field_widgets["spectrogram.n_fft"].isVisible()
    hint = page.help_hints["spectrogram.n_fft"]
    assert isinstance(hint, HelpHint)
    hint.setFocus()
    qtbot.keyClick(hint, Qt.Key.Key_Space)
    assert hint.accessibleDescription() == next(
        field.help for field in fields_for_family("cnn") if field.key == "spectrogram.n_fft"
    )
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
    page.set_field_value("n_estimators", 1200)
    page.family_input.setCurrentIndex(0)
    assert page.field_value("training.batch_size") == 32
    page.family_input.setCurrentIndex(1)
    assert page.field_value("n_estimators") == 1200
    page.discard_button.click()
    assert window.current_route == "datasets"
    assert not window.open_draft_button.isVisible()
    assert page.field_value("training.batch_size") == 16


@pytest.mark.qt
def test_native_validation_preserves_values_blocks_launch_and_resets(
    qapp, qtbot, tmp_path, wav_factory, monkeypatch
):
    """Cases: IT-TRAIN-011, IT-UI-005, IT-SIZE-002, IT-SIZE-003."""
    window, _dataset = _window(qtbot, tmp_path, wav_factory)
    page = window.training_page
    page.more_settings.click()
    page.open_detail_section("Spectrogram")
    assert isinstance(page.field_controls["spectrogram.n_fft"], NumberInput)

    learning_rate = page.field_controls["training.learning_rate"]
    assert learning_rate.control.minimum() == 0
    assert learning_rate.control.decimals() == 5
    learning_rate.setValue(-1)
    assert learning_rate.value() == 0
    page.reset_field("training.learning_rate")

    device = page.field_controls["device"]
    mps_index = device.control.findData("mps")
    mps_item = device.model().item(mps_index)
    assert not mps_item.isEnabled()
    assert mps_item.toolTip() == "Apple GPU training is not available in this version."
    assert "Apple GPU training is not available" in device.control.accessibleDescription()
    assert device.descriptionText() == ""

    noise_source = page.field_controls["augmentation.noise_source"]
    collection_noise_index = noise_source.control.findData("collection-selected")
    collection_noise_item = noise_source.model().item(collection_noise_index)
    assert not collection_noise_item.isEnabled()
    assert collection_noise_item.toolTip() == (
        "Using Collection audio as augmentation noise is not available in this version."
    )
    assert "Using Collection audio as augmentation noise is not available" in (
        noise_source.control.accessibleDescription()
    )
    assert noise_source.descriptionText() == ""

    page.set_field_value("spectrogram.n_fft", 1024)
    page.set_field_value("spectrogram.hop_length", 2048)

    assert page.field_value("spectrogram.hop_length") == 2048
    assert not page.start_button.isEnabled()
    assert "FFT hop must not exceed" in page.error_alert.text_widget.text()
    page.reset_field("spectrogram.hop_length")
    assert page.field_value("spectrogram.hop_length") == 441
    assert page.start_button.isEnabled()
    assert page.storage_estimate.expected_final.kind == "range"
    assert page.storage_section.note.text() == (
        "Output size varies with the recording and settings."
    )
    cnn_high = page.storage_estimate.expected_final.high_bytes
    page.family_input.setCurrentIndex(1)
    assert page.storage_estimate.expected_final.kind == "range"
    assert page.storage_estimate.expected_final.high_bytes < cnn_high
    page.family_input.setCurrentIndex(0)
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
    window.controller._capacity_probe = lambda path, label: CapacityObservation(
        label,
        "tight-volume",
        700 * 1024**2,
        datetime(2026, 11, 3, tzinfo=UTC),
    )
    page._validate_and_refresh()
    assert page.storage_estimate.decision is StorageDecision.TIGHT
    assert page.storage_section.note.text() == "Storage may run low while this runs. Continue?"

    def accept_dialog(dialog):
        buttons = {button.text(): button for button in dialog.buttons()}
        assert set(buttons) == {"Cancel", "Continue"}
        assert dialog.defaultButton().text() == "Cancel"
        assert dialog.escapeButton().text() == "Cancel"
        buttons["Continue"].click()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", accept_dialog)
    assert confirm_storage(page, page.storage_estimate)
    monkeypatch.setattr(
        "biocall_studio.train.gui.training.confirm_storage", lambda *_args: False
    )
    page.start_button.click()
    assert not started
    assert window.controller.active_run is None

    window.controller._capacity_probe = lambda path, label: CapacityObservation(
        label,
        "ready-volume",
        2 * 1024**3,
        datetime(2026, 11, 3, tzinfo=UTC),
    )
    page._validate_and_refresh()
    monkeypatch.setattr(
        "biocall_studio.train.gui.training.confirm_storage", lambda *_args: True
    )
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *_args, **_kwargs: ("UI verified CNN", True),
    )
    monkeypatch.setattr(
        window.controller,
        "start_training",
        lambda config, *, model_label, storage_digest, confirm_storage: started.update(
            config=config,
            model_label=model_label,
            storage_digest=storage_digest,
            confirm_storage=confirm_storage,
        ),
    )
    page.start_button.click()
    assert page.last_frozen_config is not None
    assert page.last_frozen_config.dataset_id == "dataset-training-ui"
    assert started == {
        "config": page.last_frozen_config,
        "model_label": "UI verified CNN",
        "storage_digest": page.storage_estimate.input_digest,
        "confirm_storage": False,
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
