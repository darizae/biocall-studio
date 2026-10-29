"""Native, metadata-only exploration of persisted ST-07 Detection Results."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from alp_ui.components import (
    Alert,
    Badge,
    Button,
    Card,
    DataTable,
    EmptyState,
    FolderPicker,
    HelpHint,
    SelectInput,
    Text,
)
from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSignalBlocker,
    Qt,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from biocall_studio.detect.controller import DetectWorkspaceController, ModelIntakeState
from biocall_studio.detect.result_views import (
    CandidateViewRow,
    RecordingViewRow,
    ResultContentState,
    ResultHistoryItem,
    ResultSourceState,
    ResultViewProjection,
)
from biocall_studio.detect.results import FileOutcomeStatus
from biocall_studio.detect.rf_refinement import DerivedResult, RefinementStatus


def _source_time(nanoseconds: int) -> str:
    milliseconds = nanoseconds // 1_000_000
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def _duration(recording: RecordingViewRow) -> str:
    seconds = recording.frame_count / recording.sample_rate_hz
    hours, remainder = divmod(int(seconds), 3_600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _completed_label(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except (TypeError, ValueError):
        return value
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


class RecordingResultModel(QAbstractTableModel):
    HEADERS = ("RECORDING", "OUTCOME", "CANDIDATES", "DURATION")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.recordings: tuple[RecordingViewRow, ...] = ()

    def set_projection(self, projection: ResultViewProjection | None) -> None:
        self.beginResetModel()
        self.recordings = () if projection is None else projection.recordings
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.recordings)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.recordings):
            return None
        recording = self.recordings[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return recording.recording_id
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        outcome = (
            "File error"
            if recording.outcome is FileOutcomeStatus.FAILED
            else ("None found" if not recording.candidates else "Completed")
        )
        values = (
            Path(recording.source_relative_name).name,
            outcome,
            "—" if recording.outcome is FileOutcomeStatus.FAILED else len(recording.candidates),
            _duration(recording),
        )
        return values[index.column()]

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def recording_at(self, row: int) -> RecordingViewRow | None:
        return self.recordings[row] if 0 <= row < len(self.recordings) else None

    def row_for_id(self, recording_id: str) -> int:
        for row, recording in enumerate(self.recordings):
            if recording.recording_id == recording_id:
                return row
        raise KeyError(recording_id)


class CandidateResultModel(QAbstractTableModel):
    ORIGINAL_HEADERS = ("SELECT", "START", "END", "DETECTION SCORE")
    REFINED_HEADERS = (*ORIGINAL_HEADERS, "REFINEMENT")

    def __init__(
        self,
        parent=None,
        *,
        page_size: int = 200,
        selection_changed: Callable[[str, bool], None],
    ):
        super().__init__(parent)
        self._page_size = page_size
        self._selection_changed = selection_changed
        self._candidates: tuple[CandidateViewRow, ...] = ()
        self._selected_ids: frozenset[str] = frozenset()
        self._visible = 0
        self.refinement_visible = False

    @property
    def headers(self) -> tuple[str, ...]:
        return self.REFINED_HEADERS if self.refinement_visible else self.ORIGINAL_HEADERS

    @property
    def visible_candidates(self) -> tuple[CandidateViewRow, ...]:
        return self._candidates[: self._visible]

    def set_recording(
        self,
        recording: RecordingViewRow | None,
        selected_ids: tuple[str, ...],
        *,
        refined: bool | None = None,
    ) -> None:
        self.beginResetModel()
        self._candidates = () if recording is None else recording.candidates
        self.refinement_visible = (
            any(candidate.refinement_status is not None for candidate in self._candidates)
            if refined is None
            else refined
        )
        self._selected_ids = frozenset(selected_ids)
        self._visible = min(self._page_size, len(self._candidates))
        self.endResetModel()

    def set_selected_ids(self, selected_ids: tuple[str, ...]) -> None:
        next_ids = frozenset(selected_ids)
        if next_ids == self._selected_ids:
            return
        self._selected_ids = next_ids
        if self._visible:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self._visible - 1, 0),
                [Qt.ItemDataRole.CheckStateRole],
            )

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else self._visible

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= self._visible:
            return None
        candidate = self._candidates[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return candidate.candidate_id
        if role == Qt.ItemDataRole.CheckStateRole and index.column() == 0:
            return (
                Qt.CheckState.Checked
                if candidate.candidate_id in self._selected_ids
                else Qt.CheckState.Unchecked
            )
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        values = (
            "",
            _source_time(candidate.start_time_ns),
            _source_time(candidate.end_time_ns),
            f"{candidate.max_target_score:.3f}",
            self._refinement_label(candidate),
        )
        return values[index.column()]

    @staticmethod
    def _refinement_label(candidate: CandidateViewRow) -> str:
        if candidate.refinement_status is RefinementStatus.ACCEPTED:
            return "Accepted"
        if candidate.refinement_status is RefinementStatus.REJECTED:
            return "Rejected"
        if candidate.refinement_status is RefinementStatus.UNSCORED:
            return "Could not assess"
        return ""

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):  # noqa: N802
        if (
            not index.isValid()
            or index.row() >= self._visible
            or index.column() != 0
            or role != Qt.ItemDataRole.CheckStateRole
        ):
            return False
        candidate = self._candidates[index.row()]
        selected = Qt.CheckState(value) is Qt.CheckState.Checked
        self._selection_changed(candidate.candidate_id, selected)
        self._selected_ids = (
            self._selected_ids | {candidate.candidate_id}
            if selected
            else self._selected_ids - {candidate.candidate_id}
        )
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
        return True

    def flags(self, index: QModelIndex):
        flags = super().flags(index)
        if index.isValid() and index.column() == 0:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
        return None

    def canFetchMore(self, parent: QModelIndex = QModelIndex()) -> bool:  # noqa: N802
        return not parent.isValid() and self._visible < len(self._candidates)

    def fetchMore(self, parent: QModelIndex = QModelIndex()) -> None:  # noqa: N802
        if parent.isValid() or not self.canFetchMore(parent):
            return
        count = min(self._page_size, len(self._candidates) - self._visible)
        self.beginInsertRows(QModelIndex(), self._visible, self._visible + count - 1)
        self._visible += count
        self.endInsertRows()

    def candidate_at(self, row: int) -> CandidateViewRow | None:
        return self._candidates[row] if 0 <= row < self._visible else None

    def row_for_id(self, candidate_id: str) -> int:
        for row, candidate in enumerate(self._candidates):
            if candidate.candidate_id == candidate_id:
                while row >= self._visible and self.canFetchMore():
                    self.fetchMore()
                return row
        raise KeyError(candidate_id)


class ResultExplorer(QWidget):
    run_requested = Signal()
    recordings_requested = Signal()
    export_requested = Signal()

    def __init__(self, controller: DetectWorkspaceController):
        super().__init__()
        self.controller = controller
        self._compact = False
        self._recording_by_result: dict[str, str] = {}
        self._candidate_by_recording: dict[tuple[str, str], str] = {}
        self.current_state_key = "no-results"
        self.state_title = QLabel()
        self.selected_recording_id: str | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        self.history_card = self._build_history_card()
        outer.addWidget(self.history_card)
        self.state_stack = QStackedWidget()
        self.state_stack.setMinimumWidth(0)
        self.alerts = {
            "available": Alert(
                "Candidate intervals retain their original recording positions.",
                title="Original Result",
                intent="info",
            ),
            "partial": Alert(
                "Successful recordings remain available; file errors are reported separately.",
                title="Completed with file errors",
                intent="warning",
            ),
            "empty": Alert(
                "This completed Result has no candidate intervals. Recording outcomes and "
                "provenance remain available.",
                title="Completed with no candidates",
                intent="success",
            ),
            "stale": Alert(
                "Candidate metadata is preserved, but source navigation is disabled until the "
                "recording inventory is checked again.",
                title="Recordings changed after this Result",
                intent="warning",
            ),
            "source-unavailable": Alert(
                "Candidate metadata is preserved, but the recordings folder must be relinked "
                "before source navigation is available.",
                title="Recordings folder unavailable",
                intent="danger",
            ),
        }
        for alert in self.alerts.values():
            self.state_stack.addWidget(alert)
        outer.addWidget(self.state_stack)

        self.no_results_button = Button("View Run details", variant="primary")
        self.no_results_button.clicked.connect(self.run_requested)
        self.no_results_state = EmptyState(
            "No Results yet",
            text="Complete candidate detection to create an immutable metadata-only Result.",
            action=self.no_results_button,
        )
        self.no_results_state.layout().setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter
        )
        self.result_error_button = Button("View Run details", variant="primary")
        self.result_error_button.clicked.connect(self.run_requested)
        self.result_error_state = EmptyState(
            "Result unavailable",
            text="The published Result is missing, changed, or corrupt. It is not shown as an "
            "empty successful Result.",
            action=self.result_error_button,
        )
        self.result_error_state.layout().setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter
        )
        self.content_stack = QStackedWidget()
        self.content_stack.setMinimumWidth(0)
        self.content_stack.addWidget(self.no_results_state)
        self.content_stack.addWidget(self.result_error_state)
        self.result_content = self._build_result_content()
        self.content_stack.addWidget(self.result_content)
        outer.addWidget(self.content_stack)

        footer = QHBoxLayout()
        self.run_details_button = Button("Run details", variant="outline")
        self.run_details_button.clicked.connect(self.run_requested)
        footer.addWidget(self.run_details_button)
        self.review_recordings_button = Button("Review recordings", variant="outline")
        self.review_recordings_button.clicked.connect(self.recordings_requested)
        footer.addWidget(self.review_recordings_button)
        self.export_button = Button("Plan corpus export", variant="primary")
        self.export_button.setAccessibleName("Plan export from selected Result intervals")
        self.export_button.clicked.connect(self.export_requested)
        footer.addWidget(self.export_button)
        footer.addStretch()
        outer.addLayout(footer)

        self.render()

    def _build_history_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Result history")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QGridLayout()
        copy = QVBoxLayout()
        copy.addWidget(Text("RESULT HISTORY", role="overline"))
        copy.addWidget(Text("Original candidate Results", role="heading"))
        copy.addWidget(
            Text(
                "Each completed Run publishes a separate immutable Result.",
                role="body",
                word_wrap=True,
            )
        )
        layout.addLayout(copy, 0, 0)
        self.history_select = SelectInput(label="Result")
        self.history_select.setAccessibleName("Result history")
        self.history_select.currentIndexChanged.connect(self._history_changed)
        layout.addWidget(self.history_select, 0, 1)
        layout.setColumnStretch(0, 1)
        card.content_layout.addLayout(layout)
        self.history_layout = layout
        self.history_copy = copy
        return card

    def _build_result_content(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        self.provenance_card = Card()
        self.provenance_card.setAccessibleName("Result lineage and provenance")
        provenance_heading = QHBoxLayout()
        provenance_heading.addWidget(Text("Result lineage", role="heading"))
        provenance_heading.addWidget(
            HelpHint(
                "A Result is immutable. Candidate selections are saved separately and never "
                "change its intervals, scores, or provenance.",
                subject="Result lineage",
            )
        )
        provenance_heading.addStretch()
        self.provenance_badge = Badge("Original", intent="neutral")
        provenance_heading.addWidget(self.provenance_badge)
        self.provenance_card.content_layout.addLayout(provenance_heading)
        self.lineage_label = Text("", role="subheading", word_wrap=True)
        self.provenance_card.content_layout.addWidget(self.lineage_label)
        self.provenance_grid = QGridLayout()
        self.provenance_values: dict[str, QLabel] = {}
        for row, (key, label) in enumerate(
            (
                ("completed", "Completed"),
                ("inventory", "Source inventory"),
                ("intervals", "Intervals"),
                ("files", "Recording outcomes"),
                ("metadata", "Metadata"),
                ("parent", "Parent"),
            )
        ):
            name = QLabel(label)
            name.setStyleSheet("font-weight: 600;")
            value = QLabel("—")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByKeyboard)
            self.provenance_grid.addWidget(name, row, 0, Qt.AlignmentFlag.AlignTop)
            self.provenance_grid.addWidget(value, row, 1)
            self.provenance_values[key] = value
        self.provenance_grid.setColumnStretch(1, 1)
        self.provenance_card.content_layout.addLayout(self.provenance_grid)
        layout.addWidget(self.provenance_card)

        self.results_layout = QGridLayout()
        self.results_layout.setHorizontalSpacing(16)
        self.results_layout.setVerticalSpacing(16)
        self.recording_card = self._build_recording_card()
        self.candidate_card = self._build_candidate_card()
        self.results_layout.addWidget(self.recording_card, 0, 0)
        self.results_layout.addWidget(self.candidate_card, 0, 1)
        self.results_layout.setColumnStretch(0, 2)
        self.results_layout.setColumnStretch(1, 3)
        layout.addLayout(self.results_layout)
        self.refinement_card = self._build_refinement_card()
        layout.addWidget(self.refinement_card)
        return content

    def _build_refinement_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Optional RF candidate refinement")
        heading = QHBoxLayout()
        copy = QVBoxLayout()
        copy.addWidget(Text("OPTIONAL REFINEMENT", role="overline"))
        copy.addWidget(
            Text("Refine candidate intervals with another model", role="heading")
        )
        copy.addWidget(
            Text(
                "Creates a separate metadata-only Result. The original remains selectable "
                "and unchanged.",
                role="body",
                word_wrap=True,
            )
        )
        heading.addLayout(copy, 1)
        heading.addWidget(
            HelpHint(
                "A compatible Random Forest (RF) Model evaluates only the candidate "
                "intervals in the selected original Result. Accepted means its target score "
                "meets the Model's saved threshold; Rejected means it does not; Could not "
                "assess reports a specific feature or duration reason.",
                subject="RF refinement",
            ),
            0,
            Qt.AlignmentFlag.AlignTop,
        )
        self.refinement_status_badge = Badge("Not selected", intent="neutral")
        heading.addWidget(self.refinement_status_badge, 0, Qt.AlignmentFlag.AlignTop)
        card.content_layout.addLayout(heading)

        self.refinement_picker = FolderPicker(
            label="Train RF Model folder", show_hidden=True
        )
        self.refinement_picker.setAccessibleDescription(
            "Choose a trusted Random Forest Model to assess existing candidate intervals."
        )
        self.refinement_picker.folderChanged.connect(
            self.controller.choose_refinement_model_root
        )
        card.content_layout.addWidget(self.refinement_picker)
        self.refinement_model_detail = Text("", role="body", word_wrap=True)
        card.content_layout.addWidget(self.refinement_model_detail)

        actions = QHBoxLayout()
        self.clear_refinement_model_button = Button("Clear RF Model", variant="outline")
        self.clear_refinement_model_button.clicked.connect(
            self.controller.clear_refinement_model_selection
        )
        actions.addWidget(self.clear_refinement_model_button)
        actions.addStretch()
        self.refinement_button = Button("Create refined Result", variant="primary")
        self.refinement_button.clicked.connect(self._start_refinement)
        actions.addWidget(self.refinement_button)
        card.content_layout.addLayout(actions)
        return card

    def _start_refinement(self) -> None:
        try:
            self.controller.start_refinement()
        except (OSError, RuntimeError, ValueError) as exc:
            self.refinement_model_detail.setText(str(exc))
            return
        self.run_requested.emit()

    def _build_recording_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Result recordings")
        card.content_layout.addWidget(Text("Recordings", role="heading"))
        card.content_layout.addWidget(
            Text(
                "Choose a recording to inspect its source-time candidate intervals.",
                role="body",
                word_wrap=True,
            )
        )
        self.recording_model = RecordingResultModel(self)
        self.recording_table = DataTable(model=self.recording_model)
        self.recording_table.setAccessibleName("Result recordings")
        self.recording_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.recording_table.setMinimumHeight(230)
        self.recording_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for column in range(1, len(self.recording_model.HEADERS)):
            self.recording_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        self.recording_table.selectionModel().currentRowChanged.connect(
            self._recording_changed
        )
        card.content_layout.addWidget(self.recording_table)
        return card

    def _build_candidate_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Candidate intervals")
        heading = QHBoxLayout()
        labels = QVBoxLayout()
        self.recording_title = Text("Choose a recording", role="heading", word_wrap=True)
        labels.addWidget(self.recording_title)
        self.recording_subtitle = Text(
            "Times in the original source recording", role="body", word_wrap=True
        )
        labels.addWidget(self.recording_subtitle)
        heading.addLayout(labels, 1)
        self.show_source_button = Button("Show source", variant="outline", size="small")
        self.show_source_button.clicked.connect(self._show_source)
        heading.addWidget(self.show_source_button, 0, Qt.AlignmentFlag.AlignTop)
        card.content_layout.addLayout(heading)

        selection_row = QHBoxLayout()
        self.selection_summary = Text("0 selected in this Result", role="body")
        selection_row.addWidget(self.selection_summary)
        selection_row.addWidget(
            HelpHint(
                "Selections are saved only for this Result. Changing Results never copies or "
                "overwrites another Result's selection.",
                subject="Result selection",
            )
        )
        selection_row.addStretch()
        card.content_layout.addLayout(selection_row)
        self.selection_message = QLabel()
        self.selection_message.setWordWrap(True)
        self.selection_message.setAccessibleName("Result selection status")
        self.selection_message.setStyleSheet("color: #92400E; font-weight: 600;")
        card.content_layout.addWidget(self.selection_message)

        self.candidate_model = CandidateResultModel(
            self,
            selection_changed=self.controller.set_candidate_selected,
        )
        self.candidate_table = DataTable(model=self.candidate_model)
        self.candidate_table.setAccessibleName("Candidate intervals in original source time")
        self.candidate_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.candidate_table.setMinimumHeight(230)
        for column in range(len(self.candidate_model.ORIGINAL_HEADERS)):
            self.candidate_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        self.candidate_table.selectionModel().currentRowChanged.connect(
            self._candidate_changed
        )
        self.candidate_empty = EmptyState(
            "No candidates in this recording",
            text="The recording completed successfully and no intervals met the Run settings.",
        )
        self.candidate_error = EmptyState(
            "Recording could not be analyzed",
            text="This file error is preserved separately from a successful zero-candidate "
            "recording.",
        )
        self.candidate_stack = QStackedWidget()
        self.candidate_stack.setMinimumWidth(0)
        self.candidate_stack.addWidget(self.candidate_table)
        self.candidate_stack.addWidget(self.candidate_empty)
        self.candidate_stack.addWidget(self.candidate_error)
        card.content_layout.addWidget(self.candidate_stack)

        detail = QGridLayout()
        detail.addWidget(Text("Selected interval", role="subheading"), 0, 0, 1, 2)
        self.candidate_detail_id = QLabel("—")
        self.candidate_detail_time = QLabel("—")
        self.candidate_detail_frames = QLabel("—")
        self.candidate_detail_score = QLabel("—")
        for row, (label, value) in enumerate(
            (
                ("Candidate ID", self.candidate_detail_id),
                ("Source time", self.candidate_detail_time),
                ("Source frames", self.candidate_detail_frames),
                ("Detection score", self.candidate_detail_score),
            ),
            start=1,
        ):
            name = QLabel(label)
            name.setStyleSheet("font-weight: 600;")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByKeyboard)
            detail.addWidget(name, row, 0, Qt.AlignmentFlag.AlignTop)
            detail.addWidget(value, row, 1)
        self.candidate_detail_refinement_label = QLabel("Refinement")
        self.candidate_detail_refinement_label.setStyleSheet("font-weight: 600;")
        self.candidate_detail_refinement = QLabel("—")
        self.candidate_detail_refinement.setWordWrap(True)
        self.candidate_detail_refinement.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        detail.addWidget(
            self.candidate_detail_refinement_label,
            5,
            0,
            Qt.AlignmentFlag.AlignTop,
        )
        detail.addWidget(self.candidate_detail_refinement, 5, 1)
        detail.setColumnStretch(1, 1)
        card.content_layout.addLayout(detail)
        return card

    def _history_changed(self, index: int) -> None:
        if index < 0:
            return
        result_id = self.history_select.model().index(index, 0).data(Qt.ItemDataRole.UserRole)
        if isinstance(result_id, str):
            self.controller.select_result(result_id)

    def _recording_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        recording = self.recording_model.recording_at(current.row())
        if recording is None:
            self.selected_recording_id = None
            self._render_recording(None)
            return
        self.selected_recording_id = recording.recording_id
        result_id = self.controller.selected_result_id
        if result_id is not None:
            self._recording_by_result[result_id] = recording.recording_id
        self._render_recording(recording)

    def _candidate_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        candidate = self.candidate_model.candidate_at(current.row())
        if candidate is not None:
            result_id = self.controller.selected_result_id
            if result_id is not None and self.selected_recording_id is not None:
                self._candidate_by_recording[
                    (result_id, self.selected_recording_id)
                ] = candidate.candidate_id
        self._render_candidate_detail(candidate)

    def _render_candidate_detail(self, candidate: CandidateViewRow | None) -> None:
        if candidate is None:
            values = ("—", "—", "—", "—")
        else:
            values = (
                candidate.candidate_id,
                f"{_source_time(candidate.start_time_ns)} – "
                f"{_source_time(candidate.end_time_ns)}",
                f"[{candidate.start_frame:,}, {candidate.end_frame:,})",
                f"{candidate.max_target_score:.6f} · "
                f"{candidate.contributing_windows} contributing window"
                f"{'s' if candidate.contributing_windows != 1 else ''}",
            )
        for widget, value in zip(
            (
                self.candidate_detail_id,
                self.candidate_detail_time,
                self.candidate_detail_frames,
                self.candidate_detail_score,
            ),
            values,
            strict=True,
        ):
            widget.setText(value)
        refined = candidate is not None and candidate.refinement_status is not None
        self.candidate_detail_refinement_label.setVisible(refined)
        self.candidate_detail_refinement.setVisible(refined)
        if not refined or candidate is None:
            self.candidate_detail_refinement.setText("—")
        elif candidate.refinement_status is RefinementStatus.UNSCORED:
            reason = {
                "short_segment": "the interval is shorter than this Model can assess",
                "feature_extraction_failed": "acoustic features could not be calculated",
                "non_finite_features": "calculated features were not finite",
            }.get(candidate.unscored_reason, "the interval could not be assessed")
            self.candidate_detail_refinement.setText(f"Could not assess · {reason}")
        else:
            projection = self.controller.selected_result_projection
            threshold = None if projection is None else projection.threshold
            status = (
                "Accepted"
                if candidate.refinement_status is RefinementStatus.ACCEPTED
                else "Rejected"
            )
            self.candidate_detail_refinement.setText(
                f"{status} · target score {candidate.rf_target_score:.6f} · "
                f"saved threshold {threshold:.6f}"
            )

    def _render_recording(self, recording: RecordingViewRow | None) -> None:
        selection = self.controller.result_selection
        selected_ids = () if selection is None else selection.candidate_ids
        projection = self.controller.selected_result_projection
        self.candidate_model.set_recording(
            recording,
            selected_ids,
            refined=projection is not None and projection.result_kind == "derived",
        )
        if self.candidate_model.refinement_visible:
            self.candidate_table.horizontalHeader().setSectionResizeMode(
                4, QHeaderView.ResizeMode.ResizeToContents
            )
        if recording is None:
            self.recording_title.setText("Choose a recording")
            self.candidate_stack.setCurrentWidget(self.candidate_empty)
            self.show_source_button.setEnabled(False)
            self._render_candidate_detail(None)
            return
        self.recording_title.setText(recording.source_relative_name)
        self.show_source_button.setEnabled(
            recording.outcome is FileOutcomeStatus.SUCCEEDED
            and projection is not None
            and projection.source_navigation_enabled
        )
        if recording.outcome is FileOutcomeStatus.FAILED:
            error_text = {
                "audio_decode_failed": "Audio could not be read during detection.",
                "inference_failed": "Candidate detection failed for this recording.",
                "unsupported_output": "The detector returned an unsupported output.",
            }.get(recording.error_code, "This recording failed during detection.")
            self.candidate_error.text_widget.setText(error_text)
            self.candidate_stack.setCurrentWidget(self.candidate_error)
            self._render_candidate_detail(None)
            return
        if not recording.candidates:
            self.candidate_stack.setCurrentWidget(self.candidate_empty)
            self._render_candidate_detail(None)
            return
        self.candidate_stack.setCurrentWidget(self.candidate_table)
        result_id = self.controller.selected_result_id
        candidate_id = (
            self._candidate_by_recording.get((result_id, recording.recording_id))
            if result_id is not None
            else None
        )
        try:
            row = 0 if candidate_id is None else self.candidate_model.row_for_id(candidate_id)
        except KeyError:
            row = 0
        self.candidate_table.setCurrentIndex(self.candidate_model.index(row, 0))
        self._render_candidate_detail(self.candidate_model.candidate_at(row))

    def _show_source(self) -> None:
        if self.selected_recording_id is None:
            return
        try:
            path = self.controller.selected_source_path(self.selected_recording_id)
        except (OSError, ValueError) as exc:
            self.selection_message.setText(str(exc))
            self.show_source_button.setEnabled(False)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

    def _history_label(self, item: ResultHistoryItem) -> str:
        if item.result is None:
            return f"Unavailable Result · {_completed_label(item.created_at)}"
        count = item.result.candidate_count
        if isinstance(item.result, DerivedResult):
            return (
                f"Refined Result · {_completed_label(item.result.completed_at)} · "
                f"{item.result.accepted_count:,} accepted · "
                f"{item.result.rejected_count:,} rejected · "
                f"{item.result.unscored_count:,} could not assess"
            )
        return (
            f"Original Result · {_completed_label(item.result.completed_at)} · "
            f"{count:,} candidate{'s' if count != 1 else ''}"
        )

    def _render_history(self) -> None:
        with QSignalBlocker(self.history_select.control):
            self.history_select.control.clear()
            selected_index = -1
            for index, item in enumerate(self.controller.result_history):
                self.history_select.addItem(self._history_label(item), item.result_id)
                if item.result_id == self.controller.selected_result_id:
                    selected_index = index
            self.history_select.setCurrentIndex(selected_index)
        self.history_select.setEnabled(bool(self.controller.result_history))

    def _render_refinement_controls(
        self, projection: ResultViewProjection | None
    ) -> None:
        state = self.controller.refinement_model_state
        status = {
            ModelIntakeState.EMPTY: "Not selected",
            ModelIntakeState.LOADING: "Checking",
            ModelIntakeState.COMPATIBLE: "Compatible",
            ModelIntakeState.INCOMPATIBLE: "Incompatible",
            ModelIntakeState.MISSING: "Missing files",
        }[state]
        self.refinement_status_badge.setText(status)
        self.refinement_status_badge.setAccessibleName(f"RF Model status: {status}")
        selected = self.controller.selected_refinement_model_root
        if state is not ModelIntakeState.LOADING:
            self.refinement_picker.setFolderPath(
                "" if selected is None else str(selected)
            )
        self.refinement_picker.setEnabled(
            state is not ModelIntakeState.LOADING and not self.controller.is_run_active
        )
        self.clear_refinement_model_button.setEnabled(
            selected is not None
            and state is not ModelIntakeState.LOADING
            and not self.controller.is_run_active
        )
        detail = self.controller.refinement_model_reason
        if projection is not None and projection.result_kind == "derived":
            detail = (
                "This is a refined Result. Select its original parent to create another "
                "independent refinement."
            )
        elif projection is not None and projection.candidate_count == 0:
            detail = "This original Result has no candidate intervals to refine."
        self.refinement_model_detail.setText(detail)
        self.refinement_button.setEnabled(self.controller.can_refine_selected_result)

    def _set_state(self, key: str) -> None:
        self.current_state_key = key
        self.state_stack.setVisible(key in self.alerts)
        if key in self.alerts:
            alert = self.alerts[key]
            self.state_stack.setCurrentWidget(alert)
            self.state_title = alert.title_widget
        elif key == "result-error":
            self.state_title = self.result_error_state.title_widget
        else:
            self.state_title = self.no_results_state.title_widget

    def render(self) -> None:
        self.export_button.setEnabled(False)
        self._render_history()
        item = self.controller.selected_result_item
        projection = self.controller.selected_result_projection
        self._render_refinement_controls(projection)
        if item is None:
            self._set_state("no-results")
            self.content_stack.setCurrentWidget(self.no_results_state)
            self.provenance_card.setVisible(False)
            return
        if item.result is None or projection is None:
            self._set_state("result-error")
            self.result_error_state.text_widget.setText(item.message)
            self.content_stack.setCurrentWidget(self.result_error_state)
            self.provenance_card.setVisible(False)
            return

        state_key = "available"
        if projection.source_state is ResultSourceState.UNAVAILABLE:
            state_key = "source-unavailable"
        elif projection.source_state is ResultSourceState.STALE:
            state_key = "stale"
        elif projection.content_state is ResultContentState.PARTIAL:
            state_key = "partial"
        elif projection.content_state is ResultContentState.EMPTY:
            state_key = "empty"
        self._set_state(state_key)
        self.content_stack.setCurrentWidget(self.result_content)
        self.provenance_card.setVisible(True)
        refined = projection.result_kind == "derived"
        self.provenance_badge.setText("Refined" if refined else "Original")
        self.alerts["available"].title_widget.setText(
            "Refined Result" if refined else "Original Result"
        )
        self.alerts["available"].text_widget.setText(
            "Each candidate retains its original recording position and explicit RF "
            "assessment."
            if refined
            else "Candidate intervals retain their original recording positions."
        )
        self.lineage_label.setText(
            f"Parent Result · {projection.parent_result_id}  →  RF Model · "
            f"{projection.model_id}  →  Result · {projection.result_id}"
            if refined
            else f"Detection Model · {projection.model_id}  →  Result · "
            f"{projection.result_id}"
        )
        self.provenance_values["completed"].setText(
            _completed_label(projection.completed_at)
        )
        self.provenance_values["inventory"].setText(
            f"{projection.inventory_id} · frozen for this Run"
        )
        self.provenance_values["intervals"].setText(
            f"{projection.candidate_count:,} candidate intervals · "
            f"{projection.accepted_count:,} accepted · "
            f"{projection.rejected_count:,} rejected · "
            f"{projection.unscored_count:,} could not assess · digest "
            f"{projection.result_digest}"
            if refined
            else f"{projection.candidate_count:,} candidate intervals · digest "
            f"{projection.result_digest}"
        )
        self.provenance_values["files"].setText(
            f"{projection.successful_files:,} completed · "
            f"{projection.failed_files:,} file errors"
        )
        self.provenance_values["metadata"].setText(
            "App-owned Result; source audio unchanged"
        )
        self.provenance_values["parent"].setText(
            f"{projection.parent_result_id} · digest {projection.parent_result_digest}"
            if refined
            else "None · original Result"
        )
        selection = self.controller.result_selection
        selected_ids = () if selection is None else selection.candidate_ids
        revision = 0 if selection is None else selection.selection_revision
        self.selection_summary.setText(
            f"{len(selected_ids):,} selected in this Result · selection revision {revision}"
        )
        self.export_button.setEnabled(
            bool(selected_ids)
            and projection.source_state is ResultSourceState.AVAILABLE
            and not self.controller.is_export_active
        )
        self.selection_message.setText(
            self.controller.selection_error or self.controller.selection_notice
        )
        self.selection_message.setVisible(bool(self.selection_message.text()))
        self.recording_model.set_projection(projection)
        result_id = projection.result_id
        recording_id = self._recording_by_result.get(result_id)
        try:
            row = 0 if recording_id is None else self.recording_model.row_for_id(recording_id)
        except KeyError:
            row = 0
        if self.recording_model.rowCount():
            self.recording_table.setCurrentIndex(self.recording_model.index(row, 0))
            recording = self.recording_model.recording_at(row)
            self.selected_recording_id = None if recording is None else recording.recording_id
            if recording is not None:
                self._recording_by_result[result_id] = recording.recording_id
            self._render_recording(recording)
        else:
            self.selected_recording_id = None
            self._render_recording(None)

    def set_compact(self, compact: bool) -> None:
        if compact == self._compact:
            return
        self._compact = compact
        self.history_layout.removeItem(self.history_copy)
        self.history_layout.removeWidget(self.history_select)
        self.results_layout.removeWidget(self.recording_card)
        self.results_layout.removeWidget(self.candidate_card)
        if compact:
            self.history_layout.addLayout(self.history_copy, 0, 0)
            self.history_layout.addWidget(self.history_select, 1, 0)
            self.results_layout.addWidget(self.recording_card, 0, 0)
            self.results_layout.addWidget(self.candidate_card, 1, 0)
            self.results_layout.setColumnStretch(0, 1)
            self.results_layout.setColumnStretch(1, 0)
        else:
            self.history_layout.addLayout(self.history_copy, 0, 0)
            self.history_layout.addWidget(self.history_select, 0, 1)
            self.results_layout.addWidget(self.recording_card, 0, 0)
            self.results_layout.addWidget(self.candidate_card, 0, 1)
            self.results_layout.setColumnStretch(0, 2)
            self.results_layout.setColumnStretch(1, 3)
        for layout in (self.history_layout, self.results_layout):
            layout.invalidate()
            layout.activate()
        self.updateGeometry()

    def focus_initial(self) -> None:
        if self.controller.result_history:
            self.history_select.control.setFocus()
        else:
            self.no_results_button.setFocus()


__all__ = ["CandidateResultModel", "RecordingResultModel", "ResultExplorer"]
