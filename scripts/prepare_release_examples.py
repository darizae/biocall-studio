"""Prepare a local Train Collection from the verified real-hum Review cohort.

The source WAV and provenance document are never modified. Existing generated files are
accepted only when their bytes already match; use ``--replace`` to rebuild the disposable
output under ``work/`` deliberately.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import wave
from pathlib import Path

from biocall_studio.train.application.collection_scan import scan_collection
from biocall_studio.train.persistence.collection_metadata import publish_collection_metadata

DEFAULT_EXAMPLE_ROOT = Path("work/manual-review-real-hums")
DEFAULT_OUTPUT = Path("work/release-evidence/Verified Alpaca Hums")
SOURCE_STEM = "Verified_Alpaca_Hums"
RECORDING_COUNT = 3
POSITIVES_PER_RECORDING = 8


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _replace_output(root: Path) -> None:
    resolved = root.resolve(strict=False)
    work_root = Path("work").resolve(strict=False)
    if not resolved.is_relative_to(work_root) or resolved == work_root:
        raise ValueError("Release example replacement is restricted to a named folder under work/.")
    if resolved.exists():
        shutil.rmtree(resolved)


def _write_collection(example_root: Path, output: Path) -> tuple[str, int, int]:
    provenance_path = example_root / "REAL_HUM_PROVENANCE.json"
    source = example_root / "source" / "recordings" / "verified-real-hums.wav"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    expected_sha256 = provenance["output_wav_sha256"]
    if _sha256(source) != expected_sha256:
        raise ValueError("The verified real-hum source WAV no longer matches its provenance.")

    recordings = output / "recordings"
    positives = output / "positives"
    recordings.mkdir(parents=True, exist_ok=True)
    positives.mkdir(parents=True, exist_ok=True)
    with wave.open(str(source), "rb") as reader:
        parameters = reader.getparams()
        if parameters.framerate <= 0 or parameters.nchannels not in {1, 2}:
            raise ValueError("The verified real-hum WAV format is unsupported by Train.")
        written = 0
        rows = provenance["rows"][: RECORDING_COUNT * POSITIVES_PER_RECORDING]
        for recording_index in range(RECORDING_COUNT):
            group = rows[
                recording_index
                * POSITIVES_PER_RECORDING : (recording_index + 1)
                * POSITIVES_PER_RECORDING
            ]
            group_start = max(
                0, int(group[0]["output_start_frame"]) - parameters.framerate
            )
            group_end = min(
                parameters.nframes,
                int(group[-1]["output_end_frame"]) + parameters.framerate,
            )
            stem = f"{SOURCE_STEM}_{recording_index + 1:02d}"
            reader.setpos(group_start)
            source_frames = reader.readframes(group_end - group_start)
            with wave.open(str(recordings / f"{stem}.wav"), "wb") as target:
                target.setnchannels(parameters.nchannels)
                target.setsampwidth(parameters.sampwidth)
                target.setframerate(parameters.framerate)
                target.writeframes(source_frames)

            for row in group:
                start_frame = int(row["output_start_frame"]) - group_start
                end_frame = int(row["output_end_frame"]) - group_start
                start_scaled = start_frame * 1000
                end_scaled = end_frame * 1000
                if start_scaled % parameters.framerate or end_scaled % parameters.framerate:
                    raise ValueError(
                        "A real-hum selection does not have integer-millisecond bounds."
                    )
                start_ms = start_scaled // parameters.framerate
                end_ms = end_scaled // parameters.framerate
                reader.setpos(int(row["output_start_frame"]))
                frames = reader.readframes(
                    int(row["output_end_frame"]) - int(row["output_start_frame"])
                )
                name = (
                    f"{stem}__start-{start_ms:06d}ms__end-{end_ms:06d}ms__"
                    f"alpaca_hum_{written + 1:02d}.wav"
                )
                with wave.open(str(positives / name), "wb") as target:
                    target.setnchannels(parameters.nchannels)
                    target.setsampwidth(parameters.sampwidth)
                    target.setframerate(parameters.framerate)
                    target.writeframes(frames)
                written += 1
    return expected_sha256, RECORDING_COUNT, written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--example-root", type=Path, default=DEFAULT_EXAMPLE_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    output = args.output.resolve(strict=False)
    if output.exists():
        if not args.replace:
            parser.error(f"{output} already exists; pass --replace to rebuild it")
        _replace_output(output)
    source_sha256, recording_count, positive_count = _write_collection(
        args.example_root.resolve(strict=True), output
    )
    scan = scan_collection(output)
    if not scan.valid:
        detail = "; ".join(f"{issue.relative_path}: {issue.message}" for issue in scan.issues)
        raise ValueError(f"Prepared release Collection did not validate: {detail}")
    published = publish_collection_metadata(output, scan)
    print(
        f"Prepared {published.root_name}: {recording_count} real-audio recordings, "
        f"{positive_count} verified real-hum examples, source SHA-256 {source_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
