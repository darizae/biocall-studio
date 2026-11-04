"""Audit the *current* public repository handoff, links and optional native evidence.

This is a static repository-integrity check, not scientific, Qt, playback or
owner-approval evidence. Completed ST/REV implementation specs and the historical
training-first prototype were intentionally removed; do not recreate or require
those artifacts. The active stage is defined by docs/IMPLEMENTATION_SEQUENCE.md.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]

# Files that current routing, active specifications, tests and development use.
# Retained release specs and scientific source contracts are intentionally kept.
REQUIRED = (
    "AGENTS.md",
    "README.md",
    "pyproject.toml",
    ".gitattributes",
    ".gitignore",
    "docs/agent/ROUTING.md",
    "docs/agent/GIT_DELIVERY.md",
    "docs/agent/SOURCE_MAP.md",
    "docs/agent/SPEC_WRITING_AND_IMPLEMENTATION_PRINCIPLES.md",
    "docs/IMPLEMENTATION_SEQUENCE.md",
    "docs/DEVELOPMENT.md",
    "docs/PREDICTION.md",
    "docs/UNIT_TESTING.md",
    "docs/INTEGRATION_TEST_BEHAVIORS.md",
    "docs/INTEGRATION_TEST_DATA.md",
    "docs/ST-11_QUALIFICATION.md",
    "docs/RELEASE_PROCESS.md",
    "docs/science/BINARY_CLASSIFICATION_CONTRACT.md",
    "docs/science/MODEL_EXPORT_CONTRACT.md",
    "docs/design/ALP_UI_CONSUMER_CONTRACT.md",
    "docs/design/prototypes/studio-detect/index.html",
    "docs/design/prototypes/studio-detect/prototype.js",
    "docs/design/prototypes/studio-detect/styles.css",
    "docs/design/prototypes/studio-review/index.html",
    "docs/design/prototypes/studio-review/prototype.js",
    "docs/design/prototypes/studio-review/styles.css",
    "docs/design/prototypes/studio-review/PROTOTYPE_ACCEPTANCE_CHECKLIST.md",
    "docs/specs/ST-11-unified-qualification.md",
    "docs/specs/06-macos-release-and-installer.md",
    "docs/specs/07-windows-release-and-installer.md",
    "docs/specs/manual_revision_specs/REV-05-output-size-preflight.md",
    "docs/specs/review/README.md",
    "docs/specs/review/SPECTROGRAM_DECISIONS.md",
    "docs/specs/review/SPECTROGRAM_GENERATION_INVESTIGATION.md",
)
REVIEW_SPECS = (
    "RV-01-result-intake.md",
    "RV-02-sessions-and-annotations.md",
    "RV-03-audio-and-spectrograms.md",
    "RV-04-cache-generation-and-preflight.md",
    "RV-05-native-review-ui.md",
    "RV-06-corpus-export.md",
    "RV-07-studio-detect-migration.md",
    "RV-08-qualification.md",
)
PRIVATE_REQUIRED = (
    "docs/priv/hpc-source-access/SKILL.md",
    "docs/priv/hpc-source-access/references/site.md",
    "docs/priv/hpc-source-access/scripts/hpc-source.sh",
)
# ST-11 is the existing, visible macOS Studio UI baseline. The RV-03 *owner*
# playback/field-call gate is separate and must not be inferred from these shots.
ST11_NATIVE_REQUIRED = (
    "docs/design/evidence/st-11-native/README.md",
    "docs/design/evidence/st-11-native/studio-normal.png",
    "docs/design/evidence/st-11-native/studio-compact.png",
    "docs/design/evidence/st-11-native/train-normal.png",
    "docs/design/evidence/st-11-native/train-compact.png",
    "docs/design/evidence/st-11-native/detect-normal.png",
    "docs/design/evidence/st-11-native/detect-compact.png",
    "docs/design/evidence/st-11-native/review-normal.png",
    "docs/design/evidence/st-11-native/review-compact.png",
    "docs/design/evidence/st-11-native/shared-exit-confirmation.png",
)


def audit_markdown_links(root: Path, *, require_private: bool = False) -> list[str]:
    """Find broken local Markdown links while allowing untracked private-site links."""
    errors: list[str] = []
    root = root.resolve()
    private_root = root / "docs" / "priv"
    for path in sorted(root.rglob("*.md")):
        if path.is_relative_to(private_root):
            continue  # Private documents are outside this tracked public audit.
        document = path.read_text(encoding="utf-8")
        for raw_link in re.findall(
            r"!?\[[^\]]+\]\(([^\s)]+)(?:\s+[^)]*)?\)", document
        ):
            link = unquote(raw_link.split("#", maxsplit=1)[0])
            if not link or link.startswith(("http://", "https://", "mailto:")):
                continue
            target = (path.parent / link).resolve()
            relative_document = path.relative_to(root)
            if not target.is_relative_to(root):
                errors.append(f"Markdown link escapes repository: {relative_document} → {link}")
            elif not target.exists():
                if target.is_relative_to(private_root) and not require_private:
                    continue
                errors.append(f"Broken Markdown link: {relative_document} → {link}")
    return errors


def audit_repository(
    root: Path, *, require_private: bool = False, require_native_ux: bool = False
) -> list[str]:
    """Return deterministic validation errors; no writes and no historical-artifact gate."""
    errors: list[str] = []
    root = root.resolve()
    for rel in REQUIRED:
        if not (root / rel).is_file():
            errors.append(f"Missing current handoff file: {rel}")
    for name in REVIEW_SPECS:
        rel = f"docs/specs/review/{name}"
        if not (root / rel).is_file():
            errors.append(f"Missing active Review stage contract: {rel}")
    if require_private:
        for rel in PRIVATE_REQUIRED:
            if not (root / rel).is_file():
                errors.append(f"Missing requested private ZIP-only file: {rel}")
    if require_native_ux:
        for rel in ST11_NATIVE_REQUIRED:
            path = root / rel
            if not path.is_file():
                errors.append(f"Missing ST-11 native evidence: {rel}")
            elif path.suffix == ".png" and (
                path.stat().st_size < 1024 or path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n"
            ):
                errors.append(f"Not a valid-sized ST-11 PNG: {rel}")
    if (root / "README.md").is_file():
        readme = (root / "README.md").read_text(encoding="utf-8")
        if ".venv/bin/python -m biocall_studio" not in readme:
            errors.append("README is missing the current source-app launch command")
    if (root / "docs/DEVELOPMENT.md").is_file():
        development = (root / "docs/DEVELOPMENT.md").read_text(encoding="utf-8")
        for command in ("scripts/run_tests.py background", "scripts/verify_handoff.py"):
            if command not in development:
                errors.append(f"Development guide is missing the current command: {command}")
    if (root / ".gitignore").is_file():
        if not re.search(r"(?m)^docs/priv/$", (root / ".gitignore").read_text()):
            errors.append("docs/priv/ must be ignored by Git")
    if (root / ".gitattributes").is_file():
        if "tests/data/**/*.wav filter=lfs" not in (root / ".gitattributes").read_text():
            errors.append("Scientific fixture WAVs must be Git LFS tracked")
    errors.extend(audit_markdown_links(root, require_private=require_private))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-private", action="store_true", help="Require untracked private HPC files"
    )
    parser.add_argument(
        "--require-native-ux",
        action="store_true",
        help="Require present ST-11 native Studio screenshot evidence (not an RV-03 owner gate)",
    )
    args = parser.parse_args()
    errors = audit_repository(
        ROOT, require_private=args.require_private, require_native_ux=args.require_native_ux
    )
    for item in errors:
        print(item, file=sys.stderr)
    print(
        f"Handoff audit: {len(REQUIRED)} current files; {len(REVIEW_SPECS)} Review stages; "
        f"private={args.require_private}; ST-11 native evidence={args.require_native_ux}; "
        f"{len(errors)} errors. This is not an RV-03 scientific/owner sign-off."
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
