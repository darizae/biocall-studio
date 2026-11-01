from __future__ import annotations

import pytest

from biocall_studio.detect.application.navigation import (
    DetectRoute,
    active_sidebar_route,
    adaptive_new_detection_route,
    parse_detect_route,
)


def test_typed_routes_adaptive_entry_and_nested_highlighting_fail_closed():
    """Case: UT-DET-025."""
    assert parse_detect_route("models") is DetectRoute.MODELS
    assert adaptive_new_detection_route(
        model_compatible=False,
        recordings_reviewed=False,
        active_run=False,
    ) is DetectRoute.MODELS
    assert adaptive_new_detection_route(
        model_compatible=True,
        recordings_reviewed=False,
        active_run=False,
    ) is DetectRoute.RECORDINGS
    assert adaptive_new_detection_route(
        model_compatible=True,
        recordings_reviewed=True,
        active_run=False,
    ) is DetectRoute.NEW_DETECTION
    assert adaptive_new_detection_route(
        model_compatible=False,
        recordings_reviewed=False,
        active_run=True,
    ) is DetectRoute.RUN_DETAIL

    assert active_sidebar_route(DetectRoute.RUN_DETAIL) is DetectRoute.RUNS
    assert active_sidebar_route(DetectRoute.EXPORT_DETAIL) is DetectRoute.EXPORTS
    assert active_sidebar_route(DetectRoute.EXPORT_NEW) is DetectRoute.EXPORTS
    assert active_sidebar_route(DetectRoute.RESULTS) is DetectRoute.RESULTS

    with pytest.raises(ValueError, match="Unknown Detect route"):
        parse_detect_route("setup")
    with pytest.raises(TypeError, match="text or DetectRoute"):
        parse_detect_route(None)
