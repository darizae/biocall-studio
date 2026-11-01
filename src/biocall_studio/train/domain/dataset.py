"""Qt-free Dataset Build configuration, mining, Split, and manifest decisions."""

from __future__ import annotations

import itertools
import math
import random
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from biocall_studio.shared.paths import validate_relative_path

DATASET_SCHEMA_VERSION = 1
MAX_SEED = 2_147_483_647
_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, order=True)
class Interval:
    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if type(self.start_ms) is not int or type(self.end_ms) is not int:
            raise ValueError("Source-time intervals must use integer milliseconds.")
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("Source-time intervals must be nonempty and nonnegative.")


@dataclass(frozen=True)
class MiningSource:
    source_recording_id: str
    duration_ms: int
    protected: tuple[Interval, ...]
    positive_count: int

    def __post_init__(self) -> None:
        if not self.source_recording_id:
            raise ValueError("Mining Source Recording ID must not be empty.")
        if type(self.duration_ms) is not int or self.duration_ms <= 0:
            raise ValueError("Mining source duration must be positive integer milliseconds.")
        if type(self.positive_count) is not int or self.positive_count < 0:
            raise ValueError("Mining source positive count must be nonnegative.")
        if any(interval.end_ms > self.duration_ms for interval in self.protected):
            raise ValueError("Protected interval exceeds its Source Recording duration.")


@dataclass(frozen=True, order=True)
class NoiseWindow:
    source_recording_id: str
    start_ms: int
    end_ms: int

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass(frozen=True)
class NoisePlan:
    windows: tuple[NoiseWindow, ...]
    requested: int
    underfill: int
    attempts: int
    eligible_ms_by_source: dict[str, int]


@dataclass(frozen=True)
class SplitPlan:
    assignments: dict[str, str]
    counts: dict[str, dict[str, int]]


@dataclass(frozen=True)
class BuildConfig:
    selected_recording_ids: tuple[str, ...]
    negative_mode: str
    negative_ratio: float
    negative_count: int
    allocation: str
    train_percent: int
    balance_classes: bool
    seed: int
    margin_ms: int
    attempts_per_slot: int = 256

    def __post_init__(self) -> None:
        if (
            not self.selected_recording_ids
            or len(set(self.selected_recording_ids)) != len(self.selected_recording_ids)
            or any(not value for value in self.selected_recording_ids)
        ):
            raise ValueError("Select a unique, nonempty set of Source Recordings.")
        if self.negative_mode not in {"ratio", "absolute"}:
            raise ValueError("Negative amount must be per-positive or total.")
        if (
            not isinstance(self.negative_ratio, (int, float))
            or isinstance(self.negative_ratio, bool)
            or not math.isfinite(self.negative_ratio)
            or not 0 <= self.negative_ratio <= 20
        ):
            raise ValueError("Negatives per positive must be between 0 and 20.")
        if type(self.negative_count) is not int or not 0 <= self.negative_count <= 200_000:
            raise ValueError("Total negatives must be an integer from 0 to 200000.")
        if self.allocation not in {"proportional", "even"}:
            raise ValueError("Negative allocation must be proportional or even.")
        if self.train_percent not in {70, 80, 90}:
            raise ValueError("Training Split must be 70, 80, or 90 percent.")
        if type(self.balance_classes) is not bool:
            raise ValueError("Class-ratio balancing must be true or false.")
        if type(self.seed) is not int or not 0 <= self.seed <= MAX_SEED:
            raise ValueError("Seed must be an integer from 0 to 2147483647.")
        if type(self.margin_ms) is not int or not 0 <= self.margin_ms <= 60_000:
            raise ValueError("Positive exclusion margin must be nonnegative milliseconds.")
        if type(self.attempts_per_slot) is not int or self.attempts_per_slot <= 0:
            raise ValueError("Mining attempts per slot must be a positive integer.")

    def requested_negative_count(self, positive_count: int) -> int:
        if type(positive_count) is not int or positive_count < 0:
            raise ValueError("Positive count must be a nonnegative integer.")
        if self.negative_mode == "absolute":
            return self.negative_count
        return int(positive_count * self.negative_ratio + 0.5)

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_recording_ids": list(self.selected_recording_ids),
            "negative_mode": self.negative_mode,
            "negative_ratio": self.negative_ratio,
            "negative_count": self.negative_count,
            "allocation": self.allocation,
            "train_percent": self.train_percent,
            "balance_classes": self.balance_classes,
            "seed": self.seed,
            "margin_ms": self.margin_ms,
            "attempts_per_slot": self.attempts_per_slot,
        }

    @classmethod
    def from_dict(cls, raw: object) -> BuildConfig:
        if not isinstance(raw, dict):
            raise ValueError("Dataset Build config must be an object.")
        try:
            selected = raw["selected_recording_ids"]
            if not isinstance(selected, list) or any(
                not isinstance(value, str) for value in selected
            ):
                raise ValueError("Selected Source Recording IDs must be a list of strings.")
            return cls(
                selected_recording_ids=tuple(selected),
                negative_mode=raw["negative_mode"],
                negative_ratio=raw["negative_ratio"],
                negative_count=raw["negative_count"],
                allocation=raw["allocation"],
                train_percent=raw["train_percent"],
                balance_classes=raw["balance_classes"],
                seed=raw["seed"],
                margin_ms=raw["margin_ms"],
                attempts_per_slot=raw.get("attempts_per_slot", 256),
            )
        except KeyError as exc:
            raise ValueError(f"Missing Dataset Build config field: {exc.args[0]}") from exc


