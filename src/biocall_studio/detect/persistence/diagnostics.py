"""Detect-owned bounded JSONL diagnostics with strict privacy normalization."""

from __future__ import annotations

import json
import os
import re
import stat
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

DIAGNOSTIC_SCHEMA_VERSION = 1
DEFAULT_LOG_MAX_BYTES = 256 * 1024
DEFAULT_LOG_BACKUP_COUNT = 2
MAX_RECORD_BYTES = 8 * 1024
MAX_MESSAGE_CHARACTERS = 1_000

_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_STRING_CONTEXT = frozenset(
    {"run_id", "request_id", "launch_id", "status", "stage"}
)
_NUMBER_CONTEXT = frozenset(
    {"progress", "stage_index", "exit_code", "dropped_bytes", "count"}
)
_KNOWN_FIELDS = frozenset(
    {
        "schema_version",
        "timestamp_utc",
        "level",
        "component",
        "event",
        "message",
        "pid",
        *_STRING_CONTEXT,
        *_NUMBER_CONTEXT,
    }
)
_NAME = re.compile(r"[a-z][a-z0-9_.-]{0,127}")
_EVENT = re.compile(r"[a-z][a-z0-9_]{0,95}")
_RUN_ID = re.compile(r"drun_[0-9a-f]{32}")
_LOG_NAME = re.compile(r"(?:supervisor|worker)\.jsonl(?:\.[1-2])?")
_SECRET = re.compile(
    r"(?i)\b(?:api[_-]?(?:key|token)|access[_-]?token|token|password|passwd|secret|credential)"
    r"\s*[:=]\s*[^\s,;]+"
)
_EXCEPTION = re.compile(
    r"\b[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception)\s*\([^)]*\)"
)
_WINDOWS_PATH = re.compile(r"(?i)(?<![A-Za-z0-9])(?:[A-Z]:[\\/][^\s<>\"']+)")
_UNC_PATH = re.compile(r"(?<![A-Za-z0-9])(?:\\\\[^\s<>\"']+)")
_HOME_PATH = re.compile(r"(?<![A-Za-z0-9])(?:~[\\/][^\s<>\"']+)")
_POSIX_PATH = re.compile(r"(?<![A-Za-z0-9])/(?:[^\s<>\"']+)")
_PORTABLE_PATH = re.compile(
    r"(?i)(?<![A-Za-z0-9_.-])(?:[A-Za-z0-9_.-]+[\\/])+[A-Za-z0-9_.-]+"
)
_WAV_NAME = re.compile(r"(?i)(?<![A-Za-z0-9_.-])[A-Za-z0-9_.-]+\.wav\b")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def _timestamp(moment: datetime | None = None) -> str:
    value = moment or datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sanitize_diagnostic_text(value: object, *, limit: int = MAX_MESSAGE_CHARACTERS) -> str:
    text = str(value)
    text = _SECRET.sub("<redacted credential>", text)
    text = _EXCEPTION.sub("<exception>", text)
    for pattern in (_WINDOWS_PATH, _UNC_PATH, _HOME_PATH, _POSIX_PATH, _PORTABLE_PATH):
        text = pattern.sub("<path>", text)
    text = _WAV_NAME.sub("<recording.wav>", text)
    text = _CONTROL.sub(" ", text)
    text = " ".join(text.split())
    if len(text) > limit:
        suffix = "… <truncated>"
        text = text[: max(0, limit - len(suffix))].rstrip() + suffix
    return text or "Diagnostic event"


def _safe_identifier(value: object, *, maximum: int = 160) -> str | None:
    if not isinstance(value, str) or not value or len(value) > maximum:
        return None
    if any(ord(character) < 32 for character in value) or "/" in value or "\\" in value:
        return None
    return sanitize_diagnostic_text(value, limit=maximum)


