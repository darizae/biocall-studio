"""Native Detect Run and export history list/detail surfaces."""

from __future__ import annotations

from datetime import datetime

from alp_ui.components import Badge, Button, Card, DataTable, EmptyState, Text
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from biocall_studio.detect.application.controller import DetectWorkspaceController
from biocall_studio.detect.domain.export_history import ExportAvailability, ExportHistoryRecord
from biocall_studio.detect.domain.runs import DetectRunRecord


def _time_label(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except (TypeError, ValueError):
        return value
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


class RunHistoryModel(QAbstractTableModel):
    HEADERS = ("RUN", "STATUS", "STARTED", "PROGRESS")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.records: tuple[DetectRunRecord, ...] = ()

    def set_records(self, records: tuple[DetectRunRecord, ...]) -> None:
        self.beginResetModel()
        self.records = tuple(
            sorted(records, key=lambda item: (item.created_at, item.run_id), reverse=True)
        )
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.records)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.records):
            return None
        record = self.records[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return record.run_id
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        return (
            record.title,
            record.status.value.capitalize(),
            _time_label(record.created_at),
            f"{record.progress}%",
        )[index.column()]

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def record_at(self, row: int) -> DetectRunRecord | None:
        return self.records[row] if 0 <= row < len(self.records) else None

    def row_for_id(self, run_id: str) -> int | None:
        return next(
            (row for row, record in enumerate(self.records) if record.run_id == run_id),
            None,
        )


class RunHistoryPage(QWidget):
    run_requested = Signal(str)

    def __init__(self, controller: DetectWorkspaceController):
        super().__init__()
        self.controller = controller
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)
        self.model = RunHistoryModel(self)
        self.table = DataTable(model=self.model)
        self.table.setAccessibleName("Detect Runs")
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(self.model.HEADERS)):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        self.table.doubleClicked.connect(lambda index: self._open_row(index.row()))
        self.empty = EmptyState("No Runs yet", text="Start a new detection to create a Run.")
        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.table)
        outer.addWidget(self.stack, 1)
        actions = QHBoxLayout()
        actions.addStretch()
        self.open_button = Button("Open Run", variant="primary")
        self.open_button.clicked.connect(self._open_selected)
        actions.addWidget(self.open_button)
        outer.addLayout(actions)

    def _open_row(self, row: int) -> None:
        record = self.model.record_at(row)
        if record is not None:
            self.run_requested.emit(record.run_id)

    def _open_selected(self) -> None:
        self._open_row(self.table.currentIndex().row())

    def render(self) -> None:
        self.model.set_records(self.controller.runs)
        has_rows = bool(self.controller.runs)
        self.stack.setCurrentWidget(self.table if has_rows else self.empty)
        row = self.model.row_for_id(self.controller.selected_run_id or "")
        if row is not None:
            self.table.setCurrentIndex(self.model.index(row, 0))
        elif has_rows:
            self.table.setCurrentIndex(self.model.index(0, 0))
        self.open_button.setEnabled(has_rows)

    def focus_initial(self) -> None:
        (self.table if self.model.rowCount() else self.open_button).setFocus()


class ExportHistoryModel(QAbstractTableModel):
    HEADERS = ("COMPLETED", "RESULT", "FORMAT", "CALLS", "FILES")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.records: tuple[ExportHistoryRecord, ...] = ()

    def set_records(self, records: tuple[ExportHistoryRecord, ...]) -> None:
        self.beginResetModel()
        self.records = tuple(
            sorted(records, key=lambda item: (item.completed_at, item.export_id), reverse=True)
        )
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.records)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.records):
            return None
        record = self.records[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return record.export_id
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        return (
            _time_label(record.completed_at),
            record.result_id,
            record.mode.value.replace("_", " ").title(),
            f"{record.selected_call_count:,}",
            f"{record.published_file_count:,}",
        )[index.column()]

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def record_at(self, row: int) -> ExportHistoryRecord | None:
        return self.records[row] if 0 <= row < len(self.records) else None

    def row_for_id(self, export_id: str) -> int | None:
        return next(
            (row for row, record in enumerate(self.records) if record.export_id == export_id),
            None,
        )


class ExportHistoryPage(QWidget):
    export_requested = Signal(str)

    def __init__(self, controller: DetectWorkspaceController):
        super().__init__()
        self.controller = controller
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)
        self.model = ExportHistoryModel(self)
        self.table = DataTable(model=self.model)
        self.table.setAccessibleName("Completed exports")
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in (0, 2, 3, 4):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        self.table.doubleClicked.connect(lambda index: self._open_row(index.row()))
        self.empty = EmptyState(
            "No exports yet",
            text="Historical Detect exports will appear here.",
        )
        self.empty.setAccessibleName("No historical Detect exports")
        self.empty.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.table)
        outer.addWidget(self.stack, 1)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        self.notice.setStyleSheet("color: #B91C1C; font-weight: 600;")
        outer.addWidget(self.notice)
        actions = QHBoxLayout()
        actions.addStretch()
        self.open_button = Button("Open export", variant="primary")
        self.open_button.clicked.connect(self._open_selected)
        actions.addWidget(self.open_button)
        outer.addLayout(actions)

    def _open_row(self, row: int) -> None:
        record = self.model.record_at(row)
        if record is not None:
            self.export_requested.emit(record.export_id)

    def _open_selected(self) -> None:
        self._open_row(self.table.currentIndex().row())

    def render(self) -> None:
        self.model.set_records(self.controller.export_history)
        has_rows = bool(self.controller.export_history)
        self.stack.setCurrentWidget(self.table if has_rows else self.empty)
        row = self.model.row_for_id(self.controller.selected_export_id or "")
        if row is not None:
            self.table.setCurrentIndex(self.model.index(row, 0))
        elif has_rows:
            self.table.setCurrentIndex(self.model.index(0, 0))
        self.open_button.setEnabled(has_rows)
        rejected = len(self.controller.export_history_rejected)
        self.notice.setText(
            "One saved export record could not be read. Other exports remain available."
            if rejected == 1
            else (
                f"{rejected:,} saved export records could not be read. Other exports remain "
                "available."
                if rejected
                else ""
            )
        )
        self.notice.setVisible(bool(rejected))

    def focus_initial(self) -> None:
        (self.table if self.model.rowCount() else self.empty).setFocus()


