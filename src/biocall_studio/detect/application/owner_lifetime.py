"""Detect-specific lease locations over shared owner-lifetime infrastructure."""

from __future__ import annotations

from pathlib import Path

from biocall_studio.shared.owner_lifetime import OwnerLease, WorkerOwnerGuard


class DetectOwnerLease(OwnerLease):
    @classmethod
    def create(cls, application_data_root: Path) -> DetectOwnerLease:
        leases = Path(application_data_root) / "detect" / "v1" / "leases"
        return super().create(leases, prefix="owner")


class DetectWorkerOwnerGuard(WorkerOwnerGuard):
    def __init__(self, path: Path):
        super().__init__(path, watchdog_name="biocall-studio-detect-owner-watchdog")

    def start_watchdog(self, *, interval_seconds: float = 0.1) -> None:
        super().start_watchdog(interval_seconds=interval_seconds)
