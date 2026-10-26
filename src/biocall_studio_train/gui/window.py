"""Collection-first native shell composed from public alp-ui widgets."""

from __future__ import annotations

import logging
from pathlib import Path

from alp_ui.components import (
    Alert,
    Badge,
    Button,
    Card,
    DataTable,
    Divider,
    EmptyState,
    FolderPicker,
    HelpHint,
    ProgressBar,
    Text,
)
from alp_ui.theme import ALPACA_LIGHT, interactions, make_icon
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices, QFontDatabase, QResizeEvent
from PySide6.QtWidgets import (
    QBoxLayout,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from biocall_studio_train.application.workspace import WorkspaceController
from biocall_studio_train.gui.branding import application_icon
from biocall_studio_train.gui.collection import CollectionPage, ReadingCollectionPage
from biocall_studio_train.gui.dataset import DatasetBuilderPage, DatasetDetailPage, DatasetListPage
from biocall_studio_train.gui.model import ModelDetailPage, ModelListPage
from biocall_studio_train.gui.power import KEEP_AWAKE_HELP, KeepAwakeControl
from biocall_studio_train.gui.run import RunDetailPage, RunListPage
from biocall_studio_train.gui.training import TrainingPage, TrainingWikiPage
from biocall_studio_train.persistence.datasets import load_dataset
from biocall_studio_train.persistence.models import load_model
from biocall_studio_train.persistence.training_presets import PresetStore

_ROUTES = (
    ("select", "Select Collection", "plus"),
    ("collections", "Collections", "folder"),
    ("datasets", "Datasets", "grid"),
    ("models", "Models", "info"),
    ("runs", "Runs", "list"),
    ("wiki", "Wiki", "info"),
    ("settings", "Settings", "settings"),
)


class _EmptyArtifactModel(QAbstractTableModel):
    """A real model/view seam for later artifact lists, deliberately with no rows."""

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0


class SelectCollectionPage(QScrollArea):
    """The picker communicates intent; it never scans or validates a Collection."""

    def __init__(self, controller: WorkspaceController, open_wiki):
        super().__init__()
        self.controller = controller
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAccessibleName("Select Collection")

        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(30, 36, 30, 44)
        outer.setSpacing(18)

        hero = QWidget()
        self.hero = hero
        hero.setMaximumWidth(780)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(0, 0, 0, 0)
        hero_layout.setSpacing(10)
        eyebrow = Text("COLLECTION → DATASET → MODEL", role="overline")
        eyebrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(eyebrow)
        title = Text("Train from a collection", role="title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(title)
        subtitle = Text(
            "Choose a local folder of WAV recordings and labeled positive snippets.",
            role="body",
            word_wrap=True,
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(subtitle)
        outer.addWidget(hero, 0, Qt.AlignmentFlag.AlignHCenter)

        card = Card()
        self.card = card
        card.setMaximumWidth(780)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(3)
        heading.addWidget(Text("Select Collection", role="subheading"))
        header.addLayout(heading)
        header.addStretch()
        header.addWidget(
            HelpHint(
                "Choose a folder with recordings/ and positives/. Trainer doesn't copy your "
                "WAV files. Each labeled clip filename includes when it occurs in the full "
                "recording.",
                subject="Collection folders",
            )
        )
        card.content_layout.addLayout(header)

        choose_panel = QFrame()
        choose_panel.setObjectName("collectionChoice")
        choose_panel.setAccessibleName("Collection folder structure and selection")
        choose_panel.setStyleSheet(
            f"QFrame#collectionChoice {{ background: {ALPACA_LIGHT.colors.background}; "
            f"border: 1px dashed {ALPACA_LIGHT.colors.border}; border-radius: 10px; }}"
        )
        choose_layout = QVBoxLayout(choose_panel)
        choose_layout.setContentsMargins(26, 24, 26, 24)
        choose_layout.setSpacing(9)
        folder_icon = QLabel()
        folder_icon.setPixmap(
            make_icon("folder", color=ALPACA_LIGHT.colors.primary, size=28).pixmap(28, 28)
        )
        folder_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        choose_layout.addWidget(folder_icon)
        self.structure_title = Text("One folder, two subfolders", role="subheading")
        self.structure_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        choose_layout.addWidget(self.structure_title)
        structure = Text("recordings/   +   positives/", role="caption")
        structure.setAlignment(Qt.AlignmentFlag.AlignCenter)
        choose_layout.addWidget(structure)

        self.folder_picker = FolderPicker()
        self.folder_picker.setMaximumWidth(600)
        choose = self.folder_picker.choose_button
        choose.setText("Select folder")
        choose.setAccessibleName("Select Collection folder")
        choose.setIcon(make_icon("folder", color=ALPACA_LIGHT.colors.on_primary, size=16))
        choose.variant = "primary"
        choose.setMinimumHeight(44)
        state = interactions(ALPACA_LIGHT)
        choose.setStyleSheet(
            f"QPushButton {{ background: {ALPACA_LIGHT.colors.primary}; "
            f"color: {ALPACA_LIGHT.colors.on_primary}; border: 1px solid "
            f"{ALPACA_LIGHT.colors.primary}; border-radius: 8px; padding: 0 20px; }}"
            f"QPushButton:hover {{ background: {ALPACA_LIGHT.colors.primary_hover}; }}"
            f"QPushButton:focus {{ border: 1px solid {state.focus}; }}"
        )
        choose_layout.addWidget(self.folder_picker)

        self.wiki_button = Button("How should my folder look? →", variant="outline", size="small")
        self.wiki_button.setAccessibleName("How should my folder look?")
        self.wiki_button.clicked.connect(open_wiki)
        choose_layout.addWidget(self.wiki_button, 0, Qt.AlignmentFlag.AlignHCenter)
        card.content_layout.addWidget(choose_panel)

        self.retry_scan_button = Button("Scan again", variant="outline", size="small")
        self.retry_scan_button.clicked.connect(controller.rescan)
        self.pending_alert = Alert(
            "",
            title="Selection pending",
            intent="info",
            action=self.retry_scan_button,
        )
        self.pending_alert.hide()
        card.content_layout.addWidget(self.pending_alert)
        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch()
        self.setWidget(content)

        self.folder_picker.folderChanged.connect(controller.request_collection)
        controller.pending_changed.connect(self._refresh_pending)
        self._refresh_pending()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        content_width = max(320, min(780, self.viewport().width() - 80))
        self.hero.setFixedWidth(content_width)
        self.card.setFixedWidth(content_width)

    def _refresh_pending(self) -> None:
        pending = self.controller.pending_collection_path
        if pending is None:
            self.pending_alert.hide()
            return
        message = f"{pending.name} is selected and awaiting Collection validation."
        self.pending_alert.text_widget.setText(message)
        self.pending_alert.setAccessibleDescription(message)
        self.pending_alert.show()


class WikiPage(QScrollArea):
    """Static Collection guidance, intentionally independent of scanner behavior."""

    def __init__(self, select_collection):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAccessibleName("Wiki")
        self._compact = False

        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(38, 30, 38, 38)
        outer.setSpacing(18)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(4)
        heading.addWidget(Text("WIKI", role="overline"))
        heading.addWidget(Text("Selecting a Collection", role="title"))
        header.addLayout(heading)
        header.addStretch()
        self.select_button = Button("Select Collection")
        self.select_button.setIcon(
            make_icon("folder", color=ALPACA_LIGHT.colors.on_primary, size=16)
        )
        self.select_button.clicked.connect(select_collection)
        header.addWidget(self.select_button, 0, Qt.AlignmentFlag.AlignTop)
        outer.addLayout(header)

        self.cards = QGridLayout()
        self.cards.setSpacing(16)
        self.folder_card = self._folder_card()
        self.timestamps_card = self._timestamps_card()
        self.validation_card = self._validation_card()
        self.messages_card = self._messages_card()
        outer.addLayout(self.cards)
        self.keep_awake_card = Card(shadow=False)
        self.keep_awake_title = Text("Keep computer awake", role="subheading")
        self.keep_awake_title.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.keep_awake_card.content_layout.addWidget(self.keep_awake_title)
        self.keep_awake_text = Text(KEEP_AWAKE_HELP, role="body", word_wrap=True)
        self.keep_awake_card.content_layout.addWidget(self.keep_awake_text)
        outer.addWidget(self.keep_awake_card)
        outer.addStretch()
        self.setWidget(content)
        self._place_cards(False)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        compact = event.size().width() < 850
        if compact != self._compact:
            self._compact = compact
            self._place_cards(compact)

    def _place_cards(self, compact: bool) -> None:
        for card in (
            self.folder_card,
            self.timestamps_card,
            self.validation_card,
            self.messages_card,
        ):
            self.cards.removeWidget(card)
        if compact:
            for row, card in enumerate(
                (self.folder_card, self.timestamps_card, self.validation_card, self.messages_card)
            ):
                self.cards.addWidget(card, row, 0)
        else:
            self.cards.addWidget(self.folder_card, 0, 0)
            self.cards.addWidget(self.validation_card, 0, 1)
            self.cards.addWidget(self.timestamps_card, 1, 0)
            self.cards.addWidget(self.messages_card, 1, 1)
            self.cards.setColumnStretch(0, 3)
            self.cards.setColumnStretch(1, 2)

    @staticmethod
    def _folder_card() -> Card:
        card = Card(shadow=False)
        card.content_layout.addWidget(Text("1 · Create these folders", role="subheading"))
        tree = QLabel(
            "Rainforest-dawn/  ← select this folder\n"
            "  ├─ recordings/\n"
            "  │  SITE_001.wav\n"
            "  │  SITE_002.wav\n"
            "  └─ positives/\n"
            "     SITE_001__start-012500ms__end-014900ms__call01.wav\n"
            "     SITE_002__start-001200ms__end-003600ms__call01.wav"
        )
        fixed_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        fixed_font.setPointSize(12)
        tree.setFont(fixed_font)
        tree.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        tree.setAccessibleName("Collection folder layout")
        card.content_layout.addWidget(tree)
        return card

    @staticmethod
    def _timestamps_card() -> Card:
        card = Card(shadow=False)
        header = QHBoxLayout()
        header.addWidget(Text("2 · Put times in each positive WAV name", role="subheading"))
        header.addWidget(
            HelpHint("Use whole milliseconds. 1000 ms equals 1 second.", subject="Clip times")
        )
        header.addStretch()
        card.content_layout.addLayout(header)
        card.content_layout.addWidget(Text("The times refer to the full recording.", role="body"))
        example = QLabel("SITE_001__start-012500ms__end-014900ms__call01.wav")
        fixed_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        fixed_font.setPointSize(12)
        example.setFont(fixed_font)
        example.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        example.setAccessibleName("Positive filename source-time example")
        card.content_layout.addWidget(example)
        for label, value in (
            ("Source Recording", "SITE_001.wav"),
            ("Start", "12.500 s"),
            ("End", "14.900 s"),
            ("Positive WAV duration", "2.400 s"),
        ):
            row = QHBoxLayout()
            row.addWidget(Text(label, role="caption"))
            row.addStretch()
            row.addWidget(Text(value, role="body"))
            card.content_layout.addLayout(row)
        return card

    @staticmethod
    def _validation_card() -> Card:
        card = Card(shadow=False)
        card.content_layout.addWidget(Text("3 · Validation", role="subheading"))
        for title, detail in (
            ("Folder layout", "recordings/ and positives/ exist; WAVs are directly inside."),
            ("Names", "Each positive names exactly one complete Source Recording stem."),
            ("Time intervals", "Start comes before end; end is inside the original recording."),
            ("WAV headers", "Readable audio; positive duration agrees with filename times."),
            ("Collisions", "Duplicate names and duplicate positive intervals are rejected."),
        ):
            card.content_layout.addWidget(Text(title, role="body"))
            card.content_layout.addWidget(Text(detail, role="caption", word_wrap=True))
        return card

    @staticmethod
    def _messages_card() -> Card:
        card = Card(shadow=False)
        card.content_layout.addWidget(Text("Typical validation messages", role="subheading"))
        for title, detail in (
            ("Unknown Source Recording", "Match the positive prefix to an existing WAV name."),
            ("Missing timestamps", "Add __start-…ms and __end-…ms to the filename."),
            ("Snippet outside recording", "Correct the timestamp or choose the right recording."),
            ("Duration mismatch", "Make the clip length agree with the named interval."),
        ):
            card.content_layout.addWidget(Text(title, role="body"))
            card.content_layout.addWidget(Text(detail, role="caption", word_wrap=True))
        return card


class SettingsPage(QScrollArea):
    """Explain the machine-local binding without inventing a scanner or rebind UI."""

    def __init__(
        self,
        controller: WorkspaceController,
        open_diagnostics,
        export_diagnostics,
        open_power_wiki,
    ):
        super().__init__()
        self.controller = controller
        self.is_compact = False
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAccessibleName("Settings")
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(38, 30, 38, 38)
        layout.setSpacing(18)
        layout.addWidget(Text("LOCAL FOLDERS", role="overline"))
        layout.addWidget(Text("Settings", role="title"))

        grid = QGridLayout()
        self.grid = grid
        grid.setSpacing(16)
        binding = Card(shadow=False)
        self.binding_card = binding
        binding_header = QHBoxLayout()
        binding_header.addWidget(Text("Collection folders", role="subheading"))
        binding_header.addStretch()
        binding_header.addWidget(
            HelpHint(
                "This is the folder currently open in Trainer. Changing it doesn't move or "
                "copy files.",
                subject="Collection folders",
            )
        )
        binding.content_layout.addLayout(binding_header)
        self.binding_value = Text("", role="body", word_wrap=True)
        for label, value in (
            ("Verified Collection binding", self.binding_value),
            ("Recordings / positives", Text("Read-only WAVs", role="body")),
            ("Collection summary", Text(".alpaca/collection.json", role="body")),
            ("Datasets and Models", Text(".alpaca/ inside Collection", role="body")),
            ("Binding", Text("Local Application Settings", role="body")),
        ):
            binding.content_layout.addWidget(Text(label, role="caption"))
            binding.content_layout.addWidget(value)
            binding.content_layout.addWidget(Divider())
        self.error_alert = Alert("", title="Application Settings", intent="danger")
        self.error_alert.hide()
        binding.content_layout.addWidget(self.error_alert)
        grid.addWidget(binding, 0, 0)

        grid.setColumnStretch(0, 1)
        layout.addLayout(grid)

        power = Card(shadow=False)
        self.power_card = power
        power.content_layout.addWidget(Text("Power / long-running work", role="subheading"))
        self.power_control = KeepAwakeControl(controller, open_power_wiki)
        power.content_layout.addWidget(self.power_control)
        self.keep_awake_toggle = self.power_control.toggle
        self.keep_awake_status = self.power_control.status
        self.keep_awake_hint = self.power_control.hint
        self.keep_awake_wiki_button = self.power_control.wiki_button
        self.keep_awake_retry_button = self.power_control.retry_button
        self.keep_awake_error = self.power_control.error
        layout.addWidget(power)

        diagnostics = Card(shadow=False)
        self.diagnostics_card = diagnostics
        diagnostics.content_layout.addWidget(Text("Diagnostics", role="subheading"))
        diagnostic_actions = QHBoxLayout()
        self.open_diagnostics_button = Button(
            "Open diagnostics folder", variant="outline", size="small"
        )
        self.open_diagnostics_button.setAccessibleDescription(
            "Open the local folder containing this application's session logs."
        )
        self.open_diagnostics_button.clicked.connect(self._open_diagnostics)
        diagnostic_actions.addWidget(self.open_diagnostics_button)
        self.export_diagnostics_button = Button(
            "Export diagnostics…", variant="secondary", size="small"
        )
        self.export_diagnostics_button.setAccessibleDescription(
            "Review a privacy notice, then save a sanitized local support ZIP."
        )
        self.export_diagnostics_button.clicked.connect(self._export_diagnostics)
        diagnostic_actions.addWidget(self.export_diagnostics_button)
        diagnostic_actions.addStretch()
        diagnostics.content_layout.addLayout(diagnostic_actions)
        self.diagnostics_alert = Alert("", title="Diagnostics", intent="neutral")
        self.diagnostics_alert.hide()
        diagnostics.content_layout.addWidget(self.diagnostics_alert)
        layout.addWidget(diagnostics)
        layout.addStretch()
        self.setWidget(content)

        controller.changed.connect(self._refresh)
        self._open_diagnostics_callback = open_diagnostics
        self._export_diagnostics_callback = export_diagnostics
        self._refresh()
        if controller.error_message:
            self.error_alert.text_widget.setText(controller.error_message)
            self.error_alert.show()
        if not controller.diagnostics_available:
            self._show_diagnostics_feedback(controller.diagnostics_unavailable_message)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._place_cards(event.size().width() < 850)

    def _place_cards(self, compact: bool) -> None:
        self.is_compact = compact
        self.grid.removeWidget(self.binding_card)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 0)
        self.grid.addWidget(self.binding_card, 0, 0)

    def _refresh(self) -> None:
        path = self.controller.collection_path
        self.binding_value.setText(str(path) if path else "No Collection has been validated.")

    def _show_diagnostics_feedback(self, message: str) -> None:
        self.diagnostics_alert.text_widget.setText(message)
        self.diagnostics_alert.setAccessibleName(f"Diagnostics: {message}")
        self.diagnostics_alert.show()

    def _open_diagnostics(self) -> None:
        self._show_diagnostics_feedback(self._open_diagnostics_callback())

    def _export_diagnostics(self) -> None:
        message = self._export_diagnostics_callback()
        if message:
            self._show_diagnostics_feedback(message)


class MainWindow(QMainWindow):
    """Native Collection-first shell with background Scan navigation."""

    def __init__(self, controller: WorkspaceController):
        super().__init__()
        self.controller = controller
        self.current_route = "select"
        self.is_compact = False
        self.setWindowTitle("BioCall Studio Train")
        self.setWindowIcon(application_icon())
        self.resize(1180, 790)
        self.setMinimumSize(640, 620)
        self._navigation: dict[str, QPushButton] = {}
        self._pages: dict[str, QWidget] = {}
        self.close_dialog: QMessageBox | None = None
        self._close_keep_button = None
        self._close_stop_button = None
        self._exit_requested = False
        self._exit_ready = False

        central = QWidget()
        self._root_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, central)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)
        self.sidebar = self._build_sidebar()
        self._root_layout.addWidget(self.sidebar)

        body = QWidget()
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(0)
        self.body_layout.addWidget(self._build_global_header())
        self.pages = QStackedWidget()
        self.select_page = SelectCollectionPage(controller, lambda: self.navigate("wiki"))
        self.scan_page = ReadingCollectionPage(controller)
        self.collection_page = CollectionPage(
            controller,
            lambda: self.navigate("select"),
            self.open_builder,
            lambda: self.navigate("wiki"),
        )
        self.builder_page = DatasetBuilderPage(controller)
        self.dataset_list_page = DatasetListPage(controller, self.open_builder, self.open_dataset)
        self.dataset_detail_page = DatasetDetailPage(
            self._delete_dataset,
            controller.rename_dataset,
            controller.dataset_name,
            lambda: self.navigate("collection"),
            self.open_training,
        )
        self.training_page = TrainingPage(
            controller,
            PresetStore(controller.settings_file.parent / "training-presets"),
            self._open_training_wiki,
            self._open_power_wiki,
        )
        self.training_page.draft_status_changed.connect(self._set_training_draft_open)
        self.training_page.draft_discarded.connect(lambda: self.navigate("datasets"))
        self.training_wiki_page = TrainingWikiPage(self._return_from_training_wiki)
        self.run_list_page = RunListPage(self.open_run, lambda: self.navigate("select"))
        self.run_detail_page = RunDetailPage(
            controller.cancel_active_run,
            self._open_run_output,
            lambda: self.navigate("runs"),
            self._open_run_log,
            lambda run_id: controller.worker_log_for_run(run_id) is not None,
            controller.rename_run,
            self._delete_run,
        )
        self.model_list_page = ModelListPage(
            controller,
            self.open_model,
            lambda: self.navigate("datasets"),
        )
        self.model_detail_page = ModelDetailPage(
            self.open_dataset,
            self.open_run,
            lambda: self.navigate("models"),
            controller.rename_model,
            self._delete_model,
            controller.model_name,
            lambda dataset_id, fallback: self._dataset_name(dataset_id, fallback),
        )
        self.wiki_page = WikiPage(lambda: self.navigate("select"))
        self.wiki_select_button = self.wiki_page.select_button
        self.settings_page = SettingsPage(
            controller,
            self._open_diagnostics_folder,
            self._export_diagnostics,
            self._open_power_wiki,
        )
        self.empty_pages: dict[str, EmptyState] = {}
        for route, page in (
            ("select", self.select_page),
            ("scan", self.scan_page),
            ("collection", self.collection_page),
            (
                "collections",
                self._empty_artifact_page(
                    "Collections", "Folders validated for local training.", "No Collections yet."
                ),
            ),
            ("datasets", self.dataset_list_page),
            ("builder", self.builder_page),
            ("dataset-detail", self.dataset_detail_page),
            ("training", self.training_page),
            ("training-wiki", self.training_wiki_page),
            ("models", self.model_list_page),
            ("model-detail", self.model_detail_page),
            ("runs", self.run_list_page),
            ("run-detail", self.run_detail_page),
            ("wiki", self.wiki_page),
            ("settings", self.settings_page),
        ):
            self._pages[route] = page
            self.pages.addWidget(page)
        self.empty_pages["datasets"] = self.dataset_list_page.empty
        self.empty_pages["models"] = self.model_list_page.empty
        self.empty_pages["runs"] = self.run_list_page.empty
        self.body_layout.addWidget(self.pages, 1)
        self._root_layout.addWidget(body, 1)
        self.setCentralWidget(central)
        controller.scan_started.connect(self._scan_started)
        controller.scan_progress_changed.connect(self.scan_page.refresh)
        controller.scan_completed.connect(self._scan_completed)
        controller.scan_cancelled.connect(lambda: self.navigate("select"))
        controller.scan_failed.connect(self._scan_failed)
        controller.build_started.connect(self._build_started)
        controller.build_completed.connect(self._dataset_built)
        controller.build_failed.connect(self._build_failed)
        controller.build_cancelled.connect(self._build_cancelled)
        controller.training_started.connect(self._training_started)
        controller.training_completed.connect(self._model_trained)
        controller.training_failed.connect(self._training_failed)
        controller.training_cancelled.connect(self._training_cancelled)
        controller.run_changed.connect(self._run_changed)
        controller.runs_changed.connect(self._refresh_run_surfaces)
        controller.run_conflict.connect(self._show_run_conflict)
        controller.shutdown_ready.connect(self._shutdown_ready)
        self.navigate("select")
        self._refresh_run_surfaces()
        controller.reopen_bound_collection()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_responsive_layout(event.size().width() < 820)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._exit_ready:
            event.accept()
            super().closeEvent(event)
            return
        if self._exit_requested:
            event.ignore()
            return
        if self.controller.active_run is not None:
            event.ignore()
            self._show_active_close_dialog()
            return
        if self.controller.is_scanning:
            event.ignore()
            self._begin_exit()
            return
        self.controller.finalize_shutdown()
        event.accept()
        super().closeEvent(event)

    def _show_active_close_dialog(self) -> None:
        if self.close_dialog is not None and self.close_dialog.isVisible():
            self.close_dialog.raise_()
            self.close_dialog.activateWindow()
            return
        run = self.controller.active_run
        if run is None:
            return
        if run.kind.value == "dataset_build":
            family = "Dataset Build"
        elif run.training_family == "cnn":
            family = "CNN Training"
        else:
            family = "Random Forest Training"
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Active Run")
        dialog.setText(f"{family} is still active: {run.title}")
        dialog.setInformativeText(
            "If you exit, work in progress will be lost. Trainer will stop the Worker before "
            "closing; no partially trained Dataset or Model and no resumable checkpoint will "
            "be kept. Earlier published artifacts remain unchanged."
        )
        keep = dialog.addButton("Keep app open", QMessageBox.ButtonRole.RejectRole)
        stop = dialog.addButton("Stop Run and Exit", QMessageBox.ButtonRole.DestructiveRole)
        keep.setAccessibleDescription("Dismiss this warning and leave the Active Run untouched.")
        stop.setAccessibleDescription("Cancel the Active Run, wait for its Worker, then exit.")
        dialog.setDefaultButton(keep)
        dialog.setEscapeButton(keep)
        self.close_dialog = dialog
        self._close_keep_button = keep
        self._close_stop_button = stop
        dialog.finished.connect(self._close_dialog_finished)
        dialog.open()
        keep.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def _close_dialog_finished(self, _result: int) -> None:
        dialog = self.close_dialog
        if dialog is None:
            return
        stop_requested = dialog.clickedButton() is self._close_stop_button
        self.close_dialog = None
        self._close_keep_button = None
        self._close_stop_button = None
        dialog.deleteLater()
        if stop_requested:
            if self.controller.active_run is not None:
                self.open_run(self.controller.active_run.run_id)
            self._begin_exit()

    def _begin_exit(self) -> None:
        if self._exit_requested:
            return
        self._exit_requested = True
        self.controller.request_shutdown()

    def _shutdown_ready(self) -> None:
        if self._exit_requested:
            QTimer.singleShot(0, self._finish_exit)

    def _finish_exit(self) -> None:
        if not self._exit_requested or self._exit_ready:
            return
        self.controller.finalize_shutdown()
        self._exit_ready = True
        self.close()

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("trainerSidebar")
        sidebar.setAccessibleName("Application navigation")
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(
            f"QFrame#trainerSidebar {{ background: {ALPACA_LIGHT.colors.surface}; "
            f"border-right: 1px solid {ALPACA_LIGHT.colors.border}; }}"
        )
        self.sidebar_layout = QVBoxLayout(sidebar)
        self.sidebar_layout.setContentsMargins(18, 27, 18, 18)
        self.sidebar_layout.setSpacing(7)

        self.brand = QWidget()
        brand_layout = QHBoxLayout(self.brand)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        self.brand_icon = QLabel()
        self.brand_icon.setAccessibleName("BioCall Studio Train logo")
        self.brand_icon.setPixmap(application_icon().pixmap(32, 32))
        brand_layout.addWidget(self.brand_icon)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        self.brand_title = Text("BioCall Studio", role="subheading")
        self.brand_subtitle = Text("TRAIN", role="overline")
        brand_text.addWidget(self.brand_title)
        brand_text.addWidget(self.brand_subtitle)
        brand_layout.addLayout(brand_text)
        brand_layout.addStretch()
        self.sidebar_layout.addWidget(self.brand)
        self.sidebar_layout.addSpacing(25)
        self.nav_label = Text("WORKSPACE", role="overline")
        self.sidebar_layout.addWidget(self.nav_label)

        self.nav_scroll = QScrollArea()
        self.nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.nav_scroll.setWidgetResizable(True)
        self.nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.nav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav_scroll.setStyleSheet("QScrollArea { background: transparent; border: 0; }")
        nav_content = QWidget()
        self.navigation_layout = QBoxLayout(QBoxLayout.Direction.TopToBottom, nav_content)
        self.navigation_layout.setContentsMargins(0, 0, 0, 0)
        self.navigation_layout.setSpacing(7)
        for route, label, icon in _ROUTES:
            button = QPushButton(label)
            button.setAccessibleName(f"{label} navigation")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(38)
            button.setIcon(make_icon(icon, color=ALPACA_LIGHT.colors.text_muted, size=18))
            button.clicked.connect(lambda checked=False, target=route: self.navigate(target))
            button.setProperty("icon_name", icon)
            self._navigation[route] = button
            self.navigation_layout.addWidget(button)
        self.navigation_layout.addStretch()
        self.nav_scroll.setWidget(nav_content)
        self.sidebar_layout.addWidget(self.nav_scroll, 1)

        self.sidebar_footer = QWidget()
        footer = QVBoxLayout(self.sidebar_footer)
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(6)
        self.sidebar_layout.addWidget(self.sidebar_footer)
        return sidebar

    def _build_global_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("globalHeader")
        header.setStyleSheet(
            f"QFrame#globalHeader {{ background: {ALPACA_LIGHT.colors.surface}; "
            f"border-bottom: 1px solid {ALPACA_LIGHT.colors.border}; }}"
        )
        layout = QHBoxLayout(header)
        layout.setContentsMargins(38, 16, 38, 16)
        icon = QLabel()
        icon.setPixmap(make_icon("list", color=ALPACA_LIGHT.colors.primary).pixmap(22, 22))
        layout.addWidget(icon)
        layout.addStretch()
        self.open_draft_button = Button("Training setup · Open →", variant="outline", size="small")
        self.open_draft_button.clicked.connect(lambda: self.navigate("training"))
        self.open_draft_button.hide()
        layout.addWidget(self.open_draft_button)
        active = QVBoxLayout()
        active.setSpacing(0)
        active.addWidget(Text("ACTIVE RUN", role="overline"))
        self.active_run_label = Text("No Active Run", role="body")
        active.addWidget(self.active_run_label)
        layout.addLayout(active)
        layout.addSpacing(18)
        self.idle_run_badge = Badge("Idle", intent="neutral")
        self.working_run_badge = Badge("Working", intent="warning")
        self.working_run_badge.hide()
        layout.addWidget(self.idle_run_badge)
        layout.addWidget(self.working_run_badge)
        self.active_run_progress = ProgressBar()
        self.active_run_progress.setFixedWidth(135)
        self.active_run_progress.setTextVisible(False)
        self.active_run_progress.setAccessibleName("Active Run progress")
        self.active_run_progress.hide()
        layout.addWidget(self.active_run_progress)
        self.view_run_button = Button("View Run →", variant="outline", size="small")
        self.view_run_button.clicked.connect(self._open_active_run)
        self.view_run_button.hide()
        layout.addWidget(self.view_run_button)
        return header

    def _set_training_draft_open(self, is_open: bool) -> None:
        self.open_draft_button.setVisible(is_open)

    def _empty_artifact_page(self, label: str, subtitle: str, title: str) -> QWidget:
        page = QWidget()
        page.setAccessibleName(label)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(38, 30, 38, 30)
        layout.setSpacing(10)
        layout.addWidget(Text(label.upper(), role="overline"))
        layout.addWidget(Text(label, role="title"))
        layout.addSpacing(14)
        action = Button("Select Collection")
        action.setIcon(make_icon("plus", color=ALPACA_LIGHT.colors.on_primary, size=16))
        action.clicked.connect(lambda: self.navigate("select"))
        empty = EmptyState(
            title,
            text="Choose a Collection to begin.",
            icon=make_icon("folder", color=ALPACA_LIGHT.colors.primary, size=28),
            action=action,
        )
        self.empty_pages[label.lower()] = empty
        layout.addWidget(empty, 1)
        table = DataTable(model=_EmptyArtifactModel(page))
        table.setAccessibleName(f"{label} table")
        table.setVisible(False)
        layout.addWidget(table)
        return page

    def _apply_responsive_layout(self, compact: bool) -> None:
        if compact == self.is_compact:
            return
        self.is_compact = compact
        if compact:
            self._root_layout.setDirection(QBoxLayout.Direction.TopToBottom)
            self.sidebar.setMinimumWidth(0)
            self.sidebar.setMaximumWidth(16_777_215)
            self.sidebar.setFixedHeight(132)
            self.sidebar_layout.setContentsMargins(16, 12, 16, 8)
            self.sidebar_layout.setSpacing(4)
            self.navigation_layout.setDirection(QBoxLayout.Direction.LeftToRight)
            self.nav_scroll.setFixedHeight(49)
            self.nav_label.hide()
            self.sidebar_footer.hide()
            for button in self._navigation.values():
                button.setMinimumWidth(150)
                button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        else:
            self._root_layout.setDirection(QBoxLayout.Direction.LeftToRight)
            self.sidebar.setMinimumWidth(220)
            self.sidebar.setMaximumWidth(220)
            self.sidebar.setMinimumHeight(0)
            self.sidebar.setMaximumHeight(16_777_215)
            self.sidebar_layout.setContentsMargins(18, 27, 18, 18)
            self.sidebar_layout.setSpacing(7)
            self.navigation_layout.setDirection(QBoxLayout.Direction.TopToBottom)
            self.nav_scroll.setMinimumHeight(0)
            self.nav_scroll.setMaximumHeight(16_777_215)
            self.nav_label.show()
            self.sidebar_footer.show()
            for button in self._navigation.values():
                button.setMinimumWidth(0)
                button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def navigate(self, route: str) -> None:
        """Show a named route and place keyboard focus on its first meaningful action."""
        if route == "collections" and self.controller.scan_result is not None:
            route = "collection"
        if route not in self._pages:
            raise ValueError(f"Unknown route: {route}")
        self.current_route = route
        self.pages.setCurrentWidget(self._pages[route])
        colors = ALPACA_LIGHT.colors
        selected = interactions(ALPACA_LIGHT).selected_surface
        active_route = (
            "collections"
            if route == "collection"
            else "select"
            if route == "scan"
            else "datasets"
            if route in {"builder", "dataset-detail"}
            else "models"
            if route in {"training", "model-detail"}
            else "wiki"
            if route == "training-wiki"
            else "runs"
            if route == "run-detail"
            else route
        )
        for name, button in self._navigation.items():
            current = name == active_route
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
                f"QPushButton {{ text-align: left; border: 0; border-radius: 8px; padding: 0 14px; "
                f"background: {selected if current else 'transparent'}; "
                f"color: {colors.primary_hover if current else colors.text_muted}; "
                f"font-weight: {600 if current else 400}; }}"
                f"QPushButton:hover {{ background: {selected}; color: {colors.primary_hover}; }}"
                f"QPushButton:focus {{ border: 1px solid {colors.info}; }}"
            )
        if route == "select":
            layout = self.select_page.widget().layout()
            layout.invalidate()
            layout.activate()
            self.select_page.folder_picker.choose_button.setFocus()
        elif route == "wiki":
            self.wiki_select_button.setFocus()
        elif route == "scan":
            self.scan_page.cancel_button.setFocus()
        elif route == "collection":
            target = (
                self.collection_page.build_button
                if self.collection_page.build_button.isEnabled()
                else self.collection_page.rescan_button
            )
            target.setFocus()
        elif route == "datasets":
            self.dataset_list_page.refresh(self.controller.collection_path)
            target = (
                self.dataset_list_page.table
                if self.dataset_list_page.model.rowCount()
                else self.dataset_list_page.empty.action_widget
            )
            target.setFocus()
        elif route == "builder":
            self.builder_page.build_button.setFocus()
        elif route == "dataset-detail":
            self.dataset_detail_page.delete_button.setFocus()
        elif route == "training":
            self.training_page.family_input.control.setFocus()
        elif route == "training-wiki":
            self.training_wiki_page.back_button.setFocus()
        elif route == "models":
            self.model_list_page.refresh(self.controller.collection_path)
            target = (
                self.model_list_page.table
                if self.model_list_page.model.rowCount()
                else self.model_list_page.empty
            )
            target.setFocus()
        elif route == "model-detail":
            if self.model_detail_page.artifact is not None:
                self.model_detail_page.review_run_button.setFocus()
        elif route == "runs":
            self._refresh_run_surfaces()
            target = (
                self.run_list_page.table
                if self.run_list_page.model.rowCount()
                else self.run_list_page.empty
            )
            target.setFocus()
        elif route == "run-detail":
            run = self.run_detail_page.run
            if run is not None:
                target = (
                    self.run_detail_page.cancel_button
                    if run.active
                    else self.run_detail_page.open_output_button
                    if run.status.value == "completed"
                    else self._navigation["runs"]
                )
                target.setFocus()
        elif route == "settings":
            self.settings_page.open_diagnostics_button.setFocus()

    def open_builder(self) -> None:
        result = self.controller.scan_result
        if result is None or not result.valid or not self.controller.current_inputs_ready():
            self.navigate("select")
            return
        self.builder_page.set_collection(result)
        self.navigate("builder")

    def open_dataset(self, dataset_id: str) -> None:
        root = self.controller.collection_path
        if root is None:
            self.navigate("datasets")
            return
        try:
            artifact = load_dataset(root, dataset_id)
        except (OSError, ValueError) as exc:
            self.dataset_list_page.error_alert.text_widget.setText(str(exc))
            self.dataset_list_page.error_alert.show()
            self.navigate("datasets")
            return
        self.dataset_detail_page.set_dataset(root, artifact)
        self.navigate("dataset-detail")

    def open_run(self, run_id: str) -> None:
        run = next((item for item in self.controller.runs if item.run_id == run_id), None)
        if run is None:
            self.navigate("runs")
            return
        self.run_detail_page.set_run(run)
        self.navigate("run-detail")

    def open_model(self, model_id: str) -> None:
        root = self.controller.collection_path
        if root is None:
            self.navigate("models")
            return
        try:
            artifact = load_model(root, model_id)
        except (OSError, ValueError) as exc:
            self.model_list_page.error_alert.text_widget.setText(str(exc))
            self.model_list_page.error_alert.show()
            self.navigate("models")
            return
        self.model_detail_page.set_model(artifact)
        self.navigate("model-detail")

    def _dataset_name(self, dataset_id: str, fallback: str) -> str:
        root = self.controller.collection_path
        if root is not None:
            try:
                fallback = load_dataset(root, dataset_id).label
            except (OSError, ValueError):
                pass
        return self.controller.dataset_name(dataset_id, fallback)

    def open_training(self, dataset_id: str) -> None:
        root = self.controller.collection_path
        if root is None:
            self.navigate("datasets")
            return
        try:
            artifact = load_dataset(root, dataset_id)
        except (OSError, ValueError):
            self.navigate("datasets")
            return
        self.training_page.set_dataset(root, artifact)
        self.navigate("training")

    def _open_training_wiki(self, field) -> None:
        self.training_wiki_page.show_field(field)
        self.navigate("training-wiki")

    def _open_power_wiki(self) -> None:
        self.navigate("wiki")
        self.wiki_page.ensureWidgetVisible(self.wiki_page.keep_awake_card)
        self.wiki_page.keep_awake_title.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _return_from_training_wiki(self) -> None:
        field_key = self.training_wiki_page.field_key
        self.navigate("training")
        self.training_page.restore_field_focus(field_key)

    def _open_active_run(self) -> None:
        if self.controller.active_run is not None:
            self.open_run(self.controller.active_run.run_id)

    def _open_run_output(self, run) -> None:
        if run.status.value != "completed":
            return
        if run.output_kind == "dataset":
            self.open_dataset(run.output_id)
        else:
            self.open_model(run.output_id)

    def _open_run_log(self, run) -> bool:
        path = self.controller.worker_log_for_run(run.run_id)
        if path is None:
            self.controller._diagnostic(
                "worker_log_open_failed",
                "Worker log is unavailable",
                level=logging.WARNING,
                run=run,
            )
            return False
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        self.controller._diagnostic(
            "worker_log_opened" if opened else "worker_log_open_failed",
            "Worker log opened" if opened else "Worker log could not be opened",
            level=logging.INFO if opened else logging.WARNING,
            run=run,
        )
        return opened

    def _open_diagnostics_folder(self) -> str:
        directory = self.controller.diagnostics.log_dir
        if (
            not self.controller.diagnostics_available
            or directory.is_symlink()
            or not directory.is_dir()
        ):
            self.controller._diagnostic(
                "diagnostics_folder_open_failed",
                "Diagnostics folder is unavailable",
                level=logging.WARNING,
            )
            return self.controller.diagnostics_unavailable_message
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))
        self.controller._diagnostic(
            "diagnostics_folder_opened" if opened else "diagnostics_folder_open_failed",
            "Diagnostics folder opened" if opened else "Diagnostics folder could not be opened",
            level=logging.INFO if opened else logging.WARNING,
        )
        return (
            "Opened the local diagnostics folder."
            if opened
            else "The diagnostics folder could not be opened."
        )

    def _export_diagnostics(self) -> str:
        answer = QMessageBox.question(
            self,
            "Export diagnostics?",
            "The support ZIP stays local and is never uploaded automatically. Existing log "
            "records are revalidated and redacted, but review the ZIP before sharing it. "
            "Include this session and the currently selected Run log, when available?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return ""
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export diagnostics",
            "biocall-studio-train-diagnostics.zip",
            "ZIP archive (*.zip)",
        )
        if not filename:
            return ""
        destination = Path(filename)
        if destination.suffix.lower() != ".zip":
            destination = destination.with_suffix(".zip")
        overwrite = False
        if destination.exists():
            overwrite_answer = QMessageBox.question(
                self,
                "Replace diagnostics ZIP?",
                f"A file named {destination.name} already exists. Replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if overwrite_answer != QMessageBox.StandardButton.Yes:
                return "The existing diagnostics ZIP was not changed."
            overwrite = True
        run = self.run_detail_page.run
        run_id = (
            run.run_id
            if run is not None and self.controller.worker_log_for_run(run.run_id) is not None
            else None
        )
        try:
            result = self.controller.export_diagnostics(
                destination,
                run_id=run_id,
                overwrite=overwrite,
            )
        except (FileExistsError, OSError, ValueError):
            self.controller._diagnostic(
                "diagnostics_export_failed",
                "Diagnostics support bundle export failed",
                level=logging.ERROR,
                run_id=run_id,
            )
            return "Diagnostics could not be exported. No scientific artifact was changed."
        return (
            f"Diagnostics exported with {result.included_records} sanitized records. "
            "Review the ZIP before sharing it."
        )

    def _dataset_built(self, artifact) -> None:
        self.builder_page.set_busy(False)
        root = self.controller.collection_path
        if root is None:
            return
        self.dataset_list_page.refresh(root)
        self._refresh_run_surfaces()

    def _build_started(self) -> None:
        self._refresh_run_surfaces()
        self._open_active_run()

    def _build_failed(self, _message: str) -> None:
        self.builder_page.set_busy(False)
        self._refresh_run_surfaces()

    def _build_cancelled(self) -> None:
        self.builder_page.set_busy(False)
        self._refresh_run_surfaces()

    def _training_started(self) -> None:
        self._refresh_run_surfaces()
        self._open_active_run()

    def _model_trained(self, artifact) -> None:
        self.model_list_page.refresh(self.controller.collection_path)
        self._refresh_run_surfaces()
        self.open_model(artifact.model_id)

    def _training_failed(self, _message: str) -> None:
        self._refresh_run_surfaces()

    def _training_cancelled(self) -> None:
        self._refresh_run_surfaces()

    def _set_run_header_idle(self) -> None:
        self.active_run_label.setText("No Active Run")
        self.working_run_badge.hide()
        self.idle_run_badge.show()
        self.active_run_progress.hide()
        self.view_run_button.hide()

    def _run_changed(self, run) -> None:
        self._refresh_run_surfaces()
        if self.current_route == "run-detail" and self.run_detail_page.run is not None:
            if self.run_detail_page.run.run_id == run.run_id:
                self.run_detail_page.set_run(run)

    def _refresh_run_surfaces(self) -> None:
        active = self.controller.active_run
        self.run_list_page.set_runs(self.controller.runs, active)
        runs_button = self._navigation.get("runs")
        if runs_button is not None:
            runs_button.setText("Runs  •" if active is not None else "Runs")
            runs_button.setAccessibleName(
                "Runs navigation; Active Run" if active is not None else "Runs navigation"
            )
        if active is None:
            self._set_run_header_idle()
            return
        self.active_run_label.setText(active.title)
        self.idle_run_badge.hide()
        self.working_run_badge.setText(active.status.value)
        self.working_run_badge.show()
        self.active_run_progress.setValue(active.progress)
        self.active_run_progress.setAccessibleName(f"Active Run progress {active.progress} percent")
        self.active_run_progress.show()
        self.view_run_button.show()

    def _show_run_conflict(self, message: str) -> None:
        self.select_page.pending_alert.title_widget.setText("Active Run conflict")
        self.select_page.pending_alert.text_widget.setText(message)
        self.select_page.pending_alert.setAccessibleName(f"Warning alert: {message}")
        self.select_page.pending_alert.show()

    def _delete_dataset(self, dataset_id: str) -> None:
        root = self.controller.collection_path
        if root is None:
            return
        try:
            self.controller.delete_dataset(dataset_id)
        except ValueError as exc:
            QMessageBox.warning(self, "Active Run conflict", str(exc))
            return
        self.dataset_list_page.refresh(root)
        self.navigate("datasets")

    def _delete_run(self, run_id: str) -> None:
        try:
            self.controller.delete_run(run_id)
        except ValueError as exc:
            QMessageBox.warning(self, "Run could not be deleted", str(exc))
            return
        self._refresh_run_surfaces()
        self.navigate("runs")

    def _delete_model(self, model_id: str) -> None:
        try:
            self.controller.delete_model(model_id)
        except ValueError as exc:
            QMessageBox.warning(self, "Model could not be deleted", str(exc))
            return
        self.model_list_page.refresh(self.controller.collection_path)
        self.navigate("models")

    def _scan_started(self, root: str) -> None:
        self.scan_page.begin(root)
        self.navigate("scan")

    def _scan_completed(self, result) -> None:
        self.collection_page.set_result(result)
        self.navigate("collection")

    def _scan_failed(self, message: str) -> None:
        self.navigate("select")
        self.select_page.pending_alert.text_widget.setText(message)
        self.select_page.pending_alert.setAccessibleDescription(message)
        self.select_page.pending_alert.show()
