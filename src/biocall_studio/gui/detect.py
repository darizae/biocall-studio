"""Native ST-03 Detect Collection setup, binding state, and explicit relinking."""

from __future__ import annotations

from alp_ui.components import Badge, Button, Card, CheckBox, FolderPicker, HelpHint, Text
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from biocall_studio.detect.controller import DetectWorkspaceController
from biocall_studio.detect.domain import RootBindingDecision


class DetectWorkspacePage(QScrollArea):
    """Researcher-facing Collection setup without ST-04 inventory behavior."""

    return_requested = Signal()

    def __init__(self, controller: DetectWorkspaceController):
        super().__init__()
        self.controller = controller
        self._compact = False
        self.setObjectName("detectWorkspacePage")
        self.setAccessibleName("Detect Collection setup")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)

        self.content = QWidget()
        self.outer = QVBoxLayout(self.content)
        self.outer.setContentsMargins(48, 34, 48, 48)
        self.outer.setSpacing(22)
        self.outer.addLayout(self._build_heading())
        self.outer.addLayout(self._build_navigation())
        self.selection_error = QLabel()
        self.selection_error.setWordWrap(True)
        self.selection_error.setAccessibleName("Recordings folder error")
        self.selection_error.setStyleSheet("color: #B91C1C; font-weight: 600;")
        self.outer.addWidget(self.selection_error)

        self.route_stack = QStackedWidget()
        self.setup_view = QWidget()
        setup_layout = QVBoxLayout(self.setup_view)
        setup_layout.setContentsMargins(0, 0, 0, 0)
        self.collection_card = self._build_collection_card()
        setup_layout.addWidget(self.collection_card)
        setup_layout.addStretch()

        self.recordings_view = QWidget()
        recordings_layout = QVBoxLayout(self.recordings_view)
        recordings_layout.setContentsMargins(0, 0, 0, 0)
        recordings_layout.setSpacing(18)
        self.recordings_card = self._build_recordings_card()
        recordings_layout.addWidget(self.recordings_card)
        self.relink_card = self._build_relink_card()
        recordings_layout.addWidget(self.relink_card)
        self.different_card = self._build_different_card()
        recordings_layout.addWidget(self.different_card)
        recordings_layout.addStretch()

        self.route_stack.addWidget(self.setup_view)
        self.route_stack.addWidget(self.recordings_view)
        self.outer.addWidget(self.route_stack)
        self.outer.addStretch()
        self.setWidget(self.content)

        self.controller.state_changed.connect(self._render)
        self.folder_picker.folderChanged.connect(self.controller.choose_source_root)
        self.relink_picker.folderChanged.connect(self.controller.choose_source_root)
        self.current_route = "setup"
        self._set_route("setup")
        self._render()

    def _build_heading(self) -> QHBoxLayout:
        heading = QHBoxLayout()
        copy = QVBoxLayout()
        copy.setSpacing(5)
        copy.addWidget(Text("DETECT SETUP", role="overline"))
        copy.addWidget(Text("Prepare candidate detection", role="title"))
        copy.addWidget(
            Text(
                "Choose the recordings folder for this Detect Collection.",
                role="body",
                word_wrap=True,
            )
        )
        heading.addLayout(copy, 1)
        self.back_button = Button("Back to Studio", variant="outline")
        self.back_button.setAccessibleName("Back to Studio launchpad")
        self.back_button.clicked.connect(self.return_requested)
        heading.addWidget(self.back_button, 0, Qt.AlignmentFlag.AlignTop)
        return heading

    def _build_navigation(self) -> QHBoxLayout:
        navigation = QHBoxLayout()
        navigation.setSpacing(8)
        self.setup_button = Button("Setup", variant="outline", size="small")
        self.setup_button.setAccessibleName("Open Detect setup")
        self.setup_button.setCheckable(True)
        self.setup_button.setAutoExclusive(True)
        self.setup_button.clicked.connect(lambda: self._set_route("setup"))
        navigation.addWidget(self.setup_button)
        self.recordings_button = Button("Recordings", variant="outline", size="small")
        self.recordings_button.setAccessibleName("Open Detect recordings folder")
        self.recordings_button.setCheckable(True)
        self.recordings_button.setAutoExclusive(True)
        self.recordings_button.clicked.connect(lambda: self._set_route("recordings"))
        navigation.addWidget(self.recordings_button)
        navigation.addStretch()
        return navigation

    def _build_collection_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Detect Collection source")
        card.setMaximumWidth(940)
        header = QHBoxLayout()
        labels = QVBoxLayout()
        labels.setSpacing(4)
        self.collection_title = Text("Create a Detect Collection", role="heading")
        labels.addWidget(self.collection_title)
        self.collection_description = Text(
            "Choose a folder. Detect stores its metadata separately and leaves "
            "recordings unchanged.",
            role="body",
            word_wrap=True,
        )
        labels.addWidget(self.collection_description)
        header.addLayout(labels, 1)
        hint = HelpHint(
            "A Detect Collection keeps a stable identity if its recordings folder moves. "
            "A different recordings folder creates a different Collection.",
            subject="Detect Collection",
        )
        header.addWidget(hint, 0, Qt.AlignmentFlag.AlignTop)
        self.status_badge = Badge("Not selected", intent="neutral")
        self.status_badge.setAccessibleName("Recordings folder status: Not selected")
        header.addWidget(self.status_badge, 0, Qt.AlignmentFlag.AlignTop)
        card.content_layout.addLayout(header)

        self.root_caption = Text("No recordings folder selected", role="overline")
        card.content_layout.addWidget(self.root_caption)
        self.root_path = QLabel("Choose a folder to create a Detect Collection.")
        self.root_path.setWordWrap(True)
        self.root_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.root_path.setAccessibleName("Current recordings folder")
        card.content_layout.addWidget(self.root_path)

        self.folder_picker = FolderPicker(label="Recordings folder")
        self.folder_picker.setAccessibleDescription(
            "Choose a new recordings folder or the relocated folder for this Collection."
        )
        card.content_layout.addWidget(self.folder_picker)
        return card

    def _build_recordings_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Current Detect Collection recordings folder")
        header = QHBoxLayout()
        labels = QVBoxLayout()
        labels.setSpacing(4)
        self.recordings_title = Text("Recordings folder", role="heading")
        labels.addWidget(self.recordings_title)
        self.recordings_description = Text("", role="body", word_wrap=True)
        labels.addWidget(self.recordings_description)
        header.addLayout(labels, 1)
        self.recordings_status_badge = Badge("Unavailable", intent="neutral")
        header.addWidget(self.recordings_status_badge, 0, Qt.AlignmentFlag.AlignTop)
        card.content_layout.addLayout(header)
        card.content_layout.addWidget(Text("LINKED LOCATION", role="overline"))
        self.recordings_path = QLabel()
        self.recordings_path.setWordWrap(True)
        self.recordings_path.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.recordings_path.setAccessibleName("Linked recordings folder")
        card.content_layout.addWidget(self.recordings_path)
        self.relink_picker = FolderPicker(label="Relink recordings folder")
        self.relink_picker.setAccessibleDescription(
            "Choose the relocated folder for this Detect Collection."
        )
        card.content_layout.addWidget(self.relink_picker)
        return card

    def _build_relink_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Confirm recordings folder relink")
        card.content_layout.addWidget(Text("Relink recordings folder", role="heading"))
        card.content_layout.addWidget(
            Text(
                "The folder identity matches this Collection. Confirm the new location before "
                "the binding changes.",
                role="body",
                word_wrap=True,
            )
        )
        paths = QGridLayout()
        paths.addWidget(Text("PREVIOUS LOCATION", role="overline"), 0, 0)
        paths.addWidget(Text("NEW LOCATION", role="overline"), 0, 1)
        self.previous_path = QLabel()
        self.previous_path.setWordWrap(True)
        self.new_path = QLabel()
        self.new_path.setWordWrap(True)
        paths.addWidget(self.previous_path, 1, 0)
        paths.addWidget(self.new_path, 1, 1)
        card.content_layout.addLayout(paths)
        self.relink_confirm = CheckBox(
            "I understand that recordings must be reviewed again before detection."
        )
        card.content_layout.addWidget(self.relink_confirm)
        actions = QHBoxLayout()
        actions.addStretch()
        self.cancel_relink_button = Button("Cancel", variant="outline")
        self.cancel_relink_button.clicked.connect(self.controller.cancel_relink)
        actions.addWidget(self.cancel_relink_button)
        self.confirm_relink_button = Button("Relink folder", variant="primary")
        self.confirm_relink_button.setEnabled(False)
        self.confirm_relink_button.clicked.connect(self.controller.confirm_relink)
        actions.addWidget(self.confirm_relink_button)
        card.content_layout.addLayout(actions)
        self.relink_confirm.toggled.connect(self.confirm_relink_button.setEnabled)
        return card

    def _build_different_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Different recordings folder")
        card.content_layout.addWidget(Text("This is a different folder", role="heading"))
        card.content_layout.addWidget(
            Text(
                "Its verified folder identity does not match the current Collection. "
                "Create a new Collection to prevent an unrelated folder from taking "
                "over its history.",
                role="body",
                word_wrap=True,
            )
        )
        actions = QHBoxLayout()
        actions.addStretch()
        self.cancel_different_button = Button("Keep current Collection", variant="outline")
        self.cancel_different_button.clicked.connect(self.controller.cancel_relink)
        actions.addWidget(self.cancel_different_button)
        self.new_collection_button = Button("Create new Collection", variant="primary")
        self.new_collection_button.clicked.connect(self.controller.create_new_collection)
        actions.addWidget(self.new_collection_button)
        card.content_layout.addLayout(actions)
        return card

    def _render(self) -> None:
        collection = self.controller.active_collection
        proposal = self.controller.proposal
        self.relink_card.setVisible(
            proposal is not None
            and proposal.decision is RootBindingDecision.AWAITING_CONFIRMATION
        )
        self.different_card.setVisible(
            proposal is not None and proposal.decision is RootBindingDecision.CHANGED
        )
        self.selection_error.setText(
            self.controller.selection_error or self.controller.metadata_error
        )
        self.selection_error.setVisible(bool(self.selection_error.text()))

        if collection is None:
            self.recordings_button.setEnabled(False)
            self._set_route("setup")
            self.collection_title.setText("Create a Detect Collection")
            self.collection_description.setText(
                "Choose a folder. Detect stores its metadata separately and leaves "
                "recordings unchanged."
            )
            self.status_badge.setText("Not selected")
            self.status_badge.setAccessibleName("Recordings folder status: Not selected")
            self.root_caption.setText("NO RECORDINGS FOLDER SELECTED")
            self.root_path.setText("Choose a folder to create a Detect Collection.")
            self.folder_picker.setFolderPath("")
            return

        self.recordings_button.setEnabled(True)
        decision = self.controller.root_decision
        status, description = {
            RootBindingDecision.VALID: (
                "Available",
                "The recordings folder is available. Detect keeps the source tree read-only.",
            ),
            RootBindingDecision.MISSING: (
                "Folder missing",
                "Choose the folder's new location to relink this Collection.",
            ),
            RootBindingDecision.INACCESSIBLE: (
                "Access unavailable",
                "The linked folder exists but cannot be read. Its contents are not "
                "treated as empty.",
            ),
            RootBindingDecision.CHANGED: (
                "Folder changed",
                "The location now refers to a different folder. Choose the relocated "
                "folder or create a new Collection.",
            ),
            None: ("Unavailable", "The Detect Collection binding could not be read."),
        }[decision]
        self.collection_title.setText(collection.ref.display_label)
        self.collection_description.setText(description)
        self.status_badge.setText(status)
        self.status_badge.setAccessibleName(f"Recordings folder status: {status}")
        self.root_caption.setText("CURRENT RECORDINGS FOLDER")
        self.root_path.setText(str(collection.source_root))
        self.recordings_title.setText(collection.ref.display_label)
        self.recordings_description.setText(description)
        self.recordings_status_badge.setText(status)
        self.recordings_status_badge.setAccessibleName(
            f"Recordings folder status: {status}"
        )
        self.recordings_path.setText(str(collection.source_root))
        if proposal is None:
            self.folder_picker.setFolderPath(str(collection.source_root))
            self.relink_picker.setFolderPath(str(collection.source_root))
        elif proposal.decision is RootBindingDecision.AWAITING_CONFIRMATION:
            self.previous_path.setText(str(proposal.previous_root))
            self.new_path.setText(str(proposal.candidate_root))
            self.relink_confirm.setChecked(False)
            self.confirm_relink_button.setEnabled(False)
        if proposal is not None or decision is not RootBindingDecision.VALID:
            self._set_route("recordings")

    def _set_route(self, route: str) -> None:
        if route not in {"setup", "recordings"}:
            raise ValueError(f"Unknown Detect route: {route}")
        if route == "recordings" and not self.recordings_button.isEnabled():
            route = "setup"
        self.current_route = route
        self.setup_button.setChecked(route == "setup")
        self.recordings_button.setChecked(route == "recordings")
        self.route_stack.setCurrentWidget(
            self.setup_view if route == "setup" else self.recordings_view
        )
        self.setup_button.setAccessibleDescription(
            "Current Detect page" if route == "setup" else "Open Detect setup"
        )
        self.recordings_button.setAccessibleDescription(
            "Current Detect page" if route == "recordings" else "Open recordings folder"
        )

    def focus_initial(self) -> None:
        if self.relink_card.isVisible():
            self.relink_confirm.setFocus()
            return
        picker = self.folder_picker if self.current_route == "setup" else self.relink_picker
        buttons = picker.findChildren(QPushButton)
        if buttons:
            buttons[0].setFocus()
        else:
            self.back_button.setFocus()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        compact = event.size().width() < 760
        if compact != self._compact:
            self._compact = compact
            margin = 22 if compact else 48
            self.outer.setContentsMargins(margin, 26 if compact else 34, margin, 36)
