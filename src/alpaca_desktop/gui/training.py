"""Native Dataset → Model configuration → Start Training surface."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from alp_ui.components import (
    Alert,
    Badge,
    Button,
    Card,
    CheckBox,
    Divider,
    HelpHint,
    NumberInput,
    ProgressBar,
    SelectInput,
    Text,
    TextInput,
)
from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from alpaca_desktop.domain.training import (
    DeviceCapabilities,
    FieldDefinition,
    FrozenTrainingConfig,
    TrainingDataset,
    TrainingDraft,
    TrainingValidationError,
    fields_for_family,
    freeze_training_config,
)
from alpaca_desktop.gui.power import KeepAwakeControl
from alpaca_desktop.persistence.datasets import DatasetArtifact, list_datasets, load_dataset
from alpaca_desktop.persistence.training_presets import PresetRecord, PresetStore

_SECTION_ORDER = {
    "cnn": (
        "Spectrogram",
        "Normalization",
        "Augmentation",
        "Architecture",
        "Optimization & validation",
        "Execution",
    ),
    "rf": ("Forest", "Acoustic features & preprocessing", "Execution"),
}


def _ui_section(family: str, field: FieldDefinition) -> str:
    if field.family == "Common":
        return "Execution"
    if family == "cnn" and field.section == "Optimization":
        return "Optimization & validation"
    if family == "rf" and field.section in {"Basics", "Forest"}:
        return "Forest"
    if family == "rf" and field.section == "Features":
        return "Acoustic features & preprocessing"
    return field.section


def _display_value(value: object) -> str:
    if value is None:
        return "Unlimited"
    if value == "":
        return "Empty"
    if value is True:
        return "On"
    if value is False:
        return "Off"
    return str(value)


_FLOAT_DECIMALS = {
    "training.learning_rate": 12,
    "training.lr_decay_factor": 12,
    "feature_config.min_duration_s": 9,
}


class TrainingWikiPage(QScrollArea):
    def __init__(self, back: Callable[[], None]):
        super().__init__()
        self.anchor = ""
        self.field_key = ""
        self.setWidgetResizable(True)
        self.setAccessibleName("Training configuration Wiki")
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(38, 30, 38, 42)
        layout.setSpacing(16)
        layout.addWidget(Text("WIKI  /  TRAINING CONFIGURATION", role="overline"))
        self.title = Text("Training configuration", role="title")
        layout.addWidget(self.title)
        self.anchor_label = Text("", role="caption", selectable=True)
        layout.addWidget(self.anchor_label)
        card = Card(shadow=False)
        self.help_text = Text("", role="body", word_wrap=True)
        card.content_layout.addWidget(self.help_text)
        card.content_layout.addWidget(
            Text(
                "Defaults are reproducible backend baselines, not evidence-backed optima. "
                "The selected Dataset and available hardware are validated before a Run can start.",
                role="caption",
                word_wrap=True,
            )
        )
        layout.addWidget(card)
        self.back_button = Button("← Back to Model configuration", variant="outline")
        self.back_button.clicked.connect(back)
        layout.addWidget(self.back_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        self.setWidget(content)

    def show_field(self, field: FieldDefinition) -> None:
        self.field_key = field.key
        self.anchor = field.wiki_anchor
        self.title.setText(field.label)
        self.anchor_label.setText(field.wiki_anchor)
        self.help_text.setText(field.help)
        self.back_button.setFocus()


class PresetManagerDialog(QDialog):
    def __init__(self, page: TrainingPage):
        super().__init__(page)
        self.page = page
        self.setWindowTitle("Manage saved configurations")
        self.setAccessibleName("Manage saved configurations")
        self.resize(560, 360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        layout.addWidget(Text("Saved configurations", role="heading"))
        layout.addWidget(
            Text(
                "Reusable user-level settings. Datasets and Collection paths are never stored.",
                role="caption",
                word_wrap=True,
            )
        )
        self.list_widget = QListWidget()
        self.list_widget.setAccessibleName("Saved configuration list")
        layout.addWidget(self.list_widget, 1)
        actions = QHBoxLayout()
        self.rename_button = Button("Rename", variant="outline", size="small")
        self.duplicate_button = Button("Duplicate", variant="outline", size="small")
        self.overwrite_button = Button("Overwrite", variant="secondary", size="small")
        self.delete_button = Button("Delete", variant="danger", size="small")
        self.close_button = Button("Close", variant="outline", size="small")
        for button in (
            self.rename_button,
            self.duplicate_button,
            self.overwrite_button,
            self.delete_button,
        ):
            actions.addWidget(button)
        actions.addStretch()
        actions.addWidget(self.close_button)
        layout.addLayout(actions)
        self.rename_button.clicked.connect(self._rename)
        self.duplicate_button.clicked.connect(self._duplicate)
        self.overwrite_button.clicked.connect(self._overwrite)
        self.delete_button.clicked.connect(self._delete)
        self.close_button.clicked.connect(self.close)
        self.list_widget.currentRowChanged.connect(self._update_actions)
        self.refresh()

    def refresh(self) -> None:
        selected = self.selected_id()
        self.list_widget.clear()
        for record in self.page._preset_records():
            self.list_widget.addItem(f"{record.label}  ·  {record.family.upper()}")
            item = self.list_widget.item(self.list_widget.count() - 1)
            item.setData(Qt.ItemDataRole.UserRole, record.preset_id)
            if record.preset_id == selected:
                self.list_widget.setCurrentItem(item)
        if self.list_widget.currentRow() < 0 and self.list_widget.count():
            self.list_widget.setCurrentRow(0)
        self._update_actions()

    def selected_id(self) -> str | None:
        item = self.list_widget.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item is not None else None

    def _update_actions(self, *_args) -> None:
        enabled = self.selected_id() is not None
        for button in (
            self.rename_button,
            self.duplicate_button,
            self.overwrite_button,
            self.delete_button,
        ):
            button.setEnabled(enabled)

    def _rename(self) -> None:
        preset_id = self.selected_id()
        if preset_id is None:
            return
        current = self.page.preset_store.load(preset_id).record
        label, accepted = QInputDialog.getText(
            self, "Rename configuration", "Name", text=current.label
        )
        if accepted:
            self.page.rename_preset(preset_id, label)
            self.refresh()

    def _duplicate(self) -> None:
        preset_id = self.selected_id()
        if preset_id is None:
            return
        current = self.page.preset_store.load(preset_id).record
        label, accepted = QInputDialog.getText(
            self, "Duplicate configuration", "New name", text=f"{current.label} copy"
        )
        if accepted:
            self.page.duplicate_preset(preset_id, label)
            self.refresh()

    def _overwrite(self) -> None:
        preset_id = self.selected_id()
        if preset_id is None:
            return
        answer = QMessageBox.question(
            self,
            "Overwrite saved configuration?",
            "Replace its saved values with the current draft?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.page.overwrite_preset(preset_id)
            self.refresh()

    def _delete(self) -> None:
        preset_id = self.selected_id()
        if preset_id is not None:
            self.page.delete_preset(preset_id)
            self.refresh()


class TrainingPage(QScrollArea):
    def __init__(
        self,
        controller,
        preset_store: PresetStore,
        open_wiki: Callable[[FieldDefinition], None],
        open_power_wiki: Callable[[], None],
    ):
        super().__init__()
        self.controller = controller
        self.preset_store = preset_store
        self.open_wiki = open_wiki
        self.open_power_wiki = open_power_wiki
        self.capabilities = DeviceCapabilities.detect()
        self.drafts = {"cnn": TrainingDraft.defaults("cnn"), "rf": TrainingDraft.defaults("rf")}
        self._preset_origins: dict[str, str | None] = {"cnn": None, "rf": None}
        self.family = "cnn"
        self.dataset_id: str | None = None
        self.collection_root: Path | None = None
        self.artifact: DatasetArtifact | None = None
        self.last_frozen_config: FrozenTrainingConfig | None = None
        self._compact = False
        self._updating = False
        self.manage_dialog: PresetManagerDialog | None = None
        self.field_widgets: dict[str, QWidget] = {}
        self.field_controls: dict[str, QWidget] = {}
        self.field_captions: dict[str, Text] = {}
        self.help_hints: dict[str, HelpHint] = {}
        self.wiki_buttons: dict[str, Button] = {}
        self.section_buttons: dict[str, Button] = {}
        self.section_contents: dict[str, QWidget] = {}
        self.reset_buttons: dict[str, Button] = {}

        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setAccessibleName("Train Model")
        self.content = QWidget()
        self.outer = QVBoxLayout(self.content)
        self.outer.setContentsMargins(38, 30, 38, 42)
        self.outer.setSpacing(16)
        self.outer.addWidget(Text("Datasets  /  Train Model", role="caption"))
        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(3)
        heading.addWidget(Text("TRAINING", role="overline"))
        heading.addWidget(Text("Train a Model", role="title"))
        heading.addWidget(
            Text(
                "Choose a classifier. Training uses the selected immutable Dataset.",
                role="caption",
            )
        )
        header.addLayout(heading)
        header.addStretch()
        header.addWidget(Badge("Runs locally", intent="neutral"))
        self.outer.addLayout(header)

        self.cards = QGridLayout()
        self.cards.setSpacing(16)
        self.dataset_card = self._build_dataset_card()
        self.config_card = self._build_config_card()
        self.start_card = self._build_start_card()
        self.left_stack = QWidget()
        self.left_layout = QVBoxLayout(self.left_stack)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(16)
        self.outer.addLayout(self.cards)
        self.outer.addStretch()
        self.setWidget(self.content)
        self._place_cards(False)
        self._rebuild_form()
        self.verticalScrollBar().setValue(0)
        controller.run_changed.connect(self._run_state_changed)
        controller.training_started.connect(self._training_started)
        controller.training_completed.connect(self._training_finished)
        controller.training_failed.connect(self._training_finished)
        controller.training_cancelled.connect(self._training_finished)

    @property
    def draft(self) -> TrainingDraft:
        return self.drafts[self.family]

    def _build_dataset_card(self) -> Card:
        card = Card(shadow=False)
        header = QHBoxLayout()
        title = QVBoxLayout()
        title.setSpacing(2)
        title.addWidget(Text("1 · Dataset", role="subheading"))
        title.addWidget(Text("Positive and mined-negative WAV Snippets", role="caption"))
        header.addLayout(title)
        header.addStretch()
        header.addWidget(
            HelpHint(
                "CNN and Random Forest use the same immutable Dataset with train and val Splits.",
                subject="Training Dataset",
            )
        )
        card.content_layout.addLayout(header)
        self.dataset_input = SelectInput(label="Dataset")
        self.dataset_input.currentIndexChanged.connect(self._dataset_changed)
        card.content_layout.addWidget(self.dataset_input)
        self.dataset_summary = Card(shadow=False)
        summary = QHBoxLayout()
        self.target_count = Text("0\ntarget", role="body")
        self.noise_count = Text("0\nnoise", role="body")
        self.total_count = Text("0\ntotal WAV snippets", role="body")
        for widget in (self.target_count, self.noise_count, self.total_count):
            summary.addWidget(widget, 1)
        self.dataset_summary.content_layout.addLayout(summary)
        self.class_mix = ProgressBar(maximum=1, value=0)
        self.class_mix.setTextVisible(False)
        self.class_mix.setFixedHeight(9)
        self.class_mix.setAccessibleName("Dataset target share")
        self.dataset_summary.content_layout.addWidget(self.class_mix)
        card.content_layout.addWidget(self.dataset_summary)
        self.collection_value = Text("—", role="body")
        self.split_value = Text("train / val", role="body")
        for label, value in (("Collection", self.collection_value), ("Splits", self.split_value)):
            row = QHBoxLayout()
            row.addWidget(Text(label, role="caption"))
            row.addStretch()
            row.addWidget(value)
            card.content_layout.addLayout(row)
        return card

    def _build_config_card(self) -> Card:
        card = Card(shadow=False)
        header = QHBoxLayout()
        title = QVBoxLayout()
        title.setSpacing(2)
        title.addWidget(Text("2 · Model configuration", role="subheading"))
        self.family_caption = Text("CNN · spectrogram", role="caption")
        title.addWidget(self.family_caption)
        header.addLayout(title)
        header.addStretch()
        header.addWidget(
            HelpHint(
                "CNN and Random Forest are different model families selected on this "
                "Training page.",
                subject="Model families",
            )
        )
        card.content_layout.addLayout(header)
        self.family_input = SelectInput(
            ("CNN · Spectrogram", "Random Forest · Acoustic features"), label="Model family"
        )
        self.family_input.currentIndexChanged.connect(self._family_changed)
        card.content_layout.addWidget(self.family_input)

        preset_row = QHBoxLayout()
        self.preset_input = SelectInput(("Defaults",), label="Saved configurations")
        self.preset_input.currentIndexChanged.connect(self._preset_selected)
        preset_row.addWidget(self.preset_input, 1)
        self.save_as_button = Button("Save as…", variant="outline", size="small")
        self.manage_button = Button("Manage…", variant="outline", size="small")
        self.save_as_button.clicked.connect(self._prompt_save_as)
        self.manage_button.clicked.connect(self.open_preset_manager)
        preset_row.addWidget(self.save_as_button, 0, Qt.AlignmentFlag.AlignBottom)
        preset_row.addWidget(self.manage_button, 0, Qt.AlignmentFlag.AlignBottom)
        card.content_layout.addLayout(preset_row)
        self.preset_alert = Alert(
            "",
            title="Saved configurations unavailable",
            intent="warning",
        )
        self.preset_alert.hide()
        card.content_layout.addWidget(self.preset_alert)
        card.content_layout.addWidget(Divider())

        self.form_container = QWidget()
        self.form_layout = QVBoxLayout(self.form_container)
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.form_layout.setSpacing(10)
        card.content_layout.addWidget(self.form_container)
        self.error_alert = Alert("", title="Check Model configuration", intent="danger")
        self.error_alert.hide()
        card.content_layout.addWidget(self.error_alert)
        return card

    def _build_start_card(self) -> Card:
        card = Card(shadow=False)
        header = QHBoxLayout()
        header.addWidget(Text("3 · Start Training", role="subheading"))
        header.addStretch()
        header.addWidget(
            HelpHint(
                "The complete validated configuration is frozen before future Worker dispatch.",
                subject="Start Training",
            )
        )
        card.content_layout.addLayout(header)
        self.dataset_safety = Alert(
            "Train a neural network and track loss and validation metrics.",
            title="Dataset stays unchanged",
            intent="success",
        )
        card.content_layout.addWidget(self.dataset_safety)
        self.run_summary = Text("CNN · Dataset not selected · CPU/automatic", role="caption")
        card.content_layout.addWidget(self.run_summary)
        self.launch_alert = Alert("", title="Configuration verified", intent="info")
        self.launch_alert.hide()
        card.content_layout.addWidget(self.launch_alert)
        self.power_control = KeepAwakeControl(self.controller, self.open_power_wiki)
        card.content_layout.addWidget(self.power_control)
        self.keep_awake_toggle = self.power_control.toggle
        self.keep_awake_status = self.power_control.status
        self.keep_awake_hint = self.power_control.hint
        self.keep_awake_wiki_button = self.power_control.wiki_button
        self.keep_awake_retry_button = self.power_control.retry_button
        self.keep_awake_error = self.power_control.error
        actions = QHBoxLayout()
        self.run_availability = Text("One Active Run at a time.", role="caption")
        actions.addWidget(self.run_availability)
        actions.addStretch()
        self.start_button = Button("Start Training", size="large")
        self.start_button.clicked.connect(self._prepare_start)
        actions.addWidget(self.start_button)
        card.content_layout.addLayout(actions)
        return card

    def _place_cards(self, compact: bool) -> None:
        for card in (self.dataset_card, self.config_card, self.start_card):
            self.cards.removeWidget(card)
        while self.left_layout.count():
            self.left_layout.takeAt(0)
        self.cards.removeWidget(self.left_stack)
        if compact:
            self.cards.addWidget(self.dataset_card, 0, 0)
            self.cards.addWidget(self.config_card, 1, 0)
            self.cards.addWidget(self.start_card, 2, 0)
            self.cards.setColumnStretch(0, 1)
            self.cards.setColumnStretch(1, 0)
        else:
            self.left_layout.addWidget(self.dataset_card)
            self.left_layout.addWidget(self.start_card)
            self.left_layout.addStretch()
            self.cards.addWidget(self.left_stack, 0, 0, Qt.AlignmentFlag.AlignTop)
            self.cards.addWidget(self.config_card, 0, 1, Qt.AlignmentFlag.AlignTop)
            self.cards.setColumnStretch(0, 3)
            self.cards.setColumnStretch(1, 2)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        compact = event.size().width() < 850
        if compact != self._compact:
            self._compact = compact
            self._place_cards(compact)

    def set_dataset(self, collection_root: Path, artifact: DatasetArtifact) -> None:
        self.collection_root = collection_root
        artifacts = list_datasets(collection_root)
        blocker = QSignalBlocker(self.dataset_input.control)
        self.dataset_input.control.clear()
        selected_index = 0
        for index, item in enumerate(artifacts):
            self.dataset_input.addItem(f"{item.label} · {item.dataset_id}", item.dataset_id)
            if item.dataset_id == artifact.dataset_id:
                selected_index = index
        self.dataset_input.setCurrentIndex(selected_index)
        del blocker
        self._apply_dataset(artifact)

    def _dataset_changed(self, index: int) -> None:
        if self._updating or self.collection_root is None or index < 0:
            return
        dataset_id = self.dataset_input.control.itemData(index)
        if dataset_id:
            self._apply_dataset(load_dataset(self.collection_root, str(dataset_id)))

    def _apply_dataset(self, artifact: DatasetArtifact) -> None:
        self.artifact = artifact
        self.dataset_id = artifact.dataset_id
        counts = artifact.manifest["counts"]
        self.target_count.setText(f"{counts['target']}\ntarget")
        self.noise_count.setText(f"{counts['noise']}\nnoise")
        self.total_count.setText(f"{counts['total']}\ntotal WAV snippets")
        self.class_mix.setMaximum(max(1, counts["total"]))
        self.class_mix.setValue(counts["target"])
        self.collection_value.setText(artifact.manifest["collection_label"])
        self._validate_and_refresh()

    def _family_changed(self, index: int) -> None:
        if self._updating:
            return
        self.family = "rf" if index == 1 else "cnn"
        self.family_caption.setText(
            "Random Forest · acoustic features" if self.family == "rf" else "CNN · spectrogram"
        )
        self.dataset_safety.text_widget.setText(
            "Extract features, fit a forest, validate and save the classifier."
            if self.family == "rf"
            else "Train a neural network and track loss and validation metrics."
        )
        self.last_frozen_config = None
        self.launch_alert.hide()
        self._rebuild_form()
        self.verticalScrollBar().setValue(0)

    def _clear_form(self) -> None:
        while self.form_layout.count():
            item = self.form_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()

    def _rebuild_form(self) -> None:
        self._updating = True
        self._clear_form()
        self.field_widgets = {}
        self.field_controls = {}
        self.field_captions = {}
        self.help_hints = {}
        self.wiki_buttons = {}
        self.section_buttons = {}
        self.section_contents = {}
        self.reset_buttons = {}
        fields = fields_for_family(self.family)
        primary = [field for field in fields if field.ui_tier == "primary"]
        primary_grid = QGridLayout()
        primary_grid.setSpacing(10)
        for index, field in enumerate(primary):
            widget = self._field_widget(field, detailed=False)
            primary_grid.addWidget(widget, index // 2, index % 2)
        self.form_layout.addLayout(primary_grid)

        self.more_settings = Button("More settings", variant="outline")
        self.more_settings.setCheckable(True)
        self.more_settings.setAccessibleDescription(
            "Collapsed. Reveals detailed family-specific training settings."
        )
        self.more_settings.toggled.connect(self._toggle_more_settings)
        self.form_layout.addWidget(self.more_settings)
        self.details_container = QWidget()
        details_layout = QVBoxLayout(self.details_container)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(8)
        reset_row = QHBoxLayout()
        self.modified_badge = Badge("Defaults", intent="neutral")
        reset_row.addWidget(self.modified_badge)
        reset_row.addStretch()
        self.reset_details_button = Button(
            "Reset detailed settings", variant="outline", size="small"
        )
        self.reset_details_button.clicked.connect(self._confirm_reset_details)
        reset_row.addWidget(self.reset_details_button)
        details_layout.addLayout(reset_row)
        detailed = [field for field in fields if field.ui_tier == "details"]
        for section in _SECTION_ORDER[self.family]:
            section_fields = [
                field for field in detailed if _ui_section(self.family, field) == section
            ]
            if not section_fields:
                continue
            button = Button(f"{section}  ·  {len(section_fields)}", variant="outline", size="small")
            button.setCheckable(True)
            button.setAccessibleDescription(f"Collapsed {section} settings")
            content = QWidget()
            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(10, 6, 0, 8)
            content_layout.setSpacing(9)
            for field in section_fields:
                content_layout.addWidget(self._field_widget(field, detailed=True))
            content.hide()
            button.toggled.connect(
                lambda checked, name=section: self._toggle_section(name, checked)
            )
            self.section_buttons[section] = button
            self.section_contents[section] = content
            details_layout.addWidget(button)
            details_layout.addWidget(content)
        self.details_container.hide()
        self.form_layout.addWidget(self.details_container)
        self._updating = False
        self._refresh_preset_selector()
        self._validate_and_refresh()

    def _field_widget(self, field: FieldDefinition, *, detailed: bool) -> QWidget:
        widget = QWidget()
        widget.setObjectName(f"trainingField_{field.key.replace('.', '_')}")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label_row = QHBoxLayout()
        label = QLabel(field.label)
        hint_text = (
            f"{field.help} Wiki: {field.wiki_anchor}. "
            "Suggested starting point uses the backend default; it is not an "
            "evidence-backed optimum."
            if field.mode == "editable"
            else f"{field.help} Wiki: {field.wiki_anchor}. Automatically determined."
        )
        hint = HelpHint(hint_text, subject=field.label)
        label_row.addWidget(label)
        label_row.addWidget(hint)
        wiki = Button("Wiki →", variant="outline", size="small")
        wiki.setAccessibleName(f"Open Wiki for {field.label}")
        wiki.clicked.connect(lambda checked=False, item=field: self.open_wiki(item))
        if not detailed:
            label_row.addWidget(wiki)
        label_row.addStretch()
        layout.addLayout(label_row)
        control = self._make_control(field)
        native_control = getattr(control, "control", control)
        label.setBuddy(native_control)
        native_control.setAccessibleName(field.label)
        layout.addWidget(control)
        if field.mode == "derived":
            caption_text = "Automatically determined"
        else:
            caption_text = (
                f"Default / suggested starting value: {_display_value(field.default)}"
                + (" · backend default" if detailed else "")
            )
        caption = Text(caption_text, role="caption", word_wrap=True)
        layout.addWidget(caption)
        actions = QHBoxLayout()
        if field.mode == "editable":
            reset = Button("Reset field", variant="outline", size="small")
            reset.clicked.connect(lambda checked=False, key=field.key: self.reset_field(key))
            self.reset_buttons[field.key] = reset
            if detailed:
                actions.addWidget(reset)
            else:
                reset.hide()
                layout.addWidget(reset, 0, Qt.AlignmentFlag.AlignLeft)
        if detailed:
            actions.addWidget(wiki)
            actions.addStretch()
            layout.addLayout(actions)
        self.field_widgets[field.key] = widget
        self.field_controls[field.key] = control
        self.field_captions[field.key] = caption
        self.help_hints[field.key] = hint
        self.wiki_buttons[field.key] = wiki
        return widget

    def _make_control(self, field: FieldDefinition) -> QWidget:
        value = self.draft.value(field.key)
        if field.mode == "derived":
            control = TextInput(text=_display_value(value))
            control.setReadOnly(True)
            return control
        if field.kind == "text":
            control = TextInput(text=str(value))
            control.textChanged.connect(lambda _text, key=field.key: self._control_changed(key))
            return control
        if field.kind in {"int", "nullable_int"}:
            control = NumberInput(
                kind="integer",
                minimum=-2_147_483_647,
                maximum=2_147_483_647,
                value=0 if value is None else int(value),
            )
            control.valueChanged.connect(lambda _value, key=field.key: self._control_changed(key))
            return control
        if field.kind == "float":
            control = NumberInput(
                kind="decimal",
                minimum=-1_000_000_000,
                maximum=1_000_000_000,
                decimals=_FLOAT_DECIMALS.get(field.key, 8),
                step=0.01,
                value=float(value),
            )
            control.valueChanged.connect(lambda _value, key=field.key: self._control_changed(key))
            return control
        if field.kind == "select":
            control = SelectInput()
            for choice in field.choices:
                control.addItem(_display_value(choice), choice)
            selected = control.control.findData(value)
            control.setCurrentIndex(max(0, selected))
            unavailable: list[tuple[object, str]] = []
            for index in range(control.count()):
                choice = control.control.itemData(index)
                reason = self._unavailable_choice_reason(field.key, choice)
                if reason:
                    unavailable.append((choice, reason))
                    item = control.model().item(index)
                    if item is not None:
                        item.setEnabled(False)
                        item.setToolTip(reason)
            if unavailable:
                description = self._unavailable_field_description(field.key, unavailable)
                control.setDescriptionText(description)
            control.currentIndexChanged.connect(
                lambda _index, key=field.key: self._control_changed(key)
            )
            return control
        if field.kind == "bool":
            control = CheckBox("On")
            control.setChecked(bool(value))
            control.toggled.connect(lambda _checked, key=field.key: self._control_changed(key))
            return control
        raise ValueError(f"Unsupported training field kind: {field.kind}")

    def _unavailable_choice_reason(self, key: str, choice: object) -> str:
        if key == "device" and choice == "cuda" and not self.capabilities.cuda:
            return "CUDA is unavailable because it was not detected in this runtime."
        if key == "device" and choice == "mps" and not self.capabilities.mps:
            return "MPS is unavailable in the verified training executor."
        if key == "augmentation.noise_source" and choice == "collection-selected":
            return "Collection-selected noise is unavailable until executor support is verified."
        return ""

    @staticmethod
    def _unavailable_field_description(key: str, unavailable: list[tuple[object, str]]) -> str:
        choices = {choice for choice, _reason in unavailable}
        if key == "device":
            parts = []
            if "cuda" in choices:
                parts.append("CUDA not detected")
            if "mps" in choices:
                parts.append("MPS unsupported by verified executor")
            return "Unavailable: " + "; ".join(parts) + "."
        if key == "augmentation.noise_source":
            return "Unavailable: collection-selected noise lacks verified executor support."
        return "Unavailable: " + "; ".join(reason for _choice, reason in unavailable)

    def _control_value(self, key: str) -> object:
        field = next(field for field in fields_for_family(self.family) if field.key == key)
        control = self.field_controls[key]
        if field.kind == "text":
            return control.text()
        if field.kind == "int":
            return int(control.value())
        if field.kind == "nullable_int":
            value = int(control.value())
            return None if value == 0 else value
        if field.kind == "float":
            return float(control.value())
        if field.kind == "select":
            return control.control.currentData()
        if field.kind == "bool":
            return bool(control.isChecked())
        return field.default

    def _set_control_value(self, key: str, value: object) -> None:
        field = next(field for field in fields_for_family(self.family) if field.key == key)
        control = self.field_controls[key]
        native = getattr(control, "control", control)
        blocker = QSignalBlocker(native)
        if field.kind == "text":
            control.setText(str(value))
        elif field.kind in {"int", "float"}:
            control.setValue(value)
        elif field.kind == "nullable_int":
            control.setValue(0 if value is None else value)
        elif field.kind == "select":
            control.setCurrentIndex(control.control.findData(value))
        elif field.kind == "bool":
            control.setChecked(bool(value))
        del blocker

    def _control_changed(self, key: str) -> None:
        if self._updating:
            return
        self.draft.set(key, self._control_value(key))
        self._preset_origins[self.family] = None
        self.last_frozen_config = None
        self.launch_alert.hide()
        self._refresh_preset_selector()
        self._validate_and_refresh()

    def set_field_value(self, key: str, value: object) -> None:
        self.draft.set(key, value)
        self._set_control_value(key, value)
        self._preset_origins[self.family] = None
        self._refresh_preset_selector()
        self._validate_and_refresh()

    def field_value(self, key: str) -> object:
        return self.draft.value(key)

    def reset_field(self, key: str) -> None:
        self.draft.reset(key)
        self._set_control_value(key, self.draft.value(key))
        self._preset_origins[self.family] = None
        self._refresh_preset_selector()
        self._validate_and_refresh()

    def _confirm_reset_details(self) -> None:
        changed = {
            field.key
            for field in fields_for_family(self.family)
            if field.ui_tier == "details" and field.key in self.draft.modified_keys()
        }
        if changed:
            answer = QMessageBox.question(
                self,
                "Reset detailed settings?",
                "Discard all non-default detailed values for this model family?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.draft.reset_details()
        for key in changed:
            self._set_control_value(key, self.draft.value(key))
        self._preset_origins[self.family] = None
        self._refresh_preset_selector()
        self._validate_and_refresh()

    def _toggle_more_settings(self, checked: bool) -> None:
        self.details_container.setVisible(checked)
        self.more_settings.setText("Hide settings" if checked else "More settings")
        self.more_settings.setAccessibleDescription(
            ("Expanded" if checked else "Collapsed")
            + ". Reveals detailed family-specific training settings."
        )

    def _toggle_section(self, name: str, checked: bool) -> None:
        self.section_contents[name].setVisible(checked)
        self.section_buttons[name].setAccessibleDescription(
            f"{'Expanded' if checked else 'Collapsed'} {name} settings"
        )

    def open_detail_section(self, name: str) -> None:
        if not self.more_settings.isChecked():
            self.more_settings.setChecked(True)
        self.section_buttons[name].setChecked(True)

    def detail_sections(self) -> set[str]:
        return set(self.section_buttons)

    def visible_field_keys(self) -> set[str]:
        return {field.key for field in fields_for_family(self.family) if field.ui_tier == "primary"}

    def editable_field_keys(self) -> set[str]:
        return {field.key for field in fields_for_family(self.family) if field.mode == "editable"}

    def _dataset_context(self) -> TrainingDataset | None:
        if self.artifact is None:
            return None
        try:
            return TrainingDataset.from_artifact(self.artifact)
        except ValueError:
            return None

    def _run_state_changed(self, _run) -> None:
        self._validate_and_refresh()

    def _training_started(self) -> None:
        self.start_button.setLoading(True)

    def _training_finished(self, *_args) -> None:
        self.start_button.setLoading(False)

    def _validate_and_refresh(self) -> None:
        dataset = self._dataset_context()
        errors = (
            {"dataset": "Select a valid binary target/noise Dataset."}
            if dataset is None
            else self.draft.validate(dataset, self.capabilities)
        )
        for key, control in self.field_controls.items():
            if hasattr(control, "setErrorText"):
                control.setErrorText(errors.get(key, ""))
        if errors:
            first = next(iter(errors.values()))
            suffix = f" {len(errors) - 1} more issue(s)." if len(errors) > 1 else ""
            self.error_alert.text_widget.setText(first + suffix)
            self.error_alert.show()
        else:
            self.error_alert.hide()
        active = self.controller.active_run is not None
        self.start_button.setEnabled(not errors and not active)
        self.run_availability.setText(
            "Another Run is active." if active else "One Active Run at a time."
        )
        modified_details = sum(
            field.key in self.draft.modified_keys()
            for field in fields_for_family(self.family)
            if field.ui_tier == "details"
        )
        if hasattr(self, "modified_badge"):
            self.modified_badge.setText(
                f"{modified_details} modified" if modified_details else "Defaults"
            )
        modified = self.draft.modified_keys()
        for key, button in self.reset_buttons.items():
            if (
                next(field for field in fields_for_family(self.family) if field.key == key).ui_tier
                == "primary"
            ):
                button.setVisible(key in modified)
        device = self.draft.value("device") if self.family == "cnn" else "CPU"
        dataset_label = self.dataset_id or "Dataset not selected"
        primary = (
            f"{self.draft.value('training.max_epochs')} epochs · batch "
            f"{self.draft.value('training.batch_size')}"
            if self.family == "cnn"
            else f"{self.draft.value('n_estimators')} trees · depth "
            f"{_display_value(self.draft.value('max_depth'))}"
        )
        self.run_summary.setText(f"{self.family.upper()} · {dataset_label} · {device} · {primary}")

    def _prepare_start(self) -> None:
        dataset = self._dataset_context()
        if dataset is None:
            return
        try:
            self.last_frozen_config = freeze_training_config(
                self.draft,
                dataset,
                self.capabilities,
                preset_origin=self._preset_origins[self.family],
            )
        except TrainingValidationError as exc:
            first_key = next(iter(exc.errors))
            control = self.field_controls.get(first_key)
            if control is not None:
                getattr(control, "control", control).setFocus()
            self._validate_and_refresh()
            return
        if self.artifact is None:
            return
        family_label = "CNN" if self.family == "cnn" else "Random Forest"
        default_label = f"{self.artifact.label} · {family_label}"
        label, accepted = QInputDialog.getText(
            self,
            "Name your Model",
            "Model display name",
            text=default_label[:80],
        )
        if not accepted:
            return
        try:
            self.controller.start_training(
                self.last_frozen_config,
                model_label=label,
            )
        except (OSError, ValueError) as exc:
            self.launch_alert.title_widget.setText("Training could not start")
            self.launch_alert.text_widget.setText(str(exc))
            self.launch_alert.show()

    def _refresh_preset_selector(self) -> None:
        records = [record for record in self._preset_records() if record.family == self.family]
        origin = self._preset_origins[self.family]
        dirty = bool(self.draft.modified_keys()) and origin is None
        blocker = QSignalBlocker(self.preset_input.control)
        self.preset_input.control.clear()
        self.preset_input.addItem("Defaults", "defaults")
        for record in records:
            self.preset_input.addItem(record.label, record.preset_id)
        if dirty:
            self.preset_input.addItem("Unsaved changes", "unsaved")
            self.preset_input.setCurrentIndex(self.preset_input.count() - 1)
        elif origin is not None:
            index = self.preset_input.control.findData(origin)
            self.preset_input.setCurrentIndex(max(0, index))
        else:
            self.preset_input.setCurrentIndex(0)
        del blocker

    def _preset_records(self) -> tuple[PresetRecord, ...]:
        try:
            records = self.preset_store.list()
        except (OSError, ValueError) as exc:
            self.preset_alert.text_widget.setText(str(exc))
            self.preset_alert.setAccessibleName(f"Saved configurations warning: {exc}")
            self.preset_alert.show()
            return ()
        self.preset_alert.hide()
        return records

    def _preset_selected(self, index: int) -> None:
        if self._updating or index < 0:
            return
        preset_id = self.preset_input.control.itemData(index)
        if preset_id == "defaults":
            self.drafts[self.family] = TrainingDraft.defaults(self.family)
            self._preset_origins[self.family] = None
            self._rebuild_form()
        elif preset_id not in {None, "unsaved"}:
            self.load_preset(str(preset_id))

    def _prompt_save_as(self) -> None:
        label, accepted = QInputDialog.getText(self, "Save configuration as", "Name")
        if accepted:
            try:
                self.save_preset_as(label)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "Could not save configuration", str(exc))

    def save_preset_as(self, label: str) -> PresetRecord:
        record = self.preset_store.create(label, self.draft)
        self._preset_origins[self.family] = record.preset_id
        self._refresh_preset_selector()
        return record

    def load_preset(self, preset_id: str) -> PresetRecord:
        loaded = self.preset_store.load(preset_id)
        self.drafts[loaded.record.family] = loaded.draft
        self.family = loaded.record.family
        self._preset_origins[self.family] = preset_id
        blocker = QSignalBlocker(self.family_input.control)
        self.family_input.setCurrentIndex(0 if self.family == "cnn" else 1)
        del blocker
        self.family_caption.setText(
            "CNN · spectrogram" if self.family == "cnn" else "Random Forest · acoustic features"
        )
        self._rebuild_form()
        return loaded.record

    def rename_preset(self, preset_id: str, label: str) -> PresetRecord:
        record = self.preset_store.rename(preset_id, label)
        self._refresh_preset_selector()
        return record

    def duplicate_preset(self, preset_id: str, label: str) -> PresetRecord:
        record = self.preset_store.duplicate(preset_id, label)
        self._refresh_preset_selector()
        return record

    def overwrite_preset(self, preset_id: str) -> PresetRecord:
        record = self.preset_store.overwrite(preset_id, self.draft)
        self._preset_origins[self.family] = preset_id
        self._refresh_preset_selector()
        return record

    def delete_preset(self, preset_id: str) -> None:
        record = self.preset_store.load(preset_id).record
        answer = QMessageBox.question(
            self,
            "Delete saved configuration?",
            f"Delete {record.label}? This does not change any Dataset or completed Run.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.preset_store.delete(preset_id)
        if self._preset_origins.get(record.family) == preset_id:
            self._preset_origins[record.family] = None
        self._refresh_preset_selector()

    def open_preset_manager(self) -> None:
        self.manage_dialog = PresetManagerDialog(self)
        self.manage_dialog.show()
        self.manage_dialog.raise_()
        self.manage_dialog.activateWindow()

    def restore_field_focus(self, key: str) -> None:
        button = self.wiki_buttons.get(key)
        if button is not None:
            button.setFocus()
