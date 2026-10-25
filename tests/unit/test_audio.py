from __future__ import annotations

import hashlib
import json

import pytest
from bioacoustics_dl_toolbox.audio import PcmExtractionCancelled, PcmSegmentFacts

from alpaca_desktop.persistence.integrity import sha256_file
from alpaca_desktop.workflows import audio as audio_adapter


def test_audio_transform_maps_nearest_frames_and_stable_manifest_metadata():
    """Case: UT-AUDIO-001."""
    facts = PcmSegmentFacts(
        start_frame=221,
        end_frame=265,
        sample_rate_hz=44_100,
        channels=2,
        sample_width_bytes=3,
        frame_count=44,
    )

    transform = audio_adapter.DatasetAudioTransform.from_facts(facts, start_ms=5, end_ms=6)

    assert transform.to_dict() == {
        "policy": "pcm-preserve-nearest-frame-v1",
        "start_frame": 221,
        "end_frame": 265,
        "sample_rate_hz": 44_100,
        "channels": 2,
        "sample_width_bytes": 3,
        "frame_count": 44,
    }


@pytest.mark.parametrize(
    "facts",
    [
        PcmSegmentFacts(-1, 48, 48_000, 1, 2, 49),
        PcmSegmentFacts(0, 47, 48_000, 1, 2, 48),
        PcmSegmentFacts(0, 48, 0, 1, 2, 48),
        PcmSegmentFacts(0, 48, 48_000, 0, 2, 48),
        PcmSegmentFacts(0, 48, 48_000, 1, 0, 48),
    ],
)
def test_audio_transform_rejects_mismatched_or_invalid_toolbox_facts(facts):
    """Case: UT-AUDIO-001."""
    with pytest.raises(ValueError, match="facts"):
        audio_adapter.DatasetAudioTransform.from_facts(facts, start_ms=0, end_ms=1)


def test_integrity_hash_is_streamed_and_cancellation_is_application_owned(tmp_path, monkeypatch):
    """Case: UT-AUDIO-002."""
    payload = bytes(range(256)) * 600
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(payload)
    assert sha256_file(artifact) == hashlib.sha256(payload).hexdigest()

    checks = 0

    def cancelled() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    with pytest.raises(InterruptedError, match="Dataset Build cancelled"):
        sha256_file(artifact, cancelled=cancelled)
    assert checks == 2

    def library_cancel(*_args, **_kwargs):
        raise PcmExtractionCancelled("library cancellation")

    monkeypatch.setattr(audio_adapter, "extract_pcm_wav_segment", library_cancel)
    with pytest.raises(audio_adapter.AudioExtractionCancelled) as caught:
        audio_adapter.extract_dataset_audio(
            tmp_path / "source.wav",
            tmp_path / "snippet.wav",
            start_ms=0,
            end_ms=1,
        )
    assert isinstance(caught.value.__cause__, PcmExtractionCancelled)

    provenance = audio_adapter.audio_extraction_provenance()
    assert provenance == {
        "distribution": "bioacoustics-dl-toolbox",
        "version": "0.1.1",
        "revision": "0fce0d4fa3d0931c5731e8b868f705e0a2120835",
        "api": "bioacoustics_dl_toolbox.audio.extract_pcm_wav_segment",
    }
    assert "/Users/" not in json.dumps(provenance)
