# 06 — LAST: Publish verified Studio installers, then retire completed specs across all three repositories

**Execution position: prompt 14.** This is the final administrative/release and documentation-cleanup spec, **only in BioCall Studio**. The *last build/qualification tasks* are the macOS and Windows native installer lanes (prompts 12 and 13, in parallel). The complete BioCall Studio source suite must already have run **locally before them** under [spec 05](05-final-upstream-release-qualification.md). Do **not** rerun the full Studio suite merely because installers completed with the exact unchanged inputs.

## Mandatory promotion gate — do not publish prematurely

1. Inspect the *actual* published [alp-ui](https://github.com/darizae/alp-ui/releases) and [toolbox](https://github.com/darizae/bioacoustics-dl-toolbox/releases) releases and tagged commit SHAs and the SHA-256 of their released wheel/sdist assets. Read the Studio `pyproject.toml` version and exact upstream pin/provenance and recorded `STUDIO_RELEASE_SHA`; ensure it is a reviewed commit currently reachable from Studio `main`.
2. Verify the **local Mac** spec 05 base-suite receipt (actual source SHA, clean worktree, versioned installed released wheels/import origins, ordinary unit/integration pass/skip/fail counts, Ruff and audits). A remote CI or ChatGPT VM result is supplementary, **not** a substitute.
3. Verify both independently genuine **native macOS** and **Windows x64** installed-app installer receipts produced **from the same `STUDIO_RELEASE_SHA` and upstream artifact hashes**, and include the actual `.dmg` and Windows installer `.exe` SHA-256, short installed-worker/load/export/restart smoke, safe user-data and uninstall behavior, correct icons, app identities and signing/Gatekeeper or Windows trust policy as advertised. **GitHub-hosted `windows-2025` runs can be valid Windows-native automated build/install/smoke evidence** when their actual logs prove the claimed checks; GUI operations they cannot exercise remain explicitly unqualified and can be completed on an interactive remote Windows VM.
4. Resolve the application distributor's real license and GPL-3.0-only toolbox, MIT alp-ui, PySide6/Qt, font and binary redistribution obligations, and obtain explicit owner promotion approval. An unsigned development-only installer or unresolved legal status is **not** permission to release it as a publicly verified signed installer.
5. A missing Mac **or** Windows native gate, missing local spec 05 receipt, mismatched SHA/hash, incorrect license or missing approval **blocks** the public Studio release and all post-release spec deletions. Do not create a tag as a placeholder or claim a blocked installer passed.

## Tag once, from the exactly tested source commit

Only after every gate above passes, verify the Studio version is already in the frozen `main` tree (proposed `0.1.0a1`), create the **annotated `v0.1.0a1` tag** at `STUDIO_RELEASE_SHA`, publish a GitHub Release with the **exact tested** Mac DMG, Windows installer EXE and their real SHA-256 digests, concise human-facing release notes, the upstream versions/tag target SHAs/wheel hashes, supported platform truth and legal/source/notice links. No post-test version bump, commit or relabeling of a binary; do not force-move a tag.

If source or upstream-version changes are needed, open a reviewed fix PR to `main`, choose a **new** `STUDIO_RELEASE_SHA`, return to **spec 05 local test first**, then rerun **both** spec 04 native installer lanes, then re-enter this gate. Actual Native Windows CI builds without valid GUI evidence may require an additional interactive remote Windows VM check, but not another scientific/long-running test campaign.

## Only AFTER all three releases are verified: retire finished/stale specs

This cleanup is owned **only by BioCall Studio spec 06**; neither upstream repository needs another final spec. Keep all completed specs in immutable release tags and Git history. Deletion happens **after** Studio tagging so the tested source/installer SHA remains unchanged; the three documentation-only merges intentionally move `main` beyond the release tags and must not be presented as a new executable release.

Create and review **three independent documentation-only PRs** based on each repository's *then-current* `main`:

| Repo | Branch | Content to retire after a reference audit |
|---|---|---|
| [alp-ui](https://github.com/darizae/alp-ui) | `docs/alp-ui-post-release-spec-retirement` | All five files under `docs/project/specs/2026-11-release-preparation/`; remaining completed duplicate historical task/project Markdown only if unique normative content has been preserved in canonical docs. |
| [bioacoustics-dl-toolbox](https://github.com/darizae/bioacoustics-dl-toolbox) | `docs/toolbox-post-release-spec-retirement` | All five files under `docs/specs/2026-11-release-preparation/`; retain the few genuinely useful existing docs, license, NOTICE and release history. |
| [biocall-studio](https://github.com/darizae/biocall-studio) | `docs/biocall-post-release-spec-retirement` | All **eight** files under `docs/specs/release-preparation-2026-11/`, including spec 05, **this spec 06**, index and version-control instructions; also truly redundant completed legacy RV/ST/installer specifications only after the retained maintenance and scientific decisions have been moved into live canonical docs. |

**Non-negotiable preservation:** concise `AGENTS.md`/agent-routing, core `VISION` and `ARCHITECTURE`, public API/scientific safety contracts, reproducible packaging and release-maintenance instructions, test-index and fixture contracts still used by audits, actual brand artwork, real screenshots and their provenance JSON, and GPL/MIT/Qt/font notices. Do not delete PNGs, icons or machine-readable capture evidence. Do not use a blunt glob or archive the old Markdown into another tracked folder.

Before deleting this spec, add a **short factual release record** to an existing durable Studio release notes/process location, with actual local spec 05 test proof, Mac/Windows native receipts, three GitHub Release links, tag commit SHAs, wheel/installer hashes and licenses. Update references from `AGENTS.md`, release process, Markdown indexes/READMEs and scripts. Run bounded link/image/reference audits, legal/asset preservation checks, test-ID/fixture audit if impacted, and `git diff --check`. After human/code review, merge each cleanup PR into its respective `main`. **Do not** repeat the full Studio base suite for a docs-only removal or retag the release commit.

**Final evidence:** three genuine release URLs, exact tag→tested commit mappings, the actual local Studio suite receipt, both installer native receipts, three cleanup PRs/merged-`main` SHAs, no stale broken links and no incomplete release claims. If an external native/signing or repository-write step remains blocked, preserve unfinished specs and report the blocker.
