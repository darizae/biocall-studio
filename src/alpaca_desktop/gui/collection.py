"""Native Reading and Collection overview views."""

from __future__ import annotations

from datetime import datetime

from alp_ui.components import Alert, Badge, Button, Card, DataTable, HelpHint, ProgressBar, Text
from alp_ui.theme import ALPACA_LIGHT, make_icon
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from alpaca_desktop.application.collection_scan import ScanProgress
from alpaca_desktop.application.workspace import WorkspaceController
from alpaca_desktop.domain.collection import ScanResult


def _duration(seconds: float) -> str:
    if seconds >= 3_600:
        return f"{seconds / 3_600:.1f} h"
    if seconds >= 60:
        return f"{seconds / 60:.1f} min"
    return f"{seconds:.1f} s"


class PagedRecordingModel(QAbstractTableModel):
    """Expose Source Recording aggregates to Qt in bounded pages."""

    HEADERS = ("SOURCE RECORDING", "LENGTH", "POSITIVES")

    def __init__(self, result: ScanResult, parent=None, *, page_size: int = 200):
        super().__init__(parent)
        self._records = result.records
        self._page_size = page_size
        self._visible = min(page_size, len(self._records))

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else self._visible

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else 3

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole or not index.isValid():
            return None
        record = self._records[index.row()]
        return (
            record.name,
            _duration(record.fingerprint.header.duration_seconds),
            record.positive_count,
        )[index.column()]

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def canFetchMore(self, parent: QModelIndex = QModelIndex()) -> bool:  # noqa: N802
        return not parent.isValid() and self._visible < len(self._records)

    def fetchMore(self, parent: QModelIndex = QModelIndex()) -> None:  # noqa: N802
        if parent.isValid() or not self.canFetchMore(parent):
            return
        count = min(self._page_size, len(self._records) - self._visible)
        self.beginInsertRows(QModelIndex(), self._visible, self._visible + count - 1)
        self._visible += count
        self.endInsertRows()


class IssueModel(QAbstractTableModel):
    HEADERS = ("ISSUE", "PATH AND CORRECTION")

    def __init__(self, result: ScanResult, parent=None):
        super().__init__(parent)
        self._issues = result.issues

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._issues)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else 2

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole or not index.isValid():
            return None
        issue = self._issues[index.row()]
        if index.column() == 0:
            return issue.message
        return f"{issue.relative_path} — {issue.correction}"

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None


