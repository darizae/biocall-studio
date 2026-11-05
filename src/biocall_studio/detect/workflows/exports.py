"""Filesystem execution and atomic publication for frozen Detect exports."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import uuid
import wave
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath

from biocall_studio.detect.domain.exports import (
    EXPORT_RECEIPT_SCHEMA_VERSION,
    MAX_DOCUMENT_BYTES,
    ConcatMapping,
    ExportCancelledError,
    ExportCandidate,
    ExportConflictError,
    ExportError,
    ExportMode,
    ExportReceipt,
    ExportSnapshot,
    ExportStaleSourceError,
    FrozenResultSelection,
    PublishedFile,
    RavenRow,
    ResultArtifact,
    SnippetMapping,
    SourceWaveFormat,
    _json_bytes,
    create_export_snapshot,
    render_raven_tsv,
)
from biocall_studio.detect.domain.runs import canonical_digest, utc_now
from biocall_studio.shared.atomic_directory import (
    atomic_publish_directory_no_replace,
    fsync_directory,
    fsync_directory_tree,
)
from biocall_studio.shared.integrity import sha256_file as _sha256_path

_COPY_BYTES = 1024 * 1024


def ensure_publish_target_available(
    snapshot: ExportSnapshot, *, source_root: Path | None = None
) -> Path:
    parent = Path(snapshot.destination_parent)
    if parent.is_symlink() or not parent.is_dir():
        raise ExportError("Choose an existing, non-symlink export destination folder.")
    resolved_parent = parent.resolve(strict=True)
    if stat.S_IMODE(resolved_parent.stat().st_mode) & 0o222 == 0 or not os.access(
        resolved_parent, os.W_OK | os.X_OK
    ):
        raise ExportError("The export destination is not writable.")
    if source_root is not None:
        resolved_source = Path(source_root).resolve(strict=True)
        if resolved_parent == resolved_source or resolved_source in resolved_parent.parents:
            raise ExportError(
                "Choose a destination outside the recordings folder to prevent exported audio "
                "from entering later discovery."
            )
    final = resolved_parent / snapshot.directory_name
    if final.exists() or final.is_symlink():
        raise ExportConflictError(
            f"The collision-safe export folder already exists: {snapshot.directory_name}"
        )
    return final


def _source_path(source_root: Path, recording_key: str) -> Path:
    root = Path(source_root)
    if root.is_symlink() or not root.is_dir():
        raise ExportStaleSourceError("The recordings folder is missing or unsafe.")
    resolved_root = root.resolve(strict=True)
    candidate = resolved_root.joinpath(*PurePosixPath(recording_key).parts)
    current = resolved_root
    for part in PurePosixPath(recording_key).parts:
        current /= part
        if current.is_symlink():
            raise ExportStaleSourceError("A selected source path is now a symlink.")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise ExportStaleSourceError("A selected source recording is missing or unsafe.") from exc
    if not resolved.is_file():
        raise ExportStaleSourceError("A selected source recording is missing or unsafe.")
    return resolved


def _inspect_wave(path: Path) -> tuple[SourceWaveFormat, int]:
    try:
        with wave.open(str(path), "rb") as stream:
            source_format = SourceWaveFormat(
                stream.getframerate(),
                stream.getnchannels(),
                stream.getsampwidth(),
                stream.getcomptype(),
            )
            frame_count = stream.getnframes()
            frame_bytes = source_format.channels * source_format.sample_width_bytes
            chunk_frames = max(1, _COPY_BYTES // frame_bytes)
            total_bytes = 0
            remaining = frame_count
            while remaining:
                count = min(remaining, chunk_frames)
                payload = stream.readframes(count)
                total_bytes += len(payload)
                remaining -= count
            if total_bytes != frame_count * frame_bytes:
                raise ExportStaleSourceError("A selected WAV is truncated.")
    except ExportStaleSourceError:
        raise
    except (OSError, EOFError, wave.Error, ValueError) as exc:
        raise ExportStaleSourceError("A selected source is not a supported PCM WAV.") from exc
    return source_format, frame_count


def _inspect_result_sources(
    result: ResultArtifact,
    selection: FrozenResultSelection,
    source_root: Path,
) -> dict[str, SourceWaveFormat]:
    selected = set(selection.candidate_ids)
    formats: dict[str, SourceWaveFormat] = {}
    for recording in result.recordings:
        if not any(candidate.candidate_id in selected for candidate in recording.candidates):
            continue
        path = _source_path(source_root, recording.recording_key)
        try:
            digest = _sha256_path(path)
        except OSError as exc:
            raise ExportStaleSourceError("A selected source recording cannot be read.") from exc
        source_format, frame_count = _inspect_wave(path)
        if (
            digest != recording.source_sha256
            or source_format.sample_rate_hz != recording.sample_rate_hz
            or source_format.channels != recording.channels
            or frame_count != recording.frame_count
        ):
            raise ExportStaleSourceError(
                f"Source changed after the Result was created: {recording.recording_key}"
            )
        formats[recording.recording_ref] = source_format
    return formats


def freeze_export_snapshot(
    *,
    result: ResultArtifact,
    selection: FrozenResultSelection,
    mode: ExportMode,
    source_root: Path,
    destination_parent: Path,
    export_id: str | None = None,
    created_at: str | None = None,
) -> ExportSnapshot:
    """Inspect current source facts, freeze the request, and validate publication policy."""
    formats = _inspect_result_sources(result, selection, source_root)
    snapshot = create_export_snapshot(
        result=result,
        selection=selection,
        mode=mode,
        destination_parent=Path(destination_parent).resolve(strict=True),
        source_formats=formats,
        export_id=export_id or f"exp_{uuid.uuid4().hex}",
        created_at=created_at or utc_now(),
    )
    ensure_publish_target_available(snapshot, source_root=source_root)
    return snapshot


def _validate_snapshot_sources(snapshot: ExportSnapshot, source_root: Path) -> None:
    checked: set[str] = set()
    for candidate in snapshot.candidates:
        if candidate.recording_ref in checked:
            continue
        path = _source_path(source_root, candidate.recording_key)
        try:
            digest = _sha256_path(path)
        except OSError as exc:
            raise ExportStaleSourceError("A selected source recording cannot be read.") from exc
        source_format, frame_count = _inspect_wave(path)
        if (
            digest != candidate.source_sha256
            or source_format.sample_rate_hz != candidate.sample_rate_hz
            or source_format.channels != candidate.channels
            or source_format.sample_width_bytes != candidate.sample_width_bytes
            or frame_count != candidate.frame_count
        ):
            raise ExportStaleSourceError(
                f"Source changed after export was frozen: {candidate.recording_key}"
            )
        checked.add(candidate.recording_ref)


def _cancelled(cancel_requested: Callable[[], bool] | object | None) -> bool:
    if cancel_requested is None:
        return False
    if callable(cancel_requested):
        return bool(cancel_requested())
    is_set = getattr(cancel_requested, "is_set", None)
    return bool(is_set()) if callable(is_set) else False


def _raise_if_cancelled(cancel_requested: Callable[[], bool] | object | None) -> None:
    if _cancelled(cancel_requested):
        raise ExportCancelledError(
            "Export cancelled. No new output was published; existing files are unchanged."
        )


def _copy_wave_frames(
    reader: wave.Wave_read,
    writer: wave.Wave_write,
    frame_count: int,
    *,
    frame_bytes: int,
    cancel_requested: Callable[[], bool] | object | None,
) -> None:
    remaining = frame_count
    chunk_frames = max(1, _COPY_BYTES // frame_bytes)
    copied = 0
    while remaining:
        _raise_if_cancelled(cancel_requested)
        count = min(remaining, chunk_frames)
        payload = reader.readframes(count)
        if len(payload) != count * frame_bytes:
            raise ExportStaleSourceError("A selected WAV became truncated during export.")
        writer.writeframesraw(payload)
        copied += len(payload)
        remaining -= count
    if copied != frame_count * frame_bytes:
        raise ExportError("PCM byte count disagrees with the frozen frame mapping.")


def _write_wave_segment(
    source: Path,
    destination: Path,
    candidate: ExportCandidate,
    cancel_requested: Callable[[], bool] | object | None,
) -> None:
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with wave.open(str(source), "rb") as reader, wave.open(str(destination), "wb") as writer:
        writer.setnchannels(candidate.channels)
        writer.setsampwidth(candidate.sample_width_bytes)
        writer.setframerate(candidate.sample_rate_hz)
        reader.setpos(candidate.source_start_frame)
        _copy_wave_frames(
            reader,
            writer,
            candidate.output_frame_count,
            frame_bytes=candidate.channels * candidate.sample_width_bytes,
            cancel_requested=cancel_requested,
        )
    destination.chmod(0o600)


def _write_concat(
    source_root: Path,
    destination: Path,
    snapshot: ExportSnapshot,
    cancel_requested: Callable[[], bool] | object | None,
) -> None:
    first = snapshot.candidates[0]
    with wave.open(str(destination), "wb") as writer:
        writer.setnchannels(first.channels)
        writer.setsampwidth(first.sample_width_bytes)
        writer.setframerate(first.sample_rate_hz)
        for candidate in snapshot.candidates:
            _raise_if_cancelled(cancel_requested)
            source = _source_path(source_root, candidate.recording_key)
            with wave.open(str(source), "rb") as reader:
                reader.setpos(candidate.source_start_frame)
                _copy_wave_frames(
                    reader,
                    writer,
                    candidate.output_frame_count,
                    frame_bytes=candidate.channels * candidate.sample_width_bytes,
                    cancel_requested=cancel_requested,
                )
    destination.chmod(0o600)


def _pcm_digest(path: Path) -> tuple[str, int, SourceWaveFormat]:
    digest = hashlib.sha256()
    frames = 0
    with wave.open(str(path), "rb") as stream:
        source_format = SourceWaveFormat(
            stream.getframerate(),
            stream.getnchannels(),
            stream.getsampwidth(),
            stream.getcomptype(),
        )
        frame_bytes = source_format.channels * source_format.sample_width_bytes
        chunk_frames = max(1, _COPY_BYTES // frame_bytes)
        while frames < stream.getnframes():
            count = min(chunk_frames, stream.getnframes() - frames)
            payload = stream.readframes(count)
            if len(payload) != count * frame_bytes:
                raise ExportError("Published WAV PCM is truncated.")
            digest.update(payload)
            frames += count
    return digest.hexdigest(), frames, source_format


def _published_files(root: Path, kinds: Mapping[str, str]) -> tuple[PublishedFile, ...]:
    files = []
    for relative_path, kind in sorted(kinds.items()):
        path = root / relative_path
        files.append(PublishedFile(relative_path, kind, _sha256_path(path), path.stat().st_size))
    return tuple(files)


def _build_receipt(
    snapshot: ExportSnapshot,
    stage: Path,
    final: Path,
    *,
    completed_at: str,
) -> ExportReceipt:
    kinds = {"export-snapshot.json": "snapshot"}
    snippets = []
    if snapshot.mode.includes_snippets:
        for candidate in snapshot.candidates:
            output = stage / candidate.snippet_relative_path
            pcm_digest, frames, source_format = _pcm_digest(output)
            if (
                frames != candidate.output_frame_count
                or source_format.sample_rate_hz != candidate.sample_rate_hz
                or source_format.channels != candidate.channels
                or source_format.sample_width_bytes != candidate.sample_width_bytes
            ):
                raise ExportError("A snippet WAV does not match its frozen source mapping.")
            kinds[candidate.snippet_relative_path] = "snippet_wav"
            snippets.append(
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
                    pcm_digest,
                )
            )
    concat_mappings = ()
    raven_rows = ()
    if snapshot.mode.includes_concat:
        _pcm_digest(stage / "corpus.wav")
        kinds["corpus.wav"] = "concatenated_wav"
        kinds["corpus.Table.1.selections.txt"] = "raven_tsv"
        _tsv, raven_rows = render_raven_tsv(snapshot)
        concat_mappings = tuple(
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
        "completed_at": completed_at,
        "final_destination": str(final),
        "files": [item.to_dict() for item in _published_files(stage, kinds)],
        "snippets": [item.to_dict() for item in snippets],
        "concat_mappings": [item.to_dict() for item in concat_mappings],
        "raven_rows": [item.to_dict() for item in raven_rows],
    }
    return ExportReceipt(
        **{
            **unsigned,
            "receipt_digest": canonical_digest(unsigned),
            "mode": snapshot.mode,
            "files": tuple(PublishedFile.from_dict(item) for item in unsigned["files"]),
            "snippets": tuple(SnippetMapping.from_dict(item) for item in unsigned["snippets"]),
            "concat_mappings": tuple(
                ConcatMapping.from_dict(item) for item in unsigned["concat_mappings"]
            ),
            "raven_rows": tuple(RavenRow.from_dict(item) for item in unsigned["raven_rows"]),
        }
    )


def _read_json(path: Path) -> object:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ExportError("Export metadata is missing, unsafe, or too large.")
    try:
        return json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExportError("Export metadata is corrupt.") from exc


def _verify_export_directory(root: Path, *, require_destination: bool) -> ExportReceipt:
    if root.is_symlink() or not root.is_dir():
        raise ExportError("Published export folder is missing or unsafe.")
    receipt = ExportReceipt.from_dict(_read_json(root / "export-receipt.json"))
    if require_destination and root.resolve(strict=True) != Path(receipt.final_destination).resolve(
        strict=True
    ):
        raise ExportError("ExportReceipt destination does not match the opened folder.")
    expected = {item.relative_path for item in receipt.files} | {"export-receipt.json"}
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ExportError("Published export contains an unsafe symlink.")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    if actual != expected:
        raise ExportError("Published export file set does not match its receipt.")
    for item in receipt.files:
        path = root / item.relative_path
        if path.stat().st_size != item.byte_size or _sha256_path(path) != item.sha256:
            raise ExportError(f"Published export file changed: {item.relative_path}")
    snapshot = ExportSnapshot.from_dict(_read_json(root / "export-snapshot.json"))
    if snapshot.snapshot_digest != receipt.snapshot_digest:
        raise ExportError("ExportSnapshot and ExportReceipt digests disagree.")
    if (
        receipt.export_id != snapshot.export_id
        or receipt.result_id != snapshot.result_id
        or receipt.result_digest != snapshot.result_digest
        or receipt.parent_result_id != snapshot.parent_result_id
        or receipt.parent_result_digest != snapshot.parent_result_digest
        or receipt.mode is not snapshot.mode
        or receipt.format_policy != snapshot.format_policy
        or receipt.collision_policy != snapshot.collision_policy
    ):
        raise ExportError("ExportReceipt provenance disagrees with its frozen snapshot.")
    expected_kinds = {"export-snapshot.json": "snapshot"}
    if snapshot.mode.includes_snippets:
        expected_kinds.update(
            {candidate.snippet_relative_path: "snippet_wav" for candidate in snapshot.candidates}
        )
    if snapshot.mode.includes_concat:
        expected_kinds.update(
            {
                "corpus.wav": "concatenated_wav",
                "corpus.Table.1.selections.txt": "raven_tsv",
            }
        )
    if {item.relative_path: item.kind for item in receipt.files} != expected_kinds:
        raise ExportError("ExportReceipt payload kinds disagree with its frozen snapshot.")
    if receipt.mode.includes_snippets:
        if tuple(mapping.candidate_id for mapping in receipt.snippets) != tuple(
            candidate.candidate_id for candidate in snapshot.candidates
        ):
            raise ExportError("Snippet receipt ordering disagrees with the frozen selection.")
        for mapping, candidate in zip(receipt.snippets, snapshot.candidates, strict=True):
            if (
                mapping.recording_key != candidate.recording_key
                or mapping.source_sha256 != candidate.source_sha256
                or mapping.source_start_frame != candidate.source_start_frame
                or mapping.source_end_frame != candidate.source_end_frame
                or mapping.source_start_time_ns != candidate.source_start_time_ns
                or mapping.source_end_time_ns != candidate.source_end_time_ns
                or mapping.output_relative_path != candidate.snippet_relative_path
                or mapping.output_start_frame != 0
                or mapping.output_end_frame != candidate.output_frame_count
                or mapping.sample_rate_hz != candidate.sample_rate_hz
                or mapping.channels != candidate.channels
                or mapping.sample_width_bytes != candidate.sample_width_bytes
            ):
                raise ExportError("Snippet receipt mapping disagrees with its snapshot.")
            pcm_digest, frames, source_format = _pcm_digest(root / mapping.output_relative_path)
            if (
                pcm_digest != mapping.pcm_sha256
                or frames != mapping.output_end_frame
                or source_format.sample_rate_hz != mapping.sample_rate_hz
                or source_format.channels != mapping.channels
                or source_format.sample_width_bytes != mapping.sample_width_bytes
            ):
                raise ExportError("Published snippet no longer matches its receipt.")
    if receipt.mode.includes_concat:
        if tuple(mapping.candidate_id for mapping in receipt.concat_mappings) != tuple(
            candidate.candidate_id for candidate in snapshot.candidates
        ):
            raise ExportError("Concatenation receipt ordering disagrees with the frozen selection.")
        for index, (mapping, candidate) in enumerate(
            zip(receipt.concat_mappings, snapshot.candidates, strict=True), 1
        ):
            if (
                mapping.recording_key != candidate.recording_key
                or mapping.source_sha256 != candidate.source_sha256
                or mapping.source_start_frame != candidate.source_start_frame
                or mapping.source_end_frame != candidate.source_end_frame
                or mapping.source_start_time_ns != candidate.source_start_time_ns
                or mapping.source_end_time_ns != candidate.source_end_time_ns
                or mapping.concat_start_frame != candidate.concat_start_frame
                or mapping.concat_end_frame != candidate.concat_end_frame
                or mapping.raven_selection != index
            ):
                raise ExportError("Concatenation receipt mapping disagrees with its snapshot.")
        _digest_value, frames, source_format = _pcm_digest(root / "corpus.wav")
        if (
            frames != (receipt.concat_mappings[-1].concat_end_frame)
            or source_format.sample_rate_hz != snapshot.candidates[0].sample_rate_hz
        ):
            raise ExportError("Published concatenated WAV no longer matches its receipt.")
        expected_tsv, expected_rows = render_raven_tsv(snapshot)
        if (
            root / "corpus.Table.1.selections.txt"
        ).read_bytes() != expected_tsv or expected_rows != receipt.raven_rows:
            raise ExportError("Published Raven table no longer matches frame provenance.")
    return receipt


def verify_export_directory(root: Path) -> ExportReceipt:
    """Reopen every file, checksum, WAV mapping and Raven row without rewriting output."""
    return _verify_export_directory(Path(root), require_destination=True)


def publish_export(
    snapshot: ExportSnapshot,
    *,
    source_root: Path,
    cancel_requested: Callable[[], bool] | object | None = None,
    completed_at: str | None = None,
) -> ExportReceipt:
    """Materialize privately, verify completely, then atomically publish one directory."""
    _raise_if_cancelled(cancel_requested)
    final = ensure_publish_target_available(snapshot, source_root=source_root)
    _validate_snapshot_sources(snapshot, source_root)
    _raise_if_cancelled(cancel_requested)
    staging = final.parent / f".{snapshot.directory_name}.staging-{uuid.uuid4().hex}"
    if staging.exists() or staging.is_symlink():
        raise ExportConflictError("A private export staging name already exists.")
    published = False
    try:
        staging.mkdir(mode=0o700)
        _raise_if_cancelled(cancel_requested)
        (staging / "export-snapshot.json").write_bytes(_json_bytes(snapshot.to_dict()))
        (staging / "export-snapshot.json").chmod(0o600)
        _raise_if_cancelled(cancel_requested)
        if snapshot.mode.includes_snippets:
            for candidate in snapshot.candidates:
                _write_wave_segment(
                    _source_path(source_root, candidate.recording_key),
                    staging / candidate.snippet_relative_path,
                    candidate,
                    cancel_requested,
                )
        if snapshot.mode.includes_concat:
            _write_concat(Path(source_root), staging / "corpus.wav", snapshot, cancel_requested)
            tsv, _rows = render_raven_tsv(snapshot)
            (staging / "corpus.Table.1.selections.txt").write_bytes(tsv)
            (staging / "corpus.Table.1.selections.txt").chmod(0o600)
        _raise_if_cancelled(cancel_requested)
        _validate_snapshot_sources(snapshot, source_root)
        _raise_if_cancelled(cancel_requested)
        receipt = _build_receipt(
            snapshot,
            staging,
            final,
            completed_at=completed_at or utc_now(),
        )
        (staging / "export-receipt.json").write_bytes(_json_bytes(receipt.to_dict()))
        (staging / "export-receipt.json").chmod(0o600)
        _verify_export_directory(staging, require_destination=False)
        fsync_directory_tree(staging)
        _raise_if_cancelled(cancel_requested)
        try:
            atomic_publish_directory_no_replace(staging, final)
        except FileExistsError as exc:
            raise ExportConflictError(
                "The export destination appeared during publication."
            ) from exc
        published = True
        try:
            fsync_directory(final.parent)
        except OSError:
            # The self-contained directory is already atomically visible and fully verified.
            pass
        return verify_export_directory(final)
    except (ExportError, ExportStaleSourceError, ExportCancelledError, ExportConflictError):
        raise
    except OSError as exc:
        detail = exc.strerror or str(exc)
        raise ExportError(
            f"Export write failed: {detail}. No partial corpus was published."
        ) from exc
    finally:
        if not published and staging.exists() and not staging.is_symlink():
            shutil.rmtree(staging)


__all__ = [
    "ensure_publish_target_available",
    "freeze_export_snapshot",
    "publish_export",
    "verify_export_directory",
]
