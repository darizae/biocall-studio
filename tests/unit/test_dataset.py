import pytest

from alpaca_desktop.domain.dataset import (
    BuildConfig,
    Interval,
    MiningSource,
    assign_source_splits,
    plan_noise_windows,
    protected_intervals,
    validate_dataset_manifest,
    validate_snippet_record,
)


def test_protected_intervals_merge_clip_and_exclude_noise_windows():
    """Case: UT-DB-001."""
    protected = protected_intervals(
        (Interval(100, 250), Interval(200, 400), Interval(950, 1_000)),
        duration_ms=1_000,
        margin_ms=100,
    )
    assert protected == (Interval(0, 500), Interval(850, 1_000))

    plan = plan_noise_windows(
        (MiningSource("source-a", 1_000, protected, 3),),
        window_durations_ms=(100, 100, 100),
        allocation="even",
        seed=42,
        attempts_per_slot=100,
    )
    assert plan.underfill == 0
    assert len(plan.windows) == 3
    for window in plan.windows:
        assert all(
            window.end_ms <= blocked.start_ms or window.start_ms >= blocked.end_ms
            for blocked in protected
        )


def test_seeded_noise_plan_is_bounded_deterministic_and_reports_underfill():
    """Case: UT-DB-002."""
    sources = (
        MiningSource("source-a", 2_000, (Interval(0, 1_250),), 3),
        MiningSource("source-b", 2_000, (Interval(0, 1_250),), 1),
    )
    first = plan_noise_windows(
        sources,
        window_durations_ms=(250, 250, 250, 250),
        allocation="proportional",
        seed=7,
        attempts_per_slot=20,
    )
    second = plan_noise_windows(
        sources,
        window_durations_ms=(250, 250, 250, 250),
        allocation="proportional",
        seed=7,
        attempts_per_slot=20,
    )
    assert first == second
    assert first.attempts <= 80
    assert first.underfill == 0

    no_space = plan_noise_windows(
        (MiningSource("source-a", 1_000, (Interval(0, 1_000),), 1),),
        window_durations_ms=(500, 500),
        allocation="even",
        seed=7,
        attempts_per_slot=5,
    )
    assert no_space.underfill == 2
    assert no_space.eligible_ms_by_source == {"source-a": 0}
    assert no_space.attempts == 10


def test_source_grouped_split_is_reproducible_and_rejects_impossible_coverage():
    """Case: UT-DB-003."""
    groups = {
        "source-a": {"target": 3, "noise": 3},
        "source-b": {"target": 2, "noise": 2},
        "source-c": {"target": 1, "noise": 1},
    }
    first = assign_source_splits(groups, train_percent=80, seed=9, balance_classes=True)
    second = assign_source_splits(groups, train_percent=80, seed=9, balance_classes=True)
    assert first == second
    assert set(first.assignments) == set(groups)
    assert set(first.assignments.values()) == {"train", "val"}
    assert first.counts["train"]["target"] > 0
    assert first.counts["train"]["noise"] > 0
    assert first.counts["val"]["target"] > 0
    assert first.counts["val"]["noise"] > 0

    with pytest.raises(ValueError, match="class coverage"):
        assign_source_splits(
            {
                "source-a": {"target": 2, "noise": 0},
                "source-b": {"target": 0, "noise": 2},
            },
            train_percent=80,
            seed=9,
            balance_classes=True,
        )

    many_groups = {
        f"source-{index:02d}": {
            "target": 1 if index in {0, 1} else 0,
            "noise": 1 if index in {1, 2} else 0,
        }
        for index in range(20)
    }
    large = assign_source_splits(
        many_groups,
        train_percent=80,
        seed=9,
        balance_classes=True,
    )
    assert all(
        large.counts[split][label] > 0
        for split in ("train", "val")
        for label in ("target", "noise")
    )