def protected_intervals(
    annotations: tuple[Interval, ...], *, duration_ms: int, margin_ms: int
) -> tuple[Interval, ...]:
    """Expand, clip, and merge half-open positive source-time spans."""
    if type(duration_ms) is not int or duration_ms <= 0:
        raise ValueError("Source Recording duration must be positive integer milliseconds.")
    if type(margin_ms) is not int or margin_ms < 0:
        raise ValueError("Exclusion margin must be nonnegative integer milliseconds.")
    expanded: list[Interval] = []
    for annotation in annotations:
        if annotation.end_ms > duration_ms:
            raise ValueError("Annotation exceeds Source Recording duration.")
        expanded.append(
            Interval(
                max(0, annotation.start_ms - margin_ms),
                min(duration_ms, annotation.end_ms + margin_ms),
            )
        )
    merged: list[Interval] = []
    for interval in sorted(expanded):
        if merged and interval.start_ms <= merged[-1].end_ms:
            previous = merged[-1]
            merged[-1] = Interval(previous.start_ms, max(previous.end_ms, interval.end_ms))
        else:
            merged.append(interval)
    return tuple(merged)


def _eligible_intervals(duration_ms: int, blocked: tuple[Interval, ...]) -> list[Interval]:
    eligible: list[Interval] = []
    cursor = 0
    for interval in blocked:
        if cursor < interval.start_ms:
            eligible.append(Interval(cursor, interval.start_ms))
        cursor = max(cursor, interval.end_ms)
    if cursor < duration_ms:
        eligible.append(Interval(cursor, duration_ms))
    return eligible


def _slot_allocation(sources: tuple[MiningSource, ...], count: int, mode: str) -> list[int]:
    if count == 0:
        return [0] * len(sources)
    weights = [1 if mode == "even" else source.positive_count for source in sources]
    total_weight = sum(weights)
    if total_weight <= 0:
        raise ValueError("Selected Source Recordings have no positive examples for allocation.")
    exact = [count * weight / total_weight for weight in weights]
    allocated = [math.floor(value) for value in exact]
    remainder = count - sum(allocated)
    order = sorted(
        range(len(sources)), key=lambda index: (-(exact[index] - allocated[index]), index)
    )
    for index in order[:remainder]:
        allocated[index] += 1
    return allocated


def _take_window(
    source_id: str,
    free: list[Interval],
    duration_ms: int,
    rng: random.Random,
) -> NoiseWindow | None:
    capable = [
        index
        for index, interval in enumerate(free)
        if interval.end_ms - interval.start_ms >= duration_ms
    ]
    if not capable:
        return None
    index = rng.choice(capable)
    interval = free.pop(index)
    if interval.end_ms - interval.start_ms == duration_ms or rng.randrange(2) == 0:
        start_ms = interval.start_ms
    else:
        start_ms = interval.end_ms - duration_ms
    end_ms = start_ms + duration_ms
    replacements: list[Interval] = []
    if interval.start_ms < start_ms:
        replacements.append(Interval(interval.start_ms, start_ms))
    if end_ms < interval.end_ms:
        replacements.append(Interval(end_ms, interval.end_ms))
    free[index:index] = replacements
    return NoiseWindow(source_id, start_ms, end_ms)


