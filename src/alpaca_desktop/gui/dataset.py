"""Native Dataset Builder, list, and immutable Dataset detail views."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from alp_ui.components import (
    Alert,
    Badge,
    Button,
    Card,
    CheckBox,
    DataTable,
    EmptyState,
    HelpHint,
    NumberInput,
    ProgressBar,
    SelectInput,
    Text,
)
from alp_ui.theme import ALPACA_LIGHT, make_icon
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from alpaca_desktop.application.workspace import WorkspaceController
from alpaca_desktop.domain.collection import ScanResult
from alpaca_desktop.domain.dataset import BuildConfig
from alpaca_desktop.persistence.datasets import (
    DatasetArtifact,
    dataset_dependents,
    list_datasets,
)
from alpaca_desktop.workflows.dataset_build import estimate_dataset_build


def _duration(seconds: float) -> str:
    if seconds >= 3_600:
        return f"{seconds / 3_600:.1f} h"
    if seconds >= 60:
        return f"{seconds / 60:.1f} min"
    return f"{seconds:.1f} s"


def _heading(title: str, subtitle: str, *, overline: str) -> QWidget:
    widget = QWidget()
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(3)
    layout.addWidget(Text(overline, role="overline"))
    layout.addWidget(Text(title, role="title"))
    layout.addWidget(Text(subtitle, role="caption", word_wrap=True))
    return widget


def _section_header(
    title: str,
    subtitle: str = "",
    *,
    help_text: str = "",
    subject: str = "",
) -> QHBoxLayout:
    row = QHBoxLayout()
    labels = QVBoxLayout()
    labels.setSpacing(2)
    labels.addWidget(Text(title, role="subheading"))
    if subtitle:
        labels.addWidget(Text(subtitle, role="caption", word_wrap=True))
    row.addLayout(labels)
    row.addStretch()
    if help_text:
        row.addWidget(HelpHint(help_text, subject=subject or title))
    return row


def _field_with_help(field: QWidget, label: str, help_text: str) -> QWidget:
    wrapper = QWidget()
    layout = QVBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    header = QHBoxLayout()
    header.addWidget(Text(label, role="body"))
    header.addWidget(HelpHint(help_text, subject=label))
    header.addStretch()
    layout.addLayout(header)
    layout.addWidget(field)
    field.setAccessibleName(label)
    control = getattr(field, "control", None)
    if control is not None:
        control.setAccessibleName(label)
        control.setAccessibleDescription(help_text)
    return wrapper


class SourceSelectionModel(QAbstractTableModel):
    selection_changed = Signal()
    HEADERS = ("INCLUDE", "SOURCE RECORDING", "DURATION", "POSITIVES")

    def __init__(self, result: ScanResult, parent=None):
        super().__init__(parent)
        self._records = result.records
        self._selected = {record.id for record in self._records}

    @property
    def selected_ids(self) -> tuple[str, ...]:
        return tuple(record.id for record in self._records if record.id in self._selected)

    @property
    def selected_count(self) -> int:
        return len(self._selected)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._records)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        record = self._records[index.row()]
        if role == Qt.ItemDataRole.CheckStateRole and index.column() == 0:
            return Qt.CheckState.Checked if record.id in self._selected else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                "",
                record.name,
                _duration(record.fingerprint.header.duration_seconds),
                record.positive_count,
            )[index.column()]
        if role == Qt.ItemDataRole.AccessibleTextRole:
            state = "included" if record.id in self._selected else "excluded"
            return f"{record.name}, {state}, {record.positive_count} positives"
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def flags(self, index: QModelIndex):
        flags = super().flags(index)
        if index.isValid() and index.column() == 0:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole):  # noqa: N802
        if not index.isValid() or index.column() != 0 or role != Qt.ItemDataRole.CheckStateRole:
            return False
        record_id = self._records[index.row()].id
        if value == Qt.CheckState.Checked:
            self._selected.add(record_id)
        else:
            self._selected.discard(record_id)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
        self.selection_changed.emit()
        return True

    def set_all(self, selected: bool) -> None:
        self._selected = {record.id for record in self._records} if selected else set()
        if self._records:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._records) - 1, 0),
                [Qt.ItemDataRole.CheckStateRole],
            )
        self.selection_changed.emit()


class DatasetBuilderPage(QScrollArea):
    """Prototype-ordered Dataset Build configuration with real scientific estimates."""

    def __init__(self, controller: WorkspaceController):
        super().__init__()
        self.controller = controller
        self.result: ScanResult | None = None
        self.source_model: SourceSelectionModel | None = None
        self.is_compact = False
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAccessibleName("Dataset Builder")

        self.content = QWidget()
        self.outer = QVBoxLayout(self.content)
        self.outer.setContentsMargins(38, 30, 38, 42)
        self.outer.setSpacing(17)
        self.crumbs = Text("Collection  /  Build Dataset", role="caption")
        self.outer.addWidget(self.crumbs)
        header = QHBoxLayout()
        header.addWidget(
            _heading(
                "Create a training Dataset",
                "Select Source Recordings, then configure Negative Mining.",
                overline="DATASET BUILD",
            ),
            1,
        )
        header.addWidget(Badge("Immutable output", intent="neutral"), 0, Qt.AlignmentFlag.AlignTop)
        self.outer.addLayout(header)

        self.columns = QGridLayout()
        self.columns.setSpacing(16)
        self.left_stack = QWidget()
        left = QVBoxLayout(self.left_stack)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(15)
        self.sources_card = Card(shadow=False)
        self.sources_card.content_layout.addLayout(
            _section_header(
                "1 · Choose positive examples",
                "Include or exclude complete Source Recordings.",
                help_text=(
                    "Every selected Source Recording contributes its positive Annotations. "
                    "Deselecting one excludes its positives and its audio from Negative Mining."
                ),
            )
        )
        selection = QHBoxLayout()
        self.select_all = CheckBox("Select all")
        self.select_all.setChecked(True)
        selection.addWidget(self.select_all)
        selection.addStretch()
        self.selection_label = Text("0 of 0 recordings", role="caption")
        selection.addWidget(self.selection_label)
        self.sources_card.content_layout.addLayout(selection)
        self.sources_table = DataTable()
        self.sources_table.setAccessibleName("Participating Source Recordings")
        self.sources_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.sources_table.setMinimumHeight(250)
        self.sources_card.content_layout.addWidget(self.sources_table)
        left.addWidget(self.sources_card)

        self.preview_card = Card(shadow=False)
        self.preview_card.content_layout.addLayout(
            _section_header(
                "3 · Dataset preview",
                help_text=(
                    "Counts are deterministic configuration estimates. Publication still "
                    "revalidates input bytes and verifies every materialized Snippet."
                ),
            )
        )
        summary = QFrame()
        summary.setObjectName("datasetPreviewSummary")
        summary.setStyleSheet(
            f"QFrame#datasetPreviewSummary {{ background: {ALPACA_LIGHT.colors.background}; "
            f"border: 1px solid {ALPACA_LIGHT.colors.border}; border-radius: 9px; }}"
        )
        summary_layout = QHBoxLayout(summary)
        self.target_value = self._summary_value(summary_layout, "target Snippets")
        self.noise_value = self._summary_value(summary_layout, "noise Snippets")
        self.total_value = self._summary_value(summary_layout, "total")
        self.preview_card.content_layout.addWidget(summary)
        self.class_mix = ProgressBar()
        self.class_mix.setTextVisible(False)
        self.class_mix.setFixedHeight(9)
        self.class_mix.setAccessibleName("Estimated target share of Dataset Snippets")
        self.preview_card.content_layout.addWidget(self.class_mix)
        self.preview_rows: dict[str, Text] = {}
        for label in (
            "Selected Source Recordings",
            "Requested negatives / positive",
            "train / val (estimated)",
        ):
            row = QHBoxLayout()
            row.addWidget(Text(label, role="caption"))
            row.addStretch()
            value = Text("—", role="body")
            self.preview_rows[label] = value
            row.addWidget(value)
            self.preview_card.content_layout.addLayout(row)
        self.preview_alert = Alert("", title="", intent="warning")
        self.preview_alert.hide()
        self.preview_card.content_layout.addWidget(self.preview_alert)
        self.preview_card.content_layout.addWidget(
            Text(
                "Exact Split membership and underfill checks happen during Dataset Build. "
                "Input freshness is revalidated before publication.",
                role="caption",
                word_wrap=True,
            )
        )
        left.addWidget(self.preview_card)

        self.settings_card = Card(shadow=False)
        self.settings_card.content_layout.addLayout(
            _section_header(
                "2 · Negative Mining",
                "Sample noise from unlabelled audio.",
                help_text=(
                    "Negative Mining samples background windows, never overlapping known "
                    "positive or other protected source-time spans."
                ),
            )
        )
        self.negative_mode = SelectInput(("Per positive", "Total negatives"))
        self.settings_card.content_layout.addWidget(
            _field_with_help(
                self.negative_mode,
                "Negative amount",
                "Use negatives per positive, or specify a total number of noise Snippets.",
            )
        )
        self.negative_amount = NumberInput(
            kind="decimal", value=2.0, minimum=0, maximum=20, step=0.5, decimals=1
        )
        self.negative_amount.setLabelText("Negatives per positive")
        self.settings_card.content_layout.addWidget(self.negative_amount)
        self.allocation = SelectInput(("Proportional to positives", "Even across recordings"))
        self.settings_card.content_layout.addWidget(
            _field_with_help(
                self.allocation,
                "By Source Recording",
                "Proportional follows positive counts; even distributes requests across "
                "selected recordings.",
            )
        )
        field_row = QHBoxLayout()
        self.split = SelectInput(
            ("70% train / 30% val", "80% train / 20% val", "90% train / 10% val")
        )
        self.split.setCurrentIndex(1)
        field_row.addWidget(
            _field_with_help(
                self.split,
                "Training Split",
                "Group complete Source Recordings to prevent train/val audio leakage.",
            ),
            1,
        )
        self.seed = NumberInput(kind="integer", value=42, minimum=0, maximum=2_147_483_647, step=1)
        field_row.addWidget(
            _field_with_help(
                self.seed,
                "Seed",
                "The same selected inputs, bytes, seed, and settings produce equivalent output.",
            ),
            1,
        )
        self.settings_card.content_layout.addLayout(field_row)
        self.balance = CheckBox("Keep class ratio across Splits")
        self.balance.setChecked(True)
        self.balance.setAccessibleDescription(
            "Balance target and noise where feasible while keeping each Source Recording together."
        )
        self.settings_card.content_layout.addWidget(self.balance)
        self.settings_card.content_layout.addWidget(
            Text("Split by Source Recording · no source leakage", role="caption")
        )
        self.margin = SelectInput(("None", "0.25 s", "0.5 s", "1 s"))
        self.margin.setCurrentIndex(1)
        self.settings_card.content_layout.addWidget(
            _field_with_help(
                self.margin,
                "Positive exclusion margin",
                "Additional protected time on both sides of every known positive Annotation.",
            )
        )
        self.build_button = Button("Build Dataset", size="large", loading_text="Building Dataset…")
        self.build_button.setIcon(make_icon("plus", color=ALPACA_LIGHT.colors.on_primary, size=16))
        self.build_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.settings_card.content_layout.addWidget(self.build_button)
        no_mutation = Text("Source WAVs will not be modified.", role="caption")
        no_mutation.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.settings_card.content_layout.addWidget(no_mutation)

        self.columns.addWidget(self.left_stack, 0, 0)
        self.columns.addWidget(self.settings_card, 0, 1, Qt.AlignmentFlag.AlignTop)
        self.columns.setColumnStretch(0, 3)
        self.columns.setColumnStretch(1, 2)
        self.outer.addLayout(self.columns)
        self.outer.addStretch()
        self.setWidget(self.content)

        self.select_all.stateChanged.connect(self._select_all_changed)
        self.negative_mode.currentIndexChanged.connect(self._mode_changed)
        self.negative_amount.valueChanged.connect(self._refresh)
        self.allocation.currentIndexChanged.connect(self._refresh)
        self.split.currentIndexChanged.connect(self._refresh)
        self.seed.valueChanged.connect(self._refresh)
        self.balance.stateChanged.connect(self._refresh)
        self.margin.currentIndexChanged.connect(self._refresh)
        self.build_button.clicked.connect(self._start_build)
        controller.build_started.connect(lambda: self.set_busy(True))
        controller.build_failed.connect(self.show_build_error)

    @staticmethod
    def _summary_value(layout: QHBoxLayout, label: str) -> Text:
        column = QVBoxLayout()
        value = Text("0", role="heading")
        column.addWidget(value)
        column.addWidget(Text(label, role="caption"))
        layout.addLayout(column, 1)
        return value

    def set_collection(self, result: ScanResult) -> None:
        self.result = result
        self.crumbs.setText(f"{result.root_name}  /  Build Dataset")
        self.source_model = SourceSelectionModel(result, self.sources_table)
        self.source_model.selection_changed.connect(self._selection_changed)
        self.sources_table.setModel(self.source_model)
        self.sources_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.set_busy(self.controller.is_building)
        self._refresh()

    def config(self) -> BuildConfig:
        if self.source_model is None:
            raise ValueError("Open a validated Collection before Dataset Build.")
        mode = "ratio" if self.negative_mode.currentIndex() == 0 else "absolute"
        value = self.negative_amount.value()
        return BuildConfig(
            selected_recording_ids=self.source_model.selected_ids,
            negative_mode=mode,
            negative_ratio=float(value) if mode == "ratio" else 0.0,
            negative_count=round(value) if mode == "absolute" else 0,
            allocation="proportional" if self.allocation.currentIndex() == 0 else "even",
            train_percent=(70, 80, 90)[self.split.currentIndex()],
            balance_classes=self.balance.isChecked(),
            seed=int(self.seed.value()),
            margin_ms=(0, 250, 500, 1_000)[self.margin.currentIndex()],
        )

    def set_busy(self, busy: bool) -> None:
        self.build_button.setLoading(busy)
        for widget in (
            self.sources_table,
            self.select_all,
            self.negative_mode,
            self.negative_amount,
            self.allocation,
            self.split,
            self.seed,
            self.balance,
            self.margin,
        ):
            widget.setEnabled(not busy)
        if not busy:
            self._refresh()

    def show_build_error(self, message: str) -> None:
        self.set_busy(False)
        self.preview_alert.title_widget.setText("Dataset Build failed")
        self.preview_alert.text_widget.setText(message)
        self.preview_alert.setAccessibleName(f"Danger alert: Dataset Build failed: {message}")
        self.preview_alert.show()

    def _select_all_changed(self, state: int) -> None:
        if self.source_model is not None:
            self.source_model.set_all(state == Qt.CheckState.Checked.value)

    def _selection_changed(self) -> None:
        if self.source_model is None:
            return
        blocker = QSignalBlocker(self.select_all)
        count = self.source_model.selected_count
        total = self.source_model.rowCount()
        if count == total:
            self.select_all.setCheckState(Qt.CheckState.Checked)
        elif count == 0:
            self.select_all.setCheckState(Qt.CheckState.Unchecked)
        else:
            self.select_all.setCheckState(Qt.CheckState.PartiallyChecked)
        del blocker
        self._refresh()

    def _mode_changed(self) -> None:
        if self.negative_mode.currentIndex() == 0:
            self.negative_amount.setLabelText("Negatives per positive")
            self.negative_amount.control.setDecimals(1)
            self.negative_amount.setRange(0, 20)
            self.negative_amount.setSingleStep(0.5)
            if self.negative_amount.value() > 20:
                self.negative_amount.setValue(2)
        else:
            self.negative_amount.setLabelText("Total negatives")
            self.negative_amount.control.setDecimals(0)
            self.negative_amount.setRange(0, 200_000)
            self.negative_amount.setSingleStep(1)
        self._refresh()

    def _refresh(self, *_args) -> None:
        if self.result is None or self.source_model is None:
            self.build_button.setEnabled(False)
            return
        try:
            config = self.config()
            estimate = estimate_dataset_build(self.result, config)
        except ValueError as exc:
            estimate = {
                "source_count": self.source_model.selected_count,
                "target": 0,
                "noise_requested": 0,
                "noise_available": 0,
                "underfill": 0,
                "split": None,
                "error": str(exc),
            }
        target = estimate["target"]
        noise = estimate["noise_requested"]
        self.target_value.setText(f"{target:,}")
        self.noise_value.setText(f"{noise:,}")
        self.total_value.setText(f"{target + noise:,}")
        self.class_mix.setRange(0, max(1, target + noise))
        self.class_mix.setValue(target)
        self.selection_label.setText(
            f"{estimate['source_count']} of {self.source_model.rowCount()} recordings"
        )
        self.preview_rows["Selected Source Recordings"].setText(str(estimate["source_count"]))
        ratio = noise / target if target else 0
        self.preview_rows["Requested negatives / positive"].setText(f"{ratio:g} : 1")
        split = estimate["split"]
        if split is None:
            self.preview_rows["train / val (estimated)"].setText("—")
        else:
            self.preview_rows["train / val (estimated)"].setText(
                f"{split.counts['train']['total']} / {split.counts['val']['total']}"
            )
        error = estimate["error"]
        if error:
            title = (
                "Negative Mining underfill" if "underfill" in error.lower() else "Build unavailable"
            )
            self.preview_alert.title_widget.setText(title)
            self.preview_alert.text_widget.setText(error)
            self.preview_alert.setAccessibleName(f"Warning alert: {title}: {error}")
            self.preview_alert.show()
        else:
            self.preview_alert.hide()
        self.build_button.setEnabled(not error and not self.controller.is_building)

    def _start_build(self) -> None:
        try:
            self.controller.start_dataset_build(self.config())
        except ValueError as exc:
            self.show_build_error(str(exc))

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        compact = event.size().width() < 930
        self.content.setMaximumWidth(max(320, self.viewport().width()) if compact else 16_777_215)
        if compact == self.is_compact:
            return
        self.is_compact = compact
        self.columns.removeWidget(self.left_stack)
        self.columns.removeWidget(self.settings_card)
        if compact:
            self.columns.setColumnStretch(1, 0)
            self.columns.addWidget(self.left_stack, 0, 0)
            self.columns.addWidget(self.settings_card, 1, 0)
        else:
            self.columns.setColumnStretch(1, 2)
            self.columns.addWidget(self.left_stack, 0, 0)
            self.columns.addWidget(self.settings_card, 0, 1, Qt.AlignmentFlag.AlignTop)


class DatasetListModel(QAbstractTableModel):
    HEADERS = ("DATASET", "COLLECTION", "SNIPPETS", "CREATED", "")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._artifacts: tuple[DatasetArtifact, ...] = ()

    def set_artifacts(self, artifacts: tuple[DatasetArtifact, ...]) -> None:
        self.beginResetModel()
        self._artifacts = artifacts
        self.endResetModel()

    def artifact(self, row: int) -> DatasetArtifact:
        return self._artifacts[row]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._artifacts)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole or not index.isValid():
            return None
        artifact = self._artifacts[index.row()]
        manifest = artifact.manifest
        return (
            f"{artifact.label}\n{artifact.dataset_id}",
            manifest["collection_label"],
            f"{manifest['counts']['total']:,}",
            manifest["created_at"].split("T", 1)[0],
            "Open →",
        )[index.column()]

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None


class DatasetListPage(QScrollArea):
    def __init__(self, open_builder: Callable[[], None], open_dataset: Callable[[str], None]):
        super().__init__()
        self.open_builder = open_builder
        self.open_dataset = open_dataset
        self.collection_root: Path | None = None
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAccessibleName("Datasets")
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(38, 30, 38, 38)
        layout.setSpacing(16)
        header = QHBoxLayout()
        header.addWidget(
            _heading(
                "Datasets",
                "Published, immutable training inputs.",
                overline="DATA",
            ),
            1,
        )
        self.build_button = Button("Build Dataset")
        self.build_button.setIcon(make_icon("plus", color=ALPACA_LIGHT.colors.on_primary, size=15))
        self.build_button.clicked.connect(open_builder)
        header.addWidget(self.build_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)
        self.model = DatasetListModel(self)
        self.table = DataTable(model=self.model)
        self.table.setAccessibleName("Published Datasets")
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.table.clicked.connect(
            lambda index: self.open_dataset(self.model.artifact(index.row()).dataset_id)
        )
        layout.addWidget(self.table)
        empty_action = Button("Build Dataset")
        empty_action.clicked.connect(open_builder)
        self.empty = EmptyState(
            "No Datasets yet.",
            text="Start from a validated Collection and build real target/noise Snippets.",
            icon=make_icon("grid", color=ALPACA_LIGHT.colors.primary, size=28),
            action=empty_action,
        )
        layout.addWidget(self.empty, 1)
        self.error_alert = Alert("", title="Dataset storage", intent="danger")
        self.error_alert.hide()
        layout.addWidget(self.error_alert)
        layout.addStretch()
        self.setWidget(content)

    def refresh(self, collection_root: Path | None) -> None:
        self.collection_root = collection_root
        try:
            artifacts = list_datasets(collection_root) if collection_root is not None else ()
        except (OSError, ValueError) as exc:
            artifacts = ()
            self.error_alert.text_widget.setText(str(exc))
            self.error_alert.show()
        else:
            self.error_alert.hide()
        self.model.set_artifacts(artifacts)
        self.table.setVisible(bool(artifacts))
        self.table.setFixedHeight(max(120, 44 + 45 * len(artifacts)))
        self.empty.setVisible(not artifacts)
        self.build_button.setEnabled(collection_root is not None)


class DatasetDetailPage(QScrollArea):
    def __init__(
        self,
        delete_requested: Callable[[str], None],
        open_collection: Callable[[], None],
    ):
        super().__init__()
        self.delete_requested = delete_requested
        self.open_collection = open_collection
        self.dataset: DatasetArtifact | None = None
        self.collection_root: Path | None = None
        self.is_compact = False
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAccessibleName("Dataset detail")
        self.content = QWidget()
        self.outer = QVBoxLayout(self.content)
        self.outer.setContentsMargins(38, 30, 38, 42)
        self.outer.setSpacing(16)
        self.setWidget(self.content)

    def set_dataset(self, collection_root: Path, artifact: DatasetArtifact) -> None:
        self.collection_root = collection_root
        self.dataset = artifact
        while self.outer.count():
            item = self.outer.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())
        manifest = artifact.manifest
        self.outer.addWidget(Text(f"Datasets  /  {artifact.dataset_id}", role="caption"))
        header = QHBoxLayout()
        header.addWidget(
            _heading(
                artifact.label,
                f"Dataset ID · {artifact.dataset_id} · {manifest['created_at'].split('T', 1)[0]}",
                overline="IMMUTABLE DATASET",
            ),
            1,
        )
        actions = QHBoxLayout()
        self.delete_button = Button("Delete", variant="danger")
        self.delete_button.clicked.connect(self._confirm_delete)
        actions.addWidget(self.delete_button)
        self.train_button = Button("Train Model")
        self.train_button.setEnabled(False)
        self.train_button.setAccessibleDescription(
            "Training configuration becomes available in the Training vertical."
        )
        actions.addWidget(self.train_button)
        header.addLayout(actions)
        self.outer.addLayout(header)
        stats = QGridLayout()
        values = (
            ("Target Snippets", manifest["counts"]["target"], "positive examples"),
            ("Noise Snippets", manifest["counts"]["noise"], "mined background"),
            ("Total Snippets", manifest["counts"]["total"], "materialized WAV"),
            ("Source Recordings", len(manifest["selected_sources"]), "selected for build"),
        )
        self.stat_cards: list[Card] = []
        for column, (label, value, note) in enumerate(values):
            card = Card(shadow=False)
            card.content_layout.addWidget(Text(label, role="caption"))
            card.content_layout.addWidget(Text(f"{value:,}", role="heading"))
            card.content_layout.addWidget(Text(note, role="caption"))
            stats.addWidget(card, 0, column)
            self.stat_cards.append(card)
        self.outer.addLayout(stats)

        self.columns = QGridLayout()
        self.columns.setSpacing(16)
        left_stack = QWidget()
        left = QVBoxLayout(left_stack)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(15)
        split_card = Card(shadow=False)
        split_card.content_layout.addLayout(
            _section_header(
                "train / val Splits",
                help_text=(
                    "Split assignments are deterministic and grouped by Source Recording; "
                    "no source contributes to both train and val."
                ),
            )
        )
        for split in ("train", "val"):
            counts = manifest["counts"][split]
            row = QHBoxLayout()
            row.addWidget(Text(split, role="subheading"))
            row.addStretch()
            row.addWidget(Text(f"{counts['total']} Snippets", role="caption"))
            split_card.content_layout.addLayout(row)
            class_mix = ProgressBar(maximum=max(1, counts["total"]), value=counts["target"])
            class_mix.setTextVisible(False)
            class_mix.setFixedHeight(9)
            class_mix.setAccessibleName(f"{split} target share")
            split_card.content_layout.addWidget(class_mix)
            split_card.content_layout.addWidget(
                Text(
                    f"{counts['target']} target · {counts['noise']} noise",
                    role="caption",
                )
            )
        split_card.content_layout.addWidget(
            Alert(
                "Source metadata, build parameters, Splits and per-Snippet provenance "
                "are retained.",
                title="Immutable and reproducible",
                intent="success",
            )
        )
        left.addWidget(split_card)
        files_card = Card(shadow=False)
        files_card.content_layout.addLayout(
            _section_header(
                "Generated Dataset files",
                help_text="Verified app-owned files under the selected Collection.",
            )
        )
        tree = QLabel(
            f".alpaca/datasets/{artifact.dataset_id}/\n"
            "  dataset.json\n"
            "  entries/snippets-*.jsonl\n"
            "  snippets/target/*.wav\n"
            "  snippets/noise/*.wav\n"
            "  splits/train.csv\n"
            "  splits/val.csv"
        )
        tree.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        tree.setAccessibleName("Generated Dataset file tree")
        files_card.content_layout.addWidget(tree)
        left.addWidget(files_card)

        right_stack = QWidget()
        right = QVBoxLayout(right_stack)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(15)
        provenance = Card(shadow=False)
        provenance.content_layout.addWidget(Text("Dataset provenance", role="subheading"))
        collection_button = Button(
            f"{manifest['collection_label']} →", variant="outline", size="small"
        )
        collection_button.setAccessibleDescription(f"Open Collection {manifest['collection_id']}")
        collection_button.clicked.connect(self.open_collection)
        rows: tuple[tuple[str, QWidget], ...] = (
            ("Collection", collection_button),
            (
                "Negative amount",
                Text(
                    (
                        f"{manifest['config']['negative_ratio']:g} / positive"
                        if manifest["config"]["negative_mode"] == "ratio"
                        else f"{manifest['config']['negative_count']} total"
                    ),
                    role="body",
                ),
            ),
            (
                "Distribution",
                Text(manifest["config"]["allocation"].capitalize(), role="body"),
            ),
            (
                "Split",
                Text(
                    f"{manifest['config']['train_percent']} / "
                    f"{100 - manifest['config']['train_percent']}",
                    role="body",
                ),
            ),
            (
                "Class ratio per Split",
                Text(
                    "Requested" if manifest["config"]["balance_classes"] else "Not constrained",
                    role="body",
                ),
            ),
            (
                "Exclusion margin",
                Text(f"{manifest['config']['margin_ms'] / 1_000:g} s", role="body"),
            ),
            ("Seed", Text(str(manifest["config"]["seed"]), role="body")),
        )
        for label, value in rows:
            row = QHBoxLayout()
            row.addWidget(Text(label, role="caption"))
            row.addStretch()
            row.addWidget(value)
            provenance.content_layout.addLayout(row)
        right.addWidget(provenance)
        next_card = Card(shadow=False)
        next_card.content_layout.addWidget(Text("Next", role="subheading"))
        next_card.content_layout.addWidget(
            Text(
                "Train a classifier with these target/noise Snippets. Training is not "
                "implemented yet.",
                role="caption",
                word_wrap=True,
            )
        )
        disabled_train = Button("Train Model")
        disabled_train.setEnabled(False)
        disabled_train.setAccessibleDescription(
            "Training configuration becomes available in the Training vertical."
        )
        next_card.content_layout.addWidget(disabled_train)
        right.addWidget(next_card)
        right.addStretch()
        self.columns.addWidget(left_stack, 0, 0)
        self.columns.addWidget(right_stack, 0, 1, Qt.AlignmentFlag.AlignTop)
        self.columns.setColumnStretch(0, 3)
        self.columns.setColumnStretch(1, 2)
        self.left_stack = left_stack
        self.right_stack = right_stack
        self.outer.addLayout(self.columns)
        self.outer.addStretch()

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                DatasetDetailPage._clear_layout(item.layout())

    def _confirm_delete(self) -> None:
        if self.dataset is None or self.collection_root is None:
            return
        dependencies = dataset_dependents(self.collection_root, self.dataset.dataset_id)
        consequence = (
            f" {len(dependencies)} saved Model(s) will remain, but their Dataset files "
            "will no longer be available locally."
            if dependencies
            else ""
        )
        answer = QMessageBox.question(
            self,
            "Delete Dataset?",
            f"Delete {self.dataset.label}? Its Snippets and Split files will be removed. "
            f"The original Collection WAVs stay unchanged.{consequence}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.delete_requested(self.dataset.dataset_id)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        compact = event.size().width() < 930
        if compact == self.is_compact or self.dataset is None:
            return
        self.is_compact = compact
        self.columns.removeWidget(self.left_stack)
        self.columns.removeWidget(self.right_stack)
        if compact:
            self.columns.addWidget(self.left_stack, 0, 0)
            self.columns.addWidget(self.right_stack, 1, 0)
        else:
            self.columns.addWidget(self.left_stack, 0, 0)
            self.columns.addWidget(self.right_stack, 0, 1, Qt.AlignmentFlag.AlignTop)
