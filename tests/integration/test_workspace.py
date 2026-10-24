import json
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QStandardPaths

from alpaca_desktop.application.workspace import WorkspaceController
from alpaca_desktop.gui.window import MainWindow
from alpaca_desktop.persistence import settings as settings_module
from alpaca_desktop.persistence.settings import ROOT_LABELS

pytestmark = [pytest.mark.integration, pytest.mark.qt]


def test_independent_roots_reopen_without_touching_unrelated_settings(
    workspace, qtbot, tmp_path, monkeypatch
):
    """Scaffold boundary smoke; not an indexed Trainer acceptance case."""
    unrelated = tmp_path / "unrelated-settings"
    unrelated.mkdir()
    unrelated_file = unrelated / "workspace.json"
    seeded_bytes = b'{"schema_version":1,"roots":{"runs_root":"/unrelated"},"source_bindings":{}}'
    unrelated_file.write_bytes(seeded_bytes)
    default_calls = []

    def default_location(location):
        default_calls.append(location)
        return str(unrelated)

    monkeypatch.setattr(QStandardPaths, "writableLocation", default_location)
    opened = []
    original_open = Path.open

    def observed_open(path, *args, **kwargs):
        opened.append(path)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", observed_open)
    assert workspace.roots == {}
    assert not workspace.settings_file.parent.exists()
    window = MainWindow(workspace)
    qtbot.addWidget(window)
    window.show()
    window.navigation.setCurrentItem(window.navigation.topLevelItem(4))
    expected = {}
    for index, key in enumerate(ROOT_LABELS):
        root = tmp_path / f"volume-{index}" / f"root-{index}"
        root.mkdir(parents=True)
        expected[key] = root
        window.settings_page.root_fields[key].setText(str(root))
    window.settings_page.save_roots.click()
    assert not window.settings_page.error_alert.isVisible()
    reopened = WorkspaceController(workspace.settings_file.parent)
    assert reopened.roots == expected == workspace.roots
    for key, root in expected.items():
        assert reopened.root_path(key) == root
        assert list(root.iterdir()) == []
    raw = json.loads(workspace.settings_file.read_text())
    assert raw == {
        "schema_version": 1,
        "roots": {key: str(path) for key, path in expected.items()},
        "source_bindings": {},
    }
    assert not default_calls
    assert unrelated_file not in opened
    assert unrelated_file.read_bytes() == seeded_bytes
    assert list(unrelated.iterdir()) == [unrelated_file]
    assert list(workspace.settings_file.parent.iterdir()) == [workspace.settings_file]


@pytest.mark.parametrize("invalid_kind", ["missing", "unwritable"])
def test_invalid_root_shows_error_and_retains_previous_state(
    workspace, qtbot, tmp_path, monkeypatch, invalid_kind
):
    """Scaffold boundary smoke; not an indexed Trainer acceptance case."""
    prior = tmp_path / "previous-root"
    prior.mkdir()
    workspace.set_roots({"collection_root": prior})
    prior_bytes = workspace.settings_file.read_bytes()
    invalid = tmp_path / invalid_kind
    if invalid_kind == "unwritable":
        invalid.mkdir()
        invalid.chmod(0o555)
        if os.access(invalid, os.W_OK):
            invalid.chmod(0o755)
            pytest.skip(
                "This runner cannot enforce a read-only directory; native check remains blocked"
            )
    before_paths = set(tmp_path.rglob("*"))
    monkeypatch.chdir(tmp_path)
    try:
        window = MainWindow(workspace)
        qtbot.addWidget(window)
        window.show()
        window.navigation.setCurrentItem(window.navigation.topLevelItem(4))
        window.settings_page.root_fields["collection_root"].setText(str(invalid))
        window.settings_page.save_roots.click()
        assert window.settings_page.error_alert.isVisible()
        assert str(invalid) in window.settings_page.error_alert.text_widget.text()
        assert window.settings_page.error_alert.accessibleDescription()
        assert workspace.roots == {"collection_root": prior}
        assert workspace.root_path("collection_root") == prior
        assert workspace.settings_file.read_bytes() == prior_bytes
        assert set(tmp_path.rglob("*")) == before_paths
        assert not (tmp_path / "Alpaca Workspace").exists()
        assert list(prior.iterdir()) == []
    finally:
        if invalid_kind == "unwritable":
            invalid.chmod(0o755)


