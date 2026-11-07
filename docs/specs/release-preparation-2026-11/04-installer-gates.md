# 04 — Merge installer build infrastructure, then qualify two native Studio installers

**Prerequisites:** [Studio 03](03-base-suite-and-release-candidate.md) merged the provisional candidate and package version/pins into `main`, and both upstream libraries have **published** released wheels. Follow the [branch/merge/release contract](VERSION_CONTROL.md). **This spec owns one shared packaging-source PR and two native installer lanes.** The one complete Studio source test suite, tag and GitHub Release belong **only** to [Studio 05](05-final-upstream-release-qualification.md).

Existing [macOS 06](../06-macos-release-and-installer.md), [Windows 07](../07-windows-release-and-installer.md) and [release process](../../RELEASE_PROCESS.md) include stale “Review placeholder” and heavyweight qualification text. Reconcile their active packaging requirements with this approved reduced scope without losing license, signature, actual installer or safe data ownership obligations.

## A. One packaging PR before source freeze

1. From **post-03 `main`**, create **`release/biocall-v0.1.0a1-installers`**. Implement the shared freezer/bootstrap and both platform-specific packaging configurations, worker dispatch/resource bundling, version/brand references and deterministic native-smoke scripts; avoid editable sibling code paths and untested package versions. Put macOS files and Windows files in clearly separate paths, with a single reviewed dependency manifest.
2. Test packaging configuration, imports, any feasible VM smoke, source resource inclusion and static audits. Open an implementation PR, inspect the diff and dependency/branding/licensing information, then **review and merge this PR to `main`**. Merge any additional source corrections **now**, before freezing.
3. Set **`STUDIO_RELEASE_SHA = main HEAD`** *only after this merge* and record the exact already-merged `pyproject.toml` version, published upstream tag-target commit SHAs, released wheel SHA-256s and platform build configuration. This is the **one immutable build candidate**; no new source commits in either native lane.

## B. Two independent native lanes — parallel only after A

**macOS native runner:** checkout exactly `STUDIO_RELEASE_SHA`, install exact released wheels, build one BioCall Studio `.app` and `.dmg` including checked-in `assets/branding/icons/icon.icns`, Qt/torch/scientific runtime, public alp-ui fonts and all Train/Detect/Review workspaces and frozen `--worker` modes. Install **outside** the checkout, launch all workspaces, do a small deterministic worker/load/export smoke, restart, check per-user storage outside the bundle and safe uninstall preservation. For public signed distribution, verify Developer ID signature, hardened runtime, notarization/stapling and Gatekeeper with actual credentials. Record native runner/OS, build logs, signing outcome and real artifact SHA-256. **Do not** capture a new generic UI gallery.

**Windows native x86-64 runner:** checkout **the same** `STUDIO_RELEASE_SHA`, install the same verified wheel versions/hashes, create the installable BioCall Studio app and installer with checked-in `assets/branding/icons/icon.ico`, Qt/torch runtime and bundled `--worker` entries. Install outside source, launch all workspaces, perform small worker/load/export/restart/uninstall smoke, verify per-user data preservation and signature if required for distribution. Record native runner/OS, actual installer hash and evidence. Linux-generated binaries or Mac screenshots are **not** Windows qualification.

**Parallel restriction:** build/test on separate native runners but **do not open independent platform source PRs after A**. Both lanes must use the exact same release SHA and approved upstream wheel hashes. If either reveals a source defect, open a focused **`fix/biocall-v0.1.0a1-<issue>`** branch from `main`, review/merge, re-freeze **new** `STUDIO_RELEASE_SHA`, and rebuild/reverify **both** installers. Never combine Mac from one SHA with Windows from another.

## Exclusions and handoff

Existing real Cocoa screenshots under `docs/design/evidence/release-real-data` and `docs/design/evidence/review-correction/native-rv10` are good README material. No compulsory new native capture, physical playback proof, soak, 50k, ≥600-second or large field-data performance run, or full Train→Detect→Review scientific retraining on native installers. Studio 05 owns the **one complete ordinary source suite**.

**GitHub API/VM:** packaging source PRs, metadata, static tests/checksums. **Native Mac/Windows:** actual freeze/sign/install/launch/uninstall. Do not call a source build “installed” evidence. **Done only when:** installer-source PR merged to `main`, one final frozen commit chosen, both OS installer hashes and minimal genuine native smoke evidence recorded, and all absent license/signing/hardware gates marked blocked. **No Studio tag or public GitHub Release in spec 04.**
