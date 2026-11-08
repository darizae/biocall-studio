"""Bounded positive Dataset Worker smoke against the genuinely installed Windows executable.

Only test fixtures and request construction use the Python test harness. The Dataset
is produced by the installed PyInstaller Worker, not by source Python. This is not
Train/Detect/Review end-to-end qualification or an interactive GUI test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import msvcrt
import os
import struct
import subprocess
import tempfile
import wave
from contextlib import contextmanager
from pathlib import Path

from biocall_studio.train.application.collection_scan import scan_collection
from biocall_studio.train.domain.dataset import BuildConfig
from biocall_studio.train.persistence.collection_metadata import publish_collection_metadata
from biocall_studio.train.persistence.datasets import load_dataset
from biocall_studio.train.workflows.dataset_build import DatasetBuildRequest


def wav(path: Path, frames: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16_000)
        payload = b"".join(struct.pack("<h", (index * 97) % 20_000 - 10_000) for index in range(frames))
        stream.writeframes(payload)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def owner_lease(path: Path):
    with path.open("w+b") as stream:
        stream.write(b"1")
        stream.flush()
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    path.unlink()


def check(worker: Path, external_root: Path) -> dict[str, object]:
    worker = worker.resolve(strict=True)
    external_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="biocall-positive-", dir=external_root) as temporary:
        isolated = Path(temporary)
        collection = isolated / "synthetic-collection"
        for index in range(2):
            stem = f"REC_{chr(65 + index)}"
            wav(collection / "recordings" / f"{stem}.wav", frames=64_000)
            wav(
                collection / "positives" / f"{stem}__start-00500ms__end-01000ms__call{index + 1}.wav",
                frames=8_000,
            )
        inputs = sorted(collection.glob("*/*.wav"))
        original = {str(path): sha256(path) for path in inputs}
        scan = scan_collection(collection)
        if not scan.valid:
            raise AssertionError(f"Synthetic Collection validation failed: {scan.issues}")
        published = publish_collection_metadata(collection, scan)
        config = BuildConfig(
            selected_recording_ids=tuple(record.id for record in published.records),
            negative_mode="ratio", negative_ratio=1.0, negative_count=0,
            allocation="proportional", train_percent=80, balance_classes=True,
            seed=42, margin_ms=250,
        )
        request = DatasetBuildRequest(
            run_id="run-native-smoke", request_id="request-native-smoke",
            collection_root=str(collection), collection_id=published.collection_id,
            config=config, dataset_id="dataset-native-smoke",
        )
        request_path = isolated / "request.json"
        request_path.write_text(json.dumps(request.to_dict()), encoding="utf-8")
        lease = isolated / "supervisor.lease"
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        env["PYTHONNOUSERSITE"] = "1"
        with owner_lease(lease):
            completed = subprocess.run(
                [str(worker), "--worker", "train-dataset-build", "--request",
                 str(request_path), "--owner-lease", str(lease)],
                cwd=isolated, env=env, capture_output=True, text=True, timeout=180,
            )
        events = [json.loads(line) for line in completed.stdout.splitlines() if line.startswith("{")]
        if completed.returncode != 0 or not any(event.get("event") == "completed" for event in events):
            raise AssertionError(
                f"Installed Dataset Worker failed: exit={completed.returncode}, "
                f"stdout={completed.stdout[-2000:]}, stderr={completed.stderr[-2000:]}"
            )
        dataset = load_dataset(collection, "dataset-native-smoke")
        if dataset.manifest["counts"]["total"] != 4 or len(dataset.snippets) != 4:
            raise AssertionError("Installed Worker Dataset count/reopen mismatch")
        for split in ("train", "val"):
            if not (dataset.root / "splits" / f"{split}.csv").is_file():
                raise AssertionError(f"Missing Worker-produced {split} CSV")
        if {str(path): sha256(path) for path in inputs} != original:
            raise AssertionError("Installed Worker mutated research input WAV files")
        return {
            "installed_worker": str(worker),
            "successful_mode": "train-dataset-build",
            "exit_code": completed.returncode,
            "dataset_reopened": True,
            "worker_created_snippets": len(dataset.snippets),
            "worker_created_csv_splits": ["train", "val"],
            "source_wav_hashes_unchanged": True,
            "boundaries": "Does not qualify Detect, Review exports, visible GUI, or safe quit",
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", required=True, type=Path)
    parser.add_argument("--external-root", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    result = check(args.worker, args.external_root)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
