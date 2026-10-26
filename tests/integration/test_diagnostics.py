from __future__ import annotations

import sys
from pathlib import Path
from zipfile import ZipFile

import pytest
from alp_ui.components import Alert, Button
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QMessageBox

from alpaca_desktop.application.collection_scan import scan_collection
from alpaca_desktop.application.workspace import WorkspaceController
from alpaca_desktop.domain.dataset import BuildConfig
from alpaca_desktop.domain.run import RunStatus
from alpaca_desktop.gui.app import create_application
from alpaca_desktop.gui.window import MainWindow
from alpaca_desktop.persistence.collection_metadata import publish_collection_metadata
from alpaca_desktop.persistence.diagnostics import read_diagnostic_records, worker_log_path
from alpaca_desktop.persistence.runs import load_run

pytestmark = pytest.mark.integration


def _config(result) -> BuildConfig:
    return BuildConfig(
        selected_recording_ids=tuple(record.id for record in result.records),
        negative_mode="ratio",
        negative_ratio=1.0,
        negative_count=0,
        allocation="proportional",
        train_percent=80,
        balance_classes=True,
        seed=42,
        margin_ms=100,
    )


def _ready(qtbot, tmp_path: Path, collection_factory, *, worker_delay: float = 0.0):
    root = tmp_path / "private-user-Collection"
    collection_factory(root, source_count=3)
    scan = publish_collection_metadata(root, scan_collection(root))
    controller = WorkspaceController(
        tmp_path / "settings",
        worker_step_delay_seconds=worker_delay,
        cancel_grace_ms=100,
        kill_grace_ms=200,
    )
    controller.bind_verified_collection(root, scan.collection_id)
    controller.reopen_bound_collection()
    qtbot.waitUntil(
        lambda: controller.scan_result is not None and not controller.is_scanning,
        timeout=10_000,
    )
    return root, scan, controller


@pytest.mark.qt
def test_real_session_scan_and_dataset_worker_write_correlated_private_logs(
    qtbot, tmp_path, collection_factory
):
    """Cases: IT-LOG-001, IT-LOG-002."""
    root, scan, controller = _ready(qtbot, tmp_path, collection_factory)
    app_records, notices = read_diagnostic_records(controller.diagnostics.path)
    assert notices == ()
    app_events = {record["event"] for record in app_records}
    assert {
        "session_started",
        "collection_bound",
        "collection_scan_started",
        "collection_scan_completed",
    } <= app_events
    assert {record["session_id"] for record in app_records} == {
        controller.diagnostics.session_id
    }

    run_id = controller.start_dataset_build(
        _config(scan), dataset_id="dataset-diagnostics"
    )
    qtbot.waitUntil(lambda: controller.active_run is None, timeout=20_000)
    run = load_run(root, run_id)
    assert run.status is RunStatus.COMPLETED
    worker_path = worker_log_path(root, run_id)
    worker_records, worker_notices = read_diagnostic_records(worker_path)
    assert worker_notices == ()
    assert {record["event"] for record in worker_records} >= {
        "worker_started",
        "worker_stage",
        "worker_completed",
    }
    assert {record["run_id"] for record in worker_records} == {run_id}
    assert {record["request_id"] for record in worker_records} == {run.request_id}
    assert {record["session_id"] for record in worker_records} == {
        controller.diagnostics.session_id
    }
    combined = controller.diagnostics.path.read_text() + worker_path.read_text()
    assert str(root) not in combined
    assert "private-user-Collection" not in combined
    assert "REC_A.wav" not in combined
    controller.shutdown()
    closed_records, _ = read_diagnostic_records(controller.diagnostics.path)
    assert [record["event"] for record in closed_records].count("session_finished") == 1
    controller.shutdown()