def test_external_bindings_persist_without_writing_sources_or_silently_relinking(
    workspace, qtbot, tmp_path
):
    """Scaffold boundary smoke; not an indexed Trainer acceptance case."""
    first = tmp_path / "external-a"
    second = tmp_path / "external-b"
    first.mkdir()
    second.mkdir()
    original = first / "source.txt"
    original.write_bytes(b"external source stays unchanged")
    window = MainWindow(workspace)
    qtbot.addWidget(window)
    window.show()
    window.navigation.setCurrentItem(window.navigation.topLevelItem(4))
    form = window.settings_page
    form.source_id.setText("source-a")
    form.source_path.setText(str(first))
    form.save_source.click()
    persisted = workspace.settings_file.read_bytes()
    assert WorkspaceController(workspace.settings_file.parent).source_bindings == {
        "source-a": first
    }
    assert form.source_list.count() == 1
    form.source_path.setText(str(second))
    form.save_source.click()
    assert form.error_alert.isVisible()
    assert "Verified relinking" in form.error_alert.text_widget.text()
    assert workspace.source_bindings == {"source-a": first}
    assert workspace.settings_file.read_bytes() == persisted
    assert original.read_bytes() == b"external source stays unchanged"
    assert list(first.iterdir()) == [original]
    assert list(second.iterdir()) == []


def test_corrupt_settings_are_visible_and_never_overwritten(workspace, qtbot, tmp_path):
    """Scaffold boundary smoke; not an indexed Trainer acceptance case."""
    workspace.settings_file.parent.mkdir()
    bad_bytes = b'{"schema_version":'
    workspace.settings_file.write_bytes(bad_bytes)
    reopened = WorkspaceController(workspace.settings_file.parent)
    window = MainWindow(reopened)
    qtbot.addWidget(window)
    window.show()
    assert window.pages.currentWidget() is window.settings_page
    assert window.settings_page.error_alert.isVisible()
    valid_root = tmp_path / "valid-root"
    valid_root.mkdir()
    window.settings_page.root_fields["collection_root"].setText(str(valid_root))
    window.settings_page.save_roots.click()
    assert "Repair Application Settings" in window.settings_page.error_alert.text_widget.text()
    assert workspace.settings_file.read_bytes() == bad_bytes
    assert reopened.roots == {}
    assert list(valid_root.iterdir()) == []


def test_standard_settings_location_and_failed_save_keep_previous_binding(
    workspace, qtbot, tmp_path, monkeypatch
):
    """Scaffold boundary smoke; not an indexed Trainer acceptance case."""
    location_calls = []

    def isolated_standard_location(location):
        location_calls.append(location)
        return str(tmp_path / "qt-app-local-data")

    monkeypatch.setattr(QStandardPaths, "writableLocation", isolated_standard_location)
    controller = WorkspaceController()
    assert location_calls == [QStandardPaths.StandardLocation.AppLocalDataLocation]
    assert controller.settings_file == tmp_path / "qt-app-local-data" / "workspace.json"
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    controller.set_roots({"runs_root": first})
    before = controller.settings_file.read_bytes()

    def failed_replace(source, destination):
        raise PermissionError("Application Settings destination is read-only")

    monkeypatch.setattr(settings_module.os, "replace", failed_replace)
    window = MainWindow(controller)
    qtbot.addWidget(window)
    window.show()
    window.navigation.setCurrentItem(window.navigation.topLevelItem(4))
    window.settings_page.root_fields["runs_root"].setText(str(second))
    window.settings_page.save_roots.click()
    assert window.settings_page.error_alert.isVisible()
    assert "read-only" in window.settings_page.error_alert.text_widget.text()
    assert controller.roots == {"runs_root": first}
    assert controller.settings_file.read_bytes() == before
    assert list(controller.settings_file.parent.iterdir()) == [controller.settings_file]
    assert list(first.iterdir()) == list(second.iterdir()) == []
