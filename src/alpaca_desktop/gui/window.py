"""Collection-first native shell composed from public alp-ui widgets."""

from __future__ import annotations

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
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QCloseEvent, QFontDatabase, QResizeEvent
from PySide6.QtWidgets import (
    QBoxLayout,
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

from alpaca_desktop.application.workspace import WorkspaceController
from alpaca_desktop.gui.collection import CollectionPage, ReadingCollectionPage
from alpaca_desktop.gui.dataset import DatasetBuilderPage, DatasetDetailPage, DatasetListPage
from alpaca_desktop.gui.run import RunDetailPage, RunListPage
from alpaca_desktop.persistence.datasets import load_dataset

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
        heading.addWidget(Text("We check the folder. No import or audio copy.", role="caption"))
        header.addLayout(heading)
        header.addStretch()
        header.addWidget(
            HelpHint(
                "A Collection is your existing folder with recordings/ and positives/. "
                "Positive filenames identify source-time in integer milliseconds.",
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
        local_note = Text("Local only · source WAVs stay read-only.", role="caption")
        local_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        choose_layout.addWidget(local_note)
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
        heading.addWidget(Text("One folder. WAV files. Timestamps in filenames.", role="caption"))
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
        outer.addWidget(
            Text(
                "A timestamp is a user-supplied label. Names and WAV headers cannot prove "
                "waveform identity.",
                role="caption",
                word_wrap=True,
            )
        )
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
        fixed_font.setPointSize(11)
        tree.setFont(fixed_font)
        tree.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        tree.setAccessibleName("Collection folder layout")
        card.content_layout.addWidget(tree)
        card.content_layout.addWidget(
            Text(
                "Use WAV files only. The Trainer creates .alpaca/ metadata only after validation.",
                role="caption",
                word_wrap=True,
            )
        )
        return card

    @staticmethod
    def _timestamps_card() -> Card:
        card = Card(shadow=False)
        header = QHBoxLayout()
        header.addWidget(Text("2 · Put times in each positive WAV name", role="subheading"))
        header.addWidget(
            HelpHint("Milliseconds are integers. 1000 ms = 1 s.", subject="Source-time timestamps")
        )
        header.addStretch()
        card.content_layout.addLayout(header)
        example = QLabel("SITE_001__start-012500ms__end-014900ms__call01.wav")
        fixed_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        fixed_font.setPointSize(10)
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
        card.content_layout.addWidget(
            Text(
                "These source-time bounds describe the original recording, not the positive "
                "clip timeline.",
                role="caption",
                word_wrap=True,
            )
        )
        return card

    @staticmethod
    def _validation_card() -> Card:
        card = Card(shadow=False)
        card.content_layout.addWidget(Text("3 · What we validate", role="subheading"))
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

    def __init__(self, controller: WorkspaceController):
        super().__init__()
        self.controller = controller
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAccessibleName("Settings")
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(38, 30, 38, 38)
        layout.setSpacing(18)
        layout.addWidget(Text("LOCAL FOLDERS", role="overline"))
        layout.addWidget(Text("Settings", role="title"))
        layout.addWidget(
            Text(
                "Trainer metadata and generated artifacts stay with the Collection.", role="caption"
            )
        )

        grid = QGridLayout()
        grid.setSpacing(16)
        binding = Card(shadow=False)
        binding_header = QHBoxLayout()
        binding_header.addWidget(Text("Collection folders", role="subheading"))
        binding_header.addStretch()
        binding_header.addWidget(
            HelpHint(
                "The Collection is the folder you select. Machine-specific binding stays in "
                "local Application Settings.",
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
        binding.content_layout.addWidget(
            Text(
                "A recent folder is only pending. Collection Scan validates identity before "
                "saving or rebinding it.",
                role="caption",
                word_wrap=True,
            )
        )
        self.error_alert = Alert("", title="Application Settings", intent="danger")
        self.error_alert.hide()
        binding.content_layout.addWidget(self.error_alert)
        grid.addWidget(binding, 0, 0)

        plan = Card(shadow=False)
        plan.content_layout.addWidget(Text("Native reading plan", role="subheading"))
        for title, detail in (
            ("First selection", "List folders asynchronously and read bounded WAV headers."),
            ("Reopen", "Compare cached file facts and recheck only changed inputs."),
            ("Large Collections", "Page metadata; never read all audio into memory."),
            ("Scientific safety", "Revalidate before Build and never mutate source WAVs."),
            ("Runs", "One Active Run, staged publication and recoverable cancellation."),
        ):
            plan.content_layout.addWidget(Text(title, role="body"))
            plan.content_layout.addWidget(Text(detail, role="caption", word_wrap=True))
        grid.addWidget(plan, 0, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        layout.addStretch()
        self.setWidget(content)

        controller.changed.connect(self._refresh)
        self._refresh()
        if controller.error_message:
            self.error_alert.text_widget.setText(controller.error_message)
            self.error_alert.show()

    def _refresh(self) -> None:
        path = self.controller.collection_path
        self.binding_value.setText(str(path) if path else "No Collection has been validated.")


class MainWindow(QMainWindow):
    """Native Collection-first shell with background Scan navigation."""

    def __init__(self, controller: WorkspaceController):
        super().__init__()
        self.controller = controller
        self.current_route = "select"
        self.is_compact = False
        self.setWindowTitle("alpaca Desktop Trainer")
        self.resize(1180, 790)
        self.setMinimumSize(640, 620)
        self._navigation: dict[str, QPushButton] = {}
        self._pages: dict[str, QWidget] = {}

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
        self.dataset_list_page = DatasetListPage(self.open_builder, self.open_dataset)
        self.dataset_detail_page = DatasetDetailPage(
            self._delete_dataset,
            lambda: self.navigate("collection"),
        )
        self.run_list_page = RunListPage(self.open_run, lambda: self.navigate("select"))
        self.run_detail_page = RunDetailPage(
            controller.cancel_active_run,
            self._open_run_output,
            lambda: self.navigate("runs"),
        )
        self.wiki_page = WikiPage(lambda: self.navigate("select"))
        self.wiki_select_button = self.wiki_page.select_button
        self.settings_page = SettingsPage(controller)
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
            (
                "models",
                self._empty_artifact_page(
                    "Models", "Trained classifiers from published Datasets.", "No Models yet."
                ),
            ),
            ("runs", self.run_list_page),
            ("run-detail", self.run_detail_page),
            ("wiki", self.wiki_page),
            ("settings", self.settings_page),
        ):
            self._pages[route] = page
            self.pages.addWidget(page)
        self.empty_pages["datasets"] = self.dataset_list_page.empty
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
        controller.run_changed.connect(self._run_changed)
        controller.runs_changed.connect(self._refresh_run_surfaces)
        controller.run_conflict.connect(self._show_run_conflict)
        self.navigate("select")
        self._refresh_run_surfaces()
        controller.reopen_bound_collection()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_responsive_layout(event.size().width() < 820)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.controller.shutdown()
        super().closeEvent(event)

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
        brand_icon = QLabel()
        brand_icon.setPixmap(
            make_icon("grid", color=ALPACA_LIGHT.colors.primary, size=25).pixmap(25, 25)
        )
        brand_layout.addWidget(brand_icon)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        brand_text.addWidget(Text("alpaca", role="subheading"))
        brand_text.addWidget(Text("DESKTOP TRAINER", role="overline"))
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
        footer.addWidget(Divider())
        footer.addWidget(Text("●  Local workspace", role="body"))
        footer.addWidget(Text("Scientific data stays on your computer.", role="caption"))
        footer.addWidget(Text("NATIVE DEVELOPMENT PREVIEW", role="overline"))
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
        layout.addStretch()
        return header

    def _empty_artifact_page(self, label: str, subtitle: str, title: str) -> QWidget:
        page = QWidget()
        page.setAccessibleName(label)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(38, 30, 38, 30)
        layout.setSpacing(10)
        layout.addWidget(Text(label.upper(), role="overline"))
        layout.addWidget(Text(label, role="title"))
        layout.addWidget(Text(subtitle, role="caption"))
        layout.addSpacing(14)
        action = Button("Select Collection")
        action.setIcon(make_icon("plus", color=ALPACA_LIGHT.colors.on_primary, size=16))
        action.clicked.connect(lambda: self.navigate("select"))
        empty = EmptyState(
            title,
            text="Choose a Collection to begin. No sample or simulated artifacts are shown.",
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

    def _open_active_run(self) -> None:
        if self.controller.active_run is not None:
            self.open_run(self.controller.active_run.run_id)

    def _open_run_output(self, run) -> None:
        if run.status.value != "completed":
            return
        if run.output_kind == "dataset":
            self.open_dataset(run.output_id)

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