class ReadingCollectionPage(QScrollArea):
    def __init__(self, controller: WorkspaceController):
        super().__init__()
        self.controller = controller
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAccessibleName("Reading Collection")
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(38, 42, 38, 42)
        outer.setSpacing(18)
        self.narrow = QWidget()
        self.narrow.setMaximumWidth(780)
        layout = QVBoxLayout(self.narrow)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        layout.addWidget(Text("SELECT COLLECTION", role="overline"))
        self.title = Text("Reading Collection", role="title")
        layout.addWidget(self.title)
        layout.addWidget(
            Text(
                "Validating filenames, timestamps, and WAV headers…",
                role="body",
                word_wrap=True,
            )
        )
        card = Card()
        self.card = card
        heading = QHBoxLayout()
        self.stage = Text("Listing files", role="subheading")
        heading.addWidget(self.stage)
        heading.addStretch()
        heading.addWidget(Badge("Local scan", intent="warning"))
        card.content_layout.addLayout(heading)
        progress_heading = QHBoxLayout()
        self.file_count = Text("0 / 0 files", role="body")
        self.percent = Text("0%", role="body")
        progress_heading.addWidget(self.file_count)
        progress_heading.addStretch()
        progress_heading.addWidget(self.percent)
        card.content_layout.addLayout(progress_heading)
        self.progress_bar = ProgressBar(value=0)
        self.progress_bar.setAccessibleName("Collection Scan progress")
        card.content_layout.addWidget(self.progress_bar)
        self.count_values: dict[str, Text] = {}
        for label in ("Recordings inspected", "Positives inspected", "Issues so far"):
            row = QHBoxLayout()
            row.addWidget(Text(label, role="caption"))
            row.addStretch()
            value = Text("0", role="body")
            self.count_values[label] = value
            row.addWidget(value)
            card.content_layout.addLayout(row)
        actions = QHBoxLayout()
        actions.addWidget(Text("You can cancel this scan.", role="caption"))
        actions.addStretch()
        self.cancel_button = Button("Cancel scan", variant="secondary")
        self.cancel_button.clicked.connect(controller.cancel_scan)
        actions.addWidget(self.cancel_button)
        card.content_layout.addLayout(actions)
        layout.addWidget(card)
        note = Text(
            "Large folders are read by a bounded background I/O worker; "
            "source audio is not decoded.",
            role="caption",
            word_wrap=True,
        )
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(note)
        outer.addWidget(self.narrow, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch()
        self.setWidget(content)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.narrow.setFixedWidth(max(320, min(780, self.viewport().width() - 80)))

    def begin(self, root: str) -> None:
        self.title.setText(f"Reading {root.rsplit('/', 1)[-1]}")
        self.refresh(ScanProgress("Listing files", 0, 0, 0, 0, 0))

    def refresh(self, progress: ScanProgress) -> None:
        self.stage.setText(progress.stage)
        self.file_count.setText(f"{progress.completed:,} / {progress.total:,} files")
        percent = round(progress.completed * 100 / progress.total) if progress.total else 0
        self.percent.setText(f"{percent}%")
        self.progress_bar.setValue(percent)
        self.count_values["Recordings inspected"].setText(f"{progress.recordings:,}")
        self.count_values["Positives inspected"].setText(f"{progress.positives:,}")
        self.count_values["Issues so far"].setText(f"{progress.issues:,}")


class CollectionPage(QScrollArea):
    def __init__(self, controller: WorkspaceController, open_select, open_build, open_wiki):
        super().__init__()
        self.controller = controller
        self.open_select = open_select
        self.open_build = open_build
        self.open_wiki = open_wiki
        self.result: ScanResult | None = None
        self.is_compact = False
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAccessibleName("Collection overview")
        self.content = QWidget()
        self.outer = QVBoxLayout(self.content)
        self.outer.setContentsMargins(38, 30, 38, 38)
        self.outer.setSpacing(17)
        self.setWidget(self.content)

    def set_result(self, result: ScanResult) -> None:
        self.result = result
        while self.outer.count():
            item = self.outer.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

        crumbs = Text(f"Collections  /  {result.root_name}", role="caption")
        self.outer.addWidget(crumbs)
        self.header_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        heading_widget = QWidget()
        heading = QVBoxLayout(heading_widget)
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(3)
        heading.addWidget(Text("COLLECTION", role="overline"))
        heading.addWidget(Text(result.root_name, role="title"))
        heading.addWidget(Text(f"Selected folder: {result.root_name}", role="caption"))
        heading_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.header_layout.addWidget(heading_widget)
        actions_widget = QWidget()
        actions = QHBoxLayout(actions_widget)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(9)
        self.choose_button = Button("Choose another folder", variant="outline")
        self.choose_button.clicked.connect(self.open_select)
        actions.addWidget(self.choose_button)
        self.rescan_button = Button("Rescan Collection", variant="secondary")
        self.rescan_button.clicked.connect(self.controller.rescan)
        actions.addWidget(self.rescan_button)
        self.build_button = Button("Build Dataset")
        self.build_button.setIcon(make_icon("plus", color=ALPACA_LIGHT.colors.on_primary, size=15))
        self.build_button.setEnabled(result.valid and self.controller.current_inputs_ready())
        self.build_button.setAccessibleDescription(
            "Available only while the current scanned inputs remain valid."
        )
        self.build_button.clicked.connect(self._request_build)
        actions.addWidget(self.build_button)
        self.header_layout.addWidget(actions_widget)
        self.outer.addLayout(self.header_layout)

        self.stats_layout = QGridLayout()
        self.stats_layout.setSpacing(12)
        self.summary_cards = []
        values = (
            ("Source Recordings", f"{result.recording_count:,}", "Original WAVs"),
            ("Positive examples", f"{result.positive_count:,}", "Labeled WAVs"),
            ("Recorded audio", _duration(result.duration_seconds), "From WAV headers"),
            ("Collection", "Valid" if result.valid else "Needs fixes", "Native checks"),
        )
        for column, (label, value, note) in enumerate(values):
            card = Card(shadow=False)
            card.content_layout.addWidget(Text(label, role="caption"))
            card.content_layout.addWidget(Text(value, role="heading"))
            card.content_layout.addWidget(Text(note, role="caption"))
            self.summary_cards.append(card)
            self.stats_layout.addWidget(card, 0, column)
        self.outer.addLayout(self.stats_layout)

        if result.valid:
            self.status_alert = Alert(
                "Folder, WAV headers, source names and snippet timestamps are consistent.",
                title="Collection valid",
                intent="success",
            )
        else:
            count = len(result.issues)
            self.status_alert = Alert(
                "Fix the files listed below, then rescan. Dataset Build is unavailable.",
                title=f"{count} validation {'issue' if count == 1 else 'issues'}",
                intent="warning",
            )
        self.outer.addWidget(self.status_alert)

        self.left_stack = QWidget()
        left = QVBoxLayout(self.left_stack)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(15)
        recordings = Card(shadow=False)
        table_heading = QHBoxLayout()
        title = QVBoxLayout()
        title.addWidget(Text("Recordings", role="subheading"))
        title.addWidget(Text("Positive snippets by Source Recording", role="caption"))
        table_heading.addLayout(title)
        table_heading.addStretch()
        table_heading.addWidget(
            HelpHint(
                "Positive WAV names reference the complete Source Recording stem and carry "
                "source-time start/end values in integer milliseconds.",
                subject="Source and positive mapping",
            )
        )
        recordings.content_layout.addLayout(table_heading)
        self.recording_model = PagedRecordingModel(result, recordings)
        self.recordings_table = DataTable(model=self.recording_model)
        self.recordings_table.setAccessibleName("Source Recordings and positive counts")
        self.recordings_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.recordings_table.setMinimumHeight(180)
        recordings.content_layout.addWidget(self.recordings_table)
        left.addWidget(recordings)

        validation = Card(shadow=False)
        validation_header = QHBoxLayout()
        validation_header.addWidget(Text("Validation details", role="subheading"))
        validation_header.addStretch()
        self.naming_button = Button("Naming guide →", variant="outline", size="small")
        self.naming_button.clicked.connect(self.open_wiki)
        validation_header.addWidget(self.naming_button)
        validation.content_layout.addLayout(validation_header)
        self.issue_model = IssueModel(result, validation)
        if result.issues:
            self.issues_table = DataTable(model=self.issue_model)
            self.issues_table.setAccessibleName("Fixable Collection validation issues")
            self.issues_table.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.Stretch
            )
            self.issues_table.setMinimumHeight(160)
            validation.content_layout.addWidget(self.issues_table)
        else:
            for label in (
                "Folders and WAV headers",
                "Recording names",
                "Timestamp bounds / duration",
            ):
                row = QHBoxLayout()
                row.addWidget(Text(label, role="caption"))
                row.addStretch()
                row.addWidget(Badge("Passed", intent="success"))
                validation.content_layout.addLayout(row)
            checked = datetime.fromisoformat(result.scanned_at).astimezone().strftime("%d %b %Y")
            row = QHBoxLayout()
            row.addWidget(Text("Last checked", role="caption"))
            row.addStretch()
            row.addWidget(Text(checked, role="body"))
            validation.content_layout.addLayout(row)
        left.addWidget(validation)

        self.right_stack = QWidget()
        right = QVBoxLayout(self.right_stack)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(15)
        folder = Card(shadow=False)
        folder_header = QHBoxLayout()
        folder_header.addWidget(Text("Folder", role="subheading"))
        folder_header.addStretch()
        folder_header.addWidget(
            HelpHint(
                "Compact metadata is written under .alpaca/ without changing source WAVs.",
                subject="Collection storage",
            )
        )
        folder.content_layout.addLayout(folder_header)
        sample_record = result.records[0].name if result.records else "recording.wav"
        sample_positive = (
            result.positives[0].relative_path.rsplit("/", 1)[-1]
            if result.positives
            else "recording__start-…ms__end-…ms__call.wav"
        )
        metadata_label = (
            ".alpaca/  generated metadata + outputs"
            if result.valid
            else ".alpaca/  metadata after a valid scan"
        )
        tree = QLabel(
            f"{result.root_name}/\n"
            f"  ├─ recordings/  {result.recording_count:,} WAV\n"
            f"  │  {sample_record}\n"
            f"  ├─ positives/   {result.positive_count:,} WAV\n"
            f"  │  {sample_positive}\n"
            f"  └─ {metadata_label}"
        )
        tree.setWordWrap(True)
        tree.setAccessibleName("Collection folder summary")
        folder.content_layout.addWidget(tree)
        right.addWidget(folder)

        cache = Card(shadow=False)
        cache.content_layout.addWidget(Text("Fast reopening", role="subheading"))
        for label, value in (
            ("Metadata", "Ready" if result.valid else "Not published"),
            ("Audio copies", "None"),
            ("What we check", "Header + names + times"),
        ):
            row = QHBoxLayout()
            row.addWidget(Text(label, role="caption"))
            row.addStretch()
            row.addWidget(Text(value, role="body"))
            cache.content_layout.addLayout(row)
        cache.content_layout.addWidget(
            Text(
                "Reopen compares path, size, modified time and cached header facts. "
                "Current inputs are checked again before Dataset Build.",
                role="caption",
                word_wrap=True,
            )
        )
        right.addWidget(cache)
        right.addStretch()

        self.content_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.content_layout.setSpacing(16)
        self.content_layout.addWidget(self.left_stack, 5)
        self.content_layout.addWidget(self.right_stack, 3)
        self.outer.addLayout(self.content_layout)
        note = Text(
            "Source-time intervals come from filenames; validation does not prove matching "
            "waveform content.",
            role="caption",
            word_wrap=True,
        )
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.outer.addWidget(note)
        self.outer.addStretch()
        self._apply_compact(self.viewport().width() < 850)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_compact(event.size().width() < 850)

    def _apply_compact(self, compact: bool) -> None:
        self.is_compact = compact
        if hasattr(self, "content_layout"):
            self.content_layout.setDirection(
                QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
            )
        if hasattr(self, "header_layout"):
            self.header_layout.setDirection(
                QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
            )
        if hasattr(self, "summary_cards"):
            for index, card in enumerate(self.summary_cards):
                self.stats_layout.removeWidget(card)
                columns = 2 if compact else 4
                self.stats_layout.addWidget(card, index // columns, index % columns)

    def _request_build(self) -> None:
        if not self.controller.current_inputs_ready():
            self.build_button.setEnabled(False)
            self.status_alert.text_widget.setText(
                "Collection inputs changed after the last scan. Rescan before Dataset Build."
            )
            self.status_alert.setAccessibleDescription(self.status_alert.text_widget.text())
            return
        self.open_build()

    @classmethod
    def _clear_layout(cls, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                cls._clear_layout(item.layout())
