from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from biocall_studio.detect.domain.inventory import (
    BulkInclusionConfirmationRequired,
    ChangeKind,
    DecisionOrigin,
    DecisionRule,
    InclusionDecision,
    InventoryRecording,
    InventorySnapshot,
    RecordingStatus,
    StaleInventoryRevisionError,
    WavMetadata,
    compare_snapshots,
    find_file_identity_conflicts,
    find_portable_path_conflicts,
    plan_include_all_valid_recordings,
    resolve_decision,
    summarize_inventory,
)

COLLECTION_ID = "det_0123456789abcdef0123456789abcdef"
SCANNED_AT = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


def _recording(
    key: str,
    *,
    decision: InclusionDecision = InclusionDecision.INCLUDED,
    status: RecordingStatus = RecordingStatus.VALID,
    fingerprint: str = "a" * 64,
    size: int = 3_244,
) -> InventoryRecording:
    return InventoryRecording(
        recording_key=key,
        size_bytes=size,
        mtime_ns=123_456_789,
        content_sha256=fingerprint,
        wav=WavMetadata(
            sample_rate_hz=16_000,
            channels=1,
            frame_count=1_600,
            encoding="PCM_S16LE",
        ),
        decision=decision,
        status=status,
        reason="Recognized recordings/ folder",
        decision_origin=DecisionOrigin.DEFAULT,
        decision_path="recordings/",
        change=ChangeKind.ADDED,
    )


def test_inclusion_precedence_generated_exclusions_and_counts_are_explicit():
    """Case: UT-DET-004."""
    rules = (
        DecisionRule.folder("incoming", InclusionDecision.INCLUDED),
        DecisionRule.file("incoming/skip.wav", InclusionDecision.EXCLUDED),
        DecisionRule.folder("positives", InclusionDecision.INCLUDED),
    )

    included = resolve_decision("recordings/night/a.wav", rules)
    inherited = resolve_decision("incoming/night/b.wav", rules)
    file_override = resolve_decision("incoming/skip.wav", rules)
    generated = resolve_decision("positives/call.wav", rules)
    unknown = resolve_decision("other/c.wav", rules)

    assert (included.decision, included.origin, included.source_path) == (
        InclusionDecision.INCLUDED,
        DecisionOrigin.DEFAULT,
        "recordings/",
    )
    assert (inherited.decision, inherited.origin, inherited.source_path) == (
        InclusionDecision.INCLUDED,
        DecisionOrigin.EXPLICIT_FOLDER,
        "incoming/",
    )
    assert file_override.decision is InclusionDecision.EXCLUDED
    assert file_override.origin is DecisionOrigin.EXPLICIT_FILE
    assert generated.decision is InclusionDecision.EXCLUDED
    assert generated.origin is DecisionOrigin.POLICY
    assert unknown.decision is InclusionDecision.UNDECIDED

    rows = (
        _recording("recordings/a.wav"),
        _recording("incoming/b.wav", decision=InclusionDecision.UNDECIDED),
        _recording("positives/c.wav", decision=InclusionDecision.EXCLUDED),
        _recording(
            "recordings/broken.wav",
            status=RecordingStatus.INVALID,
            fingerprint="b" * 64,
        ),
        _recording(
            "recordings/missing.wav",
            status=RecordingStatus.MISSING,
            fingerprint="c" * 64,
        ),
    )
    counts = summarize_inventory(rows)
    assert counts.included == 1
    assert counts.undecided == 1
    assert counts.excluded == 1
    assert counts.invalid == 1
    assert counts.missing == 1


def test_normalized_path_and_file_identity_conflicts_never_collapse_rows():
    """Case: UT-DET-005."""
    portable = find_portable_path_conflicts(
        (
            "recordings/Caf\u00e9.wav",
            "recordings/cafe\u0301.WAV",
            "recordings/other.wav",
        )
    )
    hardlinks = find_file_identity_conflicts(
        {
            "recordings/a.wav": (12, 34),
            "recordings/a-copy.wav": (12, 34),
            "recordings/b.wav": (12, 56),
        }
    )

    assert portable == (
        ("recordings/Caf\u00e9.wav", "recordings/cafe\u0301.WAV"),
    )
    assert find_portable_path_conflicts(
        ("recordings/Night/a.wav", "recordings/night/b.wav")
    ) == (("recordings/Night/a.wav", "recordings/night/b.wav"),)
    assert hardlinks == (("recordings/a-copy.wav", "recordings/a.wav"),)
    with pytest.raises(ValueError, match="traversal"):
        DecisionRule.folder("../outside", InclusionDecision.INCLUDED)
    with pytest.raises(ValueError, match="folder"):
        DecisionRule.folder("recordings/a.wav", InclusionDecision.INCLUDED)