def encode_diagnostic_record(
    *,
    component: str,
    event: str,
    message: object,
    level: str,
    context: Mapping[str, object] | None = None,
    timestamp: datetime | None = None,
    pid: int | None = None,
) -> bytes:
    normalized_level = str(level).upper()
    if normalized_level not in _LEVELS:
        raise ValueError("Diagnostic level is invalid.")
    if not isinstance(component, str) or _NAME.fullmatch(component) is None:
        raise ValueError("Diagnostic component is invalid.")
    if not isinstance(event, str) or _EVENT.fullmatch(event) is None:
        raise ValueError("Diagnostic event is invalid.")
    record: dict[str, object] = {
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "timestamp_utc": _timestamp(timestamp),
        "level": normalized_level,
        "component": component,
        "event": event,
        "message": sanitize_diagnostic_text(message),
        "pid": os.getpid() if pid is None else int(pid),
    }
    for key, value in (context or {}).items():
        if key in _STRING_CONTEXT:
            safe = _safe_identifier(value)
            if safe is not None:
                record[key] = safe
        elif key in _NUMBER_CONTEXT and isinstance(value, (int, float)) and not isinstance(
            value, bool
        ):
            record[key] = value
    encoded = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(encoded) > MAX_RECORD_BYTES:
        record["message"] = "Diagnostic record exceeded its size limit"
        for key in tuple(record):
            if key in _STRING_CONTEXT | _NUMBER_CONTEXT:
                record.pop(key)
        encoded = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
    return encoded


class BoundedJsonlLog:
    """Append-only per-process JSONL with a small fixed rotation budget."""

    def __init__(
        self,
        path: Path,
        *,
        max_bytes: int = DEFAULT_LOG_MAX_BYTES,
        backup_count: int = DEFAULT_LOG_BACKUP_COUNT,
    ):
        if max_bytes <= 0 or not 0 <= backup_count <= 2:
            raise ValueError("Diagnostic rotation budget is invalid.")
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.failed = False

    def write(self, payload: bytes) -> None:
        if self.failed:
            return
        try:
            fitted = bytes(payload)
            if len(fitted) > self.max_bytes:
                fitted = encode_diagnostic_record(
                    component="detect.log",
                    event="record_truncated",
                    message="Diagnostic record exceeded the configured file budget",
                    level="WARNING",
                )
            self._append(fitted)
        except (OSError, ValueError):
            self.failed = True

    def _append(self, payload: bytes) -> None:
        parent = self.path.parent
        if parent.is_symlink() or not parent.is_dir() or self.path.is_symlink():
            raise ValueError("Diagnostic log path is unsafe.")
        if self.path.exists() and not self.path.is_file():
            raise ValueError("Diagnostic log path is unsafe.")
        current = self.path.stat().st_size if self.path.exists() else 0
        if current and current + len(payload) > self.max_bytes:
            self._rotate()
        descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
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
            self.path.unlink(missing_ok=True)
            return
        oldest = self.path.with_name(f"{self.path.name}.{self.backup_count}")
        if oldest.exists() or oldest.is_symlink():
            if oldest.is_symlink() or not oldest.is_file():
                raise ValueError("Diagnostic rotation segment is unsafe.")
            oldest.unlink()
        for index in range(self.backup_count - 1, 0, -1):
            source = self.path.with_name(f"{self.path.name}.{index}")
            if source.exists() or source.is_symlink():
                if source.is_symlink() or not source.is_file():
                    raise ValueError("Diagnostic rotation segment is unsafe.")
                source.replace(self.path.with_name(f"{self.path.name}.{index + 1}"))
        if self.path.exists():
            if not self.path.is_file():
                raise ValueError("Diagnostic log is unsafe.")
            self.path.replace(self.path.with_name(f"{self.path.name}.1"))


def _contained_directory(parent: Path, child: Path, *, label: str) -> Path:
    if child.is_symlink():
        raise ValueError(f"{label} cannot be a symlink.")
    root = parent.resolve(strict=True)
    resolved = child.resolve(strict=True)
    if not resolved.is_dir() or not resolved.is_relative_to(root):
        raise ValueError(f"{label} is not a contained directory.")
    return resolved


