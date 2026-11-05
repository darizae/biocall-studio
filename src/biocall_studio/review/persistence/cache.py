"""Contained, checksummed persistence for regenerable Review spectrogram PNGs."""

from __future__ import annotations

import binascii
import hashlib
import json
import os
import re
import sqlite3
import struct
import threading
import time
import uuid
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from biocall_studio.review.domain.spectrograms import (
    SpectrogramImageTier,
    SpectrogramMetadata,
    SpectrogramRaster,
    validate_spectrogram_content_key,
)

_SCHEMA_VERSION = 1
_DIGEST = re.compile(r"[0-9a-f]{64}")
_MAX_PNG_BYTES = 8 * 1_024 * 1_024
_MAX_METADATA_BYTES = 512 * 1_024
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_FAILURE_CODES = frozenset(
    {
        "cancelled",
        "corrupt",
        "disk_full",
        "encode_failed",
        "permission",
        "render_failed",
        "stale",
        "unsafe_path",
        "worker_lost",
    }
)

_SCHEMA = """
CREATE TABLE cache_entries (
    content_key TEXT PRIMARY KEY,
    relative_path TEXT,
    checksum TEXT,
    size_bytes INTEGER,
    tier TEXT NOT NULL CHECK (tier IN ('thumbnail', 'detail')),
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    source_sha256 TEXT NOT NULL,
    settings_digest TEXT NOT NULL,
    metadata_json TEXT,
    metadata_checksum TEXT,
    state TEXT NOT NULL CHECK (state IN ('generating', 'valid', 'failed')),
    failure_code TEXT,
    created_ns INTEGER NOT NULL,
    last_access_ns INTEGER NOT NULL
) STRICT;
CREATE INDEX cache_entries_lru ON cache_entries(state, last_access_ns);
"""


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{label} digest is invalid.")
    return value


def _chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = binascii.crc32(kind)
    checksum = binascii.crc32(payload, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


def encode_rgb_png(raster: SpectrogramRaster) -> bytes:
    """Encode one fixed RGB raster with no axes, labels, or ancillary metadata."""
    if not isinstance(raster, SpectrogramRaster):
        raise TypeError("Spectrogram raster is invalid.")
    row_bytes = raster.width * 3
    scanlines = b"".join(
        b"\0" + raster.rgb_bytes[offset : offset + row_bytes]
        for offset in range(0, len(raster.rgb_bytes), row_bytes)
    )
    header = struct.pack(">IIBBBBB", raster.width, raster.height, 8, 2, 0, 0, 0)
    encoded = (
        _PNG_SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(scanlines, level=6))
        + _chunk(b"IEND", b"")
    )
    if len(encoded) > _MAX_PNG_BYTES:
        raise ValueError("Encoded spectrogram exceeds the cache file limit.")
    return encoded


def inspect_rgb_png(payload: bytes, *, expected_width: int, expected_height: int) -> None:
    """Validate CRCs, fixed RGB format, dimensions, and complete decompression."""
    if not isinstance(payload, bytes) or not payload.startswith(_PNG_SIGNATURE):
        raise ValueError("Cached spectrogram is not a PNG image.")
    if len(payload) > _MAX_PNG_BYTES:
        raise ValueError("Cached spectrogram exceeds the file limit.")
    offset = len(_PNG_SIGNATURE)
    chunks: list[tuple[bytes, bytes]] = []
    while offset < len(payload):
        if offset + 12 > len(payload):
            raise ValueError("Cached PNG is truncated.")
        size = struct.unpack(">I", payload[offset : offset + 4])[0]
        if size > _MAX_PNG_BYTES or offset + 12 + size > len(payload):
            raise ValueError("Cached PNG chunk is invalid.")
        kind = payload[offset + 4 : offset + 8]
        value = payload[offset + 8 : offset + 8 + size]
        stored_crc = struct.unpack(">I", payload[offset + 8 + size : offset + 12 + size])[0]
        calculated = binascii.crc32(kind)
        calculated = binascii.crc32(value, calculated) & 0xFFFFFFFF
        if stored_crc != calculated:
            raise ValueError("Cached PNG checksum is invalid.")
        chunks.append((kind, value))
        offset += 12 + size
        if kind == b"IEND":
            break
    if offset != len(payload) or not chunks or chunks[0][0] != b"IHDR":
        raise ValueError("Cached PNG structure is invalid.")
    header = chunks[0][1]
    if len(header) != 13:
        raise ValueError("Cached PNG header is invalid.")
    width, height, bit_depth, colour, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", header
    )
    if (
        (width, height) != (expected_width, expected_height)
        or (bit_depth, colour, compression, filtering, interlace) != (8, 2, 0, 0, 0)
    ):
        raise ValueError("Cached PNG format or dimensions do not match the manifest.")
    compressed = b"".join(value for kind, value in chunks if kind == b"IDAT")
    try:
        decoded = zlib.decompress(compressed)
    except zlib.error as exc:
        raise ValueError("Cached PNG pixels are corrupt.") from exc
    expected_bytes = height * (1 + width * 3)
    if len(decoded) != expected_bytes:
        raise ValueError("Cached PNG pixel payload is incomplete.")
    row_bytes = 1 + width * 3
    if any(decoded[offset] != 0 for offset in range(0, len(decoded), row_bytes)):
        raise ValueError("Cached PNG uses an unsupported pixel filter.")


