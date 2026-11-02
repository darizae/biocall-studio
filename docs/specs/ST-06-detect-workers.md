# ST-06 — Detect Run lifecycle, Workers and privacy-safe logging

**Historical branch:** `detect-st06-workers`. **Predecessor:** ST-05 verified Model and ST-04 inventory inputs. **Successor:** ST-07. **Status:** implemented and included in the current merged `main` source baseline.

## Scope and ownership

Detect owns its own persisted Run state, local Active Run reservation, Worker process launcher/protocol, cancellation, progress, bounded diagnostics, private staging and safe publication **infrastructure**. Preserve Train's existing Worker/Run lifecycle, settings, logs, CLI and shutdown behavior; do not rebrand or unify Train Run IDs. Share only a verified low-level helper with two actual consumers (e.g. sanitization or atomic directory publication) when justified.

A Scan (ST-04) is not a scientific Run. A Detect Run freezes Collection ID, inventory digest, selected recording keys, Model digest and explicit settings; process arguments are bounded and contain no uncontrolled paths. Support `preparing`, `running`, `cancelling`, `cancelled`, `interrupted`, `failed`, `completed` (and truthful per-file error summary in ST-07); persist terminal state only after receipt and artifact verification. Design Worker protocol for progress, errors and receipt before implementing CNN, using a minimal non-scientific process fixture **only for lifecycle tests**; never publish simulated scientific Results.

## Contract and failure policy

`DetectRunRequest` (versioned, immutable) + `DetectRunRecord` (mutable lifecycle) + `PublicationReceipt` (validated staging digest/identity). Specify launch ID, process identity, lease/reservation ownership and recovery decision on restart. Actual Worker must be QProcess, not a GUI-thread blocking Python loop. One local Detect Active Run unless measured requirements dictate otherwise; coexistence/exit arbitration with Train is explicitly reserved for ST-11, except safe non-regression of current Train behavior.

On cancellation or process death: bound termination/kill, no surviving detached writer/false success, reconcile staged receipts conservatively and never promote incomplete output. Success requires a complete atomically visible immutable artifact; if a Worker commits before crash, verify receipt/identity before retaining it. Log JSONL with allowlisted fields and stable correlation IDs, bounded size/rotation and stderr capture. Strip source filenames, roots, home/UNC/drive paths, credentials and arbitrary exception text; no diagnostics exports silently include raw paths. Prevent metadata and log symlink escapes. Preserve OS/application quit safety without designing cross-workspace behavior prematurely.

## Native parity

`#detect/run` owns real progress/cancel/status and a persistent Detect Run header (not a Train Run header). Empty/preparing/running/cancelling/cancelled/interrupted/failed states are distinct. Action labels and error guidance must be understandable to researchers; provide an accessible Open log/diagnostics route only for an existing, safe file. No decorative captions/status clutter or fake metrics.

## TDD and boundary verification

- `UT-DET-010` — state machine, Run input freeze, one-Active-Run reservation and terminal transitions.
- `UT-DET-011` — cancellation, crash, receipt/staging reconciliation and orphan recovery decisions.
- `UT-DET-012` — bounded diagnostics schema, privacy allowlist, rotation/read/symlink policy.
- `IT-DET-009` — real short QProcess worker, progress, bounded cancellation, forced loss and restart; no success without verified receipt (`TD-RUN`, `TD-FAIL`).
- `IT-DET-010` — genuine Qt event-loop responsiveness, Run header, keyboard cancel and large stderr/log privacy checks (`TD-UI`, `TD-RUN`, `TD-PATH`).
- `IT-DET-011` — actual staging/publication failure, permissions/collision, source reservation and reconciliation of valid versus incomplete output (`TD-FAIL`, `TD-RUN`).

Tests first; use a non-scientific worker only to prove this stage's mechanics. Do not run an end-to-end CNN or whole-Studio regression here. Add impacted Train Worker tests as ordinary regressions, then full feasible ordinary suites before commit; 600-second soak separately initiated.

## Gate

Real QProcess lifecycle/recovery, safe published-identity checks, bounded sanitized logs, native cancellation and existing Train non-regression reviewed. Only then local branch integration to `detect` and ST-07. No push.
