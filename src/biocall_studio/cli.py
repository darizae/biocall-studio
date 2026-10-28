"""Canonical BioCall Studio command line without eager GUI imports."""

import argparse
from importlib.metadata import version
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BioCall Studio")
    parser.add_argument("--version", action="version", version=version("biocall-studio-train"))
    parser.add_argument(
        "--settings-dir",
        type=Path,
        help="Isolate Studio application data, including Train settings, in this directory.",
    )
    parser.add_argument("--diagnostic-debug", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    from biocall_studio.gui.app import run

    return run(args.settings_dir, diagnostic_debug=args.diagnostic_debug)
