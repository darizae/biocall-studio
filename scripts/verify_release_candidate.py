"""Validate source archives, public wheel origins and B3 candidate provenance.

Run only with actual released wheels in the wheelhouse; no downloading or
reconstruction of upstream assets occurs here. This is not a native installer test.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import importlib.util
import json
import tarfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = (
    "biocall_studio/train/data/TRAINING_CONFIGURATION_FIELDS.json",
    "biocall_studio/resources/branding/icon-256.png",
    "biocall_studio/resources/branding/icon.icns",
    "biocall_studio/resources/branding/icon.ico",
    "biocall_studio/resources/legal/THIRD_PARTY_NOTICES.md",
)
UPSTREAM = (
    ("alp-ui", "alp_ui", "0.1.0a1", "41bac72971b96d352da752cc0ff140afe3ac312a",
     "20590366d06591837c2567df1191b472b9db494e5440ce3a3fadfbf1b8d53d6c"),
    ("bioacoustics-dl-toolbox", "bioacoustics_dl_toolbox", "0.3.0",
     "7027bd84cc5a44a27bf201332af540f090c38365",
     "c0f7679cbf788c2900eff26b8db719941a513fc96b5f28348e2838c8df595b28"),
)
MODES = (
    "train-dataset-build", "train-cnn-training", "train-rf-training",
    "detect-cnn", "detect-rf-refinement",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(dist: Path, wheelhouse: Path) -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]
    science = config["tool"]["biocall-studio"]["science"]
    assert project["version"] == "0.1.0a1"
    assert "license" not in project, "App-level license must not be invented"
    assert "bioacoustics-dl-toolbox[rf]==0.3.0" in project["dependencies"]
    assert "alp-ui==0.1.0a1" in project["dependencies"]
    for name, module, version, revision, digest in UPSTREAM:
        filename = f"{module}-{version}-py3-none-any.whl"
        assert science[f"{name}-version"] == version
        assert science[f"{name}-revision"] == revision
        assert science[f"{name}-wheel-sha256"] == digest
        assert science[f"{name}-wheel-url"] == (
            f"https://github.com/darizae/{name}/releases/download/v{version}/{filename}"
        )
        artifact = wheelhouse / filename
        assert artifact.is_file(), f"Missing published asset: {artifact}"
        assert sha256(artifact) == digest, f"Published wheel SHA-256 mismatch: {name}"
        with zipfile.ZipFile(artifact) as zipped:
            assert any(x.endswith(".dist-info/METADATA") for x in zipped.namelist())
        assert metadata.version(name) == version
        module_spec = importlib.util.find_spec(module)
        assert module_spec is not None and module_spec.origin is not None
        origin = Path(module_spec.origin).resolve()
        assert "site-packages" in origin.parts, f"Not a non-editable wheel import: {origin}"
        assert not origin.is_relative_to(ROOT.parent), f"Sibling import: {origin}"
        print(f"UPSTREAM {name}=={version} commit={revision} wheel-sha256={digest} origin={origin}")

    from biocall_studio.cli import WORKER_MODES

    assert tuple(WORKER_MODES) == MODES
    assert (ROOT / "src/biocall_studio/__main__.py").exists()
    assert (ROOT / "src/biocall_studio/train/workflows/worker_entry.py").exists()
    assert (ROOT / "src/biocall_studio/detect/workflows/detection.py").exists()
    assert (ROOT / "src/biocall_studio/detect/workflows/refinement.py").exists()

    wheels = sorted(dist.glob("biocall_studio-0.1.0a1-*.whl"))
    sdists = sorted(dist.glob("biocall_studio-0.1.0a1.tar.gz"))
    assert len(wheels) == 1 and len(sdists) == 1, "Exactly one Studio wheel and sdist required"
    with zipfile.ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())
        for resource in RESOURCES:
            assert resource in names, f"Wheel missing {resource}"
        fields = json.loads(archive.read(RESOURCES[0]))
        assert isinstance(fields, (dict, list))
        for resource in RESOURCES:
            assert archive.getinfo(resource).file_size > 0
        core = next(x for x in names if x.endswith(".dist-info/METADATA"))
        entry = next(x for x in names if x.endswith(".dist-info/entry_points.txt"))
        wheel_metadata = archive.read(core).decode()
        assert "Name: biocall-studio" in wheel_metadata
        assert "Version: 0.1.0a1" in wheel_metadata
        assert "Requires-Dist: alp-ui==0.1.0a1" in wheel_metadata
        assert "bioacoustics-dl-toolbox[rf]==0.3.0" in wheel_metadata
        assert "License: MIT" not in wheel_metadata
        assert "License: GPL" not in wheel_metadata
        assert "biocall-studio = biocall_studio.cli:main" in archive.read(entry).decode()
        for mode in MODES:
            assert mode in archive.read("biocall_studio/cli.py").decode()
    with tarfile.open(sdists[0], "r:gz") as archive:
        members = [x.name for x in archive.getmembers() if x.isfile()]
        for item in ("pyproject.toml", "README.md",
                     "docs/legal/THIRD_PARTY_NOTICES.md",
                     "docs/science/TRAINING_CONFIGURATION_FIELDS.json",
                     "assets/branding/icons/icon.icns", "assets/branding/icons/icon.ico"):
            assert any(x.endswith("/" + item) for x in members), f"Sdist missing {item}"
    for path in (
        "assets/branding/icons/icon.icns",
        "assets/branding/icons/icon.ico",
        "src/biocall_studio/resources/branding/icon-256.png",
    ):
        icon = ROOT / path
        assert icon.is_file() and icon.stat().st_size > 1024
        print(f"ICON SHA256 {path} {sha256(icon)}")
    for package in ("PySide6", "PySide6-Addons", "PySide6-Essentials",
                    "numpy", "scipy", "torch", "librosa", "scikit-learn"):
        try:
            print(f"DEPENDENCY {package}=={metadata.version(package)}")
        except metadata.PackageNotFoundError:
            print(f"DEPENDENCY {package}: not installed")
    print(f"STUDIO SOURCE-WHEEL {wheels[0].name} SHA256={sha256(wheels[0])}")
    print(f"STUDIO SDIST {sdists[0].name} SHA256={sha256(sdists[0])}")
    print("Provisional B3 source archives verified; no frozen native installer or tag.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--wheelhouse", type=Path, default=Path(".release-wheels"))
    args = parser.parse_args()
    verify(args.dist, args.wheelhouse)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
