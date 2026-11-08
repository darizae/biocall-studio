"""Native Review spectrogram preset editor and independent WAV preview."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from alp_ui.components import Button, Card, HelpHint, SelectInput, Text
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from biocall_studio.review.application.controller import ReviewSessionController
from biocall_studio.review.domain.sessions import (
    DEFAULT_PRESET_ID,
    SpectrogramSettingsSnapshot,
)
from biocall_studio.review.domain.spectrograms import (
    SPECTROGRAM_ALGORITHM_VERSION,
    SPECTROGRAM_RENDER_VERSION,
    Palette,
    SoundDetail,
    SpectrogramImageTier,
    SpectrogramSettings,
)
from biocall_studio.review.gui.audio_proof import SpectrogramView
from biocall_studio.review.persistence.cache import encode_rgb_png
from biocall_studio.review.workflows.audio import read_preview_wav
from biocall_studio.review.workflows.spectrograms import (
    SpectrogramRenderRequest,
    render_spectrogram,
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class SavedExampleStore:
    """Small contained derivative-only store; selected WAV paths are never recorded."""

    def __init__(self, root: Path, *, limit_per_preset: int = 4):
        self.root = Path(root).resolve(strict=False)
        self.limit_per_preset = limit_per_preset

    def _directory(self, preset_id: str) -> Path:
        if not preset_id.startswith("rsp_") or len(preset_id) != 36:
            raise ValueError("Spectrogram preset identity is invalid.")
        directory = self.root / preset_id
        if not directory.is_relative_to(self.root):
            raise ValueError("Saved example path is unsafe.")
        return directory

    def save(self, preset: SpectrogramSettingsSnapshot, png: bytes) -> Path:
        if (
            not isinstance(png, bytes)
            or not png.startswith(b"\x89PNG\r\n\x1a\n")
            or not 1 <= len(png) <= 8 * 1_024 * 1_024
        ):
            raise ValueError("Saved example image is invalid.")
        directory = self._directory(preset.preset_id)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if directory.is_symlink():
            raise ValueError("Saved example directory is unsafe.")
        example_id = "example_" + uuid.uuid4().hex
        image_path = directory / f"{example_id}.png"
        metadata_path = directory / f"{example_id}.json"
        metadata = {
            "schema_version": 1,
            "preset_revision": preset.preset_revision,
            "settings_digest": preset.settings_digest,
            "image_sha256": hashlib.sha256(png).hexdigest(),
            "created_at": _now(),
        }
        temporary_image = directory / f".{example_id}.png.tmp"
        temporary_metadata = directory / f".{example_id}.json.tmp"
        temporary_image.write_bytes(png)
        temporary_metadata.write_text(
            json.dumps(metadata, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary_image, 0o600)
        os.chmod(temporary_metadata, 0o600)
        temporary_image.replace(image_path)
        temporary_metadata.replace(metadata_path)
        manifests = sorted(
            (
                path
                for path in directory.glob("example_*.json")
                if path.is_file() and not path.is_symlink()
            ),
            key=lambda path: path.stat().st_mtime_ns,
        )
        for old in manifests[: -self.limit_per_preset]:
            (directory / f"{old.stem}.png").unlink(missing_ok=True)
            old.unlink(missing_ok=True)
        return image_path

    def delete_preset(self, preset_id: str) -> None:
        directory = self._directory(preset_id)
        if not directory.exists():
            return
        if directory.is_symlink():
            raise ValueError("Saved example directory is unsafe.")
        for path in directory.iterdir():
            if path.is_file() and not path.is_symlink() and path.name.startswith("example_"):
                path.unlink()
        directory.rmdir()

    def revision_labels(self, preset: SpectrogramSettingsSnapshot) -> tuple[str, ...]:
        return tuple(label for _path, label in self.examples(preset))

    def examples(self, preset: SpectrogramSettingsSnapshot) -> tuple[tuple[Path, str], ...]:
        directory = self._directory(preset.preset_id)
        if not directory.is_dir() or directory.is_symlink():
            return ()
        examples: list[tuple[Path, str]] = []
        for path in sorted(directory.glob("example_*.json"), reverse=True):
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                if not 1 <= path.stat().st_size <= 16 * 1_024:
                    continue
                raw = json.loads(path.read_text(encoding="utf-8"))
                revision = int(raw["preset_revision"])
                image_path = directory / f"{path.stem}.png"
                if image_path.is_symlink() or not image_path.is_file():
                    continue
                if not 1 <= image_path.stat().st_size <= 8 * 1_024 * 1_024:
                    continue
                payload = image_path.read_bytes()
                if hashlib.sha256(payload).hexdigest() != raw["image_sha256"]:
                    continue
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
            examples.append(
                (
                    image_path,
                    (
                        "Saved example"
                        if revision == preset.preset_revision
                        else "Saved example · earlier version"
                    ),
                )
            )
        return tuple(examples)


class SpectrogramSettingsPage(QScrollArea):
    back_requested = Signal()
    use_in_session_requested = Signal(object)

    _CONTROL_SPECS = (
        (
            "frequency_max_hz",
            "Frequency range",
            ("Up to 3 kHz", "Up to 4.2 kHz", "Up to 8 kHz"),
            (3_000, 4_200, 8_000),
            (
                "Sets the highest pitch shown. A lower limit enlarges low sounds, "
                "but hides higher ones."
            ),
        ),
        (
            "sound_detail",
            "Sound detail",
            ("Fast changes", "Balanced", "Close pitches"),
            (
                SoundDetail.FAST_CHANGES.value,
                SoundDetail.BALANCED.value,
                SoundDetail.CLOSE_PITCHES.value,
            ),
            "Short windows show when sounds change; long windows help separate similar pitches.",
        ),
        (
            "context_seconds",
            "Time around call",
            (
                "1 second before and after",
                "2 seconds before and after",
                "3 seconds before and after",
            ),
            (1, 2, 3),
            "Shows more or less sound before and after the detected call.",
        ),
        (
            "contrast_db",
            "Contrast",
            ("40 dB — less background", "50 dB — balanced", "65 dB — more quiet sounds"),
            (40, 50, 65),
            "Shows quieter sounds. Higher contrast range may also reveal more background noise.",
        ),
        (
            "palette",
            "Colors",
            ("Magma", "Viridis"),
            (Palette.MAGMA.value, Palette.VIRIDIS.value),
            "Changes the colors without changing the sound or measurement.",
        ),
        (
            "exact_window_ms",
            "Exact sound window",
            (
                "Use Sound detail choice",
                "20 ms",
                "25 ms",
                "30 ms",
                "40 ms",
                "50 ms",
                "60 ms",
                "80 ms",
                "100 ms",
            ),
            (None, 20, 25, 30, 40, 50, 60, 80, 100),
            "Uses the Sound detail choice or a precise sound window for this preset.",
        ),
        (
            "overlap_percent",
            "Window overlap",
            ("50%", "75%"),
            (50, 75),
            "Higher overlap adds more time slices without changing pitch resolution.",
        ),
        (
            "frequency_min_hz",
            "Lowest frequency",
            ("0 Hz", "100 Hz", "300 Hz"),
            (0, 100, 300),
            "Hides low rumble below this frequency and may also hide low calls.",
        ),
    )

    def __init__(self, controller: ReviewSessionController, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        self.example_store = SavedExampleStore(controller.store.root / "examples")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAccessibleName("Review spectrogram settings")
        self._presets: list[SpectrogramSettingsSnapshot] = []
        self._current: SpectrogramSettingsSnapshot | None = None
        self._editing = False
        self._pending_new_name: str | None = None
        self._pending_rename: str | None = None
        self._preview_raster = None

        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(32, 26, 32, 36)
        outer.setSpacing(18)
        header = QHBoxLayout()
        header.addWidget(Text("Spectrogram settings", role="title"))
        header.addStretch()
        self.back_button = Button("Back to Review", variant="outline")
        self.back_button.clicked.connect(self.back_requested)
        header.addWidget(self.back_button)
        outer.addLayout(header)

        preset_card = Card()
        preset_row = QHBoxLayout()
        self.preset_select = SelectInput(label="Preset")
        self.preset_select.setMinimumWidth(240)
        preset_row.addWidget(self.preset_select, 1)
        self.new_button = Button("New preset", variant="outline")
        self.edit_button = Button("Edit", variant="outline")
        self.rename_button = Button("Rename", variant="outline")
        self.save_button = Button("Save changes", variant="primary")
        self.delete_button = Button("Delete", variant="danger")
        for button in (
            self.new_button,
            self.edit_button,
            self.rename_button,
            self.save_button,
            self.delete_button,
        ):
            preset_row.addWidget(button, 0, Qt.AlignmentFlag.AlignBottom)
        preset_card.content_layout.addLayout(preset_row)
        outer.addWidget(preset_card)

        controls_card = Card()
        controls_card.content_layout.addWidget(Text("Settings", role="heading"))
        self.controls: list[SelectInput] = []
        self._control_values: dict[str, tuple[object, ...]] = {}
        self._controls_by_name: dict[str, SelectInput] = {}
        simple = QGridLayout()
        simple.setHorizontalSpacing(18)
        simple.setVerticalSpacing(14)
        for index, (name, label, items, values, help_text) in enumerate(self._CONTROL_SPECS[:5]):
            field = self._make_control(name, label, items, values, help_text)
            simple.addWidget(field, index // 2, index % 2)
        controls_card.content_layout.addLayout(simple)
        self.advanced_box = Button("Advanced", variant="outline")
        self.advanced_box.setCheckable(True)
        self.advanced_box.setChecked(False)
        controls_card.content_layout.addWidget(self.advanced_box)
        self.advanced_widget = QWidget()
        advanced = QGridLayout(self.advanced_widget)
        advanced.setContentsMargins(0, 0, 0, 0)
        advanced.setHorizontalSpacing(18)
        for index, (name, label, items, values, help_text) in enumerate(self._CONTROL_SPECS[5:]):
            advanced.addWidget(self._make_control(name, label, items, values, help_text), 0, index)
        self.advanced_widget.setVisible(False)
        self.advanced_box.toggled.connect(self.advanced_widget.setVisible)
        self._controls_by_name["exact_window_ms"].currentIndexChanged.connect(
            lambda _index: self._update_custom_window_state()
        )
        controls_card.content_layout.addWidget(self.advanced_widget)
        outer.addWidget(controls_card)

        preview_card = Card()
        preview_header = QHBoxLayout()
        preview_header.addWidget(Text("Test WAV", role="heading"))
        preview_header.addStretch()
        self.test_button = Button("Test WAV", variant="outline")
        self.compare_button = Button("Compare", variant="outline")
        self.save_example_button = Button("Save example", variant="outline")
        preview_header.addWidget(self.test_button)
        preview_header.addWidget(self.compare_button)
        preview_header.addWidget(self.save_example_button)
        preview_card.content_layout.addLayout(preview_header)
        self.preview_status = QLabel()
        self.preview_status.setAccessibleName("Spectrogram preview status")
        preview_card.content_layout.addWidget(self.preview_status)
        preview_views = QHBoxLayout()
        self.saved_preview = SpectrogramView(show_detection=False)
        self.draft_preview = SpectrogramView(show_detection=False)
        preview_views.addWidget(self.saved_preview, 1)
        preview_views.addWidget(self.draft_preview, 1)
        preview_card.content_layout.addLayout(preview_views)
        self.examples_label = QLabel()
        self.examples_label.setWordWrap(True)
        preview_card.content_layout.addWidget(self.examples_label)
        self.examples_layout = QHBoxLayout()
        preview_card.content_layout.addLayout(self.examples_layout)
        outer.addWidget(preview_card)
        outer.addStretch()
        self.setWidget(content)

        self.preset_select.currentIndexChanged.connect(self._preset_changed)
        self.new_button.clicked.connect(self._new_preset)
        self.edit_button.clicked.connect(self._begin_edit)
        self.rename_button.clicked.connect(self._begin_rename)
        self.save_button.clicked.connect(self._save_changes)
        self.delete_button.clicked.connect(self._delete_preset)
        self.test_button.clicked.connect(self._choose_preview_wav)
        self.save_example_button.clicked.connect(self._save_example)
        self.compare_button.clicked.connect(self._toggle_compare)
        self.reload()

    def _make_control(self, name, label, items, values, help_text) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        control = SelectInput(items=items, label=label)
        control.control.setAccessibleName(label)
        help_hint = HelpHint(help_text, subject=label)
        layout.addWidget(control, 1)
        layout.addWidget(help_hint, 0, Qt.AlignmentFlag.AlignTop)
        self.controls.append(control)
        self._controls_by_name[name] = control
        self._control_values[name] = tuple(values)
        return wrapper

    def reload(self, *, select_id: str | None = None) -> None:
        self._presets = list(self.controller.list_presets())
        self.preset_select.control.blockSignals(True)
        self.preset_select.control.clear()
        for preset in self._presets:
            self.preset_select.addItem(preset.preset_name, preset.preset_id)
        index = 0
        if select_id is not None:
            index = next(
                (i for i, preset in enumerate(self._presets) if preset.preset_id == select_id),
                0,
            )
        self.preset_select.setCurrentIndex(index)
        self.preset_select.control.blockSignals(False)
        self._preset_changed(index)

    def _preset_changed(self, index: int) -> None:
        if not 0 <= index < len(self._presets):
            return
        self._current = self._presets[index]
        self._editing = False
        self._pending_new_name = None
        self._pending_rename = None
        self._load_mapping(self._current.effective_settings)
        self._update_enabled()
        self._update_examples()

    def _load_mapping(self, mapping: dict[str, object]) -> None:
        for name, control in self._controls_by_name.items():
            values = self._control_values[name]
            control.setCurrentIndex(values.index(mapping[name]))
        self._update_custom_window_state()

    def settings(self) -> SpectrogramSettings:
        values = {
            name: self._control_values[name][control.currentIndex()]
            for name, control in self._controls_by_name.items()
        }
        return SpectrogramSettings.from_mapping(values)

    def _update_enabled(self) -> None:
        protected = self._current is None or self._current.preset_id == DEFAULT_PRESET_ID
        for control in self.controls:
            control.setEnabled(self._editing)
        self.edit_button.setEnabled(not protected and not self._editing)
        self.rename_button.setEnabled(not protected and not self._editing)
        self.delete_button.setEnabled(not protected and not self._editing)
        self.save_button.setEnabled(self._editing)
        self.preset_select.setEnabled(not self._editing)
        self.new_button.setEnabled(not self._editing)
        self.test_button.setEnabled(True)
        self.compare_button.setEnabled(self._preview_raster is not None)
        self.save_example_button.setEnabled(self._preview_raster is not None)
        self._update_custom_window_state()

    def _update_custom_window_state(self) -> None:
        detail = self._controls_by_name.get("sound_detail")
        exact = self._controls_by_name.get("exact_window_ms")
        if detail is None or exact is None:
            return
        custom = self._control_values["exact_window_ms"][exact.currentIndex()] is not None
        detail.setEnabled(self._editing and not custom)
        detail.control.setAccessibleDescription(
            "Overridden by Exact sound window." if custom else ""
        )

    def _new_preset(self) -> None:
        name, accepted = QInputDialog.getText(self, "New preset", "Preset name")
        name = " ".join(name.split())
        if not accepted or not name:
            return
        self._pending_new_name = name
        self._editing = True
        self._update_enabled()
        self._controls_by_name["frequency_max_hz"].setFocus()

    def _begin_edit(self) -> None:
        if self._current is None or self._current.preset_id == DEFAULT_PRESET_ID:
            return
        self._editing = True
        self._update_enabled()

    def _begin_rename(self) -> None:
        if self._current is None or self._current.preset_id == DEFAULT_PRESET_ID:
            return
        name, accepted = QInputDialog.getText(
            self,
            "Rename preset",
            "Preset name",
            text=self._current.preset_name,
        )
        name = " ".join(name.split())
        if not accepted or not name or name == self._current.preset_name:
            return
        self._pending_rename = name
        self._editing = True
        self._update_enabled()

    def _save_changes(self) -> None:
        try:
            settings = self.settings().to_mapping()
        except (TypeError, ValueError) as exc:
            self.preview_status.setText(str(exc))
            return
        use_in_current = False
        if self._pending_new_name is not None:
            try:
                snapshot = self.controller.create_preset(
                    name=self._pending_new_name,
                    effective_settings=settings,
                    saved_at=_now(),
                )
            except (OSError, RuntimeError, TypeError, ValueError):
                self.preview_status.setText("Couldn't save your changes. Try again.")
                return
        elif self._current is not None:
            impact = self.controller.store.preset_impact(self._current.preset_id)
            dialog = QMessageBox(self)
            dialog.setWindowTitle("Save preset")
            dialog.setText(
                f"{impact.open_count} open, {impact.closed_count} closed and "
                f"{impact.finalized_count} finalized sessions use this preset or an earlier "
                "version. Their settings won't change."
            )
            cancel = dialog.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            save = dialog.addButton("Save preset", QMessageBox.ButtonRole.AcceptRole)
            save_and_use = None
            open_session = self.controller.store.open_session()
            if open_session is not None:
                session_settings = self.controller.store.load_settings(open_session.session_id)
                if session_settings.preset_id == self._current.preset_id:
                    save_and_use = dialog.addButton(
                        "Save and use in this session",
                        QMessageBox.ButtonRole.AcceptRole,
                    )
            dialog.setDefaultButton(cancel)
            dialog.setEscapeButton(cancel)
            dialog.exec()
            if dialog.clickedButton() not in {save, save_and_use}:
                return
            use_in_current = save_and_use is not None and dialog.clickedButton() is save_and_use
            try:
                snapshot = self.controller.update_preset(
                    self._current.preset_id,
                    expected_revision=self._current.preset_revision,
                    name=self._pending_rename or self._current.preset_name,
                    effective_settings=settings,
                    saved_at=_now(),
                )
            except (OSError, RuntimeError, TypeError, ValueError):
                self.preview_status.setText("Couldn't save your changes. Try again.")
                return
        else:
            return
        self.reload(select_id=snapshot.preset_id)
        if use_in_current:
            self.use_in_session_requested.emit(snapshot)

    def _delete_preset(self) -> None:
        if self._current is None or self._current.preset_id == DEFAULT_PRESET_ID:
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Delete preset")
        dialog.setText("Delete this preset and its saved examples? Session settings won't change.")
        cancel = dialog.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        delete = dialog.addButton("Delete", QMessageBox.ButtonRole.DestructiveRole)
        dialog.setDefaultButton(cancel)
        dialog.setEscapeButton(cancel)
        dialog.exec()
        if dialog.clickedButton() is not delete:
            return
        preset_id = self._current.preset_id
        try:
            self.controller.delete_preset(
                preset_id,
                expected_revision=self._current.preset_revision,
                deleted_at=_now(),
            )
            self.example_store.delete_preset(preset_id)
        except (OSError, RuntimeError, TypeError, ValueError):
            self.preview_status.setText("Couldn't delete this preset. Try again.")
            return
        self.reload()

    def _choose_preview_wav(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Choose WAV",
            "",
            "WAV audio (*.wav)",
        )
        if filename:
            self.preview_wav(Path(filename))

    def preview_wav(self, path: Path) -> None:
        try:
            audio = read_preview_wav(path)
            draft_settings = self.settings()
            request = SpectrogramRenderRequest(
                candidate_id=audio.context.candidate_id,
                source_sha256=audio.context.source_sha256,
                context=audio.context,
                settings=draft_settings,
                tier=SpectrogramImageTier.DETAIL,
                algorithm_version=SPECTROGRAM_ALGORITHM_VERSION,
                render_version=SPECTROGRAM_RENDER_VERSION,
            )
            self._preview_raster = render_spectrogram(audio.samples, request)
            self.draft_preview.set_spectrogram(self._preview_raster)
            if self._current is not None:
                saved_request = SpectrogramRenderRequest.from_snapshot(
                    candidate_id=audio.context.candidate_id,
                    source_sha256=audio.context.source_sha256,
                    context=audio.context,
                    snapshot=self._current,
                    tier=SpectrogramImageTier.DETAIL,
                )
                self.saved_preview.set_spectrogram(render_spectrogram(audio.samples, saved_request))
            self.preview_status.setText("Preview ready.")
        except (OSError, TypeError, ValueError) as exc:
            self._preview_raster = None
            self.saved_preview.clear_spectrogram()
            self.draft_preview.clear_spectrogram()
            self.preview_status.setText(str(exc))
        self._update_enabled()

    def _toggle_compare(self) -> None:
        self.saved_preview.setVisible(not self.saved_preview.isVisible())

    def _save_example(self) -> None:
        if self._current is None or self._preview_raster is None:
            return
        try:
            self.example_store.save(self._current, encode_rgb_png(self._preview_raster))
        except (OSError, TypeError, ValueError):
            self.preview_status.setText("Couldn't save this example. Try again.")
            return
        self._update_examples()

    def _update_examples(self) -> None:
        while self.examples_layout.count():
            item = self.examples_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        examples = () if self._current is None else self.example_store.examples(self._current)
        labels = tuple(label for _path, label in examples)
        self.examples_label.setText(" · ".join(labels))
        for path, label in examples:
            image = QLabel()
            image.setAccessibleName(label)
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                image.setPixmap(
                    pixmap.scaled(
                        QSize(240, 100),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            self.examples_layout.addWidget(image)
        self.examples_layout.addStretch()


__all__ = ["SavedExampleStore", "SpectrogramSettingsPage"]
