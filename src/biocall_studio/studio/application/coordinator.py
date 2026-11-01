"""One-process ownership and whole-window workspace switching."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from biocall_studio.detect.application.controller import DetectWorkspaceController
from biocall_studio.studio.application.navigation import WorkspaceNavigation, WorkspaceRoute
from biocall_studio.studio.application.operations import (
    ExitAction,
    OwnedOperation,
    WorkflowOwner,
    decide_application_exit,
    decide_scientific_admission,
)
from biocall_studio.studio.gui.shell import StudioWindow
from biocall_studio.train.application.workspace import WorkspaceController
from biocall_studio.train.gui.window import MainWindow


class StudioCoordinator(QObject):
    """Retain Train intact while the suite shell controls visibility and app exit."""

    def __init__(
        self, controller: WorkspaceController, *, detect_data_dir=None
    ):
        super().__init__()
        app = QApplication.instance()
        if not isinstance(app, QApplication):
            raise RuntimeError("StudioCoordinator requires an existing QApplication.")
        self.app = app
        self.controller = controller
        self.navigation = WorkspaceNavigation()
        if detect_data_dir is None:
            train_root = controller.settings_file.parent.resolve()
            detect_data_dir = (
                train_root.parent.parent
                if train_root.parts[-2:] == ("train", "v1")
                else train_root.parent
            )
        self.detect_controller = DetectWorkspaceController(detect_data_dir)
        self.shell_window = StudioWindow(self.detect_controller)
        self.train_window = MainWindow(
            controller,
            back_to_studio=self.show_studio,
            application_exit_request=self.request_application_exit,
        )
        self.exit_dialog: QMessageBox | None = None
        self._exit_keep_button = None
        self._exit_stop_button = None
        self._application_exit_finishing = False
        self._application_exit_complete = False
        self._train_exit_finished = False

        self.controller.set_run_admission(
            lambda run_id, label: self._assert_run_admitted(
                WorkflowOwner.TRAIN, run_id, label
            )
        )
        self.detect_controller.set_run_admission(
            lambda run_id, label: self._assert_run_admitted(
                WorkflowOwner.DETECT, run_id, label
            )
        )

        self.shell_window.workspace_requested.connect(self.open_workspace)
        self.shell_window.application_exit_requested.connect(self.request_application_exit)
        self.train_window.application_exit_completed.connect(self._train_exit_completed)

    def start(self) -> None:
        self.shell_window.show_workspace(WorkspaceRoute.STUDIO)
        self.shell_window.show()
        self.shell_window.raise_()
        self.shell_window.activateWindow()

    def open_workspace(self, route: str | WorkspaceRoute) -> None:
        decision = self.navigation.navigate(route)
        self.navigation = decision
        if decision.current is WorkspaceRoute.TRAIN:
            self.shell_window.hide()
            self.train_window.show()
            self.train_window.raise_()
            self.train_window.activateWindow()
            if self.train_window.back_to_studio_button is not None:
                self.train_window.back_to_studio_button.setFocus()
            return
        self.train_window.hide()
        self.shell_window.show_workspace(decision.current)
        self.shell_window.show()
        self.shell_window.raise_()
        self.shell_window.activateWindow()

    def show_studio(self) -> None:
        self.open_workspace(WorkspaceRoute.STUDIO)

    def _active_scientific_operations(self) -> tuple[OwnedOperation, ...]:
        operations: list[OwnedOperation] = []
        train_run = self.controller.active_run
        if train_run is not None:
            if train_run.kind.value == "dataset_build":
                label = "Dataset Build"
            elif train_run.training_family == "cnn":
                label = "CNN Training"
            else:
                label = "Random Forest Training"
            operations.append(OwnedOperation(WorkflowOwner.TRAIN, train_run.run_id, label))
        detect_run = self.detect_controller.active_run
        if detect_run is not None:
            operations.append(
                OwnedOperation(
                    WorkflowOwner.DETECT,
                    detect_run.run_id,
                    detect_run.title,
                )
            )
        return tuple(operations)

    def _assert_run_admitted(
        self,
        owner: WorkflowOwner,
        run_id: str,
        label: str,
    ) -> None:
        decision = decide_scientific_admission(
            OwnedOperation(owner, run_id, label),
            self._active_scientific_operations(),
        )
        if not decision.allowed:
            raise ValueError(decision.reason)

    def request_application_exit(self) -> None:
        if self._application_exit_finishing:
            return
        if self.exit_dialog is not None and self.exit_dialog.isVisible():
            self.exit_dialog.raise_()
            self.exit_dialog.activateWindow()
            return
        decision = decide_application_exit(self._active_scientific_operations())
        if decision.action is ExitAction.CONFIRM_STOP:
            self._show_exit_dialog(decision.summary)
            return
        self._begin_coordinated_shutdown()

    def _show_exit_dialog(self, summary: str) -> None:
        parent = self.train_window if self.train_window.isVisible() else self.shell_window
        dialog = QMessageBox(parent)
        dialog.setObjectName("studioExitDialog")
        dialog.setAccessibleName("Stop active BioCall Studio work before exit")
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Active work")
        dialog.setText(summary)
        dialog.setInformativeText(
            "If you exit, BioCall Studio will stop each active operation and wait for its "
            "worker to finish. Completed Models, Results, and exports remain unchanged."
        )
        keep = dialog.addButton("Keep app open", QMessageBox.ButtonRole.RejectRole)
        stop = dialog.addButton("Stop work and Exit", QMessageBox.ButtonRole.DestructiveRole)
        keep.setAccessibleDescription("Leave all active work running and keep the app open.")
        stop.setAccessibleDescription("Stop all active work safely, then exit BioCall Studio.")
        dialog.setDefaultButton(keep)
        dialog.setEscapeButton(keep)
        self.exit_dialog = dialog
        self._exit_keep_button = keep
        self._exit_stop_button = stop
        dialog.finished.connect(self._exit_dialog_finished)
        dialog.open()
        keep.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def _exit_dialog_finished(self, _result: int) -> None:
        dialog = self.exit_dialog
        if dialog is None:
            return
        stop_requested = dialog.clickedButton() is self._exit_stop_button
        self.exit_dialog = None
        self._exit_keep_button = None
        self._exit_stop_button = None
        dialog.deleteLater()
        if stop_requested:
            self._begin_coordinated_shutdown()

    def _begin_coordinated_shutdown(self) -> None:
        if self._application_exit_finishing:
            return
        self._application_exit_finishing = True
        self.detect_controller.request_shutdown()
        self.train_window.begin_application_exit()
        QTimer.singleShot(25, self._finish_application_exit)

    def _train_exit_completed(self) -> None:
        self._train_exit_finished = True
        QTimer.singleShot(0, self._finish_application_exit)

    def _finish_application_exit(self) -> None:
        if not self._application_exit_finishing or self._application_exit_complete:
            return
        if not self.detect_controller._shutdown_finished:
            if self.detect_controller.shutdown_is_ready:
                self.detect_controller.shutdown()
            else:
                QTimer.singleShot(25, self._finish_application_exit)
                return
        if not self._train_exit_finished:
            QTimer.singleShot(25, self._finish_application_exit)
            return
        self._application_exit_complete = True
        self.shell_window.allow_application_close()
        self.shell_window.close()
        self.app.quit()