def plan_noise_windows(
    sources: tuple[MiningSource, ...],
    *,
    window_durations_ms: tuple[int, ...],
    allocation: str,
    seed: int,
    attempts_per_slot: int,
) -> NoisePlan:
    """Create a deterministic, bounded, nonoverlapping protected-time mining plan."""
    if not sources:
        raise ValueError("Select at least one Source Recording for Negative Mining.")
    if len({source.source_recording_id for source in sources}) != len(sources):
        raise ValueError("Mining Source Recording IDs must be unique.")
    if any(type(value) is not int or value <= 0 for value in window_durations_ms):
        raise ValueError("Noise window durations must be positive integer milliseconds.")
    if allocation not in {"proportional", "even"}:
        raise ValueError("Negative allocation must be proportional or even.")
    if type(seed) is not int or not 0 <= seed <= MAX_SEED:
        raise ValueError("Noise seed is outside the supported range.")
    if type(attempts_per_slot) is not int or attempts_per_slot <= 0:
        raise ValueError("Mining attempts per slot must be positive.")

    rng = random.Random(seed)
    durations = list(window_durations_ms)
    rng.shuffle(durations)
    allocation_counts = _slot_allocation(sources, len(durations), allocation)
    eligible = {
        source.source_recording_id: _eligible_intervals(source.duration_ms, source.protected)
        for source in sources
    }
    eligible_ms = {
        source_id: sum(interval.end_ms - interval.start_ms for interval in intervals)
        for source_id, intervals in eligible.items()
    }
    windows: list[NoiseWindow] = []
    attempts = 0
    cursor = 0
    for source, count in zip(sources, allocation_counts, strict=True):
        assigned = sorted(durations[cursor : cursor + count], reverse=True)
        cursor += count
        free = eligible[source.source_recording_id]
        for duration_ms in assigned:
            window = _take_window(source.source_recording_id, free, duration_ms, rng)
            if window is None:
                attempts += attempts_per_slot
                continue
            attempts += 1
            windows.append(window)
    windows.sort()
    return NoisePlan(
        tuple(windows),
        requested=len(window_durations_ms),
        underfill=len(window_durations_ms) - len(windows),
        attempts=attempts,
        eligible_ms_by_source=eligible_ms,
    )


def _split_counts(
    groups: dict[str, dict[str, int]], train_ids: set[str]
) -> dict[str, dict[str, int]]:
    counts = {
        "train": {"target": 0, "noise": 0},
        "val": {"target": 0, "noise": 0},
    }
    for source_id, values in groups.items():
        split = "train" if source_id in train_ids else "val"
        counts[split]["target"] += values["target"]
        counts[split]["noise"] += values["noise"]
    for values in counts.values():
        values["total"] = values["target"] + values["noise"]
    return counts


