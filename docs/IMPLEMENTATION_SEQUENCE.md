# BioCall Studio — implementation sequence

**Branch policy:** create `detect` from a clean `main`; make each stage branch from the current `detect` (e.g., `detect-st01-prototype`, `detect-st02-shell`). A stage returns to `detect` only after owner review; do not merge automatically. `main` remains unaffected until unified qualification and explicit approval. Check branch existence and history before creating anything.

Only the **active** stage gets a detailed spec. The remaining rows are scoped acceptance targets to turn into specs *one at a time*. Do not implement a later row early.

| Stage | Owns / acceptance outcome |
|---|---|
| **[ST-01](specs/ST-01-prototype.md)** | Interactive HTML/CSS/JS launchpad + Detect prototype; native Train reference; design decisions, UX matrix and states. **No Python or scientific implementation.** |
| **ST-02 — Native shell** | Single `QApplication`, Studio launchpad and workspace navigation; Train integrated without behavior/visual regressions; Review placeholder. Native screenshots and Qt integration tests. |
| **ST-03 — Detect workspace** | Independent app-owned storage, Collection identity/versioned metadata, source-root relinking and stale path checks, artifact ownership and publication. Path/storage tests. |
| **ST-04 — WAV discovery** | Safe recursive enumeration, explicit inclusion/exclusion, Train-derived WAV avoidance, no symlink escape, deterministic order/duplicates, header validation and rescans. Real-WAV tests. |
| **ST-05 — Model intake** | Verify Train CNN/RF packages, class mappings, preprocessing/feature schemas and safe loading; real inference parity research, with unavailable capabilities blocked. Fresh-process tests. |
| **ST-06 — Detect Workers and logs** | Own Run state, nonblocking background work, cancel/crash/restart recovery, bounded privacy-safe JSONL diagnostics and safe output staging. Process/Qt tests. |
| **ST-07 — CNN detection** | Compatible CNN sliding-window inference, validated thresholds/aggregation, source-time intervals and immutable result publication. Actual WAV and numerical parity tests. |
| **ST-08 — Results UX** | Native recordings/interval exploration, Run history, failure/empty results, provenance and navigation. Qt/a11y/native screenshot tests. |
| **ST-09 — RF refinement** | Optional RF assessment of existing CNN intervals; a new metadata result linked to its parent (accepted/rejected/unscored); preserve original artifact. Schema/science tests. |
| **ST-10 — Corpus export** | Frozen result selection; WAV snippets, concatenated WAV + Raven TSV, or both; explicit destination, origin-to-export mapping, atomic output and collision rules. Real audio tests. |
| **ST-11 — Cross-workflow qualification** | Unified Train/Detect regressions, visual parity, native platform test inventory; revise existing macOS/Windows release specs for Studio without claiming installers are built. |

**Every implementation stage:** use indexed cases (`UT-STU-*`/`IT-STU-*` for Studio; `UT-DET-*`/`IT-DET-*` for Detect; keep Train cases), real `TD-*` fixture classes where needed, targeted tests and impacted regressions during implementation, and the full feasible ordinary suite before commit (excluding explicit soak/installer-only cases). Add each new case to existing test indexes only when its stage begins. Verify input immutability, safe failure/cancel and native screenshots for GUI stages. A skipped/unavailable test does not pass. The 10-minute soak and actual installer production need explicit qualification runs.

**Release:** `docs/specs/06-macos-release-and-installer.md`, `07-windows-release-and-installer.md` and `docs/RELEASE_PROCESS.md` remain unexecuted release requirements. ST-11 updates their product-wide scope before any installation/release work.
