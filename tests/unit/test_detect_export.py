from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from biocall_studio.detect.application.storage import estimate_export_artifacts
from biocall_studio.detect.domain.detection import DetectionSettings
from biocall_studio.detect.domain.exports import (
    FORMAT_POLICY,
    ExportConflictError,
    ExportMode,
    ExportSnapshot,
    SourceWaveFormat,
    create_export_snapshot,
    frame_seconds,
    render_raven_tsv,
    safe_snippet_relative_path,
)
from biocall_studio.detect.domain.result_views import (
    ResultSelection,
    freeze_result_selection,
)
from biocall_studio.detect.domain.results import (
    CandidateInterval,
    DetectionResult,
    RecordingOutcome,
    candidate_identity,
    recording_identity,
)
from biocall_studio.detect.domain.rf_refinement import (
    DerivedResult,
    RefinementDecision,
)
from biocall_studio.detect.workflows.exports import ensure_publish_target_available
from biocall_studio.shared.storage import pcm_wav_bytes


def _result(
    specs: tuple[tuple[str, str, int, int, tuple[tuple[int, int], ...]], ...],
) -> DetectionResult:
    inventory_id = "inv_" + "1" * 32
    outcomes = []
    for key, digit, rate, channels, intervals in specs:
        source_digest = digit * 64
        recording_ref = recording_identity(inventory_id, key, source_digest)
        candidates = tuple(
            CandidateInterval.create(
                candidate_id=candidate_identity(
                    recording_ref, start, end, f"science-{digit}-{index}"
                ),
                recording_ref=recording_ref,
                start_frame=start,
                end_frame=end,
                sample_rate_hz=rate,
                max_target_score=0.9 - index / 10,
                contributing_windows=index + 1,
            )
            for index, (start, end) in enumerate(intervals)
        )
        outcomes.append(
            RecordingOutcome.succeeded(
                recording_ref=recording_ref,
                recording_key=key,
                source_sha256=source_digest,
                sample_rate_hz=rate,
                frame_count=rate * 4,
                channels=channels,
                candidates=candidates,
            )
        )
    settings = DetectionSettings(0.5, 50, 125, 8)
    return DetectionResult.create(
        result_id="pub_" + "a" * 32,
        run_id="drun_" + "b" * 32,
        request_id="dreq_" + "c" * 32,
        collection_id="det_" + "d" * 32,
        binding_revision=1,
        inventory_id=inventory_id,
        inventory_digest="2" * 64,
        model_id="model-cnn",
        model_snapshot_id="mdl_" + "3" * 32,
        model_manifest_sha256="4" * 64,
        model_artifact_sha256="5" * 64,
        model_snapshot_digest="6" * 64,
        settings=settings,
        window_length_samples=4_000,
        hop_samples=settings.hop_samples(4_000),
        model_sample_rate_hz=16_000,
        backend_distribution="bioacoustics-dl-toolbox",
        backend_version="0.2.0",
        backend_revision="e478ca5",
        completed_at="2026-10-29T12:00:00.000Z",
        recordings=tuple(outcomes),
    )


def _selection(result: DetectionResult, *, reverse: bool = False):
    candidate_ids = tuple(
        candidate.candidate_id
        for recording in result.recordings
        for candidate in recording.candidates
    )
    if reverse:
        candidate_ids = tuple(reversed(candidate_ids))
    return freeze_result_selection(
        result,
        ResultSelection(
            schema_version=1,
            result_id=result.result_id,
            result_digest=result.result_digest,
            selection_revision=7,
            candidate_ids=candidate_ids,
            updated_at="2026-10-29T12:01:00.000Z",
        ),
    )


def _formats(result: DetectionResult, *widths: int) -> dict[str, SourceWaveFormat]:
    return {
        recording.recording_ref: SourceWaveFormat(
            recording.sample_rate_hz,
            recording.channels,
            widths[index] if widths else 2,
            "NONE",
        )
        for index, recording in enumerate(result.recordings)
    }


