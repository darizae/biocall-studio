"""Bounded, privacy-normalized local diagnostics with no Qt dependencies."""

from __future__ import annotations

import json
import logging
import os
import re
import stat
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO
from zipfile import ZIP_DEFLATED, ZipFile

from biocall_studio.shared.paths import validate_relative_path

DIAGNOSTIC_SCHEMA_VERSION = 1
APP_LOG_MAX_BYTES = 5 * 1024 * 1024
APP_LOG_BACKUP_COUNT = 3
APP_LOG_RETENTION_DAYS = 14
APP_LOG_TOTAL_MAX_BYTES = 50 * 1024 * 1024
WORKER_LOG_MAX_BYTES = 5 * 1024 * 1024
WORKER_LOG_BACKUP_COUNT = 3
MAX_RECORD_BYTES = 16 * 1024
MAX_MESSAGE_CHARACTERS = 2_000
MAX_EXPORT_BYTES = 20 * 1024 * 1024

_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_STRING_CONTEXT = frozenset(
    {
        "run_id",
        "request_id",
        "operation",
        "run_kind",
        "training_family",
        "stage",
        "status",
        "exception_type",
        "error_id",
        "version",
        "build_id",
        "python_version",
        "qt_version",
        "toolbox_version",
        "alp_ui_version",
    }
)
_NUMBER_CONTEXT = frozenset({"duration_ms", "count"})
_KNOWN_FIELDS = frozenset(
    {
        "schema_version",
        "timestamp_utc",
        "level",
        "component",
        "event",
        "message",
        "session_id",
        "pid",
        *_STRING_CONTEXT,
        *_NUMBER_CONTEXT,
    }
)
_NAME = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_EVENT = re.compile(r"^[a-z][a-z0-9_]{0,95}$")
_APP_LOG_NAME = re.compile(r"^session-\d{4}-\d{2}-\d{2}-[A-Za-z0-9_-]{4,64}\.jsonl(?:\.[1-3])?$")
_WORKER_LOG_NAME = re.compile(r"^worker\.jsonl(?:\.[1-3])?$")
_SECRET = re.compile(
    r"(?i)\b(?:api[_-]?(?:key|token)|access[_-]?token|token|password|passwd|secret|credential)"
    r"\s*[:=]\s*[^\s,;]+"
)
_WINDOWS_PATH = re.compile(r"(?i)(?<![A-Za-z0-9])(?:[A-Z]:[\\/](?:[^\s<>\"']+))")
_UNC_PATH = re.compile(r"(?<![A-Za-z0-9])(?:\\\\[^\s<>\"']+)")
_HOME_PATH = re.compile(r"(?<![A-Za-z0-9])(?:~[\\/][^\s<>\"']+)")
_POSIX_PATH = re.compile(r"(?<![A-Za-z0-9])/(?:[^\s<>\"']+)")
_PORTABLE_PATH = re.compile(r"(?i)(?<![A-Za-z0-9_.-])(?:[A-Za-z0-9_.-]+[\\/])+[A-Za-z0-9_.-]+")
_WAV_NAME = re.compile(r"(?i)(?<![A-Za-z0-9_.-])[A-Za-z0-9_.-]+\.wav\b")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def _utc_timestamp(moment: datetime | None = None) -> str:
    value = moment or datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sanitize_diagnostic_text(value: object, *, limit: int = MAX_MESSAGE_CHARACTERS) -> str:
    """Return one bounded line that cannot retain user paths or common credentials."""
    text = str(value)
    text = _SECRET.sub("<redacted credential>", text)
    for pattern in (_WINDOWS_PATH, _UNC_PATH, _HOME_PATH, _POSIX_PATH, _PORTABLE_PATH):
        text = pattern.sub("<path>", text)
    text = _WAV_NAME.sub("<recording.wav>", text)
    text = _CONTROL.sub(" ", text)
    text = " ".join(text.split())
    if len(text) > limit:
        suffix = "… <truncated>"
        text = text[: max(0, limit - len(suffix))].rstrip() + suffix
    return text or "Diagnostic event"


def _safe_identifier(value: object, *, limit: int = 160) -> str | None:
    if not isinstance(value, str) or not value or len(value) > limit:
        return None
    if any(ord(character) < 32 for character in value):
        return None
    if "/" in value or "\\" in value or value in {".", ".."}:
        return None
    return sanitize_diagnostic_text(value, limit=limit)


