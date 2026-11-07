# 03 — Freeze Studio source candidate, metadata, licenses and focused regressions

**Prerequisites:** [Studio 01](01-upstream-ownership.md) integrated the actual tagged/released upstream packages; [Studio 02](02-human-readme-and-docs.md) has the final branded README and slim canonical docs. This spec prepares a release candidate, **not** final comprehensive Studio qualification; only [Studio 05](05-final-upstream-release-qualification.md) runs Studio's full base suite.

## Build an accurate candidate

1. On a focused source PR, verify installed **released** `alp-ui` and `bioacoustics-dl-toolbox` versions, tag SHAs, wheel hashes and direct import paths. Synchronize `pyproject.toml` pinned dependencies and `[tool.biocall-studio.science]` SHAs. Because toolbox publishes GitHub Release assets, not necessarily PyPI, document a reproducible local wheelhouse/direct approved distribution source; do not assume `pip install biocall-studio` will resolve those wheels globally.
2. Reconcile documentation with actual Review code and existing Cocoa/release-real-data captures; keep badge/link/license claims factual. Audit `README.md`, `AGENTS.md`, routing, vision and architecture and verify that Markdown cleanup did not remove test-ID/fixture contracts still required by scripts.
3. Resolve BioCall Studio redistribution license/compatibility in writing before public binaries: GPL-3.0-only toolbox adapted ANIMAL-SPOT notice, `alp-ui` MIT, PySide6/Qt and embedded third-party terms. Do not create a fabricated root LICENSE or GPL/MIT badge.
4. Prepare release manifest draft with exact source tree, locked upstream release artifact checksums, Qt/scientific versions and bundled icon digests, plus concise notes and `0.1.0a1` **proposed** metadata. Build Studio source/wheel if supported; inspect bundled required resources and main/worker entrypoints; no installer claims.
5. **Scoped checks only:** tests directly changed by upstream-adapter, docs/audit scripts, public imports, `python scripts/check_fixtures.py`, `python scripts/verify_handoff.py`, `python scripts/audit_test_ids.py`, Ruff and link checker. Record exact results; no blanket `python scripts/run_tests.py background` here. Stop for a real regression instead of deferring it to final release.

## Tool allocation and exit

**GitHub API:** PR/commits, version/doc/license changes, source/CI status. **ChatGPT VM:** static audits, focused tests, wheel and hashes. **Local native:** none in this spec. No new screenshots, physical playback, soak, 50k replay or large performance work.

**Done:** an accurately pinned **provisional** candidate merged to `main`, evidence/canonical docs consistent, focused checks green (or explicitly blocked), proposed tag **uncreated**, handed off to the packaging-source PR and then two native installer lanes in [04](04-installer-gates.md). The final immutable installer SHA is selected **after** the 04 packaging PR merges.

## Branch, release-candidate PR and provisional SHA

Follow [VERSION_CONTROL.md](VERSION_CONTROL.md). Start from the reviewed **post-02 Studio `main`** using `release/biocall-v0.1.0a1-candidate`. This is the owner-reviewed PR that commits the version bump, exact released-upstream wheel/metadata pins, license notices, worker resource contracts and human-facing release notes. Run **focused** validations only; merge the candidate-prep PR into `main` and record that merge SHA. **Do not declare it the final frozen installer/test SHA:** spec 04 still has a packaging-source PR to merge. No tag, installer upload or complete Studio test suite here; the final release SHA is selected only after the spec 04 packaging PR merges.
