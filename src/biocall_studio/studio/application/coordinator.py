"""One-process ownership and whole-window workspace switching."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from biocall_studio.detect.application.controller import DetectWorkspaceController
from biocall_studio.studio.application.navigation import WorkspaceNavigation, WorkspaceRoute
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
        self.train_window = MainWindow(controller, back_to_studio=self.show_studio)
        self._application_exit_finishing = False

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

    def request_application_exit(self) -> None:
        if self._application_exit_finishing:
            return
        if (
            self.detect_controller.is_scanning
            or self.detect_controller.is_model_loading
            or self.detect_controller.is_run_active
            or not self.detect_controller.shutdown_is_ready
        ):
            self.detect_controller.request_shutdown()
            QTimer.singleShot(25, self.request_application_exit)
            return
        if not self.detect_controller._shutdown_finished:
            self.detect_controller.shutdown()
        if self.controller.active_run is not None or self.controller.is_scanning:
            self.open_workspace(WorkspaceRoute.TRAIN)
        self.train_window.close()

    def _train_exit_completed(self) -> None:
        if self._application_exit_finishing:
            return
        self._application_exit_finishing = True
        QTimer.singleShot(0, self._finish_application_exit)

    def _finish_application_exit(self) -> None:
        self.shell_window.allow_application_close()
        self.shell_window.close()
        self.app.quit()
