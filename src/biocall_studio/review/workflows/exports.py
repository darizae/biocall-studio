"""Bounded Review export planning, materialization, verification and publication."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import uuid
import wave
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from biocall_studio.review.domain.exports import (
    COMBINED_WAV_NAME,
    FILES_NAME,
    MANIFEST_NAME,
    MAX_COMPACT_DOCUMENT_BYTES,
    MAX_FILE_INDEX_ROW_BYTES,
    MAX_JSONL_ROW_BYTES,
    RAVEN_HEADER,
    RAVEN_NAME,
    RECEIPT_NAME,
    REVIEW_EXPORT_FILE_ROW_VERSION,
    REVIEW_EXPORT_RECEIPT_VERSION,
    ROWS_NAME,
    ReviewExportFile,
    ReviewExportHistoryRecord,
    ReviewExportMode,
    ReviewExportPlan,
    ReviewExportReceipt,
    ReviewExportRow,
    ReviewSourceWaveFormat,
    canonical_json_bytes,
    create_review_export_plan,
    iter_plan_rows,
    manifest_document,
    raven_line,
)
from biocall_studio.review.domain.intake import ReviewRecording
from biocall_studio.review.persistence.sessions import ReviewSessionStore
from biocall_studio.shared.atomic_directory import (
    atomic_publish_directory_no_replace,
    fsync_directory,
    fsync_directory_tree,
)

_COPY_BYTES = 1024 * 1024


class ReviewExportError(RuntimeError):
    """A Review export could not be safely completed or verified."""


class ReviewExportConflictError(ReviewExportError):
    """The collision-safe publication path already exists."""


class ReviewExportStaleSourceError(ReviewExportError):
    """A source recording no longer matches the finalized Review session."""


class ReviewExportCancelledError(ReviewExportError):
    """Cancellation happened before atomic publication."""


@dataclass(frozen=True, slots=True)
class _SourceIdentity:
    path: Path
    source_format: ReviewSourceWaveFormat
    frame_count: int
    signature: tuple[int, int, int, int, int]
    sha256: str


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _cancelled(cancel_requested: Callable[[], bool] | object | None) -> bool:
    if cancel_requested is None:
        return False
    if callable(cancel_requested):
        return bool(cancel_requested())
    is_set = getattr(cancel_requested, "is_set", None)
    return bool(is_set()) if callable(is_set) else False


def _raise_if_cancelled(cancel_requested: Callable[[], bool] | object | None) -> None:
    if _cancelled(cancel_requested):
        raise ReviewExportCancelledError(
            "Export cancelled. No new output was published; existing files are unchanged."
        )


def _signature(facts: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        facts.st_dev,
        facts.st_ino,
        facts.st_size,
        facts.st_mtime_ns,
        facts.st_ctime_ns,
    )


def _sha256_path(path: Path, cancel_requested: Callable[[], bool] | object | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            _raise_if_cancelled(cancel_requested)
            payload = stream.read(_COPY_BYTES)
            if not payload:
                return digest.hexdigest()
            digest.update(payload)


def _source_path(source_root: Path, recording_key: str) -> Path:
    requested = Path(source_root).expanduser()
    if requested.is_symlink():
        raise ReviewExportStaleSourceError("The recordings folder is unsafe.")
    try:
        root = requested.resolve(strict=True)
    except OSError as exc:
        raise ReviewExportStaleSourceError("The recordings folder is unavailable.") from exc
    if not root.is_dir():
        raise ReviewExportStaleSourceError("The recordings folder is unavailable.")
    relative = PurePosixPath(recording_key)
    if relative.is_absolute() or ".." in relative.parts:
        raise ReviewExportStaleSourceError("A source recording reference is unsafe.")
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ReviewExportStaleSourceError("A source recording path contains a link.")
    try:
        path = current.resolve(strict=True)
        path.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ReviewExportStaleSourceError(
            "A source recording is missing or unsafe. Relink the original recordings."
        ) from exc
    if not path.is_file():
        raise ReviewExportStaleSourceError(
            "A source recording is missing. Relink the original recordings."
        )
    return path


def _inspect_source(
    source_root: Path,
    recording: ReviewRecording,
    cancel_requested: Callable[[], bool] | object | None,
) -> _SourceIdentity:
    path = _source_path(source_root, recording.recording_key)
    try:
        before = path.stat()
        digest = _sha256_path(path, cancel_requested)
        with wave.open(str(path), "rb") as stream:
            source_format = ReviewSourceWaveFormat(
                stream.getframerate(), stream.getnchannels(), stream.getsampwidth()
            )
            if stream.getcomptype() != "NONE":
                raise ReviewExportStaleSourceError(
                    "A source recording is not an uncompressed PCM WAV."
                )
            frame_count = stream.getnframes()
        after = path.stat()
    except ReviewExportError:
        raise
    except (EOFError, OSError, ValueError, wave.Error) as exc:
        raise ReviewExportStaleSourceError("A source recording is not a readable PCM WAV.") from exc
    if (
        _signature(before) != _signature(after)
        or digest != recording.source_sha256
        or source_format.sample_rate_hz != recording.sample_rate_hz
        or source_format.channels != recording.channels
        or frame_count != recording.frame_count
    ):
        raise ReviewExportStaleSourceError(
            "A source recording changed after the Result was created. Restore or relink the "
            "original recording."
        )
    return _SourceIdentity(path, source_format, frame_count, _signature(after), digest)


def _inspect_sources(
    source_root: Path,
    recordings: tuple[ReviewRecording, ...],
    cancel_requested: Callable[[], bool] | object | None = None,
) -> dict[str, _SourceIdentity]:
    identities: dict[str, _SourceIdentity] = {}
    for recording in recordings:
        if recording.failed or recording.eligible_candidate_count == 0:
            continue
        _raise_if_cancelled(cancel_requested)
        identities[recording.recording_ref] = _inspect_source(
            source_root, recording, cancel_requested
        )
    return identities


def _formats(
    identities: Mapping[str, _SourceIdentity],
) -> dict[str, ReviewSourceWaveFormat]:
    return {key: identity.source_format for key, identity in identities.items()}


def _recheck_sources(
    identities: Mapping[str, _SourceIdentity],
    cancel_requested: Callable[[], bool] | object | None,
) -> None:
    for identity in identities.values():
        _raise_if_cancelled(cancel_requested)
        try:
            facts = identity.path.stat()
        except OSError as exc:
            raise ReviewExportStaleSourceError(
                "A source recording disappeared during export."
            ) from exc
        if _signature(facts) != identity.signature:
            raise ReviewExportStaleSourceError(
                "A source recording changed during export. No output was published."
            )
        if _sha256_path(identity.path, cancel_requested) != identity.sha256:
            raise ReviewExportStaleSourceError(
                "A source recording changed during export. No output was published."
            )


def _ensure_target(plan: ReviewExportPlan, source_root: Path) -> Path:
    parent = Path(plan.destination_parent)
    if parent.is_symlink() or not parent.is_dir():
        raise ReviewExportError("Choose an existing, non-symlink export destination folder.")
    resolved_parent = parent.resolve(strict=True)
    if stat.S_IMODE(resolved_parent.stat().st_mode) & 0o222 == 0 or not os.access(
        resolved_parent, os.W_OK | os.X_OK
    ):
        raise ReviewExportError("The export destination is not writable.")
    try:
        resolved_source = Path(source_root).resolve(strict=True)
    except OSError as exc:
        raise ReviewExportStaleSourceError("The recordings folder is unavailable.") from exc
    if resolved_parent == resolved_source or resolved_source in resolved_parent.parents:
        raise ReviewExportError(
            "Choose a destination outside the recordings folder to prevent exported audio "
            "from entering later discovery."
        )
    final = resolved_parent / plan.directory_name
    if final.exists() or final.is_symlink():
        raise ReviewExportConflictError(
            f"The collision-safe export folder already exists: {plan.directory_name}"
        )
    return final


def plan_review_export(
    store: ReviewSessionStore,
    session_id: str,
    *,
    source_root: Path,
    destination_parent: Path,
    mode: ReviewExportMode,
    export_id: str | None = None,
    created_at: str | None = None,
    cancel_requested: Callable[[], bool] | object | None = None,
) -> ReviewExportPlan:
    """Verify finalization/source identity and freeze one compact export plan."""
    _raise_if_cancelled(cancel_requested)
    if not store.verify_finalization(session_id):
        raise ReviewExportError("Only a verified Finalized Review session can be exported.")
    finalization = store.load_finalization(session_id)
    source = store.load_source(session_id)
    identities = _inspect_sources(Path(source_root), source.recordings, cancel_requested)
    plan = create_review_export_plan(
        finalization=finalization,
        source=source,
        candidates=store.iter_finalized_export_candidates(session_id),
        source_formats=_formats(identities),
        mode=ReviewExportMode(mode),
        destination_parent=Path(destination_parent).resolve(strict=True),
        export_id=export_id or f"rexp_{uuid.uuid4().hex}",
        created_at=created_at or _now(),
    )
    _ensure_target(plan, Path(source_root))
    return plan


def _validated_replan(
    plan: ReviewExportPlan,
    store: ReviewSessionStore,
    source_root: Path,
    cancel_requested: Callable[[], bool] | object | None,
) -> tuple[dict[str, _SourceIdentity], dict[str, ReviewSourceWaveFormat]]:
    if not store.verify_finalization(plan.session_id):
        raise ReviewExportError("The Finalized Review session no longer verifies.")
    finalization = store.load_finalization(plan.session_id)
    source = store.load_source(plan.session_id)
    identities = _inspect_sources(source_root, source.recordings, cancel_requested)
    formats = _formats(identities)
    current = create_review_export_plan(
        finalization=finalization,
        source=source,
        candidates=store.iter_finalized_export_candidates(plan.session_id),
        source_formats=formats,
        mode=plan.mode,
        destination_parent=Path(plan.destination_parent),
        export_id=plan.export_id,
        created_at=plan.created_at,
    )
    if current != plan:
        raise ReviewExportError(
            "The finalized session, source, format or destination changed. Plan the export again."
        )
    return identities, formats


def _copy_row_audio(
    reader: wave.Wave_read,
    writers: tuple[wave.Wave_write, ...],
    row: ReviewExportRow,
    cancel_requested: Callable[[], bool] | object | None,
) -> None:
    frame_bytes = row.channels * row.sample_width_bytes
    remaining = row.source_frame_count
    reader.setpos(row.source_start_frame)
    while remaining:
        _raise_if_cancelled(cancel_requested)
        count = min(remaining, max(1, _COPY_BYTES // frame_bytes))
        payload = reader.readframes(count)
        if len(payload) != count * frame_bytes:
            raise ReviewExportStaleSourceError("A source WAV became truncated during export.")
        for writer in writers:
            writer.writeframesraw(payload)
        remaining -= count


def _open_wave_writer(path: Path, row: ReviewExportRow) -> wave.Wave_write:
    stream = wave.open(str(path), "wb")
    stream.setnchannels(row.channels)
    stream.setsampwidth(row.sample_width_bytes)
    stream.setframerate(row.sample_rate_hz)
    return stream


def _file_record(
    root: Path,
    relative_path: str,
    kind: str,
    cancel_requested: Callable[[], bool] | object | None,
) -> ReviewExportFile:
    path = root / relative_path
    return ReviewExportFile(
        REVIEW_EXPORT_FILE_ROW_VERSION,
        relative_path,
        kind,
        _sha256_path(path, cancel_requested),
        path.stat().st_size,
    )


def _write_payload(
    plan: ReviewExportPlan,
    store: ReviewSessionStore,
    stage: Path,
    identities: Mapping[str, _SourceIdentity],
    formats: Mapping[str, ReviewSourceWaveFormat],
    cancel_requested: Callable[[], bool] | object | None,
) -> tuple[str, int, int]:
    rows_digest = hashlib.sha256()
    files_digest = hashlib.sha256()
    rows_size = files_size = file_count = 0
    current_ref: str | None = None
    reader: wave.Wave_read | None = None
    concat_writer: wave.Wave_write | None = None
    selection = 0
    rows_path = stage / ROWS_NAME
    files_path = stage / FILES_NAME
    raven_stream = (stage / RAVEN_NAME).open("wb") if plan.mode.includes_combined else None
    if raven_stream is not None:
        raven_stream.write(RAVEN_HEADER)
    try:
        with rows_path.open("wb") as rows_stream, files_path.open("wb") as files_stream:
            for row in iter_plan_rows(
                plan,
                store.iter_finalized_export_candidates(plan.session_id),
                formats,
            ):
                _raise_if_cancelled(cancel_requested)
                encoded = canonical_json_bytes(row.to_dict())
                rows_stream.write(encoded)
                rows_digest.update(encoded)
                rows_size += len(encoded)
                if not row.included:
                    continue
                identity = identities.get(row.recording_ref)
                if identity is None:
                    raise ReviewExportStaleSourceError("A frozen source identity is unavailable.")
                if current_ref != row.recording_ref:
                    if reader is not None:
                        reader.close()
                    reader = wave.open(str(identity.path), "rb")
                    current_ref = row.recording_ref
                individual_writer: wave.Wave_write | None = None
                writers: list[wave.Wave_write] = []
                if plan.mode.includes_individual:
                    assert row.output_relative_path is not None
                    output = stage / row.output_relative_path
                    output.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                    individual_writer = _open_wave_writer(output, row)
                    writers.append(individual_writer)
                if plan.mode.includes_combined:
                    if concat_writer is None:
                        concat_writer = _open_wave_writer(stage / COMBINED_WAV_NAME, row)
                    writers.append(concat_writer)
                assert reader is not None
                try:
                    _copy_row_audio(reader, tuple(writers), row, cancel_requested)
                finally:
                    if individual_writer is not None:
                        individual_writer.close()
                if plan.mode.includes_individual:
                    assert row.output_relative_path is not None
                    (stage / row.output_relative_path).chmod(0o600)
                    record = _file_record(
                        stage,
                        row.output_relative_path,
                        "individual_wav",
                        cancel_requested,
                    )
                    file_line = canonical_json_bytes(record.to_dict())
                    files_stream.write(file_line)
                    files_digest.update(file_line)
                    files_size += len(file_line)
                    file_count += 1
                if raven_stream is not None:
                    selection += 1
                    raven_stream.write(raven_line(row, selection))
            if reader is not None:
                reader.close()
                reader = None
            if concat_writer is not None:
                concat_writer.close()
                concat_writer = None
                (stage / COMBINED_WAV_NAME).chmod(0o600)
            if raven_stream is not None:
                raven_stream.close()
                raven_stream = None
                (stage / RAVEN_NAME).chmod(0o600)
            if plan.mode.includes_combined:
                for relative_path, kind in (
                    (COMBINED_WAV_NAME, "combined_wav"),
                    (RAVEN_NAME, "raven_tsv"),
                ):
                    record = _file_record(stage, relative_path, kind, cancel_requested)
                    file_line = canonical_json_bytes(record.to_dict())
                    files_stream.write(file_line)
                    files_digest.update(file_line)
                    files_size += len(file_line)
                    file_count += 1
    finally:
        if reader is not None:
            reader.close()
        if concat_writer is not None:
            concat_writer.close()
        if raven_stream is not None:
            raven_stream.close()
    rows_path.chmod(0o600)
    files_path.chmod(0o600)
    if (
        rows_digest.hexdigest() != plan.rows_sha256
        or rows_size != plan.rows_byte_size
        or files_size != plan.files_index_byte_size
        or file_count != plan.payload_file_count
    ):
        raise ReviewExportError("Written export metadata disagrees with its frozen plan.")
    return files_digest.hexdigest(), files_size, file_count


def _read_compact(path: Path) -> object:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_COMPACT_DOCUMENT_BYTES:
        raise ReviewExportError("Review export metadata is missing, unsafe, or too large.")
    try:
        return json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReviewExportError("Review export metadata is corrupt.") from exc


def _iter_jsonl(path: Path, *, row_limit: int) -> Iterator[dict[str, object]]:
    if path.is_symlink() or not path.is_file():
        raise ReviewExportError("Review export streamed metadata is missing or unsafe.")
    try:
        with path.open("rb") as stream:
            for encoded in stream:
                if not encoded.endswith(b"\n") or len(encoded) > row_limit:
                    raise ReviewExportError("Review export metadata row is invalid or too large.")
                raw = json.loads(encoded)
                if not isinstance(raw, dict) or canonical_json_bytes(raw) != encoded:
                    raise ReviewExportError("Review export metadata row is not canonical.")
                yield raw
    except ReviewExportError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReviewExportError("Review export streamed metadata is corrupt.") from exc


def _verify_wave(path: Path, row: ReviewExportRow) -> None:
    try:
        with wave.open(str(path), "rb") as stream:
            if (
                stream.getcomptype() != "NONE"
                or stream.getframerate() != row.sample_rate_hz
                or stream.getnchannels() != row.channels
                or stream.getsampwidth() != row.sample_width_bytes
                or stream.getnframes() != row.source_frame_count
            ):
                raise ReviewExportError(
                    "Published individual WAV does not match its source-frame provenance."
                )
    except ReviewExportError:
        raise
    except (EOFError, OSError, wave.Error) as exc:
        raise ReviewExportError("Published individual WAV is corrupt.") from exc


def _verify_file(
    root: Path,
    record: ReviewExportFile,
    cancel_requested: Callable[[], bool] | object | None,
) -> None:
    path = root / record.relative_path
    if path.is_symlink() or not path.is_file():
        raise ReviewExportError(f"Published export file is missing: {record.relative_path}")
    if (
        path.stat().st_size != record.byte_size
        or _sha256_path(path, cancel_requested) != record.sha256
    ):
        raise ReviewExportError(f"Published export file changed: {record.relative_path}")


def _actual_file_count(root: Path) -> int:
    count = 0
    for directory, names, files in os.walk(root, followlinks=False):
        base = Path(directory)
        for name in names:
            if (base / name).is_symlink():
                raise ReviewExportError("Published export contains an unsafe symlink.")
        for name in files:
            path = base / name
            if path.is_symlink():
                raise ReviewExportError("Published export contains an unsafe symlink.")
            count += 1
    return count


def _verify_review_export_directory(
    root: Path,
    *,
    require_destination: bool,
    cancel_requested: Callable[[], bool] | object | None,
) -> ReviewExportReceipt:
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ReviewExportError("Published Review export folder is missing or unsafe.")
    receipt = ReviewExportReceipt.from_dict(_read_compact(root / RECEIPT_NAME))
    if require_destination and root.resolve(strict=True) != Path(receipt.final_destination).resolve(
        strict=True
    ):
        raise ReviewExportError("Review export receipt destination does not match this folder.")
    manifest_raw = _read_compact(root / MANIFEST_NAME)
    if not isinstance(manifest_raw, dict) or "manifest_digest" not in manifest_raw:
        raise ReviewExportError("Review export manifest is invalid.")
    manifest = dict(manifest_raw)
    manifest_digest = manifest.pop("manifest_digest")
    if (
        not isinstance(manifest_digest, str)
        or hashlib.sha256(canonical_json_bytes(manifest)).hexdigest() != manifest_digest
    ):
        raise ReviewExportError("Review export manifest digest does not match.")
    manifest_path = root / MANIFEST_NAME
    if (
        receipt.manifest_sha256 != _sha256_path(manifest_path, cancel_requested)
        or receipt.manifest_byte_size != manifest_path.stat().st_size
        or manifest.get("manifest_digest") is not None
    ):
        raise ReviewExportError("Review export manifest does not match its receipt.")
    expected_manifest = {
        "schema_version": 2,
        "export_id": receipt.export_id,
        "plan_digest": receipt.plan_digest,
        "session_id": receipt.session_id,
        "finalization_digest": receipt.finalization_digest,
        "mode": receipt.mode.value,
        "rows_file": ROWS_NAME,
        "rows_sha256": receipt.rows_sha256,
        "rows_byte_size": receipt.rows_byte_size,
        "files_index": FILES_NAME,
        "payload_file_count": receipt.payload_file_count,
    }
    for key, value in expected_manifest.items():
        if manifest.get(key) != value:
            raise ReviewExportError("Review export manifest provenance disagrees with its receipt.")

    rows_path = root / ROWS_NAME
    files_path = root / FILES_NAME
    if (
        rows_path.stat().st_size != receipt.rows_byte_size
        or _sha256_path(rows_path, cancel_requested) != receipt.rows_sha256
        or files_path.stat().st_size != receipt.files_byte_size
        or _sha256_path(files_path, cancel_requested) != receipt.files_sha256
    ):
        raise ReviewExportError("Review export streamed metadata does not match its receipt.")
    row_iter = _iter_jsonl(rows_path, row_limit=MAX_JSONL_ROW_BYTES)
    file_iter = _iter_jsonl(files_path, row_limit=MAX_FILE_INDEX_ROW_BYTES)
    raven = (root / RAVEN_NAME).open("rb") if receipt.mode.includes_combined else None
    if raven is not None and raven.readline() != RAVEN_HEADER:
        raven.close()
        raise ReviewExportError("Published Raven table header is invalid.")
    row_count = file_count = included_count = 0
    last_concat_end = 0
    first_combined: ReviewExportRow | None = None
    try:
        for raw in row_iter:
            _raise_if_cancelled(cancel_requested)
            row = ReviewExportRow.from_dict(raw)
            if row.ordinal != row_count:
                raise ReviewExportError("Review export inventory ordering is invalid.")
            row_count += 1
            if not row.included:
                continue
            included_count += 1
            if receipt.mode.includes_individual:
                try:
                    record = ReviewExportFile.from_dict(next(file_iter))
                except StopIteration as exc:
                    raise ReviewExportError("Review export file index ended early.") from exc
                if (
                    record.kind != "individual_wav"
                    or record.relative_path != row.output_relative_path
                ):
                    raise ReviewExportError(
                        "Review export individual file mapping is inconsistent."
                    )
                _verify_file(root, record, cancel_requested)
                _verify_wave(root / record.relative_path, row)
                file_count += 1
            if raven is not None:
                if first_combined is None:
                    first_combined = row
                if row.concat_start_frame != last_concat_end:
                    raise ReviewExportError("Review export concatenated offsets are not gap-free.")
                last_concat_end = row.concat_end_frame or -1
                if raven.readline() != raven_line(row, included_count):
                    raise ReviewExportError(
                        "Published Raven table no longer matches frame provenance."
                    )
        if row_count != receipt.row_count:
            raise ReviewExportError("Review export inventory row count is incomplete.")
        if raven is not None:
            if raven.read(1):
                raise ReviewExportError("Published Raven table contains unexpected rows.")
            raven.close()
            raven = None
            if first_combined is None:
                raise ReviewExportError("Combined Review export has no included rows.")
            for relative_path, kind in (
                (COMBINED_WAV_NAME, "combined_wav"),
                (RAVEN_NAME, "raven_tsv"),
            ):
                try:
                    record = ReviewExportFile.from_dict(next(file_iter))
                except StopIteration as exc:
                    raise ReviewExportError("Review export file index ended early.") from exc
                if record.relative_path != relative_path or record.kind != kind:
                    raise ReviewExportError("Review export combined file mapping is inconsistent.")
                _verify_file(root, record, cancel_requested)
                file_count += 1
            try:
                with wave.open(str(root / COMBINED_WAV_NAME), "rb") as stream:
                    if (
                        stream.getcomptype() != "NONE"
                        or stream.getframerate() != first_combined.sample_rate_hz
                        or stream.getnchannels() != first_combined.channels
                        or stream.getsampwidth() != first_combined.sample_width_bytes
                        or stream.getnframes() != last_concat_end
                    ):
                        raise ReviewExportError(
                            "Published combined WAV no longer matches frame provenance."
                        )
            except ReviewExportError:
                raise
            except (EOFError, OSError, wave.Error) as exc:
                raise ReviewExportError("Published combined WAV is corrupt.") from exc
        try:
            next(file_iter)
        except StopIteration:
            pass
        else:
            raise ReviewExportError("Review export file index contains unexpected rows.")
    finally:
        if raven is not None:
            raven.close()
    if file_count != receipt.payload_file_count:
        raise ReviewExportError("Review export payload file count is incomplete.")
    if _actual_file_count(root) != receipt.payload_file_count + 4:
        raise ReviewExportError("Published Review export file set does not match its receipt.")
    return receipt


def verify_review_export_directory(
    root: Path,
    *,
    cancel_requested: Callable[[], bool] | object | None = None,
) -> ReviewExportReceipt:
    """Stream-check every declared v2 metadata row and scientific output file."""
    return _verify_review_export_directory(
        Path(root), require_destination=True, cancel_requested=cancel_requested
    )


def history_record_for_directory(root: Path) -> ReviewExportHistoryRecord:
    """Rebuild an idempotent private history row from verified public metadata."""
    path = Path(root)
    receipt = verify_review_export_directory(path)
    manifest = _read_compact(path / MANIFEST_NAME)
    if not isinstance(manifest, dict):
        raise ReviewExportError("Review export manifest is invalid.")
    return ReviewExportHistoryRecord.from_manifest_receipt(manifest, receipt)


def verify_export_directory(
    root: Path,
    *,
    cancel_requested: Callable[[], bool] | object | None = None,
):
    """Open Review v2 or unchanged historical Detect v1 exports read-only."""
    path = Path(root)
    if (path / RECEIPT_NAME).is_file():
        return verify_review_export_directory(path, cancel_requested=cancel_requested)
    if (path / "export-receipt.json").is_file():
        from biocall_studio.detect.workflows.exports import verify_export_directory as legacy

        return legacy(path)
    raise ReviewExportError("No supported Review v2 or Detect v1 export receipt was found.")


def publish_review_export(
    plan: ReviewExportPlan,
    store: ReviewSessionStore,
    *,
    source_root: Path,
    cancel_requested: Callable[[], bool] | object | None = None,
    completed_at: str | None = None,
) -> ReviewExportReceipt:
    """Write privately, verify completely, then atomically publish without overwrite."""
    _raise_if_cancelled(cancel_requested)
    final = _ensure_target(plan, Path(source_root))
    identities, formats = _validated_replan(plan, store, Path(source_root), cancel_requested)
    staging = final.parent / f".{plan.directory_name}.staging-{uuid.uuid4().hex}"
    if staging.exists() or staging.is_symlink():
        raise ReviewExportConflictError("A private Review export staging name already exists.")
    published = False
    try:
        staging.mkdir(mode=0o700)
        manifest = manifest_document(plan)
        manifest_bytes = canonical_json_bytes(manifest)
        (staging / MANIFEST_NAME).write_bytes(manifest_bytes)
        (staging / MANIFEST_NAME).chmod(0o600)
        files_digest, files_size, file_count = _write_payload(
            plan,
            store,
            staging,
            identities,
            formats,
            cancel_requested,
        )
        _recheck_sources(identities, cancel_requested)
        finished = completed_at or _now()
        receipt = ReviewExportReceipt.create(
            schema_version=REVIEW_EXPORT_RECEIPT_VERSION,
            export_id=plan.export_id,
            plan_digest=plan.plan_digest,
            session_id=plan.session_id,
            finalization_digest=plan.finalization_digest,
            mode=plan.mode,
            completed_at=finished,
            final_destination=str(final),
            manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
            manifest_byte_size=len(manifest_bytes),
            rows_sha256=plan.rows_sha256,
            rows_byte_size=plan.rows_byte_size,
            row_count=plan.eligible_count,
            files_sha256=files_digest,
            files_byte_size=files_size,
            payload_file_count=file_count,
        )
        receipt_bytes = canonical_json_bytes(receipt.to_dict())
        (staging / RECEIPT_NAME).write_bytes(receipt_bytes)
        (staging / RECEIPT_NAME).chmod(0o600)
        actual_size = sum(path.stat().st_size for path in staging.rglob("*") if path.is_file())
        if actual_size != plan.expected_final_bytes:
            raise ReviewExportError(
                "Published byte arithmetic disagrees with the frozen storage plan."
            )
        _verify_review_export_directory(
            staging, require_destination=False, cancel_requested=cancel_requested
        )
        fsync_directory_tree(staging)
        _raise_if_cancelled(cancel_requested)
        try:
            atomic_publish_directory_no_replace(staging, final)
        except Exception as exc:
            if isinstance(exc, FileExistsError) or "exist" in str(exc).casefold():
                raise ReviewExportConflictError(
                    "The export destination appeared during publication."
                ) from exc
            raise
        published = True
        try:
            fsync_directory(final.parent)
        except OSError:
            pass
        # Publication is already atomic and the staged tree was fully verified. Once visible,
        # cancellation cannot truthfully turn the durable export into a non-success.
        return verify_review_export_directory(final)
    except ReviewExportError:
        raise
    except OSError as exc:
        detail = exc.strerror or type(exc).__name__
        raise ReviewExportError(
            f"Export write failed: {detail}. No partial corpus was published."
        ) from exc
    finally:
        if not published and staging.exists() and not staging.is_symlink():
            shutil.rmtree(staging)


def reconcile_private_staging(destination_parent: Path) -> tuple[str, ...]:
    """Remove only contained incomplete RV-06 staging directories after a restart."""
    parent = Path(destination_parent)
    if parent.is_symlink() or not parent.is_dir():
        raise ReviewExportError("Review export destination is unavailable or unsafe.")
    removed: list[str] = []
    for path in parent.iterdir():
        if not path.name.startswith(".biocall-review-export-") or ".staging-" not in path.name:
            continue
        if path.is_symlink() or not path.is_dir():
            raise ReviewExportError("An incomplete Review export staging path is unsafe.")
        shutil.rmtree(path)
        removed.append(path.name)
    return tuple(sorted(removed))


__all__ = [
    "ReviewExportCancelledError",
    "ReviewExportConflictError",
    "ReviewExportError",
    "ReviewExportStaleSourceError",
    "plan_review_export",
    "publish_review_export",
    "reconcile_private_staging",
    "history_record_for_directory",
    "verify_export_directory",
    "verify_review_export_directory",
]
