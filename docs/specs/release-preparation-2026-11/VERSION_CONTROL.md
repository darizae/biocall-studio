# Git delivery and immutable cross-repository release chain

**Authoritative for this 2026-11 spec series only.** Owner-approved planning PRs are [alp-ui #1](https://github.com/darizae/alp-ui/pull/1), [toolbox #2](https://github.com/darizae/bioacoustics-dl-toolbox/pull/2), and [BioCall Studio #5](https://github.com/darizae/biocall-studio/pull/5). All three currently use `spec/2026-11-release-preparation` and target `main`. They contain **plans** rather than completed source work. Do not reuse those existing branches as long-lived integration branches.

## Bootstrap all three repositories

Review and merge **each existing planning PR into its own repository's `main` first**, recording the actual merged SHA. Do not close/recreate those PRs or rewrite their branches. This is the first `main` synchronization point, not a source or release promotion. Once merged, every implementation step branches from the **current reviewed `main`**, creates a new focused PR, and merges to `main` only with owner review, accurate test evidence and an updated branch comparison. Never stack on an unmerged earlier step; resolve concurrent changes first. Historical local-only/no-push guidance in `docs/agent/GIT_DELIVERY.md` governed older stages; for this explicitly requested GitHub API delivery series, these reviewed PR/merge steps are the scoped replacement. No force push, tag rewrite or automatic release promotion.

## Library lanes — concurrently across repos, sequential within each

See the authoritative per-repo contracts: [alp-ui VERSION_CONTROL](https://github.com/darizae/alp-ui/blob/main/docs/project/specs/2026-11-release-preparation/VERSION_CONTROL.md) and [toolbox VERSION_CONTROL](https://github.com/darizae/bioacoustics-dl-toolbox/blob/main/docs/specs/2026-11-release-preparation/VERSION_CONTROL.md).

- **alp-ui** `feat/alp-ui-01-reuse-boundaries` → merge `main`; `docs/alp-ui-02-human-readme` → merge; `release/alp-ui-v0.1.0a1` → merge. **Only then** run its own release checks on `main HEAD`, create annotated `v0.1.0a1`, publish tested wheels, and record exact tag target SHA/hash/URL.
- **Toolbox** `feat/toolbox-01-headless-spectrogram` → merge `main`; `docs/toolbox-02-human-readme` → merge; `release/toolbox-v0.3.0` → merge. **Only then** run its own tests/build on `main HEAD`, create annotated `v0.3.0` and publish tested GitHub wheels/notes. If the feature/version decision changes, update refs and notes before tagging.
- These two tracks can be active **in parallel** because they touch independent repositories. Do **not** start Studio 01 until **both actual releases** are published, accessible and checksum-verified. No code copied from an untagged `main` or edited Studio `../sibling` source.

## BioCall Studio main synchronization

| Spec | New implementation branch from latest reviewed Studio `main` | Sync to `main` |
|---|---|---|
| [01 — released upstream adapter](01-upstream-ownership.md) | `feat/biocall-01-released-spectrogram` | Merge only after both upstream releases exist, imports/pins and focused parity checks are verified. |
| [02 — human README/docs](02-human-readme-and-docs.md) | `docs/biocall-02-human-readme` | Base on **post-01 main**, clean docs/evidence/links and merge before candidate. |
| [03 — candidate source and legal/lock](03-base-suite-and-release-candidate.md) | `release/biocall-v0.1.0a1-candidate` | Base on **post-02 main**; bump version, exact dependency/wheel hashes, notices, source test/worker packaging and release notes; focused checks, review, merge. This is a **provisional candidate**, not final immutable build SHA. |
| [04 — installer packaging source](04-installer-gates.md) | `release/biocall-v0.1.0a1-installers` | Branch from **post-03 main**; add/fix shared freezer/worker and macOS/Windows packaging scripts/configs in ONE PR; review/merge into `main` **before building either final installer**. |
| [04 — native macOS and Windows lanes](04-installer-gates.md) | **No new source branches** after freeze. Two OS-specific CI/runners use the **same main commit** and locked wheel hashes. | Run native builds/smoke in parallel only **after** installer-source PR merged; collect logs/artifact SHA-256 without committing new source. |
| [05 — final suite and promotion](05-final-upstream-release-qualification.md) | **No new source branch** for passing qualification. | One full ordinary BioCall Studio suite on the **exact frozen main SHA**, the same upstream wheels as both installers; only then owner-approved tag/release. |

**Critical cut point:** after both source PRs **03 and 04** have merged, set `STUDIO_RELEASE_SHA = main HEAD`. The provisional hash after 03 is NOT a frozen installer source because 04 may add or change packaging code. Build both native installers from `STUDIO_RELEASE_SHA`, using the exact released `alp-ui` and toolbox artifact hashes frozen in that commit. Native tasks may run concurrently, but must not push source code on their own platform-specific branches. Attach evidence to CI artifacts/PR notes or the eventual release manifest without advancing the candidate SHA.

**B5 is last:** the single complete Studio base-suite qualification and check of installer SHA/platform/worker evidence runs on `STUDIO_RELEASE_SHA`. Do **not** bump Studio version or edit release notes between the source/test/build SHA and tag. If B4 or B5 finds a defect, open a focused `fix/biocall-v0.1.0a1-<issue>` PR off current `main`, review/merge, choose **a new** `STUDIO_RELEASE_SHA`, rebuild **both** installers and rerun the entire B5 base-suite gate. Never combine installers or tests from different Studio SHAs, use stale upstream wheels, or silently re-tag.

## Publishing and final state

- Proposed tags: toolbox `v0.3.0` (additive renderer API), alp-ui `v0.1.0a1`, Studio `v0.1.0a1`; actual versions depend on what ships and must be verified against GitHub's published tag/release lists. Each library's tag must point to its **tested merged-main commit** and have released wheel/sdist artifacts BEFORE Studio 01 imports it.
- Studio's tag is created **only after** exact release SHA B5 tests, both native installer gates, license/Qt/GPL compliance and explicit owner promotion approval. Annotated `v0.1.0a1` points to `STUDIO_RELEASE_SHA`; the GitHub Release attaches exactly the tested macOS DMG and Windows installer with real hashes. Neither `spec/` nor `release/` staging branch is tagged. No PyPI publication is implied.
- The **final source tree of each repository's `main`** already includes all three implementation specs, their documentation cleanup and release version when tagged. Verify each tag's commit is on its repo's `main`, `main` isn't accidentally ahead with unqualified candidate changes, both library releases are downloadable, Studio pins and import origins match, and the Studio binary manifest references those released library hashes.
- GitHub source/API and ChatGPT VM/CI cover branches, PRs, source tests and wheel artifacts. **Real macOS/Windows runners** are indispensable for native installers/signing/install smoke. If unavailable, leave B4/B5 blocked; do not prematurely tag.

## Required agent handoff per step

Record: spec ID, repository, base `main` SHA, implementation branch/PR, resulting reviewed **merged main SHA**, exact test commands/results, the relevant upstream tag commit+wheel SHA-256, documented screenshots used (not fresh captures), blocked native/signing/release actions and the next permitted step. Never say “synced to main” for a PR still open; never confuse tag-object SHA with commit SHA.
