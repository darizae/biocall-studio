"""Qt-free Review query, navigation, and fixed-shortcut view state."""

from __future__ import annotations

from enum import StrEnum

from biocall_studio.review.application.controller import ReviewSessionController
from biocall_studio.review.domain.sessions import ReviewLabel, ReviewSessionState
from biocall_studio.review.persistence.sessions import (
    ReviewCandidateView,
    ReviewPosition,
    ReviewSession,
    SessionMutation,
)


class ReviewView(StrEnum):
    GALLERY = "gallery"
    LIST = "list"
    ONE_BY_ONE = "one_by_one"


class ReviewFilter(StrEnum):
    ALL = "all"
    UNREVIEWED = "unreviewed"
    CALL = "call"
    NOT_CALL = "not_call"


class ReviewSort(StrEnum):
    SOURCE_TIME = "source_time"
    RECORDING = "recording"
    PREDICTION_DESCENDING = "prediction_descending"


class ReviewShortcutAction(StrEnum):
    CALL = "call"
    NOT_CALL = "not_call"
    CLEAR_LABEL = "clear_label"
    PREVIOUS = "previous"
    PLAY_PAUSE = "play_pause"
    NEXT = "next"
    UNDO = "undo"


_INPUT_FOCUS_KINDS = frozenset(
    {
        "line_edit",
        "text_edit",
        "plain_text_edit",
        "combo",
        "spin",
        "slider",
        "textbox",
    }
)


def shortcut_action(
    key: str,
    *,
    modifiers: frozenset[str],
    focus_kind: str,
    view: ReviewView,
    session_state: str | ReviewSessionState,
    auto_repeat: bool,
    modal_open: bool,
) -> ReviewShortcutAction | None:
    """Map only the fixed RV-05 bindings in their safe native scope."""
    try:
        view = ReviewView(view)
        state = ReviewSessionState(session_state)
    except ValueError:
        return None
    if (
        view is not ReviewView.ONE_BY_ONE
        or auto_repeat
        or modal_open
        or focus_kind in _INPUT_FOCUS_KINDS
    ):
        return None
    normalized_key = key.upper()
    normalized_modifiers = frozenset(value.upper() for value in modifiers)
    if normalized_key == "Z" and normalized_modifiers in {
        frozenset({"CTRL"}),
        frozenset({"META"}),
    }:
        return ReviewShortcutAction.UNDO if state is ReviewSessionState.OPEN else None
    if normalized_modifiers:
        return None
    navigation = {
        "J": ReviewShortcutAction.PREVIOUS,
        "LEFT": ReviewShortcutAction.PREVIOUS,
        "K": ReviewShortcutAction.PLAY_PAUSE,
        "SPACE": ReviewShortcutAction.PLAY_PAUSE,
        "L": ReviewShortcutAction.NEXT,
        "RIGHT": ReviewShortcutAction.NEXT,
    }
    if normalized_key in navigation:
        return navigation[normalized_key]
    if state is not ReviewSessionState.OPEN:
        return None
    return {
        "F": ReviewShortcutAction.CALL,
        "D": ReviewShortcutAction.NOT_CALL,
        "S": ReviewShortcutAction.CLEAR_LABEL,
    }.get(normalized_key)