def encode_diagnostic_record(
    *,
    component: str,
    event: str,
    message: object,
    level: str,
    session_id: str | None = None,
    context: Mapping[str, object] | None = None,
    timestamp: datetime | None = None,
    pid: int | None = None,
) -> bytes:
    """Encode one allowlisted schema-v1 record as newline-terminated UTF-8 JSON."""
    normalized_level = str(level).upper()
    if normalized_level not in _LEVELS:
        raise ValueError("Unsupported diagnostic level.")
    if not isinstance(component, str) or not _NAME.fullmatch(component):
        raise ValueError("Diagnostic component is invalid.")
    if not isinstance(event, str) or not _EVENT.fullmatch(event):
        raise ValueError("Diagnostic event is invalid.")
    record: dict[str, object] = {
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "timestamp_utc": _utc_timestamp(timestamp),
        "level": normalized_level,
        "component": component,
        "event": event,
        "message": sanitize_diagnostic_text(message),
    }
    safe_session = _safe_identifier(session_id)
    if safe_session is not None:
        record["session_id"] = safe_session
    record["pid"] = os.getpid() if pid is None else int(pid)
    for key, value in (context or {}).items():
        if key in _STRING_CONTEXT:
            normalized = _safe_identifier(value)
            if normalized is not None:
                record[key] = normalized
        elif (
            key in _NUMBER_CONTEXT
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
        ):
            record[key] = value
    encoded = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(encoded) > MAX_RECORD_BYTES:
        record["message"] = "Diagnostic record exceeded its size limit"
        for key in tuple(record):
            if key in _STRING_CONTEXT | _NUMBER_CONTEXT:
                record.pop(key)
        encoded = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    return encoded


def _fallback_record(payload: bytes, max_bytes: int) -> bytes:
    try:
        raw = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raw = {}
    record = {
        "schema_version": 1,
        "timestamp_utc": raw.get("timestamp_utc", _utc_timestamp()),
        "level": raw.get("level", "WARNING"),
        "component": raw.get("component", "biocall_studio.train.diagnostics"),
        "event": raw.get("event", "record_truncated"),
        "message": "truncated",
        "pid": raw.get("pid", os.getpid()),
    }
    if isinstance(raw.get("session_id"), str):
        record["session_id"] = raw["session_id"]
    encoded = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(encoded) <= max_bytes:
        return encoded
    record.pop("session_id", None)
    record["component"] = "biocall_studio.train.log"
    record["event"] = "truncated"
    encoded = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
    return encoded if len(encoded) <= max_bytes else b""


class BoundedJsonlSink:
    """A single-process JSONL writer with owned, non-symlink rotation segments."""

    def __init__(self, path: Path, *, max_bytes: int, backup_count: int):
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.failed = False
        self.failure_count = 0
        self.failure_message = ""
        if max_bytes <= 0 or backup_count < 0:
            raise ValueError("Diagnostic sink budgets must be positive and bounded.")

    def write(self, payload: bytes) -> None:
        if self.failed:
            return
        try:
            fitted = (
                payload
                if len(payload) <= self.max_bytes
                else _fallback_record(payload, self.max_bytes)
            )
            if not fitted:
                raise OSError("Diagnostic record cannot fit the configured sink budget.")
            self._append(fitted)
        except (OSError, ValueError) as exc:
            self.failed = True
            self.failure_count = 1
            self.failure_message = type(exc).__name__
            try:
                print("BioCall Studio Train diagnostics unavailable", file=sys.stderr)
            except Exception:
                pass

    def _append(self, payload: bytes) -> None:
        parent = self.path.parent
        if parent.is_symlink() or not parent.is_dir():
            raise OSError("Diagnostic log directory is missing or unsafe.")
        if self.path.is_symlink():
            raise OSError("Diagnostic log cannot be a symlink.")
        current_size = self.path.stat().st_size if self.path.exists() else 0
        if current_size and current_size + len(payload) > self.max_bytes:
            self._rotate()
        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
        descriptor = os.open(self.path, flags, 0o600)
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            self.path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    def _rotate(self) -> None:
        if self.backup_count == 0:
            if self.path.exists():
                if self.path.is_symlink() or not self.path.is_file():
                    raise OSError("Diagnostic log is unsafe.")
                self.path.unlink()
            return
        oldest = self.path.with_name(f"{self.path.name}.{self.backup_count}")
        if oldest.exists() or oldest.is_symlink():
            if oldest.is_symlink() or not oldest.is_file():
                raise OSError("Diagnostic rotation segment is unsafe.")
            oldest.unlink()
        for index in range(self.backup_count - 1, 0, -1):
            source = self.path.with_name(f"{self.path.name}.{index}")
            destination = self.path.with_name(f"{self.path.name}.{index + 1}")
            if source.exists() or source.is_symlink():
                if source.is_symlink() or not source.is_file():
                    raise OSError("Diagnostic rotation segment is unsafe.")
                source.replace(destination)
        if self.path.exists():
            if self.path.is_symlink() or not self.path.is_file():
                raise OSError("Diagnostic log is unsafe.")
            self.path.replace(self.path.with_name(f"{self.path.name}.1"))

    def close(self) -> None:
        return


