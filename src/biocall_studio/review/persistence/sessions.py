"""Durable transactional Review sessions, annotations, presets, and snapshots."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from biocall_studio.review.domain.intake import EligibleCandidate, ReviewIntakeProjection
from biocall_studio.review.domain.sessions import (
    DEFAULT_PRESET_ID,
    DecisionOrigin,
    FinalizedCandidateDecision,
    ReviewFinalizationSnapshot,
    ReviewLabel,
    ReviewSessionSource,
    ReviewSessionState,
    SpectrogramSettingsSnapshot,
    candidate_to_storage_tuple,
    validate_candidate_id,
    validate_display_name,
    validate_preset_id,
    validate_session_id,
    validate_timestamp,
)

_DATABASE_SCHEMA_VERSION = 1
_OWNER_ID = re.compile(r"review_owner_[0-9a-f]{32}")
_MAX_PAGE_SIZE = 1_000
_MAX_SELECTION = 1_000
_MAX_UNDO_OPERATIONS = 100


class ReviewSessionStorageError(ValueError):
    """Review session storage is unsafe, corrupt, or unsupported."""


class ReviewSessionConflict(RuntimeError):
    """A live owner, stale revision, lock, or immutable state blocked a write."""


@dataclass(frozen=True, slots=True)
class ReviewSession:
    session_id: str
    name: str
    state: ReviewSessionState
    revision: int
    owner_id: str | None
    source_digest: str
    settings_digest: str
    settings_epoch: int
    parent_session_id: str | None
    parent_snapshot_digest: str | None
    final_snapshot_digest: str | None
    eligible_candidate_count: int
    call_count: int
    not_call_count: int
    unreviewed_count: int
    created_at: str
    updated_at: str

    @property
    def partial(self) -> bool:
        return self.unreviewed_count > 0


@dataclass(frozen=True, slots=True)
class SessionMutation:
    session: ReviewSession
    changed_count: int


@dataclass(frozen=True, slots=True)
class CandidateDecisionView:
    ordinal: int
    candidate_id: str
    label: ReviewLabel
    origin: DecisionOrigin | None
    modified_at: str | None


@dataclass(frozen=True, slots=True)
class ReviewPosition:
    session_id: str
    view_revision: int
    current_candidate_id: str | None
    view: str
    filter_name: str
    scroll_offset: int
    selected_candidate_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PresetImpact:
    open_count: int
    closed_count: int
    finalized_count: int


_SCHEMA = """
CREATE TABLE presets (
    preset_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL,
    protected INTEGER NOT NULL CHECK (protected IN (0, 1)),
    current_revision INTEGER NOT NULL CHECK (current_revision >= 1),
    deleted_at TEXT
) STRICT;
CREATE UNIQUE INDEX active_preset_names ON presets(name_key) WHERE deleted_at IS NULL;

CREATE TABLE preset_revisions (
    preset_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    snapshot_json TEXT NOT NULL,
    settings_digest TEXT NOT NULL,
    saved_at TEXT NOT NULL,
    PRIMARY KEY (preset_id, revision),
    FOREIGN KEY (preset_id) REFERENCES presets(preset_id) ON DELETE RESTRICT
) STRICT;

CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('open', 'closed', 'finalized')),
    revision INTEGER NOT NULL CHECK (revision >= 0),
    owner_id TEXT,
    source_json TEXT NOT NULL,
    source_digest TEXT NOT NULL,
    collection_id TEXT NOT NULL,
    result_id TEXT NOT NULL,
    projection_digest TEXT NOT NULL,
    settings_json TEXT NOT NULL,
    settings_digest TEXT NOT NULL,
    settings_preset_id TEXT NOT NULL,
    settings_preset_revision INTEGER NOT NULL,
    settings_epoch INTEGER NOT NULL CHECK (settings_epoch >= 1),
    parent_session_id TEXT,
    parent_snapshot_digest TEXT,
    final_snapshot_digest TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT,
    finalized_at TEXT,
    FOREIGN KEY (parent_session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT
) STRICT;
CREATE UNIQUE INDEX one_open_review_session ON sessions((1)) WHERE state = 'open';
CREATE INDEX sessions_by_preset ON sessions(settings_preset_id, state);

CREATE TABLE session_candidates (
    session_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    recording_ordinal INTEGER NOT NULL,
    candidate_id TEXT NOT NULL,
    recording_ref TEXT NOT NULL,
    recording_key TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    sample_rate_hz INTEGER NOT NULL,
    frame_count INTEGER NOT NULL,
    channels INTEGER NOT NULL,
    start_frame INTEGER NOT NULL,
    end_frame INTEGER NOT NULL,
    start_time_ns INTEGER NOT NULL,
    end_time_ns INTEGER NOT NULL,
    cnn_target_score REAL NOT NULL,
    rf_target_score REAL,
    contributing_windows INTEGER NOT NULL,
    PRIMARY KEY (session_id, ordinal),
    UNIQUE (session_id, candidate_id),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT
) STRICT;

CREATE TABLE operations (
    operation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('individual', 'accept_all')),
    applied INTEGER NOT NULL CHECK (applied IN (0, 1)),
    changed_count INTEGER NOT NULL CHECK (changed_count >= 1),
    action_at TEXT NOT NULL,
    last_transition_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT
) STRICT;
CREATE INDEX operations_by_session ON operations(session_id, operation_id);

CREATE TABLE decisions (
    session_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    label TEXT NOT NULL CHECK (label IN ('call', 'not_call')),
    origin TEXT NOT NULL CHECK (origin IN ('individual', 'bulk')),
    modified_at TEXT NOT NULL,
    operation_id INTEGER,
    PRIMARY KEY (session_id, candidate_id),
    FOREIGN KEY (session_id, candidate_id)
        REFERENCES session_candidates(session_id, candidate_id) ON DELETE RESTRICT,
    FOREIGN KEY (operation_id) REFERENCES operations(operation_id) ON DELETE SET NULL
) STRICT;

CREATE TABLE operation_changes (
    operation_id INTEGER NOT NULL,
    candidate_id TEXT NOT NULL,
    before_label TEXT,
    before_origin TEXT,
    before_modified_at TEXT,
    before_operation_id INTEGER,
    after_label TEXT,
    after_origin TEXT,
    after_modified_at TEXT,
    PRIMARY KEY (operation_id, candidate_id),
    FOREIGN KEY (operation_id) REFERENCES operations(operation_id) ON DELETE CASCADE
) STRICT;

CREATE TABLE finalizations (
    session_id TEXT PRIMARY KEY,
    snapshot_json TEXT NOT NULL,
    snapshot_digest TEXT NOT NULL UNIQUE,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT
) STRICT;

