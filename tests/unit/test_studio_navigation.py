import pytest

from biocall_studio.navigation import WorkspaceNavigation, WorkspaceRoute


def test_studio_route_policy_is_explicit_fail_closed_and_context_free():
    """Case: UT-STU-001."""
    navigation = WorkspaceNavigation()
    train_context = {"controller": object(), "route": "training", "draft": object()}
    retained_context = train_context.copy()

    assert navigation.current is WorkspaceRoute.STUDIO
    assert not navigation.detect_actions_enabled

    for route in (
        WorkspaceRoute.TRAIN,
        WorkspaceRoute.STUDIO,
        WorkspaceRoute.DETECT,
        WorkspaceRoute.STUDIO,
        WorkspaceRoute.REVIEW,
        WorkspaceRoute.STUDIO,
    ):
        navigation = navigation.navigate(route)
        assert navigation.current is route
        assert train_context == retained_context
        assert not navigation.detect_actions_enabled

    with pytest.raises(ValueError, match="Unknown Studio workspace"):
        navigation.navigate("results")
    assert navigation.current is WorkspaceRoute.STUDIO