class DiagnosticJsonlHandler(logging.Handler):
    """Logging handler that intentionally consumes only diagnostic allowlist extras."""

    def __init__(
        self,
        sink: BoundedJsonlSink,
        *,
        session_id: str | None,
        level: int = logging.INFO,
    ):
        super().__init__(level)
        self.sink = sink
        self.session_id = session_id

    def emit(self, record: logging.LogRecord) -> None:
        try:
            event = getattr(record, "diagnostic_event", "log_record")
            context = getattr(record, "diagnostic_context", {})
            payload = encode_diagnostic_record(
                component=record.name,
                event=event,
                message=record.getMessage(),
                level=record.levelname,
                session_id=self.session_id,
                context=context if isinstance(context, Mapping) else {},
                timestamp=datetime.fromtimestamp(record.created, UTC),
                pid=record.process,
            )
            self.sink.write(payload)
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        self.sink.close()
        super().close()


class WorkerDiagnosticSession:
    """One fresh Worker-process handler, never inherited from the GUI logger."""

    def __init__(
        self,
        collection_root: Path,
        run_id: str,
        request_id: str,
        *,
        session_id: str | None,
        debug: bool,
        request_path: Path,
        component: str,
    ):
        path = worker_log_path(collection_root, run_id, create=True)
        expected_request = path.parent.parent / "request.json"
        if request_path.resolve(strict=True) != expected_request.resolve(strict=True):
            raise ValueError("Worker request does not match its contained Run directory.")
        self.run_id = run_id
        self.request_id = request_id
        self.logger = logging.Logger(component, logging.DEBUG)
        self.logger.propagate = False
        self.handler = DiagnosticJsonlHandler(
            BoundedJsonlSink(
                path,
                max_bytes=WORKER_LOG_MAX_BYTES,
                backup_count=WORKER_LOG_BACKUP_COUNT,
            ),
            session_id=session_id,
            level=logging.DEBUG if debug else logging.INFO,
        )
        self.logger.addHandler(self.handler)
        self._closed = False

    @property
    def path(self) -> Path:
        return self.handler.sink.path

    @property
    def available(self) -> bool:
        return not self.handler.sink.failed and not self._closed

    def emit(
        self,
        event: str,
        message: str,
        *,
        level: int = logging.INFO,
        context: Mapping[str, object] | None = None,
    ) -> None:
        values = {"run_id": self.run_id, "request_id": self.request_id, **(context or {})}
        self.logger.log(
            level,
            message,
            extra={"diagnostic_event": event, "diagnostic_context": values},
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.logger.removeHandler(self.handler)
        self.handler.close()


def _contained_directory(parent: Path, child: Path, *, label: str) -> Path:
    if child.is_symlink():
        raise ValueError(f"{label} cannot be a symlink.")
    resolved_parent = parent.resolve(strict=True)
    resolved_child = child.resolve(strict=True)
    if not resolved_child.is_dir() or not resolved_child.is_relative_to(resolved_parent):
        raise ValueError(f"{label} is not a contained directory.")
    return resolved_child


def worker_log_path(collection_root: Path, run_id: str, *, create: bool = False) -> Path:
    """Resolve one trusted Run's Worker log without following writable symlink escapes."""
    safe_run_id = validate_relative_path(run_id)
    if "/" in safe_run_id:
        raise ValueError("Run ID must be one portable path segment.")
    collection = Path(collection_root).resolve(strict=True)
    alpaca = _contained_directory(collection, collection / ".alpaca", label="Metadata storage")
    runs = _contained_directory(alpaca, alpaca / "runs", label="Run storage")
    run = _contained_directory(runs, runs / safe_run_id, label="Run directory")
    logs = run / "logs"
    if logs.is_symlink():
        raise ValueError("Run log storage cannot be a symlink.")
    if create:
        logs.mkdir(mode=0o700, exist_ok=True)
    if not logs.exists():
        return logs / "worker.jsonl"
    logs = _contained_directory(run, logs, label="Run log storage")
    path = logs / "worker.jsonl"
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("Worker log is missing or unsafe.")
    return path


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Diagnostic timestamp is invalid.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Diagnostic timestamp must include UTC.")
    return parsed.astimezone(UTC)


def _normalize_existing_record(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("Unsupported diagnostic record.")
    required = {"timestamp_utc", "level", "component", "event", "message", "pid"}
    if not required.issubset(raw):
        raise ValueError("Diagnostic record is incomplete.")
    if not isinstance(raw["pid"], int):
        raise ValueError("Diagnostic process ID is invalid.")
    context = {key: raw[key] for key in _STRING_CONTEXT | _NUMBER_CONTEXT if key in raw}
    encoded = encode_diagnostic_record(
        component=raw["component"],
        event=raw["event"],
        message=raw["message"],
        level=raw["level"],
        session_id=raw.get("session_id"),
        context=context,
        timestamp=_parse_timestamp(raw["timestamp_utc"]),
        pid=raw["pid"],
    )
    normalized = json.loads(encoded)
    assert not (set(normalized) - _KNOWN_FIELDS)
    return normalized


def read_diagnostic_records(
    path: Path, *, max_bytes: int = APP_LOG_MAX_BYTES
) -> tuple[tuple[dict[str, object], ...], tuple[str, ...]]:
    """Read independent records, skipping corrupt/unknown lines without losing later records."""
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("Diagnostic log is missing or unsafe.")
    if source.stat().st_size > max_bytes:
        raise ValueError("Diagnostic log exceeds its reader budget.")
    records: list[dict[str, object]] = []
    notices: list[str] = []
    with source.open("rb") as stream:
        for line_number, line in enumerate(stream, 1):
            if len(line) > MAX_RECORD_BYTES:
                notices.append(f"Skipped overlong record {line_number}")
                continue
            try:
                raw = json.loads(line)
                records.append(_normalize_existing_record(raw))
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
                notices.append(f"Skipped invalid record {line_number}")
    return tuple(records), tuple(notices)


def _recognized_app_files(log_dir: Path) -> list[Path]:
    if log_dir.is_symlink() or not log_dir.is_dir():
        return []
    root = log_dir.resolve(strict=True)
    files: list[Path] = []
    for path in log_dir.iterdir():
        if not _APP_LOG_NAME.fullmatch(path.name) or path.is_symlink() or not path.is_file():
            continue
        if path.resolve(strict=True).parent != root:
            continue
        files.append(path)
    return files


def prune_app_logs(
    log_dir: Path,
    *,
    active_path: Path | None,
    max_age_days: int = APP_LOG_RETENTION_DAYS,
    total_max_bytes: int = APP_LOG_TOTAL_MAX_BYTES,
    now: datetime | None = None,
) -> tuple[Path, ...]:
    """Prune only recognized, non-active app logs by age and aggregate byte budget."""
    moment = (now or datetime.now(UTC)).timestamp()
    cutoff = moment - timedelta(days=max_age_days).total_seconds()
    active_names: set[str] = set()
    if active_path is not None:
        active_names = {active_path.name, *(f"{active_path.name}.{i}" for i in range(1, 4))}
    removed: list[Path] = []
    files = _recognized_app_files(Path(log_dir))
    for path in files:
        if path.name not in active_names and path.stat().st_mtime < cutoff:
            path.unlink()
            removed.append(path)
    remaining = [path for path in _recognized_app_files(Path(log_dir)) if path.exists()]
    total = sum(path.stat().st_size for path in remaining)
    for path in sorted(remaining, key=lambda item: (item.stat().st_mtime, item.name)):
        if total <= total_max_bytes:
            break
        if path.name in active_names:
            continue
        size = path.stat().st_size
        path.unlink()
        total -= size
        removed.append(path)
    return tuple(removed)


class BoundedStderrCapture:
    """Incrementally drain arbitrary stderr while retaining only sanitized bounded evidence."""

    def __init__(self, *, max_bytes: int = 64 * 1024, max_lines: int = 32):
        self.max_bytes = max_bytes
        self.max_lines = max_lines
        self._buffer = b""
        self._accepted_bytes = 0
        self.dropped_bytes = 0
        self.lines: list[str] = []

    def feed(self, chunk: bytes) -> None:
        data = bytes(chunk)
        available = max(0, self.max_bytes - self._accepted_bytes)
        accepted = data[:available]
        self._accepted_bytes += len(accepted)
        self.dropped_bytes += len(data) - len(accepted)
        self._buffer += accepted
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            self._accept_line(line)

    def _accept_line(self, line: bytes) -> None:
        text = sanitize_diagnostic_text(line.decode("utf-8", errors="replace"), limit=500)
        if len(self.lines) < self.max_lines:
            self.lines.append(text)
        else:
            self.dropped_bytes += len(line) + 1

    def finish(self) -> None:
        if self._buffer:
            self._accept_line(self._buffer)
            self._buffer = b""

    @property
    def summary(self) -> str:
        summary = " | ".join(self.lines[-3:])
        if self.dropped_bytes:
            suffix = f"stderr truncated; {self.dropped_bytes} bytes dropped"
            summary = f"{summary} | {suffix}" if summary else suffix
        return sanitize_diagnostic_text(summary or "Worker stderr was empty")


@dataclass(frozen=True)
class DiagnosticsExportResult:
    path: Path
    included_files: int
    included_records: int
    skipped_records: int
    notices: tuple[str, ...]


def _records_as_jsonl(records: Iterable[dict[str, object]]) -> bytes:
    return b"".join(
        (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
        for record in records
    )


def _safe_inventory(inventory: Mapping[str, object] | None) -> dict[str, object]:
    allowed = {
        "session_id",
        "run_id",
        "version",
        "build_id",
        "python_version",
        "qt_version",
        "toolbox_version",
        "alp_ui_version",
    }
    result: dict[str, object] = {}
    for key, value in (inventory or {}).items():
        if key in allowed:
            safe = _safe_identifier(value)
            if safe is not None:
                result[key] = safe
    return result


def export_diagnostics_bundle(
    destination: Path,
    *,
    app_log_dir: Path,
    selected_run: tuple[Path, str] | None = None,
    inventory: Mapping[str, object] | None = None,
    max_bytes: int = MAX_EXPORT_BYTES,
    overwrite: bool = False,
) -> DiagnosticsExportResult:
    """Create one explicit support ZIP from revalidated, re-encoded diagnostic records."""
    target = Path(destination)
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise ValueError("Diagnostics export destination is unsafe.")
    if target.exists() and not overwrite:
        raise FileExistsError(f"Diagnostics export already exists: {target.name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    sources: list[tuple[str, Path, int]] = []
    for path in sorted(_recognized_app_files(Path(app_log_dir)), key=lambda item: item.name):
        sources.append((f"app/{path.name}", path, APP_LOG_MAX_BYTES))
    if selected_run is not None:
        collection_root, run_id = selected_run
        base = worker_log_path(collection_root, run_id, create=False)
        for index in range(WORKER_LOG_BACKUP_COUNT, 0, -1):
            segment = base.with_name(f"{base.name}.{index}")
            if segment.exists() or segment.is_symlink():
                if (
                    segment.is_symlink()
                    or not segment.is_file()
                    or not _WORKER_LOG_NAME.fullmatch(segment.name)
                ):
                    raise ValueError("Worker diagnostic segment is unsafe.")
                sources.append((f"runs/{run_id}/{segment.name}", segment, WORKER_LOG_MAX_BYTES))
        if base.exists() or base.is_symlink():
            if base.is_symlink() or not base.is_file():
                raise ValueError("Worker diagnostic log is unsafe.")
            sources.append((f"runs/{run_id}/{base.name}", base, WORKER_LOG_MAX_BYTES))

    payloads: list[tuple[str, bytes]] = []
    notices: list[str] = []
    included_records = 0
    skipped_records = 0
    consumed = 0
    for archive_name, source, reader_budget in sources:
        records, source_notices = read_diagnostic_records(source, max_bytes=reader_budget)
        payload = _records_as_jsonl(records)
        skipped_records += len(source_notices)
        notices.extend(source_notices)
        if not payload:
            continue
        if consumed + len(payload) > max_bytes:
            notices.append("Export size cap omitted additional diagnostic records")
            break
        consumed += len(payload)
        included_records += len(records)
        payloads.append((archive_name, payload))

    manifest = {
        "schema_version": 1,
        "created_utc": _utc_timestamp(),
        **_safe_inventory(inventory),
        "files": [name for name, _payload in payloads],
        "included_records": included_records,
        "skipped_records": skipped_records,
        "notices": [
            "Records were parsed, allowlisted and privacy-normalized again during export.",
            *notices,
        ],
    }
    mode = "wb" if overwrite else "xb"
    with target.open(mode) as raw:
        _write_zip(raw, payloads, manifest)
    return DiagnosticsExportResult(
        target,
        len(payloads),
        included_records,
        skipped_records,
        tuple(notices),
    )


def _write_zip(
    stream: BinaryIO, payloads: list[tuple[str, bytes]], manifest: dict[str, object]
) -> None:
    with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
        for name, payload in payloads:
            archive.writestr(name, payload)
        archive.writestr(
            "diagnostics.json",
            json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8") + b"\n",
        )
