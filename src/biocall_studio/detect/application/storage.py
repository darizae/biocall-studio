"""Detect-owned metadata Result and corpus-export storage planners."""

from __future__ import annotations

import json
import wave
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from biocall_studio.detect.domain.exports import (
    EXPORT_RECEIPT_SCHEMA_VERSION,
    ConcatMapping,
    ExportMode,
    ExportReceipt,
    ExportSnapshot,
    PublishedFile,
    RavenRow,
    SnippetMapping,
    SourceWaveFormat,
    create_export_snapshot,
    render_raven_tsv,
)
from biocall_studio.detect.domain.result_views import FrozenResultSelection
from biocall_studio.detect.domain.rf_refinement import ResultArtifact
from biocall_studio.detect.domain.runs import canonical_digest
from biocall_studio.shared.storage import (
    MIB,
    ByteEstimate,
    EstimateConfidence,
    OperationSizePlan,
    pcm_wav_bytes,
    storage_input_digest,
)

_RESULT_DOCUMENT_LIMIT = 64 * MIB
_ZERO_DIGEST = "0" * 64


@dataclass(frozen=True, slots=True)
class DetectionRecordingFacts:
    recording_ref: str
    sample_rate_hz: int
    frame_count: int


def estimate_detection_metadata(
    recordings: Iterable[DetectionRecordingFacts],
    *,
    model_sample_rate_hz: int,
    window_samples: int,
    hop_samples: int,
) -> tuple[OperationSizePlan, int]:
    """Bound first-pass Result JSON using the verified toolbox window policy."""
    rows = tuple(recordings)
    if (
        not rows
        or type(model_sample_rate_hz) is not int
        or model_sample_rate_hz <= 0
        or type(window_samples) is not int
        or window_samples <= 0
        or type(hop_samples) is not int
        or not 0 < hop_samples <= window_samples
    ):
        return (
            OperationSizePlan(
                ByteEstimate.unavailable(),
                None,
                EstimateConfidence.INSUFFICIENT_EVIDENCE,
                "Validated recording frames and CNN window settings are required.",
                "Can't estimate the output size yet. Check the selected files and settings.",
            ),
            0,
        )
    windows = 0
    for row in rows:
        if row.sample_rate_hz <= 0 or row.frame_count <= 0:
            raise ValueError("Detection recording facts must be positive.")
        resampled_frames = (
            row.frame_count * model_sample_rate_hz + row.sample_rate_hz // 2
        ) // row.sample_rate_hz
        remaining = max(resampled_frames - window_samples, 0)
        windows += 1 + (remaining + hop_samples - 1) // hop_samples
    # Candidate survival and merging are data-dependent. The current publisher
    # refuses result.json above 64 MiB, which is the only universal proven cap.
    low = min(_RESULT_DOCUMENT_LIMIT - 1, 4 * 1_024 + len(rows) * 1_024)
    high = _RESULT_DOCUMENT_LIMIT + 1 * MIB
    return (
        OperationSizePlan(
            ByteEstimate.range(low, high),
            high + 8 * MIB,
            EstimateConfidence.ARITHMETIC,
            (
                f"{windows} worst-case CNN windows and the current 64 MB Result document limit, "
                "plus bounded publication, Run, request, and diagnostic metadata."
            ),
            "Output size varies with the recording and settings.",
        ),
        windows,
    )


def estimate_refinement_metadata(candidate_count: int) -> OperationSizePlan:
    if type(candidate_count) is not int or candidate_count <= 0:
        return OperationSizePlan(
            ByteEstimate.unavailable(),
            None,
            EstimateConfidence.INSUFFICIENT_EVIDENCE,
            "A nonempty parent Result is required for RF output sizing.",
            "Can't estimate the output size yet. Check the selected files and settings.",
        )
    low = min(_RESULT_DOCUMENT_LIMIT - 1, 4 * 1_024 + candidate_count * 256)
    high = min(_RESULT_DOCUMENT_LIMIT + 1 * MIB, 16 * 1_024 + candidate_count * 2_048)
    if high <= low:
        high = min(_RESULT_DOCUMENT_LIMIT + 1 * MIB, low + 1)
    return OperationSizePlan(
        ByteEstimate.range(low, high),
        high + 8 * MIB,
        EstimateConfidence.ARITHMETIC,
        (
            "Parent candidate count with bounded RF decision rows, publication identity, Run, "
            "request, and diagnostic metadata."
        ),
        "Output size varies with the Result and Model structure.",
    )


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _planned_export_receipt(
    snapshot: ExportSnapshot,
    files: tuple[PublishedFile, ...],
    rows: tuple[RavenRow, ...],
) -> ExportReceipt:
    snippets = (
        tuple(
            SnippetMapping(
                candidate.candidate_id,
                candidate.recording_key,
                candidate.source_sha256,
                candidate.source_start_frame,
                candidate.source_end_frame,
                candidate.source_start_time_ns,
                candidate.source_end_time_ns,
                candidate.snippet_relative_path,
                0,
                candidate.output_frame_count,
                candidate.sample_rate_hz,
                candidate.channels,
                candidate.sample_width_bytes,
                _ZERO_DIGEST,
            )
            for candidate in snapshot.candidates
        )
        if snapshot.mode.includes_snippets
        else ()
    )
    concat = (
        tuple(
            ConcatMapping(
                candidate.candidate_id,
                candidate.recording_key,
                candidate.source_sha256,
                candidate.source_start_frame,
                candidate.source_end_frame,
                candidate.source_start_time_ns,
                candidate.source_end_time_ns,
                candidate.concat_start_frame or 0,
                candidate.concat_end_frame or 0,
                index,
            )
            for index, candidate in enumerate(snapshot.candidates, 1)
        )
        if snapshot.mode.includes_concat
        else ()
    )
    unsigned = {
        "schema_version": EXPORT_RECEIPT_SCHEMA_VERSION,
        "export_id": snapshot.export_id,
        "snapshot_digest": snapshot.snapshot_digest,
        "result_id": snapshot.result_id,
        "result_digest": snapshot.result_digest,
        "parent_result_id": snapshot.parent_result_id,
        "parent_result_digest": snapshot.parent_result_digest,
        "mode": snapshot.mode.value,
        "format_policy": snapshot.format_policy,
        "collision_policy": snapshot.collision_policy,
        "completed_at": snapshot.created_at,
        "final_destination": str(Path(snapshot.destination_parent) / snapshot.directory_name),
        "files": [item.to_dict() for item in files],
        "snippets": [item.to_dict() for item in snippets],
        "concat_mappings": [item.to_dict() for item in concat],
        "raven_rows": [item.to_dict() for item in rows],
    }
    return ExportReceipt(
        **{
            **unsigned,
            "receipt_digest": canonical_digest(unsigned),
            "mode": snapshot.mode,
            "files": files,
            "snippets": snippets,
            "concat_mappings": concat,
            "raven_rows": rows,
        }
    )


