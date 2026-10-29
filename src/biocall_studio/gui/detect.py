"""Native Detect Collection setup, recording inventory, and explicit relinking."""

from __future__ import annotations

from dataclasses import dataclass

from alp_ui.components import (
    Badge,
    Button,
    Card,
    CheckBox,
    DataTable,
    FolderPicker,
    HelpHint,
    NumberInput,
    ProgressBar,
    SelectInput,
    Text,
)
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from biocall_studio.detect.controller import (
    DetectWorkspaceController,
    InventoryState,
    ModelIntakeState,
)
from biocall_studio.detect.detection import DetectionSettings
from biocall_studio.detect.domain import RootBindingDecision
from biocall_studio.detect.inventory import (
    DecisionOrigin,
    InclusionDecision,
    InventoryRecording,
    InventorySnapshot,
    RecordingStatus,
)
from biocall_studio.detect.runs import DetectRunStatus


def _duration(row: InventoryRecording) -> str:
    if row.wav is None:
        return "—"
    seconds = row.wav.frame_count / row.wav.sample_rate_hz
    if seconds >= 3_600:
        return f"{seconds / 3_600:.1f} h"
    if seconds >= 60:
        return f"{seconds / 60:.1f} min"
    return f"{seconds:.1f} s"


@dataclass(frozen=True, slots=True)
class _InventoryEntry:
    key: str
    is_folder: bool
    recording: InventoryRecording | None = None


