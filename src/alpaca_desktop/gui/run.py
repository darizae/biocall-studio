"""Native Run history and supervised Worker detail views."""

from __future__ import annotations

from collections.abc import Callable

from alp_ui.components import (
    Alert,
    Badge,
    Button,
    Card,
    DataTable,
    EmptyState,
    Plot,
    ProgressBar,
    Text,
)
from alp_ui.theme import ALPACA_LIGHT, interactions, make_icon
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFontDatabase, QResizeEvent
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

from alpaca_desktop.domain.run import RunState, RunStatus


def _heading(title: str, subtitle: str, *, overline: str) -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(3)
    layout.addWidget(Text(overline, role="overline"))
    layout.addWidget(Text(title, role="title"))
    layout.addWidget(Text(subtitle, role="caption", word_wrap=True))
    return widget


def _status_intent(status: RunStatus) -> str:
    if status is RunStatus.COMPLETED:
        return "success"
    if status in {
        RunStatus.STARTING,
        RunStatus.RUNNING,
        RunStatus.CANCELLING,
        RunStatus.CANCELLED,
    }:
        return "warning"
    if status in {RunStatus.FAILED, RunStatus.INTERRUPTED}:
        return "danger"
    return "neutral"


def _kind_label(run: RunState) -> str:
    return "Dataset Build" if run.kind.value == "dataset_build" else "Training"


class RunListModel(QAbstractTableModel):
    HEADERS = ("RUN", "KIND", "STATUS", "CREATED", "")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._runs: tuple[RunState, ...] = ()

    def set_runs(self, runs: tuple[RunState, ...]) -> None:
        self.beginResetModel()
        self._runs = runs
        self.endResetModel()

    def run(self, row: int) -> RunState:
        return self._runs[row]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._runs)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        run = self._runs[index.row()]
        if index.column() == 2:
            colors = ALPACA_LIGHT.colors
            state = interactions(ALPACA_LIGHT)
            foreground, background = {
                RunStatus.COMPLETED: (colors.primary_hover, state.feedback_success),
                RunStatus.FAILED: (colors.danger, state.feedback_danger),
                RunStatus.INTERRUPTED: (colors.danger, state.feedback_danger),
                RunStatus.CANCELLED: (colors.warning, state.feedback_warning),
                RunStatus.CANCELLING: (colors.warning, state.feedback_warning),
                RunStatus.RUNNING: (colors.warning, state.feedback_warning),
                RunStatus.STARTING: (colors.warning, state.feedback_warning),
                RunStatus.CREATED: (colors.text_muted, colors.background),
            }[run.status]
            if role == Qt.ItemDataRole.DisplayRole:
                return f"●  {run.status.value}"
            if role == Qt.ItemDataRole.ForegroundRole:
                return QColor(foreground)
            if role == Qt.ItemDataRole.BackgroundRole:
                return QColor(background)
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return Qt.AlignmentFlag.AlignCenter
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                f"{run.title}\n{run.run_id}",
                _kind_label(run),
                run.status.value,
                run.created_at.split("T", 1)[0],
                "Inspect →",
            )[index.column()]
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return f"{run.title}, {_kind_label(run)}, {run.status.value}"
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None


