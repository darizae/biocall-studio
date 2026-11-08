"""Pure frozen Review-export projection and streamed v2 metadata contracts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from biocall_studio.detect.domain.exports import frame_seconds, safe_snippet_relative_path
from biocall_studio.review.domain.intake import EligibleCandidate, ReviewResultKind
from biocall_studio.review.domain.sessions import (
    DecisionOrigin,
    FinalizedCandidateDecision,
    ReviewFinalizationSnapshot,
    ReviewLabel,
    ReviewSessionSource,
    validate_digest,
    validate_display_name,
    validate_session_id,
    validate_timestamp,
)
from biocall_studio.shared.storage import MAX_ESTIMATE_BYTES, pcm_wav_bytes

REVIEW_EXPORT_SCHEMA_VERSION = 2
REVIEW_EXPORT_ROW_VERSION = 1
REVIEW_EXPORT_RECEIPT_VERSION = 2
REVIEW_EXPORT_FILE_ROW_VERSION = 1
REVIEW_EXPORT_HISTORY_VERSION = 1
MAX_COMPACT_DOCUMENT_BYTES = 1024 * 1024
MAX_JSONL_ROW_BYTES = 16 * 1024
MAX_FILE_INDEX_ROW_BYTES = 4 * 1024
RIFF_MAX_DATA_BYTES = 0xFFFFFFFF - 36
FORMAT_POLICY = (
    "review-pcm-preserve-v2; original half-open source frames; no resample, downmix, "
    "channel merge or gap; combined output requires identical mono PCM"
)
COLLISION_POLICY = "private-same-volume-stage; atomic-no-replace-directory; never-overwrite"
ROWS_NAME = "review-export-rows.jsonl"
MANIFEST_NAME = "review-export-manifest.json"
FILES_NAME = "review-export-files.jsonl"
RECEIPT_NAME = "review-export-receipt.json"
RAVEN_NAME = "corpus.Table.1.selections.txt"
COMBINED_WAV_NAME = "corpus.wav"

_EXPORT_ID = re.compile(r"rexp_[0-9a-f]{32}")
_CANDIDATE_ID = re.compile(r"cand_[0-9a-f]{32}")
_RECORDING_ID = re.compile(r"rec_[0-9a-f]{32}")
_RESULT_ID = re.compile(r"pub_[0-9a-f]{32}")

RAVEN_HEADER = (
    b"Selection\tView\tChannel\tBegin Time (s)\tEnd Time (s)\tLow Freq (Hz)\t"
    b"High Freq (Hz)\tCandidate ID\tSource File\tSource Begin Frame\t"
    b"Source End Frame\tReview Status\tReview Label\tDecision Origin\n"
)


class ReviewExportMode(StrEnum):
    INDIVIDUAL = "individual_wav"
    COMBINED = "combined_wav_raven"
    BOTH = "both"

    @property
    def includes_individual(self) -> bool:
        return self in {ReviewExportMode.INDIVIDUAL, ReviewExportMode.BOTH}

    @property
    def includes_combined(self) -> bool:
        return self in {ReviewExportMode.COMBINED, ReviewExportMode.BOTH}


def _canonical_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("Review export metadata is not canonical JSON.") from exc


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _bounded(value: int, label: str, *, positive: bool = False) -> int:
    if type(value) is not int or value < (1 if positive else 0):
        raise ValueError(f"{label} is invalid.")
    if value > MAX_ESTIMATE_BYTES:
        raise OverflowError(f"{label} exceeds the supported byte range.")
    return value


def _add(left: int, right: int, label: str) -> int:
    _bounded(left, label)
    _bounded(right, label)
    if left > MAX_ESTIMATE_BYTES - right:
        raise OverflowError(f"{label} exceeds the supported byte range.")
    return left + right


def _timestamp(value: object, label: str) -> str:
    value = validate_timestamp(value, label)
    if len(value) != 24:
        raise ValueError(f"{label} must include millisecond UTC precision.")
    return value


def _relative(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{label} is invalid.")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError(f"{label} is unsafe.")
    return value


@dataclass(frozen=True, slots=True)
class ReviewSourceWaveFormat:
    sample_rate_hz: int
    channels: int
    sample_width_bytes: int

    def __post_init__(self) -> None:
        if (
            type(self.sample_rate_hz) is not int
            or self.sample_rate_hz <= 0
            or type(self.channels) is not int
            or self.channels <= 0
            or type(self.sample_width_bytes) is not int
            or self.sample_width_bytes not in {1, 2, 3, 4}
        ):
            raise ValueError("Review source PCM format is invalid.")

    def to_dict(self) -> dict[str, int]:
        return {
            "sample_rate_hz": self.sample_rate_hz,
            "channels": self.channels,
            "sample_width_bytes": self.sample_width_bytes,
        }


@dataclass(frozen=True, slots=True)
class ReviewExportSourceCandidate:
    candidate: EligibleCandidate
    decision: FinalizedCandidateDecision

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, EligibleCandidate) or not isinstance(
            self.decision, FinalizedCandidateDecision
        ):
            raise ValueError("Review export source candidate is invalid.")
        if (
            self.candidate.ordinal != self.decision.ordinal
            or self.candidate.candidate_id != self.decision.candidate_id
        ):
            raise ValueError("Review export candidate and finalized decision disagree.")


@dataclass(frozen=True, slots=True)
class ReviewExportRow:
    row_version: int
    ordinal: int
    candidate_id: str
    recording_ref: str
    recording_key: str
    source_sha256: str
    sample_rate_hz: int
    frame_count: int
    channels: int
    sample_width_bytes: int
    source_start_frame: int
    source_end_frame: int
    source_start_time_ns: int
    source_end_time_ns: int
    cnn_target_score: float
    rf_target_score: float | None
    label: str
    decision_origin: str | None
    decision_at: str | None
    export_status: str
    included: bool
    output_relative_path: str | None
    concat_start_frame: int | None
    concat_end_frame: int | None

    def __post_init__(self) -> None:
        if self.row_version != REVIEW_EXPORT_ROW_VERSION:
            raise ValueError("Unsupported Review export row version.")
        if type(self.ordinal) is not int or self.ordinal < 0:
            raise ValueError("Review export row order is invalid.")
        if _CANDIDATE_ID.fullmatch(self.candidate_id) is None:
            raise ValueError("Review export candidate ID is invalid.")
        if _RECORDING_ID.fullmatch(self.recording_ref) is None:
            raise ValueError("Review export recording ID is invalid.")
        _relative(self.recording_key, "Review export recording key")
        validate_digest(self.source_sha256, "Review export source")
        ReviewSourceWaveFormat(self.sample_rate_hz, self.channels, self.sample_width_bytes)
        if (
            type(self.frame_count) is not int
            or type(self.source_start_frame) is not int
            or type(self.source_end_frame) is not int
            or not 0 <= self.source_start_frame < self.source_end_frame <= self.frame_count
        ):
            raise ValueError("Review export source interval is invalid.")
        if self.label not in {item.value for item in ReviewLabel}:
            raise ValueError("Review export label is invalid.")
        expected_status = {
            (ReviewLabel.CALL.value, DecisionOrigin.INDIVIDUAL.value): "human_individual",
            (ReviewLabel.CALL.value, DecisionOrigin.BULK.value): "human_bulk",
            (ReviewLabel.UNREVIEWED.value, None): "model_only",
            (ReviewLabel.NOT_CALL.value, DecisionOrigin.INDIVIDUAL.value): "human_rejected",
            (ReviewLabel.NOT_CALL.value, DecisionOrigin.BULK.value): "human_rejected",
        }.get((self.label, self.decision_origin))
        if expected_status != self.export_status:
            raise ValueError("Review export truth status is invalid.")
        if self.decision_at is not None:
            validate_timestamp(self.decision_at, "Review export decision timestamp")
        if self.included != (self.label != ReviewLabel.NOT_CALL.value):
            raise ValueError("Review export inclusion disagrees with its frozen label.")
        if self.output_relative_path is not None:
            _relative(self.output_relative_path, "Review export output path")
        if (self.concat_start_frame is None) != (self.concat_end_frame is None):
            raise ValueError("Review export concatenated mapping is incomplete.")
        if self.concat_start_frame is not None and (
            self.concat_start_frame < 0
            or self.concat_end_frame - self.concat_start_frame
            != self.source_end_frame - self.source_start_frame
        ):
            raise ValueError("Review export concatenated mapping is invalid.")
        encoded = _canonical_bytes(self.to_dict())
        if len(encoded) > MAX_JSONL_ROW_BYTES:
            raise ValueError("Review export inventory row is too large.")

    @property
    def source_frame_count(self) -> int:
        return self.source_end_frame - self.source_start_frame

    def to_dict(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, raw: object) -> ReviewExportRow:
        if not isinstance(raw, dict) or set(raw) != set(cls.__dataclass_fields__):
            raise ValueError("Review export inventory row is invalid.")
        return cls(**raw)


@dataclass(frozen=True, slots=True)
class ReviewExportFile:
    row_version: int
    relative_path: str
    kind: str
    sha256: str
    byte_size: int

    def __post_init__(self) -> None:
        if self.row_version != REVIEW_EXPORT_FILE_ROW_VERSION:
            raise ValueError("Unsupported Review export file row version.")
        _relative(self.relative_path, "Review export file path")
        if self.kind not in {"individual_wav", "combined_wav", "raven_tsv"}:
            raise ValueError("Review export file kind is invalid.")
        validate_digest(self.sha256, "Review export file")
        _bounded(self.byte_size, "Review export file size", positive=True)
        if len(_canonical_bytes(self.to_dict())) > MAX_FILE_INDEX_ROW_BYTES:
            raise ValueError("Review export file index row is too large.")

    def to_dict(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, raw: object) -> ReviewExportFile:
        if not isinstance(raw, dict) or set(raw) != set(cls.__dataclass_fields__):
            raise ValueError("Review export file index row is invalid.")
        return cls(**raw)


@dataclass(frozen=True, slots=True)
class ReviewExportPlan:
    schema_version: int
    export_id: str
    plan_digest: str
    created_at: str
    session_id: str
    session_name: str
    finalization_digest: str
    source_digest: str
    settings_digest: str
    result_kind: str
    result_id: str
    result_digest: str
    publication_digest: str
    parent_result_id: str | None
    parent_result_digest: str | None
    mode: ReviewExportMode
    format_policy: str
    collision_policy: str
    destination_parent: str
    directory_name: str
    eligibility_scope: str
    recording_count: int
    failed_recording_count: int
    eligible_count: int
    included_count: int
    human_individual_count: int
    human_bulk_count: int
    model_only_count: int
    rejected_count: int
    rows_sha256: str
    rows_byte_size: int
    files_index_byte_size: int
    payload_file_count: int
    payload_bytes: int
    concat_frame_count: int
    concat_pcm_bytes: int
    expected_final_bytes: int

    def __post_init__(self) -> None:
        if self.schema_version != REVIEW_EXPORT_SCHEMA_VERSION:
            raise ValueError("Unsupported Review export schema.")
        if _EXPORT_ID.fullmatch(self.export_id) is None:
            raise ValueError("Review export ID is invalid.")
        _timestamp(self.created_at, "Review export creation time")
        validate_session_id(self.session_id)
        for digest, label in (
            (self.plan_digest, "Review export plan"),
            (self.finalization_digest, "Review finalization"),
            (self.source_digest, "Review source"),
            (self.settings_digest, "Review spectrogram settings"),
            (self.result_digest, "Review Result"),
            (self.publication_digest, "Review Result publication"),
            (self.rows_sha256, "Review export rows"),
        ):
            validate_digest(digest, label)
        if _RESULT_ID.fullmatch(self.result_id) is None:
            raise ValueError("Review export Result ID is invalid.")
        if (self.parent_result_id is None) != (self.parent_result_digest is None):
            raise ValueError("Review export parent Result lineage is incomplete.")
        if self.parent_result_id is not None:
            if _RESULT_ID.fullmatch(self.parent_result_id) is None:
                raise ValueError("Review export parent Result ID is invalid.")
            validate_digest(self.parent_result_digest, "Review parent Result")
        if not isinstance(self.mode, ReviewExportMode):
            raise ValueError("Review export mode is invalid.")
        if self.format_policy != FORMAT_POLICY or self.collision_policy != COLLISION_POLICY:
            raise ValueError("Review export policy is unsupported.")
        if not Path(self.destination_parent).is_absolute():
            raise ValueError("Review export destination must be absolute.")
        if self.directory_name != f"biocall-review-export-{self.export_id[5:17]}":
            raise ValueError("Review export directory name is invalid.")
        for name in (
            "recording_count",
            "failed_recording_count",
            "eligible_count",
            "included_count",
            "human_individual_count",
            "human_bulk_count",
            "model_only_count",
            "rejected_count",
            "rows_byte_size",
            "files_index_byte_size",
            "payload_file_count",
            "payload_bytes",
            "concat_frame_count",
            "concat_pcm_bytes",
            "expected_final_bytes",
        ):
            _bounded(getattr(self, name), f"Review export {name.replace('_', ' ')}")
        if self.eligible_count != self.included_count + self.rejected_count:
            raise ValueError("Review export inventory counts are inconsistent.")
        if self.included_count != (
            self.human_individual_count + self.human_bulk_count + self.model_only_count
        ):
            raise ValueError("Review export inclusion truth counts are inconsistent.")
        if self.included_count <= 0:
            raise ValueError("Review export has no Call or Unreviewed candidates.")
        if _canonical_digest(self._digest_dict()) != self.plan_digest:
            raise ValueError("Review export plan digest does not match.")

    @property
    def final_destination(self) -> Path:
        return Path(self.destination_parent) / self.directory_name

    def _digest_dict(self) -> dict[str, object]:
        omitted = {"plan_digest", "expected_final_bytes", "files_index_byte_size"}
        values = {
            name: (value.value if isinstance(value, StrEnum) else value)
            for name, value in ((name, getattr(self, name)) for name in self.__dataclass_fields__)
            if name not in omitted
        }
        return values


@dataclass(frozen=True, slots=True)
class ReviewExportReceipt:
    schema_version: int
    export_id: str
    receipt_digest: str
    plan_digest: str
    session_id: str
    finalization_digest: str
    mode: ReviewExportMode
    completed_at: str
    final_destination: str
    manifest_sha256: str
    manifest_byte_size: int
    rows_sha256: str
    rows_byte_size: int
    row_count: int
    files_sha256: str
    files_byte_size: int
    payload_file_count: int

    def __post_init__(self) -> None:
        if self.schema_version != REVIEW_EXPORT_RECEIPT_VERSION:
            raise ValueError("Unsupported Review export receipt schema.")
        if _EXPORT_ID.fullmatch(self.export_id) is None:
            raise ValueError("Review export receipt ID is invalid.")
        validate_session_id(self.session_id)
        for value, label in (
            (self.receipt_digest, "Review export receipt"),
            (self.plan_digest, "Review export plan"),
            (self.finalization_digest, "Review finalization"),
            (self.manifest_sha256, "Review export manifest"),
            (self.rows_sha256, "Review export rows"),
            (self.files_sha256, "Review export file index"),
        ):
            validate_digest(value, label)
        if not isinstance(self.mode, ReviewExportMode):
            raise ValueError("Review export receipt mode is invalid.")
        _timestamp(self.completed_at, "Review export completion time")
        if not Path(self.final_destination).is_absolute():
            raise ValueError("Review export receipt destination must be absolute.")
        for name in (
            "manifest_byte_size",
            "rows_byte_size",
            "row_count",
            "files_byte_size",
            "payload_file_count",
        ):
            _bounded(getattr(self, name), f"Review export receipt {name.replace('_', ' ')}")
        if _canonical_digest(self.unsigned_dict()) != self.receipt_digest:
            raise ValueError("Review export receipt digest does not match.")

    def unsigned_dict(self) -> dict[str, object]:
        return {
            name: (value.value if isinstance(value, StrEnum) else value)
            for name, value in ((name, getattr(self, name)) for name in self.__dataclass_fields__)
            if name != "receipt_digest"
        }

    def to_dict(self) -> dict[str, object]:
        return {**self.unsigned_dict(), "receipt_digest": self.receipt_digest}

    @classmethod
    def create(cls, **values: object) -> ReviewExportReceipt:
        unsigned = dict(values)
        mode = ReviewExportMode(unsigned["mode"])
        unsigned["mode"] = mode.value
        digest = _canonical_digest(unsigned)
        return cls(**{**values, "mode": mode, "receipt_digest": digest})

    @classmethod
    def from_dict(cls, raw: object) -> ReviewExportReceipt:
        if not isinstance(raw, dict) or set(raw) != set(cls.__dataclass_fields__):
            raise ValueError("Review export receipt document is invalid.")
        values = dict(raw)
        values["mode"] = ReviewExportMode(values["mode"])
        return cls(**values)


@dataclass(frozen=True, slots=True)
class ReviewExportHistoryRecord:
    schema_version: int
    export_id: str
    receipt_digest: str
    plan_digest: str
    session_id: str
    session_name: str
    finalization_digest: str
    result_id: str
    result_digest: str
    parent_result_id: str | None
    parent_result_digest: str | None
    mode: ReviewExportMode
    completed_at: str
    final_destination: str
    included_count: int
    rejected_count: int
    model_only_count: int
    payload_file_count: int

    def __post_init__(self) -> None:
        if self.schema_version != REVIEW_EXPORT_HISTORY_VERSION:
            raise ValueError("Unsupported Review export history schema.")
        if _EXPORT_ID.fullmatch(self.export_id) is None:
            raise ValueError("Review export history ID is invalid.")
        validate_session_id(self.session_id)
        validate_display_name(self.session_name, "Review export history session name")
        for value, label in (
            (self.receipt_digest, "Review export receipt"),
            (self.plan_digest, "Review export plan"),
            (self.finalization_digest, "Review finalization"),
            (self.result_digest, "Review Result"),
        ):
            validate_digest(value, label)
        if _RESULT_ID.fullmatch(self.result_id) is None:
            raise ValueError("Review export history Result ID is invalid.")
        if (self.parent_result_id is None) != (self.parent_result_digest is None):
            raise ValueError("Review export history parent lineage is incomplete.")
        if self.parent_result_id is not None:
            if _RESULT_ID.fullmatch(self.parent_result_id) is None:
                raise ValueError("Review export history parent Result ID is invalid.")
            validate_digest(self.parent_result_digest, "Review parent Result")
        if not isinstance(self.mode, ReviewExportMode):
            raise ValueError("Review export history mode is invalid.")
        _timestamp(self.completed_at, "Review export history completion time")
        if not Path(self.final_destination).is_absolute():
            raise ValueError("Review export history destination must be absolute.")
        for name in (
            "included_count",
            "rejected_count",
            "model_only_count",
            "payload_file_count",
        ):
            _bounded(getattr(self, name), f"Review export history {name.replace('_', ' ')}")
        if self.model_only_count > self.included_count:
            raise ValueError("Review export history truth counts are inconsistent.")

    def to_dict(self) -> dict[str, object]:
        return {
            name: (value.value if isinstance(value, StrEnum) else value)
            for name, value in ((name, getattr(self, name)) for name in self.__dataclass_fields__)
        }

    @classmethod
    def from_plan_receipt(
        cls, plan: ReviewExportPlan, receipt: ReviewExportReceipt
    ) -> ReviewExportHistoryRecord:
        if (
            receipt.export_id != plan.export_id
            or receipt.plan_digest != plan.plan_digest
            or receipt.session_id != plan.session_id
            or receipt.finalization_digest != plan.finalization_digest
            or receipt.mode is not plan.mode
        ):
            raise ValueError("Review export receipt does not match its frozen plan.")
        return cls(
            REVIEW_EXPORT_HISTORY_VERSION,
            receipt.export_id,
            receipt.receipt_digest,
            receipt.plan_digest,
            receipt.session_id,
            plan.session_name,
            receipt.finalization_digest,
            plan.result_id,
            plan.result_digest,
            plan.parent_result_id,
            plan.parent_result_digest,
            receipt.mode,
            receipt.completed_at,
            receipt.final_destination,
            plan.included_count,
            plan.rejected_count,
            plan.model_only_count,
            receipt.payload_file_count,
        )

    @classmethod
    def from_manifest_receipt(
        cls, manifest: Mapping[str, object], receipt: ReviewExportReceipt
    ) -> ReviewExportHistoryRecord:
        required = {
            "export_id",
            "plan_digest",
            "session_id",
            "session_name",
            "finalization_digest",
            "result_id",
            "result_digest",
            "parent_result_id",
            "parent_result_digest",
            "mode",
            "included_count",
            "rejected_count",
            "model_only_count",
            "payload_file_count",
        }
        if not required.issubset(manifest):
            raise ValueError("Review export manifest lacks history lineage.")
        if any(
            manifest[name] != expected
            for name, expected in (
                ("export_id", receipt.export_id),
                ("plan_digest", receipt.plan_digest),
                ("session_id", receipt.session_id),
                ("finalization_digest", receipt.finalization_digest),
                ("mode", receipt.mode.value),
                ("payload_file_count", receipt.payload_file_count),
            )
        ):
            raise ValueError("Review export manifest and receipt history lineage disagree.")
        return cls(
            REVIEW_EXPORT_HISTORY_VERSION,
            receipt.export_id,
            receipt.receipt_digest,
            receipt.plan_digest,
            receipt.session_id,
            manifest["session_name"],
            receipt.finalization_digest,
            manifest["result_id"],
            manifest["result_digest"],
            manifest["parent_result_id"],
            manifest["parent_result_digest"],
            receipt.mode,
            receipt.completed_at,
            receipt.final_destination,
            manifest["included_count"],
            manifest["rejected_count"],
            manifest["model_only_count"],
            receipt.payload_file_count,
        )

    @classmethod
    def from_dict(cls, raw: object) -> ReviewExportHistoryRecord:
        if not isinstance(raw, dict) or set(raw) != set(cls.__dataclass_fields__):
            raise ValueError("Review export history document is invalid.")
        values = dict(raw)
        values["mode"] = ReviewExportMode(values["mode"])
        return cls(**values)


def _truth(decision: FinalizedCandidateDecision) -> tuple[str, bool]:
    if decision.label is ReviewLabel.UNREVIEWED:
        return "model_only", True
    if decision.label is ReviewLabel.NOT_CALL:
        return "human_rejected", False
    if decision.origin is DecisionOrigin.INDIVIDUAL:
        return "human_individual", True
    if decision.origin is DecisionOrigin.BULK:
        return "human_bulk", True
    raise ValueError("Finalized Call decision has no human origin.")


def _row(
    source: ReviewExportSourceCandidate,
    source_format: ReviewSourceWaveFormat,
    mode: ReviewExportMode,
    concat_offset: int,
) -> ReviewExportRow:
    candidate = source.candidate
    decision = source.decision
    status, included = _truth(decision)
    length = candidate.end_frame - candidate.start_frame
    output = (
        safe_snippet_relative_path(
            candidate.recording_key,
            candidate.start_frame,
            candidate.end_frame,
            candidate.candidate_id,
        )
        if included and mode.includes_individual
        else None
    )
    concat_start = concat_offset if included and mode.includes_combined else None
    concat_end = concat_offset + length if included and mode.includes_combined else None
    return ReviewExportRow(
        row_version=REVIEW_EXPORT_ROW_VERSION,
        ordinal=candidate.ordinal,
        candidate_id=candidate.candidate_id,
        recording_ref=candidate.recording_ref,
        recording_key=candidate.recording_key,
        source_sha256=candidate.source_sha256,
        sample_rate_hz=candidate.sample_rate_hz,
        frame_count=candidate.frame_count,
        channels=candidate.channels,
        sample_width_bytes=source_format.sample_width_bytes,
        source_start_frame=candidate.start_frame,
        source_end_frame=candidate.end_frame,
        source_start_time_ns=candidate.start_time_ns,
        source_end_time_ns=candidate.end_time_ns,
        cnn_target_score=candidate.cnn_target_score,
        rf_target_score=candidate.rf_target_score,
        label=decision.label.value,
        decision_origin=None if decision.origin is None else decision.origin.value,
        decision_at=decision.modified_at,
        export_status=status,
        included=included,
        output_relative_path=output,
        concat_start_frame=concat_start,
        concat_end_frame=concat_end,
    )


def _iter_rows(
    mode: ReviewExportMode,
    candidates: Iterable[ReviewExportSourceCandidate],
    source_formats: Mapping[str, ReviewSourceWaveFormat],
) -> Iterator[ReviewExportRow]:
    concat_offset = 0
    expected_ordinal = 0
    for item in candidates:
        if item.candidate.ordinal != expected_ordinal:
            raise ValueError("Review export candidates are not in frozen order.")
        source_format = source_formats.get(item.candidate.recording_ref)
        if source_format is None:
            raise ValueError("A Review export recording has no verified PCM format.")
        if (
            source_format.sample_rate_hz != item.candidate.sample_rate_hz
            or source_format.channels != item.candidate.channels
        ):
            raise ValueError("Verified source format disagrees with the frozen Review candidate.")
        row = _row(item, source_format, mode, concat_offset)
        yield row
        if row.included and mode.includes_combined:
            concat_offset = row.concat_end_frame or concat_offset
        expected_ordinal += 1


def raven_line(row: ReviewExportRow, selection: int) -> bytes:
    if not row.included or row.concat_start_frame is None or row.concat_end_frame is None:
        raise ValueError("Only included combined rows have Raven mappings.")
    high_frequency = Decimal(row.sample_rate_hz) / 2
    high = format(high_frequency, "f").rstrip("0").rstrip(".")
    if high_frequency == high_frequency.to_integral_value():
        high = str(int(high_frequency))
    values = (
        str(selection),
        "1",
        "1",
        frame_seconds(row.concat_start_frame, row.sample_rate_hz),
        frame_seconds(row.concat_end_frame, row.sample_rate_hz),
        "0",
        high,
        row.candidate_id,
        row.recording_key,
        str(row.source_start_frame),
        str(row.source_end_frame),
        row.export_status,
        row.label,
        row.decision_origin or "",
    )
    return ("\t".join(values) + "\n").encode("utf-8")


def _manifest_unsigned(plan: ReviewExportPlan) -> dict[str, object]:
    return {
        "schema_version": plan.schema_version,
        "export_id": plan.export_id,
        "plan_digest": plan.plan_digest,
        "created_at": plan.created_at,
        "session_id": plan.session_id,
        "session_name": plan.session_name,
        "finalization_digest": plan.finalization_digest,
        "source_digest": plan.source_digest,
        "settings_digest": plan.settings_digest,
        "result_kind": plan.result_kind,
        "result_id": plan.result_id,
        "result_digest": plan.result_digest,
        "publication_digest": plan.publication_digest,
        "parent_result_id": plan.parent_result_id,
        "parent_result_digest": plan.parent_result_digest,
        "mode": plan.mode.value,
        "format_policy": plan.format_policy,
        "collision_policy": plan.collision_policy,
        "eligibility_scope": plan.eligibility_scope,
        "recording_count": plan.recording_count,
        "failed_recording_count": plan.failed_recording_count,
        "eligible_count": plan.eligible_count,
        "included_count": plan.included_count,
        "human_individual_count": plan.human_individual_count,
        "human_bulk_count": plan.human_bulk_count,
        "model_only_count": plan.model_only_count,
        "rejected_count": plan.rejected_count,
        "rows_file": ROWS_NAME,
        "rows_sha256": plan.rows_sha256,
        "rows_byte_size": plan.rows_byte_size,
        "files_index": FILES_NAME,
        "payload_file_count": plan.payload_file_count,
        "payload_bytes": plan.payload_bytes,
    }


def manifest_document(plan: ReviewExportPlan) -> dict[str, object]:
    document = _manifest_unsigned(plan)
    document["manifest_digest"] = _canonical_digest(document)
    if len(_canonical_bytes(document)) > MAX_COMPACT_DOCUMENT_BYTES:
        raise ValueError("Review export manifest is too large.")
    return document


def _planned_file(row: ReviewExportRow, kind: str, size: int) -> ReviewExportFile:
    if row.output_relative_path is None:
        raise ValueError("Review export output path is missing.")
    return ReviewExportFile(
        REVIEW_EXPORT_FILE_ROW_VERSION,
        row.output_relative_path,
        kind,
        "0" * 64,
        size,
    )


def _receipt_size(plan: ReviewExportPlan, manifest_size: int) -> int:
    placeholder = ReviewExportReceipt.create(
        schema_version=REVIEW_EXPORT_RECEIPT_VERSION,
        export_id=plan.export_id,
        plan_digest=plan.plan_digest,
        session_id=plan.session_id,
        finalization_digest=plan.finalization_digest,
        mode=plan.mode,
        completed_at=plan.created_at,
        final_destination=str(plan.final_destination),
        manifest_sha256="0" * 64,
        manifest_byte_size=manifest_size,
        rows_sha256=plan.rows_sha256,
        rows_byte_size=plan.rows_byte_size,
        row_count=plan.eligible_count,
        files_sha256="0" * 64,
        files_byte_size=plan.files_index_byte_size,
        payload_file_count=plan.payload_file_count,
    )
    return len(_canonical_bytes(placeholder.to_dict()))


def create_review_export_plan(
    *,
    finalization: ReviewFinalizationSnapshot,
    source: ReviewSessionSource,
    candidates: Iterable[ReviewExportSourceCandidate],
    source_formats: Mapping[str, ReviewSourceWaveFormat],
    mode: ReviewExportMode,
    destination_parent: Path,
    export_id: str,
    created_at: str,
) -> ReviewExportPlan:
    """Consume candidate rows once and return a compact, digest-bound export plan."""
    if not isinstance(finalization, ReviewFinalizationSnapshot) or not isinstance(
        source, ReviewSessionSource
    ):
        raise ValueError("Review export requires an immutable finalized session.")
    if finalization.source_digest != source.source_digest:
        raise ValueError("Finalized Review source digest does not match its session source.")
    mode = ReviewExportMode(mode)
    if _EXPORT_ID.fullmatch(export_id) is None:
        raise ValueError("Review export ID is invalid.")
    _timestamp(created_at, "Review export creation time")
    destination = Path(destination_parent).expanduser()
    if not destination.is_absolute():
        raise ValueError("Review export destination must be absolute.")

    rows_digest = hashlib.sha256()
    rows_size = 0
    file_index_size = 0
    payload_files = 0
    payload_bytes = 0
    concat_frames = 0
    included = individual = bulk = model = rejected = 0
    raven_bytes = len(RAVEN_HEADER) if mode.includes_combined else 0
    combined_format: tuple[int, int, int] | None = None
    decisions = iter(finalization.candidates)
    rows = iter(_iter_rows(mode, candidates, source_formats))
    count = 0
    for item in decisions:
        try:
            row = next(rows)
        except StopIteration as exc:
            raise ValueError("Review export is missing finalized candidate decisions.") from exc
        if row.ordinal != item.ordinal or row.candidate_id != item.candidate_id:
            raise ValueError("Review export candidate does not match its finalized decision.")
        encoded = _canonical_bytes(row.to_dict())
        rows_digest.update(encoded)
        rows_size = _add(rows_size, len(encoded), "Review export row bytes")
        count += 1
        if row.included:
            included += 1
            if row.export_status == "human_individual":
                individual += 1
            elif row.export_status == "human_bulk":
                bulk += 1
            else:
                model += 1
            wav_size = pcm_wav_bytes(
                row.source_frame_count,
                channels=row.channels,
                sample_width_bytes=row.sample_width_bytes,
            )
            if (
                mode.includes_individual
                and row.source_frame_count * row.channels * row.sample_width_bytes
                > RIFF_MAX_DATA_BYTES
            ):
                raise ValueError("An individual WAV would be too large for the supported format.")
            if mode.includes_individual:
                file_row = _planned_file(row, "individual_wav", wav_size)
                file_index_size = _add(
                    file_index_size,
                    len(_canonical_bytes(file_row.to_dict())),
                    "Review export file index bytes",
                )
                payload_bytes = _add(payload_bytes, wav_size, "Review export payload bytes")
                payload_files += 1
            if mode.includes_combined:
                candidate_format = (
                    row.sample_rate_hz,
                    row.channels,
                    row.sample_width_bytes,
                )
                if combined_format is None:
                    combined_format = candidate_format
                elif candidate_format != combined_format:
                    raise ValueError(
                        "Combined export requires one identical mono PCM format. "
                        "Choose individual WAV files instead."
                    )
                if row.channels != 1:
                    raise ValueError(
                        "Combined export requires mono PCM. Choose individual WAV files instead."
                    )
                concat_frames = _add(
                    concat_frames, row.source_frame_count, "Combined WAV frame count"
                )
                raven_bytes = _add(raven_bytes, len(raven_line(row, included)), "Raven TSV bytes")
        else:
            rejected += 1

    try:
        next(rows)
    except StopIteration:
        pass
    else:
        raise ValueError("Review export contains candidates outside the finalized inventory.")
    if count != len(finalization.candidates) or count != source.manifest.eligible_candidate_count:
        raise ValueError("Review export candidate inventory is not the finalized eligible set.")
    if included == 0:
        raise ValueError("Review export requires at least one Call or Unreviewed candidate.")

    concat_pcm = 0
    if mode.includes_combined:
        assert combined_format is not None
        concat_pcm = concat_frames * combined_format[1] * combined_format[2]
        if concat_pcm > RIFF_MAX_DATA_BYTES:
            raise ValueError(
                "The combined WAV would be too large. Choose individual WAV files instead."
            )
        combined_size = pcm_wav_bytes(
            concat_frames,
            channels=combined_format[1],
            sample_width_bytes=combined_format[2],
        )
        for path, kind, size in (
            (COMBINED_WAV_NAME, "combined_wav", combined_size),
            (RAVEN_NAME, "raven_tsv", raven_bytes),
        ):
            file_row = ReviewExportFile(REVIEW_EXPORT_FILE_ROW_VERSION, path, kind, "0" * 64, size)
            file_index_size = _add(
                file_index_size,
                len(_canonical_bytes(file_row.to_dict())),
                "Review export file index bytes",
            )
            payload_bytes = _add(payload_bytes, size, "Review export payload bytes")
            payload_files += 1

    manifest = source.manifest
    core = {
        "schema_version": REVIEW_EXPORT_SCHEMA_VERSION,
        "export_id": export_id,
        "created_at": created_at,
        "session_id": finalization.session_id,
        "session_name": finalization.session_name,
        "finalization_digest": finalization.snapshot_digest,
        "source_digest": finalization.source_digest,
        "settings_digest": finalization.settings.settings_digest,
        "result_kind": manifest.result_kind.value,
        "result_id": manifest.result_id,
        "result_digest": manifest.result_digest,
        "publication_digest": manifest.publication_digest,
        "parent_result_id": manifest.parent_result_id,
        "parent_result_digest": manifest.parent_result_digest,
        "mode": mode,
        "format_policy": FORMAT_POLICY,
        "collision_policy": COLLISION_POLICY,
        "destination_parent": str(destination),
        "directory_name": f"biocall-review-export-{export_id[5:17]}",
        "eligibility_scope": (
            "cnn_all" if manifest.result_kind is ReviewResultKind.CNN else "rf_accepted_only"
        ),
        "recording_count": manifest.recording_count,
        "failed_recording_count": manifest.failed_recording_count,
        "eligible_count": count,
        "included_count": included,
        "human_individual_count": individual,
        "human_bulk_count": bulk,
        "model_only_count": model,
        "rejected_count": rejected,
        "rows_sha256": rows_digest.hexdigest(),
        "rows_byte_size": rows_size,
        "payload_file_count": payload_files,
        "payload_bytes": payload_bytes,
        "concat_frame_count": concat_frames,
        "concat_pcm_bytes": concat_pcm,
    }
    digest_values = {
        name: (value.value if isinstance(value, StrEnum) else value) for name, value in core.items()
    }
    plan_digest = _canonical_digest(digest_values)
    provisional = ReviewExportPlan(
        **core,
        plan_digest=plan_digest,
        files_index_byte_size=file_index_size,
        expected_final_bytes=0,
    )
    manifest_size = len(_canonical_bytes(manifest_document(provisional)))
    receipt_size = _receipt_size(provisional, manifest_size)
    total = 0
    for size in (
        payload_bytes,
        rows_size,
        file_index_size,
        manifest_size,
        receipt_size,
    ):
        total = _add(total, size, "Review export final bytes")
    return ReviewExportPlan(
        **core,
        plan_digest=plan_digest,
        files_index_byte_size=file_index_size,
        expected_final_bytes=total,
    )


def iter_plan_rows(
    plan: ReviewExportPlan,
    candidates: Iterable[ReviewExportSourceCandidate],
    source_formats: Mapping[str, ReviewSourceWaveFormat],
) -> Iterator[ReviewExportRow]:
    """Regenerate and validate the frozen stream without materializing all rows."""
    digest = hashlib.sha256()
    size = 0
    count = 0
    for row in _iter_rows(plan.mode, candidates, source_formats):
        encoded = _canonical_bytes(row.to_dict())
        digest.update(encoded)
        size = _add(size, len(encoded), "Review export row bytes")
        count += 1
        yield row
    if (
        count != plan.eligible_count
        or size != plan.rows_byte_size
        or digest.hexdigest() != plan.rows_sha256
    ):
        raise ValueError("Review export row stream no longer matches its frozen plan.")


def canonical_json_bytes(value: object) -> bytes:
    """Public encoder used by the filesystem publisher for exact v2 bytes."""
    return _canonical_bytes(value)


__all__ = [
    "COLLISION_POLICY",
    "COMBINED_WAV_NAME",
    "FILES_NAME",
    "FORMAT_POLICY",
    "MANIFEST_NAME",
    "MAX_COMPACT_DOCUMENT_BYTES",
    "MAX_FILE_INDEX_ROW_BYTES",
    "MAX_JSONL_ROW_BYTES",
    "RAVEN_HEADER",
    "RAVEN_NAME",
    "RECEIPT_NAME",
    "REVIEW_EXPORT_FILE_ROW_VERSION",
    "REVIEW_EXPORT_HISTORY_VERSION",
    "REVIEW_EXPORT_RECEIPT_VERSION",
    "REVIEW_EXPORT_ROW_VERSION",
    "REVIEW_EXPORT_SCHEMA_VERSION",
    "RIFF_MAX_DATA_BYTES",
    "ROWS_NAME",
    "ReviewExportFile",
    "ReviewExportHistoryRecord",
    "ReviewExportMode",
    "ReviewExportPlan",
    "ReviewExportReceipt",
    "ReviewExportRow",
    "ReviewExportSourceCandidate",
    "ReviewSourceWaveFormat",
    "canonical_json_bytes",
    "create_review_export_plan",
    "iter_plan_rows",
    "manifest_document",
    "raven_line",
]
