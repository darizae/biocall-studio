"""Models belong to the desktop consumer, never to the component library."""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtWidgets import QFileSystemModel


class DirectoryPageModel(QAbstractTableModel):
    """Expose requested directory rows in pages; never open scientific files."""

    PAGE_SIZE = 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = None
        self._directory = QPersistentModelIndex()
        self._rows = []

    def set_directory(self, source: QFileSystemModel | None, directory: QModelIndex) -> None:
        if self._source is not source:
            if self._source is not None:
                self._source.directoryLoaded.disconnect(self._directory_loaded)
                self._source.rowsInserted.disconnect(self._rows_changed)
                self._source.rowsRemoved.disconnect(self._rows_changed)
                self._source.layoutChanged.disconnect(self._reload)
                self._source.dataChanged.disconnect(self._data_changed)
            self._source = source
            if source is not None:
                source.directoryLoaded.connect(self._directory_loaded)
                source.rowsInserted.connect(self._rows_changed)
                source.rowsRemoved.connect(self._rows_changed)
                source.layoutChanged.connect(self._reload)
                source.dataChanged.connect(self._data_changed)
        self._directory = QPersistentModelIndex(directory)
        self._reload()
        if source is not None and directory.isValid() and source.canFetchMore(directory):
            source.fetchMore(directory)

    def _reload(self, *args):
        self.beginResetModel()
        self._rows = []
        self.endResetModel()
        self.fetchMore()

    def _directory_loaded(self, path):
        if self._source.filePath(self._directory) == path:
            self._reload()

    def _rows_changed(self, parent, first, last):
        if parent == self._directory:
            self._reload()

    def _data_changed(self, *args):
        if self._rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._rows) - 1, 3))

    def rowCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else 4

    def canFetchMore(self, parent=QModelIndex()):  # noqa: N802
        return (
            not parent.isValid()
            and self._source is not None
            and self._directory.isValid()
            and len(self._rows) < self._source.rowCount(self._directory)
        )

    def fetchMore(self, parent=QModelIndex()):  # noqa: N802
        if not self.canFetchMore(parent):
            return
        start = len(self._rows)
        stop = min(start + self.PAGE_SIZE, self._source.rowCount(self._directory))
        self.beginInsertRows(QModelIndex(), start, stop - 1)
        self._rows.extend(
            QPersistentModelIndex(self._source.index(row, 0, self._directory))
            for row in range(start, stop)
        )
        self.endInsertRows()

    def source_index(self, index: QModelIndex) -> QModelIndex:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return QModelIndex()
        return QModelIndex(self._rows[index.row()]).siblingAtColumn(index.column())

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if self._source is not None and index.isValid():
            return self._source.data(self.source_index(index), role)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if self._source is not None:
            return self._source.headerData(section, orientation, role)
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return ("Name", "Size", "Type", "Date modified")[section] if 0 <= section < 4 else None
        return None
