from __future__ import annotations

import subprocess
import sys
import time

import pytest

from biocall_studio_train.application.power import KeepAwakeManager, native_power_adapter

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    sys.platform not in {"darwin", "win32"},
    reason="Native idle-sleep inhibition is implemented for macOS and Windows.",
)
def test_native_idle_sleep_acquisition_release_and_process_death():
    """Case: IT-POWER-002; actual OS assertion belongs only to the GUI process lifetime."""
    manager = KeepAwakeManager(native_power_adapter())
    active = manager.apply_requested(True)
    assert active.active
    assert active.error == ""
    if sys.platform == "darwin":
        assertions = subprocess.run(
            ["pmset", "-g", "assertions"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert "BioCall Studio Train long-running local work" in assertions
    released = manager.release_for_shutdown()
    assert not released.active
    assert released.error == ""

    code = """
import time
from biocall_studio_train.application.power import KeepAwakeManager, native_power_adapter
manager = KeepAwakeManager(native_power_adapter())
state = manager.apply_requested(True)
assert state.active, state.error
print('active', flush=True)
time.sleep(60)
"""
    child = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "active"
        child.kill()
        child.wait(timeout=5)
        if sys.platform == "darwin":
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                assertions = subprocess.run(
                    ["pmset", "-g", "assertions"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout
                if "BioCall Studio Train long-running local work" not in assertions:
                    break
                time.sleep(0.05)
            assert "BioCall Studio Train long-running local work" not in assertions
    finally:
        if child.poll() is None:
            child.kill()
