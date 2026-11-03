"""Train-owned native presentation for the shared Qt-free storage decision."""

from __future__ import annotations

from alp_ui.components import HelpHint, Text
from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from biocall_studio.shared.storage import (
    EstimateKind,
    StorageDecision,
    StorageEstimate,
    format_binary_size,
    format_output_estimate,
)


class StorageSection(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAccessibleName("Storage estimate")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(5)
        layout.addWidget(Text("Storage", role="subheading"))

        output_row = QHBoxLayout()
        self.output = Text("", role="body", word_wrap=True)
        self.output.setAccessibleName("Estimated output")
        output_row.addWidget(self.output, 1)
        self.output_help = HelpHint(
            "Approximate space the finished files will use.",
            subject="Estimated output",
        )
        self.output_help.setObjectName("REV05-ESTIMATED-OUTPUT")
        output_row.addWidget(self.output_help)
        layout.addLayout(output_row)

        peak_row = QHBoxLayout()
        self.peak = Text("", role="body", word_wrap=True)
        self.peak.setAccessibleName("Space needed while running")
        peak_row.addWidget(self.peak, 1)
        self.peak_help = HelpHint(
            "Includes temporary files. Some are removed when the task finishes.",
            subject="Space while running",
        )
        self.peak_help.setObjectName("REV05-SPACE-WHILE-RUNNING")
        peak_row.addWidget(self.peak_help)
        layout.addLayout(peak_row)

        self.free = Text("", role="body", word_wrap=True)
        self.free.setAccessibleName("Destination free space")
        layout.addWidget(self.free)
        self.note = Text("", role="body", word_wrap=True)
        self.note.setAccessibleName("Storage guidance")
        layout.addWidget(self.note)
        self.hide()

    def set_estimate(self, estimate: StorageEstimate, *, variable: bool = False) -> None:
        if estimate.expected_final.kind is EstimateKind.UNAVAILABLE:
            self.output.setText(
                "Can't estimate the output size yet. Check the selected files and settings."
            )
            self.peak.setText("")
            self.peak.hide()
            self.peak_help.hide()
        else:
            self.output.setText(
                f"Estimated output: {format_output_estimate(estimate.expected_final)}"
            )
            peak = estimate.peak_bytes
            self.peak.setText(
                "Space needed while running: "
                + (f"about {format_binary_size(peak)}" if peak is not None else "unknown")
            )
            self.peak.show()
            self.peak_help.show()
        volume = estimate.volumes[0]
        self.free.setText(
            f"Free on {volume.target_label}: {format_binary_size(volume.free_bytes)}"
            if volume.free_bytes is not None
            else "Can't check free space on this destination."
        )
        if estimate.decision in {
            StorageDecision.TIGHT,
            StorageDecision.INSUFFICIENT,
            StorageDecision.STALE,
        }:
            note = estimate.reason
        elif variable and estimate.expected_final.kind is EstimateKind.RANGE:
            note = "Output size varies with the recording and settings."
        else:
            note = ""
        self.note.setText(note)
        self.note.setVisible(bool(note))
        self.show()

    def clear(self) -> None:
        self.hide()


def confirm_storage(parent: QWidget, estimate: StorageEstimate) -> bool:
    if not estimate.requires_confirmation:
        return True
    dialog = QMessageBox(parent)
    dialog.setWindowTitle("Storage")
    dialog.setIcon(QMessageBox.Icon.Warning)
    dialog.setText(estimate.reason)
    cancel = dialog.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    proceed = dialog.addButton("Continue", QMessageBox.ButtonRole.AcceptRole)
    dialog.setDefaultButton(cancel)
    dialog.setEscapeButton(cancel)
    dialog.exec()
    return dialog.clickedButton() is proceed


__all__ = ["StorageSection", "confirm_storage"]