def assign_source_splits(
    groups: dict[str, dict[str, int]],
    *,
    train_percent: int,
    seed: int,
    balance_classes: bool,
) -> SplitPlan:
    """Choose a deterministic train/val assignment without Source Recording leakage."""
    if len(groups) < 2:
        raise ValueError("At least two Source Recordings are required for train/val Splits.")
    if train_percent not in {70, 80, 90} or type(seed) is not int or not 0 <= seed <= MAX_SEED:
        raise ValueError("Invalid source-grouped Split configuration.")
    for values in groups.values():
        if set(values) != {"target", "noise"} or any(
            type(value) is not int or value < 0 for value in values.values()
        ):
            raise ValueError("Source Split counts must contain nonnegative target/noise integers.")

    source_ids = sorted(groups)
    rng = random.Random(seed)
    tie_order = source_ids[:]
    rng.shuffle(tie_order)
    rank = {source_id: index for index, source_id in enumerate(tie_order)}
    total_target = sum(values["target"] for values in groups.values())
    total_noise = sum(values["noise"] for values in groups.values())
    total = total_target + total_noise
    desired = train_percent / 100

    if len(source_ids) <= 18:
        candidates = (
            set(choice)
            for size in range(1, len(source_ids))
            for choice in itertools.combinations(source_ids, size)
        )
    else:
        generated: list[set[str]] = []
        target_size = max(1, min(len(source_ids) - 1, round(len(source_ids) * desired)))
        for _ in range(256):
            shuffled = source_ids[:]
            rng.shuffle(shuffled)
            generated.append(set(shuffled[:target_size]))
        feasible_seed: set[str] | None = None
        for target_source in source_ids:
            if groups[target_source]["target"] == 0:
                continue
            for noise_source in source_ids:
                if groups[noise_source]["noise"] == 0:
                    continue
                candidate = {target_source, noise_source}
                counts = _split_counts(groups, candidate)
                if all(
                    counts[split][label] > 0
                    for split in ("train", "val")
                    for label in ("target", "noise")
                ):
                    feasible_seed = candidate
                    break
            if feasible_seed is not None:
                break
        if feasible_seed is not None:
            generated.extend((feasible_seed, set(source_ids) - feasible_seed))
        candidates = iter(generated)

    best: (
        tuple[tuple[float, float, tuple[int, ...]], set[str], dict[str, dict[str, int]]] | None
    ) = None
    for train_ids in candidates:
        counts = _split_counts(groups, train_ids)
        if any(
            counts[split][label] == 0 for split in ("train", "val") for label in ("target", "noise")
        ):
            continue
        total_error = abs(counts["train"]["total"] / total - desired) if total else math.inf
        class_error = 0.0
        if balance_classes:
            class_error = abs(counts["train"]["target"] / total_target - desired) + abs(
                counts["train"]["noise"] / total_noise - desired
            )
        tie = tuple(sorted(rank[source_id] for source_id in train_ids))
        score = (total_error, class_error, tie)
        if best is None or score < best[0]:
            best = (score, train_ids, counts)
    if best is None:
        raise ValueError(
            "Source-grouped train/val class coverage is impossible with the selected recordings."
        )
    train_ids, counts = best[1], best[2]
    return SplitPlan(
        {source_id: "train" if source_id in train_ids else "val" for source_id in source_ids},
        counts,
    )


def _validate_digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"Invalid SHA-256 for Dataset {field}.")
    return value


def _validate_file_reference(raw: object, prefix: str) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ValueError("Invalid Dataset file reference.")
    try:
        path = validate_relative_path(raw["path"])
        digest = _validate_digest(raw["sha256"], path)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid Dataset file reference.") from exc
    if not path.startswith(prefix):
        raise ValueError("Invalid Dataset file reference location.")
    return {"path": path, "sha256": digest}


