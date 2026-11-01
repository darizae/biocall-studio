from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_training_wheels_use_committed_toolbox_artifact_without_sibling_imports(tmp_path):
    """Case: IT-TRAIN-009."""
    trainer = Path(__file__).resolve().parents[2]
    toolbox = trainer.parent / "bioacoustics-dl-toolbox"
    alp_ui = trainer.parent / "alp-ui"
    trainer_config = tomllib.loads((trainer / "pyproject.toml").read_text())
    recorded_revision = trainer_config["tool"]["biocall-studio"]["science"][
        "bioacoustics-dl-toolbox-revision"
    ]
    actual_revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=toolbox,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert actual_revision == recorded_revision
    toolbox_status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=toolbox,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert toolbox_status == ""
    assert "bioacoustics-dl-toolbox[rf]==0.2.0" in trainer_config["project"]["dependencies"]
    assert "alp-ui==0.1.0a0" in trainer_config["project"]["dependencies"]
    assert (
        subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=alp_ui,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == trainer_config["tool"]["biocall-studio"]["science"]["alp-ui-revision"]
    )

    wheels = tmp_path / "wheels"
    wheels.mkdir()
    for source in (toolbox, trainer):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--wheel-dir",
                str(wheels),
                str(source),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    built = sorted(wheels.glob("*.whl"))
    assert {path.name.split("-", 1)[0] for path in built} == {
        "biocall_studio",
        "bioacoustics_dl_toolbox",
    }

    target = tmp_path / "installed"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(target),
            *(str(path) for path in built),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(target)
    check = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json; "
                "import biocall_studio, bioacoustics_dl_toolbox; "
                "from biocall_studio.train.workflows import rf_training; "
                "from bioacoustics_dl_toolbox.rf import compute_rf_features; "
                "print(json.dumps({'trainer': biocall_studio.__file__, "
                "'toolbox': bioacoustics_dl_toolbox.__file__, "
                "'extractor': compute_rf_features.__module__, "
                "'workflow': rf_training.__file__}))"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(check.stdout)
    assert Path(payload["trainer"]).is_relative_to(target)
    assert Path(payload["toolbox"]).is_relative_to(target)
    assert Path(payload["workflow"]).is_relative_to(target)
    assert payload["extractor"] == "bioacoustics_dl_toolbox.rf.features"
