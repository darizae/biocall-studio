"""Bounded native model/view adapters for large Review sessions."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable

from PySide6.QtCore import QAbstractListModel, QAbstractTableModel, QModelIndex, QSize, Qt
from PySide6.QtGui import QPixmap

from biocall_studio.review.application.view_state import ReviewViewState
from biocall_studio.review.persistence.sessions import ReviewCandidateView

_PAGE_SIZE = 100
_MAX_CACHED_PAGES = 4


def _time_text(nanoseconds: int) -> str:
    total_milliseconds = nanoseconds // 1_000_000
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def _label_text(row: ReviewCandidateView) -> str:
    return {
        "unreviewed": "○ Unreviewed",
        "call": "✓ Call",
        "not_call": "× Not a call",
    }[row.label.value]


class _PagedCandidates:
    def __init__(self, state: ReviewViewState):
        if not isinstance(state, ReviewViewState):
            raise TypeError("Review candidate model requires Review view state.")
        self.state = state
        self._pages: OrderedDict[int, tuple[ReviewCandidateView, ...]] = OrderedDict()

    @property
    def cached_row_count(self) -> int:
        return sum(len(page) for page in self._pages.values())

    def clear(self) -> None:
        self._pages.clear()

    def row(self, index: int) -> ReviewCandidateView:
        if not 0 <= index < self.state.row_count:
            raise IndexError("Review model row is outside the filtered candidate set.")
        page_number = index // _PAGE_SIZE
        page = self._pages.get(page_number)
        if page is None:
            page = self.state.page(page_number * _PAGE_SIZE, _PAGE_SIZE)
            self._pages[page_number] = page
            while len(self._pages) > _MAX_CACHED_PAGES:
                self._pages.popitem(last=False)
        else:
            self._pages.move_to_end(page_number)
        return page[index % _PAGE_SIZE]


class ReviewCandidateTableModel(QAbstractTableModel):
    HEADERS = ("Recording", "Time", "Duration", "Prediction", "Label")

    def __init__(self, state: ReviewViewState, parent=None):
        super().__init__(parent)
        self._paged = _PagedCandidates(state)

    @property
    def state(self) -> ReviewViewState:
        return self._paged.state

    @property
    def cached_row_count(self) -> int:
        return self._paged.cached_row_count

    def refresh(self) -> None:
        self.beginResetModel()
        self._paged.clear()
        self.endResetModel()

    def candidate_at(self, row: int) -> ReviewCandidateView:
        return self._paged.row(row)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else self.state.row_count

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
            and 0 <= section < len(self.HEADERS)
        ):
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.column() < len(self.HEADERS):
            return None
        row = self._paged.row(index.row())
        values = (
            row.recording_name,
            _time_text(row.start_time_ns),
            f"{row.duration_ns / 1_000_000_000:.3f} s",
            f"{row.display_score:.3f}",
            _label_text(row),
        )
        if role == Qt.ItemDataRole.DisplayRole:
            return values[index.column()]
        if role == Qt.ItemDataRole.UserRole:
            return row.candidate_id
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return ", ".join(values)
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() in {1, 2, 3}:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None


class ReviewGalleryModel(QAbstractListModel):
    def __init__(
        self,
        state: ReviewViewState,
        parent=None,
        *,
        thumbnail_provider: Callable[[ReviewCandidateView], QPixmap | None] | None = None,
    ):
        super().__init__(parent)
        self._paged = _PagedCandidates(state)
        self._thumbnail_provider = thumbnail_provider
        self._thumbnails: OrderedDict[str, QPixmap] = OrderedDict()

    @property
    def state(self) -> ReviewViewState:
        return self._paged.state

    @property
    def cached_row_count(self) -> int:
        return self._paged.cached_row_count

    def refresh(self) -> None:
        self.beginResetModel()
        self._paged.clear()
        self._thumbnails.clear()
        self.endResetModel()

    def candidate_at(self, row: int) -> ReviewCandidateView:
        return self._paged.row(row)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else self.state.row_count

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._paged.row(index.row())
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                f"{row.recording_name}\n{_time_text(row.start_time_ns)}   {_label_text(row)}"
            )
        if role == Qt.ItemDataRole.UserRole:
            return row.candidate_id
        if role == Qt.ItemDataRole.DecorationRole and self._thumbnail_provider is not None:
            thumbnail = self._thumbnails.get(row.candidate_id)
            if thumbnail is None:
                thumbnail = self._thumbnail_provider(row)
                if thumbnail is not None and not thumbnail.isNull():
                    self._thumbnails[row.candidate_id] = thumbnail
                    while len(self._thumbnails) > 32:
                        self._thumbnails.popitem(last=False)
            else:
                self._thumbnails.move_to_end(row.candidate_id)
            return thumbnail
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return (
                f"{row.recording_name}, {_time_text(row.start_time_ns)}, "
                f"{_label_text(row)}"
            )
        if role == Qt.ItemDataRole.SizeHintRole:
            return QSize(284, 108)
        return None


__all__ = ["ReviewCandidateTableModel", "ReviewGalleryModel"]
