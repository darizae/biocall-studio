import builtins
import io
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QModelIndex, Qt, QTimer
from PySide6.QtTest import QAbstractItemModelTester
from PySide6.QtWidgets import QFileSystemModel

from alpaca_desktop.gui.models import DirectoryPageModel
from alpaca_desktop.gui.window import MainWindow

pytestmark = [pytest.mark.integration, pytest.mark.qt]


def test_requested_pages_service_qt_events_without_reading_scientific_files(
    workspace, qtbot, tmp_path, monkeypatch
):
    """Scaffold boundary smoke; not an indexed Trainer acceptance case."""
    root = tmp_path / "many-collections"
    root.mkdir()
    entry_count = 1500
    for number in range(entry_count):
        directory = root / f"collection-{number:04d}"
        directory.mkdir()
        (directory / "recordings.json").write_bytes(b"not a scientific manifest to parse")
    workspace.set_roots({"collection_root": root})
    payload_reads = []
    original_open = builtins.open
    original_io_open = io.open

    def observe_open(original, path, *args, **kwargs):
        if isinstance(path, (str, Path)) and Path(path).is_relative_to(root):
            payload_reads.append(Path(path))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(
        builtins,
        "open",
        lambda path, *args, **kwargs: observe_open(original_open, path, *args, **kwargs),
    )
    monkeypatch.setattr(
        io,
        "open",
        lambda path, *args, **kwargs: observe_open(original_io_open, path, *args, **kwargs),
    )
    ticks = [time.monotonic()]
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(time.monotonic()))
    timer.start(1)
    window = MainWindow(workspace)
    qtbot.addWidget(window)
    browser = window.browsers["Collections"]
    tester = QAbstractItemModelTester(
        browser.model, QAbstractItemModelTester.FailureReportingMode.Warning, browser.model
    )
    tester.setUseFetchMore(False)
    insertions = []
    browser.model.rowsInserted.connect(lambda parent, first, last: insertions.append((first, last)))
    window.show()
    try:
        qtbot.waitUntil(
            lambda: (
                browser.model.rowCount() == DirectoryPageModel.PAGE_SIZE
                and browser.filesystem.rowCount(browser.tree.rootIndex()) == entry_count
                and len(ticks) >= 3
            ),
            timeout=5000,
        )
        assert isinstance(browser.filesystem, QFileSystemModel)
        assert browser.table.model() is browser.model
        assert browser.tree.model() is browser.filesystem
        assert browser.filesystem.isReadOnly()
        assert all(
            other.filesystem is None
            for name, other in window.browsers.items()
            if name != "Collections"
        )
        assert browser.model.canFetchMore()
        browser.model.fetchMore()
        assert browser.model.rowCount() == 2 * DirectoryPageModel.PAGE_SIZE
        assert insertions[-1] == (100, 199)
        assert all(last - first + 1 <= DirectoryPageModel.PAGE_SIZE for first, last in insertions)
        assert browser.model.rowCount(browser.model.index(0, 0)) == 0
        assert browser.model.columnCount(browser.model.index(0, 0)) == 0
        assert browser.model.data(QModelIndex()) is None
        assert browser.model.data(browser.model.index(100, 0)).startswith("collection-")
        assert max(later - earlier for earlier, later in zip(ticks, ticks[1:])) < 1.0
        assert payload_reads == []
        first_name = browser.model.data(browser.model.index(0, 0))
        first_directory = root / first_name
        first_index = browser.filesystem.index(str(first_directory))
        browser.tree.setCurrentIndex(first_index)
        qtbot.waitUntil(lambda: browser.model.rowCount() == 1, timeout=5000)
        assert browser.model.data(browser.model.index(0, 0)) == "recordings.json"
        assert not browser.model.canFetchMore()
        assert payload_reads == []
    finally:
        timer.stop()


def test_root_changes_invalidate_bound_views_and_missing_roots_do_not_fall_back(
    workspace, qtbot, tmp_path
):
    """Scaffold boundary smoke; not an indexed Trainer acceptance case."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    datasets = tmp_path / "datasets"
    for directory in (first, second, datasets):
        directory.mkdir()
    (first / "old-folder").mkdir()
    (second / "new-folder").mkdir()
    (datasets / "dataset-folder").mkdir()
    workspace.set_roots({"collection_root": first, "datasets_root": datasets})
    window = MainWindow(workspace)
    qtbot.addWidget(window)
    window.show()
    browser = window.browsers["Collections"]
    qtbot.waitUntil(lambda: browser.model.rowCount() == 1, timeout=5000)
    assert browser.model.data(browser.model.index(0, 0)) == "old-folder"
    old_source = browser.filesystem
    workspace.set_roots({"collection_root": second})
    assert browser.filesystem is not old_source
    qtbot.waitUntil(lambda: browser.model.rowCount() == 1, timeout=5000)
    assert browser.model.data(browser.model.index(0, 0)) == "new-folder"
    assert browser.tree.rootIndex() == browser.filesystem.index(str(second))
    assert window.browsers["Datasets"].filesystem is None
    tree = window.navigation
    tree.setFocus()
    qtbot.keyClick(tree, Qt.Key.Key_Down)
    other = window.browsers["Datasets"]
    qtbot.waitUntil(lambda: other.model.rowCount() == 1, timeout=5000)
    assert other.model.data(other.model.index(0, 0)) == "dataset-folder"
    (second / "new-folder").rmdir()
    second.rmdir()
    settings_before = workspace.settings_file.read_bytes()
    tree.setCurrentItem(tree.topLevelItem(0).child(0))
    assert browser.error_alert.isVisible()
    assert str(second) in browser.error_alert.text_widget.text()
    assert browser.filesystem is None
    assert browser.model.rowCount() == 0
    assert workspace.roots["collection_root"] == second
    assert workspace.settings_file.read_bytes() == settings_before
    assert not second.exists()
    assert list(first.iterdir()) == [first / "old-folder"]
    assert list(datasets.iterdir()) == [datasets / "dataset-folder"]
