from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parents[2] / "scripts" / "run_tests.py"


@pytest.mark.parametrize(
    ("mode", "platform", "marker"),
    [
        ("background", "offscreen", "not soak and not native_cocoa"),
        (
            "quick",
            "offscreen",
            "not soak and not native_cocoa and not packaged",
        ),
        ("native", "cocoa", "qt and not soak"),
    ],
)
def test_test_runner_modes_keep_background_invisible_and_native_explicit(
    mode: str, platform: str, marker: str
):
    """Case: UT-DEV-001."""
    shown = subprocess.run(
        [sys.executable, str(RUNNER), mode, "--show-plan", "tests/unit", "-q"],
        check=True,
        capture_output=True,
        text=True,
    )
    plan = json.loads(shown.stdout)
    assert plan["qt_qpa_platform"] == platform
    assert plan["marker"] == marker
    assert plan["command"][-2:] == ["tests/unit", "-q"]

    if mode == "native":
        refused = subprocess.run(
            [sys.executable, str(RUNNER), mode, "--collect-only"],
            capture_output=True,
            text=True,
        )
        assert refused.returncode == 2
        assert "--allow-visible" in refused.stderr


def test_test_runner_rejects_marker_override_that_could_enable_visible_cases():
    """Case: UT-DEV-001."""
    result = subprocess.run(
        [sys.executable, str(RUNNER), "background", "-m", "qt"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "marker expression" in result.stderr
