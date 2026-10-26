"""Native immutable Model list and detail views."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from alp_ui.components import Alert, Badge, Button, Card, DataTable, EmptyState, Text
from alp_ui.theme import ALPACA_LIGHT, make_icon
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QFontDatabase, QResizeEvent
from PySide6.QtWidgets import (
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

from biocall_studio_train.persistence.models import ModelArtifact, list_models


def _heading(title: str, subtitle: str, *, overline: str) -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(3)
    layout.addWidget(Text(overline, role="overline"))
    layout.addWidget(Text(title, role="title"))
    layout.addWidget(Text(subtitle, role="caption", word_wrap=True))
    return widget


def _metric(metric: dict[str, object]) -> str:
    value = metric["value"]
    return str(metric["reason"]) if value is None else f"{float(value):.3f}"


class ModelListModel(QAbstractTableModel):
    HEADERS = ("MODEL", "FAMILY", "DATASET", "CREATED", "")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._models: tuple[ModelArtifact, ...] = ()

    def set_models(self, models: tuple[ModelArtifact, ...]) -> None:
        self.beginResetModel()
        self._models = models
        self.endResetModel()

    def model_artifact(self, row: int) -> ModelArtifact:
        return self._models[row]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._models)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        artifact = self._models[index.row()]
        manifest = artifact.manifest
        family = "CNN" if manifest["family"] == "cnn" else "Random Forest"
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                f"{artifact.label}\n{artifact.model_id}",
                family,
                manifest["dataset_id"],
                manifest["created_at"].split("T", 1)[0],
                "Inspect →",
            )[index.column()]
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return f"{artifact.label}, {family}, Dataset {manifest['dataset_id']}"
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None


class ModelListPage(QScrollArea):
    def __init__(self, open_model: Callable[[str], None], open_datasets: Callable[[], None]):
        super().__init__()
        self.open_model = open_model
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAccessibleName("Models")
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(38, 30, 38, 38)
        layout.setSpacing(16)
        layout.addWidget(
            _heading(
                "Models",
                "Verified classifiers published by completed Training Runs.",
                overline="IMMUTABLE ARTIFACTS",
            )
        )
        self.error_alert = Alert("", title="Models could not be read", intent="danger")
        self.error_alert.hide()
        layout.addWidget(self.error_alert)
        self.model = ModelListModel(self)
        self.table = DataTable(model=self.model)
        self.table.setAccessibleName("Published Models")
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.table.clicked.connect(
            lambda index: self.open_model(self.model.model_artifact(index.row()).model_id)
        )
        layout.addWidget(self.table)
        action = Button("View Datasets")
        action.clicked.connect(open_datasets)
        self.empty = EmptyState(
            "No Models yet.",
            text="Start Training from an immutable Dataset to publish a verified Model.",
            icon=make_icon("info", color=ALPACA_LIGHT.colors.primary, size=28),
            action=action,
        )
        layout.addWidget(self.empty, 1)
        layout.addStretch()
        self.setWidget(content)

    def refresh(self, collection_root: Path | None) -> None:
        self.error_alert.hide()
        try:
            models = () if collection_root is None else list_models(collection_root)
        except (OSError, ValueError) as exc:
            models = ()
            self.error_alert.text_widget.setText(str(exc))
            self.error_alert.show()
        self.model.set_models(models)
        self.table.setVisible(bool(models))
        self.table.setFixedHeight(max(120, 44 + 48 * len(models)))
        self.empty.setVisible(not models and not self.error_alert.isVisible())


class ModelDetailPage(QScrollArea):
    def __init__(
        self,
        open_dataset: Callable[[str], None],
        open_run: Callable[[str], None],
        open_models: Callable[[], None],
    ):
        super().__init__()
        self.open_dataset = open_dataset
        self.open_run = open_run
        self.open_models = open_models
        self.artifact: ModelArtifact | None = None
        self.is_compact = False
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAccessibleName("Model detail")

    def set_model(self, artifact: ModelArtifact) -> None:
        self.artifact = artifact
        manifest = artifact.manifest
        old = self.takeWidget()
        if old is not None:
            old.deleteLater()
        self.content = QWidget()
        self.outer = QVBoxLayout(self.content)
        self.outer.setContentsMargins(38, 30, 38, 42)
        self.outer.setSpacing(16)
        self.outer.addWidget(Text(f"Models  /  {artifact.model_id}", role="caption"))
        is_rf = manifest["family"] == "random_forest"
        family_label = "Random Forest" if is_rf else "CNN"
        header = QHBoxLayout()
        header.addWidget(
            _heading(
                artifact.label,
                f"Published {family_label} classifier · read-only artifact",
                overline="MODEL",
            ),
            1,
        )
        header.addWidget(Badge("Verified", intent="success"), 0, Qt.AlignmentFlag.AlignTop)
        self.outer.addLayout(header)
        self.setAccessibleName(f"Model detail: {artifact.label} · {family_label}")

        summary = QGridLayout()
        summary.setSpacing(10)
        metrics = manifest["results"]["metrics"]
        for column, (label, value) in enumerate(
            (
                ("FAMILY", family_label),
                (
                    "DECISION THRESHOLD" if is_rf else "SELECTED EPOCH",
                    (
                        f"{manifest['random_forest']['decision_policy']['threshold']:.3f}"
                        if is_rf
                        else str(manifest["results"]["selected_epoch"])
                    ),
                ),
                ("VAL ACCURACY", _metric(metrics["accuracy"])),
                ("ARTIFACT", f"{manifest['artifact']['size_bytes'] / 1024:.1f} KiB"),
            )
        ):
            card = Card(shadow=False)
            card.content_layout.addWidget(Text(label, role="overline"))
            card.content_layout.addWidget(Text(value, role="heading"))
            summary.addWidget(card, 0, column)
        self.outer.addLayout(summary)

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

        overview = Card(shadow=False)
        overview.content_layout.addWidget(Text("Model details", role="subheading"))
        self.model_id = Text(artifact.model_id, role="body", selectable=True)
        detail_rows: tuple[tuple[str, QWidget], ...] = (
            ("Model ID", self.model_id),
            ("Dataset", Text(manifest["dataset_id"], role="body", selectable=True)),
            ("Training Run", Text(manifest["run_id"], role="body", selectable=True)),
            ("Created", Text(manifest["created_at"], role="body")),
            (
                "Task",
                Text(
                    "noise / target · target probability"
                    if is_rf
                    else "noise / target · categorical logits",
                    role="body",
                ),
            ),
        )
        for label, value in detail_rows:
            row = QHBoxLayout()
            row.addWidget(Text(label, role="caption"))
            row.addStretch()
            row.addWidget(value)
            overview.content_layout.addLayout(row)
        actions = QHBoxLayout()
        dataset_button = Button("Open Dataset", variant="outline")
        dataset_button.clicked.connect(lambda: self.open_dataset(manifest["dataset_id"]))
        actions.addWidget(dataset_button)
        self.review_run_button = Button("Review Training Run")
        self.review_run_button.clicked.connect(lambda: self.open_run(manifest["run_id"]))
        actions.addWidget(self.review_run_button)
        overview.content_layout.addLayout(actions)
        left.addWidget(overview)

        metrics_card = Card(shadow=False)
        metrics_card.content_layout.addWidget(Text("Validation metrics", role="subheading"))
        metrics_card.content_layout.addWidget(
            Text(
                (
                    "Measured on the immutable validation Split using the saved decision threshold."
                    if is_rf
                    else "Measured on the immutable validation Split using the selected checkpoint."
                ),
                role="caption",
                word_wrap=True,
            )
        )
        for name in ("accuracy", "precision", "recall", "f1", "roc_auc"):
            row = QHBoxLayout()
            row.addWidget(Text(name.replace("_", " ").upper(), role="caption"))
            row.addStretch()
            row.addWidget(Text(_metric(metrics[name]), role="body"))
            metrics_card.content_layout.addLayout(row)
        left.addWidget(metrics_card)

        files = Card(shadow=False)
        files.content_layout.addWidget(Text("Immutable files", role="subheading"))
        tree = QLabel(
            f"{artifact.model_id}/\n"
            "├── model.json   manifest + metrics + provenance\n"
            f"└── {manifest['artifact']['path']}   "
            f"{manifest['artifact']['sha256'][:12]}… sha256"
        )
        tree.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        tree.setAccessibleName("Model file tree")
        tree.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        files.content_layout.addWidget(tree)
        left.addWidget(files)

        boundary = Card(shadow=False)
        boundary.content_layout.addWidget(Text("Prediction not included", role="subheading"))
        boundary.content_layout.addWidget(
            Text(
                "This Trainer release creates and verifies the classifier. Running inference "
                "on new recordings belongs to a later, explicitly validated workflow.",
                role="body",
                word_wrap=True,
            )
        )
        boundary.content_layout.addWidget(
            Alert(
                "No prediction was run and no scientific result is implied.",
                title="Training artifact only",
                intent="info",
            )
        )
        right.addWidget(boundary)

        provenance = Card(shadow=False)
        provenance.content_layout.addWidget(Text("Provenance", role="subheading"))
        provenance_rows = [
            ("Trainer", manifest["provenance"]["trainer"]["version"]),
            ("Toolbox", manifest["provenance"]["toolbox"]["version"]),
            ("Toolbox revision", manifest["provenance"]["toolbox"]["revision"][:12]),
        ]
        if is_rf:
            provenance_rows.extend(
                (
                    ("scikit-learn", manifest["provenance"]["scikit_learn_version"]),
                    ("Librosa", manifest["provenance"]["librosa_version"]),
                )
            )
        else:
            provenance_rows.append(("PyTorch", manifest["provenance"]["torch_version"]))
        for label, value in provenance_rows:
            row = QHBoxLayout()
            row.addWidget(Text(label, role="caption"))
            row.addStretch()
            row.addWidget(Text(str(value), role="body", selectable=True))
            provenance.content_layout.addLayout(row)
        right.addWidget(provenance)
        back = Button("← All Models", variant="outline")
        back.clicked.connect(self.open_models)
        right.addWidget(back, 0, Qt.AlignmentFlag.AlignLeft)
        right.addStretch()

        self.outer.addLayout(self.columns)
        self.outer.addStretch()
        self.setWidget(self.content)
        self._place_columns(self.viewport().width() < 850)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.artifact is not None and hasattr(self, "columns"):
            self._place_columns(event.size().width() < 850)

    def _place_columns(self, compact: bool) -> None:
        self.is_compact = compact
        self.columns.removeWidget(self.left_stack)
        self.columns.removeWidget(self.right_stack)
        if compact:
            self.content.setMaximumWidth(max(320, self.viewport().width()))
            self.columns.setColumnStretch(1, 0)
            self.columns.addWidget(self.left_stack, 0, 0)
            self.columns.addWidget(self.right_stack, 1, 0)
        else:
            self.content.setMaximumWidth(16_777_215)
            self.columns.setColumnStretch(0, 3)
            self.columns.setColumnStretch(1, 2)
            self.columns.addWidget(self.left_stack, 0, 0)
            self.columns.addWidget(self.right_stack, 0, 1, Qt.AlignmentFlag.AlignTop)
