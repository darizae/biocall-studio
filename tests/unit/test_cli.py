"""The installed entry point is usable without eager GUI dependencies."""

import subprocess
import sys
from importlib.metadata import version

import pytest

from biocall_studio import cli
from biocall_studio.cli import main


def test_version_uses_installed_package_metadata_without_loading_gui(capsys):
    """Case: UT-CLI-001, UT-CLI-002."""
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == version("biocall-studio")


def test_help_explains_settings_isolation_without_loading_gui(capsys):
    """Case: UT-CLI-001."""
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0
    output = capsys.readouterr().out
    assert "--settings-dir" in output
    assert "application data" in output


def test_package_and_cli_import_without_loading_optional_gui():
    """Case: UT-CLI-001, UT-CLI-002."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import biocall_studio; import biocall_studio.cli; "
            "assert not any(n.startswith(('PySide6', 'alp_ui')) for n in sys.modules)",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_unknown_option_fails_before_startup(capsys):
    """Case: UT-CLI-001, UT-CLI-002."""
    with pytest.raises(SystemExit) as exit_info:
        main(["--unknown-option"])
    assert exit_info.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err


def test_invalid_worker_arguments_fail_without_gui_or_scientific_imports():
    """Case: UT-CLI-002."""
    code = """
import sys
from biocall_studio.cli import main
try:
    main(['--worker', 'train-cnn-training'])
except SystemExit as exc:
    assert exc.code == 2
else:
    raise AssertionError('invalid Worker arguments were accepted')
assert not any(name.startswith(('PySide6', 'alp_ui')) for name in sys.modules)
assert 'biocall_studio.train.workflows.worker_entry' not in sys.modules
assert 'biocall_studio.detect.workflows.detection' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr


def test_canonical_worker_modes_are_exact_and_require_private_arguments(monkeypatch, capsys):
    """Case: UT-CLI-002."""
    expected = {
        "train-dataset-build",
        "train-cnn-training",
        "train-rf-training",
        "detect-cnn",
        "detect-rf-refinement",
    }
    assert set(cli.WORKER_MODES) == expected

    class Guard:
        def close(self):
            pass

    called: list[tuple[str, object]] = []
    monkeypatch.setattr(cli, "_validated_owner_guard", lambda _parser, _path: Guard())
    monkeypatch.setattr(
        cli,
        "_dispatch_worker",
        lambda args, **_kwargs: called.append((args.worker, args.request)) or 0,
    )
    for mode in sorted(expected):
        request = f"/{mode}.json"
        assert main(["--worker", mode, "--request", request, "--owner-lease", "/owner"]) == 0
    assert [mode for mode, _request in called] == sorted(expected)

    for arguments in (
        ["--worker", "dataset-build", "--request", "/request", "--owner-lease", "/owner"],
        ["--worker", "train-dataset-build", "--owner-lease", "/owner"],
        ["--worker", "train-dataset-build", "--request", "/request"],
        ["--worker", "unknown", "--request", "/request", "--owner-lease", "/owner"],
    ):
        with pytest.raises(SystemExit) as exit_info:
            main(arguments)
        assert exit_info.value.code == 2
    assert called
    error_output = capsys.readouterr().err
    assert "required" in error_output or "invalid choice" in error_output


def test_worker_delay_and_diagnostic_session_are_bounded_before_dispatch(capsys):
    """Case: UT-CLI-002."""
    base = [
        "--worker",
        "detect-cnn",
        "--request",
        "/request",
        "--owner-lease",
        "/owner",
    ]
    for extra in (
        ["--worker-step-delay", "-0.1"],
        ["--worker-step-delay", "5.1"],
        ["--diagnostic-session-id", "not-a-session"],
    ):
        with pytest.raises(SystemExit) as exit_info:
            main([*base, *extra])
        assert exit_info.value.code == 2
    assert capsys.readouterr().err
