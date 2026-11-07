# BioCall Studio — post-implementation cleanup and installer-gated release series

**Specs only, not completion claims.** Starting point: `main@2b2137d8db8bb504a57d835aff46a65a73eaccf2`; package `0.1.0a0`, pinned `alp-ui==0.1.0a0` at `8cdc91f...` and `bioacoustics-dl-toolbox[rf]==0.2.0` at `22c1b342...`. Reinspect all branch heads, releases, and working trees before implementation. Keep the standing Train/Detect/Review scientific and user-data safety invariants.

1. [01 — Upstream ownership, spectrogram extraction](01-upstream-ownership.md), coordinated with both upstream library release-spec series.
2. [02 — Branded README and documentation diet](02-human-readme-and-docs.md), reuse the actual release-real-data capture set.
3. [03 — Base suite and reproducible release preparation](03-base-suite-and-release-candidate.md), update exact upstream pins in dependency order.
4. [04 — Installer-gated Studio tag/release](04-installer-gates.md), macOS AND Windows before public promotion.

**User-requested omissions:** no additional generic “genuine macOS Qt captures” requirement—the repo already has real Cocoa captures. No new physical audio playback proof as an arbitrary precondition; code + existing baseline tests cover ordinary source work. No soak, 50k, large real-data performance qualification, long-running durability suites or fresh scientific data capture. Existing release-real-data screenshots are authoritative marketing examples but **not** installed-app/package evidence. Only the minimal native installer smoke checks remain release gates because installers cannot be verified with GitHub source APIs alone.

**GitHub API:** inspect/edit/commit repository source and docs, PRs, CI and release planning. **ChatGPT VM:** targeted and ordinary base tests, Ruff, static audits, wheels and manifest/checksums when dependencies are obtainable. **Native macOS / Windows development or CI runner:** frozen bundle/installer build, actual install/launch/worker and clean uninstall, OS-specific signing/notarization where applicable. Do not mark a local-only action complete using an API checklist.

The historical agent instructions prohibit pushing; this owner explicitly requested new specs committed **via GitHub API**, so API-backed spec branch commits are authorized here. That does not authorize code merges, release tags, releases, distribution uploads, or installer promotion.
