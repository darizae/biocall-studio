"""Static documentation, relative-link, brand and genuine-capture provenance audit.

No application imports or network access: this is intentionally a docs-only gate.
Absolute/external URLs and fragment anchors on otherwise real files are not fetched.
"""

from __future__ import annotations

import json
import re
import struct
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS = ROOT / "docs/design/evidence/release-real-data"
README = ROOT / "README.md"
SKIP_DIRS = {".git", ".venv", "node_modules", "work", ".release-wheels", ".pytest_cache"}
MARKDOWN_LINK = re.compile(r"!?\[([^\]]*)\]\((<[^>]+>|[^\s)]+)(?:\s+[^)]*)?\)")
HTML_TARGET = re.compile(r"<(?:img|a)\b[^>]*(?:src|href)\s*=\s*[\"']([^\"']+)[\"']", re.I)
IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)
ATTR = re.compile(r'([a-zA-Z-]+)\s*=\s*[\"\']([^\"\']*)[\"\']')
FENCE = re.compile(r"^\s*```")


def _links(text: str):
    inside = False
    for line in text.splitlines():
        if FENCE.match(line):
            inside = not inside
            continue
        if inside:
            continue
        for match in MARKDOWN_LINK.finditer(line):
            yield match.group(2).strip("<>")
        for match in HTML_TARGET.finditer(line):
            yield match.group(1)


def _local_target(source: Path, href: str) -> Path | None:
    if not href or href.startswith("#") or href.startswith("//"):
        return None
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc:
        return None
    raw = unquote(parsed.path)
    if not raw:
        return None
    # Only local document-relative paths are accepted in a repository README.
    if raw.startswith("/"):
        return None
    return (source.parent / raw).resolve(strict=False)


def _png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        header = stream.read(24)
    assert header[:8] == b"\x89PNG\r\n\x1a\n", f"Not a PNG: {path}"
    return struct.unpack(">II", header[16:24])


def main() -> int:
    errors: list[str] = []
    docs = sorted(
        path
        for path in ROOT.rglob("*.md")
        if not (SKIP_DIRS & set(path.relative_to(ROOT).parts))
    )
    links = 0
    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        for href in _links(text):
            target = _local_target(doc, href)
            if target is None:
                continue
            links += 1
            if not target.is_relative_to(ROOT):
                errors.append(f"{doc.relative_to(ROOT)}: path escapes repository: {href}")
            elif not target.exists():
                errors.append(f"{doc.relative_to(ROOT)}: missing {href}")
        for tag in IMG_TAG.findall(text):
            attrs = dict(ATTR.findall(tag))
            if not attrs.get("src") or not attrs.get("alt"):
                errors.append(f"{doc.relative_to(ROOT)}: image lacks src or descriptive alt")
    readme = README.read_text(encoding="utf-8")
    required = {
        "assets/branding/on-background/readme-header.png",
        # Three genuine workflow screenshots are enough for the researcher README.
        # The Studio launchpad remains tracked and provenance-checked below.
        "02a-train-training-in-progress.png",
        "05-detect-results.png",
        "09-review-one-by-one.png",
    }
    for image in required:
        if image not in readme:
            errors.append(f"README misses required genuine brand/screenshot: {image}")
    if not (ROOT / "LICENSE").exists() and re.search(r"license(?:-|_)(?:mit|gpl|apache)", readme, re.I):
        errors.append("README claims a license badge despite missing application LICENSE")

    capture = json.loads((SCREENSHOTS / "capture-metadata.json").read_text(encoding="utf-8"))
    training = json.loads(
        (SCREENSHOTS / "training-capture-metadata.json").read_text(encoding="utf-8")
    )
    cohort = capture["real_example"]
    if (
        cohort["review_candidates"] != 64
        or cohort["review_call_labels"] != 18
        or cohort["review_not_call_labels"] != 0
        or cohort["review_unreviewed"] != 46
        or sum(
            cohort[k]
            for k in ("review_call_labels", "review_not_call_labels", "review_unreviewed")
        )
        != cohort["review_candidates"]
    ):
        errors.append("Original human review-count provenance changed")
    if capture["platform"]["qt_platform"] != "cocoa" or "visible" not in capture["capture_mode"]:
        errors.append("Genuine native capture provenance changed")
    if training["status_at_capture"] != "running" or training["qt_platform"] != "cocoa":
        errors.append("Genuine Train progress capture provenance changed")
    if not all(
        len(cohort[name]) == 64
        for name in ("source_wav_sha256", "provenance_sha256")
    ):
        errors.append("Real WAV or human-provenance hash invalid")
    for item in capture["captures"]:
        image = SCREENSHOTS / item["file"]
        if not image.is_file() or _png_dimensions(image) != tuple(item["png_pixels"]):
            errors.append(f"Missing/dimension-mismatched genuine capture: {item['file']}")
    active = SCREENSHOTS / "02a-train-training-in-progress.png"
    if not active.is_file() or _png_dimensions(active) != tuple(training["png_pixels"]):
        errors.append("Missing/dimension-mismatched real Train progress capture")
    for error in errors:
        print("ERROR:", error)
    print(
        f"Documentation audit: {len(docs)} Markdown files, {links} local links, "
        f"{len(capture['captures']) + 1} genuine provenance-bound PNGs; {len(errors)} errors."
    )
    print("External URLs, fragment targets, and native application behavior are not validated.")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
