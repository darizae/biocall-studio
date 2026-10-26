from __future__ import annotations

import json
from pathlib import Path

import pytest

from biocall_studio_train.application.power import KeepAwakeManager, PowerInhibitionUnavailable
from biocall_studio_train.persistence.settings import ApplicationSettings, SettingsStore


class RecordingPowerAdapter:
    def __init__(self, *, acquire_error: Exception | None = None):
        self.acquire_error = acquire_error
        self.acquire_calls = 0
        self.release_calls = 0

    def acquire(self) -> None:
        self.acquire_calls += 1
        if self.acquire_error is not None:
            raise self.acquire_error

    def release(self) -> None:
        self.release_calls += 1


def test_settings_v2_migrates_and_v3_round_trips_keep_awake(tmp_path: Path):
    """Case: UT-POWER-001."""
    path = tmp_path / "settings.json"
    collection = tmp_path / "collection"
    collection.mkdir()
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "collection_path": str(collection),
                "collection_id": "collection-existing",
            }
        )
    )

    store = SettingsStore(path)
    migrated = store.load()
    assert migrated == ApplicationSettings(collection, "collection-existing", False)

    store.save(ApplicationSettings(collection, "collection-existing", True))
    assert store.load() == ApplicationSettings(collection, "collection-existing", True)
    assert json.loads(path.read_text()) == {
        "schema_version": 3,
        "collection_path": str(collection),
        "collection_id": "collection-existing",
        "keep_computer_awake": True,
    }


@pytest.mark.parametrize("invalid", [None, 1, "yes", [], {}])
def test_settings_v3_rejects_non_boolean_keep_awake(tmp_path: Path, invalid: object):
    """Case: UT-POWER-001."""
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "collection_path": None,
                "collection_id": None,
                "keep_computer_awake": invalid,
            }
        )
    )

    with pytest.raises(ValueError, match="Invalid Application Settings"):
        SettingsStore(path).load()


def test_keep_awake_manager_is_idempotent_and_reports_retryable_failure():
    """Case: UT-POWER-001."""
    adapter = RecordingPowerAdapter(acquire_error=OSError("power service refused request"))
    manager = KeepAwakeManager(adapter)

    failed = manager.apply_requested(True)
    assert failed.requested is True
    assert failed.active is False
    assert failed.available is True
    assert failed.error == "power service refused request"

    adapter.acquire_error = None
    active = manager.apply_requested(True)
    assert active.requested is True
    assert active.active is True
    assert active.error == ""
    manager.apply_requested(True)
    assert adapter.acquire_calls == 2

    off = manager.apply_requested(False)
    assert off.requested is False
    assert off.active is False
    manager.apply_requested(False)
    assert adapter.release_calls == 1


def test_keep_awake_manager_distinguishes_unsupported_platform():
    """Case: UT-POWER-001."""
    adapter = RecordingPowerAdapter(
        acquire_error=PowerInhibitionUnavailable("Idle-sleep prevention is unavailable here.")
    )
    state = KeepAwakeManager(adapter).apply_requested(True)

    assert state.requested is True
    assert state.active is False
    assert state.available is False
    assert "unavailable" in state.error
