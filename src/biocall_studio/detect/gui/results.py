"""Native, metadata-only exploration of persisted ST-07 Detection Results."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from alp_ui.components import (
    Badge,
    Button,
    Card,
    DataTable,
    EmptyState,
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

from biocall_studio.detect.application.controller import DetectWorkspaceController, ModelIntakeState
from biocall_studio.detect.domain.result_views import (
    CandidateViewRow,
    RecordingViewRow,
    ResultContentState,
    ResultHistoryItem,
    ResultSourceState,
    ResultViewProjection,
)
from biocall_studio.detect.domain.results import FileOutcomeStatus
from biocall_studio.detect.domain.rf_refinement import DerivedResult, RefinementStatus
from biocall_studio.detect.gui.storage import StorageSection, confirm_storage


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
    ORIGINAL_HEADERS = ("START", "END", "DETECTION SCORE")
    REFINED_HEADERS = (*ORIGINAL_HEADERS, "REFINEMENT")

    def __init__(self, parent=None, *, page_size: int = 200):
        super().__init__(parent)
        self._page_size = page_size
        self._candidates: tuple[CandidateViewRow, ...] = ()
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
        self._visible = min(self._page_size, len(self._candidates))
        self.endResetModel()

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
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        values = (
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
    models_requested = Signal()

    def __init__(self, controller: DetectWorkspaceController):
        super().__init__()
        self.controller = controller
        self._compact = False
        self._recording_by_result: dict[str, str] = {}
        self._candidate_by_recording: dict[tuple[str, str], str] = {}
        self.current_state_key = "no-results"
        self.state_title = QLabel()
        self.selected_recording_id: str | None = None
        self.storage_estimate = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        self.history_card = self._build_history_card()
        outer.addWidget(self.history_card)
        self.state_row = QWidget()
        self.state_row.setAccessibleName("Result availability")
        state_layout = QHBoxLayout(self.state_row)
        state_layout.setContentsMargins(0, 0, 0, 0)
        self.state_badge = Badge("", intent="neutral")
        self.state_badge.setAccessibleName("Result availability status")
        state_layout.addWidget(self.state_badge)
        state_layout.addStretch()
        self.state_action = Button("", variant="outline", size="small")
        self.state_action.clicked.connect(self._state_action_requested)
        self.state_action.hide()
        state_layout.addWidget(self.state_action)
        self.state_row.hide()
        outer.addWidget(self.state_row)

        self.no_results_state = EmptyState(
            "No Results yet",
            text="Run detection to create results for Review.",
        )
        self.no_results_state.layout().setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter
        )
        self.result_error_state = EmptyState(
            "Result unavailable",
            text="This result is missing, changed, or unreadable. It is not shown as a "
            "successful result.",
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
        self.run_details_button = Button("Back to Run", variant="outline")
        self.run_details_button.clicked.connect(self.run_requested)
        footer.addWidget(self.run_details_button)
        footer.addStretch()
        outer.addLayout(footer)

        self.render()

    def _build_history_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Result history")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QGridLayout()
        copy = QVBoxLayout()
        copy.addWidget(Text("Results", role="heading"))
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
        self.provenance_card.setAccessibleName("Result details")
        provenance_heading = QHBoxLayout()
        provenance_heading.addWidget(Text("Result details", role="heading"))
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
                ("intervals", "Calls"),
                ("files", "Recording outcomes"),
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
        copy.addWidget(Text("Check calls with another model", role="heading"))
        heading.addLayout(copy, 1)
        self.refinement_status_badge = Badge("Not selected", intent="neutral")
        heading.addWidget(self.refinement_status_badge, 0, Qt.AlignmentFlag.AlignTop)
        card.content_layout.addLayout(heading)

        self.refinement_model_name = Text("Not selected", role="subheading", word_wrap=True)
        card.content_layout.addWidget(self.refinement_model_name)
        self.refinement_model_detail = Text("", role="body", word_wrap=True)
        card.content_layout.addWidget(self.refinement_model_detail)
        self.storage_section = StorageSection()
        card.content_layout.addWidget(self.storage_section)

        actions = QHBoxLayout()
        self.change_refinement_model_button = Button("Change model", variant="outline")
        self.change_refinement_model_button.clicked.connect(self.models_requested)
        actions.addWidget(self.change_refinement_model_button)
        actions.addStretch()
        self.refinement_button = Button("Check calls", variant="primary")
        self.refinement_button.clicked.connect(self._start_refinement)
        actions.addWidget(self.refinement_button)
        card.content_layout.addLayout(actions)
        return card

    def _start_refinement(self) -> None:
        try:
            prior_digest = (
                None if self.storage_estimate is None else self.storage_estimate.input_digest
            )
            estimate = self.controller.estimate_refinement_storage(
                expected_digest=prior_digest
            )
            self.storage_estimate = estimate
            self.storage_section.set_estimate(estimate, variable=True)
            if not estimate.can_start or not confirm_storage(self, estimate):
                return
            self.controller.start_refinement(
                storage_digest=estimate.input_digest,
                confirm_storage=estimate.requires_confirmation,
            )
        except (OSError, RuntimeError, ValueError):
            self.refinement_model_detail.setText(
                "This check could not start. Review the model and selected result, then try again."
            )
            return
        self.run_requested.emit()

    def _build_recording_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Result recordings")
        card.content_layout.addWidget(Text("Recordings", role="heading"))
        card.content_layout.addWidget(
            Text(
                "Choose a recording to inspect the calls found in it.",
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
        self.recording_table.selectionModel().currentRowChanged.connect(self._recording_changed)
        card.content_layout.addWidget(self.recording_table)
        return card

    def _build_candidate_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Calls in the selected recording")
        heading = QHBoxLayout()
        labels = QVBoxLayout()
        self.recording_title = Text("Choose a recording", role="heading", word_wrap=True)
        labels.addWidget(self.recording_title)
        self.recording_subtitle = Text(
            "Times in the original recording", role="body", word_wrap=True
        )
        labels.addWidget(self.recording_subtitle)
        heading.addLayout(labels, 1)
        self.show_source_button = Button("Show source", variant="outline", size="small")
        self.show_source_button.clicked.connect(self._show_source)
        heading.addWidget(self.show_source_button, 0, Qt.AlignmentFlag.AlignTop)
        card.content_layout.addLayout(heading)
        self.source_message = QLabel()
        self.source_message.setWordWrap(True)
        self.source_message.setAccessibleName("Recording source status")
        self.source_message.setStyleSheet("color: #92400E; font-weight: 600;")
        self.source_message.hide()
        card.content_layout.addWidget(self.source_message)

        self.candidate_model = CandidateResultModel(self)
        self.candidate_table = DataTable(model=self.candidate_model)
        self.candidate_table.setAccessibleName("Calls at their original recording times")
        self.candidate_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.candidate_table.setMinimumHeight(230)
        for column in range(len(self.candidate_model.ORIGINAL_HEADERS)):
            self.candidate_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        self.candidate_table.selectionModel().currentRowChanged.connect(self._candidate_changed)
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
                ("Time in recording", self.candidate_detail_time),
                ("Audio frames", self.candidate_detail_frames),
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
                self._candidate_by_recording[(result_id, self.selected_recording_id)] = (
                    candidate.candidate_id
                )
        self._render_candidate_detail(candidate)

    def _render_candidate_detail(self, candidate: CandidateViewRow | None) -> None:
        if candidate is None:
            values = ("—", "—", "—", "—")
        else:
            values = (
                candidate.candidate_id,
                f"{_source_time(candidate.start_time_ns)} – {_source_time(candidate.end_time_ns)}",
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
        self.source_message.clear()
        self.source_message.hide()
        projection = self.controller.selected_result_projection
        self.candidate_model.set_recording(
            recording,
            refined=projection is not None and projection.result_kind == "derived",
        )
        if self.candidate_model.refinement_visible:
            self.candidate_table.horizontalHeader().setSectionResizeMode(
                3, QHeaderView.ResizeMode.ResizeToContents
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
            self.source_message.setText(str(exc))
            self.source_message.show()
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

    def _render_refinement_controls(self, projection: ResultViewProjection | None) -> None:
        state = self.controller.refinement_model_state
        status = {
            ModelIntakeState.EMPTY: "Not selected",
            ModelIntakeState.LOADING: "Checking",
            ModelIntakeState.COMPATIBLE: "Compatible",
            ModelIntakeState.INCOMPATIBLE: "Incompatible",
            ModelIntakeState.MISSING: "Missing files",
        }[state]
        self.refinement_status_badge.setText(status)
        self.refinement_status_badge.setIntent(
            {
                ModelIntakeState.EMPTY: "neutral",
                ModelIntakeState.LOADING: "warning",
                ModelIntakeState.COMPATIBLE: "success",
                ModelIntakeState.INCOMPATIBLE: "danger",
                ModelIntakeState.MISSING: "danger",
            }[state]
        )
        self.refinement_status_badge.setAccessibleName(f"RF Model status: {status}")
        reference = self.controller.refinement_model_reference
        self.refinement_model_name.setText(
            reference.snapshot.label if reference is not None else "Not selected"
        )
        self.change_refinement_model_button.setEnabled(not self.controller.is_run_active)
        detail = {
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
        if projection is not None and projection.result_kind == "derived":
            detail = (
                "This result has already been checked. Select its original result to check it "
                "with another model."
            )
        elif projection is not None and projection.candidate_count == 0:
            detail = "This result has no calls to check."
        self.refinement_model_detail.setText(detail)
        self.refinement_model_detail.setVisible(bool(detail))
        storage_ready = False
        if self.controller.can_refine_selected_result:
            try:
                self.storage_estimate = self.controller.estimate_refinement_storage()
            except (OSError, RuntimeError, ValueError):
                self.storage_estimate = None
                self.storage_section.clear()
            else:
                self.storage_section.set_estimate(self.storage_estimate, variable=True)
                storage_ready = self.storage_estimate.can_start
        else:
            self.storage_estimate = None
            self.storage_section.clear()
        self.refinement_button.setEnabled(
            self.controller.can_refine_selected_result and storage_ready
        )

    def _state_action_requested(self) -> None:
        if self.current_state_key == "partial":
            projection = self.controller.selected_result_projection
            if projection is None:
                return
            for row, recording in enumerate(projection.recordings):
                if recording.outcome is FileOutcomeStatus.FAILED:
                    self.recording_table.setCurrentIndex(self.recording_model.index(row, 0))
                    self.recording_table.setFocus()
                    return
        elif self.current_state_key in {"stale", "source-unavailable"}:
            self.recordings_requested.emit()

    def _set_state(self, key: str) -> None:
        self.current_state_key = key
        states = {
            "partial": ("Some files failed", "warning", "View file errors"),
            "empty": ("No calls found", "neutral", ""),
            "stale": ("Recordings changed", "warning", "Review recordings"),
            "source-unavailable": ("Folder unavailable", "danger", "Relink folder"),
        }
        if key in states:
            status, intent, action = states[key]
            self.state_badge.setText(status)
            self.state_badge.setIntent(intent)
            self.state_badge.setAccessibleName(f"Result availability status: {status}")
            self.state_action.setText(action)
            self.state_action.setAccessibleName(action)
            self.state_action.setVisible(bool(action))
            self.state_row.show()
            self.state_title = self.state_badge
        elif key == "result-error":
            self.state_row.hide()
            self.state_action.hide()
            self.state_title = self.result_error_state.title_widget
        else:
            self.state_row.hide()
            self.state_action.hide()
            self.state_title = self.no_results_state.title_widget

    def render(self) -> None:
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
        self.lineage_label.setText(
            "Calls from an original result checked with a Random Forest model."
            if refined
            else "Calls found by the detection model."
        )
        self.provenance_values["completed"].setText(_completed_label(projection.completed_at))
        self.provenance_values["intervals"].setText(
            f"{projection.candidate_count:,} possible calls · "
            f"{projection.accepted_count:,} accepted · "
            f"{projection.rejected_count:,} rejected · "
            f"{projection.unscored_count:,} could not assess"
            if refined
            else f"{projection.candidate_count:,} possible "
            f"call{'s' if projection.candidate_count != 1 else ''}"
        )
        self.provenance_values["files"].setText(
            f"{projection.successful_files:,} completed · {projection.failed_files:,} file "
            f"error{'s' if projection.failed_files != 1 else ''}"
        )
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
            self.run_details_button.setFocus()


__all__ = ["CandidateResultModel", "RecordingResultModel", "ResultExplorer"]
