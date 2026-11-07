# 02 — BioCall Studio's human-facing, evidence-led README and aggressive Markdown diet

## The README should feel like an application

Today `README.md` is only an installation/developer paragraph: it never shows the **BioCall Studio** branding or the extensive native UI evidence already committed. Lead with `assets/branding/on-background/readme-header.png` (or the appropriately contrasting tracked `lockup-*.png`) and a concise real researcher story: **Train → Detect → Review**. Not a checklist announcing that all stages are “complete”.

Use the existing, provenance-described **genuine real-audio screenshots** from `docs/design/evidence/release-real-data/`:
- `00-studio.png` for native start screen;
- `01-train-collection.png` and `02a-train-training-in-progress.png` for dataset and genuine training;
- `05-detect-results.png` for detected candidates;
- `08-review-gallery.png` and `09-review-one-by-one.png` for full-size Review spectrogram, human labeling and audio control.

Feature trio as two or three compact sections; prefer three visually strong images in a narrative over a 12-image dump. Optional linked gallery to the full `release-real-data/README.md`. It states authentic verified alpaca-hum provenance, 64 source-time candidates and 18 human-Call decisions with 46 intentionally unreviewed—not fabricated negatives. Include accessible descriptive image alt text, relative paths, good GitHub rendering and sensible 680–1000px image widths. Do not claim the screenshot proves installed installers or finished review of all calls.

Keep installation/source launch short and linked to `docs/DEVELOPMENT.md`, a quick practical explanation of who uses the app and what results they get, supported platforms **accurately qualified**, links to a small workflow and contributor guide, and polished GitHub-rendered license badges. **Critical:** BioCall Studio has no root `LICENSE` in the inspected tracked tree; audit exact legal ownership and toolbox GPL-3.0-only/PySide6 redistribution obligations **before** choosing a badge, inventing a license, or publishing redistributable binaries. Include the actual correct local license link once present; otherwise display a factual notice, not a false “MIT” badge. This requirement differs from the MIT `alp-ui` package and GPL toolbox. Avoid version badges that link to nonexistent releases.

## Markdown deletions and consolidation

Protect a compact `docs/VISION.md`, `docs/ARCHITECTURE.md`, developer basics, the actual Model/Train/Detect/Review public data contracts, reproducibility and security rules, current release/installer specs, and `AGENTS.md` + `docs/agent/ROUTING.md` + a concise source map. Keep just one agent entry route and clear owning boundaries.

Perform a reference graph audit, then **remove obsolete, implemented and repetitive markdown** from:
- `docs/specs/review/RV-01`–`RV-10` and historic phase/spec research once code, decisions and relevant verified guarantees have been distilled into short canonical Review contract / `SPECTROGRAM_DECISIONS.md` and tests. Do not delete owner-approved scientific settings/session semantics merely because implementation exists. The old `SPECTROGRAM_GENERATION_INVESTIGATION.md` contains outdated future-tense claims despite implemented spectrogram rendering; resolve without losing unique scientific rationale.
- old qualification and evidence narratives such as `docs/{ST-11_QUALIFICATION,RV-08_QUALIFICATION,UNIT_TESTING,INTEGRATION_TEST_BEHAVIORS,INTEGRATION_TEST_DATA}.md` when they repeat implementation history; **do not delete** test IDs or fixture contracts that scripts/audits rely on. Collapse duplicate indexes only after updating the audit scripts and checks.
- `docs/agent/UPSTREAM_TOOLBOX_WORKFLOW.md`, `SPEC_WRITING_AND_IMPLEMENTATION_PRINCIPLES.md`, `GIT_DELIVERY.md` where overlapping rules can live once under short routing, ownership, test and Git-delivery sections. Replace stage/branch-specific instructions that no longer reflect current `main`.
- numerous per-stage evidence `README.md` files only where a small provenance manifest preserves necessary facts; **retain the actual screenshot PNGs, JSON metadata, brand assets and relevant attribution**. Remove duplicate image sets *only after byte-identical/hash comparison and reference audit*. No automatic bulk deletion of screenshots.

Update `docs/specs/README.md`, `docs/IMPLEMENTATION_SEQUENCE.md`, `AGENTS.md`, `docs/agent/ROUTING.md`, `docs/RELEASE_PROCESS.md`, `docs/DEVELOPMENT.md` to stop describing Review as a placeholder or RV-09/RV-10 as pending when they are already implemented. Clearly distinguish pending owner sign-off from implemented source and current branch evidence; verify their actual integration state first.

## Execution / acceptance

**GitHub API:** inventory, changes, deletion, PR and links. **ChatGPT VM:** relative-link/assets check, badge/link rendering review, docs-to-source/metadata assertions and basic test-ID audit. **Local:** no new real Cocoa captures or physical audio playback required. Genuine existing native screenshots are sufficient for the human README.

**Done:** visibly brand-specific README, recognizable real-workflow screenshots, accurate licensing/release claims, clear first-run instructions; sharply fewer live Markdown files; routing, core vision/architecture, provenance and legal duties intact; no dead links or historic plans masquerading as current implementation.

## Branch and `main` merge gate

Follow [VERSION_CONTROL.md](VERSION_CONTROL.md). Only after spec 01 has merged, branch `docs/biocall-02-human-readme` from that reviewed Studio `main`. Make the brand/screenshots/legal/Markdown consolidation one focused PR, including removal or correction of stale stage and Review-placeholder links. Run image path/link/docs and relevant test-ID audit checks, review and **merge to `main` before spec 03**. Record the resulting main SHA. Do not silently delete required screenshot evidence or run the full Studio source suite in this editorial stage.
