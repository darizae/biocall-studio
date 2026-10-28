from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from biocall_studio.detect.domain import (
    DETECT_COLLECTION_SCHEMA_VERSION,
    DetectCollectionRef,
    DetectRootBinding,
    RootBindingDecision,
    RootEvidence,
    RootObservation,
    apply_confirmed_relink,
    decide_root_binding,
    detect_workspace_path,
    ensure_unique_relative_references,
    validate_relative_reference,
)


def _ref(*, collection_id: str = "det_0123456789abcdef0123456789abcdef"):
    return DetectCollectionRef(
        schema_version=DETECT_COLLECTION_SCHEMA_VERSION,
        collection_id=collection_id,
        display_label="Rainforest dawn",
        created_at="2026-10-28T08:00:00Z",
        updated_at="2026-10-28T08:00:00Z",
        binding_revision=1,
        root_evidence=RootEvidence(filesystem_id=12, file_id=34),
        inventory_revision=None,
        inventory_binding_revision=None,
    )


def test_detect_collection_identity_schema_and_public_serialization_are_independent():
    """Case: UT-DET-001."""
    first = DetectCollectionRef.create(
        "Rainforest dawn",
        RootEvidence(filesystem_id=12, file_id=34),
        now=datetime(2026, 10, 28, 8, 0, tzinfo=UTC),
    )
    second = DetectCollectionRef.create(
        "Rainforest dawn",
        RootEvidence(filesystem_id=56, file_id=78),
        now=datetime(2026, 10, 28, 8, 0, tzinfo=UTC),
    )
    binding = DetectRootBinding(
        collection_id=first.collection_id,
        binding_revision=1,
        source_root_uri="file:///Volumes/Field/Rainforest_2026",
    )

    assert first.collection_id != second.collection_id
    assert first.collection_id.startswith("det_")
    assert DetectCollectionRef.from_public_dict(first.to_public_dict()) == first
    assert "source_root" not in first.to_public_dict()
    assert "/Volumes/Field" not in repr(first.to_public_dict())
    assert binding.source_root_uri not in repr(first.to_public_dict())
    assert detect_workspace_path(Path("/application/data")) == Path(
        "/application/data/detect/v1"
    )

    for version in (0, DETECT_COLLECTION_SCHEMA_VERSION + 1):
        payload = {**first.to_public_dict(), "schema_version": version}
        with pytest.raises(ValueError, match="Unsupported Detect Collection schema"):
            DetectCollectionRef.from_public_dict(payload)


def test_root_state_relink_confirmation_and_inventory_freshness_are_explicit():
    """Case: UT-DET-002."""
    expected = RootEvidence(filesystem_id=12, file_id=34)
    unrelated = RootEvidence(filesystem_id=12, file_id=99)

    assert (
        decide_root_binding(expected, RootObservation.available(expected))
        is RootBindingDecision.VALID
    )
    assert (
        decide_root_binding(expected, RootObservation.missing())
        is RootBindingDecision.MISSING
    )
    assert (
        decide_root_binding(expected, RootObservation.inaccessible())
        is RootBindingDecision.INACCESSIBLE
    )
    assert (
        decide_root_binding(expected, RootObservation.available(unrelated))
        is RootBindingDecision.CHANGED
    )

    current = replace(
        _ref(),
        inventory_revision="inv_0123456789abcdef0123456789abcdef",
        inventory_binding_revision=1,
    )
    moved = apply_confirmed_relink(
        current,
        expected,
        now=datetime(2026, 10, 28, 9, 0, tzinfo=UTC),
    )
    assert moved.binding_revision == 2
    assert moved.inventory_revision == current.inventory_revision
    assert moved.inventory_binding_revision == 1
    assert moved.inventory_is_stale

    with pytest.raises(ValueError, match="different source root"):
        apply_confirmed_relink(
            current,
            unrelated,
            now=datetime(2026, 10, 28, 9, 0, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    "value",
    [
        "/absolute.wav",
        "C:\\absolute.wav",
        "\\\\server\\share\\recording.wav",
        "recordings/../escape.wav",
        "recordings//double.wav",
        "recordings/CON.wav",
        "recordings/name?.wav",
        "recordings/control\x1f.wav",
    ],
)
def test_detect_relative_references_reject_unportable_or_escaping_values(value: str):
    """Case: UT-DET-003."""
    with pytest.raises(ValueError):
        validate_relative_reference(value)


def test_detect_relative_references_normalize_and_reject_portable_collisions():
    """Case: UT-DET-003."""
    assert validate_relative_reference("recordings/REC_A.wav") == "recordings/REC_A.wav"
    with pytest.raises(ValueError, match="collision"):
        ensure_unique_relative_references(
            ["recordings/Caf\u00e9.wav", "recordings/cafe\u0301.WAV"]
        )
