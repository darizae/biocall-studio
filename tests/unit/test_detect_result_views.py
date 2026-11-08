from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace

import pytest

from biocall_studio.detect.domain.detection import DetectionSettings
from biocall_studio.detect.domain.result_views import (
    ResultContentState,
    ResultSourceState,
    SelectionReconciliation,
    freeze_result_selection,
    project_result,
)
from biocall_studio.detect.domain.results import (
    CandidateInterval,
    DetectionResult,
    FileOutcomeStatus,
    RecordingOutcome,
    candidate_identity,
    recording_identity,
)
from biocall_studio.detect.persistence.selection import ResultSelectionStore


def _outcome(
    *,
    inventory_id: str,
    key: str,
    source_digit: str,
    candidate_frames: tuple[tuple[int, int], ...] = (),
    failed: bool = False,
) -> RecordingOutcome:
    digest = source_digit * 64
    recording_id = recording_identity(inventory_id, key, digest)
    if failed:
        return RecordingOutcome.failed(
            recording_ref=recording_id,
            recording_key=key,
            source_sha256=digest,
            sample_rate_hz=16_000,
            frame_count=32_000,
            channels=1,
            error_code="audio_decode_failed",
        )
    candidates = tuple(
        CandidateInterval.create(
            candidate_id=candidate_identity(recording_id, start, end, f"scientific-{index}"),
            recording_ref=recording_id,
            start_frame=start,
            end_frame=end,
            sample_rate_hz=16_000,
            max_target_score=0.91 - index / 10,
            contributing_windows=index + 1,
        )
        for index, (start, end) in enumerate(candidate_frames)
    )
    return RecordingOutcome.succeeded(
        recording_ref=recording_id,
        recording_key=key,
        source_sha256=digest,
        sample_rate_hz=16_000,
        frame_count=32_000,
        channels=1,
        candidates=candidates,
    )


def _result(
    token: str,
    *,
    recordings: tuple[RecordingOutcome, ...],
    result_id: str | None = None,
) -> DetectionResult:
    settings = DetectionSettings(0.5, 50, 125, 8)
    return DetectionResult.create(
        result_id=result_id or "pub_" + token * 32,
        run_id="drun_" + token * 32,
        request_id="dreq_" + token * 32,
        collection_id="det_" + "d" * 32,
        binding_revision=1,
        inventory_id="inv_" + "1" * 32,
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
        completed_at=f"2026-10-29T12:00:{int(token, 16):02d}.000Z",
        recordings=recordings,
    )