class ExportDetailPage(QWidget):
    back_requested = Signal()

    def __init__(self, controller: DetectWorkspaceController, show_in_folder):
        super().__init__()
        self.controller = controller
        self._show_in_folder = show_in_folder
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)
        self.card = Card()
        self.card.setAccessibleName("Export details")
        heading = QHBoxLayout()
        heading.addWidget(Text("Export details", role="heading"))
        heading.addStretch()
        self.status = Badge("Checking", intent="warning")
        heading.addWidget(self.status)
        self.card.content_layout.addLayout(heading)
        self.summary = Text("", role="subheading", word_wrap=True)
        self.card.content_layout.addWidget(self.summary)
        self.details = QGridLayout()
        self.values: dict[str, QLabel] = {}
        for row, (key, label) in enumerate(
            (
                ("completed", "Completed"),
                ("result", "Result"),
                ("format", "Format"),
                ("files", "Files"),
            )
        ):
            self.details.addWidget(QLabel(label), row, 0)
            value = QLabel("—")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByKeyboard)
            self.details.addWidget(value, row, 1)
            self.values[key] = value
        self.details.setColumnStretch(1, 1)
        self.card.content_layout.addLayout(self.details)
        self.message = Text("", role="body", word_wrap=True)
        self.card.content_layout.addWidget(self.message)
        outer.addWidget(self.card)
        actions = QHBoxLayout()
        self.back_button = Button("Back to Exports", variant="outline")
        self.back_button.clicked.connect(self.back_requested)
        actions.addWidget(self.back_button)
        actions.addStretch()
        self.show_button = Button("Show in folder", variant="primary")
        self.show_button.clicked.connect(self._show)
        actions.addWidget(self.show_button)
        outer.addLayout(actions)
        outer.addStretch()

    def _show(self) -> None:
        receipt = self.controller.verified_export_receipt
        if receipt is not None:
            self._show_in_folder(receipt.final_destination)

    def render(self) -> None:
        record = self.controller.selected_export
        if record is None:
            self.summary.setText("No export selected.")
            self.show_button.setEnabled(False)
            return
        state = ExportAvailability(self.controller.export_verification_state)
        labels = {
            ExportAvailability.UNSELECTED: ("Not checked", "neutral"),
            ExportAvailability.VERIFYING: ("Checking", "warning"),
            ExportAvailability.AVAILABLE: ("Available", "success"),
            ExportAvailability.MISSING: ("Missing", "danger"),
            ExportAvailability.INACCESSIBLE: ("Unavailable", "danger"),
            ExportAvailability.CHANGED: ("Changed", "danger"),
        }
        label, intent = labels[state]
        self.status.setText(label)
        self.status.setIntent(intent)
        self.status.setAccessibleName(f"Export status: {label}")
        self.summary.setText(record.export_id)
        self.values["completed"].setText(_time_label(record.completed_at))
        self.values["result"].setText(record.result_id)
        self.values["format"].setText(record.mode.value.replace("_", " ").title())
        self.values["files"].setText(
            f"{record.selected_call_count:,} calls · {record.published_file_count:,} files"
        )
        self.message.setText(self.controller.export_verification_message)
        self.show_button.setEnabled(
            state is ExportAvailability.AVAILABLE
            and self.controller.verified_export_receipt is not None
        )

    def focus_initial(self) -> None:
        (self.show_button if self.show_button.isEnabled() else self.back_button).setFocus()


__all__ = [
    "ExportDetailPage",
    "ExportHistoryModel",
    "ExportHistoryPage",
    "RunHistoryModel",
    "RunHistoryPage",
]