def test_dataset_config_and_manifest_validate_provenance_and_portable_references():
    """Case: UT-DB-004."""
    config = BuildConfig(
        selected_recording_ids=("source-a", "source-b"),
        negative_mode="ratio",
        negative_ratio=1.5,
        negative_count=0,
        allocation="even",
        train_percent=80,
        balance_classes=True,
        seed=42,
        margin_ms=250,
    )
    assert config.requested_negative_count(3) == 5

    manifest = {
        "schema_version": 1,
        "dataset_id": "dataset-0001",
        "label": "Example Collection · Dataset",
        "collection_id": "collection-0001",
        "collection_label": "Example Collection",
        "created_at": "2026-10-25T12:00:00+00:00",
        "config": config.to_dict(),
        "source_policy": {
            "audio_transform": "pcm-preserve-nearest-frame-v1",
            "scientific_reference": "alpaca-pipelines@91af528",
        },
        "selected_sources": [
            {
                "id": "source-a",
                "relative_path": "recordings/REC_A.wav",
                "sha256": "a" * 64,
                "fingerprint": {
                    "size_bytes": 1_024,
                    "mtime_ns": 1,
                    "sample_rate_hz": 16_000,
                    "channels": 1,
                    "sample_width_bytes": 2,
                    "frame_count": 16_000,
                },
            },
            {
                "id": "source-b",
                "relative_path": "recordings/REC_B.wav",
                "sha256": "b" * 64,
                "fingerprint": {
                    "size_bytes": 1_024,
                    "mtime_ns": 2,
                    "sample_rate_hz": 16_000,
                    "channels": 1,
                    "sample_width_bytes": 2,
                    "frame_count": 16_000,
                },
            },
        ],
        "positive_inputs": [
            {
                "relative_path": "positives/REC_A__start-1ms__end-2ms__call.wav",
                "source_recording_id": "source-a",
                "start_ms": 1,
                "end_ms": 2,
                "sha256": "f" * 64,
            },
            {
                "relative_path": "positives/REC_B__start-2ms__end-3ms__call.wav",
                "source_recording_id": "source-b",
                "start_ms": 2,
                "end_ms": 3,
                "sha256": "1" * 64,
            },
        ],
        "entries": [{"path": "entries/snippets-00001.jsonl", "sha256": "c" * 64}],
        "splits": {
            "train": {"path": "splits/train.csv", "sha256": "d" * 64},
            "val": {"path": "splits/val.csv", "sha256": "e" * 64},
        },
        "source_groups": {"source-a": "train", "source-b": "val"},
        "counts": {
            "target": 2,
            "noise": 4,
            "total": 6,
            "train": {"target": 1, "noise": 3, "total": 4},
            "val": {"target": 1, "noise": 1, "total": 2},
        },
    }
    assert validate_dataset_manifest(manifest)["dataset_id"] == "dataset-0001"
    snippet = {
        "snippet_id": "target-000001",
        "relative_path": "snippets/target/target-000001.wav",
        "label": "target",
        "source_recording_id": "source-a",
        "source_ref": "recordings/REC_A.wav",
        "source_sha256": "a" * 64,
        "start_ms": 1,
        "end_ms": 2,
        "producing_positive_ref": "positives/REC_A__start-1ms__end-2ms__call.wav",
        "split": "train",
        "transform": {
            "policy": "pcm-preserve-nearest-frame-v1",
            "start_frame": 16,
            "end_frame": 32,
            "sample_rate_hz": 16_000,
            "channels": 1,
            "sample_width_bytes": 2,
            "frame_count": 16,
        },
        "sha256": "b" * 64,
    }
    assert validate_snippet_record(snippet)["producing_positive_ref"].startswith("positives/")
    fingerprint = manifest["selected_sources"][0].pop("fingerprint")
    with pytest.raises(ValueError, match="provenance"):
        validate_dataset_manifest(manifest)
    manifest["selected_sources"][0]["fingerprint"] = fingerprint
    snippet["source_ref"] = "../REC_A.wav"
    with pytest.raises(ValueError, match="reference"):
        validate_snippet_record(snippet)
    manifest["entries"][0]["path"] = "../snippets.jsonl"
    with pytest.raises(ValueError, match="reference"):
        validate_dataset_manifest(manifest)
