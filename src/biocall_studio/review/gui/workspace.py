"""Native researcher-facing Review workspace."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from alp_ui.components import (
    Badge,
    Button,
    Card,
    HelpHint,
    ProgressBar,
    SelectInput,
    Text,
    TextInput,
)
from PySide6.QtCore import QEvent, QModelIndex, QObject, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QDesktopServices,
    QKeySequence,
    QPainter,
    QPixmap,
    QResizeEvent,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from biocall_studio.review.application.cache import (
    change_session_settings_with_preflight,
    session_token_is_current,
)
from biocall_studio.review.application.controller import ReviewSessionController
from biocall_studio.review.application.generation import (
    GenerationCancelled,
    GenerationJob,
    GenerationToken,
    SpectrogramGenerationSupervisor,
)
from biocall_studio.review.application.storage import (
    ReviewCacheSizePlan,
    assess_review_cache_storage,
    plan_review_cache_generation,
)
from biocall_studio.review.application.view_state import (
    ReviewFilter,
    ReviewShortcutAction,
    ReviewSort,
    ReviewView,
    ReviewViewState,
    shortcut_action,
)
from biocall_studio.review.domain.cache import CachePriority
from biocall_studio.review.domain.exports import (
    ReviewExportMode,
    ReviewExportPlan,
    ReviewExportReceipt,
)
from biocall_studio.review.domain.intake import EligibleCandidate
from biocall_studio.review.domain.sessions import ReviewLabel, ReviewSessionState
from biocall_studio.review.domain.spectrograms import (
    SpectrogramImageTier,
    SpectrogramSettings,
    plan_candidate_context,
)
from biocall_studio.review.gui.audio_proof import QtMediaPlayback, SpectrogramView
from biocall_studio.review.gui.models import ReviewCandidateTableModel, ReviewGalleryModel
from biocall_studio.review.gui.settings import SpectrogramSettingsPage
from biocall_studio.review.persistence.cache import SpectrogramCache
from biocall_studio.review.persistence.sessions import ReviewCandidateView, ReviewSession
from biocall_studio.review.workflows.audio import (
    AudioSourceError,
    AudioSourceProblem,
    SourceIdentityCache,
    read_candidate_audio,
)
from biocall_studio.review.workflows.spectrograms import (
    SpectrogramRenderRequest,
    render_spectrogram,
    spectrogram_content_key,
)
from biocall_studio.shared.storage import (
    StorageDecision,
    StorageEstimate,
    format_binary_size,
    format_output_estimate,
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _completed_date(timestamp: str) -> str:
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return timestamp


@dataclass(frozen=True, slots=True)
class ReviewResultChoice:
    collection_id: str
    result_id: str
    name: str
    kind: str
    completed_at: str
    eligible_count: int


class _FocusTooltipFilter(QObject):
    def eventFilter(self, watched, event):  # noqa: N802
        if event.type() is QEvent.Type.FocusIn and watched.toolTip():
            QToolTip.showText(
                watched.mapToGlobal(watched.rect().bottomLeft()), watched.toolTip(), watched
            )
        return super().eventFilter(watched, event)


class _GalleryDelegate(QStyledItemDelegate):
    def sizeHint(self, _option, _index):  # noqa: N802
        return QSize(284, 108)

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            painter.fillRect(option.rect, option.palette.highlight())
        content = option.rect.adjusted(4, 4, -4, -4)
        image_rect = content.adjusted(0, 0, 0, -(content.height() - 70))
        thumbnail = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(thumbnail, QPixmap) and not thumbnail.isNull():
            painter.drawPixmap(
                image_rect,
                thumbnail.scaled(
                    image_rect.size(),
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ),
            )
        text_rect = content.adjusted(0, 72, 0, 0)
        painter.setPen(
            option.palette.highlightedText().color() if selected else option.palette.text().color()
        )
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            str(index.data(Qt.ItemDataRole.DisplayRole) or ""),
        )
        painter.restore()


class ReviewLandingPage(QScrollArea):
    start_requested = Signal(object, object)
    session_requested = Signal(str)
    successor_requested = Signal(str)
    settings_requested = Signal()

    def __init__(self, controller: ReviewSessionController, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        self.choices: tuple[ReviewResultChoice, ...] = ()
        self.session_rows: tuple[ReviewSession, ...] = ()
        self.export_rows = ()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAccessibleName("Review result and session landing")
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(32, 28, 32, 36)
        outer.setSpacing(20)

        heading = QHBoxLayout()
        heading.addWidget(Text("Choose Result", role="title"))
        heading.addStretch()
        self.preset_select = SelectInput(label="Spectrogram preset")
        self.preset_select.setMinimumWidth(220)
        heading.addWidget(self.preset_select)
        self.settings_button = Button("Settings", variant="outline")
        self.start_button = Button("Start session", variant="primary")
        heading.addWidget(self.settings_button, 0, Qt.AlignmentFlag.AlignBottom)
        heading.addWidget(self.start_button, 0, Qt.AlignmentFlag.AlignBottom)
        outer.addLayout(heading)

        self.results = QTableWidget(0, 4)
        self.results.setObjectName("reviewResultTable")
        self.results.setHorizontalHeaderLabels(("Result", "Kind", "Completed", "Eligible"))
        self.results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results.verticalHeader().hide()
        self.results.horizontalHeader().setStretchLastSection(True)
        self.results.setAccessibleName("Available completed Detect Results")
        outer.addWidget(self.results)
        self.empty_label = QLabel("No detections to review.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setAccessibleName("No Review detections")
        outer.addWidget(self.empty_label)

        session_heading = QHBoxLayout()
        session_heading.addWidget(Text("Sessions", role="heading"))
        session_heading.addStretch()
        self.open_session_button = Button("Open", variant="outline")
        session_heading.addWidget(self.open_session_button)
        outer.addLayout(session_heading)
        self.sessions = QTableWidget(0, 4)
        self.sessions.setObjectName("reviewSessionTable")
        self.sessions.setHorizontalHeaderLabels(("Session", "Status", "Reviewed", "Updated"))
        self.sessions.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sessions.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.sessions.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sessions.verticalHeader().hide()
        self.sessions.horizontalHeader().setStretchLastSection(True)
        self.sessions.setAccessibleName("Review sessions")
        outer.addWidget(self.sessions)

        export_heading = QHBoxLayout()
        export_heading.addWidget(Text("Exports", role="heading"))
        export_heading.addStretch()
        self.show_export_button = Button("Show in folder", variant="outline")
        export_heading.addWidget(self.show_export_button)
        outer.addLayout(export_heading)
        self.exports = QTableWidget(0, 4)
        self.exports.setObjectName("reviewExportHistoryTable")
        self.exports.setHorizontalHeaderLabels(("Session", "Format", "Included", "Completed"))
        self.exports.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.exports.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.exports.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.exports.verticalHeader().hide()
        self.exports.horizontalHeader().setStretchLastSection(True)
        self.exports.setAccessibleName("Completed Review exports")
        outer.addWidget(self.exports)
        outer.addStretch()
        self.setWidget(content)

        self.settings_button.clicked.connect(self.settings_requested)
        self.start_button.clicked.connect(self._start)
        self.open_session_button.clicked.connect(self._open_selected_session)
        self.sessions.doubleClicked.connect(lambda _index: self._inspect_selected_session())
        self.sessions.currentCellChanged.connect(lambda *_args: self._update_session_action())
        self.exports.currentCellChanged.connect(lambda *_args: self._update_export_action())
        self.exports.doubleClicked.connect(lambda _index: self._show_selected_export())
        self.show_export_button.clicked.connect(self._show_selected_export)
        self.results.currentCellChanged.connect(lambda *_args: self._update_result_action())

    def refresh(self, choices: tuple[ReviewResultChoice, ...]) -> None:
        self.choices = tuple(choice for choice in choices if choice.eligible_count >= 0)
        self.results.setRowCount(len(self.choices))
        for row, choice in enumerate(self.choices):
            values = (
                choice.name,
                choice.kind,
                _completed_date(choice.completed_at),
                f"{choice.eligible_count:,}",
            )
            for column, value in enumerate(values):
                self.results.setItem(row, column, QTableWidgetItem(value))
        if self.choices:
            self.results.selectRow(0)
        open_exists = self.controller.store.open_session() is not None
        self._update_result_action(open_exists=open_exists)

        selected_preset = self.preset_select.currentText()
        self.preset_select.control.clear()
        for preset in self.controller.list_presets():
            self.preset_select.addItem(preset.preset_name, preset.preset_id)
        preset_names = [
            self.preset_select.control.itemText(i) for i in range(self.preset_select.count())
        ]
        if selected_preset in preset_names:
            self.preset_select.setCurrentIndex(preset_names.index(selected_preset))

        self.session_rows = self.controller.list_sessions()
        self.sessions.setRowCount(len(self.session_rows))
        for row, session in enumerate(self.session_rows):
            values = (
                session.name,
                session.state.value.title(),
                (
                    f"{session.call_count + session.not_call_count:,} of "
                    f"{session.eligible_candidate_count:,}"
                ),
                _completed_date(session.updated_at),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, session.session_id)
                self.sessions.setItem(row, column, item)
        if self.session_rows:
            self.sessions.selectRow(0)
        self._update_session_action()

        self.export_rows = self.controller.list_export_history()
        self.exports.setRowCount(len(self.export_rows))
        mode_names = {
            ReviewExportMode.INDIVIDUAL: "Individual WAV files",
            ReviewExportMode.COMBINED: "Combined WAV + Raven TSV",
            ReviewExportMode.BOTH: "Both",
        }
        for row, record in enumerate(self.export_rows):
            values = (
                record.session_name,
                mode_names[record.mode],
                f"{record.included_count:,}",
                _completed_date(record.completed_at),
            )
            for column, value in enumerate(values):
                self.exports.setItem(row, column, QTableWidgetItem(value))
        if self.export_rows:
            self.exports.selectRow(0)
        self._update_export_action()

    def _update_export_action(self) -> None:
        self.show_export_button.setEnabled(0 <= self.exports.currentRow() < len(self.export_rows))

    def _show_selected_export(self) -> None:
        row = self.exports.currentRow()
        if not 0 <= row < len(self.export_rows):
            return
        try:
            receipt = self.controller.verify_export_history(self.export_rows[row])
        except (OSError, RuntimeError, ValueError):
            QMessageBox.warning(
                self,
                "Export unavailable",
                "This export no longer matches its verified receipt.",
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(receipt.final_destination))

    def _update_result_action(self, *, open_exists: bool | None = None) -> None:
        row = self.results.currentRow()
        selected = self.choices[row] if 0 <= row < len(self.choices) else None
        if open_exists is None:
            open_exists = self.controller.store.open_session() is not None
        has_detections = selected is not None and selected.eligible_count > 0
        self.start_button.setEnabled(has_detections and not open_exists)
        self.empty_label.setVisible(selected is None or not has_detections)

    def _selected_session(self) -> ReviewSession | None:
        row = self.sessions.currentRow()
        return self.session_rows[row] if 0 <= row < len(self.session_rows) else None

    def _update_session_action(self) -> None:
        session = self._selected_session()
        if session is None:
            self.open_session_button.setEnabled(False)
            self.open_session_button.setText("Open")
            return
        self.open_session_button.setText(
            {
                ReviewSessionState.OPEN: "Open",
                ReviewSessionState.CLOSED: "Resume",
                ReviewSessionState.FINALIZED: "Continue in new session",
            }[session.state]
        )
        active = self.controller.store.open_session()
        self.open_session_button.setEnabled(
            active is None or active.session_id == session.session_id
        )

    def _start(self) -> None:
        row = self.results.currentRow()
        preset_index = self.preset_select.currentIndex()
        presets = self.controller.list_presets()
        if 0 <= row < len(self.choices) and 0 <= preset_index < len(presets):
            self.start_requested.emit(self.choices[row], presets[preset_index])

    def _open_selected_session(self) -> None:
        session = self._selected_session()
        if session is None:
            return
        if session.state is ReviewSessionState.FINALIZED:
            self.successor_requested.emit(session.session_id)
        else:
            self.session_requested.emit(session.session_id)

    def _inspect_selected_session(self) -> None:
        session = self._selected_session()
        if session is not None:
            self.session_requested.emit(session.session_id)


class ReviewSessionPage(QWidget):
    view_requested = Signal(str)
    filter_requested = Signal(str)
    sort_requested = Signal(str)
    search_requested = Signal(str)
    label_requested = Signal(str)
    previous_requested = Signal()
    next_requested = Signal()
    play_requested = Signal()
    undo_requested = Signal()
    accept_all_requested = Signal()
    close_requested = Signal()
    finalize_requested = Signal()
    export_requested = Signal()
    rename_requested = Signal(str)
    shortcuts_requested = Signal()
    clear_requested = Signal()
    clear_selection_requested = Signal()
    settings_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._compact = False
        self._tooltip_filter = _FocusTooltipFilter(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(30, 24, 30, 30)
        outer.setSpacing(14)

        header = QGridLayout()
        self.header_layout = header
        self.name_input = TextInput(label="Session name")
        self.name_input.control.setObjectName("reviewSessionName")
        self.name_input.control.setMaxLength(120)
        self.status_badge = Badge("Open", intent="success")
        self.counts_label = QLabel()
        self.counts_label.setAccessibleName("Review progress counts")
        self.undo_button = self._shortcut_button(
            "Undo", "Undo last label action · Ctrl/⌘+Z", "Undo"
        )
        self.close_button = Button("Close session", variant="outline")
        self.finalize_button = Button("Finalize", variant="primary")
        self.export_button = Button("Export", variant="primary")
        outer.addLayout(header)
        self.progress = ProgressBar(minimum=0, maximum=1, value=0)
        self.progress.setAccessibleName("Reviewed detections")
        outer.addWidget(self.progress)

        controls = QHBoxLayout()
        self.view_buttons: dict[ReviewView, Button] = {}
        for view, text in (
            (ReviewView.GALLERY, "Gallery"),
            (ReviewView.LIST, "List"),
            (ReviewView.ONE_BY_ONE, "One by one"),
        ):
            button = Button(text, variant="outline")
            button.setCheckable(True)
            button.clicked.connect(
                lambda _checked=False, value=view: self.view_requested.emit(value.value)
            )
            controls.addWidget(button)
            self.view_buttons[view] = button
        controls.addStretch()
        self.settings_button = Button("Spectrograms", variant="outline")
        controls.addWidget(self.settings_button)
        outer.addLayout(controls)

        query = QHBoxLayout()
        self.filter_buttons: dict[ReviewFilter, Button] = {}
        for filter_name, text in (
            (ReviewFilter.ALL, "All"),
            (ReviewFilter.UNREVIEWED, "Unreviewed"),
            (ReviewFilter.CALL, "Call"),
            (ReviewFilter.NOT_CALL, "Not a call"),
        ):
            button = Button(text, variant="outline", size="small")
            button.setCheckable(True)
            button.clicked.connect(
                lambda _checked=False, value=filter_name: self.filter_requested.emit(value.value)
            )
            query.addWidget(button)
            self.filter_buttons[filter_name] = button
        query.addStretch()
        self.search = QLineEdit()
        self.search.setObjectName("reviewRecordingSearch")
        self.search.setPlaceholderText("Search recordings")
        self.search.setAccessibleName("Search recordings")
        self.search.setMaximumWidth(230)
        query.addWidget(self.search)
        self.sort = QComboBox()
        self.sort.setAccessibleName("Sort detections")
        self.sort.addItem("Time", ReviewSort.SOURCE_TIME.value)
        self.sort.addItem("Recording", ReviewSort.RECORDING.value)
        self.sort.addItem("Prediction", ReviewSort.PREDICTION_DESCENDING.value)
        query.addWidget(self.sort)
        outer.addLayout(query)

        self.views = QStackedWidget()
        self.gallery = QListView()
        self.gallery.setObjectName("reviewCandidateGallery")
        self.gallery.setViewMode(QListView.ViewMode.IconMode)
        self.gallery.setResizeMode(QListView.ResizeMode.Adjust)
        self.gallery.setMovement(QListView.Movement.Static)
        self.gallery.setUniformItemSizes(True)
        self.gallery.setGridSize(QSize(300, 122))
        self.gallery.setIconSize(QSize(284, 70))
        self.gallery.setItemDelegate(_GalleryDelegate(self.gallery))
        self.gallery.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.gallery.setAccessibleName("Review spectrogram gallery")
        self.table = QTableView()
        self.table.setObjectName("reviewCandidateTable")
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAccessibleName("Review candidate list")
        self.one_scroll = QScrollArea()
        self.one_scroll.setWidgetResizable(True)
        self.one_scroll.setFrameShape(QFrame.Shape.NoFrame)
        one_content = QWidget()
        self.one_layout = QGridLayout(one_content)
        self.one_layout.setContentsMargins(0, 0, 0, 0)
        self.one_layout.setSpacing(16)
        self.detail_card = Card()
        self.current_label = QLabel()
        self.current_label.setAccessibleName("Current recording and time")
        self.detail_card.content_layout.addWidget(self.current_label)
        self.spectrogram = SpectrogramView()
        self.detail_card.content_layout.addWidget(self.spectrogram, 1)
        audio_row = QHBoxLayout()
        self.play_button = self._shortcut_button(
            "Play", "Play / Pause · K or Space", "Play or pause"
        )
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setAccessibleName("Audio position")
        self.audio_time = QLabel("0:00 / 0:00")
        audio_row.addWidget(self.play_button)
        audio_row.addWidget(self.seek, 1)
        audio_row.addWidget(self.audio_time)
        self.detail_card.content_layout.addLayout(audio_row)
        self.detail_status = QLabel()
        self.detail_status.setWordWrap(True)
        self.detail_status.setAccessibleName("Review audio and spectrogram status")
        self.detail_card.content_layout.addWidget(self.detail_status)

        self.action_card = Card()
        self.action_card.content_layout.addWidget(Text("Label", role="heading"))
        self.call_button = self._shortcut_button("Call", "Call · F", "Label as Call")
        self.not_call_button = self._shortcut_button(
            "Not a call", "Not a call · D", "Label as Not a call"
        )
        self.clear_label_button = self._shortcut_button(
            "Clear label", "Clear label · S", "Clear label"
        )
        self.action_card.content_layout.addWidget(self.call_button)
        self.action_card.content_layout.addWidget(self.not_call_button)
        self.action_card.content_layout.addWidget(self.clear_label_button)
        navigation = QHBoxLayout()
        self.previous_button = self._shortcut_button(
            "Previous", "Previous · J or ←", "Previous detection"
        )
        self.next_button = self._shortcut_button("Next", "Next · L or →", "Next detection")
        navigation.addWidget(self.previous_button)
        navigation.addWidget(self.next_button)
        self.action_card.content_layout.addLayout(navigation)
        clear_row = QHBoxLayout()
        self.clear_spectrograms_button = Button("Clear spectrograms", variant="outline")
        clear_help = HelpHint(
            (
                "Frees disk space by deleting generated images. "
                "Your labels and recordings stay unchanged."
            ),
            subject="Clear spectrograms",
        )
        clear_row.addWidget(self.clear_spectrograms_button, 1)
        clear_row.addWidget(clear_help)
        self.action_card.content_layout.addLayout(clear_row)
        self.shortcuts_button = Button("Keyboard shortcuts", variant="outline")
        self.shortcuts_button.setToolTip("Show the fixed Review keyboard shortcuts.")
        self.shortcuts_button.setAccessibleDescription(self.shortcuts_button.toolTip())
        self.action_card.content_layout.addWidget(self.shortcuts_button)
        self.one_scroll.setWidget(one_content)
        self.views.addWidget(self.gallery)
        self.views.addWidget(self.table)
        self.views.addWidget(self.one_scroll)
        outer.addWidget(self.views, 1)

        actions = QHBoxLayout()
        self.selection_label = QLabel()
        actions.addWidget(self.selection_label)
        self.clear_selected_button = Button("Clear spectrograms", variant="outline")
        self.clear_selected_button.setToolTip(
            "Frees disk space by deleting generated images. "
            "Your labels and recordings stay unchanged."
        )
        self.clear_selected_button.setAccessibleDescription(self.clear_selected_button.toolTip())
        actions.addWidget(self.clear_selected_button)
        actions.addStretch()
        accept_wrap = QHBoxLayout()
        self.accept_all_button = Button("Accept all", variant="outline")
        accept_help = HelpHint(
            "Marks all unreviewed detections as calls. Existing labels won't change.",
            subject="Accept all",
        )
        accept_wrap.addWidget(self.accept_all_button)
        accept_wrap.addWidget(accept_help)
        actions.addLayout(accept_wrap)
        outer.addLayout(actions)

        self._place_header(False)
        self._place_one(False)
        self.name_input.control.editingFinished.connect(
            lambda: self.rename_requested.emit(self.name_input.control.text())
        )
        self.undo_button.clicked.connect(self.undo_requested)
        self.close_button.clicked.connect(self.close_requested)
        self.finalize_button.clicked.connect(self.finalize_requested)
        self.export_button.clicked.connect(self.export_requested)
        self.settings_button.clicked.connect(self.settings_requested)
        self.search.textChanged.connect(self.search_requested)
        self.sort.currentIndexChanged.connect(
            lambda _index: self.sort_requested.emit(self.sort.currentData())
        )
        self.call_button.clicked.connect(lambda: self.label_requested.emit(ReviewLabel.CALL.value))
        self.not_call_button.clicked.connect(
            lambda: self.label_requested.emit(ReviewLabel.NOT_CALL.value)
        )
        self.clear_label_button.clicked.connect(
            lambda: self.label_requested.emit(ReviewLabel.UNREVIEWED.value)
        )
        self.previous_button.clicked.connect(self.previous_requested)
        self.next_button.clicked.connect(self.next_requested)
        self.play_button.clicked.connect(self.play_requested)
        self.shortcuts_button.clicked.connect(self.shortcuts_requested)
        self.clear_spectrograms_button.clicked.connect(self.clear_requested)
        self.clear_selected_button.clicked.connect(self.clear_selection_requested)
        self.accept_all_button.clicked.connect(self.accept_all_requested)

    def _shortcut_button(self, text: str, tooltip: str, accessible_name: str) -> Button:
        button = Button(text, variant="outline")
        button.setToolTip(tooltip)
        button.setAccessibleName(accessible_name)
        button.setAccessibleDescription(tooltip)
        button.installEventFilter(self._tooltip_filter)
        return button

    def _place_one(self, compact: bool) -> None:
        self.one_layout.removeWidget(self.detail_card)
        self.one_layout.removeWidget(self.action_card)
        if compact:
            self.one_layout.addWidget(self.detail_card, 0, 0)
            self.one_layout.addWidget(self.action_card, 1, 0)
            self.one_layout.setColumnStretch(0, 1)
            self.one_layout.setColumnStretch(1, 0)
        else:
            self.one_layout.addWidget(self.detail_card, 0, 0)
            self.one_layout.addWidget(self.action_card, 0, 1)
            self.one_layout.setColumnStretch(0, 4)
            self.one_layout.setColumnStretch(1, 1)
        self._compact = compact

    def _place_header(self, compact: bool) -> None:
        widgets = (
            self.name_input,
            self.status_badge,
            self.counts_label,
            self.undo_button,
            self.close_button,
            self.finalize_button,
            self.export_button,
        )
        for widget in widgets:
            self.header_layout.removeWidget(widget)
        for column in range(6):
            self.header_layout.setColumnStretch(column, 0)
        if compact:
            self.header_layout.addWidget(self.name_input, 0, 0, 1, 3)
            self.header_layout.addWidget(self.status_badge, 0, 3)
            self.header_layout.addWidget(self.counts_label, 1, 0, 1, 4)
            self.header_layout.addWidget(self.undo_button, 2, 0)
            self.header_layout.addWidget(self.close_button, 2, 1)
            self.header_layout.addWidget(self.finalize_button, 2, 2)
            self.header_layout.addWidget(self.export_button, 2, 3)
            self.header_layout.setColumnStretch(0, 1)
        else:
            self.header_layout.addWidget(self.name_input, 0, 0, 2, 1)
            self.header_layout.addWidget(self.status_badge, 0, 1)
            self.header_layout.addWidget(self.counts_label, 1, 1)
            self.header_layout.addWidget(self.undo_button, 0, 2, 2, 1)
            self.header_layout.addWidget(self.close_button, 0, 3, 2, 1)
            self.header_layout.addWidget(self.finalize_button, 0, 4, 2, 1)
            self.header_layout.addWidget(self.export_button, 0, 5, 2, 1)
            self.header_layout.setColumnStretch(0, 1)

    def set_compact(self, compact: bool) -> None:
        if compact != self._compact:
            self._place_header(compact)
            self._place_one(compact)
            self.updateGeometry()

    def render_state(self, state: ReviewViewState) -> None:
        session = state.session
        self.name_input.control.blockSignals(True)
        self.name_input.control.setText(session.name)
        self.name_input.control.blockSignals(False)
        self.name_input.control.setEnabled(session.state is ReviewSessionState.OPEN)
        self.status_badge.setText(session.state.value.title())
        reviewed = state.reviewed_count
        self.counts_label.setText(
            f"{reviewed:,} reviewed of {session.eligible_candidate_count:,} · "
            f"✓ Call {session.call_count:,} · × Not a call {session.not_call_count:,} · "
            f"○ Unreviewed {session.unreviewed_count:,}"
        )
        self.progress.setRange(0, max(1, session.eligible_candidate_count))
        self.progress.setValue(reviewed)
        self.progress.setFormat(f"{reviewed:,} of {session.eligible_candidate_count:,}")
        for view, button in self.view_buttons.items():
            button.setChecked(view is state.view)
        for filter_name, button in self.filter_buttons.items():
            button.setChecked(filter_name is state.filter)
        self.search.blockSignals(True)
        self.search.setText(state.search)
        self.search.blockSignals(False)
        sort_index = self.sort.findData(state.sort.value)
        self.sort.blockSignals(True)
        self.sort.setCurrentIndex(sort_index)
        self.sort.blockSignals(False)
        self.views.setCurrentIndex(
            {
                ReviewView.GALLERY: 0,
                ReviewView.LIST: 1,
                ReviewView.ONE_BY_ONE: 2,
            }[state.view]
        )
        editable = session.state is ReviewSessionState.OPEN
        for button in (
            self.call_button,
            self.not_call_button,
            self.clear_label_button,
            self.undo_button,
            self.accept_all_button,
            self.close_button,
            self.finalize_button,
        ):
            button.setEnabled(editable)
        self.export_button.setEnabled(session.state is ReviewSessionState.FINALIZED)


class ReviewSpectrogramsPage(QScrollArea):
    back_requested = Signal()
    settings_requested = Signal()
    generate_requested = Signal()
    cancel_requested = Signal()
    retry_requested = Signal()
    clear_requested = Signal()
    preset_change_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAccessibleName("Review spectrogram cache")
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(32, 28, 32, 36)
        outer.setSpacing(20)
        header = QHBoxLayout()
        header.addWidget(Text("Spectrograms", role="title"))
        header.addStretch()
        self.back_button = Button("Back to Review", variant="outline")
        self.settings_button = Button("Settings", variant="outline")
        self.clear_button = Button("Clear spectrograms", variant="outline")
        self.generate_button = Button("Generate all", variant="primary")
        self.cancel_button = Button("Cancel", variant="outline")
        self.retry_button = Button("Retry", variant="outline")
        for button in (
            self.back_button,
            self.settings_button,
            self.clear_button,
            self.generate_button,
            self.cancel_button,
            self.retry_button,
        ):
            header.addWidget(button)
        outer.addLayout(header)

        preset_row = QHBoxLayout()
        self.preset_select = SelectInput(label="Spectrogram preset")
        self.preset_select.setMinimumWidth(240)
        self.change_preset_button = Button("Change preset", variant="outline")
        preset_row.addWidget(self.preset_select)
        preset_row.addWidget(self.change_preset_button, 0, Qt.AlignmentFlag.AlignBottom)
        preset_row.addStretch()
        outer.addLayout(preset_row)

        card = Card()
        self.session_label = Text("", role="heading")
        self.availability_label = QLabel()
        card.content_layout.addWidget(self.session_label)
        card.content_layout.addWidget(self.availability_label)
        storage = QGridLayout()
        self.output_value = QLabel()
        self.peak_value = QLabel()
        self.free_value = QLabel()
        for column, (heading, widget) in enumerate(
            (
                ("Estimated output", self.output_value),
                ("Space needed while running", self.peak_value),
                ("Free on Spectrogram cache", self.free_value),
            )
        ):
            box = Card()
            box.content_layout.addWidget(Text(heading, role="caption"))
            box.content_layout.addWidget(widget)
            storage.addWidget(box, 0, column)
        card.content_layout.addLayout(storage)
        self.progress_label = QLabel()
        self.progress_label.setAccessibleName("Spectrogram generation progress")
        self.progress = ProgressBar(minimum=0, maximum=1, value=0)
        card.content_layout.addWidget(self.progress_label)
        card.content_layout.addWidget(self.progress)
        outer.addWidget(card)
        outer.addStretch()
        self.setWidget(content)

        clear_help = (
            "Frees disk space by deleting generated images. "
            "Your labels and recordings stay unchanged."
        )
        self.clear_button.setToolTip(clear_help)
        self.clear_button.setAccessibleDescription(clear_help)
        self.back_button.clicked.connect(self.back_requested)
        self.settings_button.clicked.connect(self.settings_requested)
        self.generate_button.clicked.connect(self.generate_requested)
        self.cancel_button.clicked.connect(self.cancel_requested)
        self.retry_button.clicked.connect(self.retry_requested)
        self.clear_button.clicked.connect(self.clear_requested)
        self.change_preset_button.clicked.connect(
            lambda: self.preset_change_requested.emit(str(self.preset_select.control.currentData()))
        )
        self.set_running(False)

    def set_presets(
        self,
        presets,
        *,
        current_preset_id: str,
        editable: bool,
    ) -> None:
        self.preset_select.control.blockSignals(True)
        self.preset_select.control.clear()
        current_index = 0
        for index, preset in enumerate(presets):
            self.preset_select.addItem(preset.preset_name, preset.preset_id)
            if preset.preset_id == current_preset_id:
                current_index = index
        self.preset_select.setCurrentIndex(current_index)
        self.preset_select.control.blockSignals(False)
        self.preset_select.setEnabled(editable)
        self.change_preset_button.setEnabled(editable)

    def set_estimate(
        self,
        session: ReviewSession,
        plan: ReviewCacheSizePlan,
        estimate: StorageEstimate,
        *,
        cached_count: int | None,
    ) -> None:
        self.session_label.setText(session.name)
        if cached_count is None:
            self.availability_label.setText("Checking spectrogram availability…")
        else:
            self.availability_label.setText(
                f"{cached_count:,} of {session.eligible_candidate_count:,} spectrograms available"
            )
        self.output_value.setText(format_output_estimate(estimate.expected_final) or "Unknown")
        self.peak_value.setText(
            "Unknown" if estimate.peak_bytes is None else format_binary_size(estimate.peak_bytes)
        )
        free = estimate.volumes[0].free_bytes
        self.free_value.setText("Unknown" if free is None else format_binary_size(free))
        self.progress.setRange(0, max(1, session.eligible_candidate_count))
        self.progress.setValue(0 if cached_count is None else cached_count)

    def set_running(self, running: bool) -> None:
        self.generate_button.setVisible(not running)
        self.cancel_button.setVisible(running)
        self.retry_button.setVisible(False)
        if not running:
            self.progress_label.clear()

    def set_progress(self, completed: int, total: int) -> None:
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(completed)
        self.progress_label.setText(f"Generating spectrograms: {completed:,} of {total:,}")

    def set_stopped(self, *, failed: bool = False) -> None:
        self.set_running(False)
        self.progress_label.setText(
            "Couldn't generate this spectrogram. Retry." if failed else "Generation stopped."
        )
        self.retry_button.setVisible(failed)


class ReviewExportPage(QScrollArea):
    back_requested = Signal()
    prepare_requested = Signal(object, object)
    publish_requested = Signal()
    cancel_requested = Signal()
    show_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.plan: ReviewExportPlan | None = None
        self.estimate: StorageEstimate | None = None
        self.receipt: ReviewExportReceipt | None = None
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAccessibleName("Review corpus export")
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(32, 28, 32, 36)
        outer.setSpacing(18)

        header = QHBoxLayout()
        header.addWidget(Text("Export", role="title"))
        header.addStretch()
        self.back_button = Button("Back to Review", variant="outline")
        header.addWidget(self.back_button)
        outer.addLayout(header)
        self.session_label = QLabel()
        self.session_label.setAccessibleName("Finalized Review session")
        outer.addWidget(self.session_label)

        card = Card()
        card.content_layout.addWidget(Text("Format", role="heading"))
        self.mode = QComboBox()
        self.mode.setAccessibleName("Corpus export format")
        self.mode.addItem("Individual WAV files", ReviewExportMode.INDIVIDUAL.value)
        self.mode.addItem("Combined WAV + Raven TSV", ReviewExportMode.COMBINED.value)
        self.mode.addItem("Both", ReviewExportMode.BOTH.value)
        card.content_layout.addWidget(self.mode)
        format_help = HelpHint(
            (
                "Individual files preserve each included detection separately. Combined output "
                "also creates one WAV and a Raven selection table and requires matching mono "
                "recordings."
            ),
            subject="Export format",
        )
        card.content_layout.addWidget(format_help)
        card.content_layout.addWidget(Text("Destination", role="heading"))
        destination_row = QHBoxLayout()
        self.destination = QLineEdit()
        self.destination.setReadOnly(True)
        self.destination.setAccessibleName("Corpus export destination")
        self.choose_button = Button("Choose folder", variant="outline")
        destination_row.addWidget(self.destination, 1)
        destination_row.addWidget(self.choose_button)
        card.content_layout.addLayout(destination_row)
        outer.addWidget(card)

        self.estimate_label = QLabel()
        self.estimate_label.setWordWrap(True)
        self.estimate_label.setAccessibleName("Export storage estimate")
        outer.addWidget(self.estimate_label)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("Export status")
        outer.addWidget(self.status_label)

        actions = QHBoxLayout()
        actions.addStretch()
        self.prepare_button = Button("Check export", variant="primary")
        self.publish_button = Button("Export", variant="primary")
        self.cancel_button = Button("Cancel", variant="outline")
        self.show_button = Button("Show in folder", variant="outline")
        actions.addWidget(self.prepare_button)
        actions.addWidget(self.publish_button)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.show_button)
        outer.addLayout(actions)
        outer.addStretch()
        self.setWidget(content)

        self.publish_button.hide()
        self.cancel_button.hide()
        self.show_button.hide()
        self.back_button.clicked.connect(self.back_requested)
        self.choose_button.clicked.connect(self._choose_destination)
        self.prepare_button.clicked.connect(self._prepare)
        self.publish_button.clicked.connect(self.publish_requested)
        self.cancel_button.clicked.connect(self.cancel_requested)
        self.show_button.clicked.connect(self.show_requested)
        self.mode.currentIndexChanged.connect(self.reset_plan)

    def set_session(self, session: ReviewSession) -> None:
        self.session_label.setText(
            f"{session.name} · {session.call_count + session.unreviewed_count:,} included · "
            f"{session.not_call_count:,} excluded"
        )
        self.reset_plan()

    def _choose_destination(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Choose export destination")
        if selected:
            self.destination.setText(str(Path(selected)))
            self.reset_plan()

    def _prepare(self) -> None:
        if not self.destination.text():
            self.status_label.setText("Choose a destination folder.")
            return
        self.set_running(True, "Checking source files and storage…")
        self.prepare_requested.emit(
            ReviewExportMode(self.mode.currentData()), Path(self.destination.text())
        )

    def reset_plan(self) -> None:
        self.plan = None
        self.estimate = None
        self.receipt = None
        self.estimate_label.clear()
        self.status_label.clear()
        self.prepare_button.show()
        self.publish_button.hide()
        self.cancel_button.hide()
        self.show_button.hide()

    def set_running(self, running: bool, message: str = "") -> None:
        self.mode.setEnabled(not running)
        self.choose_button.setEnabled(not running)
        self.back_button.setEnabled(not running)
        self.prepare_button.setVisible(not running and self.plan is None)
        self.publish_button.setVisible(not running and self.plan is not None)
        self.cancel_button.setVisible(running)
        if message:
            self.status_label.setText(message)

    def set_prepared(self, plan: ReviewExportPlan, estimate: StorageEstimate) -> None:
        self.plan = plan
        self.estimate = estimate
        self.receipt = None
        self.set_running(False)
        self.estimate_label.setText(
            f"{plan.included_count:,} detections · "
            f"{format_output_estimate(estimate.expected_final)} · {estimate.reason}"
        )
        self.status_label.setText("Ready to export." if estimate.can_start else estimate.reason)
        self.publish_button.setEnabled(estimate.can_start)

    def set_failed(self, message: str) -> None:
        self.plan = None
        self.estimate = None
        self.set_running(False)
        self.status_label.setText(message)

    def set_completed(self, receipt: ReviewExportReceipt, message: str) -> None:
        self.receipt = receipt
        self.set_running(False)
        self.prepare_button.hide()
        self.publish_button.hide()
        self.status_label.setText(message)
        self.show_button.show()


class _ReviewExportPrepareThread(QThread):
    prepared = Signal(object, object)
    failed = Signal(str)

    def __init__(
        self,
        controller: ReviewSessionController,
        session_id: str,
        source_root: Path,
        destination: Path,
        mode: ReviewExportMode,
    ):
        super().__init__()
        self.controller = controller
        self.session_id = session_id
        self.source_root = source_root
        self.destination = destination
        self.mode = mode
        self.cancel_event = threading.Event()

    def run(self) -> None:
        try:
            plan = self.controller.plan_export(
                self.session_id,
                source_root=self.source_root,
                destination_parent=self.destination,
                mode=self.mode,
                cancel_requested=self.cancel_event,
            )
            estimate = self.controller.estimate_export_storage(plan)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self.failed.emit(str(exc) or "Couldn't prepare this export.")
            return
        self.prepared.emit(plan, estimate)


class _ReviewExportPublishThread(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        controller: ReviewSessionController,
        plan: ReviewExportPlan,
        source_root: Path,
        storage_digest: str,
        confirm_storage: bool,
    ):
        super().__init__()
        self.controller = controller
        self.plan = plan
        self.source_root = source_root
        self.storage_digest = storage_digest
        self.confirm_storage = confirm_storage
        self.cancel_event = threading.Event()

    def run(self) -> None:
        try:
            outcome = self.controller.publish_export(
                self.plan,
                source_root=self.source_root,
                storage_input_digest=self.storage_digest,
                confirm_storage=self.confirm_storage,
                cancel_requested=self.cancel_event,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self.failed.emit(str(exc) or "Couldn't complete this export.")
            return
        self.succeeded.emit(outcome)


class ReviewWorkspacePage(QStackedWidget):
    return_requested = Signal()
    generation_prepared = Signal(object, object, int)
    generation_prepare_failed = Signal(str)
    settings_change_prepared = Signal(object, object, object, int)

    def __init__(
        self,
        controller: ReviewSessionController,
        *,
        result_provider: Callable[[], tuple[ReviewResultChoice, ...]] | None = None,
        source_root_resolver: Callable[[ReviewSession], Path | None] | None = None,
        operation_admission: Callable[[str, str], None] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setMinimumSize(520, 480)
        self.controller = controller
        self.result_provider = result_provider or (lambda: ())
        self.source_root_resolver = source_root_resolver or (lambda _session: None)
        self.operation_admission = operation_admission
        self.current_state: ReviewViewState | None = None
        self.compact = False
        self._shortcuts: list[QShortcut] = []
        self._shortcut_dialog: QMessageBox | None = None
        self._current_content_key: str | None = None
        self.cache = SpectrogramCache(
            controller.store.root / "cache" / "spectrograms",
            limit_bytes=512 * 1024 * 1024,
        )
        self.supervisor = SpectrogramGenerationSupervisor(
            self.cache,
            token_is_current=lambda token: session_token_is_current(self.controller, token),
        )
        self._generation_batch_id: str | None = None
        self._generation_prepare_cancel = threading.Event()
        self._generation_prepare_thread: threading.Thread | None = None
        self._pending_generation_plan: ReviewCacheSizePlan | None = None
        self._pending_generation_estimate: StorageEstimate | None = None
        self._pending_settings_snapshot = None
        self._generation_confirm_dialog: QMessageBox | None = None
        self._settings_change_dialog: QMessageBox | None = None
        self._settings_return_to_cache = False
        self._export_prepare_thread: _ReviewExportPrepareThread | None = None
        self._export_publish_thread: _ReviewExportPublishThread | None = None
        self._owned_operation: tuple[str, str] | None = None
        self._shutdown_complete = False
        self.playback = QtMediaPlayback(self)

        self.landing_page = ReviewLandingPage(controller)
        self.session_page = ReviewSessionPage()
        self.cache_page = ReviewSpectrogramsPage()
        self.settings_page = SpectrogramSettingsPage(controller)
        self.export_page = ReviewExportPage()
        self.addWidget(self.landing_page)
        self.addWidget(self.session_page)
        self.addWidget(self.cache_page)
        self.addWidget(self.settings_page)
        self.addWidget(self.export_page)

        self.landing_page.start_requested.connect(self._start_session)
        self.landing_page.session_requested.connect(self._session_selected)
        self.landing_page.successor_requested.connect(self._continue_in_new_session)
        self.landing_page.settings_requested.connect(self.show_settings)
        self.settings_page.back_requested.connect(self._settings_back)
        self.settings_page.use_in_session_requested.connect(self._save_and_use_preset)
        self.cache_page.back_requested.connect(self.show_session)
        self.cache_page.settings_requested.connect(self.show_settings)
        self.cache_page.generate_requested.connect(self._prepare_generate_all)
        self.cache_page.retry_requested.connect(self._prepare_generate_all)
        self.cache_page.cancel_requested.connect(self._cancel_generation)
        self.cache_page.clear_requested.connect(self._clear_all_spectrograms)
        self.cache_page.preset_change_requested.connect(self._prepare_preset_change)
        self.session_page.view_requested.connect(self._set_view)
        self.session_page.filter_requested.connect(self._set_filter)
        self.session_page.sort_requested.connect(self._set_sort)
        self.session_page.search_requested.connect(self._set_search)
        self.session_page.label_requested.connect(self._set_label)
        self.session_page.previous_requested.connect(self._previous)
        self.session_page.next_requested.connect(self._next)
        self.session_page.play_requested.connect(self._toggle_playback)
        self.session_page.undo_requested.connect(self._undo)
        self.session_page.accept_all_requested.connect(self._accept_all)
        self.session_page.close_requested.connect(self._close_session)
        self.session_page.finalize_requested.connect(self._finalize)
        self.session_page.export_requested.connect(self.show_export)
        self.session_page.rename_requested.connect(self._rename)
        self.session_page.shortcuts_requested.connect(self._show_shortcuts)
        self.session_page.clear_requested.connect(self._clear_current_spectrogram)
        self.session_page.clear_selection_requested.connect(self._clear_selected_spectrograms)
        self.session_page.settings_requested.connect(self.show_spectrograms)
        self.export_page.back_requested.connect(self.show_session)
        self.export_page.prepare_requested.connect(self._prepare_export)
        self.export_page.publish_requested.connect(self._publish_export)
        self.export_page.cancel_requested.connect(self._cancel_export)
        self.export_page.show_requested.connect(self._show_export_in_folder)
        self.session_page.gallery.doubleClicked.connect(self._open_gallery_index)
        self.session_page.table.doubleClicked.connect(self._open_table_index)
        self.playback.position_changed.connect(self._playback_position)
        self.playback.duration_changed.connect(self._playback_duration)
        self.playback.playing_changed.connect(self._playback_playing)
        self.playback.failure.connect(
            lambda _detail: self._set_detail_error("Couldn't play this recording.")
        )
        self.generation_prepared.connect(self._generation_ready)
        self.generation_prepare_failed.connect(self._generation_failed)
        self.settings_change_prepared.connect(self._settings_change_ready)
        self._generation_timer = QTimer(self)
        self._generation_timer.setInterval(100)
        self._generation_timer.timeout.connect(self._poll_generation)
        self.session_page.seek.sliderMoved.connect(self.playback.set_position)
        self._add_shortcuts()
        self.show_landing()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(520, 480)

    def _add_shortcuts(self) -> None:
        bindings = (
            ("F",),
            ("D",),
            ("S",),
            ("J", "Left"),
            ("K", "Space"),
            ("L", "Right"),
        )
        for sequences in bindings:
            for sequence in sequences:
                shortcut = QShortcut(QKeySequence(sequence), self.session_page)
                shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
                shortcut.setAutoRepeat(False)
                shortcut.activated.connect(lambda value=sequence: self._shortcut_triggered(value))
                self._shortcuts.append(shortcut)
        undo = QShortcut(QKeySequence(QKeySequence.StandardKey.Undo), self.session_page)
        undo.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        undo.setAutoRepeat(False)
        undo.activated.connect(lambda: self._shortcut_triggered("UNDO"))
        self._shortcuts.append(undo)

    def _focus_kind(self) -> str:
        focus = QApplication.focusWidget()
        if isinstance(focus, QLineEdit):
            return "line_edit"
        if isinstance(focus, (QTextEdit, QPlainTextEdit)):
            return "text_edit"
        if isinstance(focus, QComboBox):
            return "combo"
        if isinstance(focus, QAbstractSpinBox):
            return "spin"
        if isinstance(focus, QAbstractSlider):
            return "slider"
        return "button"

    def _shortcut_triggered(self, sequence: str) -> None:
        state = self.current_state
        if state is None:
            return
        modifiers = frozenset()
        key = sequence
        if sequence == "UNDO":
            key = "Z"
            modifiers = frozenset({"META" if QApplication.platformName() == "cocoa" else "CTRL"})
        action = shortcut_action(
            key,
            modifiers=modifiers,
            focus_kind=self._focus_kind(),
            view=state.view,
            session_state=state.session.state,
            auto_repeat=False,
            modal_open=QApplication.activeModalWidget() is not None,
        )
        if action is None:
            return
        {
            ReviewShortcutAction.CALL: lambda: self._set_label(ReviewLabel.CALL.value),
            ReviewShortcutAction.NOT_CALL: lambda: self._set_label(ReviewLabel.NOT_CALL.value),
            ReviewShortcutAction.CLEAR_LABEL: lambda: self._set_label(ReviewLabel.UNREVIEWED.value),
            ReviewShortcutAction.PREVIOUS: self._previous,
            ReviewShortcutAction.PLAY_PAUSE: self._toggle_playback,
            ReviewShortcutAction.NEXT: self._next,
            ReviewShortcutAction.UNDO: self._undo,
        }[action]()

    def show_landing(self) -> None:
        if self.current_state is not None:
            self._persist_view()
        self.landing_page.refresh(tuple(self.result_provider()))
        self.setCurrentWidget(self.landing_page)
        self.landing_page.results.setFocus()

    def show_settings(self) -> None:
        if self.current_state is not None:
            self._persist_view()
        self._settings_return_to_cache = self.currentWidget() is self.cache_page
        selected_id = None
        if self.current_state is not None:
            selected_id = self.controller.store.load_settings(
                self.current_state.session.session_id
            ).preset_id
        self.settings_page.reload(select_id=selected_id)
        self.setCurrentWidget(self.settings_page)
        self.settings_page.back_button.setFocus()

    def _settings_back(self) -> None:
        if self.current_state is None:
            self.show_landing()
        elif self._settings_return_to_cache:
            self.show_spectrograms()
        else:
            self.show_session()

    def show_spectrograms(self) -> None:
        state = self.current_state
        if state is None:
            self.show_landing()
            return
        try:
            snapshot = self.controller.store.load_settings(state.session.session_id)
            plan = plan_review_cache_generation(
                missing_count=state.session.eligible_candidate_count,
                existing_file_sizes=(),
                tier=SpectrogramImageTier.THUMBNAIL,
                settings_digest=snapshot.settings_digest,
                calibration=None,
            )
            estimate = assess_review_cache_storage(plan, cache_root=self.cache.root)
        except (OSError, RuntimeError, TypeError, ValueError):
            self._message("Spectrograms", "Couldn't check spectrogram storage. Try again.")
            return
        self.cache_page.set_estimate(state.session, plan, estimate, cached_count=None)
        self.cache_page.set_presets(
            self.controller.list_presets(),
            current_preset_id=snapshot.preset_id,
            editable=state.session.state is ReviewSessionState.OPEN,
        )
        self.cache_page.set_running(self._generation_batch_id is not None)
        self.setCurrentWidget(self.cache_page)
        self.cache_page.generate_button.setFocus()

    def show_export(self) -> None:
        state = self.current_state
        if state is None or state.session.state is not ReviewSessionState.FINALIZED:
            return
        self.export_page.set_session(state.session)
        self.setCurrentWidget(self.export_page)
        self.export_page.choose_button.setFocus()

    def _prepare_export(self, mode: ReviewExportMode, destination: Path) -> None:
        state = self.current_state
        if (
            state is None
            or state.session.state is not ReviewSessionState.FINALIZED
            or self._export_prepare_thread is not None
            or self._export_publish_thread is not None
        ):
            self.export_page.set_failed("Only a Finalized Review session can be exported.")
            return
        source_root = self.source_root_resolver(state.session)
        if source_root is None:
            self.export_page.set_failed(
                "The original recordings are unavailable. Relink them before exporting."
            )
            return
        thread = _ReviewExportPrepareThread(
            self.controller,
            state.session.session_id,
            Path(source_root),
            Path(destination),
            ReviewExportMode(mode),
        )
        self._export_prepare_thread = thread
        thread.prepared.connect(self._export_prepared)
        thread.failed.connect(self._export_failed)

        def finished() -> None:
            if self._export_prepare_thread is thread:
                self._export_prepare_thread = None
            thread.deleteLater()

        thread.finished.connect(finished)
        thread.start()

    def _export_prepared(self, plan: ReviewExportPlan, estimate: StorageEstimate) -> None:
        state = self.current_state
        if state is None or plan.session_id != state.session.session_id:
            self.export_page.set_failed("The selected Review session changed. Check again.")
            return
        self.export_page.set_prepared(plan, estimate)

    def _publish_export(self) -> None:
        state = self.current_state
        plan = self.export_page.plan
        estimate = self.export_page.estimate
        if (
            state is None
            or plan is None
            or estimate is None
            or not estimate.can_start
            or self._export_publish_thread is not None
        ):
            return
        source_root = self.source_root_resolver(state.session)
        if source_root is None:
            self.export_page.set_failed(
                "The original recordings are unavailable. Relink them before exporting."
            )
            return
        confirmed = False
        if estimate.requires_confirmation:
            answer = QMessageBox.question(
                self,
                "Export storage",
                estimate.reason,
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok,
                QMessageBox.StandardButton.Cancel,
            )
            if answer is not QMessageBox.StandardButton.Ok:
                return
            confirmed = True
        try:
            operation_id = self._begin_owned_operation("Review corpus export")
        except (RuntimeError, ValueError) as exc:
            self.export_page.set_failed(str(exc))
            return
        thread = _ReviewExportPublishThread(
            self.controller,
            plan,
            Path(source_root),
            estimate.input_digest,
            confirmed,
        )
        self._export_publish_thread = thread
        self.export_page.set_running(True, "Writing and verifying the finalized Review session…")
        thread.succeeded.connect(self._export_succeeded)
        thread.failed.connect(self._export_failed)

        def finished() -> None:
            if self._export_publish_thread is thread:
                self._export_publish_thread = None
            self._release_owned_operation(operation_id)
            thread.deleteLater()

        thread.finished.connect(finished)
        thread.start()

    def _export_succeeded(self, outcome) -> None:
        message = "Export complete." if outcome.history_saved else outcome.message
        self.export_page.set_completed(outcome.receipt, message)

    def _export_failed(self, message: str) -> None:
        if "cancel" in message.casefold():
            message = "Export cancelled. No new output was published."
        self.export_page.set_failed(message or "Couldn't complete this export.")

    def _cancel_export(self) -> None:
        if self._export_prepare_thread is not None:
            self._export_prepare_thread.cancel_event.set()
        if self._export_publish_thread is not None:
            self._export_publish_thread.cancel_event.set()
        self.export_page.status_label.setText("Cancelling before publication…")

    def _show_export_in_folder(self) -> None:
        receipt = self.export_page.receipt
        if receipt is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(receipt.final_destination))

    def _prepare_preset_change(self, preset_id: str) -> None:
        state = self.current_state
        if state is None or state.session.state is not ReviewSessionState.OPEN:
            return
        if self._generation_batch_id is not None:
            return
        if (
            self._generation_prepare_thread is not None
            and self._generation_prepare_thread.is_alive()
        ):
            return
        try:
            current = self.controller.store.load_settings(state.session.session_id)
            target = next(
                preset for preset in self.controller.list_presets() if preset.preset_id == preset_id
            )
            if current == target:
                return
            settings = SpectrogramSettings.from_mapping(target.effective_settings)
        except (OSError, RuntimeError, StopIteration, TypeError, ValueError):
            self.cache_page.set_stopped(failed=True)
            return
        session = state.session
        self._generation_prepare_cancel = threading.Event()
        cancel_event = self._generation_prepare_cancel
        self._pending_settings_snapshot = target
        self.cache_page.set_running(True)
        self.cache_page.progress_label.setText("Checking spectrogram availability…")

        def prepare() -> None:
            try:
                valid_keys = set(self.cache.valid_content_keys())
                existing_sizes: list[int] = []
                offset = 0
                while offset < session.eligible_candidate_count:
                    if cancel_event.is_set():
                        self.generation_prepare_failed.emit("Generation stopped.")
                        return
                    rows = self.controller.store.candidate_page(
                        session.session_id, offset=offset, limit=1_000
                    )
                    if not rows:
                        break
                    for row in rows:
                        context = plan_candidate_context(
                            self._eligible(row), context_seconds=settings.context_seconds
                        )
                        request = SpectrogramRenderRequest.from_snapshot(
                            candidate_id=row.candidate_id,
                            source_sha256=row.source_sha256,
                            context=context,
                            snapshot=target,
                            tier=SpectrogramImageTier.THUMBNAIL,
                        )
                        key = spectrogram_content_key(request)
                        if key in valid_keys:
                            entry = self.cache.lookup(key)
                            if entry is not None:
                                existing_sizes.append(entry.size_bytes)
                    offset += len(rows)
                plan = plan_review_cache_generation(
                    missing_count=session.eligible_candidate_count - len(existing_sizes),
                    existing_file_sizes=existing_sizes,
                    tier=SpectrogramImageTier.THUMBNAIL,
                    settings_digest=target.settings_digest,
                    calibration=None,
                )
                estimate = assess_review_cache_storage(plan, cache_root=self.cache.root)
            except (OSError, RuntimeError, TypeError, ValueError):
                self.generation_prepare_failed.emit("Couldn't generate this spectrogram. Retry.")
                return
            if cancel_event.is_set():
                self.generation_prepare_failed.emit("Generation stopped.")
                return
            self.settings_change_prepared.emit(target, plan, estimate, len(existing_sizes))

        self._generation_prepare_thread = threading.Thread(
            target=prepare,
            name="biocall-review-settings-preflight",
            daemon=True,
        )
        self._generation_prepare_thread.start()

    def _save_and_use_preset(self, snapshot) -> None:
        state = self.current_state
        if state is None or state.session.state is not ReviewSessionState.OPEN:
            return
        self.show_spectrograms()
        self._prepare_preset_change(snapshot.preset_id)

    def _settings_change_ready(
        self,
        target,
        plan: ReviewCacheSizePlan,
        estimate: StorageEstimate,
        cached_count: int,
    ) -> None:
        self._generation_prepare_thread = None
        state = self.current_state
        if state is None or self._pending_settings_snapshot != target:
            self.cache_page.set_running(False)
            return
        current = self.controller.store.load_settings(state.session.session_id)
        self.cache_page.set_estimate(state.session, plan, estimate, cached_count=cached_count)
        if not estimate.can_start:
            self.cache_page.set_running(False)
            self.cache_page.progress_label.setText(
                "Not enough free space. Clear some spectrograms or free up disk space."
                if estimate.decision is StorageDecision.INSUFFICIENT
                else estimate.reason
            )
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Change preset")
        dialog.setText(
            f"Change {current.preset_name} to {target.preset_name}? "
            f"{plan.missing_count:,} spectrograms will need to be generated. "
            "Your labels won't change."
        )
        cancel = dialog.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        change = dialog.addButton("Change preset", QMessageBox.ButtonRole.AcceptRole)
        dialog.setDefaultButton(cancel)
        dialog.setEscapeButton(cancel)
        self._settings_change_dialog = dialog

        def finished(_result: int) -> None:
            confirmed = dialog.clickedButton() is change
            self._settings_change_dialog = None
            dialog.deleteLater()
            if not confirmed or self.current_state is not state:
                self._pending_settings_snapshot = None
                self.cache_page.set_running(False)
                return
            try:
                changed = change_session_settings_with_preflight(
                    self.controller,
                    self.supervisor,
                    state.session.session_id,
                    target,
                    plan,
                    expected_revision=state.session.revision,
                    expected_settings_epoch=state.session.settings_epoch,
                    changed_at=_now(),
                    confirmed_change=True,
                    confirmed_storage=estimate.requires_confirmation,
                )
            except (OSError, RuntimeError, TypeError, ValueError):
                self._pending_settings_snapshot = None
                self.cache_page.set_stopped(failed=True)
                return
            self._pending_settings_snapshot = None
            state.session = changed.session
            self.table_model.refresh()
            self.gallery_model.refresh()
            self.show_spectrograms()

        dialog.finished.connect(finished)
        dialog.open()

    def _prepare_generate_all(self) -> None:
        state = self.current_state
        if state is None or self._generation_batch_id is not None:
            return
        if (
            self._generation_prepare_thread is not None
            and self._generation_prepare_thread.is_alive()
        ):
            return
        try:
            session = self.controller.store.get_session(state.session.session_id)
            snapshot = self.controller.store.load_settings(session.session_id)
            settings = SpectrogramSettings.from_mapping(snapshot.effective_settings)
        except (OSError, RuntimeError, TypeError, ValueError):
            self.cache_page.set_stopped(failed=True)
            return
        self._generation_prepare_cancel = threading.Event()
        cancel_event = self._generation_prepare_cancel
        self.cache_page.set_running(True)
        self.cache_page.progress_label.setText("Checking spectrogram availability…")

        def prepare() -> None:
            try:
                valid_keys = set(self.cache.valid_content_keys())
                existing_sizes: list[int] = []
                offset = 0
                while offset < session.eligible_candidate_count:
                    if cancel_event.is_set():
                        self.generation_prepare_failed.emit("Generation stopped.")
                        return
                    rows = self.controller.store.candidate_page(
                        session.session_id, offset=offset, limit=1_000
                    )
                    if not rows:
                        break
                    for row in rows:
                        context = plan_candidate_context(
                            self._eligible(row), context_seconds=settings.context_seconds
                        )
                        request = SpectrogramRenderRequest.from_snapshot(
                            candidate_id=row.candidate_id,
                            source_sha256=row.source_sha256,
                            context=context,
                            snapshot=snapshot,
                            tier=SpectrogramImageTier.THUMBNAIL,
                        )
                        key = spectrogram_content_key(request)
                        if key in valid_keys:
                            entry = self.cache.lookup(key)
                            if entry is not None:
                                existing_sizes.append(entry.size_bytes)
                    offset += len(rows)
                missing = session.eligible_candidate_count - len(existing_sizes)
                plan = plan_review_cache_generation(
                    missing_count=missing,
                    existing_file_sizes=existing_sizes,
                    tier=SpectrogramImageTier.THUMBNAIL,
                    settings_digest=snapshot.settings_digest,
                    calibration=None,
                )
                estimate = assess_review_cache_storage(plan, cache_root=self.cache.root)
            except (OSError, RuntimeError, TypeError, ValueError):
                self.generation_prepare_failed.emit("Couldn't generate this spectrogram. Retry.")
                return
            if cancel_event.is_set():
                self.generation_prepare_failed.emit("Generation stopped.")
                return
            self.generation_prepared.emit(plan, estimate, len(existing_sizes))

        self._generation_prepare_thread = threading.Thread(
            target=prepare,
            name="biocall-review-cache-preflight",
            daemon=True,
        )
        self._generation_prepare_thread.start()

    def _generation_ready(
        self,
        plan: ReviewCacheSizePlan,
        estimate: StorageEstimate,
        cached_count: int,
    ) -> None:
        self._generation_prepare_thread = None
        state = self.current_state
        if state is None:
            self.cache_page.set_running(False)
            return
        self._pending_generation_plan = plan
        self._pending_generation_estimate = estimate
        self.cache_page.set_estimate(state.session, plan, estimate, cached_count=cached_count)
        if plan.missing_count == 0:
            self.cache_page.set_running(False)
            return
        if not estimate.can_start:
            self.cache_page.set_running(False)
            if estimate.decision is StorageDecision.INSUFFICIENT:
                self.cache_page.progress_label.setText(
                    "Not enough free space. Clear some spectrograms or free up disk space."
                )
            else:
                self.cache_page.progress_label.setText(estimate.reason)
            return
        if estimate.requires_confirmation:
            dialog = QMessageBox(self)
            dialog.setWindowTitle("Storage")
            dialog.setIcon(QMessageBox.Icon.Warning)
            dialog.setText(estimate.reason)
            cancel = dialog.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            proceed = dialog.addButton("Continue", QMessageBox.ButtonRole.AcceptRole)
            dialog.setDefaultButton(cancel)
            dialog.setEscapeButton(cancel)
            self._generation_confirm_dialog = dialog

            def finished(_result: int) -> None:
                confirmed = dialog.clickedButton() is proceed
                self._generation_confirm_dialog = None
                dialog.deleteLater()
                if confirmed:
                    self._start_generation(confirmed=True)
                else:
                    self.cache_page.set_running(False)

            dialog.finished.connect(finished)
            dialog.open()
            return
        self._start_generation(confirmed=False)

    def _generation_failed(self, message: str) -> None:
        self._generation_prepare_thread = None
        self._pending_settings_snapshot = None
        self.cache_page.set_running(False)
        if message == "Generation stopped.":
            self.cache_page.set_stopped()
        else:
            self.cache_page.set_stopped(failed=True)

    def _generation_jobs(
        self,
        session: ReviewSession,
        snapshot,
        source_root: Path,
    ):
        settings = SpectrogramSettings.from_mapping(snapshot.effective_settings)
        token_base = {
            "session_id": session.session_id,
            "settings_epoch": session.settings_epoch,
            "settings_digest": snapshot.settings_digest,
        }
        identity_cache = SourceIdentityCache()
        offset = 0
        while offset < session.eligible_candidate_count:
            rows = self.controller.store.candidate_page(
                session.session_id, offset=offset, limit=1_000
            )
            if not rows:
                return
            for row in rows:
                candidate = self._eligible(row)
                context = plan_candidate_context(
                    candidate, context_seconds=settings.context_seconds
                )
                request = SpectrogramRenderRequest.from_snapshot(
                    candidate_id=row.candidate_id,
                    source_sha256=row.source_sha256,
                    context=context,
                    snapshot=snapshot,
                    tier=SpectrogramImageTier.THUMBNAIL,
                )

                def render(
                    cancelled,
                    *,
                    candidate=candidate,
                    request=request,
                    context_seconds=settings.context_seconds,
                ):
                    if cancelled():
                        raise GenerationCancelled("Spectrogram generation was cancelled.")
                    audio = read_candidate_audio(
                        source_root,
                        candidate,
                        context_seconds=context_seconds,
                        cancelled=cancelled,
                        identity_cache=identity_cache,
                    )
                    if cancelled():
                        raise GenerationCancelled("Spectrogram generation was cancelled.")
                    return render_spectrogram(audio.samples, request)

                yield GenerationJob(
                    content_key=spectrogram_content_key(request),
                    tier=SpectrogramImageTier.THUMBNAIL,
                    priority=CachePriority.GENERATE_ALL,
                    token=GenerationToken(
                        source_sha256=row.source_sha256,
                        **token_base,
                    ),
                    render=render,
                )
            offset += len(rows)

    def _start_generation(self, *, confirmed: bool) -> None:
        state = self.current_state
        estimate = self._pending_generation_estimate
        plan = self._pending_generation_plan
        if state is None or estimate is None or plan is None:
            self.cache_page.set_running(False)
            return
        try:
            operation_id = self._begin_owned_operation("Spectrogram generation")
            session = self.controller.store.get_session(state.session.session_id)
            snapshot = self.controller.store.load_settings(session.session_id)
            source_root = self.source_root_resolver(session)
            if source_root is None:
                raise ValueError("Recording root is unavailable.")
            if (
                snapshot.settings_digest != plan.settings_digest
                or session.settings_epoch != state.session.settings_epoch
            ):
                raise ValueError("Session settings changed during generation setup.")
            estimate = assess_review_cache_storage(
                plan,
                cache_root=self.cache.root,
                expected_input_digest=plan.input_digest,
            )
            batch_id = self.supervisor.submit_bulk(
                self._generation_jobs(session, snapshot, Path(source_root)),
                storage_estimate=estimate,
                confirmed=confirmed,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            if "operation_id" in locals():
                self._release_owned_operation(operation_id)
            self.cache_page.set_stopped(failed=True)
            return
        self._generation_batch_id = batch_id
        self.cache_page.set_running(True)
        self.cache_page.set_progress(0, session.eligible_candidate_count)
        self._generation_timer.start()

    def _poll_generation(self) -> None:
        batch_id = self._generation_batch_id
        state = self.current_state
        if batch_id is None:
            self._generation_timer.stop()
            return
        try:
            progress = self.supervisor.progress(batch_id)
        except KeyError:
            self._generation_batch_id = None
            self._release_owned_operation()
            self._generation_timer.stop()
            self.cache_page.set_stopped(failed=True)
            return
        completed = progress.completed + progress.cache_hits + progress.failed + progress.cancelled
        total = state.session.eligible_candidate_count if state is not None else progress.requested
        self.cache_page.set_progress(completed, total)
        if not progress.done:
            return
        self._generation_batch_id = None
        self._release_owned_operation()
        self._generation_timer.stop()
        if progress.failed:
            self.cache_page.set_stopped(failed=True)
        elif progress.cancelled:
            self.cache_page.set_stopped()
        else:
            self.cache_page.set_running(False)
            if state is not None:
                self._prepare_generate_all()

    def _cancel_generation(self) -> None:
        self._generation_prepare_cancel.set()
        batch_id = self._generation_batch_id
        if batch_id is not None:
            try:
                self.supervisor.cancel(batch_id)
            except KeyError:
                pass

    def _clear_all_spectrograms(self) -> None:
        try:
            keys = self.cache.valid_content_keys()
            self.supervisor.clear_cache(keys)
        except (OSError, RuntimeError, TypeError, ValueError):
            self.cache_page.set_stopped(failed=True)
            return
        self._current_content_key = None
        self.session_page.spectrogram.clear_spectrogram()
        if self.current_state is not None:
            self.show_spectrograms()

    def show_session(self) -> None:
        if self.current_state is None:
            self.show_landing()
            return
        self.setCurrentWidget(self.session_page)
        self._refresh_models()
        self._render()

    def _start_session(self, choice: ReviewResultChoice, settings) -> None:
        try:
            session = self.controller.start_session(
                choice.collection_id,
                choice.result_id,
                name=None,
                settings=settings,
                created_at=_now(),
            )
        except (OSError, RuntimeError, ValueError) as exc:
            self._message("Review", str(exc))
            return
        self.open_session(session.session_id)

    def _session_selected(self, session_id: str) -> None:
        session = self.controller.store.get_session(session_id)
        if session.state is ReviewSessionState.CLOSED:
            try:
                session, _availability = self.controller.resume_session(
                    session_id,
                    expected_revision=session.revision,
                    resumed_at=_now(),
                )
            except (OSError, RuntimeError, ValueError) as exc:
                self._message("Review", str(exc))
                return
        elif session.state is ReviewSessionState.FINALIZED:
            # Read-only inspection is allowed; successor creation remains explicit on landing.
            pass
        self.open_session(session.session_id)

    def _continue_in_new_session(self, session_id: str) -> None:
        parent = self.controller.store.get_session(session_id)
        base = parent.name[:100].rstrip()
        try:
            child, _availability = self.controller.continue_in_new_session(
                session_id,
                name=f"{base} continuation",
                created_at=_now(),
            )
        except (OSError, RuntimeError, ValueError) as exc:
            self._message("Review", str(exc))
            return
        self.open_session(child.session_id)

    def open_session(self, session_id: str) -> None:
        self.current_state = ReviewViewState(self.controller, session_id)
        if (
            self.current_state.current_candidate_id is None
            and self.current_state.session.eligible_candidate_count
        ):
            first = self.controller.store.candidate_page(session_id, offset=0, limit=1)
            if first:
                self.current_state.current_candidate_id = first[0].candidate_id
        self._refresh_models()
        self.show_session()

    def _refresh_models(self) -> None:
        state = self.current_state
        if state is None:
            return
        if not hasattr(self, "table_model"):
            self.table_model = ReviewCandidateTableModel(state, self)
            self.gallery_model = ReviewGalleryModel(
                state, self, thumbnail_provider=self._gallery_thumbnail
            )
            self.session_page.table.setModel(self.table_model)
            self.session_page.gallery.setModel(self.gallery_model)
            self.session_page.table.selectionModel().selectionChanged.connect(
                lambda _selected, _deselected: self._selection_changed(self.session_page.table)
            )
            self.session_page.gallery.selectionModel().selectionChanged.connect(
                lambda _selected, _deselected: self._selection_changed(self.session_page.gallery)
            )
        else:
            self.table_model._paged.state = state
            self.gallery_model._paged.state = state
            self.table_model.refresh()
            self.gallery_model.refresh()

    def _render(self) -> None:
        state = self.current_state
        if state is None:
            return
        self.session_page.render_state(state)
        self.table_model.refresh()
        self.gallery_model.refresh()
        self.session_page.selection_label.setText(
            f"{len(state.selected_candidate_ids):,} selected"
            if state.selected_candidate_ids
            else f"{state.row_count:,} detections"
        )
        self.session_page.clear_selected_button.setEnabled(bool(state.selected_candidate_ids))
        if state.view is ReviewView.ONE_BY_ONE:
            self._load_current()

    def _set_view(self, value: str) -> None:
        state = self.current_state
        if state is None:
            return
        state.set_query(view=ReviewView(value))
        self._persist_view()
        self._render()

    def _set_filter(self, value: str) -> None:
        state = self.current_state
        if state is None:
            return
        state.set_query(filter_name=ReviewFilter(value))
        self._persist_view()
        self._render()

    def _set_sort(self, value: str) -> None:
        state = self.current_state
        if state is None or value is None:
            return
        state.set_query(sort=ReviewSort(value))
        self._persist_view()
        self._render()

    def _set_search(self, value: str) -> None:
        state = self.current_state
        if state is None:
            return
        state.set_query(search=value)
        self._persist_view()
        self.table_model.refresh()
        self.gallery_model.refresh()

    def _selection_changed(self, view: QAbstractItemView) -> None:
        state = self.current_state
        model = view.model()
        if state is None or model is None:
            return
        candidate_ids = tuple(
            dict.fromkeys(
                index.data(Qt.ItemDataRole.UserRole)
                for index in view.selectionModel().selectedRows()
                if index.data(Qt.ItemDataRole.UserRole)
            )
        )
        state.set_selection(candidate_ids[:1_000])
        self.session_page.selection_label.setText(f"{len(candidate_ids):,} selected")
        self.session_page.clear_selected_button.setEnabled(bool(candidate_ids))

    def _open_gallery_index(self, index: QModelIndex) -> None:
        self._open_candidate(index.data(Qt.ItemDataRole.UserRole))

    def _open_table_index(self, index: QModelIndex) -> None:
        self._open_candidate(index.data(Qt.ItemDataRole.UserRole))

    def _open_candidate(self, candidate_id: str | None) -> None:
        if self.current_state is None or not candidate_id:
            return
        self.current_state.set_current(candidate_id)
        self.current_state.set_query(view=ReviewView.ONE_BY_ONE)
        self._persist_view()
        self._render()

    @staticmethod
    def _eligible(row: ReviewCandidateView) -> EligibleCandidate:
        return EligibleCandidate(
            ordinal=row.ordinal,
            recording_ordinal=row.recording_ordinal,
            candidate_id=row.candidate_id,
            recording_ref=row.recording_ref,
            recording_key=row.recording_key,
            source_sha256=row.source_sha256,
            sample_rate_hz=row.sample_rate_hz,
            frame_count=row.frame_count,
            channels=row.channels,
            start_frame=row.start_frame,
            end_frame=row.end_frame,
            start_time_ns=row.start_time_ns,
            end_time_ns=row.end_time_ns,
            cnn_target_score=row.cnn_target_score,
            rf_target_score=row.rf_target_score,
            contributing_windows=row.contributing_windows,
        )

    def _gallery_thumbnail(self, row: ReviewCandidateView) -> QPixmap | None:
        state = self.current_state
        if state is None:
            return None
        try:
            snapshot = self.controller.store.load_settings(state.session.session_id)
            settings = SpectrogramSettings.from_mapping(snapshot.effective_settings)
            context = plan_candidate_context(
                self._eligible(row), context_seconds=settings.context_seconds
            )
            request = SpectrogramRenderRequest.from_snapshot(
                candidate_id=row.candidate_id,
                source_sha256=row.source_sha256,
                context=context,
                snapshot=snapshot,
                tier=SpectrogramImageTier.THUMBNAIL,
            )
            entry = self.cache.lookup(spectrogram_content_key(request))
            if entry is None:
                return None
            thumbnail = QPixmap(str(entry.path))
        except (OSError, RuntimeError, TypeError, ValueError):
            return None
        return thumbnail if not thumbnail.isNull() else None

    def _load_current(self) -> None:
        state = self.current_state
        if state is None:
            return
        row = state.current()
        if row is None:
            self.session_page.current_label.setText("No detections to review.")
            self.session_page.spectrogram.clear_spectrogram()
            return
        self.playback.stop()
        self.session_page.play_button.setEnabled(False)
        self._current_content_key = None
        position = self.controller.store.candidate_position(
            state.session.session_id, row.candidate_id, sort_name=state.sort.value
        )
        self.session_page.current_label.setText(
            f"{row.recording_name} · {row.start_time_ns / 1_000_000_000:.3f} s · "
            f"{position + 1:,} / {state.session.eligible_candidate_count:,}"
        )
        self.session_page.previous_button.setEnabled(position > 0)
        self.session_page.next_button.setEnabled(
            position + 1 < state.session.eligible_candidate_count
        )
        source_root = self.source_root_resolver(state.session)
        if source_root is None:
            self._set_detail_error("Recording not found. Relink the recordings folder to continue.")
            return
        try:
            snapshot = self.controller.store.load_settings(state.session.session_id)
            settings = SpectrogramSettings.from_mapping(snapshot.effective_settings)
            audio = read_candidate_audio(
                Path(source_root),
                self._eligible(row),
                context_seconds=settings.context_seconds,
            )
            request = SpectrogramRenderRequest.from_snapshot(
                candidate_id=row.candidate_id,
                source_sha256=row.source_sha256,
                context=audio.context,
                snapshot=snapshot,
                tier=SpectrogramImageTier.DETAIL,
            )
            raster = render_spectrogram(audio.samples, request)
            self.cache.publish(raster, settings_digest=snapshot.settings_digest)
            self._current_content_key = raster.content_key
            self.session_page.spectrogram.set_spectrogram(raster)
            self.playback.load_clip(audio.wav_bytes)
            self.session_page.play_button.setEnabled(True)
            self.session_page.detail_status.clear()
        except AudioSourceError as exc:
            message = {
                AudioSourceProblem.MISSING: (
                    "Recording not found. Relink the recordings folder to continue."
                ),
                AudioSourceProblem.CHANGED: (
                    "This recording has changed since detection. "
                    "Restore the original file to continue."
                ),
            }.get(exc.problem, "Couldn't play this recording.")
            self._set_detail_error(message)
        except (OSError, TypeError, ValueError):
            self._set_detail_error("Couldn't generate this spectrogram. Retry.")

    def _set_detail_error(self, message: str) -> None:
        self.session_page.detail_status.setText(message)
        self.session_page.spectrogram.clear_spectrogram()
        self.session_page.play_button.setEnabled(False)

    def _set_label(self, value: str) -> None:
        state = self.current_state
        if state is None or state.session.state is not ReviewSessionState.OPEN:
            return
        try:
            state.set_label(ReviewLabel(value), modified_at=_now())
        except (OSError, RuntimeError, ValueError):
            self._set_detail_error("Couldn't save your change. Try again.")
            return
        self._render()

    def _previous(self) -> None:
        if self.current_state is not None and self.current_state.previous() is not None:
            self._persist_view()
            self._render()

    def _next(self) -> None:
        if self.current_state is not None and self.current_state.next() is not None:
            self._persist_view()
            self._render()

    def _toggle_playback(self) -> None:
        if not self.session_page.play_button.isEnabled():
            return
        if self.session_page.play_button.text() == "Pause":
            self.playback.pause()
        else:
            self.playback.play()

    def _playback_position(self, milliseconds: int) -> None:
        if not self.session_page.seek.isSliderDown():
            self.session_page.seek.setValue(max(0, milliseconds))
        duration = max(0, self.session_page.seek.maximum())
        self.session_page.audio_time.setText(
            f"0:{milliseconds // 1_000:02d} / 0:{duration // 1_000:02d}"
        )

    def _playback_duration(self, milliseconds: int) -> None:
        self.session_page.seek.setRange(0, max(0, milliseconds))

    def _playback_playing(self, playing: bool) -> None:
        self.session_page.play_button.setText("Pause" if playing else "Play")

    def _undo(self) -> None:
        state = self.current_state
        if state is None or state.session.state is not ReviewSessionState.OPEN:
            return
        try:
            state.undo(modified_at=_now())
        except (OSError, RuntimeError, ValueError):
            self._set_detail_error("Couldn't save your change. Try again.")
            return
        self._render()

    def _accept_all(self) -> None:
        state = self.current_state
        if state is None or state.session.unreviewed_count == 0:
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Accept all")
        dialog.setText(
            f"Accept {state.session.unreviewed_count:,} unreviewed detections? "
            "Existing labels won't change."
        )
        cancel = dialog.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        accept = dialog.addButton("Accept all", QMessageBox.ButtonRole.AcceptRole)
        dialog.setDefaultButton(cancel)
        dialog.setEscapeButton(cancel)
        dialog.exec()
        if dialog.clickedButton() is not accept:
            return
        try:
            mutation = self.controller.accept_all(
                state.session.session_id,
                expected_revision=state.session.revision,
                modified_at=_now(),
            )
        except (OSError, RuntimeError, ValueError):
            self._set_detail_error("Couldn't save your change. Try again.")
            return
        state.session = mutation.session
        self._render()

    def _rename(self, name: str) -> None:
        state = self.current_state
        if (
            state is None
            or state.session.state is not ReviewSessionState.OPEN
            or name == state.session.name
        ):
            return
        try:
            state.session = self.controller.rename_session(
                state.session.session_id,
                name=" ".join(name.split()),
                expected_revision=state.session.revision,
                renamed_at=_now(),
            )
        except (OSError, RuntimeError, ValueError):
            self.session_page.name_input.control.setText(state.session.name)
            self._set_detail_error("Couldn't save your change. Try again.")
        self._render()

    def _close_session(self) -> None:
        state = self.current_state
        if state is None:
            return
        self._persist_view()
        try:
            state.session = self.controller.close_session(
                state.session.session_id,
                expected_revision=state.session.revision,
                closed_at=_now(),
            )
        except (OSError, RuntimeError, ValueError):
            self._set_detail_error("Couldn't save your change. Try again.")
            return
        self.current_state = None
        self.show_landing()

    def _finalize(self) -> None:
        state = self.current_state
        if state is None:
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Finalize")
        if state.session.unreviewed_count:
            dialog.setText(
                f"{state.session.unreviewed_count:,} detections haven't been reviewed. "
                "They'll be included as model detections. Finalize anyway?"
            )
        else:
            dialog.setText("Finalize this session? Further changes will require a new session.")
        cancel = dialog.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        finalize = dialog.addButton("Finalize", QMessageBox.ButtonRole.AcceptRole)
        dialog.setDefaultButton(cancel)
        dialog.setEscapeButton(cancel)
        dialog.exec()
        if dialog.clickedButton() is not finalize:
            return
        self._persist_view()
        try:
            state.session = self.controller.finalize_session(
                state.session.session_id,
                expected_revision=state.session.revision,
                finalized_at=_now(),
            )
        except (OSError, RuntimeError, ValueError):
            self._set_detail_error("Couldn't save your change. Try again.")
            return
        self._render()

    def _clear_current_spectrogram(self) -> None:
        state = self.current_state
        if state is not None and state.current_candidate_id is not None:
            self._clear_candidate_spectrograms((state.current_candidate_id,))
        self.session_page.spectrogram.clear_spectrogram()

    def _clear_selected_spectrograms(self) -> None:
        state = self.current_state
        if state is None or not state.selected_candidate_ids:
            return
        self._clear_candidate_spectrograms(state.selected_candidate_ids)

    def _clear_candidate_spectrograms(self, candidate_ids: tuple[str, ...]) -> None:
        state = self.current_state
        if state is None:
            return
        try:
            snapshot = self.controller.store.load_settings(state.session.session_id)
            settings = SpectrogramSettings.from_mapping(snapshot.effective_settings)
            keys: list[str] = []
            for candidate_id in candidate_ids:
                row = self.controller.store.candidate_by_id(state.session.session_id, candidate_id)
                context = plan_candidate_context(
                    self._eligible(row), context_seconds=settings.context_seconds
                )
                for tier in (
                    SpectrogramImageTier.THUMBNAIL,
                    SpectrogramImageTier.DETAIL,
                ):
                    request = SpectrogramRenderRequest.from_snapshot(
                        candidate_id=row.candidate_id,
                        source_sha256=row.source_sha256,
                        context=context,
                        snapshot=snapshot,
                        tier=tier,
                    )
                    keys.append(spectrogram_content_key(request))
            self.supervisor.clear_cache(keys)
        except (OSError, RuntimeError, TypeError, ValueError):
            self._set_detail_error("Couldn't generate this spectrogram. Retry.")
            return
        self._current_content_key = None
        self.gallery_model.refresh()

    def _show_shortcuts(self) -> None:
        if self._shortcut_dialog is not None:
            self._shortcut_dialog.raise_()
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Keyboard shortcuts")
        dialog.setText(
            "F — Call\nD — Not a call\nS — Clear label\n"
            "J or ← — Previous\nK or Space — Play / Pause\nL or → — Next\n"
            "Ctrl/⌘+Z — Undo"
        )
        close = dialog.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(close)
        dialog.setEscapeButton(close)
        self._shortcut_dialog = dialog
        dialog.finished.connect(self._shortcut_dialog_finished)
        dialog.open()
        close.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def _shortcut_dialog_finished(self, _result: int) -> None:
        dialog = self._shortcut_dialog
        self._shortcut_dialog = None
        if dialog is not None:
            dialog.deleteLater()

    def _persist_view(self) -> None:
        state = self.current_state
        if state is None or state.session.state is not ReviewSessionState.OPEN:
            return
        try:
            state.save_position()
        except (OSError, RuntimeError, ValueError):
            # View state is non-scientific; keep the committed labels/session authoritative.
            pass

    @staticmethod
    def _message(title: str, text: str) -> None:
        QMessageBox.warning(QApplication.activeWindow(), title, text)

    def focus_initial(self) -> None:
        if self.currentWidget() is self.session_page:
            self.session_page.view_buttons[ReviewView.GALLERY].setFocus()
        elif self.currentWidget() is self.export_page:
            self.export_page.choose_button.setFocus()
        else:
            self.landing_page.results.setFocus()

    @property
    def has_open_session(self) -> bool:
        return self.controller.store.open_session() is not None

    @property
    def active_operation(self) -> tuple[str, str] | None:
        return self._owned_operation

    def _begin_owned_operation(self, label: str) -> str:
        if self._owned_operation is not None:
            raise RuntimeError("Review work is already active.")
        operation_id = f"review_{uuid.uuid4().hex}"
        if self.operation_admission is not None:
            self.operation_admission(operation_id, label)
        self._owned_operation = (operation_id, label)
        return operation_id

    def _release_owned_operation(self, operation_id: str | None = None) -> None:
        active = self._owned_operation
        if active is None or (operation_id is not None and active[0] != operation_id):
            return
        self._owned_operation = None

    def request_exit_stop(self) -> None:
        """Request cancellation without closing or mutating the Open session."""
        self._generation_prepare_cancel.set()
        self._cancel_generation()
        self._cancel_export()

    @property
    def exit_stop_ready(self) -> bool:
        preparation_running = (
            self._generation_prepare_thread is not None
            and self._generation_prepare_thread.is_alive()
        )
        export_running = any(
            thread is not None and thread.isRunning()
            for thread in (self._export_prepare_thread, self._export_publish_thread)
        )
        generation_running = (
            self._generation_batch_id is not None
            or self.supervisor.pending_count > 0
            or self.supervisor.active_count > 0
        )
        ready = not preparation_running and not export_running and not generation_running
        if ready:
            self._release_owned_operation()
        return ready

    def checkpoint_open_session_for_exit(self) -> ReviewSession | None:
        """Persist the current view and durably Close the one Open session."""
        opened = self.controller.store.open_session()
        if opened is None:
            return None
        state = self.current_state
        if state is not None and state.session.session_id == opened.session_id:
            state.save_position()
        latest = self.controller.store.get_session(opened.session_id)
        closed = self.controller.close_session(
            latest.session_id,
            expected_revision=latest.revision,
            closed_at=_now(),
        )
        if state is not None and state.session.session_id == closed.session_id:
            state.session = closed
        return closed

    def leave_workspace(self) -> None:
        self._persist_view()
        self.playback.stop()

    def shutdown(self) -> None:
        if self._shutdown_complete:
            return
        self._generation_prepare_cancel.set()
        for export_thread in (
            self._export_prepare_thread,
            self._export_publish_thread,
        ):
            if export_thread is not None and export_thread.isRunning():
                export_thread.cancel_event.set()
                export_thread.wait(5_000)
        self._generation_timer.stop()
        thread = self._generation_prepare_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)
        self.supervisor.shutdown(wait=True)
        self.playback.close()
        self._shutdown_complete = True

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        compact = event.size().width() < 900
        if compact != self.compact:
            self.compact = compact
            self.session_page.set_compact(compact)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.shutdown()
        super().closeEvent(event)


__all__ = ["ReviewResultChoice", "ReviewWorkspacePage"]
