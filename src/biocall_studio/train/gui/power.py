"""Shared native controls for the app-wide keep-awake preference."""

from __future__ import annotations

from alp_ui.components import Alert, Button, HelpHint, Switch, Text
from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

KEEP_AWAKE_HELP = (
    "When this is on, Trainer asks your computer to stay awake while the app is open. "
    "Your screen can still turn off. It may use more battery. Closing the lid or putting "
    "the computer to sleep yourself can still pause training."
)


class KeepAwakeControl(QWidget):
    def __init__(self, controller, open_wiki, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        row = QHBoxLayout()
        self.toggle = Switch("Keep computer awake")
        self.toggle.setAccessibleDescription(KEEP_AWAKE_HELP)
        self.hint = HelpHint(KEEP_AWAKE_HELP, subject="Keep computer awake")
        self.status = Text("Off", role="body")
        self.status.setAccessibleName("Keep computer awake status")
        row.addWidget(self.toggle)
        row.addWidget(self.hint)
        row.addStretch()
        row.addWidget(self.status)
        layout.addLayout(row)

        actions = QHBoxLayout()
        self.wiki_button = Button(
            "Read Keep computer awake Wiki entry →", variant="outline", size="small"
        )
        self.wiki_button.clicked.connect(open_wiki)
        actions.addWidget(self.wiki_button)
        self.retry_button = Button("Retry", variant="secondary", size="small")
        self.retry_button.clicked.connect(controller.retry_keep_awake)
        self.retry_button.hide()
        actions.addWidget(self.retry_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.error = Alert("", title="Keep computer awake is not active", intent="warning")
        self.error.hide()
        layout.addWidget(self.error)

        self.toggle.toggled.connect(controller.set_keep_awake)
        controller.power_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        blocker = QSignalBlocker(self.toggle)
        self.toggle.setChecked(self.controller.keep_awake_requested)
        del blocker
        if self.controller.keep_awake_active:
            status = "On"
        elif self.controller.keep_awake_requested:
            status = "Not active"
        else:
            status = "Off"
        self.status.setText(status)
        self.status.setAccessibleDescription(status)
        error = self.controller.keep_awake_error
        if error:
            self.error.text_widget.setText(error)
            self.error.setAccessibleDescription(error)
            self.error.show()
        else:
            self.error.hide()
        self.retry_button.setVisible(bool(error))
