# 04 — Produce and minimally qualify macOS and Windows Studio installers

**Prerequisite:** [Studio 03](03-base-suite-and-release-candidate.md) has frozen an immutable candidate with exact **released** upstream wheel hashes and app source identity. This spec is only the native **installer stage**. The **single final Studio base-suite run and public tag/release promotion** are deferred to [Studio 05](05-final-upstream-release-qualification.md).

Historical files [macOS 06](../06-macos-release-and-installer.md), [Windows 07](../07-windows-release-and-installer.md) and [release process](../../RELEASE_PROCESS.md) include stale “Review placeholder” and heavyweight qualification prose; correct those under the source/doc spec. Preserve only real installer, legal and basic native smoke obligations, not duplicate source/scientific experiments.

## Two independent, parallel native lanes on the same source candidate

**macOS runner:** freeze and package BioCall Studio `.app`/`.dmg` from the pinned source and released wheels, with Qt/torch scientific runtime, `alp-ui` fonts, all Train/Detect/Review workspaces, the actual suite `assets/branding/icons/icon.icns` and self-contained `--worker` dispatch. Install outside the checkout, launch the app, open each workspace, perform a **small deterministic** worker/import/export smoke, restart and check user data outside the bundle; preserve user recordings on uninstall. For a signed public build, verify actual Developer ID/hardened runtime, notarization/staple and Gatekeeper with real credentials—not inferred from a .dmg filename. Record tested artifact SHA-256, OS/architecture, build log and outcome.

**Windows x86-64 runner:** build installable app and installer from the same frozen candidate, use actual suite `assets/branding/icons/icon.ico` in installed identity, package scientific/Qt runtime and all `--worker` modes, fresh install/launch all workspaces, small deterministic worker/load/export smoke, restart, user-data paths and clean uninstall preservation. Verify signing if required by public distribution policy. Record tested artifact SHA-256 and platform/runner logs. Linux VM or macOS capture is not Windows execution evidence.

These two lanes **may run in parallel** but share immutable source SHA, pinned upstream wheel versions/checksums, release settings and branding, and do not change source independently. If either lane requires a source fix, return to [Studio 03](03-base-suite-and-release-candidate.md), regenerate **both** candidate installers and checksums; never combine artifacts from different commits.

## Exclusions / gate

The existing real Cocoa screenshots (`docs/design/evidence/release-real-data` and `docs/design/evidence/review-correction/native-rv10`) are suitable for the README. **No blanket request** for fresh native screenshots, physical playback verification, long-running durability, 50k or field-performance benchmark, or a full native Train→Detect→Review retrain journey. Source correctness is qualified in the one final Studio test spec.

**GitHub API / VM:** packaging source and manifest, checksum helpers. **Native macOS and Windows environments:** actual freezer/sign/install/uninstall verification. **Done when:** two genuinely runnable, checksummed installer artifacts from identical source/upstream versions; any missing platform/signature/license evidence remains explicitly blocked. **Do not create a Git tag or publish a GitHub Release here.**
