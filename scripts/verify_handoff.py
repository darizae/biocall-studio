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
    "docs/HANDOFF.md",
    "docs/agent/ROUTING.md",
    "docs/agent/SOURCE_MAP.md",
    "docs/agent/SPEC_WRITING_AND_IMPLEMENTATION_PRINCIPLES.md",
    "docs/design/ALP_UI_CONSUMER_CONTRACT.md",
    "docs/design/UX_PARITY_MATRIX.md",
    "docs/design/references/alp-ui-showcase.png",
    "docs/design/prototypes/training-first/index.html",
    "docs/design/prototypes/training-first/app.js",
    "docs/design/prototypes/training-first/styles.css",
    "docs/design/prototypes/training-first/landing-preview.png",
    "docs/design/prototypes/training-first/wiki-preview.png",
    "docs/INTEGRATION_TEST_DATA.md",
    "docs/RELEASE_PROCESS.md",
    "tests/data/README.md",
    "tests/data/SHA256SUMS",
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
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    if not re.search(r"(?m)^docs/priv/$", ignore):
        errors.append("docs/priv/ must be ignored by Git")
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    if "tests/data/**/*.wav filter=lfs" not in attrs:
        errors.append("Binary scientific WAVs must be Git LFS tracked")
    routing = (ROOT / "docs" / "agent" / "ROUTING.md").read_text(encoding="utf-8")
    if "../alpaca-pipelines" not in routing or "../alp-ui" not in routing:
        errors.append("Sibling repos not explicitly mapped in routing")
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
        f"Handoff audit: {len(REQUIRED)} tracked required files; 7 specs; "
        f"private ZIP mode={args.require_private}; {len(errors)} errors."
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
