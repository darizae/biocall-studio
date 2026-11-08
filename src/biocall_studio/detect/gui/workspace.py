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
from alp_ui.theme import ALPACA_LIGHT, interactions, make_icon
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPalette, QResizeEvent
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from biocall_studio.detect.application.controller import (
    DetectWorkspaceController,
    InventoryState,
    ModelIntakeState,
)
from biocall_studio.detect.application.navigation import (
    SIDEBAR_ROUTES,
    DetectRoute,
    active_sidebar_route,
    adaptive_new_detection_route,
    parse_detect_route,
)
from biocall_studio.detect.domain import RootBindingDecision
from biocall_studio.detect.domain.detection import DetectionSettings
from biocall_studio.detect.domain.inventory import (
    DecisionOrigin,
    InclusionDecision,
    InventoryRecording,
    InventorySnapshot,
    RecordingStatus,
)
from biocall_studio.detect.domain.runs import DetectRunStatus
from biocall_studio.detect.gui.history import (
    ExportDetailPage,
    ExportHistoryPage,
    RunHistoryPage,
)
from biocall_studio.detect.gui.results import ResultExplorer
from biocall_studio.detect.gui.storage import StorageSection, confirm_storage


def _duration(row: InventoryRecording) -> str:
    if row.wav is None:
        return "—"
    seconds = row.wav.frame_count / row.wav.sample_rate_hz
    if seconds >= 3_600:
        return f"{seconds / 3_600:.1f} h"
    if seconds >= 60:
        return f"{seconds / 60:.1f} min"
    return f"{seconds:.1f} s"


def _researcher_run_text(value: str) -> str:
    text = value
    for technical, plain in (
        ("Inventory", "Recording review"),
        ("inventory", "recording review"),
        ("Frozen inputs", "Inputs"),
        ("frozen inputs", "inputs"),
        ("publication receipt", "saved result"),
        ("publication", "saving"),
        ("immutable", "saved"),
        ("Worker", "Detection"),
        ("worker", "detection"),
        ("artifact", "result"),
        ("digest", "identifier"),
        ("manifest", "model information"),
        ("checksum", "file check"),
        ("runtime", "software"),
        ("schema", "format"),
        ("source-time", "recording time"),
    ):
        text = text.replace(technical, plain)
    return text


def _context_help(copy_id: str, help_text: str, subject: str) -> HelpHint:
    hint = HelpHint(help_text, subject=subject)
    hint.setObjectName(copy_id)
    return hint


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
        return tuple(row for row in self._snapshot.recordings if row.recording_key.startswith(key))

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