CREATE TABLE session_views (
    session_id TEXT PRIMARY KEY,
    view_revision INTEGER NOT NULL CHECK (view_revision >= 0),
    current_candidate_id TEXT,
    view_name TEXT NOT NULL,
    filter_name TEXT NOT NULL,
    scroll_offset INTEGER NOT NULL CHECK (scroll_offset >= 0),
    selection_json TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT
) STRICT;
"""


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _owner(value: object) -> str:
    if not isinstance(value, str) or _OWNER_ID.fullmatch(value) is None:
        raise ValueError("Review session owner ID is invalid.")
    return value


class ReviewSessionStore:
    """One contained SQLite store for editable sessions and immutable snapshots."""

    def __init__(self, root: Path, *, busy_timeout_seconds: float = 1.0):
        requested = Path(root).expanduser()
        if requested.is_symlink():
            raise ReviewSessionStorageError("Review application-data root cannot be a symlink.")
        self.root = requested.resolve(strict=False)
        self.database_path = self.root / "sessions.sqlite3"
        if not isinstance(busy_timeout_seconds, (int, float)) or not 0 < busy_timeout_seconds <= 30:
            raise ValueError("Review database busy timeout is invalid.")
        self.busy_timeout_seconds = float(busy_timeout_seconds)
        self._schema_checked = False

    def _ensure_root(self) -> None:
        for path in (self.root.parent, self.root):
            if path.is_symlink():
                raise ReviewSessionStorageError(
                    "Review application-data directories cannot be symbolic links."
                )
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise ReviewSessionStorageError("Review application-data root is unsafe.")
        self.root.chmod(0o700)
        if self.database_path.is_symlink():
            raise ReviewSessionStorageError("Review session database cannot be a symlink.")

    def _connect(self) -> sqlite3.Connection:
        self._ensure_root()
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                self.database_path,
                timeout=self.busy_timeout_seconds,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA journal_mode = DELETE")
            connection.execute("PRAGMA synchronous = FULL")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                connection.executescript(_SCHEMA)
                connection.execute(f"PRAGMA user_version = {_DATABASE_SCHEMA_VERSION}")
            elif version != _DATABASE_SCHEMA_VERSION:
                raise ReviewSessionStorageError("Review session database schema is unsupported.")
            if not self._schema_checked:
                check = connection.execute("PRAGMA quick_check").fetchone()[0]
                if check != "ok":
                    raise ReviewSessionStorageError(
                        "Review session database integrity check failed."
                    )
                self._schema_checked = True
            os.chmod(self.database_path, 0o600)
            return connection
        except sqlite3.OperationalError as exc:
            if connection is not None:
                connection.close()
            if "locked" in str(exc).casefold() or "busy" in str(exc).casefold():
                raise ReviewSessionConflict("Review session database is busy or locked.") from exc
            raise ReviewSessionStorageError("Review session database could not be opened.") from exc
        except sqlite3.DatabaseError as exc:
            if connection is not None:
                connection.close()
            raise ReviewSessionStorageError("Review session database is corrupt.") from exc

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            detail = str(exc).casefold()
            if "one_open_review_session" in detail or "unique constraint" in detail:
                raise ReviewSessionConflict(
                    "Only one Open Review session is allowed. Close it before opening another."
                ) from exc
            raise ReviewSessionStorageError(
                "Review session transaction violated storage integrity."
            ) from exc
        except sqlite3.OperationalError as exc:
            connection.rollback()
            if "locked" in str(exc).casefold() or "busy" in str(exc).casefold():
                raise ReviewSessionConflict("Review session database is busy or locked.") from exc
            raise ReviewSessionStorageError("Review session transaction failed.") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _snapshot_json(snapshot: SpectrogramSettingsSnapshot) -> str:
        return _canonical(snapshot.to_dict())

    @staticmethod
    def _source_json(source: ReviewSessionSource) -> str:
        return _canonical(source.to_dict())

    @staticmethod
    def _preset_name_key(name: str) -> str:
        return validate_display_name(name, "Spectrogram preset name").casefold()

    def _preset_in_connection(
        self,
        connection: sqlite3.Connection,
        preset_id: str,
        revision: int,
        *,
        active_required: bool,
    ) -> SpectrogramSettingsSnapshot:
        row = connection.execute(
            """
            SELECT p.deleted_at, p.current_revision, r.snapshot_json
              FROM presets p
              JOIN preset_revisions r
                ON r.preset_id = p.preset_id AND r.revision = ?
             WHERE p.preset_id = ?
            """,
            (revision, preset_id),
        ).fetchone()
        if row is None or (active_required and row["deleted_at"] is not None):
            raise KeyError("Spectrogram preset or revision is unavailable.")
        return SpectrogramSettingsSnapshot.from_dict(json.loads(row["snapshot_json"]))

    def ensure_default_preset(
        self, snapshot: SpectrogramSettingsSnapshot, *, saved_at: str
    ) -> SpectrogramSettingsSnapshot:
        if snapshot.preset_id != DEFAULT_PRESET_ID or snapshot.preset_name != "Default":
            raise ValueError("The protected Default preset has a fixed identity and name.")
        if snapshot.preset_revision != 1:
            raise ValueError("The protected Default preset begins at revision 1.")
        validate_timestamp(saved_at, "Spectrogram preset timestamp")
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT current_revision, deleted_at FROM presets WHERE preset_id = ?",
                (DEFAULT_PRESET_ID,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO presets VALUES (?, ?, ?, 1, 1, NULL)",
                    (DEFAULT_PRESET_ID, "Default", "default"),
                )
                connection.execute(
                    "INSERT INTO preset_revisions VALUES (?, 1, ?, ?, ?)",
                    (
                        DEFAULT_PRESET_ID,
                        self._snapshot_json(snapshot),
                        snapshot.settings_digest,
                        saved_at,
                    ),
                )
            else:
                stored = self._preset_in_connection(
                    connection, DEFAULT_PRESET_ID, 1, active_required=True
                )
                if stored != snapshot or existing["current_revision"] != 1:
                    raise ReviewSessionStorageError(
                        "The protected Default preset differs from its stored definition."
                    )
        return snapshot

    def create_preset(
        self,
        *,
        name: str,
        algorithm_version: str,
        render_version: str,
        effective_settings: object,
        saved_at: str,
        preset_id: str | None = None,
    ) -> SpectrogramSettingsSnapshot:
        preset_id = preset_id or f"rsp_{uuid.uuid4().hex}"
        validate_preset_id(preset_id)
        if preset_id == DEFAULT_PRESET_ID:
            raise ValueError("Use ensure_default_preset for the protected Default.")
        validate_timestamp(saved_at, "Spectrogram preset timestamp")
        snapshot = SpectrogramSettingsSnapshot.create(
            preset_id=preset_id,
            preset_name=name,
            preset_revision=1,
            algorithm_version=algorithm_version,
            render_version=render_version,
            effective_settings=effective_settings,
        )
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO presets VALUES (?, ?, ?, 0, 1, NULL)",
                (preset_id, name, self._preset_name_key(name)),
            )
            connection.execute(
                "INSERT INTO preset_revisions VALUES (?, 1, ?, ?, ?)",
                (preset_id, self._snapshot_json(snapshot), snapshot.settings_digest, saved_at),
            )
        return snapshot

    def update_preset(
        self,
        preset_id: str,
        *,
        expected_revision: int,
        name: str,
        algorithm_version: str,
        render_version: str,
        effective_settings: object,
        saved_at: str,
    ) -> SpectrogramSettingsSnapshot:
        validate_preset_id(preset_id)
        if preset_id == DEFAULT_PRESET_ID:
            raise ReviewSessionConflict("The protected Default preset cannot be edited.")
        validate_timestamp(saved_at, "Spectrogram preset timestamp")
        next_revision = expected_revision + 1
        snapshot = SpectrogramSettingsSnapshot.create(
            preset_id=preset_id,
            preset_name=name,
            preset_revision=next_revision,
            algorithm_version=algorithm_version,
            render_version=render_version,
            effective_settings=effective_settings,
        )
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT protected, current_revision, deleted_at FROM presets WHERE preset_id = ?",
                (preset_id,),
            ).fetchone()
            if row is None or row["deleted_at"] is not None:
                raise KeyError("Spectrogram preset is unavailable.")
            if row["protected"]:
                raise ReviewSessionConflict("The protected Default preset cannot be edited.")
            if row["current_revision"] != expected_revision:
                raise ReviewSessionConflict("Spectrogram preset revision changed.")
            connection.execute(
                "INSERT INTO preset_revisions VALUES (?, ?, ?, ?, ?)",
                (
                    preset_id,
                    next_revision,
                    self._snapshot_json(snapshot),
                    snapshot.settings_digest,
                    saved_at,
                ),
            )
            connection.execute(
                """
                UPDATE presets SET name = ?, name_key = ?, current_revision = ?
                 WHERE preset_id = ?
                """,
                (name, self._preset_name_key(name), next_revision, preset_id),
            )
        return snapshot

    def delete_preset(self, preset_id: str, *, expected_revision: int, deleted_at: str) -> None:
        validate_preset_id(preset_id)
        validate_timestamp(deleted_at, "Spectrogram preset deletion timestamp")
        if preset_id == DEFAULT_PRESET_ID:
            raise ReviewSessionConflict("The protected Default preset cannot be deleted.")
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT protected, current_revision, deleted_at FROM presets WHERE preset_id = ?",
                (preset_id,),
            ).fetchone()
            if row is None or row["deleted_at"] is not None:
                raise KeyError("Spectrogram preset is unavailable.")
            if row["protected"]:
                raise ReviewSessionConflict("The protected Default preset cannot be deleted.")
            if row["current_revision"] != expected_revision:
                raise ReviewSessionConflict("Spectrogram preset revision changed.")
            connection.execute(
                "UPDATE presets SET deleted_at = ? WHERE preset_id = ?",
                (deleted_at, preset_id),
            )

    def preset_impact(self, preset_id: str) -> PresetImpact:
        validate_preset_id(preset_id)
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT
                    SUM(CASE WHEN state = 'open' THEN 1 ELSE 0 END) AS open_count,
                    SUM(CASE WHEN state = 'closed' THEN 1 ELSE 0 END) AS closed_count,
                    SUM(CASE WHEN state = 'finalized' THEN 1 ELSE 0 END) AS finalized_count
                  FROM sessions WHERE settings_preset_id = ?
                """,
                (preset_id,),
            ).fetchone()
            return PresetImpact(
                int(row["open_count"] or 0),
                int(row["closed_count"] or 0),
                int(row["finalized_count"] or 0),
            )
        finally:
            connection.close()

    @staticmethod
    def _session_from_row(row: sqlite3.Row) -> ReviewSession:
        return ReviewSession(
            session_id=row["session_id"],
            name=row["name"],
            state=ReviewSessionState(row["state"]),
            revision=row["revision"],
            owner_id=row["owner_id"],
            source_digest=row["source_digest"],
            settings_digest=row["settings_digest"],
            settings_epoch=row["settings_epoch"],
            parent_session_id=row["parent_session_id"],
            parent_snapshot_digest=row["parent_snapshot_digest"],
            final_snapshot_digest=row["final_snapshot_digest"],
            eligible_candidate_count=row["eligible_candidate_count"],
            call_count=row["call_count"],
            not_call_count=row["not_call_count"],
            unreviewed_count=row["eligible_candidate_count"]
            - row["call_count"]
            - row["not_call_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _session_select() -> str:
        return """
        SELECT s.*,
               (SELECT COUNT(*) FROM session_candidates c
                 WHERE c.session_id = s.session_id) AS eligible_candidate_count,
               (SELECT COUNT(*) FROM decisions d
                 WHERE d.session_id = s.session_id AND d.label = 'call') AS call_count,
               (SELECT COUNT(*) FROM decisions d
                 WHERE d.session_id = s.session_id AND d.label = 'not_call') AS not_call_count
          FROM sessions s
        """

    def get_session(self, session_id: str) -> ReviewSession:
        validate_session_id(session_id)
        connection = self._connect()
        try:
            row = connection.execute(
                self._session_select() + " WHERE s.session_id = ?", (session_id,)
            ).fetchone()
            if row is None:
                raise KeyError("Review session does not exist.")
            return self._session_from_row(row)
        finally:
            connection.close()

    def open_session(self) -> ReviewSession | None:
        connection = self._connect()
        try:
            row = connection.execute(self._session_select() + " WHERE s.state = 'open'").fetchone()
            return None if row is None else self._session_from_row(row)
        finally:
            connection.close()

    def _session_row(self, connection: sqlite3.Connection, session_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise KeyError("Review session does not exist.")
        return row

    @staticmethod
    def _require_open(row: sqlite3.Row, *, owner_id: str, expected_revision: int) -> None:
        if row["state"] is not None and row["state"] == ReviewSessionState.FINALIZED.value:
            raise ReviewSessionConflict("A Finalized Review session is immutable.")
        if row["state"] != ReviewSessionState.OPEN.value:
            raise ReviewSessionConflict("Review session must be Open before it can be edited.")
        if row["owner_id"] != owner_id:
            raise ReviewSessionConflict("Review session belongs to another live owner.")
        if row["revision"] != expected_revision:
            raise ReviewSessionConflict("Review session revision changed.")

    def create_session(
        self,
        *,
        name: str,
        source: ReviewSessionSource,
        candidates: tuple[EligibleCandidate, ...],
        settings: SpectrogramSettingsSnapshot,
        owner_id: str,
        created_at: str,
        session_id: str | None = None,
    ) -> ReviewSession:
        validate_display_name(name, "Review session name")
        owner_id = _owner(owner_id)
        validate_timestamp(created_at, "Review session creation timestamp")
        session_id = session_id or f"rsn_{uuid.uuid4().hex}"
        validate_session_id(session_id)
        if not isinstance(source, ReviewSessionSource) or not isinstance(
            settings, SpectrogramSettingsSnapshot
        ):
            raise ValueError("Review session source or settings are invalid.")
        candidates = tuple(candidates)
        ReviewIntakeProjection(source.manifest, source.recordings, candidates)
        with self._transaction() as connection:
            stored_settings = self._preset_in_connection(
                connection,
                settings.preset_id,
                settings.preset_revision,
                active_required=True,
            )
            if stored_settings != settings:
                raise ReviewSessionStorageError(
                    "Selected spectrogram settings do not match the saved preset revision."
                )
            connection.execute(
                """
                INSERT INTO sessions (
                    session_id, name, state, revision, owner_id, source_json,
                    source_digest, collection_id, result_id, projection_digest,
                    settings_json, settings_digest, settings_preset_id,
                    settings_preset_revision, settings_epoch, parent_session_id,
                    parent_snapshot_digest, final_snapshot_digest, created_at,
                    updated_at, closed_at, finalized_at
                ) VALUES (
                    ?, ?, 'open', 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1,
                    NULL, NULL, NULL, ?, ?, NULL, NULL
                )
                """,
                (
                    session_id,
                    name,
                    owner_id,
                    self._source_json(source),
                    source.source_digest,
                    source.manifest.collection_id,
                    source.manifest.result_id,
                    source.manifest.projection_digest,
                    self._snapshot_json(settings),
                    settings.settings_digest,
                    settings.preset_id,
                    settings.preset_revision,
                    created_at,
                    created_at,
                ),
            )
            connection.executemany(
                """
                INSERT INTO session_candidates VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                ((session_id, *candidate_to_storage_tuple(row)) for row in candidates),
            )
            first_id = None if not candidates else candidates[0].candidate_id
            connection.execute(
                "INSERT INTO session_views VALUES (?, 0, ?, 'gallery', 'all', 0, '[]')",
                (session_id, first_id),
            )
        return self.get_session(session_id)

    def _truncate_redo(self, connection: sqlite3.Connection, session_id: str) -> None:
        connection.execute(
            "DELETE FROM operations WHERE session_id = ? AND applied = 0", (session_id,)
        )

    def _prune_history(self, connection: sqlite3.Connection, session_id: str) -> None:
        connection.execute(
            """
            DELETE FROM operations
             WHERE session_id = ? AND applied = 1 AND operation_id NOT IN (
                SELECT operation_id FROM operations
                 WHERE session_id = ? AND applied = 1
                 ORDER BY operation_id DESC LIMIT ?
             )
            """,
            (session_id, session_id, _MAX_UNDO_OPERATIONS),
        )

    def set_label(
        self,
        session_id: str,
        candidate_id: str,
        label: ReviewLabel,
        *,
        owner_id: str,
        expected_revision: int,
        modified_at: str,
    ) -> SessionMutation:
        validate_session_id(session_id)
        validate_candidate_id(candidate_id)
        owner_id = _owner(owner_id)
        if not isinstance(label, ReviewLabel):
            raise ValueError("Review label is invalid.")
        validate_timestamp(modified_at, "Review decision timestamp")
        changed = 0
        with self._transaction() as connection:
            session = self._session_row(connection, session_id)
            self._require_open(session, owner_id=owner_id, expected_revision=expected_revision)
            exists = connection.execute(
                "SELECT 1 FROM session_candidates WHERE session_id = ? AND candidate_id = ?",
                (session_id, candidate_id),
            ).fetchone()
            if exists is None:
                raise KeyError("Candidate is not eligible for this Review session.")
            before = connection.execute(
                "SELECT * FROM decisions WHERE session_id = ? AND candidate_id = ?",
                (session_id, candidate_id),
            ).fetchone()
            desired = None if label is ReviewLabel.UNREVIEWED else label.value
            if before is None and desired is None:
                return SessionMutation(self.get_session(session_id), 0)
            if (
                before is not None
                and before["label"] == desired
                and before["origin"] == DecisionOrigin.INDIVIDUAL.value
            ):
                return SessionMutation(self.get_session(session_id), 0)
            self._truncate_redo(connection, session_id)
            operation_id = connection.execute(
                """
                INSERT INTO operations(session_id, kind, applied, changed_count, action_at,
                                       last_transition_at)
                VALUES (?, 'individual', 1, 1, ?, ?) RETURNING operation_id
                """,
                (session_id, modified_at, modified_at),
            ).fetchone()[0]
            after_origin = None if desired is None else DecisionOrigin.INDIVIDUAL.value
            after_modified = None if desired is None else modified_at
            connection.execute(
                """
                INSERT INTO operation_changes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    operation_id,
                    candidate_id,
                    None if before is None else before["label"],
                    None if before is None else before["origin"],
                    None if before is None else before["modified_at"],
                    None if before is None else before["operation_id"],
                    desired,
                    after_origin,
                    after_modified,
                ),
            )
            if desired is None:
                connection.execute(
                    "DELETE FROM decisions WHERE session_id = ? AND candidate_id = ?",
                    (session_id, candidate_id),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO decisions VALUES (?, ?, ?, 'individual', ?, ?)
                    ON CONFLICT(session_id, candidate_id) DO UPDATE SET
                        label = excluded.label,
                        origin = excluded.origin,
                        modified_at = excluded.modified_at,
                        operation_id = excluded.operation_id
                    """,
                    (session_id, candidate_id, desired, modified_at, operation_id),
                )
            connection.execute(
                "UPDATE sessions SET revision = revision + 1, updated_at = ? WHERE session_id = ?",
                (modified_at, session_id),
            )
            self._prune_history(connection, session_id)
            changed = 1
        return SessionMutation(self.get_session(session_id), changed)

    def accept_all(
        self,
        session_id: str,
        *,
        owner_id: str,
        expected_revision: int,
        modified_at: str,
    ) -> SessionMutation:
        validate_session_id(session_id)
        owner_id = _owner(owner_id)
        validate_timestamp(modified_at, "Review bulk decision timestamp")
        changed = 0
        with self._transaction() as connection:
            session = self._session_row(connection, session_id)
            self._require_open(session, owner_id=owner_id, expected_revision=expected_revision)
            changed = connection.execute(
                """
                SELECT COUNT(*) FROM session_candidates c
                 WHERE c.session_id = ? AND NOT EXISTS (
                    SELECT 1 FROM decisions d
                     WHERE d.session_id = c.session_id AND d.candidate_id = c.candidate_id
                 )
                """,
                (session_id,),
            ).fetchone()[0]
            if not changed:
                return SessionMutation(self.get_session(session_id), 0)
            self._truncate_redo(connection, session_id)
            operation_id = connection.execute(
                """
                INSERT INTO operations(session_id, kind, applied, changed_count, action_at,
                                       last_transition_at)
                VALUES (?, 'accept_all', 1, ?, ?, ?) RETURNING operation_id
                """,
                (session_id, changed, modified_at, modified_at),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO decisions(session_id, candidate_id, label, origin, modified_at,
                                      operation_id)
                SELECT c.session_id, c.candidate_id, 'call', 'bulk', ?, ?
                  FROM session_candidates c
                 WHERE c.session_id = ? AND NOT EXISTS (
                    SELECT 1 FROM decisions d
                     WHERE d.session_id = c.session_id AND d.candidate_id = c.candidate_id
                 )
                """,
                (modified_at, operation_id, session_id),
            )
            connection.execute(
                "UPDATE sessions SET revision = revision + 1, updated_at = ? WHERE session_id = ?",
                (modified_at, session_id),
            )
            self._prune_history(connection, session_id)
        return SessionMutation(self.get_session(session_id), changed)

    @staticmethod
    def _decision_matches(row: sqlite3.Row | None, prefix: str, change: sqlite3.Row) -> bool:
        label = change[f"{prefix}_label"]
        if label is None:
            return row is None
        operation_id = (
            change["before_operation_id"]
            if prefix == "before"
            else change["operation_id"]
        )
        return bool(
            row is not None
            and row["label"] == label
            and row["origin"] == change[f"{prefix}_origin"]
            and row["modified_at"] == change[f"{prefix}_modified_at"]
            and row["operation_id"] == operation_id
        )

    @staticmethod
    def _restore_decision(
        connection: sqlite3.Connection,
        session_id: str,
        change: sqlite3.Row,
        prefix: str,
    ) -> None:
        label = change[f"{prefix}_label"]
        candidate_id = change["candidate_id"]
        if label is None:
            connection.execute(
                "DELETE FROM decisions WHERE session_id = ? AND candidate_id = ?",
                (session_id, candidate_id),
            )
            return
        connection.execute(
            """
            INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, candidate_id) DO UPDATE SET
                label = excluded.label,
                origin = excluded.origin,
                modified_at = excluded.modified_at,
                operation_id = excluded.operation_id
            """,
            (
                session_id,
                candidate_id,
                label,
                change[f"{prefix}_origin"],
                change[f"{prefix}_modified_at"],
                (
                    change["before_operation_id"]
                    if prefix == "before"
                    else change["operation_id"]
                ),
            ),
        )

    def undo(
        self,
        session_id: str,
        *,
        owner_id: str,
        expected_revision: int,
        modified_at: str,
    ) -> SessionMutation:
        validate_session_id(session_id)
        owner_id = _owner(owner_id)
        validate_timestamp(modified_at, "Review undo timestamp")
        with self._transaction() as connection:
            session = self._session_row(connection, session_id)
            self._require_open(session, owner_id=owner_id, expected_revision=expected_revision)
            operation = connection.execute(
                """
                SELECT * FROM operations
                 WHERE session_id = ? AND applied = 1
                 ORDER BY operation_id DESC LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if operation is None:
                raise ReviewSessionConflict("There is no Review annotation action to undo.")
            if operation["kind"] == "accept_all":
                changed = connection.execute(
                    "DELETE FROM decisions WHERE session_id = ? AND operation_id = ?",
                    (session_id, operation["operation_id"]),
                ).rowcount
                if changed != operation["changed_count"]:
                    raise ReviewSessionConflict("Review bulk history is no longer applicable.")
            else:
                change = connection.execute(
                    "SELECT * FROM operation_changes WHERE operation_id = ?",
                    (operation["operation_id"],),
                ).fetchone()
                current = connection.execute(
                    "SELECT * FROM decisions WHERE session_id = ? AND candidate_id = ?",
                    (session_id, change["candidate_id"]),
                ).fetchone()
                if not self._decision_matches(current, "after", change):
                    raise ReviewSessionConflict(
                        "Review annotation history is no longer applicable."
                    )
                self._restore_decision(connection, session_id, change, "before")
                changed = 1
            connection.execute(
                "UPDATE operations SET applied = 0, last_transition_at = ? WHERE operation_id = ?",
                (modified_at, operation["operation_id"]),
            )
            connection.execute(
                "UPDATE sessions SET revision = revision + 1, updated_at = ? WHERE session_id = ?",
                (modified_at, session_id),
            )
        return SessionMutation(self.get_session(session_id), changed)

    def redo(
        self,
        session_id: str,
        *,
        owner_id: str,
        expected_revision: int,
        modified_at: str,
    ) -> SessionMutation:
        validate_session_id(session_id)
        owner_id = _owner(owner_id)
        validate_timestamp(modified_at, "Review redo timestamp")
        with self._transaction() as connection:
            session = self._session_row(connection, session_id)
            self._require_open(session, owner_id=owner_id, expected_revision=expected_revision)
            operation = connection.execute(
                """
                SELECT * FROM operations
                 WHERE session_id = ? AND applied = 0
                 ORDER BY operation_id ASC LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if operation is None:
                raise ReviewSessionConflict("There is no Review annotation action to redo.")
            later = connection.execute(
                """
                SELECT 1 FROM operations
                 WHERE session_id = ? AND applied = 1 AND operation_id > ? LIMIT 1
                """,
                (session_id, operation["operation_id"]),
            ).fetchone()
            if later is not None:
                raise ReviewSessionConflict("Review redo history is no longer applicable.")
            if operation["kind"] == "accept_all":
                changed = connection.execute(
                    """
                    INSERT INTO decisions(session_id, candidate_id, label, origin, modified_at,
                                          operation_id)
                    SELECT c.session_id, c.candidate_id, 'call', 'bulk', ?, ?
                      FROM session_candidates c
                     WHERE c.session_id = ? AND NOT EXISTS (
                        SELECT 1 FROM decisions d
                         WHERE d.session_id = c.session_id
                           AND d.candidate_id = c.candidate_id
                     )
                    """,
                    (modified_at, operation["operation_id"], session_id),
                ).rowcount
                if changed != operation["changed_count"]:
                    raise ReviewSessionConflict("Review bulk redo history is no longer applicable.")
            else:
                change = connection.execute(
                    "SELECT * FROM operation_changes WHERE operation_id = ?",
                    (operation["operation_id"],),
                ).fetchone()
                current = connection.execute(
                    "SELECT * FROM decisions WHERE session_id = ? AND candidate_id = ?",
                    (session_id, change["candidate_id"]),
                ).fetchone()
                if not self._decision_matches(current, "before", change):
                    raise ReviewSessionConflict(
                        "Review annotation redo history is no longer applicable."
                    )
                if change["after_label"] is None:
                    self._restore_decision(connection, session_id, change, "after")
                else:
                    connection.execute(
                        """
                        INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(session_id, candidate_id) DO UPDATE SET
                            label = excluded.label,
                            origin = excluded.origin,
                            modified_at = excluded.modified_at,
                            operation_id = excluded.operation_id
                        """,
                        (
                            session_id,
                            change["candidate_id"],
                            change["after_label"],
                            change["after_origin"],
                            modified_at,
                            operation["operation_id"],
                        ),
                    )
                    connection.execute(
                        """
                        UPDATE operation_changes SET after_modified_at = ?
                         WHERE operation_id = ? AND candidate_id = ?
                        """,
                        (
                            modified_at,
                            operation["operation_id"],
                            change["candidate_id"],
                        ),
                    )
                changed = 1
            connection.execute(
                "UPDATE operations SET applied = 1, last_transition_at = ? WHERE operation_id = ?",
                (modified_at, operation["operation_id"]),
            )
            connection.execute(
                "UPDATE sessions SET revision = revision + 1, updated_at = ? WHERE session_id = ?",
                (modified_at, session_id),
            )
        return SessionMutation(self.get_session(session_id), changed)

    def decision_page(
        self, session_id: str, *, offset: int, limit: int
    ) -> tuple[CandidateDecisionView, ...]:
        validate_session_id(session_id)
        if type(offset) is not int or offset < 0:
            raise ValueError("Review page offset is invalid.")
        if type(limit) is not int or not 1 <= limit <= _MAX_PAGE_SIZE:
            raise ValueError("Review page size is invalid.")
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT c.ordinal, c.candidate_id, d.label, d.origin, d.modified_at
                  FROM session_candidates c
                  LEFT JOIN decisions d
                    ON d.session_id = c.session_id AND d.candidate_id = c.candidate_id
                 WHERE c.session_id = ? ORDER BY c.ordinal LIMIT ? OFFSET ?
                """,
                (session_id, limit, offset),
            )
            return tuple(
                CandidateDecisionView(
                    ordinal=row["ordinal"],
                    candidate_id=row["candidate_id"],
                    label=(
                        ReviewLabel.UNREVIEWED
                        if row["label"] is None
                        else ReviewLabel(row["label"])
                    ),
                    origin=(None if row["origin"] is None else DecisionOrigin(row["origin"])),
                    modified_at=row["modified_at"],
                )
                for row in rows
            )
        finally:
            connection.close()

    def annotation_digest(self, session_id: str) -> str:
        validate_session_id(session_id)
        digest = hashlib.sha256(b"biocall-review-annotations-v1\n")
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT c.ordinal, c.candidate_id, d.label, d.origin, d.modified_at
                  FROM session_candidates c LEFT JOIN decisions d
                    ON d.session_id = c.session_id AND d.candidate_id = c.candidate_id
                 WHERE c.session_id = ? ORDER BY c.ordinal
                """,
                (session_id,),
            )
            for row in rows:
                digest.update((_canonical(dict(row)) + "\n").encode("utf-8"))
            return digest.hexdigest()
        finally:
            connection.close()

    def close_session(
        self,
        session_id: str,
        *,
        owner_id: str,
        expected_revision: int,
        closed_at: str,
    ) -> ReviewSession:
        validate_session_id(session_id)
        owner_id = _owner(owner_id)
        validate_timestamp(closed_at, "Review close timestamp")
        with self._transaction() as connection:
            row = self._session_row(connection, session_id)
            self._require_open(row, owner_id=owner_id, expected_revision=expected_revision)
            connection.execute(
                """
                UPDATE sessions SET state = 'closed', owner_id = NULL,
                    revision = revision + 1, updated_at = ?, closed_at = ?
                 WHERE session_id = ?
                """,
                (closed_at, closed_at, session_id),
            )
        return self.get_session(session_id)

    def resume_session(
        self,
        session_id: str,
        *,
        owner_id: str,
        expected_revision: int,
        resumed_at: str,
    ) -> ReviewSession:
        validate_session_id(session_id)
        owner_id = _owner(owner_id)
        validate_timestamp(resumed_at, "Review resume timestamp")
        with self._transaction() as connection:
            row = self._session_row(connection, session_id)
            if row["state"] == ReviewSessionState.FINALIZED.value:
                raise ReviewSessionConflict(
                    "A Finalized Review session cannot resume; continue in a new session."
                )
            if row["state"] != ReviewSessionState.CLOSED.value:
                raise ReviewSessionConflict("Only a Closed Review session can resume.")
            if row["revision"] != expected_revision:
                raise ReviewSessionConflict("Review session revision changed.")
            connection.execute(
                """
                UPDATE sessions SET state = 'open', owner_id = ?, revision = revision + 1,
                    updated_at = ?, closed_at = NULL WHERE session_id = ?
                """,
                (owner_id, resumed_at, session_id),
            )
        return self.get_session(session_id)

    def claim_orphaned_open_session(
        self,
        session_id: str,
        *,
        previous_owner_id: str,
        owner_id: str,
        expected_revision: int,
        claimed_at: str,
    ) -> ReviewSession:
        validate_session_id(session_id)
        previous_owner_id = _owner(previous_owner_id)
        owner_id = _owner(owner_id)
        validate_timestamp(claimed_at, "Review recovery timestamp")
        with self._transaction() as connection:
            row = self._session_row(connection, session_id)
            if (
                row["state"] != ReviewSessionState.OPEN.value
                or row["owner_id"] != previous_owner_id
                or row["revision"] != expected_revision
            ):
                raise ReviewSessionConflict("Open Review session ownership changed.")
            connection.execute(
                """
                UPDATE sessions SET owner_id = ?, revision = revision + 1, updated_at = ?
                 WHERE session_id = ?
                """,
                (owner_id, claimed_at, session_id),
            )
        return self.get_session(session_id)

    def change_settings(
        self,
        session_id: str,
        settings: SpectrogramSettingsSnapshot,
        *,
        owner_id: str,
        expected_revision: int,
        expected_settings_epoch: int,
        changed_at: str,
    ) -> ReviewSession:
        validate_session_id(session_id)
        owner_id = _owner(owner_id)
        validate_timestamp(changed_at, "Review settings change timestamp")
        if not isinstance(settings, SpectrogramSettingsSnapshot):
            raise ValueError("Review spectrogram settings are invalid.")
        with self._transaction() as connection:
            row = self._session_row(connection, session_id)
            self._require_open(row, owner_id=owner_id, expected_revision=expected_revision)
            if row["settings_epoch"] != expected_settings_epoch:
                raise ReviewSessionConflict("Review settings revision changed.")
            stored = self._preset_in_connection(
                connection,
                settings.preset_id,
                settings.preset_revision,
                active_required=True,
            )
            if stored != settings:
                raise ReviewSessionStorageError(
                    "Selected spectrogram settings do not match the saved preset revision."
                )
            connection.execute(
                """
                UPDATE sessions SET settings_json = ?, settings_digest = ?,
                    settings_preset_id = ?, settings_preset_revision = ?,
                    settings_epoch = settings_epoch + 1, revision = revision + 1,
                    updated_at = ? WHERE session_id = ?
                """,
                (
                    self._snapshot_json(settings),
                    settings.settings_digest,
                    settings.preset_id,
                    settings.preset_revision,
                    changed_at,
                    session_id,
                ),
            )
        return self.get_session(session_id)

    def rename_session(
        self,
        session_id: str,
        name: str,
        *,
        owner_id: str,
        expected_revision: int,
        renamed_at: str,
    ) -> ReviewSession:
        validate_session_id(session_id)
        validate_display_name(name, "Review session name")
        owner_id = _owner(owner_id)
        validate_timestamp(renamed_at, "Review session rename timestamp")
        with self._transaction() as connection:
            row = self._session_row(connection, session_id)
            self._require_open(row, owner_id=owner_id, expected_revision=expected_revision)
            connection.execute(
                """
                UPDATE sessions SET name = ?, revision = revision + 1, updated_at = ?
                 WHERE session_id = ?
                """,
                (name, renamed_at, session_id),
            )
        return self.get_session(session_id)

    def load_settings(self, session_id: str) -> SpectrogramSettingsSnapshot:
        validate_session_id(session_id)
        connection = self._connect()
        try:
            row = self._session_row(connection, session_id)
            return SpectrogramSettingsSnapshot.from_dict(json.loads(row["settings_json"]))
        finally:
            connection.close()

    def load_source(self, session_id: str) -> ReviewSessionSource:
        validate_session_id(session_id)
        connection = self._connect()
        try:
            row = self._session_row(connection, session_id)
            return ReviewSessionSource.from_dict(json.loads(row["source_json"]))
        finally:
            connection.close()

    def _finalized_decisions(
        self, connection: sqlite3.Connection, session_id: str
    ) -> tuple[FinalizedCandidateDecision, ...]:
        rows = connection.execute(
            """
            SELECT c.ordinal, c.candidate_id, d.label, d.origin, d.modified_at
              FROM session_candidates c LEFT JOIN decisions d
                ON d.session_id = c.session_id AND d.candidate_id = c.candidate_id
             WHERE c.session_id = ? ORDER BY c.ordinal
            """,
            (session_id,),
        )
        return tuple(
            FinalizedCandidateDecision(
                ordinal=row["ordinal"],
                candidate_id=row["candidate_id"],
                label=(
                    ReviewLabel.UNREVIEWED if row["label"] is None else ReviewLabel(row["label"])
                ),
                origin=(None if row["origin"] is None else DecisionOrigin(row["origin"])),
                modified_at=row["modified_at"],
            )
            for row in rows
        )

    def _snapshot_from_current(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        finalized_at: str,
    ) -> ReviewFinalizationSnapshot:
        source = ReviewSessionSource.from_dict(json.loads(row["source_json"]))
        if (
            source.source_digest != row["source_digest"]
            or source.manifest.collection_id != row["collection_id"]
            or source.manifest.result_id != row["result_id"]
            or source.manifest.projection_digest != row["projection_digest"]
        ):
            raise ReviewSessionStorageError("Review session source snapshot is inconsistent.")
        candidate_rows = connection.execute(
            """
            SELECT ordinal, recording_ordinal, candidate_id, recording_ref, recording_key,
                   source_sha256, sample_rate_hz, frame_count, channels, start_frame,
                   end_frame, start_time_ns, end_time_ns, cnn_target_score, rf_target_score,
                   contributing_windows
              FROM session_candidates WHERE session_id = ? ORDER BY ordinal
            """,
            (row["session_id"],),
        )
        candidates = tuple(
            EligibleCandidate(
                ordinal=candidate["ordinal"],
                recording_ordinal=candidate["recording_ordinal"],
                candidate_id=candidate["candidate_id"],
                recording_ref=candidate["recording_ref"],
                recording_key=candidate["recording_key"],
                source_sha256=candidate["source_sha256"],
                sample_rate_hz=candidate["sample_rate_hz"],
                frame_count=candidate["frame_count"],
                channels=candidate["channels"],
                start_frame=candidate["start_frame"],
                end_frame=candidate["end_frame"],
                start_time_ns=candidate["start_time_ns"],
                end_time_ns=candidate["end_time_ns"],
                cnn_target_score=candidate["cnn_target_score"],
                rf_target_score=candidate["rf_target_score"],
                contributing_windows=candidate["contributing_windows"],
            )
            for candidate in candidate_rows
        )
        ReviewIntakeProjection(source.manifest, source.recordings, candidates)
        settings = SpectrogramSettingsSnapshot.from_dict(json.loads(row["settings_json"]))
        if settings.settings_digest != row["settings_digest"]:
            raise ReviewSessionStorageError("Review session settings snapshot is inconsistent.")
        return ReviewFinalizationSnapshot.create(
            session_id=row["session_id"],
            session_name=row["name"],
            source_digest=row["source_digest"],
            settings=settings,
            parent_session_id=row["parent_session_id"],
            parent_snapshot_digest=row["parent_snapshot_digest"],
            finalized_at=finalized_at,
            candidates=self._finalized_decisions(connection, row["session_id"]),
        )

    def finalize_session(
        self,
        session_id: str,
        *,
        owner_id: str,
        expected_revision: int,
        finalized_at: str,
    ) -> ReviewSession:
        validate_session_id(session_id)
        owner_id = _owner(owner_id)
        validate_timestamp(finalized_at, "Review finalization timestamp")
        with self._transaction() as connection:
            row = self._session_row(connection, session_id)
            self._require_open(row, owner_id=owner_id, expected_revision=expected_revision)
            snapshot = self._snapshot_from_current(connection, row, finalized_at)
            connection.execute(
                "INSERT INTO finalizations VALUES (?, ?, ?)",
                (session_id, _canonical(snapshot.to_dict()), snapshot.snapshot_digest),
            )
            connection.execute(
                """
                UPDATE sessions SET state = 'finalized', owner_id = NULL,
                    revision = revision + 1, final_snapshot_digest = ?,
                    finalized_at = ?, updated_at = ? WHERE session_id = ?
                """,
                (snapshot.snapshot_digest, finalized_at, finalized_at, session_id),
            )
        finalized = self.get_session(session_id)
        if not self.verify_finalization(session_id):
            raise ReviewSessionStorageError("Review finalization failed post-commit verification.")
        return finalized

    def finalization_document(self, session_id: str) -> dict[str, object] | None:
        validate_session_id(session_id)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT snapshot_json FROM finalizations WHERE session_id = ?", (session_id,)
            ).fetchone()
            if row is None:
                return None
            raw = json.loads(row["snapshot_json"])
            if not isinstance(raw, dict):
                raise ReviewSessionStorageError("Review finalization document is corrupt.")
            return raw
        finally:
            connection.close()

    def verify_finalization(self, session_id: str) -> bool:
        validate_session_id(session_id)
        connection = self._connect()
        try:
            row = self._session_row(connection, session_id)
            finalization = connection.execute(
                "SELECT * FROM finalizations WHERE session_id = ?", (session_id,)
            ).fetchone()
            if (
                finalization is None
                or row["state"] != ReviewSessionState.FINALIZED.value
                or row["final_snapshot_digest"] != finalization["snapshot_digest"]
            ):
                return False
            try:
                stored = ReviewFinalizationSnapshot.from_dict(
                    json.loads(finalization["snapshot_json"])
                )
                current = self._snapshot_from_current(connection, row, stored.finalized_at)
            except (TypeError, ValueError, json.JSONDecodeError):
                return False
            return stored == current and stored.snapshot_digest == finalization["snapshot_digest"]
        finally:
            connection.close()

    def continue_in_new_session(
        self,
        parent_session_id: str,
        *,
        name: str,
        owner_id: str,
        created_at: str,
        session_id: str | None = None,
    ) -> ReviewSession:
        validate_session_id(parent_session_id)
        validate_display_name(name, "Review session name")
        owner_id = _owner(owner_id)
        validate_timestamp(created_at, "Review successor creation timestamp")
        session_id = session_id or f"rsn_{uuid.uuid4().hex}"
        validate_session_id(session_id)
        if not self.verify_finalization(parent_session_id):
            raise ReviewSessionConflict("Finalized parent snapshot is missing or inconsistent.")
        with self._transaction() as connection:
            parent = self._session_row(connection, parent_session_id)
            connection.execute(
                """
                INSERT INTO sessions (
                    session_id, name, state, revision, owner_id, source_json,
                    source_digest, collection_id, result_id, projection_digest,
                    settings_json, settings_digest, settings_preset_id,
                    settings_preset_revision, settings_epoch, parent_session_id,
                    parent_snapshot_digest, final_snapshot_digest, created_at,
                    updated_at, closed_at, finalized_at
                ) VALUES (
                    ?, ?, 'open', 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1,
                    ?, ?, NULL, ?, ?, NULL, NULL
                )
                """,
                (
                    session_id,
                    name,
                    owner_id,
                    parent["source_json"],
                    parent["source_digest"],
                    parent["collection_id"],
                    parent["result_id"],
                    parent["projection_digest"],
                    parent["settings_json"],
                    parent["settings_digest"],
                    parent["settings_preset_id"],
                    parent["settings_preset_revision"],
                    parent_session_id,
                    parent["final_snapshot_digest"],
                    created_at,
                    created_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO session_candidates
                SELECT ?, ordinal, recording_ordinal, candidate_id, recording_ref, recording_key,
                       source_sha256, sample_rate_hz, frame_count, channels, start_frame,
                       end_frame, start_time_ns, end_time_ns, cnn_target_score, rf_target_score,
                       contributing_windows
                  FROM session_candidates WHERE session_id = ? ORDER BY ordinal
                """,
                (session_id, parent_session_id),
            )
            connection.execute(
                """
                INSERT INTO decisions(session_id, candidate_id, label, origin, modified_at,
                                      operation_id)
                SELECT ?, candidate_id, label, origin, modified_at, NULL
                  FROM decisions WHERE session_id = ?
                """,
                (session_id, parent_session_id),
            )
            first = connection.execute(
                """
                SELECT candidate_id FROM session_candidates
                 WHERE session_id = ? ORDER BY ordinal LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            connection.execute(
                "INSERT INTO session_views VALUES (?, 0, ?, 'gallery', 'all', 0, '[]')",
                (session_id, None if first is None else first["candidate_id"]),
            )
        return self.get_session(session_id)

    def save_position(
        self,
        session_id: str,
        *,
        candidate_id: str | None,
        view: str,
        filter_name: str,
        scroll_offset: int,
        selected_candidate_ids: tuple[str, ...],
        owner_id: str,
        expected_view_revision: int,
    ) -> ReviewPosition:
        validate_session_id(session_id)
        owner_id = _owner(owner_id)
        if candidate_id is not None:
            validate_candidate_id(candidate_id)
        if view not in {"gallery", "list", "one_by_one"}:
            raise ValueError("Review view is invalid.")
        if filter_name not in {"all", "unreviewed", "call", "not_call"}:
            raise ValueError("Review filter is invalid.")
        if type(scroll_offset) is not int or scroll_offset < 0:
            raise ValueError("Review scroll position is invalid.")
        if len(selected_candidate_ids) > _MAX_SELECTION:
            raise ValueError("Review selection is too large.")
        for selected in selected_candidate_ids:
            validate_candidate_id(selected)
        if len(set(selected_candidate_ids)) != len(selected_candidate_ids):
            raise ValueError("Review selection repeats a candidate.")
        with self._transaction() as connection:
            session = self._session_row(connection, session_id)
            if session["state"] != ReviewSessionState.OPEN.value:
                raise ReviewSessionConflict("Review position can change only while Open.")
            if session["owner_id"] != owner_id:
                raise ReviewSessionConflict("Review session belongs to another live owner.")
            view_row = connection.execute(
                "SELECT * FROM session_views WHERE session_id = ?", (session_id,)
            ).fetchone()
            if view_row["view_revision"] != expected_view_revision:
                raise ReviewSessionConflict("Review view revision changed.")
            candidate_set = {candidate_id, *selected_candidate_ids} - {None}
            if candidate_set:
                placeholders = ",".join("?" for _ in candidate_set)
                count = connection.execute(
                    f"""SELECT COUNT(*) FROM session_candidates
                         WHERE session_id = ? AND candidate_id IN ({placeholders})""",
                    (session_id, *candidate_set),
                ).fetchone()[0]
                if count != len(candidate_set):
                    raise KeyError("Review position contains an ineligible candidate.")
            connection.execute(
                """
                UPDATE session_views SET view_revision = view_revision + 1,
                    current_candidate_id = ?, view_name = ?, filter_name = ?,
                    scroll_offset = ?, selection_json = ? WHERE session_id = ?
                """,
                (
                    candidate_id,
                    view,
                    filter_name,
                    scroll_offset,
                    _canonical(list(selected_candidate_ids)),
                    session_id,
                ),
            )
        return self.load_position(session_id)

    def load_position(self, session_id: str) -> ReviewPosition:
        validate_session_id(session_id)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM session_views WHERE session_id = ?", (session_id,)
            ).fetchone()
            if row is None:
                raise KeyError("Review session position does not exist.")
            selected = json.loads(row["selection_json"])
            if not isinstance(selected, list) or not all(
                isinstance(item, str) for item in selected
            ):
                raise ReviewSessionStorageError("Review session position is corrupt.")
            return ReviewPosition(
                session_id=session_id,
                view_revision=row["view_revision"],
                current_candidate_id=row["current_candidate_id"],
                view=row["view_name"],
                filter_name=row["filter_name"],
                scroll_offset=row["scroll_offset"],
                selected_candidate_ids=tuple(selected),
            )
        finally:
            connection.close()


__all__ = [
    "CandidateDecisionView",
    "PresetImpact",
    "ReviewPosition",
    "ReviewSession",
    "ReviewSessionConflict",
    "ReviewSessionStorageError",
    "ReviewSessionStore",
    "SessionMutation",
]
