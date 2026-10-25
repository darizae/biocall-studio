# 04 — Scientific Runs and supervised Worker Process

**Scoped references:** [Architecture](../ARCHITECTURE.md) §4; [Run state rules](../models/WORKFLOW_RULES.md) §4; [Run UX row](../design/UX_PARITY_MATRIX.md); indexed `UT-RUN-*` in [unit](../UNIT_TESTING.md), `IT-RUN-*` in [integration](../INTEGRATION_TEST_BEHAVIORS.md).

## User behavior

Dataset Build and Training show dedicated **Run** progress/detail screens and history. The active task is visible from navigation; user can request cancellation. Running a second scientific operation or deleting/rebinding active inputs reports a conflict instead of corrupting data. On restart, interrupted work is reconciled with accurate persisted status.

## Ownership

- Application Controller owns at most **one Active Run**. Only `dataset_build` and `training` are Run kinds. Collection Scan has a separate cancellable I/O activity and never reserves this singleton.
- QProcess starts the installed app's actual Worker entry point from the active Python environment (`sys.executable`/`-m` in development) or bundled executable `--worker` under packaging. No shell interpolation, globally discovered Python or GUI imports in Worker code. Pass versioned request IDs, Collection binding, Dataset ID, config path and isolation settings.
- Worker writes state, stages scientific output on destination filesystem and sends rate-limited structured progress/error. Application owns lifecycle controls, reservations, QProcess supervision/cleanup; Worker owns computation and artifact validation. Persist `created → starting → running → cancelling → terminal` transitions with atomic state replacement.
- Crash and startup reconciliation cross-check `run_state.json`, staged output, file completeness and published artifact manifest. A `completed` flag without valid manifest is failure; an orphaned `running` state becomes `interrupted`. Never silently resume/retry.
- Reserve Collection/Dataset input IDs/paths and prospective output; enforce at persistence/command boundary even if GUI button was disabled. Read-only browsing stays permitted. Stage path is private/invisible. No new output may overwrite a directory with the same ID.

## UI/packaging handoff

Progress display uses `alp-ui` `ProgressBar`/`Badge`/`Alert`/`Button`, with **actual** Worker events, not the prototype timer. QProcess launch must be designed for frozen `.app`/`.exe` `--worker` as well as dev Python, without a global interpreter dependency. Compare Run/active-sidebar prototype states to the native Qt UI.

## Blocking prototype parity (native UI)

**`IT-RUN-005`:** The native Run detail, Active Run/sidebar indicator and Runs history must follow the prototype's visible hierarchy, status labels, stage progress, cancel action, terminal states and navigation, not a text-only log window. Use real `QProcess` status/events (not JS animation); make cancellation/conflict/failure visibly distinct. Write failing `pytest-qt` interaction checks, capture `spec-04-native/` screenshots of active/cancelling/failed/history and check all six [Prototype acceptance](../design/PROTOTYPE_ACCEPTANCE.md) dimensions against the Run prototype states plus current `alp-ui` Showcase. Unapproved gaps block the spec even if process-level tests pass.

## Tests / exit

- Unit: `UT-RUN-001`, `UT-RUN-002` with deterministic transition/reservation examples (`TD-RUN`).
- Integration: `IT-RUN-001`…`IT-RUN-004` actual QProcess, real minimal Dataset Build, cancel/kill, conflict, restart recovery, collisions, non-mutation (`TD-RUN`, `TD-FAIL`). Validate both persisted terminal state and real published bytes and input immutability. Native packaged Worker success is part of spec 06; don't claim it from development launch.

## Implementation closeout — 25 October 2026

**Complete and ready for owner review.** Dataset Build now runs through a persisted, versioned Run
record and supervised QProcess with structured bounded progress, immutable request/completion
receipts, cooperative cancellation plus terminate/kill fallback, one-Run reservations, atomic state
replacement and conservative restart reconciliation. Verified output is the only route to
`completed`; cancel, crash, collision, corrupt output and nonzero exit never promote an output
pointer or overwrite an existing Dataset.

`UT-RUN-001`/`002` and `IT-RUN-001`…`005` are asserting tests, not planned IDs. TDD began with
missing Run-domain and native Run-page imports before the pure rules, persistence, process
supervision and UI were implemented. The existing verified Dataset Build algorithm remains the
scientific owner; the Worker only adds lifecycle/progress/cancellation hooks and Run provenance.

The adjacent `alpaca-pipelines` checkout was verified at
`91af5287dc18313f88902dc9696e8756274736b3`. Its remote/HPC orchestration and schemas were not
adopted: the source map assigns Spec 04 local QProcess ownership to the Trainer. The native UI was
implemented against sibling `alp-ui` `330aaab96a6b32dd2d83ae84a52a2a238446d264`.

Verified commands on native macOS 26.6.2 arm64, Python 3.12.7 and Qt 6.11.2 are recorded in the
[native evidence ledger](../design/evidence/README.md), including the full pytest suite, Ruff,
test-ID/handoff/fixture audits, Git LFS verification and the six-image visible Cocoa capture. Native
packaged Worker success remains Spec 06; Windows QProcess/filesystem qualification remains Spec 07.

```text
.venv/bin/python -m pytest -q                              53 passed
.venv/bin/python -m ruff check src tests scripts           passed
.venv/bin/python -m ruff format --check src tests scripts  passed
.venv/bin/python scripts/audit_test_ids.py                 36 IDs, 0 unknown
.venv/bin/python scripts/check_fixtures.py                 6 WAVs verified
.venv/bin/python scripts/verify_handoff.py --require-native-ux
                                                            0 errors
git lfs fsck                                                OK
unset QT_QPA_PLATFORM; .venv/bin/python -u scripts/capture_spec04_screenshots.py
                                                            6 Cocoa captures reviewed
```
