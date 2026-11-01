import pytest

from biocall_studio.shared.paths import ensure_unique_portable_paths, validate_relative_path


@pytest.mark.parametrize(
    "value",
    [
        "/absolute.wav",
        "C:\\absolute.wav",
        "\\\\server\\share\\recording.wav",
        "recordings/../escape.wav",
        "recordings//double.wav",
        "recordings/CON.wav",
        "recordings/name?.wav",
        "recordings/control\x1f.wav",
    ],
)
def test_portable_relative_paths_reject_unsafe_segments(value):
    """Case: UT-PATH-001."""
    with pytest.raises(ValueError):
        validate_relative_path(value)


def test_portable_relative_paths_accept_collection_children():
    """Case: UT-PATH-001."""
    assert validate_relative_path("recordings/REC_A.wav") == "recordings/REC_A.wav"


def test_portable_paths_reject_unicode_and_casefold_collisions():
    """Case: UT-PATH-002."""
    with pytest.raises(ValueError, match="collision"):
        ensure_unique_portable_paths(["recordings/Caf\u00e9.wav", "recordings/cafe\u0301.WAV"])
