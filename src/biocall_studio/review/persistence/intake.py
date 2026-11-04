"""Transactional Review intake index and read-only Detect Result consumer."""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from biocall_studio.detect.application.discovery import validate_recording_source
from biocall_studio.detect.domain import RootBindingDecision, validate_collection_id
from biocall_studio.detect.domain.inventory import InventorySnapshot
from biocall_studio.detect.domain.results import DetectionResult
from biocall_studio.detect.domain.rf_refinement import DerivedResult, ResultArtifact
from biocall_studio.detect.domain.runs import DetectRunStatus
from biocall_studio.detect.persistence import (
    DetectWorkspaceStore,
    PersistedDetectCollection,
)
from biocall_studio.detect.persistence.runs import DetectRunRepository
from biocall_studio.review.domain.intake import (
    REVIEW_INTAKE_SCHEMA_VERSION,
    EligibleCandidate,
    ReviewIntakeManifest,
    ReviewIntakeProjection,
    ReviewRecording,
    ReviewResultKind,
    build_review_projection,
    projection_digest,
)
from biocall_studio.review.domain.sessions import ReviewSessionSource

_RESULT_ID = re.compile(r"pub_[0-9a-f]{32}")
_DATABASE_SCHEMA_VERSION = 1
_MAX_PAGE_SIZE = 1_000


class ReviewIntakeStorageError(ValueError):
    """Review intake storage is unsafe, corrupt, or unsupported."""


class IntakeAvailability(StrEnum):
    READY = "ready"
    RELINK_NEEDED = "relink_needed"
    SOURCE_CHANGED = "source_changed"
    SOURCE_UNSAFE = "source_unsafe"
    RESULT_UNAVAILABLE = "result_unavailable"
    RESULT_CHANGED = "result_changed"
    UNSUPPORTED_INPUT = "unsupported_input"


@dataclass(frozen=True, slots=True)
class ReviewIntakeInspection:
    availability: IntakeAvailability
    manifest: ReviewIntakeManifest | None
    message: str

    @property
    def ready(self) -> bool:
        return self.availability is IntakeAvailability.READY

    @property
    def eligible_candidate_count(self) -> int | None:
        return None if self.manifest is None else self.manifest.eligible_candidate_count


@dataclass(frozen=True, slots=True)
class PreparedReviewSession:
    source: ReviewSessionSource
    candidates: tuple[EligibleCandidate, ...]


_CREATE_STATEMENTS = (
    """
    CREATE TABLE intakes (
        collection_id TEXT NOT NULL,
        result_id TEXT NOT NULL,
        schema_version INTEGER NOT NULL,
        projection_digest TEXT NOT NULL,
        result_kind TEXT NOT NULL,
        result_digest TEXT NOT NULL,
        publication_digest TEXT NOT NULL,
        parent_result_id TEXT,
        parent_result_digest TEXT,
        binding_revision INTEGER NOT NULL,
        inventory_id TEXT NOT NULL,
        inventory_digest TEXT NOT NULL,
        source_time_semantics TEXT NOT NULL,
        recording_count INTEGER NOT NULL,
        failed_recording_count INTEGER NOT NULL,
        eligible_candidate_count INTEGER NOT NULL,
        PRIMARY KEY (collection_id, result_id)
    ) STRICT
    """,
    """
    CREATE TABLE recordings (
        collection_id TEXT NOT NULL,
        result_id TEXT NOT NULL,
        ordinal INTEGER NOT NULL,
        recording_ref TEXT NOT NULL,
        recording_key TEXT NOT NULL,
        source_sha256 TEXT NOT NULL,
        sample_rate_hz INTEGER NOT NULL,
        frame_count INTEGER NOT NULL,
        channels INTEGER NOT NULL,
        failed INTEGER NOT NULL,
        error_code TEXT NOT NULL,
        eligible_candidate_count INTEGER NOT NULL,
        PRIMARY KEY (collection_id, result_id, ordinal),
        UNIQUE (collection_id, result_id, recording_ref),
        FOREIGN KEY (collection_id, result_id)
            REFERENCES intakes(collection_id, result_id) ON DELETE RESTRICT
    ) STRICT
    """,
    """
    CREATE TABLE candidates (
        collection_id TEXT NOT NULL,
        result_id TEXT NOT NULL,
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
        PRIMARY KEY (collection_id, result_id, ordinal),
        UNIQUE (collection_id, result_id, candidate_id),
        FOREIGN KEY (collection_id, result_id)
            REFERENCES intakes(collection_id, result_id) ON DELETE RESTRICT,
        FOREIGN KEY (collection_id, result_id, recording_ordinal)
            REFERENCES recordings(collection_id, result_id, ordinal) ON DELETE RESTRICT
    ) STRICT
    """,
    """
    CREATE INDEX candidates_by_recording
        ON candidates(collection_id, result_id, recording_ordinal, ordinal)
    """,
)