class ReviewViewState:
    """Keep one Review session's lightweight view state over indexed SQLite pages."""

    def __init__(self, controller: ReviewSessionController, session_id: str):
        if not isinstance(controller, ReviewSessionController):
            raise TypeError("Review view state requires a session controller.")
        self.controller = controller
        self.store = controller.store
        self.session: ReviewSession = self.store.get_session(session_id)
        position = self.store.load_position(session_id)
        self.view = ReviewView(position.view)
        self.filter = ReviewFilter(position.filter_name)
        self.sort = ReviewSort(position.sort_name)
        self.search = position.search_text
        self.current_candidate_id = position.current_candidate_id
        self.selected_candidate_ids = position.selected_candidate_ids
        self.scroll_offset = position.scroll_offset
        self.view_revision = position.view_revision

    @property
    def row_count(self) -> int:
        return self.store.candidate_count(
            self.session.session_id,
            filter_name=self.filter.value,
            search_text=self.search,
        )

    @property
    def reviewed_count(self) -> int:
        return self.session.call_count + self.session.not_call_count

    def page(self, offset: int, limit: int) -> tuple[ReviewCandidateView, ...]:
        return self.store.candidate_page(
            self.session.session_id,
            offset=offset,
            limit=limit,
            filter_name=self.filter.value,
            search_text=self.search,
            sort_name=self.sort.value,
        )

    def set_query(
        self,
        *,
        view: ReviewView | None = None,
        filter_name: ReviewFilter | None = None,
        sort: ReviewSort | None = None,
        search: str | None = None,
    ) -> None:
        if view is not None:
            self.view = ReviewView(view)
        if filter_name is not None:
            self.filter = ReviewFilter(filter_name)
        if sort is not None:
            self.sort = ReviewSort(sort)
        if search is not None:
            if not isinstance(search, str):
                raise TypeError("Review recording search must be text.")
            self.search = " ".join(search.split())
        # Validate every query immediately instead of letting a Qt model fail later.
        self.store.candidate_count(
            self.session.session_id,
            filter_name=self.filter.value,
            search_text=self.search,
        )
        self.store.candidate_page(
            self.session.session_id,
            offset=0,
            limit=1,
            filter_name=self.filter.value,
            search_text=self.search,
            sort_name=self.sort.value,
        )

    def current(self) -> ReviewCandidateView | None:
        if self.current_candidate_id is None:
            return None
        return self.store.candidate_by_id(self.session.session_id, self.current_candidate_id)

    def set_current(self, candidate_id: str) -> ReviewCandidateView:
        row = self.store.candidate_by_id(self.session.session_id, candidate_id)
        self.current_candidate_id = row.candidate_id
        return row

    def _move(self, delta: int) -> ReviewCandidateView | None:
        if delta not in {-1, 1}:
            raise ValueError("Review navigation step is invalid.")
        count = self.store.candidate_count(self.session.session_id)
        if count == 0:
            self.current_candidate_id = None
            return None
        if self.current_candidate_id is None:
            target = 0 if delta > 0 else count - 1
        else:
            current = self.store.candidate_position(
                self.session.session_id,
                self.current_candidate_id,
                sort_name=self.sort.value,
            )
            target = current + delta
        if not 0 <= target < count:
            return self.current()
        row = self.store.candidate_page(
            self.session.session_id,
            offset=target,
            limit=1,
            sort_name=self.sort.value,
        )[0]
        self.current_candidate_id = row.candidate_id
        return row

    def previous(self) -> ReviewCandidateView | None:
        return self._move(-1)

    def next(self) -> ReviewCandidateView | None:
        return self._move(1)

    def set_label(self, label: ReviewLabel, *, modified_at: str) -> SessionMutation:
        label = ReviewLabel(label)
        if self.current_candidate_id is None:
            raise ValueError("No Review candidate is selected.")
        candidate_id = self.current_candidate_id
        mutation = self.controller.set_label(
            self.session.session_id,
            candidate_id,
            label,
            expected_revision=self.session.revision,
            modified_at=modified_at,
        )
        # Assign only after the durable transaction succeeds.
        self.session = mutation.session
        if label is not ReviewLabel.UNREVIEWED:
            next_row = self.store.next_unreviewed_candidate(
                self.session.session_id,
                candidate_id,
                sort_name=self.sort.value,
            )
            if next_row is not None:
                self.current_candidate_id = next_row.candidate_id
        return mutation

    def undo(self, *, modified_at: str) -> SessionMutation:
        mutation = self.controller.undo(
            self.session.session_id,
            expected_revision=self.session.revision,
            modified_at=modified_at,
        )
        self.session = mutation.session
        return mutation

    def set_selection(self, candidate_ids: tuple[str, ...]) -> None:
        candidate_ids = tuple(candidate_ids)
        if len(candidate_ids) > 1_000 or len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("Review selection is invalid.")
        for candidate_id in candidate_ids:
            self.store.candidate_by_id(self.session.session_id, candidate_id)
        self.selected_candidate_ids = candidate_ids

    def save_position(self) -> ReviewPosition:
        if self.session.state is not ReviewSessionState.OPEN:
            return self.store.load_position(self.session.session_id)
        position = self.controller.save_position(
            self.session.session_id,
            candidate_id=self.current_candidate_id,
            view=self.view.value,
            filter_name=self.filter.value,
            sort_name=self.sort.value,
            search_text=self.search,
            scroll_offset=self.scroll_offset,
            selected_candidate_ids=self.selected_candidate_ids,
            expected_view_revision=self.view_revision,
        )
        self.view_revision = position.view_revision
        return position


__all__ = [
    "ReviewFilter",
    "ReviewShortcutAction",
    "ReviewSort",
    "ReviewView",
    "ReviewViewState",
    "shortcut_action",
]
