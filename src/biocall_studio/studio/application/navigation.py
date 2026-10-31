"""Pure Studio workspace routing policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkspaceRoute(StrEnum):
    STUDIO = "studio"
    TRAIN = "train"
    DETECT = "detect"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class WorkspaceNavigation:
    """An explicit route decision with no ownership of workspace state."""

    current: WorkspaceRoute = WorkspaceRoute.STUDIO

    def navigate(self, route: str | WorkspaceRoute) -> WorkspaceNavigation:
        try:
            target = WorkspaceRoute(route)
        except ValueError as exc:
            raise ValueError(f"Unknown Studio workspace: {route}") from exc
        return WorkspaceNavigation(target)

    @property
    def detect_actions_enabled(self) -> bool:
        """ST-02 exposes only the Detect landing state."""
        return False
