"""Kernel-owned process leases for Review session write ownership."""

from __future__ import annotations

import re
from pathlib import Path

from biocall_studio.shared.owner_lifetime import OwnerLease, WorkerOwnerGuard

_OWNER_ID = re.compile(r"review_owner_[0-9a-f]{32}")


class ReviewOwnerLease(OwnerLease):
    @classmethod
    def create(cls, application_data_root: Path) -> ReviewOwnerLease:
        leases = Path(application_data_root) / "review" / "v1" / "leases"
        return super().create(leases, prefix="review_owner")


def review_owner_alive(application_data_root: Path, owner_id: str) -> bool:
    if not isinstance(owner_id, str) or _OWNER_ID.fullmatch(owner_id) is None:
        raise ValueError("Review session owner ID is invalid.")
    path = Path(application_data_root) / "review" / "v1" / "leases" / f"{owner_id}.lease"
    if path.is_symlink() or not path.is_file():
        return False
    try:
        guard = WorkerOwnerGuard(path, watchdog_name="biocall-review-owner-inspection")
    except (OSError, ValueError):
        return False
    try:
        return guard.owner_alive()
    finally:
        guard.close()


__all__ = ["ReviewOwnerLease", "review_owner_alive"]
