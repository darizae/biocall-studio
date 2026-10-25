from __future__ import annotations

import json
import os
import subprocess
import sys
import wave
from pathlib import Path

import pytest

from alpaca_desktop.workflows.audio import (
    AudioExtractionCancelled,
    extract_dataset_audio,
)

pytestmark = pytest.mark.integration


def _payload(frame_count: int, channels: int, sample_width: int) -> bytes:
    return bytes((index * 29 + 17) % 256 for index in range(frame_count * channels * sample_width))


def _write_wav(
    path: Path,
    *,
    frame_count: int,
    sample_rate: int,
    channels: int,
    sample_width: int,
) -> bytes:
    payload = _payload(frame_count, channels, sample_width)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(sample_width)
        stream.setframerate(sample_rate)
        stream.writeframes(payload)
    return payload


@pytest.mark.parametrize(
    ("label", "sample_rate", "channels", "sample_width", "start_ms", "end_ms"),
    [
        ("target", 44_100, 1, 1, 5, 6),
        ("noise", 44_100, 2, 2, 0, 10),
        ("target", 48_000, 1, 3, 9, 10),
        ("noise", 48_000, 2, 4, 0, 2),
    ],
)
def test_real_toolbox_slices_match_pre_migration_pcm_baseline(
    tmp_path, label, sample_rate, channels, sample_width, start_ms, end_ms
):
    """Case: IT-AUDIO-001."""
    source = tmp_path / "source.wav"
    destination = tmp_path / "snippets" / label / f"{label}.wav"
    source_payload = _write_wav(
        source,
        frame_count=sample_rate // 100,
        sample_rate=sample_rate,
        channels=channels,
        sample_width=sample_width,
    )
    source_bytes = source.read_bytes()

    transform = extract_dataset_audio(
        source,
        destination,
        start_ms=start_ms,
        end_ms=end_ms,
    )

    start_frame = (start_ms * sample_rate + 500) // 1_000
    end_frame = (end_ms * sample_rate + 500) // 1_000
    bytes_per_frame = channels * sample_width
    with wave.open(str(destination), "rb") as stream:
        assert (
            stream.getframerate(),
            stream.getnchannels(),
            stream.getsampwidth(),
            stream.getnframes(),
        ) == (sample_rate, channels, sample_width, end_frame - start_frame)
        assert (
            stream.readframes(stream.getnframes())
            == source_payload[start_frame * bytes_per_frame : end_frame * bytes_per_frame]
        )
    assert transform.to_dict()["policy"] == "pcm-preserve-nearest-frame-v1"
    assert source.read_bytes() == source_bytes


def test_toolbox_failures_cancel_and_existing_output_leave_no_partial_snippet(
    tmp_path, monkeypatch
):
    """Case: IT-AUDIO-002."""
    source = tmp_path / "source.wav"
    _write_wav(
        source,
        frame_count=96_000,
        sample_rate=48_000,
        channels=2,
        sample_width=2,
    )
    source_bytes = source.read_bytes()

    existing = tmp_path / "existing.wav"
    existing.write_bytes(b"published")
    with pytest.raises(FileExistsError):
        extract_dataset_audio(source, existing, start_ms=0, end_ms=1)
    assert existing.read_bytes() == b"published"

    invalid = tmp_path / "invalid.wav"
    with pytest.raises(ValueError, match="interval"):
        extract_dataset_audio(source, invalid, start_ms=1, end_ms=1)
    assert not invalid.exists()

    unsupported_source = tmp_path / "unsupported.wav"
    unsupported = bytearray(source_bytes)
    unsupported[20:22] = (3).to_bytes(2, "little")
    unsupported_source.write_bytes(unsupported)
    unsupported_output = tmp_path / "unsupported-output.wav"
    with pytest.raises(ValueError, match="PCM WAV"):
        extract_dataset_audio(unsupported_source, unsupported_output, start_ms=0, end_ms=1)
    assert not unsupported_output.exists()

    truncated_source = tmp_path / "truncated.wav"
    truncated_source.write_bytes(source_bytes[:-1_000])
    truncated_output = tmp_path / "truncated-output.wav"
    with pytest.raises(ValueError, match="ended"):
        extract_dataset_audio(truncated_source, truncated_output, start_ms=0, end_ms=2_000)
    assert not truncated_output.exists()

    checks = 0

    def cancelled() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    cancelled_output = tmp_path / "cancelled.wav"
    with pytest.raises(AudioExtractionCancelled, match="cancelled"):
        extract_dataset_audio(
            source,
            cancelled_output,
            start_ms=0,
            end_ms=2_000,
            cancelled=cancelled,
        )
    assert not cancelled_output.exists()

    failed_output = tmp_path / "failed.wav"
    original_write = wave.Wave_write.writeframesraw
    raised = False

    def fail_after_write(stream, payload):
        nonlocal raised
        result = original_write(stream, payload)
        if payload and not raised:
            raised = True
            raise OSError("injected disk failure")
        return result

    monkeypatch.setattr(wave.Wave_write, "writeframesraw", fail_after_write)
    with pytest.raises(OSError, match="injected disk failure"):
        extract_dataset_audio(source, failed_output, start_ms=0, end_ms=2_000)
    assert not failed_output.exists()
    assert source.read_bytes() == source_bytes


def test_fresh_installed_process_resolves_committed_separate_toolbox(tmp_path):
    """Case: IT-AUDIO-004."""
    repository = Path(__file__).resolve().parents[2]
    toolbox = repository.parent / "bioacoustics-dl-toolbox"
    script = """
import importlib.util
import json
import bioacoustics_dl_toolbox
from alpaca_desktop.workflows import audio
print(json.dumps({
    "package_file": bioacoustics_dl_toolbox.__file__,
    "api_module": audio.extract_pcm_wav_segment.__module__,
    "distribution": audio.TOOLBOX_DISTRIBUTION,
    "version": audio.TOOLBOX_VERSION,
    "revision": audio.TOOLBOX_SOURCE_REVISION,
    "legacy_computation": importlib.util.find_spec("alpaca_desktop.computation") is not None,
}))
"""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    resolved = json.loads(completed.stdout)

    assert Path(resolved["package_file"]).resolve().is_relative_to(toolbox.resolve())
    assert "alpaca-pipelines" not in resolved["package_file"]
    assert set(resolved) == {
        "package_file",
        "api_module",
        "distribution",
        "version",
        "revision",
        "legacy_computation",
    }
    assert resolved["api_module"] == "bioacoustics_dl_toolbox.audio.io"
    assert resolved["distribution"] == "bioacoustics-dl-toolbox"
    assert resolved["version"] == "0.1.1"
    assert resolved["revision"] == "0fce0d4fa3d0931c5731e8b868f705e0a2120835"
    assert resolved["legacy_computation"] is False
