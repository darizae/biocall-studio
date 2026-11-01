"""Train-specific lease locations over shared owner-lifetime infrastructure."""

from __future__ import annotations

from pathlib import Path

from biocall_studio.shared.owner_lifetime import OwnerLease as _OwnerLease
from biocall_studio.shared.owner_lifetime import WorkerOwnerGuard as _WorkerOwnerGuard


class OwnerLease(_OwnerLease):
    @classmethod
    def create(cls, settings_dir: Path) -> OwnerLease:
        return super().create(Path(settings_dir) / "leases", prefix="train_owner")


class WorkerOwnerGuard(_WorkerOwnerGuard):
    def __init__(self, path: Path):
        super().__init__(path, watchdog_name="biocall-studio-owner-watchdog")