def test_result_projection_selection_digest_mapping_and_no_cross_result_bleed(tmp_path):
    """Case: UT-DET-016."""
    inventory_id = "inv_" + "1" * 32
    first = _result(
        "a",
        recordings=(
            _outcome(
                inventory_id=inventory_id,
                key="recordings/dawn.wav",
                source_digit="7",
                candidate_frames=((160, 320), (640, 960)),
            ),
        ),
    )
    second = _result(
        "b",
        recordings=(
            _outcome(
                inventory_id=inventory_id,
                key="recordings/night.wav",
                source_digit="8",
                candidate_frames=((1_600, 1_920),),
            ),
        ),
    )
    first_projection = project_result(first, source_state=ResultSourceState.AVAILABLE)
    first_ids = tuple(
        candidate.candidate_id
        for recording in first_projection.recordings
        for candidate in recording.candidates
    )
    second_projection = project_result(second, source_state=ResultSourceState.AVAILABLE)
    second_ids = tuple(
        candidate.candidate_id
        for recording in second_projection.recordings
        for candidate in recording.candidates
    )
    assert first_projection.result_id == first.result_id
    assert first_projection.result_digest == first.result_digest
    assert first_projection.recordings[0].recording_id == first.recordings[0].recording_ref
    assert first_projection.recordings[0].source_relative_name == "recordings/dawn.wav"
    assert first_ids == tuple(item.candidate_id for item in first.recordings[0].candidates)
    assert first_projection.recordings[0].candidates[0].start_frame == 160
    assert first_projection.recordings[0].candidates[0].end_frame == 320
    assert first_projection.recordings[0].candidates[0].max_target_score == 0.91
    with pytest.raises(FrozenInstanceError):
        first_projection.result_id = second.result_id  # type: ignore[misc]

    collection_root = tmp_path / "collection"
    collection_root.mkdir()
    result_document = collection_root / "result.json"
    result_document.write_text(json.dumps(first.to_dict(), sort_keys=True), encoding="utf-8")
    original_result_bytes = result_document.read_bytes()
    store = ResultSelectionStore(collection_root)
    first_selection = store.replace(first, first_ids[:1])
    second_selection = store.replace(second, second_ids)
    assert first_selection.selection_revision == 1
    assert second_selection.selection_revision == 1
    assert store.read(first).selection.candidate_ids == first_ids[:1]
    assert store.read(second).selection.candidate_ids == second_ids
    assert result_document.read_bytes() == original_result_bytes

    frozen = freeze_result_selection(first, store.read(first).selection)
    assert frozen.result_id == first.result_id
    assert frozen.result_digest == first.result_digest
    assert frozen.selection_revision == 1
    assert frozen.candidate_ids == first_ids[:1]
    assert type(frozen).from_dict(frozen.to_dict()) == frozen

    selection_path = store.path_for(first.result_id)
    missing_candidate = json.loads(selection_path.read_text(encoding="utf-8"))
    missing_candidate["candidate_ids"] = ["cand_" + "f" * 32]
    selection_path.write_text(json.dumps(missing_candidate, sort_keys=True), encoding="utf-8")
    removed = store.read(first)
    assert removed.reconciliation is SelectionReconciliation.CANDIDATES_REMOVED
    assert removed.selection.selection_revision == 2
    assert removed.selection.candidate_ids == ()
    assert removed.message
    restored = store.replace(first, first_ids[:1])
    assert restored.selection_revision == 3

    changed_outcome = replace(first.recordings[0], candidates=first.recordings[0].candidates[1:])
    changed = _result("c", result_id=first.result_id, recordings=(changed_outcome,))
    reconciled = store.read(changed)
    assert reconciled.reconciliation is SelectionReconciliation.RESULT_CHANGED
    assert reconciled.selection.result_digest == changed.result_digest
    assert reconciled.selection.selection_revision == 4
    assert reconciled.selection.candidate_ids == ()
    assert reconciled.message


def test_result_status_and_provenance_decisions_are_truthful():
    """Case: UT-DET-017."""
    inventory_id = "inv_" + "1" * 32
    populated = _result(
        "1",
        recordings=(
            _outcome(
                inventory_id=inventory_id,
                key="recordings/dawn.wav",
                source_digit="7",
                candidate_frames=((160, 320),),
            ),
        ),
    )
    empty = _result(
        "2",
        recordings=(
            _outcome(
                inventory_id=inventory_id,
                key="recordings/quiet.wav",
                source_digit="8",
            ),
        ),
    )
    partial = _result(
        "3",
        recordings=(
            _outcome(
                inventory_id=inventory_id,
                key="recordings/dawn.wav",
                source_digit="7",
                candidate_frames=((160, 320),),
            ),
            _outcome(
                inventory_id=inventory_id,
                key="recordings/broken.wav",
                source_digit="9",
                failed=True,
            ),
        ),
    )

    populated_view = project_result(populated, source_state=ResultSourceState.AVAILABLE)
    empty_view = project_result(empty, source_state=ResultSourceState.AVAILABLE)
    partial_view = project_result(partial, source_state=ResultSourceState.AVAILABLE)
    unavailable_view = project_result(populated, source_state=ResultSourceState.UNAVAILABLE)
    stale_view = project_result(populated, source_state=ResultSourceState.STALE)

    assert populated_view.content_state is ResultContentState.POPULATED
    assert empty_view.content_state is ResultContentState.EMPTY
    assert partial_view.content_state is ResultContentState.PARTIAL
    assert partial_view.recordings[0].outcome is FileOutcomeStatus.FAILED
    assert partial_view.recordings[0].error_code == "audio_decode_failed"
    assert unavailable_view.provenance_visible
    assert unavailable_view.candidate_count == populated.candidate_count
    assert unavailable_view.recordings[0].candidates[0].start_time_ns == 10_000_000
    assert not unavailable_view.source_navigation_enabled
    assert stale_view.provenance_visible
    assert not stale_view.source_navigation_enabled
    assert populated_view.source_navigation_enabled