class ReviewIntakeStore:
    """SQLite-backed immutable, paged candidate projection below `review/v1`."""

    def __init__(self, root: Path):
        requested = Path(root).expanduser()
        if requested.is_symlink():
            raise ReviewIntakeStorageError("Review application-data root cannot be a symlink.")
        self.root = requested.resolve(strict=False)
        self.database_path = self.root / "intake.sqlite3"

    def _ensure_root(self) -> None:
        for path in (self.root.parent, self.root):
            if path.is_symlink():
                raise ReviewIntakeStorageError(
                    "Review application-data directories cannot be symbolic links."
                )
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise ReviewIntakeStorageError("Review application-data root is unsafe.")
        self.root.chmod(0o700)
        if self.database_path.is_symlink():
            raise ReviewIntakeStorageError("Review intake database cannot be a symlink.")

    def _connect(self) -> sqlite3.Connection:
        self._ensure_root()
        try:
            connection = sqlite3.connect(self.database_path, timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA journal_mode = DELETE")
            connection.execute("PRAGMA synchronous = FULL")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                for statement in _CREATE_STATEMENTS:
                    connection.execute(statement)
                connection.execute(f"PRAGMA user_version = {_DATABASE_SCHEMA_VERSION}")
                connection.commit()
            elif version != _DATABASE_SCHEMA_VERSION:
                raise ReviewIntakeStorageError("Review intake database schema is unsupported.")
            check = connection.execute("PRAGMA quick_check").fetchone()[0]
            if check != "ok":
                raise ReviewIntakeStorageError("Review intake database integrity check failed.")
            os.chmod(self.database_path, 0o600)
            return connection
        except sqlite3.DatabaseError as exc:
            raise ReviewIntakeStorageError("Review intake database is corrupt.") from exc

    @staticmethod
    def _manifest(row: sqlite3.Row) -> ReviewIntakeManifest:
        return ReviewIntakeManifest(
            schema_version=row["schema_version"],
            projection_digest=row["projection_digest"],
            result_kind=ReviewResultKind(row["result_kind"]),
            collection_id=row["collection_id"],
            result_id=row["result_id"],
            result_digest=row["result_digest"],
            publication_digest=row["publication_digest"],
            parent_result_id=row["parent_result_id"],
            parent_result_digest=row["parent_result_digest"],
            binding_revision=row["binding_revision"],
            inventory_id=row["inventory_id"],
            inventory_digest=row["inventory_digest"],
            source_time_semantics=row["source_time_semantics"],
            recording_count=row["recording_count"],
            failed_recording_count=row["failed_recording_count"],
            eligible_candidate_count=row["eligible_candidate_count"],
        )

    @staticmethod
    def _recording(row: sqlite3.Row) -> ReviewRecording:
        return ReviewRecording(
            ordinal=row["ordinal"],
            recording_ref=row["recording_ref"],
            recording_key=row["recording_key"],
            source_sha256=row["source_sha256"],
            sample_rate_hz=row["sample_rate_hz"],
            frame_count=row["frame_count"],
            channels=row["channels"],
            failed=bool(row["failed"]),
            error_code=row["error_code"],
            eligible_candidate_count=row["eligible_candidate_count"],
        )

    @staticmethod
    def _candidate(row: sqlite3.Row) -> EligibleCandidate:
        return EligibleCandidate(
            ordinal=row["ordinal"],
            recording_ordinal=row["recording_ordinal"],
            candidate_id=row["candidate_id"],
            recording_ref=row["recording_ref"],
            recording_key=row["recording_key"],
            source_sha256=row["source_sha256"],
            sample_rate_hz=row["sample_rate_hz"],
            frame_count=row["frame_count"],
            channels=row["channels"],
            start_frame=row["start_frame"],
            end_frame=row["end_frame"],
            start_time_ns=row["start_time_ns"],
            end_time_ns=row["end_time_ns"],
            cnn_target_score=row["cnn_target_score"],
            rf_target_score=row["rf_target_score"],
            contributing_windows=row["contributing_windows"],
        )

    def save(self, projection: ReviewIntakeProjection) -> ReviewIntakeManifest:
        manifest = projection.manifest
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT projection_digest FROM intakes WHERE collection_id = ? AND result_id = ?",
                (manifest.collection_id, manifest.result_id),
            ).fetchone()
            if existing is not None:
                if existing["projection_digest"] != manifest.projection_digest:
                    raise ReviewIntakeStorageError(
                        "This immutable Detect Result already has a different Review projection."
                    )
            else:
                connection.execute(
                    """
                    INSERT INTO intakes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        manifest.collection_id,
                        manifest.result_id,
                        manifest.schema_version,
                        manifest.projection_digest,
                        manifest.result_kind.value,
                        manifest.result_digest,
                        manifest.publication_digest,
                        manifest.parent_result_id,
                        manifest.parent_result_digest,
                        manifest.binding_revision,
                        manifest.inventory_id,
                        manifest.inventory_digest,
                        manifest.source_time_semantics,
                        manifest.recording_count,
                        manifest.failed_recording_count,
                        manifest.eligible_candidate_count,
                    )
                )
                connection.executemany(
                    """
                    INSERT INTO recordings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            manifest.collection_id,
                            manifest.result_id,
                            row.ordinal,
                            row.recording_ref,
                            row.recording_key,
                            row.source_sha256,
                            row.sample_rate_hz,
                            row.frame_count,
                            row.channels,
                            int(row.failed),
                            row.error_code,
                            row.eligible_candidate_count,
                        )
                        for row in projection.recordings
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO candidates VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        (
                            manifest.collection_id,
                            manifest.result_id,
                            row.ordinal,
                            row.recording_ordinal,
                            row.candidate_id,
                            row.recording_ref,
                            row.recording_key,
                            row.source_sha256,
                            row.sample_rate_hz,
                            row.frame_count,
                            row.channels,
                            row.start_frame,
                            row.end_frame,
                            row.start_time_ns,
                            row.end_time_ns,
                            row.cnn_target_score,
                            row.rf_target_score,
                            row.contributing_windows,
                        )
                        for row in projection.candidates
                    ),
                )
        verified = self.load_manifest(manifest.collection_id, manifest.result_id)
        if verified != manifest:
            raise ReviewIntakeStorageError("Review projection did not verify after publication.")
        return manifest

    def load_manifest(
        self, collection_id: str, result_id: str
    ) -> ReviewIntakeManifest | None:
        validate_collection_id(collection_id)
        if not isinstance(result_id, str) or _RESULT_ID.fullmatch(result_id) is None:
            raise ValueError("Review Result reference is invalid.")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM intakes WHERE collection_id = ? AND result_id = ?",
                (collection_id, result_id),
            ).fetchone()
            if row is None:
                return None
            manifest = self._manifest(row)
            recording_cursor = connection.execute(
                """
                SELECT ordinal, recording_ref, recording_key, source_sha256, sample_rate_hz,
                       frame_count, channels, failed, error_code, eligible_candidate_count
                  FROM recordings
                 WHERE collection_id = ? AND result_id = ?
                 ORDER BY ordinal
                """,
                (collection_id, result_id),
            )
            candidate_cursor = connection.execute(
                """
                SELECT ordinal, recording_ordinal, candidate_id, recording_ref, recording_key,
                       source_sha256, sample_rate_hz, frame_count, channels, start_frame,
                       end_frame, start_time_ns, end_time_ns, cnn_target_score, rf_target_score,
                       contributing_windows
                  FROM candidates
                 WHERE collection_id = ? AND result_id = ?
                 ORDER BY ordinal
                """,
                (collection_id, result_id),
            )
            recordings = (self._recording(item) for item in recording_cursor)
            candidates = (self._candidate(item) for item in candidate_cursor)
            if projection_digest(manifest, recordings, candidates) != manifest.projection_digest:
                raise ReviewIntakeStorageError("Stored Review projection digest does not match.")
            counts = connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM recordings
                      WHERE collection_id = ? AND result_id = ?) AS recording_count,
                    (SELECT COUNT(*) FROM candidates
                      WHERE collection_id = ? AND result_id = ?) AS candidate_count
                """,
                (collection_id, result_id, collection_id, result_id),
            ).fetchone()
            if (
                counts["recording_count"] != manifest.recording_count
                or counts["candidate_count"] != manifest.eligible_candidate_count
            ):
                raise ReviewIntakeStorageError("Stored Review projection counts do not match.")
            return manifest

    @staticmethod
    def _page(offset: int, limit: int) -> None:
        if type(offset) is not int or offset < 0:
            raise ValueError("Review page offset is invalid.")
        if type(limit) is not int or not 1 <= limit <= _MAX_PAGE_SIZE:
            raise ValueError(f"Review page size must be between 1 and {_MAX_PAGE_SIZE:,}.")

    def candidate_page(
        self,
        collection_id: str,
        result_id: str,
        *,
        offset: int,
        limit: int,
    ) -> tuple[EligibleCandidate, ...]:
        self._page(offset, limit)
        validate_collection_id(collection_id)
        if not isinstance(result_id, str) or _RESULT_ID.fullmatch(result_id) is None:
            raise ValueError("Review Result reference is invalid.")
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM intakes WHERE collection_id = ? AND result_id = ?",
                (collection_id, result_id),
            ).fetchone()
            if exists is None:
                raise KeyError("Review intake does not exist.")
            rows = connection.execute(
                """
                SELECT ordinal, recording_ordinal, candidate_id, recording_ref, recording_key,
                       source_sha256, sample_rate_hz, frame_count, channels, start_frame,
                       end_frame, start_time_ns, end_time_ns, cnn_target_score, rf_target_score,
                       contributing_windows
                  FROM candidates
                 WHERE collection_id = ? AND result_id = ?
                 ORDER BY ordinal
                 LIMIT ? OFFSET ?
                """,
                (collection_id, result_id, limit, offset),
            )
            return tuple(self._candidate(row) for row in rows)


@dataclass(frozen=True, slots=True)
class _VerifiedOrigin:
    result: ResultArtifact
    parent: DetectionResult | None
    collection: PersistedDetectCollection
    inventory: InventorySnapshot
    publication_digest: str


class ReviewResultIntake:
    """Consume only completed Detect Results and never mutate their owning storage."""

    def __init__(self, suite_data_root: Path, store: ReviewIntakeStore | None = None):
        requested = Path(suite_data_root).expanduser()
        if requested.is_symlink():
            raise ValueError("Suite application-data root cannot be a symlink.")
        self.suite_data_root = requested.resolve(strict=False)
        self.store = store or ReviewIntakeStore(
            self.suite_data_root / "review" / f"v{REVIEW_INTAKE_SCHEMA_VERSION}"
        )
        self.detect_store = DetectWorkspaceStore(self.suite_data_root)

    @staticmethod
    def _unavailable(
        availability: IntakeAvailability,
        manifest: ReviewIntakeManifest | None,
        message: str,
    ) -> ReviewIntakeInspection:
        return ReviewIntakeInspection(availability, manifest, message)

    def _completed_record(self, repository: DetectRunRepository, result_id: str):
        records = tuple(
            record
            for record in repository.list_records()
            if record.artifact_id == result_id
        )
        if len(records) != 1 or records[0].status is not DetectRunStatus.COMPLETED:
            raise ValueError("Detect Result does not belong to one completed Run.")
        record = records[0]
        receipt = repository.load_receipt(record)
        if record.published_artifact_digest != receipt.artifact_digest:
            raise ValueError("Completed Detect Run and publication digest disagree.")
        return record, receipt

    def _load_origin(self, collection_id: str, result_id: str) -> _VerifiedOrigin:
        validate_collection_id(collection_id)
        if not isinstance(result_id, str) or _RESULT_ID.fullmatch(result_id) is None:
            raise ValueError("Review accepts only a Detect Result reference.")
        collection = self.detect_store.load_collection(collection_id)
        collection_root = self.detect_store.paths_for(collection_id).collection_directory
        for name in ("runs", "results", "publications", ".staging"):
            path = collection_root / name
            if path.is_symlink() or not path.is_dir():
                raise ValueError("Detect Result storage is missing or unsafe.")
        repository = DetectRunRepository(self.suite_data_root, collection_id)
        record, receipt = self._completed_record(repository, result_id)
        parent: DetectionResult | None = None
        if receipt.artifact_kind == "detection_result":
            result: ResultArtifact = repository.load_detection_result(record)
        elif receipt.artifact_kind == "derived_result":
            result = repository.load_derived_result(record)
            parent_record, _parent_receipt = self._completed_record(
                repository, result.parent_result_id
            )
            parent = repository.load_detection_result(parent_record)
        else:
            raise ValueError("Completed artifact is not a scientific Detect Result.")
        inventory = self.detect_store.load_inventory(collection_id, result.inventory_id)
        return _VerifiedOrigin(
            result=result,
            parent=parent,
            collection=collection,
            inventory=inventory,
            publication_digest=receipt.artifact_digest,
        )

    def _source_state(
        self,
        origin: _VerifiedOrigin,
        projection: ReviewIntakeProjection,
    ) -> tuple[IntakeAvailability, str]:
        try:
            root_state = self.detect_store.root_decision(origin.collection)
        except (OSError, ValueError):
            return (
                IntakeAvailability.RELINK_NEEDED,
                "The recordings folder is unavailable. Relink the Detect Collection.",
            )
        if root_state is not RootBindingDecision.VALID:
            return (
                IntakeAvailability.RELINK_NEEDED,
                "The recordings folder is unavailable. Relink the Detect Collection.",
            )
        inventory_rows = {
            row.recording_key: row for row in origin.inventory.recordings
        }
        for recording in projection.recordings:
            try:
                validate_recording_source(
                    origin.collection.source_root,
                    inventory_rows[recording.recording_key],
                )
            except (FileNotFoundError, PermissionError, OSError, KeyError):
                return (
                    IntakeAvailability.RELINK_NEEDED,
                    "A source recording is unavailable. Relink or restore the Detect source.",
                )
            except ValueError as exc:
                detail = str(exc).casefold()
                unsafe = any(
                    phrase in detail
                    for phrase in (
                        "symbolic link",
                        "reparse",
                        "outside the source root",
                        "not a regular file",
                    )
                )
                return (
                    IntakeAvailability.SOURCE_UNSAFE
                    if unsafe
                    else IntakeAvailability.SOURCE_CHANGED,
                    (
                        "A source recording path is unsafe and cannot be opened."
                        if unsafe
                        else "A source recording changed after the Detect inventory was frozen."
                    ),
                )
        return IntakeAvailability.READY, "Detect Result and source recordings are verified."

    def _projection(self, origin: _VerifiedOrigin) -> ReviewIntakeProjection:
        return build_review_projection(
            origin.result,
            origin.inventory,
            publication_digest=origin.publication_digest,
            parent=origin.parent,
        )

    def intake(self, collection_id: str, result_id: str) -> ReviewIntakeInspection:
        try:
            validate_collection_id(collection_id)
        except ValueError:
            return self._unavailable(
                IntakeAvailability.UNSUPPORTED_INPUT,
                None,
                "Review accepts only a Detect Collection and Result reference.",
            )
        if not isinstance(result_id, str) or _RESULT_ID.fullmatch(result_id) is None:
            return self._unavailable(
                IntakeAvailability.UNSUPPORTED_INPUT,
                None,
                "Review accepts only a completed Detect Result, not a WAV or annotation file.",
            )
        try:
            origin = self._load_origin(collection_id, result_id)
            projection = self._projection(origin)
        except (FileNotFoundError, OSError, ValueError):
            return self._unavailable(
                IntakeAvailability.RESULT_UNAVAILABLE,
                None,
                "The Detect Result, its completed Run, or its verified lineage is unavailable.",
            )
        availability, message = self._source_state(origin, projection)
        manifest = self.store.save(projection)
        return ReviewIntakeInspection(availability, manifest, message)

    def prepare_session(self, collection_id: str, result_id: str) -> PreparedReviewSession:
        """Return only a currently verified Result projection for session creation."""
        try:
            origin = self._load_origin(collection_id, result_id)
            projection = self._projection(origin)
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise ValueError(
                "The Detect Result, its completed Run, or its verified lineage is unavailable."
            ) from exc
        availability, message = self._source_state(origin, projection)
        if availability is not IntakeAvailability.READY:
            raise ValueError(message)
        self.store.save(projection)
        if isinstance(origin.result, DerivedResult):
            score_semantics = origin.result.score_semantics
            eligibility_threshold = origin.result.threshold
            if origin.parent is None:
                raise ValueError("RF Review source lost its verified parent lineage.")
            parent_score_semantics = origin.parent.score_semantics
            parent_eligibility_threshold = origin.parent.settings.minimum_score
        else:
            score_semantics = origin.result.score_semantics
            eligibility_threshold = origin.result.settings.minimum_score
            parent_score_semantics = None
            parent_eligibility_threshold = None
        source = ReviewSessionSource.from_projection(
            projection,
            score_semantics=score_semantics,
            eligibility_threshold=eligibility_threshold,
            parent_score_semantics=parent_score_semantics,
            parent_eligibility_threshold=parent_eligibility_threshold,
        )
        return PreparedReviewSession(source=source, candidates=projection.candidates)

    def reopen(self, collection_id: str, result_id: str) -> ReviewIntakeInspection:
        try:
            manifest = self.store.load_manifest(collection_id, result_id)
        except (ValueError, ReviewIntakeStorageError):
            return self._unavailable(
                IntakeAvailability.UNSUPPORTED_INPUT,
                None,
                "The Review intake reference is invalid or unsupported.",
            )
        if manifest is None:
            return self._unavailable(
                IntakeAvailability.RESULT_UNAVAILABLE,
                None,
                "No verified Review intake exists for this Detect Result.",
            )
        try:
            origin = self._load_origin(collection_id, result_id)
            projection = self._projection(origin)
        except (FileNotFoundError, OSError, ValueError):
            return self._unavailable(
                IntakeAvailability.RESULT_UNAVAILABLE,
                manifest,
                "The original Detect Result or its verified lineage is unavailable.",
            )
        if projection.manifest.projection_digest != manifest.projection_digest:
            return self._unavailable(
                IntakeAvailability.RESULT_CHANGED,
                manifest,
                "The Detect Result no longer matches the frozen Review projection.",
            )
        availability, message = self._source_state(origin, projection)
        return ReviewIntakeInspection(availability, manifest, message)


__all__ = [
    "IntakeAvailability",
    "PreparedReviewSession",
    "ReviewIntakeInspection",
    "ReviewIntakeStorageError",
    "ReviewIntakeStore",
    "ReviewResultIntake",
]