def validate_snippet_record(raw: object) -> dict[str, Any]:
    """Validate one materialized Snippet's source-time and file provenance."""
    if not isinstance(raw, dict):
        raise ValueError("Dataset Snippet entry must be an object.")
    required = {
        "snippet_id",
        "relative_path",
        "label",
        "source_recording_id",
        "source_ref",
        "source_sha256",
        "start_ms",
        "end_ms",
        "producing_positive_ref",
        "split",
        "transform",
        "sha256",
    }
    if not required.issubset(raw):
        raise ValueError("Dataset Snippet entry is missing provenance fields.")
    snippet_id = raw["snippet_id"]
    source_id = raw["source_recording_id"]
    label = raw["label"]
    split = raw["split"]
    start_ms = raw["start_ms"]
    end_ms = raw["end_ms"]
    if (
        not isinstance(snippet_id, str)
        or not snippet_id
        or not isinstance(source_id, str)
        or not source_id
        or label not in {"target", "noise"}
        or split not in {"train", "val"}
        or type(start_ms) is not int
        or type(end_ms) is not int
        or start_ms < 0
        or end_ms <= start_ms
    ):
        raise ValueError("Dataset Snippet identity, source-time, label, or Split is invalid.")
    try:
        relative = validate_relative_path(raw["relative_path"])
        source_ref = validate_relative_path(raw["source_ref"])
        _validate_digest(raw["source_sha256"], source_ref)
        _validate_digest(raw["sha256"], relative)
    except (TypeError, ValueError) as exc:
        raise ValueError("Dataset Snippet contains an invalid file reference or digest.") from exc
    if not relative.startswith(f"snippets/{label}/") or not source_ref.startswith("recordings/"):
        raise ValueError("Dataset Snippet reference does not match its label or source.")
    positive_ref = raw["producing_positive_ref"]
    if label == "target":
        try:
            positive_ref = validate_relative_path(positive_ref)
        except (TypeError, ValueError) as exc:
            raise ValueError("Target Snippet must name its producing Positive Example.") from exc
        if not positive_ref.startswith("positives/"):
            raise ValueError("Target Snippet must name its producing Positive Example.")
    elif positive_ref is not None:
        raise ValueError("Noise Snippet cannot claim a producing Positive Example.")
    transform = raw["transform"]
    if (
        not isinstance(transform, dict)
        or transform.get("policy") != "pcm-preserve-nearest-frame-v1"
    ):
        raise ValueError("Dataset Snippet audio transform policy is invalid.")
    integer_fields = (
        "start_frame",
        "end_frame",
        "sample_rate_hz",
        "channels",
        "sample_width_bytes",
        "frame_count",
    )
    if any(type(transform.get(field)) is not int for field in integer_fields):
        raise ValueError("Dataset Snippet audio transform facts are invalid.")
    if (
        transform["start_frame"] < 0
        or transform["end_frame"] <= transform["start_frame"]
        or transform["frame_count"] != transform["end_frame"] - transform["start_frame"]
        or transform["sample_rate_hz"] <= 0
        or transform["channels"] not in {1, 2}
        or transform["sample_width_bytes"] not in {1, 2, 3, 4}
    ):
        raise ValueError("Dataset Snippet audio transform facts are invalid.")
    return raw