class DetectWorkspacePage(QWidget):
    """Persistent Detect navigation with workflow-owned nested history routes."""

    return_requested = Signal()

    def __init__(self, controller: DetectWorkspaceController):
        super().__init__()
        self.controller = controller
        self._compact = False
        self._recordings_attention_active = False
        self._rendered_inventory_id: str | None = None
        self.selected_key: str | None = None
        self.storage_estimate = None
        self.setObjectName("detectWorkspacePage")
        self.setAccessibleName("Detect workspace")

        self._root_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)
        self.sidebar = self._build_sidebar()
        self._root_layout.addWidget(self.sidebar)

        self.body = QWidget()
        light_palette = self.body.palette()
        light_palette.setColor(QPalette.ColorRole.Window, QColor(ALPACA_LIGHT.colors.background))
        self.body.setAutoFillBackground(True)
        self.body.setPalette(light_palette)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(0)
        self.slim_header = self._build_slim_header()
        self.body_layout.addWidget(self.slim_header)

        self.content_scroll = QScrollArea()
        self.content_scroll.setObjectName("detectContentScroll")
        self.content_scroll.setAccessibleName("Detect page content")
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.content = QWidget()
        self.content.setAutoFillBackground(True)
        self.content.setPalette(light_palette)
        self.outer = QVBoxLayout(self.content)
        self.outer.setContentsMargins(38, 30, 38, 42)
        self.outer.setSpacing(22)
        self.outer.addLayout(self._build_heading())
        self.selection_error = QLabel()
        self.selection_error.setWordWrap(True)
        self.selection_error.setAccessibleName("Detect page error")
        self.selection_error.setStyleSheet("color: #B91C1C; font-weight: 600;")
        self.outer.addWidget(self.selection_error)

        self.route_stack = QStackedWidget()
        self.route_stack.setMinimumWidth(0)
        self.route_stack.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )

        self.settings_card = self._build_settings_card()
        self.new_detection_view = self._build_new_detection_view()

        self.models_view = QWidget()
        models_view_layout = QVBoxLayout(self.models_view)
        models_view_layout.setContentsMargins(0, 0, 0, 0)
        models_view_layout.setSpacing(16)
        self.models_layout = QGridLayout()
        self.models_layout.setHorizontalSpacing(16)
        self.models_layout.setVerticalSpacing(16)
        self.model_card = self._build_model_card()
        self.refinement_model_card = self._build_refinement_model_card()
        self.models_layout.addWidget(self.model_card, 0, 0)
        self.models_layout.addWidget(self.refinement_model_card, 0, 1)
        self.models_layout.setColumnStretch(0, 1)
        self.models_layout.setColumnStretch(1, 1)
        models_view_layout.addLayout(self.models_layout)
        models_actions = QHBoxLayout()
        models_actions.addStretch()
        self.models_continue_button = Button("Continue to Recordings", variant="primary")
        self.models_continue_button.clicked.connect(lambda: self._set_route(DetectRoute.RECORDINGS))
        models_actions.addWidget(self.models_continue_button)
        models_view_layout.addLayout(models_actions)
        models_view_layout.addStretch()

        self.recordings_view = QWidget()
        recordings_layout = QVBoxLayout(self.recordings_view)
        recordings_layout.setContentsMargins(0, 0, 0, 0)
        recordings_layout.setSpacing(18)
        self.collection_card = self._build_collection_card()
        recordings_layout.addWidget(self.collection_card)
        self.recordings_card = self._build_recordings_card()
        recordings_layout.addWidget(self.recordings_card)
        self.inventory_content = self._build_inventory_content()
        recordings_layout.addWidget(self.inventory_content)
        self.relink_card = self._build_relink_card()
        recordings_layout.addWidget(self.relink_card)
        self.different_card = self._build_different_card()
        recordings_layout.addWidget(self.different_card)
        recordings_actions = QHBoxLayout()
        self.recordings_back_button = Button("Back to Models", variant="outline")
        self.recordings_back_button.clicked.connect(lambda: self._set_route(DetectRoute.MODELS))
        recordings_actions.addWidget(self.recordings_back_button)
        recordings_actions.addStretch()
        self.recordings_continue_button = Button("Continue to New detection", variant="primary")
        self.recordings_continue_button.clicked.connect(
            lambda: self._set_route(DetectRoute.NEW_DETECTION)
        )
        recordings_actions.addWidget(self.recordings_continue_button)
        recordings_layout.addLayout(recordings_actions)
        recordings_layout.addStretch()

        self.run_view = self._build_run_view()
        self.run_history_page = RunHistoryPage(self.controller)
        self.run_history_page.run_requested.connect(self._open_run)
        self.result_explorer = ResultExplorer(self.controller)
        self.result_explorer.run_requested.connect(self._open_result_or_active_run)
        self.result_explorer.recordings_requested.connect(
            lambda: self._set_route(DetectRoute.RECORDINGS)
        )
        self.result_explorer.models_requested.connect(lambda: self._set_route(DetectRoute.MODELS))
        self.export_history_page = ExportHistoryPage(self.controller)
        self.export_history_page.export_requested.connect(self._open_export_detail)
        self.export_detail_page = ExportDetailPage(self.controller, self._show_in_folder)
        self.export_detail_page.back_requested.connect(lambda: self._set_route(DetectRoute.EXPORTS))
        self._route_pages = {
            DetectRoute.NEW_DETECTION: self.new_detection_view,
            DetectRoute.RECORDINGS: self.recordings_view,
            DetectRoute.MODELS: self.models_view,
            DetectRoute.RUNS: self.run_history_page,
            DetectRoute.RUN_DETAIL: self.run_view,
            DetectRoute.RESULTS: self.result_explorer,
            DetectRoute.EXPORTS: self.export_history_page,
            DetectRoute.EXPORT_DETAIL: self.export_detail_page,
        }
        for page in self._route_pages.values():
            self.route_stack.addWidget(page)
        self.outer.addWidget(self.route_stack)
        self.outer.addStretch()
        self.content_scroll.setWidget(self.content)
        self.content_scroll.viewport().setAutoFillBackground(True)
        self.content_scroll.viewport().setPalette(light_palette)
        self.body_layout.addWidget(self.content_scroll, 1)
        self._root_layout.addWidget(self.body, 1)

        self.controller.state_changed.connect(self._render)
        self.controller.scan_progress_changed.connect(lambda _progress: self._render_scan())
        self.model_picker.folderChanged.connect(self.controller.choose_model_root)
        self.refinement_model_picker.folderChanged.connect(
            self.controller.choose_refinement_model_root
        )
        self.folder_picker.folderChanged.connect(self.controller.choose_source_root)
        self.relink_picker.folderChanged.connect(self.controller.choose_source_root)
        self.minimum_score.valueChanged.connect(lambda _value: self._render_readiness())
        self.window_overlap.currentIndexChanged.connect(lambda _index: self._render_readiness())
        self.combine_nearby.currentIndexChanged.connect(lambda _index: self._render_readiness())
        self.current_route = DetectRoute.MODELS
        self._navigate_new_detection()
        self._render()

    def _setting_row(self, field: QWidget, help_text: str, subject: str, copy_id: str) -> QWidget:
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
            _context_help(copy_id, help_text, subject),
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
            "Only results at or above this score are kept. Higher scores usually return fewer "
            "results.",
            "Minimum detection score",
            "CTX-01",
        )
        self.window_overlap = SelectInput(
            ("0%", "25%", "50%", "75%"),
            label="Window overlap",
        )
        self.window_overlap_row = self._setting_row(
            self.window_overlap,
            "How much each scan window overlaps the next. More overlap takes longer.",
            "Window overlap",
            "CTX-02",
        )
        self.combine_nearby = SelectInput(
            ("Do not combine across gaps", "0.20 s", "0.50 s"),
            label="Combine nearby candidates",
        )
        self.combine_nearby_row = self._setting_row(
            self.combine_nearby,
            "Joins nearby results when the gap between them is no larger than this value. "
            "Overlapping results are always joined.",
            "Combine nearby candidates",
            "CTX-03",
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
        self.storage_section = StorageSection()
        card.content_layout.addWidget(self.storage_section)
        actions = QHBoxLayout()
        actions.addStretch()
        self.start_detection_button = Button("Start detection", variant="primary")
        self.start_detection_button.setAccessibleDescription(
            "Freeze the verified setup and run CNN candidate detection."
        )
        self.start_detection_button.clicked.connect(self._run_primary_action)
        actions.addWidget(self.start_detection_button)
        card.content_layout.addLayout(actions)
        return card

    def _run_primary_action(self) -> None:
        self._start_detection()

    def _detection_settings(self) -> DetectionSettings:
        overlaps = (0, 25, 50, 75)
        gaps = (0, 200, 500)
        return DetectionSettings(
            minimum_score=float(self.minimum_score.value()),
            window_overlap_percent=overlaps[self.window_overlap.currentIndex()],
            combine_gap_ms=gaps[self.combine_nearby.currentIndex()],
            batch_size=16,
        )

    def _start_detection(self) -> None:
        settings = self._detection_settings()
        try:
            prior_digest = (
                None if self.storage_estimate is None else self.storage_estimate.input_digest
            )
            estimate = self.controller.estimate_detection_storage(
                settings,
                expected_digest=prior_digest,
            )
            self.storage_estimate = estimate
            self.storage_section.set_estimate(estimate, variable=True)
            if not estimate.can_start or not confirm_storage(self, estimate):
                return
            self.controller.start_detection(
                settings,
                storage_digest=estimate.input_digest,
                confirm_storage=estimate.requires_confirmation,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            self.selection_error.setText(str(exc))
            self.selection_error.setVisible(True)
            return
        self._set_route(DetectRoute.RUN_DETAIL)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("detectSidebar")
        sidebar.setAccessibleName("Detect navigation")
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(
            f"QFrame#detectSidebar {{ background: {ALPACA_LIGHT.colors.surface}; "
            f"border-right: 1px solid {ALPACA_LIGHT.colors.border}; }}"
        )
        self.sidebar_layout = QVBoxLayout(sidebar)
        self.sidebar_layout.setContentsMargins(18, 27, 18, 18)
        self.sidebar_layout.setSpacing(7)

        self.sidebar_brand = Text("Detect", role="subheading")
        self.sidebar_layout.addWidget(self.sidebar_brand)
        self.sidebar_layout.addSpacing(18)

        self.nav_scroll = QScrollArea()
        self.nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.nav_scroll.setWidgetResizable(True)
        self.nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.nav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav_scroll.setStyleSheet("QScrollArea { background: transparent; border: 0; }")
        nav_content = QWidget()
        nav_palette = nav_content.palette()
        nav_palette.setColor(QPalette.ColorRole.Window, QColor(ALPACA_LIGHT.colors.surface))
        nav_content.setAutoFillBackground(True)
        nav_content.setPalette(nav_palette)
        self.nav_scroll.viewport().setAutoFillBackground(True)
        self.nav_scroll.viewport().setPalette(nav_palette)
        self.navigation_layout = QBoxLayout(QBoxLayout.Direction.TopToBottom, nav_content)
        self.navigation_layout.setContentsMargins(0, 0, 0, 0)
        self.navigation_layout.setSpacing(7)
        labels = {
            DetectRoute.NEW_DETECTION: ("New detection", "plus"),
            DetectRoute.RECORDINGS: ("Recordings", "folder"),
            DetectRoute.MODELS: ("Models", "info"),
            DetectRoute.RUNS: ("Runs", "list"),
            DetectRoute.RESULTS: ("Results", "grid"),
            DetectRoute.EXPORTS: ("Exports", "folder"),
        }
        self._navigation: dict[DetectRoute, QPushButton] = {}
        for route in SIDEBAR_ROUTES:
            label, icon = labels[route]
            button = QPushButton(label)
            button.setAccessibleName(f"{label} navigation")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(38)
            button.setIcon(make_icon(icon, color=ALPACA_LIGHT.colors.text_muted, size=18))
            button.setProperty("icon_name", icon)
            if route is DetectRoute.NEW_DETECTION:
                button.clicked.connect(self._navigate_new_detection)
            else:
                button.clicked.connect(
                    lambda _checked=False, selected=route: self._set_route(selected)
                )
            self._navigation[route] = button
            self.navigation_layout.addWidget(button)
        self.navigation_layout.addStretch()
        self.nav_scroll.setWidget(nav_content)
        self.sidebar_layout.addWidget(self.nav_scroll, 1)
        return sidebar

    def _build_slim_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("detectHeader")
        header.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        header.setStyleSheet(
            f"QFrame#detectHeader {{ background: {ALPACA_LIGHT.colors.surface}; "
            f"border-bottom: 1px solid {ALPACA_LIGHT.colors.border}; }}"
        )
        self.header_layout = QGridLayout(header)
        self.header_layout.setContentsMargins(28, 12, 28, 12)
        self.header_layout.setHorizontalSpacing(12)
        self.header_layout.setVerticalSpacing(8)
        self.back_button = Button("Back to Studio", variant="outline", size="small")
        self.back_button.setAccessibleName("Back to Studio launchpad")
        self.back_button.clicked.connect(self.return_requested)
        self.header_layout.addWidget(self.back_button, 0, 0)
        self.header_layout.setColumnStretch(1, 1)
        self.active_run_label = Text("No active Run", role="body", word_wrap=True)
        self.header_layout.addWidget(self.active_run_label, 0, 2)
        self.active_run_badge = Badge("Idle", intent="neutral")
        self.active_run_badge.setAccessibleName("Detect Run status: Idle")
        self.header_layout.addWidget(self.active_run_badge, 0, 3)
        self.view_run_button = Button("View Run", variant="outline", size="small")
        self.view_run_button.setAccessibleName("View active Detect Run")
        self.view_run_button.clicked.connect(self._open_active_run)
        self.header_layout.addWidget(self.view_run_button, 0, 4)
        return header

    def _build_heading(self) -> QGridLayout:
        heading = QGridLayout()
        heading.setHorizontalSpacing(16)
        heading.setVerticalSpacing(10)
        self.heading_copy = QVBoxLayout()
        self.heading_copy.setSpacing(5)
        self.page_title = Text("Prepare candidate detection", role="title")
        self.heading_copy.addWidget(self.page_title)
        self.page_description = Text(
            "Choose a detection model and recordings folder.",
            role="body",
            word_wrap=True,
        )
        self.heading_copy.addWidget(self.page_description)
        heading.addLayout(self.heading_copy, 0, 0)
        heading.setColumnStretch(0, 1)
        self.heading_layout = heading
        return heading

    def _build_new_detection_view(self) -> QWidget:
        view = QWidget()
        outer = QVBoxLayout(view)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)
        self.run_summary_card = Card()
        self.run_summary_card.setAccessibleName("Detection input summary and readiness")
        self.run_summary_card.content_layout.addWidget(Text("Inputs", role="heading"))
        summary = QGridLayout()
        summary.setHorizontalSpacing(18)
        summary.setVerticalSpacing(8)
        summary.addWidget(QLabel("Detection model"), 0, 0)
        summary.addWidget(QLabel("Included recordings"), 0, 1)
        self.run_summary_model = Text("Not selected", role="subheading", word_wrap=True)
        self.run_summary_recordings = Text("0 recordings", role="subheading")
        summary.addWidget(self.run_summary_model, 1, 0)
        summary.addWidget(self.run_summary_recordings, 1, 1)
        self.change_model_button = Button("Change model", variant="outline", size="small")
        self.change_model_button.clicked.connect(lambda: self._set_route(DetectRoute.MODELS))
        summary.addWidget(self.change_model_button, 2, 0, Qt.AlignmentFlag.AlignLeft)
        self.change_recordings_button = Button("Review recordings", variant="outline", size="small")
        self.change_recordings_button.clicked.connect(
            lambda: self._set_route(DetectRoute.RECORDINGS)
        )
        summary.addWidget(self.change_recordings_button, 2, 1, Qt.AlignmentFlag.AlignLeft)
        summary.setColumnStretch(0, 1)
        summary.setColumnStretch(1, 1)
        self.run_summary_card.content_layout.addLayout(summary)
        self.run_blocker = Text("Choose a compatible detection model.", role="body", word_wrap=True)
        self.run_blocker.setAccessibleName("Detection readiness")
        self.run_summary_card.content_layout.addWidget(self.run_blocker)
        outer.addWidget(self.run_summary_card)
        outer.addWidget(self.settings_card)
        footer = QHBoxLayout()
        self.settings_back_button = Button("Back to Recordings", variant="outline")
        self.settings_back_button.clicked.connect(lambda: self._set_route(DetectRoute.RECORDINGS))
        footer.addWidget(self.settings_back_button)
        footer.addStretch()
        outer.addLayout(footer)
        outer.addStretch()
        return view

    def _build_refinement_model_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Random Forest model selection")
        header = QHBoxLayout()
        header.addWidget(Text("Random Forest model", role="heading"))
        header.addWidget(
            _context_help(
                "CTX-09",
                "Optionally use a Random Forest model to check the calls found by the detection "
                "model. The original results stay unchanged.",
                "RF refinement",
            ),
            0,
            Qt.AlignmentFlag.AlignTop,
        )
        header.addStretch()
        self.refinement_model_status_badge = Badge("Not selected", intent="neutral")
        header.addWidget(self.refinement_model_status_badge, 0, Qt.AlignmentFlag.AlignTop)
        card.content_layout.addLayout(header)
        self.refinement_model_name = Text("", role="subheading", word_wrap=True)
        self.refinement_model_name.hide()
        card.content_layout.addWidget(self.refinement_model_name)
        self.refinement_model_detail = QLabel("")
        self.refinement_model_detail.setWordWrap(True)
        self.refinement_model_detail.hide()
        card.content_layout.addWidget(self.refinement_model_detail)
        self.refinement_model_picker = FolderPicker(
            label="Random Forest model folder", show_hidden=True
        )
        self.refinement_model_picker.setAccessibleDescription(
            "Choose one Random Forest model folder created in Train."
        )
        card.content_layout.addWidget(self.refinement_model_picker)
        actions = QHBoxLayout()
        actions.addStretch()
        self.clear_refinement_model_button = Button("Clear model", variant="outline", size="small")
        self.clear_refinement_model_button.clicked.connect(
            self.controller.clear_refinement_model_selection
        )
        actions.addWidget(self.clear_refinement_model_button)
        card.content_layout.addLayout(actions)
        return card

    def _open_run(self, run_id: str) -> None:
        self.controller.select_run(run_id)
        self._set_route(DetectRoute.RUN_DETAIL)

    def _open_active_run(self) -> None:
        record = self.controller.active_run
        if record is not None:
            self._open_run(record.run_id)

    def _open_result_or_active_run(self) -> None:
        active = self.controller.active_run
        if active is not None:
            self._open_run(active.run_id)
            return
        item = self.controller.selected_result_item
        if item is not None:
            self._open_run(item.run_id)

    def _open_selected_run_result(self) -> None:
        record = self.controller.selected_run
        if record is None:
            return
        try:
            self.controller.select_result_for_run(record.run_id)
        except ValueError as exc:
            self.selection_error.setText(str(exc))
            self.selection_error.show()
            return
        self._set_route(DetectRoute.RESULTS)

    def _open_export_detail(self, export_id: str) -> None:
        try:
            self.controller.select_export(export_id)
        except (RuntimeError, ValueError) as exc:
            self.selection_error.setText(str(exc))
            self.selection_error.show()
            return
        self._set_route(DetectRoute.EXPORT_DETAIL)

    def _show_in_folder(self, path: str) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _navigate_new_detection(self) -> None:
        route = adaptive_new_detection_route(
            model_compatible=(
                self.controller.model_state is ModelIntakeState.COMPATIBLE
                and self.controller.model_reference is not None
            ),
            recordings_reviewed=self.controller.recordings_reviewed,
            active_run=self.controller.active_run is not None,
        )
        if route is DetectRoute.RUN_DETAIL and self.controller.active_run is not None:
            self.controller.select_run(self.controller.active_run.run_id)
        self._set_route(route)

    def _build_run_view(self) -> QWidget:
        view = QWidget()
        outer = QVBoxLayout(view)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        self.run_guidance = QLabel()
        self.run_guidance.setWordWrap(True)
        self.run_guidance.setAccessibleName("Detect Run guidance")
        self.run_guidance.setStyleSheet(
            "padding: 12px; color: #0F172A; background: #EFF6FF; "
            "border: 1px solid #CBD5E1; border-left: 4px solid #2563EB; "
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
        self.cancel_run_button.setAccessibleDescription("Stop detection safely.")
        self.cancel_run_button.clicked.connect(self.controller.cancel_active_run)
        actions.addWidget(self.cancel_run_button)
        actions.addStretch()
        self.open_run_result_button = Button("Open Result", variant="primary")
        self.open_run_result_button.clicked.connect(self._open_selected_run_result)
        actions.addWidget(self.open_run_result_button)
        self.open_run_log_button = Button("Open Run log", variant="outline")
        self.open_run_log_button.setAccessibleDescription(
            "Open the diagnostic log for this detection run."
        )
        self.open_run_log_button.clicked.connect(self._open_run_log)
        actions.addWidget(self.open_run_log_button)
        self.run_progress_card.content_layout.addLayout(actions)

        self.run_activity_card = Card()
        self.run_activity_card.setAccessibleName("Detect Run activity")
        self.run_activity_card.content_layout.addWidget(Text("Activity", role="heading"))
        self.run_activity = QLabel("No activity yet.")
        self.run_activity.setWordWrap(True)
        self.run_activity.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.run_activity.setAccessibleName("Detect Run activity entries")
        self.run_activity_card.content_layout.addWidget(self.run_activity)
        self.run_layout.addWidget(self.run_progress_card, 0, 0)
        self.run_layout.addWidget(self.run_activity_card, 0, 1)
        self.run_layout.setColumnStretch(0, 2)
        self.run_layout.setColumnStretch(1, 1)
        outer.addLayout(self.run_layout)
        footer = QHBoxLayout()
        self.run_back_button = Button("Back to Runs", variant="outline")
        self.run_back_button.clicked.connect(lambda: self._set_route(DetectRoute.RUNS))
        footer.addWidget(self.run_back_button)
        footer.addStretch()
        outer.addLayout(footer)
        outer.addStretch()
        return view

    def _open_run_log(self) -> None:
        record = self.controller.selected_run
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
        header.addLayout(labels, 1)
        header.addWidget(
            _context_help(
                "CTX-04",
                "A model trained in BioCall Studio that searches your recordings for possible "
                "calls.",
                "Detection Model",
            ),
            0,
            Qt.AlignmentFlag.AlignTop,
        )
        self.model_status_badge = Badge("Not selected", intent="neutral")
        self.model_status_badge.setAccessibleName("Detection Model status: Not selected")
        header.addWidget(self.model_status_badge, 0, Qt.AlignmentFlag.AlignTop)
        card.content_layout.addLayout(header)

        self.model_name = Text("", role="subheading", word_wrap=True)
        self.model_name.hide()
        card.content_layout.addWidget(self.model_name)
        self.model_detail = QLabel("")
        self.model_detail.setWordWrap(True)
        self.model_detail.setAccessibleName("Detection Model compatibility detail")
        self.model_detail.hide()
        card.content_layout.addWidget(self.model_detail)

        self.model_picker = FolderPicker(label="Train Model folder", show_hidden=True)
        self.model_picker.setAccessibleDescription("Choose one model folder created in Train.")
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
        card.setAccessibleName("Recordings folder selection")
        header = QHBoxLayout()
        labels = QVBoxLayout()
        labels.setSpacing(4)
        self.collection_title = Text("Recordings folder", role="heading")
        labels.addWidget(self.collection_title)
        self.collection_description = Text("", role="body", word_wrap=True)
        self.collection_description.hide()
        labels.addWidget(self.collection_description)
        header.addLayout(labels, 1)
        hint = _context_help(
            "CTX-05",
            "The folder of WAV files you want to search. BioCall Studio remembers it so you "
            "can relink the folder if it moves.",
            "Recordings folder",
        )
        header.addWidget(hint, 0, Qt.AlignmentFlag.AlignTop)
        self.status_badge = Badge("Not selected", intent="neutral")
        self.status_badge.setAccessibleName("Recordings folder status: Not selected")
        header.addWidget(self.status_badge, 0, Qt.AlignmentFlag.AlignTop)
        card.content_layout.addLayout(header)

        self.folder_picker = FolderPicker(label="Recordings folder")
        self.folder_picker.setAccessibleDescription(
            "Choose a new recordings folder or the relocated saved folder."
        )
        card.content_layout.addWidget(self.folder_picker)
        return card

    def _build_recordings_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Current recordings folder")
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
        self.relink_picker.setAccessibleDescription("Choose the relocated saved recordings folder.")
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
        labels.addWidget(Text("Approve recording inclusion", role="heading"))
        labels.addWidget(
            Text(
                "Review which WAV files belong to this recordings folder.",
                role="body",
                word_wrap=True,
            )
        )
        heading.addLayout(labels, 1)
        self.rescan_button = Button("Rescan", variant="primary")
        self.rescan_button.setAccessibleDescription(
            "Read the recordings folder again and save only a complete review."
        )
        self.rescan_button.clicked.connect(self.controller.rescan)
        heading.addWidget(self.rescan_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(heading)

        self.inventory_alert = QLabel()
        self.inventory_alert.setWordWrap(True)
        self.inventory_alert.setAccessibleName("Recording review status")
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
            _context_help(
                "CTX-06",
                "Included recordings are searched. Excluded and undecided recordings are skipped.",
                "Recording inclusion",
            )
        )
        self.inventory_table_card.content_layout.addLayout(table_heading)
        decision_actions = QHBoxLayout()
        self.include_selection_button = Button("Include selection", variant="outline", size="small")
        self.include_selection_button.clicked.connect(
            lambda: self._set_selected_decision(InclusionDecision.INCLUDED)
        )
        decision_actions.addWidget(self.include_selection_button)
        self.exclude_selection_button = Button("Exclude selection", variant="outline", size="small")
        self.exclude_selection_button.clicked.connect(
            lambda: self._set_selected_decision(InclusionDecision.EXCLUDED)
        )
        decision_actions.addWidget(self.exclude_selection_button)
        self.reset_selection_button = Button("Reset decision", variant="outline", size="small")
        self.reset_selection_button.clicked.connect(self._clear_selected_decision)
        decision_actions.addWidget(self.reset_selection_button)
        self.include_all_button = Button(
            "Include all valid recordings", variant="outline", size="small"
        )
        self.include_all_button.setAccessibleDescription(
            "Include every valid WAV in this recordings folder."
        )
        self.include_all_button.clicked.connect(self._include_all_valid_recordings)
        decision_actions.addWidget(self.include_all_button)
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
        self.detail_kind = Text("Selected item", role="caption")
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

    def _include_all_valid_recordings(self) -> None:
        snapshot = self.controller.snapshot
        if snapshot is None:
            return
        expected_inventory_id = snapshot.inventory_id
        exclusion_count = self.controller.bulk_inclusion_replaced_exclusion_count()
        confirmed = False
        if exclusion_count:
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Icon.Warning)
            dialog.setWindowTitle("Include all valid recordings?")
            noun = "recording" if exclusion_count == 1 else "recordings"
            dialog.setText(f"This will replace {exclusion_count} explicitly excluded {noun}.")
            dialog.setInformativeText(
                "Every currently valid WAV will be included. Invalid and unavailable "
                "entries will remain unavailable."
            )
            dialog.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
            )
            dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)
            dialog.setEscapeButton(QMessageBox.StandardButton.Cancel)
            confirmed = dialog.exec() == QMessageBox.StandardButton.Yes
            if not confirmed:
                return
        self.controller.include_all_valid_recordings(
            expected_inventory_id=expected_inventory_id,
            exclusions_confirmed=confirmed,
        )

    def _build_relink_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Confirm recordings folder relink")
        card.content_layout.addWidget(Text("Relink recordings folder", role="heading"))
        card.content_layout.addWidget(
            Text(
                "The folder identity matches the saved recordings folder. Confirm the new "
                "location before "
                "the binding changes.",
                role="body",
                word_wrap=True,
            )
        )
        paths = QGridLayout()
        paths.addWidget(Text("Previous location", role="caption"), 0, 0)
        paths.addWidget(Text("New location", role="caption"), 0, 1)
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
                "Its verified identity does not match the saved recordings folder. Use it as "
                "a new recording source instead of attaching unrelated files to saved history.",
                role="body",
                word_wrap=True,
            )
        )
        actions = QHBoxLayout()
        actions.addStretch()
        self.cancel_different_button = Button("Keep saved folder", variant="outline")
        self.cancel_different_button.clicked.connect(self.controller.cancel_relink)
        actions.addWidget(self.cancel_different_button)
        self.new_collection_button = Button("Use as new recordings folder", variant="primary")
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
            "Scan cancelled. No recording review was saved. Rescan before detection."
            if snapshot is None
            else "Scan cancelled. The last complete recording review was kept and no partial "
            "result was saved. Rescan before using it for detection."
        )
        message = {
            InventoryState.EMPTY: (
                "Recordings have not been reviewed yet. Scan this folder to discover WAV files."
            ),
            InventoryState.SCANNING: (
                "Scanning the recordings folder. The previous complete review remains unchanged."
            ),
            InventoryState.READY: "Review undecided and excluded recordings.",
            InventoryState.CANCELLED: cancelled_message,
            InventoryState.INVALID: (
                "The recording review needs attention. Repair invalid included recordings or "
                "change their inclusion, then rescan."
            ),
            InventoryState.STALE: (
                "Recordings changed after the last complete scan. Rescan before detection."
            ),
            InventoryState.MISSING: (
                "The recordings folder is unavailable. Relink it before rescanning."
            ),
        }[state]
        if self.controller.inventory_error and state is not InventoryState.CANCELLED:
            message = f"{message} {_researcher_run_text(self.controller.inventory_error)}"
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
        self.include_all_button.setEnabled(
            snapshot is not None
            and any(row.status is RecordingStatus.VALID for row in snapshot.recordings)
            and not self.controller.is_scanning
            and not self.controller.is_run_active
        )

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
        self.model_status_badge.setIntent(
            {
                ModelIntakeState.EMPTY: "neutral",
                ModelIntakeState.LOADING: "warning",
                ModelIntakeState.COMPATIBLE: "success",
                ModelIntakeState.INCOMPATIBLE: "danger",
                ModelIntakeState.MISSING: "danger",
            }[state]
        )
        self.model_status_badge.setAccessibleName(f"Detection Model status: {status}")
        if reference is not None:
            self.model_name.setText(reference.snapshot.label)
            self.model_name.show()
        else:
            self.model_name.setText("")
            self.model_name.hide()
        correction = {
            ModelIntakeState.EMPTY: "",
            ModelIntakeState.LOADING: "",
            ModelIntakeState.COMPATIBLE: "",
            ModelIntakeState.INCOMPATIBLE: (
                "This folder does not contain a compatible BioCall Studio model. "
                "Choose a different model folder."
            ),
            ModelIntakeState.MISSING: (
                "The selected model files are unavailable. Choose the model folder again."
            ),
        }[state]
        self.model_detail.setText(correction)
        self.model_detail.setVisible(bool(correction))
        inputs_locked = self.controller.is_run_active
        self.model_picker.setEnabled(state is not ModelIntakeState.LOADING and not inputs_locked)
        self.clear_model_button.setEnabled(
            selected is not None and state is not ModelIntakeState.LOADING and not inputs_locked
        )
        if state is not ModelIntakeState.LOADING:
            self.model_picker.setFolderPath("" if selected is None else str(selected))

    def _render_refinement_model(self) -> None:
        state = self.controller.refinement_model_state
        status = {
            ModelIntakeState.EMPTY: "Not selected",
            ModelIntakeState.LOADING: "Checking",
            ModelIntakeState.COMPATIBLE: "Compatible",
            ModelIntakeState.INCOMPATIBLE: "Incompatible",
            ModelIntakeState.MISSING: "Missing files",
        }[state]
        self.refinement_model_status_badge.setText(status)
        self.refinement_model_status_badge.setIntent(
            {
                ModelIntakeState.EMPTY: "neutral",
                ModelIntakeState.LOADING: "warning",
                ModelIntakeState.COMPATIBLE: "success",
                ModelIntakeState.INCOMPATIBLE: "danger",
                ModelIntakeState.MISSING: "danger",
            }[state]
        )
        self.refinement_model_status_badge.setAccessibleName(
            f"Random Forest model status: {status}"
        )
        reference = self.controller.refinement_model_reference
        selected = self.controller.selected_refinement_model_root
        self.refinement_model_name.setText(
            reference.snapshot.label if reference is not None else ""
        )
        self.refinement_model_name.setVisible(reference is not None)
        correction = {
            ModelIntakeState.EMPTY: "",
            ModelIntakeState.LOADING: "",
            ModelIntakeState.COMPATIBLE: "",
            ModelIntakeState.INCOMPATIBLE: (
                "This folder does not contain a compatible Random Forest model. "
                "Choose a different model folder."
            ),
            ModelIntakeState.MISSING: (
                "The selected Random Forest model files are unavailable. "
                "Choose the model folder again."
            ),
        }[state]
        self.refinement_model_detail.setText(correction)
        self.refinement_model_detail.setVisible(bool(correction))
        inputs_locked = self.controller.is_run_active
        self.refinement_model_picker.setEnabled(
            state is not ModelIntakeState.LOADING and not inputs_locked
        )
        self.clear_refinement_model_button.setEnabled(
            selected is not None and state is not ModelIntakeState.LOADING and not inputs_locked
        )
        if state is not ModelIntakeState.LOADING:
            self.refinement_model_picker.setFolderPath("" if selected is None else str(selected))

    def _render_readiness(self) -> None:
        settings_locked = self.controller.is_run_active
        for field in (
            self.minimum_score,
            self.window_overlap,
            self.combine_nearby,
        ):
            field.setEnabled(not settings_locked)
        snapshot = self.controller.snapshot
        reference = self.controller.model_reference
        model_ready = (
            self.controller.model_state is ModelIntakeState.COMPATIBLE and reference is not None
        )
        self.models_continue_button.setEnabled(model_ready)
        self.recordings_continue_button.setEnabled(self.controller.recordings_reviewed)
        self.run_summary_model.setText(
            reference.snapshot.label if reference is not None else "Not selected"
        )
        included = 0 if snapshot is None else snapshot.counts.included
        self.run_summary_recordings.setText(f"{included:,} recording{'s' if included != 1 else ''}")
        self.start_detection_button.setText("Start detection")
        self.start_detection_button.setAccessibleDescription(
            "Check the selected model and recordings, then start detection."
        )
        storage_ready = False
        if self.controller.inputs_ready and not self.controller.is_run_active:
            try:
                self.storage_estimate = self.controller.estimate_detection_storage(
                    self._detection_settings()
                )
            except (OSError, RuntimeError, ValueError):
                self.storage_estimate = None
                self.storage_section.clear()
            else:
                self.storage_section.set_estimate(self.storage_estimate, variable=True)
                storage_ready = self.storage_estimate.can_start
        else:
            self.storage_estimate = None
            self.storage_section.clear()
        if self.controller.is_run_active:
            self.start_detection_button.setText("Detection running")
            self.start_detection_button.setEnabled(False)
        else:
            self.start_detection_button.setEnabled(self.controller.inputs_ready and storage_ready)
        self.change_model_button.setEnabled(not settings_locked)
        self.change_recordings_button.setEnabled(not settings_locked)
        if self.controller.is_run_active:
            self.run_blocker.setText("Detection is running with the selected inputs.")
            return
        if self.controller.inputs_ready:
            self.run_blocker.setText("Ready to start detection.")
            return
        if self.controller.model_state is ModelIntakeState.LOADING:
            detail = "Wait while the detection model is checked."
        elif self.controller.model_state in {
            ModelIntakeState.INCOMPATIBLE,
            ModelIntakeState.MISSING,
        }:
            detail = self.model_detail.text()
        elif self.controller.model_state is ModelIntakeState.EMPTY:
            detail = "Select a model created in Train."
        elif self.controller.active_collection is None:
            detail = "Choose a recordings folder and review its WAV files."
        elif self.controller.root_decision is not RootBindingDecision.VALID:
            detail = "Relink or restore the recordings folder before using this setup."
        elif self.controller.inventory_state is not InventoryState.READY:
            detail = "Finish reviewing the recordings and include at least one valid WAV file."
        else:
            detail = "Include at least one valid WAV recording."
        self.run_blocker.setText(detail)

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
                row for row in snapshot.recordings if row.recording_key.startswith(entry.key)
            )
        return () if entry.recording is None else (entry.recording,)

    def _render_inventory_detail(self, entry: _InventoryEntry | None) -> None:
        if entry is None:
            self.detail_kind.setText("Selected item")
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
            self.detail_kind.setText("Selected folder" if entry.is_folder else "Selected file")
            self.detail_title.setText(entry.key)
            decisions = {row.decision.value.capitalize() for row in rows}
            statuses = {row.status.value.capitalize() for row in rows}
            sources = {row.decision_path or "No default rule" for row in rows}
            self.detail_decision.setText(next(iter(decisions)) if len(decisions) == 1 else "Mixed")
            self.detail_status.setText(next(iter(statuses)) if len(statuses) == 1 else "Mixed")
            self.detail_source.setText(next(iter(sources)) if len(sources) == 1 else "Mixed")
            seconds = sum(
                row.wav.frame_count / row.wav.sample_rate_hz for row in rows if row.wav is not None
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
            row.decision_origin in {DecisionOrigin.POLICY, DecisionOrigin.CONFLICT} for row in rows
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
        entry = self.inventory_model.entry_at(self.inventory_table.currentIndex().row())
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
        entry = self.inventory_model.entry_at(self.inventory_table.currentIndex().row())
        if entry is None:
            return
        self.controller.clear_inventory_decision(entry.key.rstrip("/"), is_folder=entry.is_folder)

    def _render_run_header(self) -> None:
        record = self.controller.active_run
        if record is None:
            self.active_run_label.setText("No active Run")
            self.active_run_badge.setText("Idle")
            self.active_run_badge.setAccessibleName("Detect Run status: Idle")
            self.active_run_badge.setIntent("neutral")
            self.view_run_button.setVisible(False)
            return
        status = record.status.value.capitalize()
        self.active_run_label.setText(record.title)
        self.active_run_badge.setText(status)
        self.active_run_badge.setIntent("warning")
        self.active_run_badge.setAccessibleName(f"Detect Run status: {status}")
        self.view_run_button.setVisible(self.current_route is not DetectRoute.RUN_DETAIL)

    def _render_run(self) -> None:
        record = self.controller.selected_run
        if record is None:
            self.run_title.setText("Run not started")
            self.run_stage.setText("Waiting for verified setup")
            self.run_status_badge.setText("Idle")
            self.run_status_badge.setAccessibleName("Run detail status: Idle")
            self.run_percent.setText("0%")
            self.run_progress_bar.setValue(0)
            self.run_stage_list.setText("○ Check inputs\n○ Search recordings\n○ Save results")
            self.run_activity.setText("No activity yet.")
            self.run_guidance.setText(
                "No Run has started. Prepare a compatible Model and review the recordings."
            )
            self.cancel_run_button.setEnabled(False)
            self.open_run_log_button.setEnabled(False)
            self.open_run_result_button.setEnabled(False)
            return

        status = record.status.value.capitalize()
        result_item = self.controller.result_item_for_run(record.run_id)
        result = None if result_item is None else result_item.result
        guidance = {
            DetectRunStatus.PREPARING: "Preparing the recordings.",
            DetectRunStatus.RUNNING: "Searching recordings for possible calls.",
            DetectRunStatus.CANCELLING: (
                "Cancellation requested. Waiting for detection to stop safely."
            ),
            DetectRunStatus.CANCELLED: (
                "This run was cancelled. Review the inputs and start a new detection."
            ),
            DetectRunStatus.INTERRUPTED: (
                "Detection stopped unexpectedly. Review the inputs and start a new detection."
            ),
            DetectRunStatus.FAILED: (
                _researcher_run_text(record.error_message)
                or "The run failed. Review the inputs and start a new detection."
            ),
            DetectRunStatus.COMPLETED: (
                (
                    f"Detection finished: {result.candidate_count:,} possible calls across "
                    f"{result.successful_files:,} recordings"
                    + (
                        f"; {result.failed_files:,} "
                        f"{'file' if result.failed_files == 1 else 'files'} failed."
                        if result.failed_files
                        else "."
                    )
                )
                if result is not None
                else "Detection finished, but the result could not be opened."
            ),
        }[record.status]
        self.run_title.setText(record.title)
        self.run_stage.setText(_researcher_run_text(record.current_stage))
        self.run_status_badge.setText(status)
        self.run_status_badge.setAccessibleName(f"Run detail status: {status}")
        self.run_percent.setText(f"{record.progress}%")
        self.run_progress_bar.setValue(record.progress)
        stage_rows = []
        for index, stage in enumerate(record.stages):
            marker = (
                "✓" if index < record.stage_index else ("●" if index == record.stage_index else "○")
            )
            if record.status is DetectRunStatus.COMPLETED:
                marker = "✓"
            stage_rows.append(f"{marker} {_researcher_run_text(stage)}")
        self.run_stage_list.setText("\n".join(stage_rows))
        self.run_activity.setText(
            "\n".join(_researcher_run_text(item) for item in record.activity[-8:])
            or "No activity yet."
        )
        self.run_guidance.setText(guidance)
        self.cancel_run_button.setEnabled(
            record.active and record.status in {DetectRunStatus.PREPARING, DetectRunStatus.RUNNING}
        )
        self.open_run_result_button.setEnabled(
            record.status is DetectRunStatus.COMPLETED and result is not None
        )
        self.open_run_log_button.setEnabled(
            self.controller.safe_run_log_path(record.run_id) is not None
        )

    def _render(self) -> None:
        self._render_run_header()
        self._render_run()
        self._render_model()
        self._render_refinement_model()
        self.run_history_page.render()
        self.result_explorer.render()
        self.export_history_page.render()
        self.export_detail_page.render()
        self._update_route_heading()
        collection = self.controller.active_collection
        proposal = self.controller.proposal
        self.relink_card.setVisible(
            proposal is not None and proposal.decision is RootBindingDecision.AWAITING_CONFIRMATION
        )
        self.different_card.setVisible(
            proposal is not None and proposal.decision is RootBindingDecision.CHANGED
        )
        self.selection_error.setText(
            self.controller.selection_error or self.controller.metadata_error
        )
        self.selection_error.setVisible(bool(self.selection_error.text()))

        if collection is None:
            self.collection_title.setText("Recordings folder")
            self.collection_description.setText("")
            self.collection_description.hide()
            self.status_badge.setText("Not selected")
            self.status_badge.setAccessibleName("Recordings folder status: Not selected")
            self.folder_picker.setFolderPath("")
            self._render_inventory()
            self._render_readiness()
            return

        decision = self.controller.root_decision
        status, description = {
            RootBindingDecision.VALID: (
                "Available",
                "",
            ),
            RootBindingDecision.MISSING: (
                "Folder missing",
                "Relink the recordings folder to continue.",
            ),
            RootBindingDecision.INACCESSIBLE: (
                "Access unavailable",
                "BioCall Studio cannot read this folder. Check access or relink it.",
            ),
            RootBindingDecision.CHANGED: (
                "Folder changed",
                "This location contains different recordings. Relink the original folder or "
                "use this as a new recordings folder.",
            ),
            None: ("Unavailable", "The saved recordings folder link could not be read."),
        }[decision]
        self.collection_title.setText(collection.ref.display_label)
        self.collection_description.setText(description)
        self.collection_description.setVisible(bool(description))
        self.status_badge.setText(status)
        self.status_badge.setAccessibleName(f"Recordings folder status: {status}")
        self.recordings_title.setText(collection.ref.display_label)
        self.recordings_description.setText(description)
        self.recordings_status_badge.setText(status)
        self.recordings_status_badge.setAccessibleName(f"Recordings folder status: {status}")
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
        recordings_attention = (
            proposal is not None
            or decision is not RootBindingDecision.VALID
            or self.controller.inventory_state is InventoryState.SCANNING
        )
        if recordings_attention and not self._recordings_attention_active:
            self._recordings_attention_active = True
            if self.current_route is DetectRoute.NEW_DETECTION:
                self._set_route(DetectRoute.RECORDINGS)
        elif not recordings_attention:
            self._recordings_attention_active = False
        self._render_inventory()
        self._render_readiness()

    def _update_route_heading(self) -> None:
        record = self.controller.selected_run
        titles = {
            DetectRoute.NEW_DETECTION: (
                "New detection",
                "Review the selected inputs and candidate settings.",
            ),
            DetectRoute.RECORDINGS: (
                "Recordings",
                "Choose the WAV files to search in this recordings folder.",
            ),
            DetectRoute.MODELS: (
                "Models",
                "Choose the detection model and optional Random Forest model.",
            ),
            DetectRoute.RUNS: ("Runs", "Open current and previous detection Runs."),
            DetectRoute.RUN_DETAIL: (
                "Run" if record is None else record.title,
                "Follow progress or review the completed Run.",
            ),
            DetectRoute.RESULTS: (
                "Results",
                "Review possible calls at their original recording times.",
            ),
            DetectRoute.EXPORTS: ("Exports", "Open completed corpus exports."),
            DetectRoute.EXPORT_DETAIL: (
                "Export details",
                "Check the saved files against their receipt.",
            ),
        }
        title, description = titles[self.current_route]
        self.page_title.setText(title)
        self.page_description.setText(description)

    def _set_route(self, route: str | DetectRoute) -> None:
        parsed = parse_detect_route(route)
        route_changed = getattr(self, "current_route", None) is not parsed
        self.current_route = parsed
        self.route_stack.setCurrentWidget(self._route_pages[parsed])
        active = active_sidebar_route(parsed)
        colors = ALPACA_LIGHT.colors
        selected = interactions(ALPACA_LIGHT).selected_surface
        for name, button in self._navigation.items():
            current = name is active
            button.setChecked(current)
            button.setAccessibleDescription("Current page" if current else "")
            button.setIcon(
                make_icon(
                    button.property("icon_name"),
                    color=colors.primary if current else colors.text_muted,
                    size=18,
                )
            )
            button.setStyleSheet(
                f"QPushButton {{ text-align: left; border: 0; border-radius: 8px; "
                f"padding: 0 14px; background: {selected if current else 'transparent'}; "
                f"color: {colors.primary_hover if current else colors.text_muted}; "
                f"font-weight: {600 if current else 400}; }}"
                f"QPushButton:hover {{ background: {selected}; "
                f"color: {colors.primary_hover}; }}"
                f"QPushButton:focus {{ border: 1px solid {colors.info}; }}"
            )
        self._update_route_heading()
        self._render_run_header()
        if route_changed:
            QTimer.singleShot(0, lambda: self.content_scroll.verticalScrollBar().setValue(0))
            QTimer.singleShot(0, self.focus_initial)

    def focus_initial(self) -> None:
        if self.current_route is DetectRoute.MODELS:
            buttons = self.model_picker.findChildren(QPushButton)
            (buttons[0] if buttons else self.models_continue_button).setFocus()
        elif self.current_route is DetectRoute.RECORDINGS:
            if self.relink_card.isVisible():
                self.relink_confirm.setFocus()
                return
            buttons = self.folder_picker.findChildren(QPushButton)
            (buttons[0] if buttons else self.recordings_continue_button).setFocus()
        elif self.current_route is DetectRoute.NEW_DETECTION:
            target = (
                self.start_detection_button
                if self.start_detection_button.isEnabled()
                else self.change_model_button
            )
            target.setFocus()
        elif self.current_route is DetectRoute.RUNS:
            self.run_history_page.focus_initial()
        elif self.current_route is DetectRoute.RUN_DETAIL:
            target = (
                self.cancel_run_button
                if self.cancel_run_button.isEnabled()
                else (
                    self.open_run_result_button
                    if self.open_run_result_button.isEnabled()
                    else self.run_back_button
                )
            )
            target.setFocus()
        elif self.current_route is DetectRoute.RESULTS:
            self.result_explorer.focus_initial()
        elif self.current_route is DetectRoute.EXPORTS:
            self.export_history_page.focus_initial()
        elif self.current_route is DetectRoute.EXPORT_DETAIL:
            self.export_detail_page.focus_initial()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        compact = event.size().width() < 820
        if compact == self._compact:
            return
        self._compact = compact
        margin = 20 if compact else 38
        self.outer.setContentsMargins(margin, 24 if compact else 30, margin, 36)

        if compact:
            self._root_layout.setDirection(QBoxLayout.Direction.TopToBottom)
            self.sidebar.setMinimumWidth(0)
            self.sidebar.setMaximumWidth(16_777_215)
            self.sidebar.setFixedHeight(78)
            self.sidebar.setStyleSheet(
                f"QFrame#detectSidebar {{ background: {ALPACA_LIGHT.colors.surface}; "
                f"border-bottom: 1px solid {ALPACA_LIGHT.colors.border}; }}"
            )
            self.sidebar_layout.setContentsMargins(12, 8, 12, 8)
            self.sidebar_layout.setSpacing(0)
            self.sidebar_brand.hide()
            self.navigation_layout.setDirection(QBoxLayout.Direction.LeftToRight)
            self.nav_scroll.setFixedHeight(58)
            for button in self._navigation.values():
                button.setMinimumWidth(145)
                button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        else:
            self._root_layout.setDirection(QBoxLayout.Direction.LeftToRight)
            self.sidebar.setMinimumWidth(220)
            self.sidebar.setMaximumWidth(220)
            self.sidebar.setMinimumHeight(0)
            self.sidebar.setMaximumHeight(16_777_215)
            self.sidebar.setStyleSheet(
                f"QFrame#detectSidebar {{ background: {ALPACA_LIGHT.colors.surface}; "
                f"border-right: 1px solid {ALPACA_LIGHT.colors.border}; }}"
            )
            self.sidebar_layout.setContentsMargins(18, 27, 18, 18)
            self.sidebar_layout.setSpacing(7)
            self.sidebar_brand.show()
            self.navigation_layout.setDirection(QBoxLayout.Direction.TopToBottom)
            self.nav_scroll.setMinimumHeight(0)
            self.nav_scroll.setMaximumHeight(16_777_215)
            for button in self._navigation.values():
                button.setMinimumWidth(0)
                button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        for widget in (
            self.back_button,
            self.active_run_label,
            self.active_run_badge,
            self.view_run_button,
        ):
            self.header_layout.removeWidget(widget)
        if compact:
            self.header_layout.addWidget(self.back_button, 0, 0, 1, 2)
            self.header_layout.addWidget(self.active_run_label, 1, 0)
            self.header_layout.addWidget(self.active_run_badge, 1, 1)
            self.header_layout.addWidget(self.view_run_button, 1, 2)
        else:
            self.header_layout.addWidget(self.back_button, 0, 0)
            self.header_layout.addWidget(self.active_run_label, 0, 2)
            self.header_layout.addWidget(self.active_run_badge, 0, 3)
            self.header_layout.addWidget(self.view_run_button, 0, 4)

        for widget in (self.model_card, self.refinement_model_card):
            self.models_layout.removeWidget(widget)
        for row in (
            self.minimum_score_row,
            self.window_overlap_row,
            self.combine_nearby_row,
        ):
            self.settings_layout.removeWidget(row)
        self.inventory_layout.removeWidget(self.inventory_table_card)
        self.inventory_layout.removeWidget(self.inventory_detail_card)
        self.run_layout.removeWidget(self.run_progress_card)
        self.run_layout.removeWidget(self.run_activity_card)
        if compact:
            self.models_layout.addWidget(self.model_card, 0, 0)
            self.models_layout.addWidget(self.refinement_model_card, 1, 0)
            self.models_layout.setColumnStretch(0, 1)
            self.models_layout.setColumnStretch(1, 0)
            self.settings_layout.addWidget(self.minimum_score_row, 0, 0)
            self.settings_layout.addWidget(self.window_overlap_row, 1, 0)
            self.settings_layout.addWidget(self.combine_nearby_row, 2, 0)
            self.settings_layout.setColumnStretch(0, 1)
            self.settings_layout.setColumnStretch(1, 0)
            self.settings_layout.setColumnStretch(2, 0)
            self.inventory_layout.addWidget(self.inventory_table_card, 0, 0)
            self.inventory_layout.addWidget(self.inventory_detail_card, 1, 0)
            self.run_layout.addWidget(self.run_progress_card, 0, 0)
            self.run_layout.addWidget(self.run_activity_card, 1, 0)
        else:
            self.models_layout.addWidget(self.model_card, 0, 0)
            self.models_layout.addWidget(self.refinement_model_card, 0, 1)
            self.models_layout.setColumnStretch(0, 1)
            self.models_layout.setColumnStretch(1, 1)
            self.settings_layout.addWidget(self.minimum_score_row, 0, 0)
            self.settings_layout.addWidget(self.window_overlap_row, 0, 1)
            self.settings_layout.addWidget(self.combine_nearby_row, 0, 2)
            for column in range(3):
                self.settings_layout.setColumnStretch(column, 1)
            self.inventory_layout.addWidget(self.inventory_table_card, 0, 0)
            self.inventory_layout.addWidget(self.inventory_detail_card, 0, 1)
            self.run_layout.addWidget(self.run_progress_card, 0, 0)
            self.run_layout.addWidget(self.run_activity_card, 0, 1)
        self.result_explorer.set_compact(compact)
        for layout in (
            self._root_layout,
            self.sidebar_layout,
            self.navigation_layout,
            self.header_layout,
            self.models_layout,
            self.settings_layout,
            self.inventory_layout,
            self.run_layout,
            self.route_stack.layout(),
        ):
            layout.invalidate()
            layout.activate()
        for widget in (*self._route_pages.values(), self.route_stack, self.content):
            widget.updateGeometry()

    @property
    def is_compact(self) -> bool:
        return self._compact
