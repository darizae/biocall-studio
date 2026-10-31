# ST-11 — Whole-Studio qualification and release-spec revision

**Branch:** `detect-st11-qualification` from reviewed `detect`. **Predecessors:** approved ST-03…ST-10 and REV-01…REV-03. **Status:** planned; packaging, signing and public release remain separate unexecuted work.

## Scope and ownership

This is the **only stage owning full Studio/Train/Detect scientific end-to-end tests**, cross-workspace Run/quit arbitration, final native UX parity review and qualification evidence. It owns coordinated regression and documentation updates; it does **not** opportunistically redesign Train, reimplement Detect science, create a Review workspace, produce installers or declare unavailable platforms passed.

Revise, **in place**, the existing [macOS installer spec](06-macos-release-and-installer.md), [Windows installer spec](07-windows-release-and-installer.md) and [release process](../RELEASE_PROCESS.md) to apply to BioCall Studio, including both workflows, tested bundled Workers, per-user metadata paths, current brand/icons, immutable outputs, clean install/uninstall and signed/native packaging requirements. Preserve existing `IT-MAC-*`, `IT-WIN-*`, `IT-E2E-*` IDs; do not create a competing release-spec series. Record installer-only checks as **deferred** until a separate explicitly approved packaging stage.

## Qualification contracts

One test corpus of deterministic source WAVs and genuine produced Models/Results/Exports drives: native Studio launch→real Train (existing scientific workflow/Model export)→return preserving Train controller→Detect Collection and inclusion→trusted CNN Model→real QProcess CNN Run→original Result→optional real RF child→export WAV+TSV→restart/reopen/relink→clean/confirmed quit. Distinct immutable IDs, digests, timestamps, exact source-to-export mapping and unchanged recording bytes must be asserted. Inject source replacement, missing Model, process crash and cancel at targeted boundaries without falsely claiming full end-to-end success. Repeat native normal/compact layout, focus/a11y/tooltip/copy checks against accepted prototype and native Train; planned Review remains placeholder.

A shared application-exit decision must handle simultaneous or sequential Train/Detect live operations with one visible safe confirmation and bounded supervised stopping, without changed Train semantics or implicit cross-workspace input mutation. If concurrent scientific Runs cannot be supported safely, establish and test an explicit global resource admission rule rather than pretending independence implies safe parallel GPU use.

## TDD and qualification matrix

- `UT-STU-002` — pure cross-workspace quit/admission policy and independent Train/Detect ownership; no duplicate Run IDs, hidden Worker's lifetime not inferred from visibility.
- `IT-STU-007` — **one genuine whole-Studio scenario**: retained Train and trusted Model, Detect Collection/scan/CNN/Results/RF/export, restart/relink/provenance, unchanged originals, native navigation and user-visible success (`TD-UI`, `TD-RUN`, `TD-WAV`, `TD-TRAIN`, `TD-EXPORT`).
- `IT-STU-008` — real Qt/QProcess cross-workspace active operation/exit contention, keep-open/confirm, crash recovery and no orphaned workers without altering Train's existing behavior (`TD-RUN`, `TD-FAIL`, `TD-UI`).
- `IT-DET-022` — end-to-end **scientific round trip** cross-checking source CNN→RF→export frame times, class/feature parity, checksums and TSV rows against reference numeric outputs (`TD-WAV`, `TD-EXPORT`, `TD-TRAIN`).

Re-run every feasible existing ordinary unit/integration case (`UT-*`, `IT-*`), scoped negative cases, `ruff`, `scripts/audit_test_ids.py`, native screenshots and source/checksum audit. Explicit ≥600s soak only when separately initiated. Report each ID **pass / fail / blocked / skipped / deferred-native**, actual commands, OS and installed versions, scientific upstream SHAs, reproducibility, prior artifact immutability and owner-reviewed UX deviations. Do not label an offscreen screenshot Cocoa/Windows evidence; don't claim installers were built/installed/signed/notarized.

## Gate and local integration

Review the complete qualification matrix, scientific numerical reference chain, source-time provenance, Train non-regression, prototype/native parity and revised **existing** release specs. Only after explicit owner sign-off: review branch diff, locally integrate `detect-st11-qualification` → `detect`, then locally merge approved `detect` → `main`, record actual branch/commit/merge SHAs and clean state. **Never push, tag, publish or produce an installer automatically.** If release qualification remains blocked, keep `main` unchanged and report blockers.
