"""Workspace form delegates validation and persistence to its application owner."""

from alp_ui.components import Alert, Button, Card, Text, TextInput
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from alpaca_desktop.application.workspace import WorkspaceController
from alpaca_desktop.persistence.settings import ROOT_LABELS


class SettingsPage(QScrollArea):
    """Scrollable native form for three independent roots and external bindings."""

    def __init__(self, controller: WorkspaceController):
        super().__init__()
        self.controller = controller
        self.setAccessibleName("Settings")
        self.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addWidget(Text("Settings", role="heading"))
        self.error_alert = Alert("", title="Application Settings", intent="danger")
        self.error_alert.hide()
        layout.addWidget(self.error_alert)
        roots_card = Card(shadow=False)
        roots_card.content_layout.addWidget(Text("Workspace roots", role="subheading"))
        self.root_fields = {}
        for root_id, label in ROOT_LABELS.items():
            row = QHBoxLayout()
            field = TextInput(label=label, placeholder="Choose an existing folder")
            self.root_fields[root_id] = field
            row.addWidget(field, 1)
            browse = Button("Choose folder", variant="outline")
            browse.setAccessibleName(f"Choose {label}")
            browse.clicked.connect(lambda checked=False, target=field: self._choose(target))
            row.addWidget(browse)
            roots_card.content_layout.addLayout(row)
        self.save_roots = Button("Save Workspace roots")
        self.save_roots.clicked.connect(self._save_roots)
        roots_card.content_layout.addWidget(self.save_roots)
        layout.addWidget(roots_card)

        sources_card = Card(shadow=False)
        sources_card.content_layout.addWidget(
            Text("External source-folder bindings", role="subheading")
        )
        self.source_id = TextInput(label="Source root ID")
        self.source_path = TextInput(label="External source folder")
        sources_card.content_layout.addWidget(self.source_id)
        sources_card.content_layout.addWidget(self.source_path)
        source_browse = Button("Choose source folder", variant="outline")
        source_browse.clicked.connect(lambda: self._choose(self.source_path))
        sources_card.content_layout.addWidget(source_browse)
        self.save_source = Button("Add source binding")
        self.save_source.clicked.connect(self._save_source)
        sources_card.content_layout.addWidget(self.save_source)
        self.source_list = QListWidget()
        self.source_list.setAccessibleName("External source-folder bindings")
        sources_card.content_layout.addWidget(self.source_list)
        layout.addWidget(sources_card)
        self.save_message = Text("", role="caption", word_wrap=True)
        layout.addWidget(self.save_message)
        layout.addStretch()
        self.setWidget(content)
        self.controller.changed.connect(self._refresh)
        self._refresh()
        if self.controller.error_message:
            self._show_error(self.controller.error_message)

    def _refresh(self):
        for root_id, field in self.root_fields.items():
            field.setText(str(self.controller.roots.get(root_id, "")))
        self.source_list.clear()
        for root_id, path in self.controller.source_bindings.items():
            self.source_list.addItem(f"{root_id}: {path}")

    def _choose(self, field):
        selected = QFileDialog.getExistingDirectory(self, field.labelText(), field.text())
        if selected:
            field.setText(selected)

    def _save_roots(self):
        try:
            self.controller.set_roots(
                {
                    key: field.text()
                    for key, field in self.root_fields.items()
                    if field.text() or key in self.controller.roots
                }
            )
        except (OSError, ValueError) as exc:
            self._show_error(str(exc))
        else:
            self.error_alert.hide()
            self.save_message.setText("Workspace roots saved.")

    def _save_source(self):
        try:
            self.controller.add_source_binding(self.source_id.text(), self.source_path.text())
        except (OSError, ValueError) as exc:
            self._show_error(str(exc))
        else:
            self.error_alert.hide()
            self.save_message.setText("Source binding saved. External source files stay in place.")

    def _show_error(self, message):
        self.save_message.clear()
        self.error_alert.text_widget.setText(message)
        self.error_alert.setAccessibleDescription(message)
        self.error_alert.show()