@dataclass(frozen=True, slots=True)
class CacheEntry:
    content_key: str
    path: Path
    checksum: str
    size_bytes: int
    tier: SpectrogramImageTier
    width: int
    height: int
    source_sha256: str
    settings_digest: str
    metadata: SpectrogramMetadata
    last_access_ns: int = field(compare=False)


@dataclass(frozen=True, slots=True)
class CacheMutation:
    deleted_keys: tuple[str, ...]
    failed_keys: tuple[str, ...]
    protected_keys: tuple[str, ...]
    freed_bytes: int


@dataclass(frozen=True, slots=True)
class CacheReconciliation:
    removed_staging_names: tuple[str, ...]
    removed_orphan_names: tuple[str, ...]
    invalid_keys: tuple[str, ...]


class CachePublicationStale(RuntimeError):
    """A manual clear happened after this cache render started."""


class SpectrogramCache:
    """A versioned SQLite manifest plus content-addressed PNG object directory."""

    def __init__(self, root: Path, *, limit_bytes: int):
        requested = Path(root).expanduser()
        if requested.is_symlink():
            raise ValueError("Spectrogram cache root cannot be a symbolic link.")
        self.root = requested.resolve(strict=False)
        self.objects_root = self.root / "objects"
        self.staging_root = self.root / "staging"
        self.database_path = self.root / "manifest.sqlite3"
        if type(limit_bytes) is not int or limit_bytes < 1:
            raise ValueError("Spectrogram cache limit must be a positive byte count.")
        self.limit_bytes = limit_bytes
        self._lock = threading.RLock()
        self._automatic_pins: frozenset[str] = frozenset()
        self._clear_epoch = 0
        self._ensure_layout()
        self._initialize_database()

    def _ensure_layout(self) -> None:
        if self.root.parent.is_symlink():
            raise ValueError("Spectrogram cache parent cannot be a symbolic link.")
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        for directory in (self.root, self.objects_root, self.staging_root):
            if directory.is_symlink():
                raise ValueError("Spectrogram cache directory cannot be a symbolic link.")
            directory.mkdir(mode=0o700, exist_ok=True)
            if not directory.is_dir():
                raise ValueError("Spectrogram cache path is not a directory.")
            directory.chmod(0o700)
        if self.database_path.is_symlink():
            raise ValueError("Spectrogram cache manifest cannot be a symbolic link.")

    def _connect(self) -> sqlite3.Connection:
        self._ensure_layout()
        connection = sqlite3.connect(self.database_path, timeout=1.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.execute("PRAGMA synchronous = FULL")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            connection.executescript(_SCHEMA)
            connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            connection.commit()
        elif version != _SCHEMA_VERSION:
            connection.close()
            raise ValueError("Spectrogram cache manifest version is unsupported.")
        os.chmod(self.database_path, 0o600)
        return connection

    def _initialize_database(self) -> None:
        connection = self._connect()
        try:
            if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("Spectrogram cache manifest is corrupt.")
        finally:
            connection.close()

    def object_path(self, content_key: str, *, create_parent: bool = False) -> Path:
        key = validate_spectrogram_content_key(content_key)
        shard = self.objects_root / key[5:7]
        if shard.is_symlink():
            raise ValueError("Spectrogram cache object path contains a symbolic link.")
        if create_parent:
            shard.mkdir(mode=0o700, exist_ok=True)
            if shard.is_symlink() or not shard.is_dir():
                raise ValueError("Spectrogram cache object directory is unsafe.")
        path = shard / f"{key}.png"
        if path.is_symlink():
            raise ValueError("Spectrogram cache object cannot be a symbolic link.")
        return path

    @staticmethod
    def _relative_path(content_key: str) -> str:
        return f"objects/{content_key[5:7]}/{content_key}.png"

    def _mark_generating(self, raster: SpectrogramRaster, settings_digest: str) -> None:
        now = time.time_ns()
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO cache_entries (
                    content_key, relative_path, checksum, size_bytes, tier, width, height,
                    source_sha256, settings_digest, metadata_json, metadata_checksum,
                    state, failure_code, created_ns, last_access_ns
                ) VALUES (?, NULL, NULL, NULL, ?, ?, ?, ?, ?, NULL, NULL,
                          'generating', NULL, ?, ?)
                ON CONFLICT(content_key) DO UPDATE SET
                    relative_path = NULL, checksum = NULL, size_bytes = NULL,
                    tier = excluded.tier, width = excluded.width, height = excluded.height,
                    source_sha256 = excluded.source_sha256,
                    settings_digest = excluded.settings_digest, metadata_json = NULL,
                    metadata_checksum = NULL, state = 'generating', failure_code = NULL,
                    last_access_ns = excluded.last_access_ns
                """,
                (
                    raster.content_key,
                    raster.metadata.tier.value,
                    raster.width,
                    raster.height,
                    raster.metadata.source_sha256,
                    settings_digest,
                    now,
                    now,
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def mark_failed(self, content_key: str, failure_code: str) -> None:
        key = validate_spectrogram_content_key(content_key)
        if failure_code not in _FAILURE_CODES:
            raise ValueError("Spectrogram cache failure code is invalid.")
        connection = self._connect()
        try:
            connection.execute(
                """
                UPDATE cache_entries SET state = 'failed', failure_code = ?,
                    relative_path = NULL, checksum = NULL, size_bytes = NULL,
                    metadata_json = NULL, metadata_checksum = NULL,
                    last_access_ns = ? WHERE content_key = ?
                """,
                (failure_code, time.time_ns(), key),
            )
            connection.commit()
        finally:
            connection.close()

    def publish(
        self,
        raster: SpectrogramRaster,
        *,
        settings_digest: str,
        protected_keys: set[str] | frozenset[str] = frozenset(),
        expected_clear_epoch: int | None = None,
    ) -> CacheEntry:
        if not isinstance(raster, SpectrogramRaster):
            raise TypeError("Spectrogram raster is invalid.")
        settings_digest = _digest(settings_digest, "Spectrogram settings")
        if raster.metadata.tier.dimensions != (raster.width, raster.height):
            raise ValueError("Spectrogram raster tier dimensions are invalid.")
        metadata_json = json.dumps(
            raster.metadata.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        if len(metadata_json.encode("utf-8")) > _MAX_METADATA_BYTES:
            raise ValueError("Spectrogram metadata exceeds the cache manifest limit.")
        metadata_checksum = hashlib.sha256(metadata_json.encode("utf-8")).hexdigest()
        payload = encode_rgb_png(raster)
        checksum = hashlib.sha256(payload).hexdigest()
        with self._lock:
            if expected_clear_epoch is not None and expected_clear_epoch != self._clear_epoch:
                raise CachePublicationStale(
                    "Spectrogram cache was cleared after this render started."
                )
            existing = self.lookup(raster.content_key)
            if existing is not None:
                if (
                    existing.source_sha256 != raster.metadata.source_sha256
                    or existing.tier is not raster.metadata.tier
                ):
                    raise ValueError("Existing cache identity conflicts with the rendered content.")
                return existing
            self._mark_generating(raster, settings_digest)
            staging = self.staging_root / f"{raster.content_key}.{uuid.uuid4().hex}.part"
            try:
                target = self.object_path(raster.content_key, create_parent=True)
                with staging.open("xb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                inspect_rgb_png(
                    staging.read_bytes(),
                    expected_width=raster.width,
                    expected_height=raster.height,
                )
                os.replace(staging, target)
                try:
                    directory_fd = os.open(target.parent, os.O_RDONLY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
                except OSError:
                    # The file itself was fsynced before atomic replacement; some
                    # filesystems do not permit directory fsync.
                    pass
                now = time.time_ns()
                connection = self._connect()
                try:
                    connection.execute(
                        """
                        UPDATE cache_entries SET relative_path = ?, checksum = ?,
                            size_bytes = ?, metadata_json = ?, metadata_checksum = ?,
                            state = 'valid', failure_code = NULL, last_access_ns = ?
                         WHERE content_key = ? AND state = 'generating'
                        """,
                        (
                            self._relative_path(raster.content_key),
                            checksum,
                            len(payload),
                            metadata_json,
                            metadata_checksum,
                            now,
                            raster.content_key,
                        ),
                    )
                    connection.commit()
                finally:
                    connection.close()
            except Exception as exc:
                try:
                    if staging.exists() and not staging.is_symlink():
                        staging.unlink()
                except OSError:
                    pass
                failure = "disk_full" if isinstance(exc, OSError) and exc.errno == 28 else None
                if failure is None:
                    failure = (
                        "permission"
                        if isinstance(exc, PermissionError)
                        else "encode_failed"
                    )
                self.mark_failed(raster.content_key, failure)
                raise
            entry = self.lookup(raster.content_key)
            if entry is None:
                raise RuntimeError("Published spectrogram failed cache verification.")
            self.evict_to_limit(
                self.limit_bytes,
                protected_keys={raster.content_key, *protected_keys},
            )
            return entry

    def set_automatic_pins(self, content_keys: set[str] | frozenset[str]) -> None:
        """Protect the current and visible objects from automatic LRU eviction."""
        pins = frozenset(validate_spectrogram_content_key(key) for key in content_keys)
        with self._lock:
            self._automatic_pins = pins

    @property
    def publication_epoch(self) -> int:
        with self._lock:
            return self._clear_epoch

    def _row(self, content_key: str) -> sqlite3.Row | None:
        connection = self._connect()
        try:
            return connection.execute(
                "SELECT * FROM cache_entries WHERE content_key = ?", (content_key,)
            ).fetchone()
        finally:
            connection.close()

    def _invalidate(self, content_key: str, path: Path | None) -> None:
        if path is not None:
            try:
                if not path.is_symlink() and path.is_file():
                    path.unlink()
            except OSError:
                pass
        self.mark_failed(content_key, "corrupt")

    def lookup(self, content_key: str) -> CacheEntry | None:
        key = validate_spectrogram_content_key(content_key)
        with self._lock:
            row = self._row(key)
            if row is None or row["state"] != "valid":
                return None
            path: Path | None = None
            try:
                expected_relative = self._relative_path(key)
                if row["relative_path"] != expected_relative:
                    raise ValueError("Cache manifest path is not content-addressed.")
                path = self.object_path(key)
                if not path.is_file() or path.is_symlink():
                    raise ValueError("Cached spectrogram file is unavailable or unsafe.")
                if (
                    type(row["size_bytes"]) is not int
                    or not 1 <= row["size_bytes"] <= _MAX_PNG_BYTES
                ):
                    raise ValueError("Cached spectrogram size is invalid.")
                if path.stat().st_size != row["size_bytes"]:
                    raise ValueError("Cached spectrogram size changed.")
                payload = path.read_bytes()
                if hashlib.sha256(payload).hexdigest() != row["checksum"]:
                    raise ValueError("Cached spectrogram checksum changed.")
                inspect_rgb_png(
                    payload,
                    expected_width=row["width"],
                    expected_height=row["height"],
                )
                metadata_json = row["metadata_json"]
                if (
                    not isinstance(metadata_json, str)
                    or len(metadata_json.encode()) > _MAX_METADATA_BYTES
                ):
                    raise ValueError("Cached spectrogram metadata is invalid.")
                if hashlib.sha256(metadata_json.encode()).hexdigest() != row["metadata_checksum"]:
                    raise ValueError("Cached spectrogram metadata checksum changed.")
                metadata = SpectrogramMetadata.from_dict(json.loads(metadata_json))
                tier = SpectrogramImageTier(row["tier"])
                if (
                    metadata.source_sha256 != row["source_sha256"]
                    or metadata.tier is not tier
                    or metadata.width != row["width"]
                    or metadata.height != row["height"]
                ):
                    raise ValueError("Cached spectrogram metadata disagrees with its manifest.")
                _digest(row["checksum"], "Cached spectrogram")
                _digest(row["source_sha256"], "Spectrogram source")
                _digest(row["settings_digest"], "Spectrogram settings")
            except (OSError, TypeError, ValueError, json.JSONDecodeError, sqlite3.Error):
                self._invalidate(key, path)
                return None
            now = time.time_ns()
            connection = self._connect()
            try:
                connection.execute(
                    "UPDATE cache_entries SET last_access_ns = ? WHERE content_key = ?",
                    (now, key),
                )
                connection.commit()
            finally:
                connection.close()
            return CacheEntry(
                content_key=key,
                path=path,
                checksum=row["checksum"],
                size_bytes=row["size_bytes"],
                tier=tier,
                width=row["width"],
                height=row["height"],
                source_sha256=row["source_sha256"],
                settings_digest=row["settings_digest"],
                metadata=metadata,
                last_access_ns=now,
            )

    @property
    def actual_bytes(self) -> int:
        connection = self._connect()
        try:
            value = connection.execute(
                "SELECT COALESCE(SUM(size_bytes), 0) FROM cache_entries WHERE state = 'valid'"
            ).fetchone()[0]
            return int(value)
        finally:
            connection.close()

    def valid_content_keys(self, *, limit: int = 100_000) -> tuple[str, ...]:
        if type(limit) is not int or not 1 <= limit <= 100_000:
            raise ValueError("Cache key query limit is invalid.")
        connection = self._connect()
        try:
            rows = connection.execute(
                """SELECT content_key FROM cache_entries
                     WHERE state = 'valid' ORDER BY content_key LIMIT ?""",
                (limit,),
            )
            return tuple(row["content_key"] for row in rows)
        finally:
            connection.close()

    @property
    def manifest_bytes(self) -> int:
        """Return actual SQLite bytes without scanning cached objects."""
        try:
            return self.database_path.stat().st_size
        except OSError:
            return 0

    def clear(
        self,
        content_keys: tuple[str, ...] | list[str],
        *,
        protected_keys: set[str] | frozenset[str] = frozenset(),
        invalidate_publications: bool = True,
    ) -> CacheMutation:
        keys = tuple(dict.fromkeys(validate_spectrogram_content_key(key) for key in content_keys))
        protected = frozenset(
            validate_spectrogram_content_key(key) for key in protected_keys
        )
        deleted: list[str] = []
        failed: list[str] = []
        skipped: list[str] = []
        freed = 0
        with self._lock:
            if invalidate_publications:
                self._clear_epoch += 1
            for key in keys:
                if key in protected:
                    skipped.append(key)
                    continue
                row = self._row(key)
                if row is None or row["state"] != "valid":
                    continue
                try:
                    if row["relative_path"] != self._relative_path(key):
                        raise ValueError("Spectrogram cache path is unsafe.")
                    path = self.object_path(key)
                    if path.is_symlink():
                        raise ValueError("Spectrogram cache object is unsafe.")
                    path.unlink(missing_ok=True)
                    connection = self._connect()
                    try:
                        connection.execute(
                            "DELETE FROM cache_entries WHERE content_key = ?", (key,)
                        )
                        connection.commit()
                    finally:
                        connection.close()
                    deleted.append(key)
                    freed += int(row["size_bytes"])
                except (OSError, ValueError, sqlite3.Error):
                    failed.append(key)
        return CacheMutation(tuple(deleted), tuple(failed), tuple(skipped), freed)

    def evict_to_limit(
        self,
        limit_bytes: int,
        *,
        protected_keys: set[str] | frozenset[str] = frozenset(),
    ) -> CacheMutation:
        if type(limit_bytes) is not int or limit_bytes < 0:
            raise ValueError("Spectrogram cache limit is invalid.")
        protected = frozenset(
            validate_spectrogram_content_key(key) for key in protected_keys
        ).union(self._automatic_pins)
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT content_key, size_bytes FROM cache_entries
                 WHERE state = 'valid' ORDER BY last_access_ns, content_key
                """
            ).fetchall()
        finally:
            connection.close()
        total = sum(int(row["size_bytes"]) for row in rows)
        candidates: list[str] = []
        for row in rows:
            if total <= limit_bytes:
                break
            key = row["content_key"]
            if key in protected:
                continue
            candidates.append(key)
            total -= int(row["size_bytes"])
        mutation = self.clear(
            candidates,
            protected_keys=protected,
            invalidate_publications=False,
        )
        return CacheMutation(
            mutation.deleted_keys,
            mutation.failed_keys,
            tuple(sorted(protected.intersection(row["content_key"] for row in rows))),
            mutation.freed_bytes,
        )

    def reconcile(self, *, max_entries: int = 1_000) -> CacheReconciliation:
        if type(max_entries) is not int or not 1 <= max_entries <= 100_000:
            raise ValueError("Spectrogram cache reconciliation bound is invalid.")
        removed: list[str] = []
        orphans: list[str] = []
        invalid: list[str] = []
        with self._lock:
            staged = sorted(self.staging_root.iterdir(), key=lambda item: item.name)
            for path in staged[:max_entries]:
                try:
                    path.unlink()
                    removed.append(path.name)
                except OSError:
                    continue
            connection = self._connect()
            try:
                connection.execute(
                    """
                    UPDATE cache_entries SET state = 'failed', failure_code = 'worker_lost',
                        relative_path = NULL, checksum = NULL, size_bytes = NULL,
                        metadata_json = NULL, metadata_checksum = NULL
                     WHERE state = 'generating'
                    """
                )
                rows = connection.execute(
                    "SELECT content_key FROM cache_entries WHERE state = 'valid' LIMIT ?",
                    (max_entries,),
                ).fetchall()
                connection.execute(
                    """
                    DELETE FROM cache_entries
                     WHERE state = 'failed' AND content_key NOT IN (
                        SELECT content_key FROM cache_entries WHERE state = 'failed'
                         ORDER BY last_access_ns DESC LIMIT ?
                     )
                    """,
                    (max_entries,),
                )
                connection.commit()
            finally:
                connection.close()
            for row in rows:
                if self.lookup(row["content_key"]) is None:
                    invalid.append(row["content_key"])
            inspected = 0
            for shard in sorted(self.objects_root.iterdir(), key=lambda item: item.name):
                if inspected >= max_entries:
                    break
                if shard.is_symlink() or not shard.is_dir():
                    continue
                for path in sorted(shard.iterdir(), key=lambda item: item.name):
                    if inspected >= max_entries:
                        break
                    inspected += 1
                    if path.is_symlink() or not path.is_file():
                        continue
                    name = path.name
                    key = name[:-4] if name.endswith(".png") else ""
                    try:
                        validate_spectrogram_content_key(key)
                    except ValueError:
                        key = ""
                    row = self._row(key) if key else None
                    if row is not None and row["state"] == "valid":
                        continue
                    try:
                        path.unlink()
                        orphans.append(name)
                    except OSError:
                        continue
        return CacheReconciliation(tuple(removed), tuple(orphans), tuple(invalid))


__all__ = [
    "CacheEntry",
    "CacheMutation",
    "CachePublicationStale",
    "CacheReconciliation",
    "SpectrogramCache",
    "encode_rgb_png",
    "inspect_rgb_png",
]
