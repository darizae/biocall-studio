# BioCall Studio — release preparation and current execution order

The first two upstream library releases are **already published**:
- [alp-ui `v0.1.0a1`](https://github.com/darizae/alp-ui/releases/tag/v0.1.0a1)
- [bioacoustics-dl-toolbox `v0.3.0`](https://github.com/darizae/bioacoustics-dl-toolbox/releases/tag/v0.3.0)

The original BioCall Studio implementation PRs for [01](01-upstream-ownership.md) (released toolbox adapter), [02](02-human-readme-and-docs.md) (genuine branded README/Markdown trimming) and [03](03-base-suite-and-release-candidate.md) (provisional source candidate) are **merged**. The [shared installer packaging-source PR #9](https://github.com/darizae/biocall-studio/pull/9) for [04](04-installer-gates.md) is also merged. These historical specs remain available for traceability; do not rerun their implementation stages merely because they are listed here.

## Remaining work — order matters

1. **[05 — local full BioCall Studio base suite](05-final-upstream-release-qualification.md) (execution prompt 11).** From the **current reviewed Studio `main` after the packaging PR**, freeze `STUDIO_RELEASE_SHA`; locally on the developer's Mac, verify the published upstream wheels and run **the single full ordinary Studio unit/integration suite** plus Ruff/audits. **No installer, tag, release or cleanup is required to run this test.** A remote ChatGPT VM/CI result does not substitute for this requested local pass.
2. **[04 — native installer lanes](04-installer-gates.md) (execution prompts 12 and 13).** Only after the local 05 suite passes, build/verify macOS and Windows installers **in parallel from the identical frozen `STUDIO_RELEASE_SHA` and upstream wheel hashes**. The macOS lane can run on the owner's Mac; the Windows x64 lane can run remotely on a GitHub-hosted `windows-2025` VM and, if needed for visible UI checks, an interactive Windows x64 cloud VM. No borrowing a physical Windows laptop is required.
3. **[06 — publish and retire verified specs](06-release-and-post-release-cleanup.md) (execution prompt 14).** This last administrative step checks both real native installers + the earlier local suite and required licensing/signatures/owner approval; then and **only then** annotates Studio's tested `main` SHA, publishes the exact tested installers and, after all three genuine releases are verified, coordinates docs-only removal of completed/stale specifications in **all three repositories**.

This split puts **all substantive native installer execution at the end** while preserving the immutable rule that you cannot publish a release before both installers exist. Do not rerun the local full suite after successful installers when no source, version, wheel or lock has changed. **A source change discovered on either platform requires a reviewed fix PR, a new frozen SHA, a fresh local 05 suite and rebuild of both installers** before 06 promotion.

The [Git/version-control contract](VERSION_CONTROL.md) owns exact PR/merge/tag handoffs. Existing `spec/2026-11-release-preparation` branches are completed planning sources; start any *new* correction PR from current reviewed `main`, not from old spec branches.

## Scope protections

No unnecessary new Cocoa screenshots, physical audio-device playback campaign, soak, 600-second runs, 50k reruns or large real-data performance qualification. Reuse real release-real-data screenshots in human-facing docs. Preserve the approved `AGENTS.md`/routing, `VISION`/`ARCHITECTURE`, domain science and safety contracts, trademarks/brand assets, screenshots/provenance JSON, and GPL/MIT/Qt/font compliance. Real Mac/Windows installation and basic worker/user-data smoke remain installer-specific gates.

**GitHub API:** documents, branches/PRs, published release verification, CI and artifact metadata. **Local Mac:** final full Studio test and macOS installer. **GitHub Windows runner / remote Windows VM:** actual Windows native installer. **Spec 06:** gated release promotion and post-release doc retirement.
