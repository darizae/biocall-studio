"""Run BioCall Studio tests without unexpectedly covering the active desktop."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class TestMode:
    marker: str
    qt_qpa_platform: str
    visible: bool = False


MODES = {
    "background": TestMode(
        marker="not soak and not native_cocoa",
        qt_qpa_platform="offscreen",
    ),
    "quick": TestMode(
        marker="not soak and not native_cocoa and not packaged",
        qt_qpa_platform="offscreen",
    ),
    "native": TestMode(
        marker="qt and not soak",
        qt_qpa_platform="cocoa",
        visible=True,
    ),
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run tests offscreen by default. Native mode opens visible Cocoa windows and "
            "requires --allow-visible."
        )
    )
    parser.add_argument("mode", nargs="?", choices=MODES, default="background")
    parser.add_argument(
        "--allow-visible",
        action="store_true",
        help="acknowledge that native mode may cover or focus the active desktop",
    )
    parser.add_argument(
        "--show-plan",
        action="store_true",
        help="print the resolved command and environment without running pytest",
    )
    return parser


def _reject_marker_override(parser: argparse.ArgumentParser, pytest_args: list[str]) -> None:
    if "-m" in pytest_args or "--markexpr" in pytest_args:
        parser.error(
            "pass a test path or -k expression, not a marker expression; "
            "the selected mode owns the safety marker"
        )


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    options, pytest_args = parser.parse_known_args(argv)
    _reject_marker_override(parser, pytest_args)
    mode = MODES[options.mode]
    command = [sys.executable, "-m", "pytest", "-m", mode.marker, *pytest_args]
    plan = {
        "mode": options.mode,
        "visible": mode.visible,
        "qt_qpa_platform": mode.qt_qpa_platform,
        "marker": mode.marker,
        "command": command,
    }
    if options.show_plan:
        print(json.dumps(plan, sort_keys=True))
        return 0
    if mode.visible and not options.allow_visible:
        parser.error(
            "native mode opens Cocoa windows; rerun with --allow-visible only when desktop "
            "interruption is acceptable, or use a dedicated macOS test session"
        )
    if mode.visible and sys.platform != "darwin":
        parser.error("native mode requires macOS; use background mode on this platform")

    environment = dict(os.environ)
    environment["QT_QPA_PLATFORM"] = mode.qt_qpa_platform
    return subprocess.run(command, env=environment, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