def _snapshot(
    result: DetectionResult,
    *,
    mode: ExportMode = ExportMode.BOTH,
    formats: dict[str, SourceWaveFormat] | None = None,
    destination: Path = Path("/tmp/exports"),
) -> ExportSnapshot:
    return create_export_snapshot(
        result=result,
        selection=_selection(result, reverse=True),
        mode=mode,
        destination_parent=destination,
        source_formats=formats or _formats(result),
        export_id="exp_" + "e" * 32,
        created_at="2026-10-29T12:02:00.000Z",
    )


def test_exact_frame_byte_and_raven_offset_arithmetic_has_no_accumulated_drift():
    """Case: UT-DET-021."""
    result = _result(
        (
            ("recordings/a.wav", "7", 44_100, 1, ((1, 4), (10, 15))),
            ("recordings/b.wav", "8", 44_100, 1, ((20, 27),)),
        )
    )
    snapshot = _snapshot(result)

    assert [candidate.source_start_frame for candidate in snapshot.candidates] == [1, 10, 20]
    assert [candidate.source_end_frame for candidate in snapshot.candidates] == [4, 15, 27]
    assert [candidate.output_frame_count for candidate in snapshot.candidates] == [3, 5, 7]
    assert [candidate.expected_pcm_bytes for candidate in snapshot.candidates] == [6, 10, 14]
    assert [candidate.concat_start_frame for candidate in snapshot.candidates] == [0, 3, 8]
    assert [candidate.concat_end_frame for candidate in snapshot.candidates] == [3, 8, 15]
    assert frame_seconds(3, 44_100) == "0.000068027211"

    tsv, rows = render_raven_tsv(snapshot)
    lines = tsv.decode("utf-8").splitlines()
    assert lines[0].split("\t")[:7] == [
        "Selection",
        "View",
        "Channel",
        "Begin Time (s)",
        "End Time (s)",
        "Low Freq (Hz)",
        "High Freq (Hz)",
    ]
    assert [row.begin_frame for row in rows] == [0, 3, 8]
    assert [row.end_frame for row in rows] == [3, 8, 15]
    assert rows[0].begin_seconds == "0"
    assert rows[-1].end_seconds == frame_seconds(15, 44_100)
    assert all(row.gap_frames == 0 for row in rows)
    assert len(lines) == 4
    with pytest.raises(ValueError, match="source frame mapping"):
        replace(
            snapshot.candidates[0],
            source_end_frame=snapshot.candidates[0].source_start_frame,
        )
    with pytest.raises(ValueError, match="source frame mapping"):
        replace(
            snapshot.candidates[0],
            source_end_frame=snapshot.candidates[0].frame_count + 1,
        )


def test_storage_plan_counts_snippets_concat_and_tsv_once() -> None:
    """Case: UT-SIZE-001."""
    result = _result((("recordings/a.wav", "7", 8_000, 1, ((1, 4), (10, 15))),))
    snapshot = _snapshot(result, mode=ExportMode.BOTH)
    plan = estimate_export_artifacts(snapshot)

    expected_audio = (
        pcm_wav_bytes(3, channels=1, sample_width_bytes=2)
        + pcm_wav_bytes(5, channels=1, sample_width_bytes=2)
        + pcm_wav_bytes(8, channels=1, sample_width_bytes=2)
    )
    tsv, _rows = render_raven_tsv(snapshot)
    assert plan.expected_final.kind == "exact"
    assert plan.expected_final.high_bytes is not None
    assert plan.expected_final.high_bytes > expected_audio + len(tsv)
    assert plan.peak_bytes == plan.expected_final.high_bytes


