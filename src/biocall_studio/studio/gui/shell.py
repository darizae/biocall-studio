"""Native Studio launchpad with retained Train and the staged Detect workspace."""

from __future__ import annotations

from alp_ui.components import Badge, Button, Card, Text
from alp_ui.theme import ALPACA_LIGHT, make_icon
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from biocall_studio.detect.application.controller import DetectWorkspaceController
from biocall_studio.detect.gui.workspace import DetectWorkspacePage
from biocall_studio.studio.application.navigation import WorkspaceRoute
from biocall_studio.studio.gui.branding import application_icon


class WorkspaceCard(Card):
    """Accessible launchpad card built only from public alp-ui components."""

    def __init__(
        self,
        *,
        workspace: str,
        description: str,
        action_text: str,
        icon_name: str,
        accent: str,
        action,
        featured: bool = False,
    ) -> None:
        super().__init__()
        self.setObjectName(f"{workspace.lower()}WorkspaceCard")
        self.setAccessibleName(f"{workspace} workspace")
        self.setAccessibleDescription(description)
        self.setMinimumHeight(285)

        accent_bar = QFrame()
        accent_bar.setFixedHeight(4)
        accent_bar.setStyleSheet(f"background: {accent}; border-radius: 2px;")
        self.content_layout.addWidget(accent_bar)

        icon = QLabel()
        icon.setFixedSize(58, 58)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(make_icon(icon_name, color="#FFFFFF", size=30).pixmap(30, 30))
        icon.setStyleSheet(f"background: {accent}; border-radius: 13px;")
        icon.setAccessibleName(f"{workspace} icon")
        self.content_layout.addWidget(icon)
        self.content_layout.addWidget(Text(workspace, role="title"))
        self.content_layout.addWidget(Text(description, role="body", word_wrap=True))
        self.content_layout.addStretch()
        self.action_button = Button(
            action_text,
            variant="primary" if featured or workspace == "Train" else "outline",
            size="large",
        )
        self.action_button.setAccessibleName(f"{action_text} workspace")
        self.action_button.clicked.connect(action)
        self.content_layout.addWidget(self.action_button)


class LaunchpadPage(QScrollArea):
    workspace_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("studioLaunchpad")
        self.setAccessibleName("BioCall Studio workspace launchpad")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self._compact = False

        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(48, 34, 48, 48)
        outer.setSpacing(26)

        intro = QVBoxLayout()
        intro.setSpacing(7)
        title = Text("From raw audio to corpora", role="title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        intro.addWidget(title)
        outer.addLayout(intro)

        self.cards = QGridLayout()
        self.cards.setSpacing(18)
        self.train_card = WorkspaceCard(
            workspace="Train",
            description="Create models using labeled examples from your recordings.",
            action_text="Open Train",
            icon_name="list",
            accent="#0C4A6E",
            action=lambda: self.workspace_requested.emit(WorkspaceRoute.TRAIN.value),
        )
        self.detect_card = WorkspaceCard(
            workspace="Detect",
            description="Find candidate calls, refine results, and prepare audio for review.",
            action_text="Open Detect",
            icon_name="search",
            accent="#4C1D95",
            action=lambda: self.workspace_requested.emit(WorkspaceRoute.DETECT.value),
            featured=True,
        )
        self.review_card = WorkspaceCard(
            workspace="Review",
            description="Inspect and confirm detected calls.",
            action_text="Coming later",
            icon_name="check",
            accent="#92400E",
            action=lambda: self.workspace_requested.emit(WorkspaceRoute.REVIEW.value),
        )
        outer.addLayout(self.cards)
        outer.addStretch()
        self.setWidget(content)
        self._place_cards(compact=False)

    def _place_cards(self, *, compact: bool) -> None:
        cards = (self.train_card, self.detect_card, self.review_card)
        for card in cards:
            self.cards.removeWidget(card)
            card.setMinimumHeight(205 if compact else 285)
        if compact:
            for row, card in enumerate(cards):
                self.cards.addWidget(card, row, 0)
            self.cards.setColumnStretch(0, 1)
            self.cards.setColumnStretch(1, 0)
            self.cards.setColumnStretch(2, 0)
        else:
            for column, card in enumerate(cards):
                self.cards.addWidget(card, 0, column)
                self.cards.setColumnStretch(column, 1)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        compact = event.size().width() < 900
        if compact != self._compact:
            self._compact = compact
            self._place_cards(compact=compact)


class LandingPage(QWidget):
    return_requested = Signal()

    def __init__(
        self,
        *,
        workspace: str,
        title: str,
        description: str,
        status: str,
        icon_name: str,
        accent: str,
    ) -> None:
        super().__init__()
        self.setAccessibleName(f"{workspace} workspace landing")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(48, 42, 48, 48)
        outer.setSpacing(18)
        outer.addStretch()

        card = Card()
        card.setMaximumWidth(720)
        card.setMinimumHeight(330)
        card.setAccessibleName(f"{workspace} status")
        icon = QLabel()
        icon.setFixedSize(72, 72)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(make_icon(icon_name, color="#FFFFFF", size=38).pixmap(38, 38))
        icon.setStyleSheet(f"background: {accent}; border-radius: 16px;")
        card.content_layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignHCenter)
        heading = Text(title, role="title")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card.content_layout.addWidget(heading)
        body = Text(description, role="body", word_wrap=True)
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card.content_layout.addWidget(body)
        badge = Badge(status, intent="neutral")
        badge.setAccessibleName(f"{workspace} status: {status}")
        card.content_layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignHCenter)
        self.back_button = Button("Back to Studio", variant="outline", size="large")
        self.back_button.clicked.connect(self.return_requested)
        card.content_layout.addWidget(self.back_button)
        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch()


