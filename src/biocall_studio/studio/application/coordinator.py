"""One-process ownership and whole-window workspace switching."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from biocall_studio.detect.application.controller import DetectWorkspaceController
from biocall_studio.detect.domain import RootBindingDecision
from biocall_studio.review.application.controller import (
    ReviewSessionController,
    default_spectrogram_snapshot,
)
from biocall_studio.review.application.data_location import (
    ReviewDataLocationError,
    ReviewDataLocationManager,
    ReviewDataMovePlan,
)
from biocall_studio.review.domain.intake import ReviewResultKind
from biocall_studio.review.gui.workspace import ReviewResultChoice, ReviewWorkspacePage
from biocall_studio.review.persistence.intake import IntakeAvailability
from biocall_studio.review.persistence.sessions import ReviewSession
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


class _ReviewDataMoveThread(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        manager: ReviewDataLocationManager,
        plan: ReviewDataMovePlan,
        *,
        confirm_storage: bool,
    ):
        super().__init__()
        self.manager = manager
        self.plan = plan
        self.confirm_storage = confirm_storage

    def run(self) -> None:
        try:
            self.manager.move(self.plan, confirm_storage=self.confirm_storage)
        except (OSError, RuntimeError, TypeError, ValueError):
            self.failed.emit("Couldn't move Review data. Your original folder is unchanged.")
            return
        self.succeeded.emit(self.plan.target_root)


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
        self.review_data_locations = ReviewDataLocationManager(detect_data_dir)
        self.review_controller, self.review_page = self._create_review_workspace(
            self.review_data_locations.current_root()
        )
        self._review_move_thread: _ReviewDataMoveThread | None = None
        self._exit_after_review_move = False
        self.shell_window = StudioWindow(self.detect_controller, self.review_page)
        self.train_window = MainWindow(
            controller,
            back_to_studio=self.show_studio,
            application_exit_request=self.request_application_exit,
        )
        self.exit_dialog: QMessageBox | None = None
        self._exit_keep_button = None
        self._exit_stop_button = None
        self._exit_dialog_action: ExitAction | None = None
        self.exit_failure_dialog: QMessageBox | None = None
        self._application_exit_finishing = False
        self._application_exit_complete = False
        self._train_exit_finished = False
        self._review_exit_save = False
        self._review_stop_deadline = 0.0

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

    def _create_review_workspace(
        self, review_data_root
    ) -> tuple[ReviewSessionController, ReviewWorkspacePage]:
        controller = ReviewSessionController(
            self.review_data_locations.suite_data_root,
            review_data_root=review_data_root,
        )
        self.review_controller = controller
        now = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        controller.ensure_default_preset(default_spectrogram_snapshot(), saved_at=now)
        page = ReviewWorkspacePage(
            controller,
            result_provider=self._review_result_choices,
            source_root_resolver=self._review_source_root,
            operation_admission=lambda run_id, label: self._assert_run_admitted(
                WorkflowOwner.REVIEW, run_id, label
            ),
        )
        page.data_folder_change_requested.connect(self.request_review_data_folder_change)
        recovered = controller.recover_open_session(recovered_at=now)
        if recovered is not None:
            page.open_session(recovered.session_id)
        return controller, page

    def start(self) -> None:
        self.shell_window.show_workspace(WorkspaceRoute.STUDIO)
        self.shell_window.show()
        self.shell_window.raise_()
        self.shell_window.activateWindow()

    def open_workspace(self, route: str | WorkspaceRoute) -> None:
        previous = self.navigation.current
        decision = self.navigation.navigate(route)
        self.navigation = decision
        if previous is WorkspaceRoute.REVIEW and decision.current is not WorkspaceRoute.REVIEW:
            self.review_page.leave_workspace()
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

    def _review_result_choices(self) -> tuple[ReviewResultChoice, ...]:
        choices: list[ReviewResultChoice] = []
        for item in self.detect_controller.result_history:
            result = item.result
            if not item.available or result is None:
                continue
            inspection = self.review_controller.intake.intake(
                result.collection_id, result.result_id
            )
            if (
                inspection.availability is not IntakeAvailability.READY
                or inspection.manifest is None
            ):
                continue
            choices.append(
                ReviewResultChoice(
                    collection_id=result.collection_id,
                    result_id=result.result_id,
                    name=(
                        next(
                            (
                                record.title
                                for record in self.detect_controller.runs
                                if record.run_id == item.run_id
                            ),
                            result.result_id,
                        )
                    ),
                    kind=(
                        "RF refined"
                        if inspection.manifest.result_kind is ReviewResultKind.RF
                        else "Original"
                    ),
                    completed_at=result.completed_at,
                    eligible_count=inspection.manifest.eligible_candidate_count,
                )
            )
        return tuple(choices)

    def _review_source_root(self, session: ReviewSession):
        try:
            source = self.review_controller.store.load_source(session.session_id)
            collection = self.detect_controller.store.load_collection(
                source.manifest.collection_id
            )
            if (
                self.detect_controller.store.root_decision(collection)
                is not RootBindingDecision.VALID
            ):
                return None
            return collection.source_root
        except (OSError, RuntimeError, ValueError):
            return None

    def _review_move_forbidden_roots(self) -> tuple:
        roots = []
        collection_ids = {
            item.result.collection_id
            for item in self.detect_controller.result_history
            if item.result is not None
        }
        for collection_id in collection_ids:
            try:
                roots.append(self.detect_controller.store.load_collection(collection_id).source_root)
            except (OSError, RuntimeError, ValueError):
                continue
        for record in self.review_controller.list_export_history():
            roots.append(record.final_destination)
        return tuple(roots)

    def request_review_data_folder_change(self, target) -> None:
        page = self.review_page
        page.show_data_settings()
        if self._review_move_thread is not None:
            page.data_settings_page.set_status("Review data is already being moved.")
            return
        if not page.data_location_change_allowed:
            page.data_settings_page.reset_selection()
            page.data_settings_page.set_status(
                "Close the open Review session before changing the folder."
            )
            return
        try:
            plan = self.review_data_locations.plan_move(
                target,
                forbidden_roots=tuple(Path(root) for root in self._review_move_forbidden_roots()),
            )
        except (OSError, ReviewDataLocationError, ValueError) as exc:
            page.data_settings_page.reset_selection()
            page.data_settings_page.set_status(str(exc))
            return
        confirmed = False
        if plan.storage_estimate.requires_confirmation:
            answer = QMessageBox.question(
                self.shell_window,
                "Review data folder",
                plan.storage_estimate.reason,
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok,
                QMessageBox.StandardButton.Cancel,
            )
            if answer is not QMessageBox.StandardButton.Ok:
                page.data_settings_page.set_status("Review data folder unchanged.")
                return
            confirmed = True
        page.data_settings_page.set_moving(True)
        page.shutdown()
        self.review_controller.shutdown()
        thread = _ReviewDataMoveThread(
            self.review_data_locations,
            plan,
            confirm_storage=confirmed,
        )
        self._review_move_thread = thread
        thread.succeeded.connect(self._review_data_move_succeeded)
        thread.failed.connect(self._review_data_move_failed)

        def finished() -> None:
            if self._review_move_thread is thread:
                self._review_move_thread = None
            thread.deleteLater()
            if self._exit_after_review_move:
                self._exit_after_review_move = False
                QTimer.singleShot(0, self.request_application_exit)

        thread.finished.connect(finished)
        thread.start()

    def _replace_review_workspace(self, root, *, status: str) -> None:
        controller, page = self._create_review_workspace(root)
        self.review_controller = controller
        self.review_page = page
        self.shell_window.replace_review_page(page)
        page.show_data_settings()
        page.data_settings_page.set_status(status)
        page.focus_initial()

    def _review_data_move_succeeded(self, target) -> None:
        self._replace_review_workspace(
            target,
            status="Review data moved. Existing sessions and settings are ready.",
        )

    def _review_data_move_failed(self, message: str) -> None:
        try:
            root = self.review_data_locations.current_root()
            self._replace_review_workspace(
                root,
                status=(
                    message
                    or "Couldn't move Review data. Your original folder is unchanged."
                ),
            )
        except (OSError, RuntimeError, ValueError):
            QMessageBox.critical(
                self.shell_window,
                "Review data folder",
                "Couldn't move Review data. Your original folder is unchanged.",
            )

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
        review_operation = self.review_page.active_operation
        if review_operation is not None:
            run_id, label = review_operation
            operations.append(OwnedOperation(WorkflowOwner.REVIEW, run_id, label))
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
        if self._review_move_thread is not None:
            self._exit_after_review_move = True
            self.open_workspace(WorkspaceRoute.REVIEW)
            self.review_page.show_data_settings()
            self.review_page.data_settings_page.set_status(
                "Wait for the Review data move to finish before exiting."
            )
            return
        if self.exit_failure_dialog is not None and self.exit_failure_dialog.isVisible():
            self.exit_failure_dialog.raise_()
            self.exit_failure_dialog.activateWindow()
            return
        if self.exit_dialog is not None and self.exit_dialog.isVisible():
            self.exit_dialog.raise_()
            self.exit_dialog.activateWindow()
            return
        decision = decide_application_exit(
            self._active_scientific_operations(),
            review_session_open=self.review_page.has_open_session,
        )
        if decision.action in {
            ExitAction.CONFIRM_STOP,
            ExitAction.CONFIRM_SAVE_REVIEW,
        }:
            self._show_exit_dialog(decision)
            return
        self._begin_coordinated_shutdown()

    def _show_exit_dialog(self, decision) -> None:
        parent = self.train_window if self.train_window.isVisible() else self.shell_window
        dialog = QMessageBox(parent)
        dialog.setObjectName("studioExitDialog")
        review_exit = decision.action is ExitAction.CONFIRM_SAVE_REVIEW
        dialog.setAccessibleName(
            "Save the Open Review session before exit"
            if review_exit
            else "Stop active BioCall Studio work before exit"
        )
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Open Review session" if review_exit else "Active work")
        dialog.setText(decision.summary)
        if review_exit:
            active = "; ".join(
                f"{operation.label} in {operation.owner.value}"
                for operation in decision.operations
            )
            dialog.setInformativeText(
                "BioCall Studio will save and close the Review session, stop active work "
                "safely, and then exit."
                + (f" Active work: {active}." if active else "")
            )
        else:
            dialog.setInformativeText(
                "If you exit, BioCall Studio will stop each active operation and wait for its "
                "worker to finish. Completed Models, Results, and exports remain unchanged."
            )
        keep = dialog.addButton("Keep app open", QMessageBox.ButtonRole.RejectRole)
        stop = dialog.addButton(
            "Save and Exit" if review_exit else "Stop work and Exit",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        keep.setAccessibleDescription("Leave all active work running and keep the app open.")
        stop.setAccessibleDescription(
            "Save and close the Review session, stop active work safely, then exit BioCall Studio."
            if review_exit
            else "Stop all active work safely, then exit BioCall Studio."
        )
        dialog.setDefaultButton(keep)
        dialog.setEscapeButton(keep)
        self.exit_dialog = dialog
        self._exit_keep_button = keep
        self._exit_stop_button = stop
        self._exit_dialog_action = decision.action
        dialog.finished.connect(self._exit_dialog_finished)
        dialog.open()
        keep.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def _exit_dialog_finished(self, _result: int) -> None:
        dialog = self.exit_dialog
        if dialog is None:
            return
        stop_requested = dialog.clickedButton() is self._exit_stop_button
        action = self._exit_dialog_action
        self.exit_dialog = None
        self._exit_keep_button = None
        self._exit_stop_button = None
        self._exit_dialog_action = None
        dialog.deleteLater()
        if stop_requested:
            self._begin_coordinated_shutdown(
                save_review_session=action is ExitAction.CONFIRM_SAVE_REVIEW
            )

    def _begin_coordinated_shutdown(self, *, save_review_session: bool = False) -> None:
        if self._application_exit_finishing:
            return
        self._application_exit_finishing = True
        self._review_exit_save = save_review_session
        self._review_stop_deadline = time.monotonic() + 15.0
        try:
            self.review_page.request_exit_stop()
        except (OSError, RuntimeError, ValueError):
            self._abort_application_exit("Review work couldn't be stopped. Try again.")
            return
        QTimer.singleShot(0, self._continue_after_review_stop)

    def _continue_after_review_stop(self) -> None:
        if not self._application_exit_finishing or self._application_exit_complete:
            return
        if not self.review_page.exit_stop_ready:
            if time.monotonic() >= self._review_stop_deadline:
                self._abort_application_exit(
                    "Review work couldn't be stopped. Wait for it to finish, then try again."
                )
                return
            QTimer.singleShot(25, self._continue_after_review_stop)
            return
        if self._review_exit_save:
            try:
                self.review_page.checkpoint_open_session_for_exit()
            except (OSError, RuntimeError, ValueError):
                self._abort_application_exit(
                    "The Review session couldn't be saved. Check storage access and try again."
                )
                return
        self._review_exit_save = False
        self.detect_controller.request_shutdown()
        self.train_window.begin_application_exit()
        QTimer.singleShot(25, self._finish_application_exit)

    def _abort_application_exit(self, message: str) -> None:
        self._application_exit_finishing = False
        self._review_exit_save = False
        parent = self.train_window if self.train_window.isVisible() else self.shell_window
        dialog = QMessageBox(parent)
        dialog.setObjectName("studioExitFailureDialog")
        dialog.setAccessibleName("BioCall Studio exit blocked")
        dialog.setIcon(QMessageBox.Icon.Critical)
        dialog.setWindowTitle("Couldn't exit")
        dialog.setText(message)
        keep = dialog.addButton("Keep app open", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(keep)
        dialog.setEscapeButton(keep)
        self.exit_failure_dialog = dialog

        def finished(_result: int) -> None:
            if self.exit_failure_dialog is dialog:
                self.exit_failure_dialog = None
            dialog.deleteLater()

        dialog.finished.connect(finished)
        dialog.open()
        keep.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

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
        if self.review_page.has_open_session:
            self._abort_application_exit(
                "The Review session is still open. Save and close it before exiting."
            )
            return
        self.review_page.shutdown()
        self.review_controller.shutdown()
        self._application_exit_complete = True
        self.shell_window.allow_application_close()
        self.shell_window.close()
        self.app.quit()
