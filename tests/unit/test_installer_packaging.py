"""Spec 04A: static and source worker-launch checks, not installed native proof."""

import ast
import hashlib
import sys
import tomllib
from pathlib import Path

import pytest

from biocall_studio.shared.worker_launch import worker_command

ROOT = Path(__file__).resolve().parents[2]


def test_worker_launch_sources_and_native_paths(monkeypatch, tmp_path):
    """Source workers run module entry; macOS frozen workers share app binary."""
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python"))
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    arguments = ["--worker", "train-dataset-build"]
    assert worker_command(arguments) == (
        str(tmp_path / "python"), ["-m", "biocall_studio", *arguments]
    )
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert worker_command(arguments) == (str(tmp_path / "python"), arguments)


def test_windows_worker_must_be_console_executable(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "BioCall Studio.exe"))
    with pytest.raises(FileNotFoundError, match="Worker executable"):
        worker_command(["--worker", "detect-cnn"])
    worker = tmp_path / "BioCall Studio Worker.exe"
    worker.touch()
    assert worker_command(["--worker", "detect-cnn"]) == (
        str(worker), ["--worker", "detect-cnn"]
    )


def test_native_configs_are_both_present_and_source_paths_are_not_bundled():
    specs = [
        ROOT / "packaging/macos/biocall.spec",
        ROOT / "packaging/windows/biocall.spec",
    ]
    for spec in specs:
        source = spec.read_text(encoding="utf-8")
        ast.parse(source)
        assert "pathex=[]" in source
        assert "collect_bundle()" in source
        assert "BioCall Studio" in source
    windows = specs[1].read_text(encoding="utf-8")
    assert 'console=False' in windows
    assert 'console=True' in windows
    assert "BioCall Studio Worker" in windows
    macos = specs[0].read_text(encoding="utf-8")
    assert "icon.icns" in macos and "BUNDLE(" in macos
    installer = (ROOT / "packaging/windows/biocall.iss").read_text(encoding="utf-8")
    assert "icon.ico" in installer
    assert "recursesubdirs" in installer
    assert "[UninstallDelete]" not in installer.splitlines()


def test_canonical_version_and_published_wheels():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["version"] == "0.1.0a1"
    pins = project["tool"]["biocall-studio"]["science"]
    expected = (
        ("alp-ui", "0.1.0a1", "41bac72971b96d352da752cc0ff140afe3ac312a",
         "20590366d06591837c2567df1191b472b9db494e5440ce3a3fadfbf1b8d53d6c"),
        ("bioacoustics-dl-toolbox", "0.3.0",
         "7027bd84cc5a44a27bf201332af540f090c38365",
         "c0f7679cbf788c2900eff26b8db719941a513fc96b5f28348e2838c8df595b28"),
    )
    for package, version, revision, digest in expected:
        assert pins[f"{package}-version"] == version
        assert pins[f"{package}-revision"] == revision
        assert pins[f"{package}-wheel-sha256"] == digest
        assert f"/releases/download/v{version}/" in pins[f"{package}-wheel-url"]


@pytest.mark.parametrize(
    ("name", "digest"),
    [
        ("icon.icns", "a8ac55cbef988ac92b25bb6993a385c13718e56881d137b2f1705057efb85cce"),
        ("icon.ico", "7135f6a948f23aa650d8a7ffb9f3a483a4e7263556bee1fdc1d834d93a43193f"),
    ],
)
def test_checked_in_brand_assets_are_unchanged(name, digest):
    data = (ROOT / "assets/branding/icons" / name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == digest


def test_shared_freezer_lists_every_private_worker_and_legal_resource():
    source = (ROOT / "packaging/shared/freezer.py").read_text(encoding="utf-8")
    parsed = ast.parse(source)
    assert parsed
    for name in (
        "train-dataset-build", "train-cnn-training", "train-rf-training",
        "detect-cnn", "detect-rf-refinement",
        "biocall_studio", "alp_ui", "bioacoustics_dl_toolbox",
        "copy_metadata", "collect_data_files", "collect_submodules",
    ):
        assert name in source
    for filename in (
        "packaging/macos/build.sh",
        "packaging/windows/build.ps1",
        "packaging/macos/smoke.sh",
        "packaging/windows/smoke.ps1",
        "packaging/shared/native_smoke.py",
    ):
        assert (ROOT / filename).is_file()