def test_snapshot_freezes_selection_digest_lineage_and_reproducible_order():
    """Case: UT-DET-022."""
    parent = _result(
        (
            ("recordings/a.wav", "7", 8_000, 1, ((80, 160),)),
            ("recordings/b.wav", "8", 8_000, 1, ((320, 400),)),
        )
    )
    decisions = {
        candidate.candidate_id: RefinementDecision.scored(0.8, threshold=0.6)
        for recording in parent.recordings
        for candidate in recording.candidates
    }
    derived = DerivedResult.create(
        result_id="pub_" + "e" * 32,
        run_id="drun_" + "f" * 32,
        request_id="dreq_" + "0" * 32,
        parent=parent,
        rf_model_id="model-rf",
        rf_model_snapshot_id="mdl_" + "8" * 32,
        rf_model_manifest_sha256="9" * 64,
        rf_model_artifact_sha256="a" * 64,
        rf_model_snapshot_digest="b" * 64,
        threshold=0.6,
        probability_class_order=(0, 1),
        target_probability_column=1,
        feature_family="robust-mfcc-v1",
        feature_names=("first",),
        feature_config=(("sample_rate_hz", 8_000),),
        preprocessing_order=("decode",),
        backend_distribution="scikit-learn",
        backend_version="1.7.2",
        backend_revision="e478ca5",
        completed_at="2026-10-29T12:01:30.000Z",
        decisions=decisions,
    )
    selected = tuple(
        candidate.candidate_id
        for recording in reversed(derived.recordings)
        for candidate in reversed(recording.candidates)
    )
    frozen = freeze_result_selection(
        derived,
        ResultSelection(
            1,
            derived.result_id,
            derived.result_digest,
            9,
            selected,
            "2026-10-29T12:01:40.000Z",
        ),
    )
    snapshot = create_export_snapshot(
        result=derived,
        selection=frozen,
        mode=ExportMode.SNIPPETS,
        destination_parent=Path("/exports"),
        source_formats=_formats(parent),
        export_id="exp_" + "1" * 32,
        created_at="2026-10-29T12:02:00.000Z",
    )

    assert snapshot.result_id == derived.result_id
    assert snapshot.result_digest == derived.result_digest
    assert snapshot.parent_result_id == parent.result_id
    assert snapshot.parent_result_digest == parent.result_digest
    assert snapshot.selection_revision == 9
    assert snapshot.selected_candidate_ids == tuple(
        candidate.candidate_id
        for recording in derived.recordings
        for candidate in recording.candidates
    )
    assert snapshot.format_policy == FORMAT_POLICY
    assert ExportSnapshot.from_dict(json.loads(json.dumps(snapshot.to_dict()))) == snapshot
    assert ExportSnapshot.from_dict(snapshot.to_dict()).snapshot_digest == snapshot.snapshot_digest
    with pytest.raises(FrozenInstanceError):
        snapshot.result_id = parent.result_id  # type: ignore[misc]


def test_windows_safe_names_mixed_format_policy_and_no_overwrite(tmp_path):
    """Case: UT-DET-023."""
    result = _result(
        (
            ("recordings/bird.wav", "7", 8_000, 1, ((80, 160),)),
            ("recordings/BIRD.WAV", "8", 16_000, 2, ((160, 320),)),
        )
    )
    formats = _formats(result, 2, 3)
    snippets = _snapshot(
        result,
        mode=ExportMode.SNIPPETS,
        formats=formats,
        destination=tmp_path,
    )
    names = [candidate.snippet_relative_path for candidate in snippets.candidates]
    assert len({name.casefold() for name in names}) == 2
    assert all(name.startswith("snippets/") and name.endswith(".wav") for name in names)
    assert all(not any(character in name for character in '<>:"|?*') for name in names)
    reserved = safe_snippet_relative_path("recordings/CON.wav", 1, 2, "cand_" + "f" * 32)
    assert Path(reserved).stem.split("__", 1)[0] == "CON_source"

    with pytest.raises(ValueError, match="same sample rate, channel count, and sample width"):
        _snapshot(result, mode=ExportMode.CONCAT, formats=formats, destination=tmp_path)
    with pytest.raises(ValueError, match="same sample rate, channel count, and sample width"):
        _snapshot(result, mode=ExportMode.BOTH, formats=formats, destination=tmp_path)

    final = tmp_path / snippets.directory_name
    final.mkdir()
    marker = final / "existing.txt"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(ExportConflictError, match="already exists"):
        ensure_publish_target_available(snippets)
    assert marker.read_text(encoding="utf-8") == "keep"
