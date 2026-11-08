"""Build-aware worker command: never invoke host Python from a frozen Studio."""

from __future__ import annotations

import sys
from pathlib import Path


def worker_command(arguments: list[str]) -> tuple[str, list[str]]:
    """Use the same private CLI protocol in source and both native bundles."""
    if not getattr(sys, "frozen", False):
        return sys.executable, ["-m", "biocall_studio", *arguments]
    if sys.platform == "win32":
        # A windowed Windows EXE has no stdout. QProcess must instead start the
        # sibling console-subsystem EXE so the JSON progress protocol survives.
        executable = Path(sys.executable).with_name("BioCall Studio Worker.exe")
        if not executable.is_file():
            raise FileNotFoundError(f"Frozen Worker executable is missing: {executable}")
        return str(executable), arguments
    return sys.executable, arguments