class StudioWindow(QMainWindow):
    workspace_requested = Signal(str)
    application_exit_requested = Signal()

    def __init__(self, detect_controller: DetectWorkspaceController) -> None:
        super().__init__()
        self.setObjectName("bioCallStudioWindow")
        self.setWindowTitle("BioCall Studio")
        self.setWindowIcon(application_icon())
        self.resize(1180, 790)
        self.setMinimumSize(640, 620)
        self._allow_close = False
        self.current_workspace = WorkspaceRoute.STUDIO

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.global_header = self._build_header()
        layout.addWidget(self.global_header)
        self.pages = QStackedWidget()
        self.launchpad = LaunchpadPage()
        self.detect_page = DetectWorkspacePage(detect_controller)
        self.review_page = LandingPage(
            workspace="Review",
            title="Review is coming later",
            description="Inspect and confirm detected calls in a future workspace.",
            status="Coming later",
            icon_name="check",
            accent="#92400E",
        )
        self._pages = {
            WorkspaceRoute.STUDIO: self.launchpad,
            WorkspaceRoute.DETECT: self.detect_page,
            WorkspaceRoute.REVIEW: self.review_page,
        }
        for page in self._pages.values():
            self.pages.addWidget(page)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(central)

        self.launchpad.workspace_requested.connect(self.workspace_requested)
        self.detect_page.return_requested.connect(
            lambda: self.workspace_requested.emit(WorkspaceRoute.STUDIO.value)
        )
        self.review_page.return_requested.connect(
            lambda: self.workspace_requested.emit(WorkspaceRoute.STUDIO.value)
        )
        self.show_workspace(WorkspaceRoute.STUDIO)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("studioHeader")
        header.setStyleSheet(
            f"QFrame#studioHeader {{ background: {ALPACA_LIGHT.colors.surface}; "
            f"border-bottom: 1px solid {ALPACA_LIGHT.colors.border}; }}"
        )
        layout = QHBoxLayout(header)
        layout.setContentsMargins(48, 14, 48, 14)
        icon = QLabel()
        icon.setPixmap(application_icon().pixmap(40, 40))
        icon.setAccessibleName("BioCall Studio logo")
        layout.addWidget(icon)
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(Text("BioCall Studio", role="subheading"))
        layout.addLayout(text)
        layout.addStretch()
        return header

    def show_workspace(self, route: WorkspaceRoute) -> None:
        if route is WorkspaceRoute.TRAIN:
            raise ValueError("Train is a retained independent window.")
        self.current_workspace = route
        self.pages.setCurrentWidget(self._pages[route])
        self.global_header.setVisible(route is not WorkspaceRoute.DETECT)
        self.setWindowTitle(
            "BioCall Studio"
            if route is WorkspaceRoute.STUDIO
            else f"BioCall Studio — {route.title()}"
        )
        if route is WorkspaceRoute.STUDIO:
            self.launchpad.train_card.action_button.setFocus()
        elif route is WorkspaceRoute.DETECT:
            self.detect_page.focus_initial()
        else:
            self.review_page.back_button.setFocus()

    def allow_application_close(self) -> None:
        self._allow_close = True

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._allow_close:
            event.accept()
            super().closeEvent(event)
            return
        event.ignore()
        self.application_exit_requested.emit()
