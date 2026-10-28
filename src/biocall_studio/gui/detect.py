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
    ProgressBar,
    Text,
)
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from biocall_studio.detect.controller import (
    DetectWorkspaceController,
    InventoryState,
)
from biocall_studio.detect.domain import RootBindingDecision
from biocall_studio.detect.inventory import (
    DecisionOrigin,
    InclusionDecision,
    InventoryRecording,
    InventorySnapshot,
    RecordingStatus,
)


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

        self.content = QWidget()
        self.outer = QVBoxLayout(self.content)
        self.outer.setContentsMargins(48, 34, 48, 48)
        self.outer.setSpacing(22)
        self.outer.addLayout(self._build_heading())
        self.outer.addLayout(self._build_navigation())
        self.selection_error = QLabel()
        self.selection_error.setWordWrap(True)
        self.selection_error.setAccessibleName("Recordings folder error")
        self.selection_error.setStyleSheet("color: #B91C1C; font-weight: 600;")
        self.outer.addWidget(self.selection_error)

        self.route_stack = QStackedWidget()
        self.setup_view = QWidget()
        setup_layout = QVBoxLayout(self.setup_view)
        setup_layout.setContentsMargins(0, 0, 0, 0)
        self.collection_card = self._build_collection_card()
        setup_layout.addWidget(self.collection_card)
        setup_layout.addStretch()

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

        self.route_stack.addWidget(self.setup_view)
        self.route_stack.addWidget(self.recordings_view)
        self.outer.addWidget(self.route_stack)
        self.outer.addStretch()
        self.setWidget(self.content)

        self.controller.state_changed.connect(self._render)
        self.controller.scan_progress_changed.connect(lambda _progress: self._render_scan())
        self.folder_picker.folderChanged.connect(self.controller.choose_source_root)
        self.relink_picker.folderChanged.connect(self.controller.choose_source_root)
        self.current_route = "setup"
        self._set_route("setup")
        self._render()

    def _build_heading(self) -> QHBoxLayout:
        heading = QHBoxLayout()
        copy = QVBoxLayout()
        copy.setSpacing(5)
        self.page_overline = Text("DETECT SETUP", role="overline")
        copy.addWidget(self.page_overline)
        self.page_title = Text("Prepare candidate detection", role="title")
        copy.addWidget(self.page_title)
        self.page_description = Text(
                "Choose the recordings folder for this Detect Collection.",
                role="body",
                word_wrap=True,
        )
        copy.addWidget(self.page_description)
        heading.addLayout(copy, 1)
        self.back_button = Button("Back to Studio", variant="outline")
        self.back_button.setAccessibleName("Back to Studio launchpad")
        self.back_button.clicked.connect(self.return_requested)
        heading.addWidget(self.back_button, 0, Qt.AlignmentFlag.AlignTop)
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
        navigation.addStretch()
        return navigation

    def _build_collection_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Detect Collection source")
        card.setMaximumWidth(940)
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

    def _render(self) -> None:
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

    def _set_route(self, route: str) -> None:
        if route not in {"setup", "recordings"}:
            raise ValueError(f"Unknown Detect route: {route}")
        if route == "recordings" and not self.recordings_button.isEnabled():
            route = "setup"
        route_changed = getattr(self, "current_route", None) != route
        self.current_route = route
        self.setup_button.setChecked(route == "setup")
        self.recordings_button.setChecked(route == "recordings")
        self.route_stack.setCurrentWidget(
            self.setup_view if route == "setup" else self.recordings_view
        )
        if route == "setup":
            self.page_overline.setText("DETECT SETUP")
            self.page_title.setText("Prepare candidate detection")
            self.page_description.setText(
                "Choose the recordings folder for this Detect Collection."
            )
        else:
            self.page_overline.setText("SOURCE INVENTORY")
            self.page_title.setText("Recordings")
            self.page_description.setText(
                "Approve the WAVs that belong to this Detect Collection."
            )
        self.setup_button.setAccessibleDescription(
            "Current Detect page" if route == "setup" else "Open Detect setup"
        )
        self.recordings_button.setAccessibleDescription(
            "Current Detect page" if route == "recordings" else "Open recordings folder"
        )
        if route_changed:
            QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(0))

    def focus_initial(self) -> None:
        if self.relink_card.isVisible():
            self.relink_confirm.setFocus()
            return
        picker = self.folder_picker if self.current_route == "setup" else self.relink_picker
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
            self.inventory_layout.removeWidget(self.inventory_table_card)
            self.inventory_layout.removeWidget(self.inventory_detail_card)
            if compact:
                self.inventory_layout.addWidget(self.inventory_table_card, 0, 0)
                self.inventory_layout.addWidget(self.inventory_detail_card, 1, 0)
            else:
                self.inventory_layout.addWidget(self.inventory_table_card, 0, 0)
                self.inventory_layout.addWidget(self.inventory_detail_card, 0, 1)

    @property
    def is_compact(self) -> bool:
        return self._compact