def estimate_export_artifacts(snapshot: ExportSnapshot) -> OperationSizePlan:
    """Calculate every destination file exactly from the frozen frame mapping."""
    snapshot_size = len(_json_bytes(snapshot.to_dict()))
    sizes: dict[str, tuple[str, int]] = {"export-snapshot.json": ("snapshot", snapshot_size)}
    if snapshot.mode.includes_snippets:
        for candidate in snapshot.candidates:
            sizes[candidate.snippet_relative_path] = (
                "snippet_wav",
                pcm_wav_bytes(
                    candidate.output_frame_count,
                    channels=candidate.channels,
                    sample_width_bytes=candidate.sample_width_bytes,
                ),
            )
    rows: tuple[RavenRow, ...] = ()
    if snapshot.mode.includes_concat:
        total_frames = sum(candidate.output_frame_count for candidate in snapshot.candidates)
        first = snapshot.candidates[0]
        sizes["corpus.wav"] = (
            "concatenated_wav",
            pcm_wav_bytes(
                total_frames,
                channels=first.channels,
                sample_width_bytes=first.sample_width_bytes,
            ),
        )
        tsv, rows = render_raven_tsv(snapshot)
        sizes["corpus.Table.1.selections.txt"] = ("raven_tsv", len(tsv))
    files = tuple(
        PublishedFile(path, kind, _ZERO_DIGEST, size)
        for path, (kind, size) in sorted(sizes.items())
    )
    receipt = _planned_export_receipt(snapshot, files, rows)
    total = sum(size for _kind, size in sizes.values()) + len(_json_bytes(receipt.to_dict()))
    return OperationSizePlan(
        ByteEstimate.exact(total),
        total,
        EstimateConfidence.ARITHMETIC,
        (
            "Frozen PCM frame counts, standard WAV headers, exact snapshot/Raven rows, and the "
            "fixed-length digest receipt."
        ),
    )


def export_input_digest(snapshot: ExportSnapshot) -> str:
    return storage_input_digest(
        {
            "operation": "detect.export",
            "snapshot_digest": snapshot.snapshot_digest,
            "destination_parent": snapshot.destination_parent,
            "mode": snapshot.mode.value,
        }
    )


def preview_export_snapshot(
    *,
    result: ResultArtifact,
    selection: FrozenResultSelection,
    mode: ExportMode,
    source_root: Path,
    destination_parent: Path,
) -> ExportSnapshot:
    """Read bounded WAV headers for UI sizing; publication still revalidates full sources."""
    root = Path(source_root).resolve(strict=True)
    destination = Path(destination_parent).resolve(strict=True)
    selected = set(selection.candidate_ids)
    formats: dict[str, SourceWaveFormat] = {}
    for recording in result.recordings:
        if not any(candidate.candidate_id in selected for candidate in recording.candidates):
            continue
        candidate = root.joinpath(*PurePosixPath(recording.recording_key).parts)
        if candidate.is_symlink():
            raise ValueError("A selected source recording is missing or unsafe.")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise ValueError("A selected source recording is missing or unsafe.")
        try:
            with wave.open(str(resolved), "rb") as stream:
                source_format = SourceWaveFormat(
                    stream.getframerate(),
                    stream.getnchannels(),
                    stream.getsampwidth(),
                    stream.getcomptype(),
                )
                frame_count = stream.getnframes()
        except (OSError, EOFError, wave.Error, ValueError) as exc:
            raise ValueError("A selected source is not a supported PCM WAV.") from exc
        if (
            source_format.sample_rate_hz != recording.sample_rate_hz
            or source_format.channels != recording.channels
            or frame_count != recording.frame_count
        ):
            raise ValueError("A selected source recording changed. Check recordings again.")
        formats[recording.recording_ref] = source_format
    token = canonical_digest(
        {
            "result_digest": result.result_digest,
            "candidate_ids": list(selection.candidate_ids),
            "mode": ExportMode(mode).value,
            "destination": str(destination),
        }
    )[:32]
    return create_export_snapshot(
        result=result,
        selection=selection,
        mode=ExportMode(mode),
        destination_parent=destination,
        source_formats=formats,
        export_id=f"exp_{token}",
        created_at="2000-01-01T00:00:00.000Z",
    )


__all__ = [
    "DetectionRecordingFacts",
    "estimate_detection_metadata",
    "estimate_export_artifacts",
    "estimate_refinement_metadata",
    "export_input_digest",
    "preview_export_snapshot",
]
