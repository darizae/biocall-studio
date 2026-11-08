"""Reject unverified wheels, editable source inputs and wrong build revisions.

Run on a native runner *before* PyInstaller. The --frozen option is required for
final native lanes, and intentionally unavailable to the pre-merge A checks.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import importlib.util
import json
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_MODES = (
    "train-dataset-build", "train-cnn-training", "train-rf-training",
    "detect-cnn", "detect-rf-refinement",
)
UPSTREAM = {
    "alp-ui": ("alp_ui", "0.1.0a1"),
    "bioacoustics-dl-toolbox": ("bioacoustics_dl_toolbox", "0.3.0"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check(wheelhouse: Path, *, frozen: bool = False) -> dict[str, object]:
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("Native candidate requires Python 3.12.")
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]
    science = config["tool"]["biocall-studio"]["science"]
    version = project["version"]
    if version != "0.1.0a1" or "license" in project:
        raise RuntimeError("Unexpected Studio version or invented application license.")
    if metadata.version("biocall-studio") != version:
        raise RuntimeError("Installed Studio wheel does not match pyproject.toml.")
    for name, (module, release) in UPSTREAM.items():
        path = wheelhouse / f"{module}-{release}-py3-none-any.whl"
        expected = science[f"{name}-wheel-sha256"]
        url = science[f"{name}-wheel-url"]
        if len(expected) != 64 or sha256(path) != expected:
            raise RuntimeError(f"Published upstream wheel SHA-256 mismatch: {name}")
        if url != (
            f"https://github.com/darizae/{name}/releases/download/v{release}/{path.name}"
        ):
            raise RuntimeError(f"Unexpected published release URL for {name}")
        if science[f"{name}-version"] != release or len(science[f"{name}-revision"]) != 40:
            raise RuntimeError(f"Upstream version/revision mismatch for {name}")
        if metadata.version(name) != release:
            raise RuntimeError(f"Incorrect installed wheel version for {name}")
    for name in ("biocall_studio", "alp_ui", "bioacoustics_dl_toolbox"):
        spec = importlib.util.find_spec(name)
        if spec is None or spec.origin is None:
            raise RuntimeError(f"Missing import {name}")
        origin = Path(spec.origin).resolve()
        if "site-packages" not in origin.parts or origin.is_relative_to(ROOT):
            raise RuntimeError(f"Editable or checkout import is forbidden: {origin}")
    from biocall_studio.cli import WORKER_MODES

    if tuple(WORKER_MODES) != EXPECTED_MODES:
        raise RuntimeError("Private Worker mode coverage has drifted.")
    icons = {}
    for name in ("icon.icns", "icon.ico"):
        path = ROOT / "assets" / "branding" / "icons" / name
        signature = b"icns" if name.endswith(".icns") else b"\x00\x00\x01\x00"
        if path.stat().st_size < 1024 or path.read_bytes()[:4] != signature:
            raise RuntimeError(f"Invalid native brand asset: {path}")
        icons[name] = sha256(path)
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if frozen:
        import os

        if os.environ.get("STUDIO_RELEASE_SHA") != revision:
            raise RuntimeError("STUDIO_RELEASE_SHA must equal the frozen checkout HEAD.")
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ).strip()
        if dirty:
            raise RuntimeError("Frozen native build checkout is dirty.")
    return {
        "studio_version": version,
        "source_commit": revision,
        "upstream": {
            name: {
                "tag_target_commit": science[f"{name}-revision"],
                "wheel_sha256": science[f"{name}-wheel-sha256"],
            }
            for name in UPSTREAM
        },
        "icons_sha256": icons,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheelhouse", type=Path, default=Path(".release-wheels"))
    parser.add_argument("--frozen", action="store_true")
    args = parser.parse_args()
    print(json.dumps(check(args.wheelhouse, frozen=args.frozen), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
