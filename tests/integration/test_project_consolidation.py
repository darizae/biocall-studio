"""Installed-wheel boundary checks for the unified BioCall Studio distribution."""

from __future__ import annotations

import os
import subprocess
import sys
import venv
import zipfile
from importlib.util import find_spec
from pathlib import Path

import pytest

from biocall_studio.shared.owner_lifetime import OwnerLease

pytestmark = [pytest.mark.integration, pytest.mark.packaged]


def test_unified_wheel_shell_and_private_workers_have_one_installed_identity(tmp_path):
    """Case: IT-STU-009."""
    root = Path(__file__).resolve().parents[2]
    wheel_dir = tmp_path / "wheels"
    wheel_dir.mkdir()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(wheel_dir),
            str(root),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(wheel_dir.glob("biocall_studio-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    assert any(name.startswith("biocall_studio/") for name in names)
    assert not any(name.startswith("biocall_studio" + "_train/") for name in names)
    assert not any("biocall-studio" + "-train" in name for name in names)

    environment = tmp_path / "environment"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    scripts = environment / ("Scripts" if os.name == "nt" else "bin")
    toolbox_spec = find_spec("bioacoustics_dl_toolbox")
    alp_ui_spec = find_spec("alp_ui")
    assert toolbox_spec is not None and toolbox_spec.origin is not None
    assert alp_ui_spec is not None and alp_ui_spec.origin is not None
    released_site_packages = Path(toolbox_spec.origin).resolve().parent.parent
    assert Path(alp_ui_spec.origin).resolve().parent.parent == released_site_packages
    child_site_packages = Path(
        subprocess.run(
            [str(python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    (child_site_packages / "released-upstreams.pth").write_text(
        f"{released_site_packages}\n", encoding="utf-8"
    )
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--force-reinstall",
            str(wheel),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    check = subprocess.run(
        [
            str(python),
            "-c",
            (
                "import importlib.util; import pathlib; "
                "import alp_ui, biocall_studio, bioacoustics_dl_toolbox; "
                "from importlib.metadata import version; "
                "assert importlib.util.find_spec('biocall_studio' + '_train') is None; "
                f"root=pathlib.Path(r'{environment}'); "
                f"siblings=pathlib.Path(r'{root.parent}'); "
                "assert not pathlib.Path(alp_ui.__file__).is_relative_to(siblings / 'alp-ui'); "
                "assert not pathlib.Path(bioacoustics_dl_toolbox.__file__).is_relative_to("
                "siblings / 'bioacoustics-dl-toolbox'); "
                "assert version('alp-ui') == '0.1.0a1'; "
                "assert version('bioacoustics-dl-toolbox') == '0.3.0'; "
                "print(biocall_studio.__file__)"
            ),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert str(environment) in check.stdout
    assert (scripts / ("biocall-studio.exe" if os.name == "nt" else "biocall-studio")).exists()
    removed_command = "biocall-studio" + "-train"
    removed_executable = f"{removed_command}.exe" if os.name == "nt" else removed_command
    assert not (scripts / removed_executable).exists()

    suite_data = tmp_path / "suite-data"
    train_data = suite_data / "train" / "v1"
    shell_code = (
        "from PySide6.QtCore import QTimer; "
        "from pathlib import Path; "
        "from biocall_studio.studio.application.app import create_application; "
        "from biocall_studio.studio.application.coordinator import StudioCoordinator; "
        "from biocall_studio.train.application.workspace import WorkspaceController; "
        "app=create_application([]); "
        f"controller=WorkspaceController(Path(r'{train_data}')); "
        f"coordinator=StudioCoordinator(controller, detect_data_dir=Path(r'{suite_data}')); "
        f"expected_detect=Path(r'{suite_data}') / 'detect/v1'; "
        "assert coordinator.detect_controller.store.workspace_root == expected_detect; "
        "coordinator.start(); QTimer.singleShot(0, app.quit); app.exec(); "
        "controller.shutdown()"
    )
    shell = subprocess.run(
        [str(python), "-c", shell_code],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert shell.returncode == 0, shell.stderr

    lease = OwnerLease.create(tmp_path / "leases", prefix="integration")
    try:
        for mode in (
            "train-dataset-build",
            "train-cnn-training",
            "train-rf-training",
            "detect-cnn",
            "detect-rf-refinement",
        ):
            run = subprocess.run(
                [
                    str(python),
                    "-m",
                    "biocall_studio",
                    "--worker",
                    mode,
                    "--request",
                    str(tmp_path / f"missing-{mode}.json"),
                    "--owner-lease",
                    str(lease.path),
                ],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert run.returncode == 1, (mode, run.stdout, run.stderr)
    finally:
        lease.close()