def validate_dataset_manifest(raw: object) -> dict[str, Any]:
    """Validate portable Dataset identity, config, counts, and referenced file metadata."""
    if not isinstance(raw, dict) or raw.get("schema_version") != DATASET_SCHEMA_VERSION:
        raise ValueError("Unsupported Dataset manifest schema.")
    required = {
        "dataset_id",
        "label",
        "collection_id",
        "collection_label",
        "created_at",
        "config",
        "source_policy",
        "selected_sources",
        "positive_inputs",
        "entries",
        "splits",
        "source_groups",
        "counts",
    }
    if not required.issubset(raw):
        raise ValueError("Dataset manifest is missing required fields.")
    for field in ("dataset_id", "label", "collection_id", "collection_label"):
        if not isinstance(raw[field], str) or not raw[field]:
            raise ValueError(f"Invalid Dataset {field}.")
    try:
        datetime.fromisoformat(raw["created_at"])
        config = BuildConfig.from_dict(raw["config"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid Dataset timestamp or Build config.") from exc
    run = raw.get("run")
    if run is not None and (
        not isinstance(run, dict)
        or set(run) != {"run_id", "request_id"}
        or any(not isinstance(value, str) or not value for value in run.values())
    ):
        raise ValueError("Invalid Dataset Run provenance.")
    policy = raw["source_policy"]
    if (
        not isinstance(policy, dict)
        or policy.get("audio_transform") != "pcm-preserve-nearest-frame-v1"
        or not isinstance(policy.get("scientific_reference"), str)
        or not policy["scientific_reference"]
    ):
        raise ValueError("Invalid Dataset source policy.")
    audio_extraction = policy.get("audio_extraction")
    if audio_extraction is not None and (
        not isinstance(audio_extraction, dict)
        or set(audio_extraction) != {"distribution", "version", "revision", "api"}
        or audio_extraction.get("distribution") != "bioacoustics-dl-toolbox"
        or not isinstance(audio_extraction.get("version"), str)
        or not audio_extraction["version"]
        or not isinstance(audio_extraction.get("revision"), str)
        or len(audio_extraction["revision"]) != 40
        or any(character not in "0123456789abcdef" for character in audio_extraction["revision"])
        or audio_extraction.get("api") != "bioacoustics_dl_toolbox.audio.extract_pcm_wav_segment"
    ):
        raise ValueError("Invalid Dataset audio extraction provenance.")
    sources = raw["selected_sources"]
    if not isinstance(sources, list) or not sources:
        raise ValueError("Dataset must contain selected Source Recording provenance.")
    source_ids: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("Invalid Dataset Source Recording provenance.")
        try:
            source_id = source["id"]
            path = validate_relative_path(source["relative_path"])
            _validate_digest(source["sha256"], path)
            fingerprint = source["fingerprint"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Invalid Dataset Source Recording provenance.") from exc
        if (
            not isinstance(source_id, str)
            or not source_id
            or not path.startswith("recordings/")
            or not isinstance(fingerprint, dict)
            or set(fingerprint)
            != {
                "size_bytes",
                "mtime_ns",
                "sample_rate_hz",
                "channels",
                "sample_width_bytes",
                "frame_count",
            }
            or any(type(value) is not int for value in fingerprint.values())
            or fingerprint["size_bytes"] <= 0
            or fingerprint["sample_rate_hz"] <= 0
            or fingerprint["channels"] not in {1, 2}
            or fingerprint["sample_width_bytes"] not in {1, 2, 3, 4}
            or fingerprint["frame_count"] <= 0
        ):
            raise ValueError("Invalid Dataset Source Recording provenance.")
        if source_id in source_ids:
            raise ValueError("Dataset Source Recording provenance must be unique.")
        source_ids.add(source_id)
    if source_ids != set(config.selected_recording_ids):
        raise ValueError("Dataset selected Source Recordings do not match its Build config.")
    positives = raw["positive_inputs"]
    if not isinstance(positives, list) or not positives:
        raise ValueError("Dataset must retain producing Positive Example provenance.")
    positive_paths: set[str] = set()
    for positive in positives:
        if not isinstance(positive, dict):
            raise ValueError("Invalid Dataset Positive Example provenance.")
        try:
            path = validate_relative_path(positive["relative_path"])
            source_id = positive["source_recording_id"]
            start_ms = positive["start_ms"]
            end_ms = positive["end_ms"]
            _validate_digest(positive["sha256"], path)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Invalid Dataset Positive Example provenance.") from exc
        if (
            not path.startswith("positives/")
            or path in positive_paths
            or source_id not in source_ids
            or type(start_ms) is not int
            or type(end_ms) is not int
            or start_ms < 0
            or end_ms <= start_ms
        ):
            raise ValueError("Invalid Dataset Positive Example provenance.")
        positive_paths.add(path)
    entries = raw["entries"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("Dataset must reference at least one Snippet entry partition.")
    entry_paths = [_validate_file_reference(entry, "entries/")["path"] for entry in entries]
    if len(entry_paths) != len(set(entry_paths)):
        raise ValueError("Dataset Snippet entry partition references must be unique.")
    splits = raw["splits"]
    if not isinstance(splits, dict) or set(splits) != {"train", "val"}:
        raise ValueError("Dataset must reference train and val Split files.")
    for split in ("train", "val"):
        _validate_file_reference(splits[split], f"splits/{split}.")
    groups = raw["source_groups"]
    if (
        not isinstance(groups, dict)
        or set(groups) != source_ids
        or any(value not in {"train", "val"} for value in groups.values())
        or set(groups.values()) != {"train", "val"}
    ):
        raise ValueError("Invalid Dataset source-group Split assignment.")
    counts = raw["counts"]
    if not isinstance(counts, dict) or set(counts) != {"target", "noise", "total", "train", "val"}:
        raise ValueError("Invalid Dataset counts.")
    for split in ("train", "val"):
        values = counts[split]
        if not isinstance(values, dict) or set(values) != {"target", "noise", "total"}:
            raise ValueError("Invalid Dataset Split counts.")
        if any(type(value) is not int or value < 0 for value in values.values()):
            raise ValueError("Invalid Dataset Split counts.")
        if values["target"] + values["noise"] != values["total"]:
            raise ValueError("Dataset Split count total is inconsistent.")
    if (
        any(type(counts[key]) is not int or counts[key] < 0 for key in ("target", "noise", "total"))
        or counts["target"] != len(positive_paths)
        or counts["target"] != counts["train"]["target"] + counts["val"]["target"]
        or counts["noise"] != counts["train"]["noise"] + counts["val"]["noise"]
        or counts["total"] != counts["target"] + counts["noise"]
    ):
        raise ValueError("Dataset counts are inconsistent.")
    return raw