def test_snapshot_digest_roundtrip_change_interpretation_and_validation():
    """Case: UT-DET-006."""
    previous_rows = (
        _recording("recordings/a.wav", fingerprint="a" * 64),
        _recording("recordings/removed.wav", fingerprint="b" * 64),
        _recording("recordings/replaced.wav", fingerprint="c" * 64),
    )
    current_rows = (
        replace(previous_rows[0], change=ChangeKind.UNCHANGED),
        _recording("recordings/added.wav", fingerprint="d" * 64),
        replace(
            previous_rows[2],
            content_sha256="e" * 64,
            change=ChangeKind.REPLACED,
        ),
    )
    first = InventorySnapshot.create(
        collection_id=COLLECTION_ID,
        binding_revision=3,
        recordings=reversed(previous_rows),
        scanned_at=SCANNED_AT,
    )
    same = InventorySnapshot.create(
        collection_id=COLLECTION_ID,
        binding_revision=3,
        recordings=previous_rows,
        scanned_at=SCANNED_AT,
    )
    current = InventorySnapshot.create(
        collection_id=COLLECTION_ID,
        binding_revision=3,
        recordings=current_rows,
        scanned_at=SCANNED_AT,
    )

    assert first.inventory_id == same.inventory_id
    assert first.digest == same.digest
    assert InventorySnapshot.from_dict(first.to_dict()) == first
    delta = compare_snapshots(first, current)
    assert delta.added == frozenset({"recordings/added.wav"})
    assert delta.removed == frozenset({"recordings/removed.wav"})
    assert delta.replaced == frozenset({"recordings/replaced.wav"})
    assert delta.unchanged == frozenset({"recordings/a.wav"})

    tampered = first.to_dict()
    tampered["recordings"][0]["size_bytes"] += 1
    with pytest.raises(ValueError, match="digest"):
        InventorySnapshot.from_dict(tampered)


def test_bulk_inclusion_is_a_revision_checked_complete_atomic_replacement():
    """Case: UT-DET-024."""
    original = InventorySnapshot.create(
        collection_id=COLLECTION_ID,
        binding_revision=3,
        recordings=(
            _recording("recordings/already-included.wav"),
            replace(
                _recording(
                    "incoming/explicitly-excluded.wav",
                    decision=InclusionDecision.EXCLUDED,
                ),
                reason="Explicit file decision",
                decision_origin=DecisionOrigin.EXPLICIT_FILE,
                decision_path="incoming/explicitly-excluded.wav",
            ),
            replace(
                _recording(
                    "recordings/invalid.wav",
                    decision=InclusionDecision.EXCLUDED,
                    status=RecordingStatus.INVALID,
                    fingerprint="b" * 64,
                ),
                reason="Unsupported WAV encoding",
                decision_origin=DecisionOrigin.EXPLICIT_FILE,
                decision_path="recordings/invalid.wav",
            ),
            replace(
                _recording(
                    "positives/labeled.wav",
                    decision=InclusionDecision.EXCLUDED,
                    fingerprint="d" * 64,
                ),
                reason="Recognized generated or labeled-data folder",
                decision_origin=DecisionOrigin.POLICY,
                decision_path="positives/",
            ),
            replace(
                _recording(
                    "recordings/missing.wav",
                    decision=InclusionDecision.EXCLUDED,
                    status=RecordingStatus.MISSING,
                    fingerprint="c" * 64,
                ),
                reason="Recording is missing",
                decision_origin=DecisionOrigin.DEFAULT,
                decision_path="recordings/",
            ),
        ),
        decision_rules=(
            DecisionRule.file(
                "incoming/explicitly-excluded.wav", InclusionDecision.EXCLUDED
            ),
            DecisionRule.file("recordings/invalid.wav", InclusionDecision.EXCLUDED),
        ),
        scanned_at=SCANNED_AT,
    )
    original_document = original.to_dict()

    with pytest.raises(BulkInclusionConfirmationRequired) as confirmation:
        plan_include_all_valid_recordings(
            original,
            expected_inventory_id=original.inventory_id,
            exclusions_confirmed=False,
        )
    assert confirmation.value.exclusion_count == 1
    assert original.to_dict() == original_document

    with pytest.raises(StaleInventoryRevisionError):
        plan_include_all_valid_recordings(
            original,
            expected_inventory_id="inv_" + "f" * 32,
            exclusions_confirmed=True,
        )
    assert original.to_dict() == original_document

    plan = plan_include_all_valid_recordings(
        original,
        expected_inventory_id=original.inventory_id,
        exclusions_confirmed=True,
    )

    assert plan.expected_inventory_id == original.inventory_id
    assert plan.replaced_exclusion_count == 1
    assert plan.snapshot is not original
    assert {
        row.recording_key
        for row in plan.snapshot.recordings
        if row.decision is InclusionDecision.INCLUDED
    } == {
        "incoming/explicitly-excluded.wav",
        "positives/labeled.wav",
        "recordings/already-included.wav",
    }
    assert {
        rule.path for rule in plan.snapshot.decision_rules
    } == {
        "incoming/explicitly-excluded.wav",
        "positives/labeled.wav",
        "recordings/already-included.wav",
        "recordings/invalid.wav",
    }
    assert resolve_decision(
        "positives/labeled.wav", plan.snapshot.decision_rules
    ).decision is InclusionDecision.INCLUDED
    invalid = next(
        row
        for row in plan.snapshot.recordings
        if row.recording_key == "recordings/invalid.wav"
    )
    missing = next(
        row
        for row in plan.snapshot.recordings
        if row.recording_key == "recordings/missing.wav"
    )
    assert (invalid.status, invalid.decision) == (
        RecordingStatus.INVALID,
        InclusionDecision.EXCLUDED,
    )
    assert (missing.status, missing.decision) == (
        RecordingStatus.MISSING,
        InclusionDecision.EXCLUDED,
    )
    assert original.to_dict() == original_document
