"""Shared PyInstaller collection manifest for both native Studio bundles.

The native runner installs the *released wheels* and Studio's built wheel before
running either spec. We deliberately do not prepend sibling/src paths to pathex.
"""

from __future__ import annotations

import importlib.metadata as metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "packaging" / "shared" / "entrypoint.py"
VERSION = "0.1.0a1"
WORKER_ENTRYPOINTS = (
    "biocall_studio.train.workflows.worker_entry",
    "biocall_studio.train.workflows.dataset_build",
    "biocall_studio.train.workflows.cnn_training",
    "biocall_studio.train.workflows.rf_training",
    "biocall_studio.detect.workflows.detection",
    "biocall_studio.detect.workflows.refinement",
)
WORKER_MODES = (
    "train-dataset-build",
    "train-cnn-training",
    "train-rf-training",
    "detect-cnn",
    "detect-rf-refinement",
)


def collect_bundle() -> tuple[list[tuple[str, str]], list[str]]:
    """Return reviewed data/metadata and hidden imports for either platform.

    Keep the public alp-ui font/OFL resources, toolbox data, source package
    icons, JSON schema, Qt/torch runtime metadata and private worker modules.
    PyInstaller's stock Qt, torch and scientific hooks collect native binaries.
    """
    from PyInstaller.utils.hooks import (
        collect_data_files,
        collect_submodules,
        copy_metadata,
    )

    datas: list[tuple[str, str]] = []
    for package in ("biocall_studio", "alp_ui", "bioacoustics_dl_toolbox"):
        datas.extend(collect_data_files(package))
    for distribution in (
        "biocall-studio",
        "alp-ui",
        "bioacoustics-dl-toolbox",
        "PySide6-Addons",
        "PySide6-Essentials",
        "PySide6",
        "shiboken6",
        "torch",
        "numpy",
        "scipy",
        "scikit-learn",
        "librosa",
        "joblib",
    ):
        try:
            metadata.distribution(distribution)
        except metadata.PackageNotFoundError:
            continue
        datas.extend(copy_metadata(distribution))

    # Verbatim release-tagged upstream license/attribution files, not app license.
    for path, destination in (
        ("alp-ui/LICENSE", "legal/alp-ui"),
        ("toolbox/LICENSE", "legal/toolbox"),
        ("toolbox/NOTICE.md", "legal/toolbox"),
    ):
        datas.append((str(ROOT / "packaging" / "legal" / path), destination))

    hidden = set(WORKER_ENTRYPOINTS)
    for package in (
        "biocall_studio.train.workflows",
        "biocall_studio.detect.workflows",
        "biocall_studio.review.workflows",
        "bioacoustics_dl_toolbox",
        "alp_ui",
    ):
        hidden.update(collect_submodules(package, on_error="warn once"))
    # Include eager entrypoints even when importlib dynamic edges are invisible.
    hidden.update(
        (
            "biocall_studio.cli",
            "biocall_studio.studio.application.app",
            "biocall_studio.studio.application.coordinator",
        )
    )
    return sorted(set(datas)), sorted(hidden)
