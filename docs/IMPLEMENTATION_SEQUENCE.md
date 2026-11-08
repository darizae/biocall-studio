# BioCall Studio — source status and release route

**Verified reviewed baseline (2026-11-08):** Studio [spec 01](specs/release-preparation-2026-11/01-upstream-ownership.md) merged through [PR #6](https://github.com/darizae/biocall-studio/pull/6) into `main@b867f148db1afbc34be8e7b37a6d94512bb0bf0f`. The released `alp-ui v0.1.0a1` and `bioacoustics-dl-toolbox v0.3.0` wheels were independently SHA-256 verified and used for focused Review spectrogram regressions on Python 3.11–3.13. The separate source stage did **not** run Studio's complete suite.

**Source implementation:** Train, Detect and Review are in the main application, including native Review Gallery/List/One by one, audio/playback, session management, safe populated Review data-folder selection, bounded spectrogram queue/cache, finalized reviewed WAV/Raven export and immutable source/result provenance. The earlier local `review`/RV-09/RV-10 *pending implementation* descriptions are obsolete. Review's scientific/annotation behavior is retained in [Review contract](specs/review/README.md) and [spectrogram decisions](specs/review/SPECTROGRAM_DECISIONS.md). [Existing visible Cocoa evidence](design/evidence/review-correction/README.md) and [genuine real-audio release screenshots](design/evidence/release-real-data/README.md) describe what was actually captured, not current installed binaries. Final owner visual approval, physical audio/accessibility, macOS/Windows installed-app behavior and signing remain distinct gates.

## Current ordered release stages

1. **01 — Completed/merged.** [Published upstream spectrogram adapter](specs/release-preparation-2026-11/01-upstream-ownership.md) with exact science pins in [`pyproject.toml`](../pyproject.toml).
2. **02 — Current documentation PR.** [Human-facing README and safe Markdown consolidation](specs/release-preparation-2026-11/02-human-readme-and-docs.md); no final-suite claim.
3. **03 — Pending.** [Source/package and legal/lock candidate](specs/release-preparation-2026-11/03-base-suite-and-release-candidate.md), only after spec 02 merges.
4. **04 — Pending.** [Installer source/native macOS and Windows lanes](specs/release-preparation-2026-11/04-installer-gates.md) from one frozen reviewed SHA.
5. **05 — Last.** [Local full Studio suite, owner promotion and post-release spec-series retirement](specs/release-preparation-2026-11/05-final-upstream-release-qualification.md). **Do not retire the 2026-11 spec series before this gate.**

[Version-control and main synchronization rules](specs/release-preparation-2026-11/VERSION_CONTROL.md) govern this series. A documentation or source CI check is not evidence of signed/notarized macOS or Windows installers. App-level licensing is currently **undeclared**; resolve it and third-party GPL/Qt redistribution obligations before release. No Studio installer, Studio `v0.1.0a1` tag, full local suite or release approval is asserted.

## Canonical retained contracts

[Vision](VISION.md) · [Architecture](ARCHITECTURE.md) · [Train workflow](models/WORKFLOW_RULES.md) · [Detect](PREDICTION.md) · [Review](specs/review/README.md) · [Model](science/MODEL_EXPORT_CONTRACT.md) · [test IDs](UNIT_TESTING.md) · [integration IDs](INTEGRATION_TEST_BEHAVIORS.md) · [fixtures](INTEGRATION_TEST_DATA.md) · [release process](RELEASE_PROCESS.md).
