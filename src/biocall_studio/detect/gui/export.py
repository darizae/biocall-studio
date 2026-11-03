"""Native frozen-selection corpus export controls."""

from __future__ import annotations

from pathlib import Path

from alp_ui.components import Badge, Button, Card, FolderPicker, HelpHint, Text
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from biocall_studio.detect.application.controller import DetectWorkspaceController
from biocall_studio.detect.domain.exports import (
    ExportMode,
    ExportState,
    safe_snippet_relative_path,
)
from biocall_studio.detect.gui.storage import StorageSection, confirm_storage


def _source_time(nanoseconds: int) -> str:
    milliseconds = nanoseconds // 1_000_000
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


class ExportPage(QWidget):
    """Render and operate one frozen Result selection without mutating it."""

    results_requested = Signal()
    exports_requested = Signal()

    def __init__(self, controller: DetectWorkspaceController):
        super().__init__()
        self.controller = controller
        self._compact = False
        self.storage_estimate = None
        self.setAccessibleName("Corpus export")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        self.export_grid = QGridLayout()
        self.export_grid.setHorizontalSpacing(16)
        self.export_grid.setVerticalSpacing(16)
        self.selection_card = self._build_selection_card()
        self.format_card = self._build_format_card()
        self.destination_card = self._build_destination_card()
        self.mapping_card = self._build_mapping_card()
        self.review_card = self._build_review_card()
        self.export_grid.addWidget(self.selection_card, 0, 0)
        self.export_grid.addWidget(self.review_card, 0, 1, 4, 1)
        self.export_grid.addWidget(self.format_card, 1, 0)
        self.export_grid.addWidget(self.destination_card, 2, 0)
        self.export_grid.addWidget(self.mapping_card, 3, 0)
        self.export_grid.setColumnStretch(0, 3)
        self.export_grid.setColumnStretch(1, 2)
        outer.addLayout(self.export_grid)

        footer = QHBoxLayout()
        self.results_button = Button("Back to Results", variant="outline")
        self.results_button.setAccessibleName("Return to Detect Results")
        self.results_button.clicked.connect(self.results_requested)
        footer.addWidget(self.results_button)
        footer.addStretch()
        outer.addLayout(footer)
        outer.addStretch()

        self.destination_picker.folderChanged.connect(lambda _path: self.render())
        self.mode_group.buttonToggled.connect(lambda _button, _checked: self.render())
        self.start_button.clicked.connect(self._start)
        self.cancel_button.clicked.connect(self.controller.cancel_export)
        self.show_button.clicked.connect(self._show_output)
        self.controller.state_changed.connect(self.render)
        self.render()

    def _build_selection_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Selected calls")
        heading = QHBoxLayout()
        heading.addWidget(Text("Selected calls", role="heading"))
        heading.addStretch()
        self.frozen_count = Badge("No intervals", intent="success")
        self.frozen_count.setAccessibleName("Selected call count")
        heading.addWidget(self.frozen_count)
        card.content_layout.addLayout(heading)
        self.result_label = Text("No result selected.", role="subheading")
        card.content_layout.addWidget(self.result_label)
        self.selection_summary = Text("Return to Results and select intervals.", role="body")
        card.content_layout.addWidget(self.selection_summary)
        return card

    def _build_format_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Export format")
        heading = QHBoxLayout()
        heading.addWidget(Text("Export format", role="heading"))
        self.format_help = HelpHint(
            "Individual snippets creates one WAV per selected call. Concatenated creates one "
            "WAV and a Raven table, and requires matching audio formats.",
            subject="Corpus export formats",
        )
        self.format_help.setObjectName("CTX-07")
        heading.addWidget(self.format_help)
        heading.addStretch()
        card.content_layout.addLayout(heading)
        self.mode_group = QButtonGroup(self)
        self.mode_snippets = QRadioButton("Individual WAV snippets")
        self.mode_concat = QRadioButton("Concatenated WAV with Raven TSV")
        self.mode_both = QRadioButton("Both")
        self.mode_both.setChecked(True)
        for identifier, button in enumerate((self.mode_snippets, self.mode_concat, self.mode_both)):
            self.mode_group.addButton(button, identifier)
            card.content_layout.addWidget(button)
        return card

    def _build_destination_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Export destination")
        heading = QHBoxLayout()
        heading.addWidget(Text("Destination", role="heading"))
        heading.addStretch()
        heading.addWidget(Badge("Required", intent="warning"))
        card.content_layout.addLayout(heading)
        self.destination_picker = FolderPicker(label="Export folder")
        self.destination_picker.setAccessibleName("Choose persistent corpus export destination")
        card.content_layout.addWidget(self.destination_picker)
        card.content_layout.addWidget(
            Text(
                "Exported audio may be sensitive. BioCall Studio creates a new folder inside "
                "this destination and never overwrites existing files.",
                role="body",
                word_wrap=True,
            )
        )
        return card

    def _build_mapping_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Planned audio output")
        card.content_layout.addWidget(Text("Planned output", role="heading"))
        self.mapping_label = QLabel()
        self.mapping_label.setWordWrap(True)
        self.mapping_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.mapping_label.setAccessibleName("Planned source and output audio")
        card.content_layout.addWidget(self.mapping_label)
        return card

    def _build_review_card(self) -> Card:
        card = Card()
        card.setAccessibleName("Review corpus export")
        card.content_layout.addWidget(Text("Review export", role="heading"))
        self.review_summary = Text("Select calls in Results to continue.", role="body")
        card.content_layout.addWidget(self.review_summary)
        self.status_title = Text("Selection required", role="subheading")
        self.status_title.setAccessibleName("Export status")
        card.content_layout.addWidget(self.status_title)
        self.status_detail = Text(
            "Return to Results and choose at least one interval.", role="body", word_wrap=True
        )
        card.content_layout.addWidget(self.status_detail)
        self.storage_section = StorageSection()
        card.content_layout.addWidget(self.storage_section)
        self.start_button = Button("Export corpus", variant="primary")
        self.start_button.setAccessibleName("Export selected calls")
        card.content_layout.addWidget(self.start_button)
        self.cancel_button = Button("Cancel export", variant="outline")
        self.cancel_button.setAccessibleName("Cancel corpus export")
        card.content_layout.addWidget(self.cancel_button)
        self.show_button = Button("Show in folder", variant="outline")
        self.show_button.setAccessibleName("Show completed corpus export in folder")
        card.content_layout.addWidget(self.show_button)
        self.view_exports_button = Button("View in Exports", variant="outline")
        self.view_exports_button.setAccessibleName("View completed export in export history")
        self.view_exports_button.clicked.connect(self.exports_requested)
        card.content_layout.addWidget(self.view_exports_button)
        self.history_warning = QLabel()
        self.history_warning.setWordWrap(True)
        self.history_warning.setStyleSheet("color: #B91C1C; font-weight: 600;")
        self.history_warning.setAccessibleName("Export history warning")
        card.content_layout.addWidget(self.history_warning)
        self.retry_history_button = Button("Retry saving to history", variant="outline")
        self.retry_history_button.clicked.connect(
            getattr(self.controller, "retry_save_export_history", lambda: None)
        )
        card.content_layout.addWidget(self.retry_history_button)
        card.content_layout.addStretch()
        return card

    def _mode(self) -> ExportMode:
        if self.mode_snippets.isChecked():
            return ExportMode.SNIPPETS
        if self.mode_concat.isChecked():
            return ExportMode.CONCAT
        return ExportMode.BOTH

    def _selected_rows(self):
        result = self.controller.export_result
        frozen = self.controller.export_selection
        if result is None or frozen is None:
            return ()
        selected = set(frozen.candidate_ids)
        return tuple(
            (recording, candidate)
            for recording in result.recordings
            for candidate in recording.candidates
            if candidate.candidate_id in selected
        )

    def _start(self) -> None:
        destination = self.destination_picker.folderPath().strip()
        if not destination:
            return
        try:
            prior_digest = (
                None if self.storage_estimate is None else self.storage_estimate.input_digest
            )
            estimate = self.controller.estimate_export_storage(
                self._mode(),
                Path(destination),
                expected_digest=prior_digest,
            )
            self.storage_estimate = estimate
            self.storage_section.set_estimate(estimate)
            if not estimate.can_start or not confirm_storage(self, estimate):
                return
            self.controller.start_export(
                self._mode(),
                Path(destination),
                storage_digest=estimate.input_digest,
                confirm_storage=estimate.requires_confirmation,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            self.status_detail.setText(str(exc))

    def _show_output(self) -> None:
        try:
            receipt = self.controller.verify_export_receipt()
        except (OSError, RuntimeError, ValueError):
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(receipt.final_destination))

    def render(self) -> None:
        rows = self._selected_rows()
        count = len(rows)
        recordings = len({recording.recording_ref for recording, _candidate in rows})
        self.frozen_count.setText(
            "No intervals" if not count else f"{count:,} interval{'s' if count != 1 else ''}"
        )
        frozen = self.controller.export_selection
        self.result_label.setText(
            "No result selected."
            if frozen is None
            else (
                f"{'Refined' if frozen.result_kind == 'derived' else 'Original'} Result · "
                f"{frozen.result_id}"
            )
        )
        self.selection_summary.setText(
            "Return to Results and select intervals."
            if not count
            else (
                f"{count:,} intervals from {recordings:,} recording{'s' if recordings != 1 else ''}"
            )
        )
        mode = self._mode()
        lines = []
        offset = 0
        for recording, candidate in rows:
            length = candidate.end_frame - candidate.start_frame
            snippet = safe_snippet_relative_path(
                recording.recording_key,
                candidate.start_frame,
                candidate.end_frame,
                candidate.candidate_id,
            )
            output = (
                snippet
                if mode is ExportMode.SNIPPETS
                else (f"{snippet} + corpus.wav" if mode is ExportMode.BOTH else "corpus.wav")
            )
            concat = (
                ""
                if mode is ExportMode.SNIPPETS
                else f" · output frames [{offset:,}, {offset + length:,})"
            )
            lines.append(
                f"{recording.recording_key} · {_source_time(candidate.start_time_ns)}–"
                f"{_source_time(candidate.end_time_ns)} · source frames "
                f"[{candidate.start_frame:,}, {candidate.end_frame:,}) → {output}{concat}"
            )
            offset += length
        self.mapping_label.setText("\n".join(lines) or "No selected calls to map.")
        audio_outputs = (
            count
            if mode is ExportMode.SNIPPETS
            else (1 if mode is ExportMode.CONCAT else count + 1)
        )
        companions = "Details file" if mode is ExportMode.SNIPPETS else "Raven TSV and details file"
        self.review_summary.setText(
            f"{audio_outputs:,} WAV output{'s' if audio_outputs != 1 else ''} · {companions}"
            if count
            else "Select calls in Results to continue."
        )
        state = ExportState(self.controller.export_state)
        active = bool(self.controller.is_export_active)
        destination = self.destination_picker.folderPath().strip()
        titles = {
            ExportState.READY: "Ready to export"
            if destination and count
            else ("Destination required" if count else "Selection required"),
            ExportState.RUNNING: "Exporting selected calls",
            ExportState.CONFLICT: "Destination conflict",
            ExportState.STALE: "Source changed",
            ExportState.CANCELLED: "Export cancelled",
            ExportState.ERROR: "Export failed",
            ExportState.SUCCESS: "Export completed",
        }
        self.status_title.setText(titles[state])
        detail = self.controller.export_message
        if state is ExportState.READY and not destination and count:
            detail = "Choose a persistent destination folder to continue."
        elif state is ExportState.READY and not count:
            detail = "Return to Results and choose at least one interval."
        storage_ready = False
        storage_error = ""
        if (
            state is ExportState.READY
            and count
            and destination
            and not active
            and not self.controller.export_history_warning
        ):
            try:
                self.storage_estimate = self.controller.estimate_export_storage(
                    mode,
                    Path(destination),
                )
            except (OSError, RuntimeError, ValueError) as exc:
                self.storage_estimate = None
                storage_error = str(exc)
                self.storage_section.clear()
            else:
                self.storage_section.set_estimate(self.storage_estimate)
                storage_ready = self.storage_estimate.can_start
        else:
            self.storage_estimate = None
            self.storage_section.clear()
        if storage_error:
            detail = storage_error
        self.status_detail.setText(detail)
        history_warning = getattr(self.controller, "export_history_warning", "")
        self.start_button.setEnabled(
            count > 0
            and bool(destination)
            and state is ExportState.READY
            and not active
            and not history_warning
            and storage_ready
        )
        self.cancel_button.setVisible(active)
        self.cancel_button.setEnabled(active)
        self.show_button.setVisible(
            state is ExportState.SUCCESS
            and self.controller.export_receipt is not None
            and Path(self.controller.export_receipt.final_destination).is_dir()
        )
        self.history_warning.setText(history_warning)
        self.history_warning.setVisible(bool(history_warning))
        self.retry_history_button.setVisible(bool(history_warning))
        self.retry_history_button.setEnabled(bool(history_warning) and not active)
        saved_export = (
            state is ExportState.SUCCESS
            and self.controller.export_receipt is not None
            and getattr(self.controller, "selected_export_id", None)
            == self.controller.export_receipt.export_id
            and not history_warning
        )
        self.view_exports_button.setVisible(saved_export)
        self.view_exports_button.setEnabled(saved_export)
        for button in (self.mode_snippets, self.mode_concat, self.mode_both):
            button.setEnabled(not active)
        self.destination_picker.setEnabled(not active)

    def set_compact(self, compact: bool) -> None:
        if compact == self._compact:
            return
        self._compact = compact
        for widget in (
            self.selection_card,
            self.format_card,
            self.destination_card,
            self.mapping_card,
            self.review_card,
        ):
            self.export_grid.removeWidget(widget)
        if compact:
            for row, widget in enumerate(
                (
                    self.selection_card,
                    self.format_card,
                    self.destination_card,
                    self.mapping_card,
                    self.review_card,
                )
            ):
                self.export_grid.addWidget(widget, row, 0)
            self.export_grid.setColumnStretch(0, 1)
            self.export_grid.setColumnStretch(1, 0)
        else:
            self.export_grid.addWidget(self.selection_card, 0, 0)
            self.export_grid.addWidget(self.review_card, 0, 1, 4, 1)
            self.export_grid.addWidget(self.format_card, 1, 0)
            self.export_grid.addWidget(self.destination_card, 2, 0)
            self.export_grid.addWidget(self.mapping_card, 3, 0)
            self.export_grid.setColumnStretch(0, 3)
            self.export_grid.setColumnStretch(1, 2)
        self.export_grid.invalidate()
        self.export_grid.activate()
        self.updateGeometry()

    @property
    def is_compact(self) -> bool:
        return self._compact

    def focus_initial(self) -> None:
        if self.start_button.isEnabled():
            self.start_button.setFocus()
            return
        buttons = self.destination_picker.findChildren(QWidget)
        target = next(
            (button for button in buttons if button.focusPolicy() != Qt.FocusPolicy.NoFocus),
            None,
        )
        (target or self.results_button).setFocus()


__all__ = ["ExportPage"]
