"""Lazy physical directory browsing, separate from future artifact readers."""

from alp_ui.components import Alert, DataTable, EmptyState, Text
from PySide6.QtCore import QDir, QModelIndex, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileSystemModel,
    QSplitter,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from alpaca_desktop.application.workspace import WorkspaceController
from alpaca_desktop.gui.models import DirectoryPageModel
from alpaca_desktop.persistence.settings import ROOT_LABELS


class RootBrowser(QWidget):
    """Bind only the visible page to a root; Qt enumerates folders asynchronously."""

    def __init__(self, controller: WorkspaceController, root_id: str, name: str):
        super().__init__()
        self.controller = controller
        self.root_id = root_id
        self.filesystem = None
        self._bound_path = None
        self.path_label = Text("", selectable=True, word_wrap=True)
        self.error_alert = Alert("", intent="warning", title=ROOT_LABELS[root_id])
        self.error_alert.hide()
        self.empty_state = EmptyState(
            "No folder entries", text="Select a folder to browse its entries."
        )
        self.empty_state.hide()
        self.tree = QTreeView()
        self.tree.setHeaderHidden(True)
        self.tree.setAccessibleName(f"{name} physical folders")
        self.model = DirectoryPageModel(self)
        self.table = DataTable(model=self.model)
        self.table.setAccessibleName(f"{name} table")
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._open_directory)
        self.model.rowsInserted.connect(self._update_empty_state)
        self.model.modelReset.connect(self._update_empty_state)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.tree)
        splitter.addWidget(self.table)
        splitter.setStretchFactor(1, 2)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.path_label)
        layout.addWidget(self.error_alert)
        layout.addWidget(self.empty_state)
        layout.addWidget(splitter, 1)

    def clear(self):
        self.model.set_directory(None, QModelIndex())
        self.tree.setModel(None)
        if self.filesystem is not None:
            self.filesystem.deleteLater()
        self.filesystem = None
        self._bound_path = None
        self.path_label.clear()
        self.empty_state.hide()

    def activate(self):
        try:
            root = self.controller.root_path(self.root_id)
        except (OSError, ValueError) as exc:
            self.clear()
            self.error_alert.text_widget.setText(str(exc))
            self.error_alert.setAccessibleDescription(str(exc))
            self.error_alert.show()
            return
        self.error_alert.hide()
        if root == self._bound_path:
            return
        self.clear()
        self._bound_path = root
        self.path_label.setText(f"{ROOT_LABELS[self.root_id]}: {root}")
        self.filesystem = QFileSystemModel(self)
        self.filesystem.setReadOnly(True)
        self.filesystem.setOption(QFileSystemModel.Option.DontUseCustomDirectoryIcons, True)
        self.filesystem.setFilter(QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot)
        root_index = self.filesystem.setRootPath(str(root))
        self.tree.setModel(self.filesystem)
        self.tree.setRootIndex(root_index)
        for column in range(1, 4):
            self.tree.hideColumn(column)
        self.tree.selectionModel().currentChanged.connect(self._select_directory)
        self.model.set_directory(self.filesystem, root_index)

    def _select_directory(self, current, previous):
        if self.filesystem is not None and current.isValid() and self.filesystem.isDir(current):
            self.model.set_directory(self.filesystem, current)

    def _open_directory(self, index):
        source_index = self.model.source_index(index)
        if self.filesystem.isDir(source_index):
            self.tree.setCurrentIndex(source_index)
            self.tree.expand(source_index)

    def _update_empty_state(self, *args):
        self.empty_state.setVisible(self.filesystem is not None and self.model.rowCount() == 0)
