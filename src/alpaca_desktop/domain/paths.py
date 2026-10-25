"""Portable relative-path decisions for Collection-controlled filenames."""

from __future__ import annotations

import re
import unicodedata

_RESERVED_WINDOWS_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
_DRIVE_PATH = re.compile(r"^[A-Za-z]:")
_INVALID_SEGMENT = re.compile(r'[<>:"\\|?*\x00-\x1f]')


def validate_relative_path(value: str) -> str:
    """Return one portable relative path or reject an unsafe Collection reference."""
    if not isinstance(value, str) or not value:
        raise ValueError("Collection paths must be nonempty strings.")
    if value.startswith(("/", "\\\\")) or _DRIVE_PATH.match(value) or "\\" in value:
        raise ValueError("Collection paths must be portable relative paths.")
    segments = value.split("/")
    if any(not segment or segment in {".", ".."} for segment in segments):
        raise ValueError("Collection paths cannot contain traversal or empty segments.")
    for segment in segments:
        stem = segment.split(".", 1)[0].upper()
        if _INVALID_SEGMENT.search(segment) or segment.endswith((" ", ".")):
            raise ValueError(f"Unsafe Collection path segment: {segment!r}")
        if stem in _RESERVED_WINDOWS_NAMES:
            raise ValueError(f"Reserved platform filename: {segment!r}")
    return value


def ensure_unique_portable_paths(values: list[str]) -> None:
    """Reject filenames that collide under portable Unicode/case identity."""
    seen: set[str] = set()
    for value in values:
        path = validate_relative_path(value)
        identity = unicodedata.normalize("NFC", path).casefold()
        if identity in seen:
            raise ValueError(f"Portable filename collision: {path!r}")
        seen.add(identity)
