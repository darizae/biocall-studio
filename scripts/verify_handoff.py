"""Static handoff/Markdown routing audit; independent of local sibling checkout and SSH."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "AGENTS.md",
    "docs/agent/ROUTING.md",
    "docs/science/BINARY_CLASSIFICATION_CONTRACT.md",
    "docs/specs/SPEC_04_5_UPSTREAM_AUDIO_EXTRACTION.md",
    "docs/agent/GIT_DELIVERY.md",
    "docs/specs/SPEC_01_CLOSEOUT.md",
    "docs/design/evidence/README.md",
    "docs/agent/SOURCE_MAP.md",
    "docs/agent/SPEC_WRITING_AND_IMPLEMENTATION_PRINCIPLES.md",
    "docs/design/ALP_UI_CONSUMER_CONTRACT.md",
    "docs/design/UX_PARITY_MATRIX.md",
    "docs/design/PROTOTYPE_ACCEPTANCE.md",
    "docs/design/references/alp-ui-showcase.png",
    "docs/design/prototypes/training-first/index.html",
    "docs/design/prototypes/training-first/app.js",
    "docs/design/prototypes/training-first/styles.css",
    "docs/design/prototypes/training-first/landing-preview.png",
    "docs/design/prototypes/training-first/wiki-preview.png",
    "docs/INTEGRATION_TEST_DATA.md",
    "docs/RELEASE_PROCESS.md",
)


PRIVATE_REQUIRED = (
    "docs/priv/hpc-source-access/SKILL.md",
    "docs/priv/hpc-source-access/references/site.md",
    "docs/priv/hpc-source-access/scripts/hpc-source.sh",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-private", action="store_true", help="Assert private ZIP-only HPC files included"
    )
    parser.add_argument(
        "--require-native-ux",
        action="store_true",
        help="Require checked-in native macOS UI shots and README references (Spec 01 closeout)",
    )
    args = parser.parse_args()
    errors: list[str] = []
    if args.require_private:
        for rel in PRIVATE_REQUIRED:
            if not (ROOT / rel).is_file():
                errors.append(f"Missing required private ZIP-only file: {rel}")
    for rel in REQUIRED:
        if not (ROOT / rel).is_file():
            errors.append(f"Missing required handoff file: {rel}")
    for i in range(1, 8):
        specs = list((ROOT / "docs" / "specs").glob(f"{i:02d}-*.md"))
        if len(specs) != 1:
            errors.append(f"Expected exactly one spec {i:02d}; found {specs}")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    # Static docs validation only. Native provenance, UX parity and Git commits require
    # human/CI evidence.
    image_paths = re.findall(r"!\[[^\]]+\]\(([^)]+)\)", readme)
    for rel in image_paths:
        if rel.startswith(("http://", "https://")):
            continue
        if not (ROOT / rel).is_file():
            errors.append(f"README screenshot image missing: {rel}")
    for command in (
        "python3.12 -m venv .venv",
        "python -m pip install -e ../alp-ui",
        "python -m biocall_studio",
    ):
        if command not in readme:
            errors.append(f"README missing expected local setup/run command: {command}")
    if args.require_native_ux:
        directory = ROOT / "docs/design/evidence/spec-01-native"
        for name in (
            "select.png",
            "wiki.png",
            "settings.png",
            "empty-collections.png",
            "empty-datasets.png",
            "empty-models.png",
            "empty-runs.png",
            "select-narrow.png",
        ):
            shot = directory / name
            if not shot.is_file() or shot.stat().st_size < 1024:
                errors.append(f"Missing valid-sized persistent macOS Trainer screenshot: {shot}")
            elif shot.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
                errors.append(f"Not a real PNG: {shot}")
        if "**Missing" in (ROOT / "docs/design/evidence/README.md").read_text(encoding="utf-8"):
            errors.append("Native UX evidence ledger still contains Missing entries")
        run_directory = ROOT / "docs/design/evidence/spec-04-native"
        for name in (
            "run-active.png",
            "run-cancelling.png",
            "run-failed.png",
            "run-completed.png",
            "runs-history.png",
            "run-narrow.png",
        ):
            shot = run_directory / name
            if not shot.is_file() or shot.stat().st_size < 1024:
                errors.append(f"Missing valid-sized persistent Spec 04 screenshot: {shot}")
            elif shot.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
                errors.append(f"Not a real PNG: {shot}")
            if name in {"run-active.png", "runs-history.png"} and (
                f"docs/design/evidence/spec-04-native/{name}" not in readme
            ):
                errors.append(f"README must embed real native Spec 04 screenshot: {name}")
        training_directory = ROOT / "docs/design/evidence/spec-05-native"
        for name in (
            "train-cnn.png",
            "train-rf.png",
            "train-cnn-advanced.png",
            "train-rf-advanced.png",
            "presets-list.png",
            "presets-unsaved.png",
            "presets-confirm-delete.png",
            "train-cnn-narrow-focus.png",
            "run-cnn-plot.png",
            "run-rf-plot.png",
            "model-detail.png",
            "model-detail-rf.png",
            "alp-ui-showcase-current.png",
        ):
            shot = training_directory / name
            if not shot.is_file() or shot.stat().st_size < 1024:
                errors.append(f"Missing valid-sized persistent Spec 05 screenshot: {shot}")
            elif shot.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
                errors.append(f"Not a real PNG: {shot}")
            if name in {"train-cnn.png", "run-rf-plot.png", "model-detail-rf.png"} and (
                f"docs/design/evidence/spec-05-native/{name}" not in readme
            ):
                errors.append(f"README must embed real native Spec 05 screenshot: {name}")
        diagnostics_directory = ROOT / "docs/design/evidence/spec-05d-native"
        for name in (
            "run-open-log.png",
            "settings-diagnostics.png",
            "export-privacy-confirmation.png",
            "run-open-log-narrow.png",
            "settings-stacked-narrow.png",
            "settings-diagnostics-narrow.png",
            "alp-ui-showcase-current.png",
        ):
            shot = diagnostics_directory / name
            if not shot.is_file() or shot.stat().st_size < 1024:
                errors.append(f"Missing valid-sized persistent Spec 05d screenshot: {shot}")
            elif shot.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
                errors.append(f"Not a real PNG: {shot}")
            if name in {"run-open-log.png", "settings-diagnostics.png"} and (
                f"docs/design/evidence/spec-05d-native/{name}" not in readme
            ):
                errors.append(f"README must embed real native Spec 05d screenshot: {name}")
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    if not re.search(r"(?m)^docs/priv/$", ignore):
        errors.append("docs/priv/ must be ignored by Git")
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    if "tests/data/**/*.wav filter=lfs" not in attrs:
        errors.append("Binary scientific WAVs must be Git LFS tracked")
    source_map = (ROOT / "docs" / "agent" / "SOURCE_MAP.md").read_text(encoding="utf-8")
    if any(
        repo not in source_map
        for repo in ("../alpaca-pipelines", "../alp-ui", "../bioacoustics-dl-toolbox")
    ):
        errors.append("Sibling repos not explicitly mapped in source map")
    # Token-budget guard: AGENTS is a universal entrypoint, not a per-spec manual.
    entry = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    if len(entry.split()) > 450:
        errors.append("AGENTS.md exceeds 450 words; move scoped requirements into the owning spec")
    for scoped_name in (
        "TRAINING_CONFIGURATION_CATALOG",
        "TRAINING_PRESETS",
        "SPEC05_CONFIGURATION_EXTENSION",
    ):
        if scoped_name in entry:
            errors.append(f"AGENTS.md contains spec-only route: {scoped_name}")
    for spec_path in (
        *(ROOT / "docs" / "specs").glob("[0-9][0-9]-*.md"),
        ROOT / "docs" / "specs" / "SPEC_04_5_UPSTREAM_AUDIO_EXTRACTION.md",
    ):
        if spec_path.exists() and "**Scoped references:**" not in spec_path.read_text(
            encoding="utf-8"
        ):
            errors.append(
                f"Missing spec-local scoped reference entry: {spec_path.relative_to(ROOT)}"
            )
    # Ensure the intermediate upstream phase is discoverable by the router and sequence.
    for rel in ("docs/agent/ROUTING.md", "docs/IMPLEMENTATION_SEQUENCE.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        if "SPEC_04_5_UPSTREAM_AUDIO_EXTRACTION.md" not in text:
            errors.append(f"Spec 04.5 is not routed from {rel}")
    # This catches ordinary relative Markdown links, not arbitrary dynamically-created code strings.
    for path in ROOT.rglob("*.md"):
        if "docs/priv" in path.relative_to(ROOT).as_posix():
            continue  # Private notes can contain references outside the distributed project.
        doc = path.read_text(encoding="utf-8")
        for link in re.findall(r"(?<!!)\[[^\]]+\]\(([^\s)]+)(?:\s+[^)]*)?\)", doc):
            link = unquote(link.split("#")[0])
            if not link or link.startswith(("http://", "https://", "mailto:")):
                continue
            target = (path.parent / link).resolve()
            if not target.is_relative_to(ROOT.resolve()):
                errors.append(f"Markdown link escapes bundle: {path.relative_to(ROOT)} → {link}")
            elif not target.exists():
                # Private site material is deliberately ignored and absent in clean Git clones / CI.
                if target.is_relative_to(ROOT / "docs" / "priv") and not args.require_private:
                    continue
                errors.append(f"Broken Markdown link: {path.relative_to(ROOT)} → {link}")
    for item in errors:
        print(item, file=sys.stderr)
    print(
        f"Handoff audit: {len(REQUIRED)} tracked required files; 8 phases (including 04.5); "
        f"private ZIP mode={args.require_private}; native UX gate={args.require_native_ux}; "
        f"{len(errors)} errors."
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