class InventoryTableModel(QAbstractTableModel):
    """Expose a bounded page of folder summaries and immutable recording rows."""

    HEADERS = ("PATH", "DECISION", "STATUS", "DURATION")

    def __init__(self, parent=None, *, page_size: int = 200):
        super().__init__(parent)
        self._page_size = page_size
        self._entries: tuple[_InventoryEntry, ...] = ()
        self._visible = 0
        self._snapshot: InventorySnapshot | None = None

    def set_snapshot(self, snapshot: InventorySnapshot | None) -> None:
        self.beginResetModel()
        self._snapshot = snapshot
        folders: set[str] = set()
        recordings = () if snapshot is None else snapshot.recordings
        for recording in recordings:
            parts = recording.recording_key.split("/")[:-1]
            for index in range(1, len(parts) + 1):
                folders.add("/".join(parts[:index]) + "/")
        self._entries = tuple(
            [_InventoryEntry(path, True) for path in sorted(folders)]
            + [
                _InventoryEntry(recording.recording_key, False, recording)
                for recording in recordings
            ]
        )
        self._visible = min(self._page_size, len(self._entries))
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else self._visible

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def _folder_rows(self, key: str) -> tuple[InventoryRecording, ...]:
        if self._snapshot is None:
            return ()
        return tuple(
            row for row in self._snapshot.recordings if row.recording_key.startswith(key)
        )

    def _decision_text(self, rows: tuple[InventoryRecording, ...]) -> str:
        values = {row.decision.value for row in rows}
        return next(iter(values)).capitalize() if len(values) == 1 else "Mixed"

    def _status_text(self, rows: tuple[InventoryRecording, ...]) -> str:
        invalid = sum(row.status is RecordingStatus.INVALID for row in rows)
        missing = sum(row.status is RecordingStatus.MISSING for row in rows)
        if invalid:
            return f"{invalid} invalid"
        if missing:
            return f"{missing} missing"
        return f"{len(rows)} WAV" if rows else "Empty"

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= self._visible:
            return None
        entry = self._entries[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return entry.key
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if entry.is_folder:
            rows = self._folder_rows(entry.key)
            values = (
                f"▾  {entry.key}",
                self._decision_text(rows),
                self._status_text(rows),
                "—",
            )
        else:
            row = entry.recording
            assert row is not None
            values = (
                f"    {row.recording_key}",
                row.decision.value.capitalize(),
                row.status.value.capitalize(),
                _duration(row),
            )
        return values[index.column()]

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def canFetchMore(self, parent: QModelIndex = QModelIndex()) -> bool:  # noqa: N802
        return not parent.isValid() and self._visible < len(self._entries)

    def fetchMore(self, parent: QModelIndex = QModelIndex()) -> None:  # noqa: N802
        if parent.isValid() or not self.canFetchMore(parent):
            return
        count = min(self._page_size, len(self._entries) - self._visible)
        self.beginInsertRows(QModelIndex(), self._visible, self._visible + count - 1)
        self._visible += count
        self.endInsertRows()

    def row_for_key(self, key: str) -> int:
        for index, entry in enumerate(self._entries):
            if entry.key == key:
                while index >= self._visible and self.canFetchMore():
                    self.fetchMore()
                return index
        raise KeyError(key)

    def entry_at(self, row: int) -> _InventoryEntry | None:
        if 0 <= row < self._visible:
            return self._entries[row]
        return None


class DetectWorkspacePage(QScrollArea):
    """Researcher-facing Collection setup and read-only source inventory."""

    return_requested = Signal()

    def __init__(self, controller: DetectWorkspaceController):
        super().__init__()
        self.controller = controller
        self._compact = False
        self._rendered_inventory_id: str | None = None
        self.selected_key: str | None = None
        self.setObjectName("detectWorkspacePage")
        self.setAccessibleName("Detect Collection setup")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.content = QWidget()
        self.outer = QVBoxLayout(self.content)
        self.outer.setContentsMargins(48, 34, 48, 48)
        self.outer.setSpacing(22)
        self.outer.addLayout(self._build_heading())
        self.run_header = self._build_run_header()
        self.outer.addWidget(self.run_header)
        self.outer.addLayout(self._build_navigation())
        self.selection_error = QLabel()
        self.selection_error.setWordWrap(True)
        self.selection_error.setAccessibleName("Recordings folder error")
        self.selection_error.setStyleSheet("color: #B91C1C; font-weight: 600;")
        self.outer.addWidget(self.selection_error)

        self.route_stack = QStackedWidget()
        self.route_stack.setMinimumWidth(0)
        self.route_stack.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self.setup_view = QWidget()
        setup_view_layout = QVBoxLayout(self.setup_view)
        setup_view_layout.setContentsMargins(0, 0, 0, 0)
        setup_view_layout.setSpacing(16)
        self.setup_layout = QGridLayout()
        self.setup_layout.setHorizontalSpacing(16)
        self.setup_layout.setVerticalSpacing(16)
        self.model_card = self._build_model_card()
        self.collection_card = self._build_collection_card()
        self.setup_layout.addWidget(self.model_card, 0, 0)
        self.setup_layout.addWidget(self.collection_card, 0, 1)
        self.setup_layout.setColumnStretch(0, 1)
        self.setup_layout.setColumnStretch(1, 1)
        setup_view_layout.addLayout(self.setup_layout)
        self.settings_card = self._build_settings_card()
        setup_view_layout.addWidget(self.settings_card)
        self.readiness_card = Card()
        self.readiness_card.setAccessibleName("Detect setup readiness")
        self.readiness_title = Text("Setup needs attention", role="subheading")
        self.readiness_detail = Text(
            "Choose a compatible CNN Model and recordings folder.",
            role="body",
            word_wrap=True,
        )
        self.readiness_card.content_layout.addWidget(self.readiness_title)
        self.readiness_card.content_layout.addWidget(self.readiness_detail)
        setup_view_layout.addWidget(self.readiness_card)
        setup_view_layout.addStretch()

        self.recordings_view = QWidget()
        recordings_layout = QVBoxLayout(self.recordings_view)
        recordings_layout.setContentsMargins(0, 0, 0, 0)
        recordings_layout.setSpacing(18)
        self.recordings_card = self._build_recordings_card()
        recordings_layout.addWidget(self.recordings_card)
        self.inventory_content = self._build_inventory_content()
        recordings_layout.addWidget(self.inventory_content)
        self.relink_card = self._build_relink_card()
        recordings_layout.addWidget(self.relink_card)
        self.different_card = self._build_different_card()
        recordings_layout.addWidget(self.different_card)
        recordings_layout.addStretch()

        self.run_view = self._build_run_view()

        self.route_stack.addWidget(self.setup_view)
        self.route_stack.addWidget(self.recordings_view)
        self.route_stack.addWidget(self.run_view)
        self.outer.addWidget(self.route_stack)
        self.outer.addStretch()
        self.setWidget(self.content)

        self.controller.state_changed.connect(self._render)
        self.controller.scan_progress_changed.connect(lambda _progress: self._render_scan())
        self.model_picker.folderChanged.connect(self.controller.choose_model_root)
        self.folder_picker.folderChanged.connect(self.controller.choose_source_root)
        self.relink_picker.folderChanged.connect(self.controller.choose_source_root)
        self.current_route = "setup"
        self._set_route("setup")
        self._render()

    def _setting_row(self, field: QWidget, help_text: str, subject: str) -> QWidget:
        row = QWidget()
        field.setMinimumWidth(0)
        field.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        row.setMinimumWidth(0)
        row.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        layout = QGridLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(8)
        layout.addWidget(field, 0, 0)
        layout.addWidget(
            HelpHint(help_text, subject=subject),
            0,
            1,
            Qt.AlignmentFlag.AlignTop,
        )
        layout.setColumnStretch(0, 1)
        return row

    def _build_settings_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Candidate detection settings")
        card.content_layout.addWidget(Text("Candidate settings", role="heading"))
        card.content_layout.addWidget(
            Text(
                "Set how the CNN scans recordings and joins candidate intervals.",
                role="body",
                word_wrap=True,
            )
        )
        self.minimum_score = NumberInput(
            kind="decimal",
            value=0.5,
            minimum=0.0,
            maximum=1.0,
            step=0.01,
            decimals=2,
            label="Minimum detection score",
        )
        self.minimum_score_row = self._setting_row(
            self.minimum_score,
            "Includes windows whose binary target score meets this value. A score is not a "
            "certainty percentage; higher values usually return fewer candidates.",
            "Minimum detection score",
        )
        self.window_overlap = SelectInput(
            ("0%", "25%", "50%", "75%"),
            label="Window overlap",
        )
        self.window_overlap_row = self._setting_row(
            self.window_overlap,
            "Controls how often neighboring portions of a recording are examined. More overlap "
            "adds analysis windows and can increase processing time.",
            "Window overlap",
        )
        self.combine_nearby = SelectInput(
            ("Do not combine across gaps", "0.20 s", "0.50 s"),
            label="Combine nearby candidates",
        )
        self.combine_nearby_row = self._setting_row(
            self.combine_nearby,
            "Joins candidate intervals when the source-time gap between them is no greater "
            "than the selected value. Overlapping candidates are always joined.",
            "Combine nearby candidates",
        )
        self.settings_layout = QGridLayout()
        self.settings_layout.setHorizontalSpacing(16)
        self.settings_layout.setVerticalSpacing(14)
        self.settings_layout.addWidget(self.minimum_score_row, 0, 0)
        self.settings_layout.addWidget(self.window_overlap_row, 0, 1)
        self.settings_layout.addWidget(self.combine_nearby_row, 0, 2)
        for column in range(3):
            self.settings_layout.setColumnStretch(column, 1)
        card.content_layout.addLayout(self.settings_layout)
        actions = QHBoxLayout()
        actions.addStretch()
        self.start_detection_button = Button("Start detection", variant="primary")
        self.start_detection_button.setAccessibleDescription(
            "Freeze the verified setup and run CNN candidate detection."
        )
        self.start_detection_button.clicked.connect(self._start_detection)
        actions.addWidget(self.start_detection_button)
        card.content_layout.addLayout(actions)
        return card

    def _start_detection(self) -> None:
        overlaps = (0, 25, 50, 75)
        gaps = (0, 200, 500)
        settings = DetectionSettings(
            minimum_score=float(self.minimum_score.value()),
            window_overlap_percent=overlaps[self.window_overlap.currentIndex()],
            combine_gap_ms=gaps[self.combine_nearby.currentIndex()],
            batch_size=16,
        )
        try:
            self.controller.start_detection(settings)
        except (OSError, RuntimeError, ValueError) as exc:
            self.selection_error.setText(str(exc))
            self.selection_error.setVisible(True)
            return
        self._set_route("run")

    def _build_heading(self) -> QGridLayout:
        heading = QGridLayout()
        heading.setHorizontalSpacing(16)
        heading.setVerticalSpacing(10)
        self.heading_copy = QVBoxLayout()
        self.heading_copy.setSpacing(5)
        self.page_overline = Text("DETECT SETUP", role="overline")
        self.heading_copy.addWidget(self.page_overline)
        self.page_title = Text("Prepare candidate detection", role="title")
        self.heading_copy.addWidget(self.page_title)
        self.page_description = Text(
            "Choose a detection Model and recordings folder in either order.",
            role="body",
            word_wrap=True,
        )
        self.heading_copy.addWidget(self.page_description)
        heading.addLayout(self.heading_copy, 0, 0)
        heading.setColumnStretch(0, 1)
        self.back_button = Button("Back to Studio", variant="outline")
        self.back_button.setAccessibleName("Back to Studio launchpad")
        self.back_button.clicked.connect(self.return_requested)
        heading.addWidget(self.back_button, 0, 1, Qt.AlignmentFlag.AlignTop)
        self.heading_layout = heading
        return heading

    def _build_navigation(self) -> QHBoxLayout:
        navigation = QHBoxLayout()
        navigation.setSpacing(8)
        self.setup_button = Button("Setup", variant="outline", size="small")
        self.setup_button.setAccessibleName("Open Detect setup")
        self.setup_button.setCheckable(True)
        self.setup_button.setAutoExclusive(True)
        self.setup_button.clicked.connect(lambda: self._set_route("setup"))
        navigation.addWidget(self.setup_button)
        self.recordings_button = Button("Recordings", variant="outline", size="small")
        self.recordings_button.setAccessibleName("Open Detect recordings folder")
        self.recordings_button.setCheckable(True)
        self.recordings_button.setAutoExclusive(True)
        self.recordings_button.clicked.connect(lambda: self._set_route("recordings"))
        navigation.addWidget(self.recordings_button)
        self.run_button = Button("Run", variant="outline", size="small")
        self.run_button.setAccessibleName("Open Detect Run")
        self.run_button.setCheckable(True)
        self.run_button.setAutoExclusive(True)
        self.run_button.clicked.connect(lambda: self._set_route("run"))
        navigation.addWidget(self.run_button)
        navigation.addStretch()
        return navigation

    def _build_run_header(self) -> Card:
        card = Card()
        card.setAccessibleName("Current Detect Run")
        layout = QGridLayout()
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)
        self.run_header_labels = QVBoxLayout()
        self.run_header_labels.setSpacing(3)
        self.run_header_labels.addWidget(Text("DETECT RUN", role="overline"))
        self.active_run_label = Text("No active Run", role="subheading", word_wrap=True)
        self.run_header_labels.addWidget(self.active_run_label)
        layout.addLayout(self.run_header_labels, 0, 0)
        layout.setColumnStretch(0, 1)
        self.active_run_badge = Badge("Idle", intent="neutral")
        self.active_run_badge.setAccessibleName("Detect Run status: Idle")
        layout.addWidget(self.active_run_badge, 0, 1)
        self.view_run_button = Button("View Run", variant="outline", size="small")
        self.view_run_button.setAccessibleName("View current Detect Run")
        self.view_run_button.clicked.connect(lambda: self._set_route("run"))
        layout.addWidget(self.view_run_button, 0, 2)
        self.run_header_layout = layout
        card.content_layout.addLayout(layout)
        return card

    def _build_run_view(self) -> QWidget:
        view = QWidget()
        outer = QVBoxLayout(view)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        self.run_guidance = QLabel()
        self.run_guidance.setWordWrap(True)
        self.run_guidance.setAccessibleName("Detect Run guidance")
        self.run_guidance.setStyleSheet(
            "padding: 12px; border: 1px solid #CBD5E1; border-left: 4px solid #2563EB; "
            "border-radius: 7px;"
        )
        outer.addWidget(self.run_guidance)

        self.run_layout = QGridLayout()
        self.run_layout.setHorizontalSpacing(16)
        self.run_layout.setVerticalSpacing(16)
        self.run_progress_card = Card()
        progress_heading = QHBoxLayout()
        progress_labels = QVBoxLayout()
        self.run_title = Text("Run not started", role="heading", word_wrap=True)
        progress_labels.addWidget(self.run_title)
        self.run_stage = Text("Waiting", role="body", word_wrap=True)
        progress_labels.addWidget(self.run_stage)
        progress_heading.addLayout(progress_labels, 1)
        self.run_status_badge = Badge("Idle", intent="neutral")
        self.run_status_badge.setAccessibleName("Run detail status: Idle")
        progress_heading.addWidget(self.run_status_badge)
        self.run_percent = Text("0%", role="subheading")
        progress_heading.addWidget(self.run_percent)
        self.run_progress_card.content_layout.addLayout(progress_heading)
        self.run_progress_bar = ProgressBar(value=0)
        self.run_progress_bar.setAccessibleName("Detect Run progress")
        self.run_progress_card.content_layout.addWidget(self.run_progress_bar)
        self.run_stage_list = QLabel()
        self.run_stage_list.setWordWrap(True)
        self.run_stage_list.setAccessibleName("Detect Run stages")
        self.run_progress_card.content_layout.addWidget(self.run_stage_list)
        actions = QHBoxLayout()
        self.cancel_run_button = Button("Cancel Run", variant="danger")
        self.cancel_run_button.setAccessibleDescription(
            "Request cancellation, then stop the Worker within the bounded grace period."
        )
        self.cancel_run_button.clicked.connect(self.controller.cancel_active_run)
        actions.addWidget(self.cancel_run_button)
        actions.addStretch()
        self.open_run_log_button = Button("Open Run log", variant="outline")
        self.open_run_log_button.setAccessibleDescription(
            "Open the existing privacy-safe diagnostic log for this Detect Run."
        )
        self.open_run_log_button.clicked.connect(self._open_run_log)
        actions.addWidget(self.open_run_log_button)
        self.run_progress_card.content_layout.addLayout(actions)

        self.run_activity_card = Card()
        self.run_activity_card.setAccessibleName("Detect Run activity")
        self.run_activity_card.content_layout.addWidget(Text("Activity", role="heading"))
        self.run_activity = QLabel("No activity yet.")
        self.run_activity.setWordWrap(True)
        self.run_activity.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.run_activity.setAccessibleName("Detect Run activity entries")
        self.run_activity_card.content_layout.addWidget(self.run_activity)
        self.run_layout.addWidget(self.run_progress_card, 0, 0)
        self.run_layout.addWidget(self.run_activity_card, 0, 1)
        self.run_layout.setColumnStretch(0, 2)
        self.run_layout.setColumnStretch(1, 1)
        outer.addLayout(self.run_layout)
        outer.addStretch()
        return view

    def _open_run_log(self) -> None:
        record = self.controller.current_run
        if record is None:
            return
        path = self.controller.safe_run_log_path(record.run_id)
        if path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _build_model_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Detection Model selection")
        header = QHBoxLayout()
        labels = QVBoxLayout()
        labels.setSpacing(4)
        labels.addWidget(Text("Detection Model", role="heading"))
        labels.addWidget(
            Text(
                "Choose the trained CNN Model that will search your recordings.",
                role="body",
                word_wrap=True,
            )
        )
        header.addLayout(labels, 1)
        header.addWidget(
            HelpHint(
                "Detect verifies the Train manifest, checksums, binary class mapping, and "
                "runtime structure. Numerical prediction behavior is rechecked before a Run.",
                subject="Detection Model",
            ),
            0,
            Qt.AlignmentFlag.AlignTop,
        )
        self.model_status_badge = Badge("Not selected", intent="neutral")
        self.model_status_badge.setAccessibleName("Detection Model status: Not selected")
        header.addWidget(self.model_status_badge, 0, Qt.AlignmentFlag.AlignTop)
        card.content_layout.addLayout(header)

        self.model_name = Text("No Model selected", role="subheading", word_wrap=True)
        card.content_layout.addWidget(self.model_name)
        self.model_detail = QLabel("Choose a CNN Model published by Train.")
        self.model_detail.setWordWrap(True)
        self.model_detail.setAccessibleName("Detection Model compatibility detail")
        card.content_layout.addWidget(self.model_detail)
        self.selected_model_path = QLabel("Choose a Train Model folder.")
        self.selected_model_path.setWordWrap(True)
        self.selected_model_path.setMinimumWidth(0)
        self.selected_model_path.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self.selected_model_path.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.selected_model_path.setAccessibleName("Selected Model folder")
        card.content_layout.addWidget(self.selected_model_path)

        self.model_picker = FolderPicker(label="Train Model folder")
        self.model_picker.setAccessibleDescription(
            "Choose one Model folder published inside a local Train Collection."
        )
        card.content_layout.addWidget(self.model_picker)
        actions = QHBoxLayout()
        actions.addStretch()
        self.clear_model_button = Button("Clear Model", variant="outline", size="small")
        self.clear_model_button.clicked.connect(self.controller.clear_model_selection)
        actions.addWidget(self.clear_model_button)
        card.content_layout.addLayout(actions)
        return card

    def _build_collection_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Detect Collection source")
        header = QHBoxLayout()
        labels = QVBoxLayout()
        labels.setSpacing(4)
        self.collection_title = Text("Create a Detect Collection", role="heading")
        labels.addWidget(self.collection_title)
        self.collection_description = Text(
            "Choose a folder. Detect stores its metadata separately and leaves "
            "recordings unchanged.",
            role="body",
            word_wrap=True,
        )
        labels.addWidget(self.collection_description)
        header.addLayout(labels, 1)
        hint = HelpHint(
            "A Detect Collection keeps a stable identity if its recordings folder moves. "
            "A different recordings folder creates a different Collection.",
            subject="Detect Collection",
        )
        header.addWidget(hint, 0, Qt.AlignmentFlag.AlignTop)
        self.status_badge = Badge("Not selected", intent="neutral")
        self.status_badge.setAccessibleName("Recordings folder status: Not selected")
        header.addWidget(self.status_badge, 0, Qt.AlignmentFlag.AlignTop)
        card.content_layout.addLayout(header)

        self.root_caption = Text("No recordings folder selected", role="overline")
        card.content_layout.addWidget(self.root_caption)
        self.root_path = QLabel("Choose a folder to create a Detect Collection.")
        self.root_path.setWordWrap(True)
        self.root_path.setMinimumWidth(0)
        self.root_path.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self.root_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.root_path.setAccessibleName("Current recordings folder")
        card.content_layout.addWidget(self.root_path)

        self.folder_picker = FolderPicker(label="Recordings folder")
        self.folder_picker.setAccessibleDescription(
            "Choose a new recordings folder or the relocated folder for this Collection."
        )
        card.content_layout.addWidget(self.folder_picker)
        return card

    def _build_recordings_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Current Detect Collection recordings folder")
        header = QHBoxLayout()
        labels = QVBoxLayout()
        labels.setSpacing(4)
        self.recordings_title = Text("Recordings folder", role="heading")
        labels.addWidget(self.recordings_title)
        self.recordings_description = Text("", role="body", word_wrap=True)
        labels.addWidget(self.recordings_description)
        header.addLayout(labels, 1)
        self.recordings_status_badge = Badge("Unavailable", intent="neutral")
        header.addWidget(self.recordings_status_badge, 0, Qt.AlignmentFlag.AlignTop)
        card.content_layout.addLayout(header)
        card.content_layout.addWidget(Text("LINKED LOCATION", role="overline"))
        self.recordings_path = QLabel()
        self.recordings_path.setWordWrap(True)
        self.recordings_path.setMinimumWidth(0)
        self.recordings_path.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self.recordings_path.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.recordings_path.setAccessibleName("Linked recordings folder")
        card.content_layout.addWidget(self.recordings_path)
        self.relink_picker = FolderPicker(label="Relink recordings folder")
        self.relink_picker.setAccessibleDescription(
            "Choose the relocated folder for this Detect Collection."
        )
        card.content_layout.addWidget(self.relink_picker)
        return card

    def _build_inventory_content(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        heading = QHBoxLayout()
        labels = QVBoxLayout()
        labels.setSpacing(4)
        labels.addWidget(Text("SOURCE INVENTORY", role="overline"))
        labels.addWidget(Text("Approve recording inclusion", role="heading"))
        labels.addWidget(
            Text(
                "Review which WAV files belong to this Detect Collection.",
                role="body",
                word_wrap=True,
            )
        )
        heading.addLayout(labels, 1)
        self.rescan_button = Button("Rescan", variant="primary")
        self.rescan_button.setAccessibleDescription(
            "Read the source folder again and publish only a complete inventory."
        )
        self.rescan_button.clicked.connect(self.controller.rescan)
        heading.addWidget(self.rescan_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(heading)

        self.inventory_alert = QLabel()
        self.inventory_alert.setWordWrap(True)
        self.inventory_alert.setAccessibleName("Recording inventory status")
        self.inventory_alert.setStyleSheet(
            "padding: 12px; border: 1px solid #CBD5E1; border-left: 4px solid #D97706; "
            "border-radius: 7px;"
        )
        layout.addWidget(self.inventory_alert)

        self.scan_card = Card()
        scan_heading = QHBoxLayout()
        self.scan_title = Text("Scanning recordings", role="subheading")
        self.scan_stage = Text("Listing WAV files", role="body")
        scan_labels = QVBoxLayout()
        scan_labels.addWidget(self.scan_title)
        scan_labels.addWidget(self.scan_stage)
        scan_heading.addLayout(scan_labels, 1)
        self.scan_percent = Text("0%", role="body")
        scan_heading.addWidget(self.scan_percent)
        self.scan_card.content_layout.addLayout(scan_heading)
        self.scan_progress_bar = ProgressBar(value=0)
        self.scan_progress_bar.setAccessibleName("Recording scan progress")
        self.scan_card.content_layout.addWidget(self.scan_progress_bar)
        scan_footer = QHBoxLayout()
        self.scan_count = Text("0 / 0 WAV files", role="caption")
        scan_footer.addWidget(self.scan_count)
        scan_footer.addStretch()
        self.cancel_scan_button = Button("Cancel scan", variant="outline", size="small")
        self.cancel_scan_button.clicked.connect(self.controller.cancel_scan)
        scan_footer.addWidget(self.cancel_scan_button)
        self.scan_card.content_layout.addLayout(scan_footer)
        layout.addWidget(self.scan_card)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(12)
        metrics.setVerticalSpacing(12)
        self.metric_values: dict[str, Text] = {}
        for column, (label, suffix) in enumerate(
            (
                ("Included", "source WAVs"),
                ("Undecided", "skipped WAVs"),
                ("Excluded", "skipped WAVs"),
                ("Invalid", "needs review"),
            )
        ):
            card = Card()
            card.content_layout.addWidget(Text(label, role="caption"))
            value = Text("0", role="heading")
            self.metric_values[label] = value
            card.content_layout.addWidget(value)
            card.content_layout.addWidget(Text(suffix, role="caption"))
            metrics.addWidget(card, 0, column)
        layout.addLayout(metrics)

        self.inventory_layout = QGridLayout()
        self.inventory_layout.setHorizontalSpacing(16)
        self.inventory_layout.setVerticalSpacing(16)
        self.inventory_table_card = Card()
        table_heading = QHBoxLayout()
        table_labels = QVBoxLayout()
        self.inventory_root_title = Text("Recording hierarchy", role="subheading")
        table_labels.addWidget(self.inventory_root_title)
        self.inventory_root_path = Text("", role="caption", word_wrap=True)
        table_labels.addWidget(self.inventory_root_path)
        table_heading.addLayout(table_labels, 1)
        table_heading.addStretch()
        table_heading.addWidget(
            HelpHint(
                "Included recordings are available to analysis. Excluded and undecided "
                "recordings are skipped. Inclusion never modifies source files.",
                subject="Recording inclusion",
            )
        )
        self.inventory_table_card.content_layout.addLayout(table_heading)
        decision_actions = QHBoxLayout()
        self.include_selection_button = Button(
            "Include selection", variant="outline", size="small"
        )
        self.include_selection_button.clicked.connect(
            lambda: self._set_selected_decision(InclusionDecision.INCLUDED)
        )
        decision_actions.addWidget(self.include_selection_button)
        self.exclude_selection_button = Button(
            "Exclude selection", variant="outline", size="small"
        )
        self.exclude_selection_button.clicked.connect(
            lambda: self._set_selected_decision(InclusionDecision.EXCLUDED)
        )
        decision_actions.addWidget(self.exclude_selection_button)
        self.reset_selection_button = Button("Reset decision", variant="outline", size="small")
        self.reset_selection_button.clicked.connect(self._clear_selected_decision)
        decision_actions.addWidget(self.reset_selection_button)
        decision_actions.addStretch()
        self.inventory_table_card.content_layout.addLayout(decision_actions)
        self.inventory_model = InventoryTableModel(self)
        self.inventory_table = DataTable(model=self.inventory_model)
        self.inventory_table.setAccessibleName("Recording folder hierarchy")
        self.inventory_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for column in range(1, 4):
            self.inventory_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        self.inventory_table.setMinimumHeight(300)
        self.inventory_table.selectionModel().currentChanged.connect(
            lambda current, _previous: self._select_inventory_row(current.row())
        )
        self.inventory_table_card.content_layout.addWidget(self.inventory_table)

        self.inventory_detail_card = Card()
        self.detail_kind = Text("SELECTED ITEM", role="overline")
        self.inventory_detail_card.content_layout.addWidget(self.detail_kind)
        self.detail_title = Text("No recording selected", role="heading")
        self.inventory_detail_card.content_layout.addWidget(self.detail_title)
        self.detail_decision = QLabel("—")
        self.detail_status = QLabel("—")
        self.detail_source = QLabel("—")
        self.detail_audio = QLabel("—")
        for label, value in (
            ("Decision", self.detail_decision),
            ("Status", self.detail_status),
            ("Decision source", self.detail_source),
            ("Recorded audio", self.detail_audio),
        ):
            row = QHBoxLayout()
            row.addWidget(Text(label, role="caption"))
            row.addStretch()
            value.setWordWrap(True)
            value.setAccessibleName(f"Selected recording {label.lower()}")
            row.addWidget(value)
            self.inventory_detail_card.content_layout.addLayout(row)
        self.inventory_detail_card.content_layout.addWidget(
            Text(
                "Inclusion changes analysis eligibility only; source files remain unchanged.",
                role="caption",
                word_wrap=True,
            )
        )
        self.inventory_layout.addWidget(self.inventory_table_card, 0, 0)
        self.inventory_layout.addWidget(self.inventory_detail_card, 0, 1)
        self.inventory_layout.setColumnStretch(0, 3)
        self.inventory_layout.setColumnStretch(1, 1)
        layout.addLayout(self.inventory_layout)
        return content

    def _build_relink_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Confirm recordings folder relink")
        card.content_layout.addWidget(Text("Relink recordings folder", role="heading"))
        card.content_layout.addWidget(
            Text(
                "The folder identity matches this Collection. Confirm the new location before "
                "the binding changes.",
                role="body",
                word_wrap=True,
            )
        )
        paths = QGridLayout()
        paths.addWidget(Text("PREVIOUS LOCATION", role="overline"), 0, 0)
        paths.addWidget(Text("NEW LOCATION", role="overline"), 0, 1)
        self.previous_path = QLabel()
        self.previous_path.setWordWrap(True)
        self.new_path = QLabel()
        self.new_path.setWordWrap(True)
        paths.addWidget(self.previous_path, 1, 0)
        paths.addWidget(self.new_path, 1, 1)
        card.content_layout.addLayout(paths)
        self.relink_confirm = CheckBox(
            "I understand that recordings must be reviewed again before detection."
        )
        card.content_layout.addWidget(self.relink_confirm)
        actions = QHBoxLayout()
        actions.addStretch()
        self.cancel_relink_button = Button("Cancel", variant="outline")
        self.cancel_relink_button.clicked.connect(self.controller.cancel_relink)
        actions.addWidget(self.cancel_relink_button)
        self.confirm_relink_button = Button("Relink folder", variant="primary")
        self.confirm_relink_button.setEnabled(False)
        self.confirm_relink_button.clicked.connect(self.controller.confirm_relink)
        actions.addWidget(self.confirm_relink_button)
        card.content_layout.addLayout(actions)
        self.relink_confirm.toggled.connect(self.confirm_relink_button.setEnabled)
        return card

    def _build_different_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Different recordings folder")
        card.content_layout.addWidget(Text("This is a different folder", role="heading"))
        card.content_layout.addWidget(
            Text(
                "Its verified folder identity does not match the current Collection. "
                "Create a new Collection to prevent an unrelated folder from taking "
                "over its history.",
                role="body",
                word_wrap=True,
            )
        )
        actions = QHBoxLayout()
        actions.addStretch()
        self.cancel_different_button = Button("Keep current Collection", variant="outline")
        self.cancel_different_button.clicked.connect(self.controller.cancel_relink)
        actions.addWidget(self.cancel_different_button)
        self.new_collection_button = Button("Create new Collection", variant="primary")
        self.new_collection_button.clicked.connect(self.controller.create_new_collection)
        actions.addWidget(self.new_collection_button)
        card.content_layout.addLayout(actions)
        return card

    def _render_scan(self) -> None:
        progress = self.controller.scan_progress
        total = progress.total
        percent = round(progress.completed * 100 / total) if total else 0
        self.scan_stage.setText(progress.stage)
        self.scan_percent.setText(f"{percent}%")
        self.scan_progress_bar.setValue(percent)
        self.scan_count.setText(f"{progress.completed:,} / {total:,} WAV files")

    def _render_inventory(self) -> None:
        snapshot = self.controller.snapshot
        state = self.controller.inventory_state
        self.scan_card.setVisible(state is InventoryState.SCANNING)
        self.cancel_scan_button.setEnabled(self.controller.is_scanning)
        self.rescan_button.setEnabled(
            self.controller.active_collection is not None
            and self.controller.root_decision is RootBindingDecision.VALID
            and not self.controller.is_scanning
        )
        self._render_scan()

        cancelled_message = (
            "Scan cancelled. No inventory was published. Rescan before detection."
            if snapshot is None
            else "Scan cancelled. The last complete inventory was kept and no partial result "
            "was published. Rescan before using it for detection."
        )
        message = {
            InventoryState.EMPTY: (
                "No complete inventory yet. Scan this folder to discover WAV recordings."
            ),
            InventoryState.SCANNING: (
                "Scanning the source folder. The previous complete inventory remains unchanged."
            ),
            InventoryState.READY: "Inventory ready. Review undecided and excluded recordings.",
            InventoryState.CANCELLED: cancelled_message,
            InventoryState.INVALID: (
                "The inventory needs attention. Repair invalid included recordings or change "
                "their inclusion, then rescan."
            ),
            InventoryState.STALE: (
                "Recordings changed after the last complete scan. Rescan before detection."
            ),
            InventoryState.MISSING: (
                "The recordings folder is unavailable. Relink it before rescanning."
            ),
        }[state]
        if (
            self.controller.inventory_error
            and state is not InventoryState.CANCELLED
        ):
            message = f"{message} {self.controller.inventory_error}"
        self.inventory_alert.setText(message)

        counts = snapshot.counts if snapshot is not None else None
        for label, value in self.metric_values.items():
            count = 0 if counts is None else getattr(counts, label.casefold())
            value.setText(f"{count:,}")
        self.inventory_root_title.setText(
            "Recording hierarchy"
            if self.controller.active_collection is None
            else f"{self.controller.active_collection.ref.display_label}/"
        )
        self.inventory_root_path.setText(
            ""
            if self.controller.active_collection is None
            else str(self.controller.active_collection.source_root)
        )

        inventory_id = None if snapshot is None else snapshot.inventory_id
        if inventory_id != self._rendered_inventory_id:
            previous_key = self.selected_key
            self.inventory_model.set_snapshot(snapshot)
            self._rendered_inventory_id = inventory_id
            if snapshot is None or self.inventory_model.rowCount() == 0:
                self.selected_key = None
                self._render_inventory_detail(None)
            else:
                try:
                    row = (
                        self.inventory_model.row_for_key(previous_key)
                        if previous_key is not None
                        else 0
                    )
                except KeyError:
                    row = 0
                self.inventory_table.setCurrentIndex(self.inventory_model.index(row, 0))
                self._select_inventory_row(row)
        elif self.selected_key is not None:
            try:
                row = self.inventory_model.row_for_key(self.selected_key)
            except KeyError:
                self.selected_key = None
                self._render_inventory_detail(None)
            else:
                self._render_inventory_detail(self.inventory_model.entry_at(row))
        has_snapshot = snapshot is not None and self.inventory_model.rowCount() > 0
        self.inventory_table.setEnabled(has_snapshot and not self.controller.is_scanning)

    def _render_model(self) -> None:
        state = self.controller.model_state
        status = {
            ModelIntakeState.EMPTY: "Not selected",
            ModelIntakeState.LOADING: "Checking",
            ModelIntakeState.COMPATIBLE: "Compatible",
            ModelIntakeState.INCOMPATIBLE: "Incompatible",
            ModelIntakeState.MISSING: "Missing files",
        }[state]
        reference = self.controller.model_reference
        selected = self.controller.selected_model_root
        self.model_status_badge.setText(status)
        self.model_status_badge.setAccessibleName(f"Detection Model status: {status}")
        if reference is not None:
            self.model_name.setText(reference.snapshot.label)
        elif selected is not None:
            self.model_name.setText(selected.name or "Selected Model")
        else:
            self.model_name.setText("No Model selected")
        self.model_detail.setText(self.controller.model_reason)
        self.selected_model_path.setText(
            "Choose a Train Model folder." if selected is None else str(selected)
        )
        self.model_picker.setEnabled(state is not ModelIntakeState.LOADING)
        self.clear_model_button.setEnabled(
            selected is not None and state is not ModelIntakeState.LOADING
        )
        if state is not ModelIntakeState.LOADING:
            self.model_picker.setFolderPath("" if selected is None else str(selected))

    def _render_readiness(self) -> None:
        settings_locked = self.controller.is_run_active
        for field in (
            self.minimum_score,
            self.window_overlap,
            self.combine_nearby,
        ):
            field.setEnabled(not settings_locked)
        self.start_detection_button.setEnabled(self.controller.inputs_ready)
        if self.controller.inputs_ready:
            self.readiness_title.setText("Setup inputs verified")
            self.readiness_detail.setText(
                f"Compatible CNN Model · {self.controller.snapshot.counts.included:,} included "
                "WAV recordings."
            )
            return
        if self.controller.model_state is ModelIntakeState.LOADING:
            title = "Checking Detection Model"
            detail = self.controller.model_reason
        elif self.controller.model_state in {
            ModelIntakeState.INCOMPATIBLE,
            ModelIntakeState.MISSING,
        }:
            title = "Detection Model needs attention"
            detail = self.controller.model_reason
        elif self.controller.model_state is ModelIntakeState.EMPTY:
            title = "Choose a compatible CNN Model"
            detail = "Select a Model published by Train."
        elif self.controller.active_collection is None:
            title = "Choose a recordings folder"
            detail = "Create a Detect Collection and review its WAV inventory."
        elif self.controller.root_decision is not RootBindingDecision.VALID:
            title = "Recordings folder needs attention"
            detail = "Relink or restore the recordings folder before using this setup."
        elif self.controller.inventory_state is not InventoryState.READY:
            title = "Recording review is not ready"
            detail = "Complete a current inventory with at least one included WAV recording."
        else:
            title = "No recordings included"
            detail = "Include at least one valid WAV recording."
        self.readiness_title.setText(title)
        self.readiness_detail.setText(detail)

    def _select_inventory_row(self, row: int) -> None:
        entry = self.inventory_model.entry_at(row)
        self.selected_key = None if entry is None else entry.key
        self._render_inventory_detail(entry)

    def _rows_for_entry(self, entry: _InventoryEntry) -> tuple[InventoryRecording, ...]:
        snapshot = self.controller.snapshot
        if snapshot is None:
            return ()
        if entry.is_folder:
            return tuple(
                row
                for row in snapshot.recordings
                if row.recording_key.startswith(entry.key)
            )
        return () if entry.recording is None else (entry.recording,)

    def _render_inventory_detail(self, entry: _InventoryEntry | None) -> None:
        if entry is None:
            self.detail_kind.setText("SELECTED ITEM")
            self.detail_title.setText("No recording selected")
            for value in (
                self.detail_decision,
                self.detail_status,
                self.detail_source,
                self.detail_audio,
            ):
                value.setText("—")
            enabled = False
        else:
            rows = self._rows_for_entry(entry)
            self.detail_kind.setText("SELECTED FOLDER" if entry.is_folder else "SELECTED FILE")
            self.detail_title.setText(entry.key)
            decisions = {row.decision.value.capitalize() for row in rows}
            statuses = {row.status.value.capitalize() for row in rows}
            sources = {
                row.decision_path or "No default rule"
                for row in rows
            }
            self.detail_decision.setText(
                next(iter(decisions)) if len(decisions) == 1 else "Mixed"
            )
            self.detail_status.setText(
                next(iter(statuses)) if len(statuses) == 1 else "Mixed"
            )
            self.detail_source.setText(next(iter(sources)) if len(sources) == 1 else "Mixed")
            seconds = sum(
                row.wav.frame_count / row.wav.sample_rate_hz
                for row in rows
                if row.wav is not None
            )
            self.detail_audio.setText(
                f"{seconds / 3_600:.1f} h"
                if seconds >= 3_600
                else (f"{seconds / 60:.1f} min" if seconds >= 60 else f"{seconds:.1f} s")
            )
            enabled = (
                bool(rows)
                and not self.controller.is_scanning
                and self.controller.inventory_state
                in {InventoryState.READY, InventoryState.INVALID}
            )
        locked = bool(entry and rows) and all(
            row.decision_origin in {DecisionOrigin.POLICY, DecisionOrigin.CONFLICT}
            for row in rows
        )
        self.include_selection_button.setEnabled(enabled and not locked)
        self.exclude_selection_button.setEnabled(enabled and not locked)
        target = "" if entry is None else entry.key.rstrip("/")
        has_rule = bool(entry and self.controller.snapshot) and any(
            rule.path == target and rule.is_folder == entry.is_folder
            for rule in self.controller.snapshot.decision_rules
        )
        self.reset_selection_button.setEnabled(enabled and has_rule)

    def _set_selected_decision(self, decision: InclusionDecision) -> None:
        if self.selected_key is None:
            return
        entry = self.inventory_model.entry_at(
            self.inventory_table.currentIndex().row()
        )
        if entry is None:
            return
        self.controller.set_inventory_decision(
            entry.key.rstrip("/"),
            is_folder=entry.is_folder,
            decision=decision,
        )

    def _clear_selected_decision(self) -> None:
        if self.selected_key is None:
            return
        entry = self.inventory_model.entry_at(
            self.inventory_table.currentIndex().row()
        )
        if entry is None:
            return
        self.controller.clear_inventory_decision(
            entry.key.rstrip("/"), is_folder=entry.is_folder
        )

    def _render_run_header(self) -> None:
        record = self.controller.current_run
        if record is None:
            self.active_run_label.setText("No active Run")
            self.active_run_badge.setText("Idle")
            self.active_run_badge.setAccessibleName("Detect Run status: Idle")
            self.view_run_button.setVisible(False)
            return
        status = record.status.value.capitalize()
        self.active_run_label.setText(record.title)
        self.active_run_badge.setText(status)
        self.active_run_badge.setAccessibleName(f"Detect Run status: {status}")
        self.view_run_button.setVisible(self.current_route != "run")

    def _render_run(self) -> None:
        record = self.controller.current_run
        if record is None:
            self.run_title.setText("Run not started")
            self.run_stage.setText("Waiting for verified setup")
            self.run_status_badge.setText("Idle")
            self.run_status_badge.setAccessibleName("Run detail status: Idle")
            self.run_percent.setText("0%")
            self.run_progress_bar.setValue(0)
            self.run_stage_list.setText(
                "○ Validate frozen inputs\n○ Run the supervised Worker\n○ Verify publication"
            )
            self.run_activity.setText("No activity yet.")
            self.run_guidance.setText(
                "No Run has started. Prepare a compatible Model and current recording inventory."
            )
            self.cancel_run_button.setEnabled(False)
            self.open_run_log_button.setEnabled(False)
            return

        status = record.status.value.capitalize()
        result = self.controller.current_result
        guidance = {
            DetectRunStatus.PREPARING: "Preparing frozen inputs and starting the Worker.",
            DetectRunStatus.RUNNING: "The supervised Worker is running.",
            DetectRunStatus.CANCELLING: (
                "Cancellation requested. Detect is waiting for the Worker to stop safely."
            ),
            DetectRunStatus.CANCELLED: (
                "This Run was cancelled without publication. Review setup and start a new Run."
            ),
            DetectRunStatus.INTERRUPTED: (
                "The Worker stopped unexpectedly. Review setup and start a new Run."
            ),
            DetectRunStatus.FAILED: (
                record.error_message
                or "The Run failed without publication. Review setup and start a new Run."
            ),
            DetectRunStatus.COMPLETED: (
                (
                    f"The metadata-only Result was verified and published: "
                    f"{result.candidate_count:,} candidate intervals across "
                    f"{result.successful_files:,} recordings"
                    + (
                        f"; {result.failed_files:,} recording files failed separately."
                        if result.failed_files
                        else "."
                    )
                )
                if result is not None
                else "The immutable artifact and its publication receipt were verified."
            ),
        }[record.status]
        self.run_title.setText(record.title)
        self.run_stage.setText(record.current_stage)
        self.run_status_badge.setText(status)
        self.run_status_badge.setAccessibleName(f"Run detail status: {status}")
        self.run_percent.setText(f"{record.progress}%")
        self.run_progress_bar.setValue(record.progress)
        stage_rows = []
        for index, stage in enumerate(record.stages):
            marker = (
                "✓"
                if index < record.stage_index
                else ("●" if index == record.stage_index else "○")
            )
            if record.status is DetectRunStatus.COMPLETED:
                marker = "✓"
            stage_rows.append(f"{marker} {stage}")
        self.run_stage_list.setText("\n".join(stage_rows))
        self.run_activity.setText("\n".join(record.activity[-8:]) or "No activity yet.")
        self.run_guidance.setText(guidance)
        self.cancel_run_button.setEnabled(
            record.status in {DetectRunStatus.PREPARING, DetectRunStatus.RUNNING}
        )
        self.open_run_log_button.setEnabled(
            self.controller.safe_run_log_path(record.run_id) is not None
        )

    def _render(self) -> None:
        self._render_run_header()
        self._render_run()
        self._render_model()
        collection = self.controller.active_collection
        proposal = self.controller.proposal
        self.relink_card.setVisible(
            proposal is not None
            and proposal.decision is RootBindingDecision.AWAITING_CONFIRMATION
        )
        self.different_card.setVisible(
            proposal is not None and proposal.decision is RootBindingDecision.CHANGED
        )
        self.selection_error.setText(
            self.controller.selection_error or self.controller.metadata_error
        )
        self.selection_error.setVisible(bool(self.selection_error.text()))

        if collection is None:
            self.recordings_button.setEnabled(False)
            self._set_route("setup")
            self.collection_title.setText("Create a Detect Collection")
            self.collection_description.setText(
                "Choose a folder. Detect stores its metadata separately and leaves "
                "recordings unchanged."
            )
            self.status_badge.setText("Not selected")
            self.status_badge.setAccessibleName("Recordings folder status: Not selected")
            self.root_caption.setText("NO RECORDINGS FOLDER SELECTED")
            self.root_path.setText("Choose a folder to create a Detect Collection.")
            self.folder_picker.setFolderPath("")
            self._render_inventory()
            self._render_readiness()
            return

        self.recordings_button.setEnabled(True)
        decision = self.controller.root_decision
        status, description = {
            RootBindingDecision.VALID: (
                "Available",
                "The recordings folder is available. Detect keeps the source tree read-only.",
            ),
            RootBindingDecision.MISSING: (
                "Folder missing",
                "Choose the folder's new location to relink this Collection.",
            ),
            RootBindingDecision.INACCESSIBLE: (
                "Access unavailable",
                "The linked folder exists but cannot be read. Its contents are not "
                "treated as empty.",
            ),
            RootBindingDecision.CHANGED: (
                "Folder changed",
                "The location now refers to a different folder. Choose the relocated "
                "folder or create a new Collection.",
            ),
            None: ("Unavailable", "The Detect Collection binding could not be read."),
        }[decision]
        self.collection_title.setText(collection.ref.display_label)
        self.collection_description.setText(description)
        self.status_badge.setText(status)
        self.status_badge.setAccessibleName(f"Recordings folder status: {status}")
        self.root_caption.setText("CURRENT RECORDINGS FOLDER")
        self.root_path.setText(str(collection.source_root))
        self.recordings_title.setText(collection.ref.display_label)
        self.recordings_description.setText(description)
        self.recordings_status_badge.setText(status)
        self.recordings_status_badge.setAccessibleName(
            f"Recordings folder status: {status}"
        )
        self.recordings_card.setVisible(
            decision is not RootBindingDecision.VALID or proposal is not None
        )
        self.recordings_path.setText(str(collection.source_root))
        if proposal is None:
            self.folder_picker.setFolderPath(str(collection.source_root))
            self.relink_picker.setFolderPath(str(collection.source_root))
        elif proposal.decision is RootBindingDecision.AWAITING_CONFIRMATION:
            self.previous_path.setText(str(proposal.previous_root))
            self.new_path.setText(str(proposal.candidate_root))
            self.relink_confirm.setChecked(False)
            self.confirm_relink_button.setEnabled(False)
        if proposal is not None or decision is not RootBindingDecision.VALID:
            self._set_route("recordings")
        elif self.controller.inventory_state is InventoryState.SCANNING:
            self._set_route("recordings")
        self._render_inventory()
        self._render_readiness()

    def _set_route(self, route: str) -> None:
        if route not in {"setup", "recordings", "run"}:
            raise ValueError(f"Unknown Detect route: {route}")
        if route == "recordings" and not self.recordings_button.isEnabled():
            route = "setup"
        route_changed = getattr(self, "current_route", None) != route
        self.current_route = route
        self.setup_button.setChecked(route == "setup")
        self.recordings_button.setChecked(route == "recordings")
        self.run_button.setChecked(route == "run")
        self.route_stack.setCurrentWidget(
            {
                "setup": self.setup_view,
                "recordings": self.recordings_view,
                "run": self.run_view,
            }[route]
        )
        if route == "setup":
            self.page_overline.setText("DETECT SETUP")
            self.page_title.setText("Prepare candidate detection")
            self.page_description.setText(
                "Choose a detection Model and recordings folder in either order."
            )
        elif route == "recordings":
            self.page_overline.setText("SOURCE INVENTORY")
            self.page_title.setText("Recordings")
            self.page_description.setText(
                "Approve the WAVs that belong to this Detect Collection."
            )
        else:
            self.page_overline.setText("RUN · CANDIDATE DETECTION")
            self.page_title.setText(
                "Detect Run"
                if self.controller.current_run is None
                else self.controller.current_run.title
            )
            self.page_description.setText(
                "Follow Worker progress, cancellation, recovery, and verified publication."
            )
        self.setup_button.setAccessibleDescription(
            "Current Detect page" if route == "setup" else "Open Detect setup"
        )
        self.recordings_button.setAccessibleDescription(
            "Current Detect page" if route == "recordings" else "Open recordings folder"
        )
        self.run_button.setAccessibleDescription(
            "Current Detect page" if route == "run" else "Open Detect Run details"
        )
        self._render_run_header()
        if route_changed:
            QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(0))

    def focus_initial(self) -> None:
        if self.relink_card.isVisible():
            self.relink_confirm.setFocus()
            return
        if self.current_route == "run":
            target = (
                self.cancel_run_button
                if self.cancel_run_button.isEnabled()
                else self.run_button
            )
            target.setFocus()
            return
        picker = self.model_picker if self.current_route == "setup" else self.relink_picker
        buttons = picker.findChildren(QPushButton)
        if buttons:
            buttons[0].setFocus()
        else:
            self.back_button.setFocus()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        compact = event.size().width() < 760
        if compact != self._compact:
            self._compact = compact
            margin = 22 if compact else 48
            self.outer.setContentsMargins(margin, 26 if compact else 34, margin, 36)
            self.heading_layout.removeItem(self.heading_copy)
            self.heading_layout.removeWidget(self.back_button)
            self.run_header_layout.removeItem(self.run_header_labels)
            self.run_header_layout.removeWidget(self.active_run_badge)
            self.run_header_layout.removeWidget(self.view_run_button)
            if compact:
                self.heading_layout.addLayout(self.heading_copy, 0, 0)
                self.heading_layout.addWidget(
                    self.back_button, 1, 0, Qt.AlignmentFlag.AlignLeft
                )
                self.run_header_layout.addLayout(self.run_header_labels, 0, 0, 1, 2)
                self.run_header_layout.addWidget(self.active_run_badge, 1, 0)
                self.run_header_layout.addWidget(self.view_run_button, 1, 1)
            else:
                self.heading_layout.addLayout(self.heading_copy, 0, 0)
                self.heading_layout.addWidget(
                    self.back_button, 0, 1, Qt.AlignmentFlag.AlignTop
                )
                self.run_header_layout.addLayout(self.run_header_labels, 0, 0)
                self.run_header_layout.addWidget(self.active_run_badge, 0, 1)
                self.run_header_layout.addWidget(self.view_run_button, 0, 2)
            self.setup_layout.removeWidget(self.model_card)
            self.setup_layout.removeWidget(self.collection_card)
            for row in (
                self.minimum_score_row,
                self.window_overlap_row,
                self.combine_nearby_row,
            ):
                self.settings_layout.removeWidget(row)
            if compact:
                self.setup_layout.addWidget(self.model_card, 0, 0)
                self.setup_layout.addWidget(self.collection_card, 1, 0)
                self.setup_layout.setColumnStretch(0, 1)
                self.setup_layout.setColumnStretch(1, 0)
                self.settings_layout.addWidget(self.minimum_score_row, 0, 0)
                self.settings_layout.addWidget(self.window_overlap_row, 1, 0)
                self.settings_layout.addWidget(self.combine_nearby_row, 2, 0)
                self.settings_layout.setColumnStretch(0, 1)
                self.settings_layout.setColumnStretch(1, 0)
                self.settings_layout.setColumnStretch(2, 0)
            else:
                self.setup_layout.addWidget(self.model_card, 0, 0)
                self.setup_layout.addWidget(self.collection_card, 0, 1)
                self.setup_layout.setColumnStretch(0, 1)
                self.setup_layout.setColumnStretch(1, 1)
                self.settings_layout.addWidget(self.minimum_score_row, 0, 0)
                self.settings_layout.addWidget(self.window_overlap_row, 0, 1)
                self.settings_layout.addWidget(self.combine_nearby_row, 0, 2)
                for column in range(3):
                    self.settings_layout.setColumnStretch(column, 1)
            self.inventory_layout.removeWidget(self.inventory_table_card)
            self.inventory_layout.removeWidget(self.inventory_detail_card)
            if compact:
                self.inventory_layout.addWidget(self.inventory_table_card, 0, 0)
                self.inventory_layout.addWidget(self.inventory_detail_card, 1, 0)
            else:
                self.inventory_layout.addWidget(self.inventory_table_card, 0, 0)
                self.inventory_layout.addWidget(self.inventory_detail_card, 0, 1)
            self.run_layout.removeWidget(self.run_progress_card)
            self.run_layout.removeWidget(self.run_activity_card)
            if compact:
                self.run_layout.addWidget(self.run_progress_card, 0, 0)
                self.run_layout.addWidget(self.run_activity_card, 1, 0)
            else:
                self.run_layout.addWidget(self.run_progress_card, 0, 0)
                self.run_layout.addWidget(self.run_activity_card, 0, 1)
            for layout in (
                self.setup_layout,
                self.settings_layout,
                self.setup_view.layout(),
                self.inventory_layout,
                self.recordings_view.layout(),
                self.run_layout,
                self.run_view.layout(),
            ):
                layout.invalidate()
                layout.activate()
            self.route_stack.layout().invalidate()
            self.route_stack.layout().activate()
            for widget in (
                self.setup_view,
                self.recordings_view,
                self.run_view,
                self.route_stack,
                self.content,
            ):
                widget.updateGeometry()

    @property
    def is_compact(self) -> bool:
        return self._compact
