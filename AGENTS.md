# BioCall Studio — contributor and agent entry

BioCall Studio is **one** Python/PySide6 desktop app with source-implemented **Train → Detect → Review** workspaces. Read [routing](docs/agent/ROUTING.md), then the affected [source/data contract](docs/ARCHITECTURE.md) and tests; do not load all historical specs. Current release-stage ownership and verified Git SHAs live in [implementation status](docs/IMPLEMENTATION_SEQUENCE.md).

## Scientific, safety and UI boundaries

- Train owns Collection/Dataset/Model production; Detect owns immutable CNN/RF Results; Review owns eligible-candidate sessions, source-linked spectrogram cache, human labels, finalization and **new** reviewed corpus exports. Keep source WAVs read-only and metadata in app-owned versioned roots outside recording trees. [Architecture](docs/ARCHITECTURE.md), [Detect](docs/PREDICTION.md), [Review](docs/specs/review/README.md), [Train](docs/models/WORKFLOW_RULES.md).
- Validate untrusted paths, audio, source digests and relative references before publication; use bounded reads and staging, stable source-time provenance, no-clobber commits and truthful failure/cancel handling. Never treat missing sources as zero candidates, unreviewed as negative, or an offscreen screenshot as native/release evidence.
- Reusable NumPy/audio scientific behavior belongs in the **released** `bioacoustics-dl-toolbox`; reusable native presentation primitives belong in `alp-ui`. Confirm real installed origins, versions, upstream commit SHAs and published wheel hashes from `pyproject.toml`. Do not use editable sibling packages to qualify a release.
- Preserve the reviewed Studio/Detect hierarchy and Review native-sidebar/layout evidence. UI uses installed public `alp-ui` and real Qt for focus, keyboard, compact layout, HelpHint and native appearance. [UI evidence](docs/design/evidence/review-correction/README.md), [source map](docs/agent/SOURCE_MAP.md).
- Tests are **evidence, not documentation claims**. Update existing `UT-*`/`IT-*` indexes before changing contracts, run focused actual regressions, Ruff and [test-ID audit](scripts/audit_test_ids.py), and report failures/skips. [Release process](docs/RELEASE_PROCESS.md) records the shipped `v0.1.0a1` alpha provenance and gates future releases; native qualification is not covered by ordinary CI.

## Branches and qualification

Each change branches from the latest *reviewed, merged* `main`, receives a focused PR/review, then merges on green owned checks. Do not force-push/rewrite tags, manufacture installer evidence, or claim approval from a PR that remains open. Release promotion requires exact cross-repository provenance, native installer qualification, licensing review and owner signoff. Use [development and test commands](docs/DEVELOPMENT.md) for day-to-day work.