@pytest.mark.qt
def test_stderr_storm_is_drained_sanitized_and_cannot_complete_run(
    qtbot, tmp_path, collection_factory, monkeypatch
):
    """Case: IT-LOG-003."""
    root, scan, controller = _ready(qtbot, tmp_path, collection_factory)
    script = (
        "import json,sys; "
        "sys.stderr.write('/Users/alice/private-bird.wav token=secret\\n'*20000); "
        "sys.stderr.flush(); "
        "print(json.dumps({'schema_version':1,'event':'error','message':'worker failed'}),"
        " flush=True); raise SystemExit(1)"
    )
    monkeypatch.setattr(
        controller,
        "_worker_command",
        lambda _arguments: (sys.executable, ["-c", script]),
    )
    run_id = controller.start_dataset_build(_config(scan), dataset_id="dataset-stderr-fail")
    qtbot.waitUntil(lambda: controller.active_run is None, timeout=20_000)
    run = load_run(root, run_id)
    assert run.status is RunStatus.FAILED
    assert run.published_artifact_id is None
    assert not (root / ".alpaca" / "datasets" / "dataset-stderr-fail").exists()
    assert controller._run_stderr.dropped_bytes > 0
    app_records, _ = read_diagnostic_records(controller.diagnostics.path)
    stderr_records = [
        record for record in app_records if record["event"] == "worker_stderr_observed"
    ]
    assert len(stderr_records) == 1
    raw = controller.diagnostics.path.read_text()
    assert "alice" not in raw
    assert "private-bird.wav" not in raw
    assert "secret" not in raw


@pytest.mark.qt
def test_native_log_access_and_confirmed_sanitized_export(
    qapp, qtbot, tmp_path, collection_factory, monkeypatch
):
    """Case: IT-LOG-004."""
    create_application()
    root, scan, controller = _ready(qtbot, tmp_path, collection_factory)
    run_id = controller.start_dataset_build(_config(scan), dataset_id="dataset-ui-log")
    qtbot.waitUntil(lambda: controller.active_run is None, timeout=20_000)
    window = MainWindow(controller)
    qtbot.addWidget(window)
    window.show()
    window.open_run(run_id)

    detail = window.run_detail_page
    assert isinstance(detail.open_log_button, Button)
    assert detail.open_log_button.isVisible()
    assert detail.open_log_button.focusPolicy().value != 0
    opened: list[QUrl] = []
    monkeypatch.setattr(
        QDesktopServices,
        "openUrl",
        lambda url: opened.append(url) or True,
    )
    detail.open_log_button.click()
    assert opened and opened[-1].isLocalFile()
    assert opened[-1].toLocalFile().endswith("worker.jsonl")

    window.navigate("settings")
    settings = window.settings_page
    assert isinstance(settings.open_diagnostics_button, Button)
    assert isinstance(settings.export_diagnostics_button, Button)
    assert isinstance(settings.diagnostics_alert, Alert)
    destination = tmp_path / "support-bundle.zip"
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(destination), "ZIP archive (*.zip)"),
    )
    settings.export_diagnostics_button.setFocus()
    settings.export_diagnostics_button.click()
    assert destination.is_file()
    assert settings.diagnostics_alert.isVisible()
    assert "exported" in settings.diagnostics_alert.text_widget.text().lower()
    with ZipFile(destination) as archive:
        assert "diagnostics.json" in archive.namelist()
        assert f"runs/{run_id}/worker.jsonl" in archive.namelist()
        payload = b"".join(archive.read(name) for name in archive.namelist())
    assert str(root).encode() not in payload
    assert b"REC_A.wav" not in payload

    window.resize(700, 780)
    qtbot.waitUntil(lambda: settings.is_compact)
    assert settings.grid.itemAtPosition(0, 0).widget() is settings.binding_card
    assert settings.grid.itemAtPosition(1, 0).widget() is settings.plan_card

    old_run = next(item for item in controller.runs if item.run_id == run_id)
    worker_log_path(root, run_id).unlink()
    window.run_detail_page.set_run(old_run)
    assert not window.run_detail_page.open_log_button.isVisible()
    assert "older Runs" in window.run_detail_page.log_unavailable.text()
