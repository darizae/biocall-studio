"""Atomic app-owned persistence for mutable per-Result selections."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from biocall_studio.detect.domain.result_views import (
    MAX_SELECTION_BYTES,
    RESULT_SELECTION_SCHEMA_VERSION,
    ResolvedResultSelection,
    ResultSelection,
    ResultSelectionError,
    SelectionReconciliation,
    _ordered_candidate_ids,
)
from biocall_studio.detect.domain.rf_refinement import ResultArtifact
from biocall_studio.detect.domain.runs import utc_now


class ResultSelectionStore:
    """Atomic mutable selection metadata kept beside, never inside, Results."""

    def __init__(self, collection_root: Path):
        root = Path(collection_root)
        if root.is_symlink() or not root.is_dir():
            raise ResultSelectionError("Detect Collection metadata root is missing or unsafe.")
        self.collection_root = root.resolve(strict=True)
        self.selection_root = self.collection_root / "result-selections"

    def _ensure_root(self) -> None:
        if self.selection_root.is_symlink():
            raise ResultSelectionError("Result selection storage cannot be a symlink.")
        if self.selection_root.exists() and not self.selection_root.is_dir():
            raise ResultSelectionError("Result selection storage must be a directory.")
        self.selection_root.mkdir(mode=0o700, exist_ok=True)
        self.selection_root.chmod(0o700)

    def path_for(self, result_id: str) -> Path:
        from biocall_studio.detect.domain.result_views import _RESULT_ID

        if not isinstance(result_id, str) or _RESULT_ID.fullmatch(result_id) is None:
            raise ResultSelectionError("Result selection Result ID is invalid.")
        return self.selection_root / f"{result_id}.json"

    def _load(self, result_id: str) -> ResultSelection | None:
        if self.selection_root.is_symlink() or (
            self.selection_root.exists() and not self.selection_root.is_dir()
        ):
            raise ResultSelectionError("Result selection storage is unsafe.")
        path = self.path_for(result_id)
        if not path.exists() and not path.is_symlink():
            return None
        if path.is_symlink() or not path.is_file():
            raise ResultSelectionError("Result selection document is missing or unsafe.")
        try:
            if path.stat().st_size > MAX_SELECTION_BYTES:
                raise ResultSelectionError("Result selection document exceeds 1 MiB.")
            raw = json.loads(path.read_bytes())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResultSelectionError("Result selection document is corrupt.") from exc
        selection = ResultSelection.from_dict(raw)
        if selection.result_id != result_id:
            raise ResultSelectionError("Result selection filename and Result ID disagree.")
        return selection

    def _write(self, selection: ResultSelection) -> None:
        self._ensure_root()
        path = self.path_for(selection.result_id)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ResultSelectionError("Result selection document path is unsafe.")
        payload = (
            json.dumps(selection.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        if len(payload) > MAX_SELECTION_BYTES:
            raise ResultSelectionError("Result selection document exceeds 1 MiB.")
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.selection_root,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                os.chmod(temporary, 0o600)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            path.chmod(0o600)
            try:
                descriptor = os.open(self.selection_root, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            except OSError:
                pass
        except OSError as exc:
            raise ResultSelectionError("Result selection could not be saved.") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def read(self, result: ResultArtifact) -> ResolvedResultSelection:
        stored = self._load(result.result_id)
        if stored is None:
            return ResolvedResultSelection(
                ResultSelection.empty(result), SelectionReconciliation.CURRENT, ""
            )
        if stored.result_digest != result.result_digest:
            selection = ResultSelection(
                RESULT_SELECTION_SCHEMA_VERSION,
                result.result_id,
                result.result_digest,
                stored.selection_revision + 1,
                (),
                utc_now(),
            )
            self._write(selection)
            return ResolvedResultSelection(
                selection,
                SelectionReconciliation.RESULT_CHANGED,
                "Saved selections were cleared because the Result contents changed.",
            )
        valid_ids = {
            candidate.candidate_id
            for recording in result.recordings
            for candidate in recording.candidates
        }
        retained = tuple(
            candidate_id for candidate_id in stored.candidate_ids if candidate_id in valid_ids
        )
        if retained != stored.candidate_ids:
            selection = ResultSelection(
                RESULT_SELECTION_SCHEMA_VERSION,
                result.result_id,
                result.result_digest,
                stored.selection_revision + 1,
                retained,
                utc_now(),
            )
            self._write(selection)
            return ResolvedResultSelection(
                selection,
                SelectionReconciliation.CANDIDATES_REMOVED,
                "Selections that no longer exist in this Result were removed.",
            )
        return ResolvedResultSelection(stored, SelectionReconciliation.CURRENT, "")

    def replace(
        self,
        result: ResultArtifact,
        candidate_ids: tuple[str, ...] | list[str] | set[str],
    ) -> ResultSelection:
        ordered = _ordered_candidate_ids(result, candidate_ids)
        resolved = self.read(result)
        selection = ResultSelection(
            RESULT_SELECTION_SCHEMA_VERSION,
            result.result_id,
            result.result_digest,
            resolved.selection.selection_revision + 1,
            ordered,
            utc_now(),
        )
        self._write(selection)
        return selection
