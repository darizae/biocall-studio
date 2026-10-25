"""Command-line configuration, kept independent of GUI imports."""

import argparse
import json
import sys
from importlib.metadata import version
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="alpaca Desktop Trainer")
    parser.add_argument("--version", action="version", version=version("alpaca-desktop"))
    parser.add_argument(
        "--settings-dir",
        type=Path,
        help="Isolate Application Settings in this directory instead of the Qt standard location.",
    )
    parser.add_argument("--worker", choices=("dataset-build",), help=argparse.SUPPRESS)
    parser.add_argument("--request", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.worker == "dataset-build":
        if args.request is None:
            parser.error("--request is required for the Dataset Build Worker")
        return _run_dataset_build_worker(args.request)

    from alpaca_desktop.gui.app import run

    return run(args.settings_dir)


def _run_dataset_build_worker(request_path: Path) -> int:
    from alpaca_desktop.persistence.collection_metadata import load_collection_metadata
    from alpaca_desktop.workflows.dataset_build import DatasetBuildRequest, build_dataset

    try:
        if request_path.stat().st_size > 1_000_000:
            raise ValueError("Dataset Build request exceeds 1 MiB.")
        with request_path.open(encoding="utf-8") as stream:
            request = DatasetBuildRequest.from_dict(json.load(stream))
        root = Path(request.collection_root)
        artifact = build_dataset(
            root,
            load_collection_metadata(root),
            request.config,
            dataset_id=request.dataset_id,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps({"dataset_id": artifact.dataset_id}))
    return 0
