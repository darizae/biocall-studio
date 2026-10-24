# 04 — Scientific Runs and supervised Worker Process

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

## Tests / exit

- Unit: `UT-RUN-001`, `UT-RUN-002` with deterministic transition/reservation examples (`TD-RUN`).
- Integration: `IT-RUN-001`…`IT-RUN-004` actual QProcess, real minimal Dataset Build, cancel/kill, conflict, restart recovery, collisions, non-mutation (`TD-RUN`, `TD-FAIL`). Validate both persisted terminal state and real published bytes and input immutability. Native packaged Worker success is part of spec 06; don't claim it from development launch.
