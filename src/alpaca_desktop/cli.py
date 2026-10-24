"""Command-line configuration, kept independent of GUI imports."""

import argparse
from importlib.metadata import version
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="alpaca Desktop Trainer")
    parser.add_argument("--version", action="version", version=version("alpaca-desktop"))
    parser.add_argument(
        "--settings-dir",
        type=Path,
        help="Isolate Application Settings in this directory instead of the Qt standard location.",
    )
    args = parser.parse_args(argv)

    from alpaca_desktop.gui.app import run

    return run(args.settings_dir)