class RunListPage(QScrollArea):
    def __init__(self, open_run: Callable[[str], None], select_collection: Callable[[], None]):
        super().__init__()
        self.open_run = open_run
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAccessibleName("Runs history")
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(38, 30, 38, 38)
        layout.setSpacing(16)

        header = QHBoxLayout()
        header.addWidget(
            _heading(
                "Runs",
                "Dataset Build and Training history.",
                overline="EXECUTION",
            ),
            1,
        )
        self.active_button = Button("View Active Run")
        self.active_button.setIcon(make_icon("list", color=ALPACA_LIGHT.colors.on_primary, size=15))
        self._active_run_id: str | None = None
        self.active_button.clicked.connect(self._open_active)
        self.active_button.hide()
        header.addWidget(self.active_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        self.model = RunListModel(self)
        self.table = DataTable(model=self.model)
        self.table.setAccessibleName("Scientific Run history")
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.table.clicked.connect(lambda index: self.open_run(self.model.run(index.row()).run_id))
        layout.addWidget(self.table)

        empty_action = Button("Select Collection")
        empty_action.clicked.connect(select_collection)
        self.empty = EmptyState(
            "No Runs yet.",
            text="Dataset Build and Training activity will appear here.",
            icon=make_icon("list", color=ALPACA_LIGHT.colors.primary, size=28),
            action=empty_action,
        )
        layout.addWidget(self.empty, 1)
        layout.addStretch()
        self.setWidget(content)

    def set_runs(self, runs: tuple[RunState, ...], active: RunState | None) -> None:
        self.model.set_runs(runs)
        self.table.setVisible(bool(runs))
        self.table.setFixedHeight(max(120, 44 + 45 * len(runs)))
        self.empty.setVisible(not runs)
        if active is None:
            self._active_run_id = None
            self.active_button.hide()
        else:
            self._active_run_id = active.run_id
            self.active_button.show()

    def _open_active(self) -> None:
        if self._active_run_id is not None:
            self.open_run(self._active_run_id)


class RunDetailPage(QScrollArea):
    section_order = ("progress", "measurements", "activity", "output", "details")

    def __init__(
        self,
        cancel_run: Callable[[], None],
        open_output: Callable[[RunState], None],
        open_history: Callable[[], None],
        open_log: Callable[[RunState], bool],
        log_available: Callable[[str], bool],
    ):
        super().__init__()
        self.cancel_run = cancel_run
        self.open_output = open_output
        self.open_history = open_history
        self.open_log = open_log
        self.log_available = log_available
        self.run: RunState | None = None
        self.is_compact = False
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAccessibleName("Run detail")
        self._render_empty()

    def _render_empty(self) -> None:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(38, 30, 38, 38)
        layout.addWidget(Text("Run is not available.", role="title"))
        self.setWidget(content)

    def set_run(self, run: RunState) -> None:
        self.run = run
        old = self.takeWidget()
        if old is not None:
            old.deleteLater()
        self.content = QWidget()
        self.outer = QVBoxLayout(self.content)
        self.outer.setContentsMargins(38, 30, 38, 42)
        self.outer.setSpacing(16)
        self.outer.addWidget(Text(f"Runs  /  {run.run_id}", role="caption"))

        header = QHBoxLayout()
        header.addWidget(
            _heading(
                run.title,
                f"Run ID · {run.run_id} · {run.created_at.split('T', 1)[0]}",
                overline=f"RUN · {_kind_label(run).upper()}",
            ),
            1,
        )
        actions = QHBoxLayout()
        self.cancel_button = Button("Cancel Run", variant="danger")
        self.cancel_button.setAccessibleDescription(
            "Request cooperative cancellation; unpublished output will not be published."
        )
        self.cancel_button.clicked.connect(self._confirm_cancel)
        self.cancel_button.setVisible(run.active)
        self.cancel_button.setEnabled(run.status is not RunStatus.CANCELLING)
        actions.addWidget(self.cancel_button)
        self.open_log_button = Button("Open log", variant="outline")
        self.open_log_button.setAccessibleDescription(
            "Open this Run's contained local Worker diagnostic log."
        )
        self.open_log_button.clicked.connect(self._open_log)
        self.open_log_button.setVisible(self.log_available(run.run_id))
        actions.addWidget(self.open_log_button)
        self.open_output_button = Button(
            "Open Dataset" if run.output_kind == "dataset" else "Open Model"
        )
        self.open_output_button.setIcon(
            make_icon("check", color=ALPACA_LIGHT.colors.on_primary, size=15)
        )
        self.open_output_button.clicked.connect(lambda: self.open_output(run))
        self.open_output_button.setVisible(run.status is RunStatus.COMPLETED)
        actions.addWidget(self.open_output_button)
        header.addLayout(actions)
        self.outer.addLayout(header)

        self.columns = QGridLayout()
        self.columns.setSpacing(16)
        self.left_stack = QWidget()
        left = QVBoxLayout(self.left_stack)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(15)
        self.right_stack = QWidget()
        right = QVBoxLayout(self.right_stack)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(15)

        self.progress_card = Card(shadow=False)
        progress_header = QHBoxLayout()
        progress_header.addWidget(
            Text(
                "Working locally"
                if run.status in {RunStatus.STARTING, RunStatus.RUNNING}
                else "Cancelling safely"
                if run.status is RunStatus.CANCELLING
                else "Run completed"
                if run.status is RunStatus.COMPLETED
                else "Run stopped",
                role="subheading",
            )
        )
        progress_header.addStretch()
        self.status_badge = Badge(run.status.value, intent=_status_intent(run.status))
        progress_header.addWidget(self.status_badge)
        self.progress_card.content_layout.addLayout(progress_header)
        progress_values = QHBoxLayout()
        progress_values.addWidget(Text(run.current_stage, role="body"))
        progress_values.addStretch()
        progress_values.addWidget(Text(f"{run.progress}%", role="heading"))
        self.progress_card.content_layout.addLayout(progress_values)
        self.progress = ProgressBar(value=run.progress)
        self.progress.setAccessibleName(f"Run progress {run.progress} percent")
        self.progress_card.content_layout.addWidget(self.progress)
        self.stage_labels: list[Text] = []
        for index, stage in enumerate(run.stages):
            row = QHBoxLayout()
            done = run.stage_index > index
            current = run.active and run.stage_index == index
            marker = Badge("✓" if done else str(index + 1), intent="success" if done else "neutral")
            marker.setFixedWidth(30)
            row.addWidget(marker)
            label = Text(stage, role="body" if current else "caption", word_wrap=True)
            label.setAccessibleDescription(
                "completed" if done else "current" if current else "pending"
            )
            self.stage_labels.append(label)
            row.addWidget(label, 1)
            self.progress_card.content_layout.addLayout(row)
        left.addWidget(self.progress_card)

        if run.kind.value == "training":
            measurements_card = Card(shadow=False)
            if run.training_family == "rf":
                measurements_card.content_layout.addWidget(
                    Text("Validation and feature importance", role="subheading")
                )
                measurements_card.content_layout.addWidget(
                    Text(
                        "Random Forest reports held-out validation metrics and actual fitted "
                        "feature importances; it does not produce epoch loss.",
                        role="caption",
                        word_wrap=True,
                    )
                )
                importance_rows = [
                    item for item in run.measurements if item.get("kind") == "feature_importance"
                ]
                bars = [
                    (str(item["feature"]), float(item["importance"])) for item in importance_rows
                ]
                self.training_plot_data = tuple(bars)
                self.training_plot = Plot(kind="bar", x_label="Feature", y_label="Importance")
                self.training_plot.setAccessibleName("Random Forest feature importance")
                self.training_plot.setBars(bars)
                summaries = [f"{name} · {value:.6f}" for name, value in bars]
                empty_text = "Measured feature importances appear after the forest has been fitted."
                accessible_name = "Feature importance numeric values"
            else:
                measurements_card.content_layout.addWidget(Text("Training loss", role="subheading"))
                measurements_card.content_layout.addWidget(
                    Text(
                        "Measured train and validation loss reported by the supervised Worker.",
                        role="caption",
                        word_wrap=True,
                    )
                )
                lines: dict[str, list[tuple[float, float]]] = {}
                for phase in ("train", "val"):
                    points = [
                        (float(item["epoch"]), float(item["loss"]))
                        for item in run.measurements
                        if item.get("phase") == phase
                    ]
                    if points:
                        lines[f"{phase} loss"] = points
                self.training_plot_data = tuple(
                    (label, tuple(points)) for label, points in lines.items()
                )
                self.training_plot = Plot(kind="line", x_label="Epoch", y_label="Loss")
                self.training_plot.setAccessibleName("CNN train and validation loss")
                self.training_plot.setLines(lines)
                by_epoch: dict[int, dict[str, float]] = {}
                for item in run.measurements:
                    phase = item.get("phase")
                    epoch = item.get("epoch")
                    loss = item.get("loss")
                    if phase in {"train", "val"} and isinstance(epoch, int):
                        by_epoch.setdefault(epoch, {})[str(phase)] = float(loss)
                summaries = []
                for epoch, phases in sorted(by_epoch.items())[-6:]:
                    values = " · ".join(
                        f"{phase} loss {phases[phase]:.4f}"
                        for phase in ("train", "val")
                        if phase in phases
                    )
                    summaries.append(f"Epoch {epoch} · {values}")
                empty_text = "Measured loss appears after the first completed training phase."
                accessible_name = "Numeric CNN loss measurements"
            self.training_plot.setMinimumHeight(230)
            measurements_card.content_layout.addWidget(self.training_plot)
            self.training_values = QLabel("\n".join(summaries) if summaries else empty_text)
            self.training_values.setWordWrap(True)
            self.training_values.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self.training_values.setAccessibleName(accessible_name)
            measurements_card.content_layout.addWidget(self.training_values)
            left.addWidget(measurements_card)

        activity_card = Card(shadow=False)
        activity_card.content_layout.addWidget(Text("Run activity", role="subheading"))
        self.activity = QLabel("\n".join(run.activity))
        self.activity.setObjectName("runActivity")
        self.activity.setWordWrap(True)
        self.activity.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.activity.setAccessibleName("Run activity log")
        fixed = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        fixed.setPointSize(10)
        self.activity.setFont(fixed)
        self.activity.setStyleSheet(
            "QLabel#runActivity { background: #0f172a; color: #b8d4ca; "
            "border-radius: 8px; padding: 12px; }"
        )
        activity_card.content_layout.addWidget(self.activity)
        self.log_unavailable = Text(
            "No Worker log is available for older Runs; diagnostics are not backfilled.",
            role="caption",
            word_wrap=True,
        )
        self.log_unavailable.setVisible(not self.log_available(run.run_id))
        activity_card.content_layout.addWidget(self.log_unavailable)
        left.addWidget(activity_card)

        output_card = Card(shadow=False)
        output_header = QHBoxLayout()
        output_header.addWidget(Text("Output", role="subheading"))
        output_header.addStretch()
        output_card.content_layout.addLayout(output_header)
        title, text, intent = self._output_feedback(run)
        self.output_alert = Alert(text, title=title, intent=intent)
        output_card.content_layout.addWidget(self.output_alert)
        if run.status is RunStatus.COMPLETED:
            output_id = QHBoxLayout()
            output_id.addWidget(
                Text(
                    "Dataset ID" if run.output_kind == "dataset" else "Model ID",
                    role="caption",
                )
            )
            output_id.addStretch()
            output_id.addWidget(Text(run.output_id, role="body"))
            output_card.content_layout.addLayout(output_id)
            open_again = Button(
                "Open Dataset →" if run.output_kind == "dataset" else "Open Model →"
            )
            open_again.clicked.connect(lambda: self.open_output(run))
            output_card.content_layout.addWidget(open_again)
        right.addWidget(output_card)

        details_card = Card(shadow=False)
        details_card.content_layout.addWidget(Text("Run details", role="subheading"))
        for label, value in (
            ("Kind", _kind_label(run)),
            ("Status", run.status.value),
            ("Collection", run.collection_id),
            ("Started", run.created_at),
        ):
            row = QHBoxLayout()
            row.addWidget(Text(label, role="caption"))
            row.addStretch()
            row.addWidget(Text(value, role="body"))
            details_card.content_layout.addLayout(row)
        right.addWidget(details_card)
        right.addStretch()

        self.outer.addLayout(self.columns)
        self.outer.addStretch()
        self.setWidget(self.content)
        self._place_columns(self.viewport().width() < 850)

    @staticmethod
    def _output_feedback(run: RunState) -> tuple[str, str, str]:
        if run.status in {RunStatus.CREATED, RunStatus.STARTING, RunStatus.RUNNING}:
            return (
                "Not yet published",
                "Inputs are read-only. Output stays private until validation completes.",
                "neutral",
            )
        if run.status is RunStatus.CANCELLING:
            return (
                "Cancellation requested",
                "The Worker is stopping. No partial Dataset or Model will be published.",
                "warning",
            )
        if run.status is RunStatus.COMPLETED:
            return (
                "Dataset ready" if run.output_kind == "dataset" else "Model ready",
                "The verified immutable output is published and ready to open.",
                "success",
            )
        if run.status is RunStatus.CANCELLED:
            return (
                "No published artifact",
                "Cancellation completed without publishing partial output.",
                "warning",
            )
        if run.status is RunStatus.INTERRUPTED:
            return (
                "Worker interrupted",
                run.error or "The Worker stopped before verified completion.",
                "danger",
            )
        return ("Run failed", run.error or "The Worker did not publish an output.", "danger")

    def _confirm_cancel(self) -> None:
        if self.run is None or not self.run.active:
            return
        answer = QMessageBox.question(
            self,
            f"Cancel {_kind_label(self.run)}?",
            "Unpublished files will be cleaned up. No Dataset or Model will be published.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.cancel_run()

    def _open_log(self) -> None:
        if self.run is None or not self.open_log(self.run):
            self.open_log_button.hide()
            self.log_unavailable.show()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.run is not None:
            self._place_columns(event.size().width() < 850)

    def _place_columns(self, compact: bool) -> None:
        if not hasattr(self, "columns"):
            return
        self.is_compact = compact
        if compact:
            self.content.setMinimumWidth(0)
            self.content.setMaximumWidth(max(320, self.viewport().width()))
        else:
            self.content.setMaximumWidth(16_777_215)
        self.columns.removeWidget(self.left_stack)
        self.columns.removeWidget(self.right_stack)
        if compact:
            self.columns.setColumnStretch(1, 0)
            self.columns.addWidget(self.left_stack, 0, 0)
            self.columns.addWidget(self.right_stack, 1, 0)
        else:
            self.columns.setColumnStretch(0, 3)
            self.columns.setColumnStretch(1, 2)
            self.columns.addWidget(self.left_stack, 0, 0)
            self.columns.addWidget(self.right_stack, 0, 1, Qt.AlignmentFlag.AlignTop)
