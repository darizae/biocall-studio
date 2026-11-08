# BioCall Studio — source status and release route

**Verified reviewed baseline (2026-11-08):** Studio spec 01 (published upstream spectrogram adapter; preserved in Git history) merged through [PR #6](https://github.com/darizae/biocall-studio/pull/6) into `main@b867f148db1afbc34be8e7b37a6d94512bb0bf0f`. The released `alp-ui v0.1.0a1` and `bioacoustics-dl-toolbox v0.3.0` wheels were independently SHA-256 verified and used for focused Review spectrogram regressions on Python 3.11–3.13. The separate source stage did **not** run Studio's complete suite.

**Source implementation:** Train, Detect and Review are in the main application, including native Review Gallery/List/One by one, audio/playback, session management, safe populated Review data-folder selection, bounded spectrogram queue/cache, finalized reviewed WAV/Raven export and immutable source/result provenance. The earlier local `review`/RV-09/RV-10 *pending implementation* descriptions are obsolete. Review's scientific/annotation behavior is retained in [Review contract](specs/review/README.md) and [spectrogram decisions](specs/review/SPECTROGRAM_DECISIONS.md). [Existing visible Cocoa evidence](design/evidence/review-correction/README.md) and [genuine real-audio release screenshots](design/evidence/release-real-data/README.md) describe what was actually captured, not current installed binaries. Final owner visual approval, physical audio/accessibility, macOS/Windows installed-app behavior and signing remain distinct gates.

## Release status

1. **Specs 01–04 — Completed/merged** (published upstream adapter, human README, provisional candidate, installer packaging source; individual specs preserved in Git history at the [release tag](https://github.com/darizae/biocall-studio/tree/v0.1.0a1) and in [PRs #6–#8](https://github.com/darizae/biocall-studio/pulls?q=is%3Apr+is%3Amerged)).
2. **05 — Completed.** Full Studio ordinary suite ran locally at the exact binary-source SHA `8354089cc7f0878e3dd594ca3620e90c4f16b6f8` (302 passed, 1 skipped, 5 deselected, Ruff and audits passing) in the repair worktree before the final merge.
3. **06 — Completed.** Both native installers built and smoke-tested at the same SHA; owner-authorized **unsigned alpha [`v0.1.0a1` pre-release published](https://github.com/darizae/biocall-studio/releases/tag/v0.1.0a1)** with README download links ([PR #14](https://github.com/darizae/biocall-studio/pull/14)) and full provenance in [release process](RELEASE_PROCESS.md).

The completed 2026-11 spec series is preserved in Git history and in the release tag. A documentation or source CI check is not evidence of signed/notarized macOS or Windows installers. Studio's application source is licensed **GPL-3.0-only**; third-party notices record actual component licenses and redistribution materials shipped with the alpha. Native signing/notarization and installed Review GUI export remain unverified alpha limitations.

## Canonical retained contracts

[Vision](VISION.md) · [Architecture](ARCHITECTURE.md) · [Train workflow](models/WORKFLOW_RULES.md) · [Detect](PREDICTION.md) · [Review](specs/review/README.md) · [Model](science/MODEL_EXPORT_CONTRACT.md) · [test IDs](UNIT_TESTING.md) · [integration IDs](INTEGRATION_TEST_BEHAVIORS.md) · [fixtures](INTEGRATION_TEST_DATA.md) · [release process](RELEASE_PROCESS.md).
