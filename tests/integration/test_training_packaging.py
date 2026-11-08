"""Released-upstream wheel and Studio packaging contract, without sibling checkouts."""

from __future__ import annotations

import tomllib
import zipfile
from importlib import metadata, util
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.packaged]

ROOT = Path(__file__).resolve().parents[2]


def test_training_wheels_use_committed_toolbox_artifact_without_sibling_imports():
    """Case: IT-TRAIN-009."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    science = project["tool"]["biocall-studio"]["science"]
    assert project["project"]["version"] == "0.1.0a1"
    assert "bioacoustics-dl-toolbox[rf]==0.3.0" in project["project"]["dependencies"]
    assert "alp-ui==0.1.0a1" in project["project"]["dependencies"]

    published = (
        (
            "alp-ui",
            "alp_ui",
            "0.1.0a1",
            "41bac72971b96d352da752cc0ff140afe3ac312a",
            "20590366d06591837c2567df1191b472b9db494e5440ce3a3fadfbf1b8d53d6c",
        ),
        (
            "bioacoustics-dl-toolbox",
            "bioacoustics_dl_toolbox",
            "0.3.0",
            "7027bd84cc5a44a27bf201332af540f090c38365",
            "c0f7679cbf788c2900eff26b8db719941a513fc96b5f28348e2838c8df595b28",
        ),
    )
    for distribution, module, version, sha, wheel_sha in published:
        assert science[f"{distribution}-version"] == version
        assert science[f"{distribution}-revision"] == sha
        assert science[f"{distribution}-wheel-sha256"] == wheel_sha
        assert science[f"{distribution}-wheel-url"].endswith(
            f"/releases/download/v{version}/{module}-{version}-py3-none-any.whl"
        )
        assert metadata.version(distribution) == version
        spec = util.find_spec(module)
        assert spec is not None and spec.origin is not None
        assert "site-packages" in Path(spec.origin).resolve().parts
        assert not Path(spec.origin).resolve().is_relative_to(ROOT.parent / distribution)


def test_candidate_wheel_resources_and_metadata():
    """Case: IT-TRAIN-009."""
    # B3 workflow first builds the source wheel. No fallback to unverified build.
    wheels = sorted((ROOT / "dist").glob("biocall_studio-0.1.0a1-*.whl"))
    if not wheels:
        pytest.skip("Run the B3 source-wheel verifier after building dist/ to exercise archive")
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        names = archive.namelist()
        for required in (
            "biocall_studio/train/data/TRAINING_CONFIGURATION_FIELDS.json",
            "biocall_studio/resources/branding/icon-256.png",
            "biocall_studio/resources/branding/icon.ico",
            "biocall_studio/resources/branding/icon.icns",
            "biocall_studio/resources/legal/THIRD_PARTY_NOTICES.md",
        ):
            assert required in names
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        entry_name = next(name for name in names if name.endswith(".dist-info/entry_points.txt"))
        core = archive.read(metadata_name).decode()
        entries = archive.read(entry_name).decode()
        assert "Version: 0.1.0a1" in core
        assert "biocall-studio = biocall_studio.cli:main" in entries
