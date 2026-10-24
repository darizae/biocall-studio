"""Artifact-oriented navigation composed from public alp-ui and native Qt."""

from alp_ui.components import Alert, Badge, Button, Card, Divider, Text
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from alpaca_desktop.application.workspace import WorkspaceController
from alpaca_desktop.gui.browser import RootBrowser
from alpaca_desktop.gui.settings import SettingsPage

_ACTIONS = {
    "Collections": ("Import Collection", "Build Dataset"),
    "Datasets": ("Train Model",),
    "Models": ("Run Prediction",),
    "Corpora": ("Review", "Apply Filter"),
    "Runs": (),
}


class MainWindow(QMainWindow):
    """Native window owns navigation; components only render presentation."""

    def __init__(self, controller: WorkspaceController):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("alpaca Desktop Trainer")
        self.resize(1120, 780)
        central = QWidget()
        layout = QVBoxLayout(central)
        header = QHBoxLayout()
        header.addWidget(Text("alpaca Desktop Trainer", role="title"))
        header.addStretch()
        header.addWidget(Badge("Local application"))
        layout.addLayout(header)
        layout.addWidget(Divider())

        body = QHBoxLayout()
        self.navigation = QTreeWidget()
        self.navigation.setHeaderHidden(True)
        self.navigation.setAccessibleName("Artifact navigation")
        self.navigation.setFixedWidth(210)
        data_item = QTreeWidgetItem(self.navigation, ["Data"])
        data_item.setFlags(data_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        for name in ("Collections", "Datasets"):
            QTreeWidgetItem(data_item, [name])
        data_item.setExpanded(True)
        for name in ("Models", "Corpora", "Runs", "Settings"):
            QTreeWidgetItem(self.navigation, [name])
        body.addWidget(self.navigation)

        self.pages = QStackedWidget()
        self.artifact_pages = {}
        self.browsers = {}
        for name, actions in _ACTIONS.items():
            page = Card(shadow=False)
            page.setAccessibleName(name)
            page.content_layout.addWidget(Text(name, role="heading"))
            action_row = QHBoxLayout()
            for action_name in actions:
                button = Button(action_name, variant="outline")
                reason = f"{action_name} is unavailable in this version."
                button.setEnabled(False)
                button.setToolTip(reason)
                button.setAccessibleDescription(reason)
                action_row.addWidget(button)
            action_row.addStretch()
            page.content_layout.addLayout(action_row)
            page.content_layout.addWidget(
                Alert(
                    "Artifact details and actions are unavailable in this version. "
                    "Browse physical folders below.",
                    intent="info",
                )
            )
            root_id = {"Collections": "collection_root", "Datasets": "datasets_root"}.get(
                name, "runs_root"
            )
            browser = RootBrowser(controller, root_id, name)
            self.browsers[name] = browser
            page.content_layout.addWidget(browser, 1)
            self.artifact_pages[name] = page
            self.pages.addWidget(page)

        self.settings_page = SettingsPage(controller)
        self.pages.addWidget(self.settings_page)
        body.addWidget(self.pages, 1)
        layout.addLayout(body, 1)
        self.setCentralWidget(central)
        self.navigation.currentItemChanged.connect(self._navigate)
        controller.changed.connect(self._workspace_changed)
        self.navigation.setCurrentItem(data_item.child(0))
        if controller.error_message:
            self.navigation.setCurrentItem(self.navigation.topLevelItem(4))

    def _navigate(self, current, previous):
        if current is None:
            return
        name = current.text(0)
        if name == "Settings":
            self.pages.setCurrentWidget(self.settings_page)
        elif name in self.artifact_pages:
            self.pages.setCurrentWidget(self.artifact_pages[name])
            self.browsers[name].activate()

    def _workspace_changed(self):
        for browser in self.browsers.values():
            browser.clear()
        name = self.pages.currentWidget().accessibleName()
        if name in self.browsers:
            self.browsers[name].activate()