def resolve_run_log_path(
    collection_root: Path,
    run_id: str,
    log_kind: str,
    *,
    create: bool = False,
) -> Path:
    if _RUN_ID.fullmatch(run_id) is None:
        raise ValueError("Detect Run ID is invalid.")
    if log_kind not in {"supervisor", "worker"}:
        raise ValueError("Detect log kind is invalid.")
    collection = Path(collection_root).resolve(strict=True)
    runs = _contained_directory(collection, collection / "runs", label="Run storage")
    run = _contained_directory(runs, runs / run_id, label="Run directory")
    logs = run / "logs"
    if logs.is_symlink():
        raise ValueError("Run log storage cannot be a symlink.")
    if create:
        logs.mkdir(mode=0o700, exist_ok=True)
    if not logs.exists():
        return logs / f"{log_kind}.jsonl"
    logs = _contained_directory(run, logs, label="Run log storage")
    path = logs / f"{log_kind}.jsonl"
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("Detect diagnostic log is missing or unsafe.")
    return path


def _normalize_record(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict) or raw.get("schema_version") != DIAGNOSTIC_SCHEMA_VERSION:
        raise ValueError("Unsupported Detect diagnostic record.")
    required = {"timestamp_utc", "level", "component", "event", "message", "pid"}
    if not required.issubset(raw) or set(raw) - _KNOWN_FIELDS:
        raise ValueError("Detect diagnostic record is not allowlisted.")
    parsed = datetime.fromisoformat(str(raw["timestamp_utc"]).replace("Z", "+00:00"))
    context = {key: raw[key] for key in _STRING_CONTEXT | _NUMBER_CONTEXT if key in raw}
    return json.loads(
        encode_diagnostic_record(
            component=raw["component"],
            event=raw["event"],
            message=raw["message"],
            level=raw["level"],
            context=context,
            timestamp=parsed,
            pid=raw["pid"],
        )
    )


def read_diagnostic_records(
    collection_root: Path,
    path: Path,
    *,
    max_bytes: int = DEFAULT_LOG_MAX_BYTES,
) -> tuple[tuple[dict[str, object], ...], tuple[str, ...]]:
    collection = Path(collection_root).resolve(strict=True)
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("Detect diagnostic log is missing or unsafe.")
    resolved = source.resolve(strict=True)
    if not resolved.is_relative_to(collection) or _LOG_NAME.fullmatch(source.name) is None:
        raise ValueError("Detect diagnostic log is not contained.")
    if source.stat().st_size > max_bytes:
        raise ValueError("Detect diagnostic log exceeds its reader budget.")
    records: list[dict[str, object]] = []
    notices: list[str] = []
    with source.open("rb") as stream:
        for line_number, line in enumerate(stream, 1):
            if len(line) > MAX_RECORD_BYTES:
                notices.append(f"Skipped overlong record {line_number}")
                continue
            try:
                records.append(_normalize_record(json.loads(line)))
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
                notices.append(f"Skipped invalid record {line_number}")
    return tuple(records), tuple(notices)


class BoundedStderrCapture:
    def __init__(self, *, max_bytes: int = 64 * 1024, max_lines: int = 32):
        if max_bytes <= 0 or max_lines <= 0:
            raise ValueError("stderr capture bounds must be positive.")
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
            self._accept(line)

    def _accept(self, line: bytes) -> None:
        if len(self.lines) < self.max_lines:
            self.lines.append(
                sanitize_diagnostic_text(line.decode("utf-8", errors="replace"), limit=500)
            )
        else:
            self.dropped_bytes += len(line) + 1

    def finish(self) -> None:
        if self._buffer:
            self._accept(self._buffer)
            self._buffer = b""

    @property
    def summary(self) -> str:
        summary = " | ".join(self.lines[-3:])
        if self.dropped_bytes:
            suffix = f"stderr truncated; {self.dropped_bytes} bytes dropped"
            summary = f"{summary} | {suffix}" if summary else suffix
        return sanitize_diagnostic_text(summary or "Worker stderr was empty")
