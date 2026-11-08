"""Canonical suite-owned application-data layout decisions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SuiteDataPaths:
    root: Path
    train: Path
    detect: Path
    review: Path

    @classmethod
    def from_root(cls, root: Path) -> SuiteDataPaths:
        candidate = Path(root).expanduser()
        if candidate.is_symlink():
            raise ValueError("BioCall Studio application-data root cannot be a symlink.")
        resolved = candidate.resolve(strict=False)
        train = resolved / "train" / "v1"
        detect = resolved / "detect" / "v1"
        review = resolved / "review" / "v1"
        if not all(path.is_relative_to(resolved) for path in (train, detect, review)):
            raise ValueError("Workflow application-data roots must stay inside the suite root.")
        return cls(root=resolved, train=train, detect=detect, review=review)
