"""The installed entry point is usable without the optional GUI dependencies."""

import subprocess
import sys
from importlib.metadata import version

import pytest

from alpaca_desktop.cli import main


def test_version_uses_installed_package_metadata_without_loading_gui(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == version("alpaca-desktop")


def test_help_explains_settings_isolation_without_loading_gui(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0
    output = capsys.readouterr().out
    assert "--settings-dir" in output
    assert "Qt standard location" in output


def test_package_and_cli_import_without_loading_optional_gui():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import alpaca_desktop; import alpaca_desktop.cli; "
            "assert not any(n.startswith(('PySide6', 'alp_ui')) for n in sys.modules)",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_unknown_option_fails_before_startup(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--unknown-option"])
    assert exit_info.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err
