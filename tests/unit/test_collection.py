import pytest

from biocall_studio_train.domain.collection import (
    MAX_TIMESTAMP_MS,
    InventoryEntry,
    WavHeader,
    compare_inventories,
    ensure_unique_interval,
    parse_positive_filename,
    validate_interval,
    validate_source_match,
    validate_wav_header,
)
from biocall_studio_train.persistence.collection_metadata import validate_collection_manifest


def _header(*, frames=16_000, rate=16_000, channels=1, width=2, codec="PCM"):
    return WavHeader(codec, channels, rate, width, frames)


def test_positive_filename_parser_is_anchored_and_preserves_complete_source_stem():
    """Case: UT-COL-001."""
    parsed = parse_positive_filename("SITE__north__start-012500ms__end-014900ms__call-01.wav")
    assert (parsed.source_stem, parsed.start_ms, parsed.end_ms, parsed.label) == (
        "SITE__north",
        12_500,
        14_900,
        "call-01",
    )
    for invalid in (
        "SITE__start-1.5ms__end-2ms__call.wav",
        "SITE__start--1ms__end-2ms__call.wav",
        "SITE__start-1ms__end-2ms__.wav",
        "prefix_SITE__start-1ms__end-2ms__call.wav.extra",
        f"SITE__start-1ms__end-{MAX_TIMESTAMP_MS + 1}ms__call.wav",
    ):
        with pytest.raises(ValueError):
            parse_positive_filename(invalid)


def test_source_resolution_is_exact_and_duplicate_intervals_are_rejected():
    """Case: UT-COL-002."""
    assert validate_source_match("REC", {"REC": "source-a", "REC_LONG": "source-b"}) == "source-a"
    with pytest.raises(ValueError, match="Unknown Source Recording"):
        validate_source_match("RE", {"REC": "source-a"})
    with pytest.raises(ValueError, match="Ambiguous Source Recording"):
        validate_source_match("REC", {"REC": ("source-a", "source-b")})
    seen = set()
    ensure_unique_interval("source-a", 0, 1_000, seen)
    with pytest.raises(ValueError, match="Duplicate"):
        ensure_unique_interval("source-a", 0, 1_000, seen)


def test_source_time_bounds_and_frame_rounding_tolerance_are_exact():
    """Case: UT-COL-003."""
    source = _header(frames=160_000)
    positive = _header(frames=16_001)
    validate_interval(0, 1_000, source, positive)
    with pytest.raises(ValueError, match="start must be earlier"):
        validate_interval(1_000, 1_000, source, positive)
    with pytest.raises(ValueError, match="outside Source Recording"):
        validate_interval(9_500, 10_001, source, _header(frames=8_016))
    with pytest.raises(ValueError, match="duration disagrees"):
        validate_interval(0, 1_000, source, _header(frames=16_003))


def test_wav_header_facts_reject_unsupported_or_inconsistent_audio():
    """Case: UT-COL-004."""
    validate_wav_header(_header())
    for header, match in (
        (_header(codec="IEEE_FLOAT"), "codec"),
        (_header(channels=0), "channel"),
        (_header(rate=0), "sample rate"),
        (_header(width=0), "sample width"),
        (_header(frames=0), "empty"),
    ):
        with pytest.raises(ValueError, match=match):
            validate_wav_header(header)


def test_inventory_change_decision_distinguishes_all_cache_states():
    """Case: UT-COL-005."""
    old = {
        "recordings/a.wav": InventoryEntry("recordings/a.wav", 10, 1),
        "recordings/removed.wav": InventoryEntry("recordings/removed.wav", 20, 2),
        "recordings/changed.wav": InventoryEntry("recordings/changed.wav", 30, 3),
    }
    current = {
        "recordings/a.wav": InventoryEntry("recordings/a.wav", 10, 1),
        "recordings/added.wav": InventoryEntry("recordings/added.wav", 40, 4),
        "recordings/changed.wav": InventoryEntry("recordings/changed.wav", 31, 3),
    }
    change = compare_inventories(old, current)
    assert change.unchanged == {"recordings/a.wav"}
    assert change.added == {"recordings/added.wav"}
    assert change.removed == {"recordings/removed.wav"}
    assert change.changed == {"recordings/changed.wav"}
    assert compare_inventories(None, current).cache_state == "absent"
    assert compare_inventories(old, current, cache_valid=False).cache_state == "corrupt"


def test_collection_manifest_rejects_versions_and_unsafe_partition_refs():
    """Case: UT-COL-006."""
    valid = {
        "schema_version": 2,
        "collection_id": "collection-123",
        "collection_name": "Example",
        "scanned_at": "2026-10-24T10:00:00+00:00",
        "valid": True,
        "summary": {"recordings": 1, "positives": 1, "duration_seconds": 8.0},
        "inventory": [],
        "record_partitions": ["records/scan-part-00001.jsonl"],
        "positive_partitions": ["positives/scan-part-00001.jsonl"],
        "partition_sha256": {
            "records/scan-part-00001.jsonl": "a" * 64,
            "positives/scan-part-00001.jsonl": "b" * 64,
        },
        "header_reads": 2,
    }
    assert validate_collection_manifest(valid)["collection_id"] == "collection-123"
    with pytest.raises(ValueError, match="schema"):
        validate_collection_manifest({**valid, "schema_version": 1})
    with pytest.raises(ValueError, match="partition"):
        validate_collection_manifest({**valid, "record_partitions": ["../escape.jsonl"]})
    with pytest.raises(ValueError, match="digest"):
        validate_collection_manifest({**valid, "partition_sha256": {}})
    with pytest.raises(ValueError, match="manifest facts"):
        validate_collection_manifest({**valid, "collection_name": None})
    with pytest.raises(ValueError, match="manifest facts"):
        validate_collection_manifest({**valid, "scanned_at": "not-a-timestamp"})
