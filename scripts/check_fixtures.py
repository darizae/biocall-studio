"""Verify committed synthetic WAV example and SHA register; never reads from HPC."""

from __future__ import annotations

import hashlib
import re
import sys
import wave
from pathlib import Path

from generate_example_collection import DURATION_SECONDS, EXAMPLES, RATE

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "data"
EXAMPLE = DATA / "example_collection"


def main() -> int:
    register = DATA / "SHA256SUMS"
    if not register.is_file():
        print("Missing SHA256SUMS", file=sys.stderr)
        return 1
    hashes: dict[str, str] = {}
    for line in register.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        m = re.fullmatch(
            r"([a-f0-9]{64})  (example_collection/(?:recordings|positives)/[^/]+\.wav)",
            line,
        )
        if not m or m.group(2) in hashes:
            print(f"Bad/duplicate SHA256SUMS entry: {line!r}", file=sys.stderr)
            return 1
        hashes[m.group(2)] = m.group(1)
    expected: set[str] = set()
    for stem, start_ms, end_ms, label, _, _ in EXAMPLES:
        src = EXAMPLE / "recordings" / f"{stem}.wav"
        pos = (
            EXAMPLE
            / "positives"
            / f"{stem}__start-{start_ms:05d}ms__end-{end_ms:05d}ms__{label}.wav"
        )
        source_info: tuple[int, int, int, int]
        with wave.open(str(src), "rb") as wav:
            source_info = (
                wav.getnchannels(),
                wav.getsampwidth(),
                wav.getframerate(),
                wav.getnframes(),
            )
            source_pcm = wav.readframes(wav.getnframes())
        with wave.open(str(pos), "rb") as wav:
            positive_info = (
                wav.getnchannels(),
                wav.getsampwidth(),
                wav.getframerate(),
                wav.getnframes(),
            )
            positive_pcm = wav.readframes(wav.getnframes())
        if source_info != (1, 2, RATE, DURATION_SECONDS * RATE):
            raise ValueError(f"Wrong real WAV source header: {src}: {source_info}")
        if positive_info != (1, 2, RATE, (end_ms - start_ms) * RATE // 1000):
            raise ValueError(f"Wrong real WAV positive header: {pos}: {positive_info}")
        if positive_pcm != source_pcm[start_ms * RATE // 1000 * 2 : end_ms * RATE // 1000 * 2]:
            raise ValueError(f"Positive must match exact source-time excerpt: {pos}")
        for path in (src, pos):
            rel = path.relative_to(DATA).as_posix()
            expected.add(rel)
            if (
                not path.is_file()
                or hashes.get(rel) != hashlib.sha256(path.read_bytes()).hexdigest()
            ):
                raise ValueError(f"Missing or incorrect SHA256: {rel}")
    actual = {p.relative_to(DATA).as_posix() for p in EXAMPLE.rglob("*.wav")}
    if expected != actual or expected != set(hashes):
        raise ValueError(
            f"Fixture inventory mismatch: expected={expected}, found={actual}, hashes={set(hashes)}"
        )
    print(
        f"Verified {len(expected)} real WAVs, SHA-256 hashes, "
        "headers and source-time excerpt identities."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
