"""Pure typed navigation policy for the Detect workspace."""

from __future__ import annotations

from enum import StrEnum


class DetectRoute(StrEnum):
    NEW_DETECTION = "new-detection"
    RECORDINGS = "recordings"
    MODELS = "models"
    RUNS = "runs"
    RUN_DETAIL = "run-detail"
    RESULTS = "results"
    EXPORTS = "exports"
    EXPORT_DETAIL = "export-detail"


SIDEBAR_ROUTES = (
    DetectRoute.NEW_DETECTION,
    DetectRoute.RECORDINGS,
    DetectRoute.MODELS,
    DetectRoute.RUNS,
    DetectRoute.RESULTS,
    DetectRoute.EXPORTS,
)

_ACTIVE_SIDEBAR_ROUTE = {
    DetectRoute.NEW_DETECTION: DetectRoute.NEW_DETECTION,
    DetectRoute.RECORDINGS: DetectRoute.RECORDINGS,
    DetectRoute.MODELS: DetectRoute.MODELS,
    DetectRoute.RUNS: DetectRoute.RUNS,
    DetectRoute.RUN_DETAIL: DetectRoute.RUNS,
    DetectRoute.RESULTS: DetectRoute.RESULTS,
    DetectRoute.EXPORTS: DetectRoute.EXPORTS,
    DetectRoute.EXPORT_DETAIL: DetectRoute.EXPORTS,
}


def parse_detect_route(value: str | DetectRoute) -> DetectRoute:
    if isinstance(value, DetectRoute):
        return value
    if not isinstance(value, str):
        raise TypeError("Detect route must be text or DetectRoute.")
    try:
        return DetectRoute(value)
    except ValueError as exc:
        raise ValueError(f"Unknown Detect route: {value}") from exc


def active_sidebar_route(route: str | DetectRoute) -> DetectRoute:
    return _ACTIVE_SIDEBAR_ROUTE[parse_detect_route(route)]


def adaptive_new_detection_route(
    *,
    model_compatible: bool,
    recordings_reviewed: bool,
    active_run: bool,
) -> DetectRoute:
    """Choose the first unresolved input, unless an active Run already owns the flow."""
    if active_run:
        return DetectRoute.RUN_DETAIL
    if not model_compatible:
        return DetectRoute.MODELS
    if not recordings_reviewed:
        return DetectRoute.RECORDINGS
    return DetectRoute.NEW_DETECTION


__all__ = [
    "DetectRoute",
    "SIDEBAR_ROUTES",
    "active_sidebar_route",
    "adaptive_new_detection_route",
    "parse_detect_route",
]
