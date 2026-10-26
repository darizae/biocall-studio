# Implementation sequence — native Trainer

This roadmap describes **phase order**, not the current Git state. Use [agent routing](agent/ROUTING.md) to choose one active spec based on actual acceptance evidence. Work in a reviewed branch and finish tests, documentation and a real commit before the next phase.

| Phase | Acceptance outcome | Owned tests |
|---|---|---|
| [01 — Native shell](specs/01-shell-and-test-foundation.md) | `alp-ui` Select Collection, navigation, Wiki, Settings, native evidence; [closeout](specs/SPEC_01_CLOSEOUT.md) only if still deficient | `UT-PATH-*`, `IT-UI-*` |
| [02 — Scan](specs/02-collection-scan-and-metadata.md) | Real WAV and filename validation, actionable errors, rebuildable metadata/cache | `UT-COL-*`, `IT-COL-*` |
| [03 — Dataset](specs/03-dataset-build.md) | Protected `target`/`noise` extraction, source-grouped splits, immutable Dataset | `UT-DB-*`, `IT-DB-*` |
| [04 — Worker](specs/04-runs-and-worker.md) | Real supervised QProcess lifecycle, one Active Run, cancellation/recovery | `UT-RUN-*`, `IT-RUN-*` |
| [04.5 — Upstream audio](specs/SPEC_04_5_UPSTREAM_AUDIO_EXTRACTION.md) | Move reusable extraction into toolbox, preserve bytewise Dataset compatibility; two-repo test/commit | `UT-AUDIO-*`, `IT-AUDIO-*` |
| [05a — Configuration/presets](specs/05a-training-configuration-and-presets.md) | Native small-form + detailed typed controls, validation and reusable saved presets; no fabricated training | `UT-TRAIN-007`–`010`, `IT-TRAIN-010`/`011`/`013` |
| [05b — CNN + Model foundation](specs/05b-cnn-training-and-model-foundation.md) | Real binary CPU CNN through Worker, immutable common Model format + trusted CNN structural reload | `UT-TRAIN-001`/`004`/`005`, `IT-TRAIN-001`; shared family IDs remain open |
| [05c — RF + joint acceptance](specs/05c-rf-training-and-cross-family-acceptance.md) | Genuine RF features/fit, exported RF and CNN/RF plots, two-family Model reload and end-to-end preset tests; **no inference** | `UT-TRAIN-002`/`003`/`006`, `IT-TRAIN-002`–`009`/`012`/`014`; recheck all Spec 05 IDs |
| [05d — Logging + diagnostics](specs/05d-end-to-end-logging-and-diagnostics.md) | Privacy-safe bounded app/Worker JSONL, incremental stderr draining, contained native access and sanitized support export | `UT-LOG-*`, `IT-LOG-*`; recheck affected Run/Build/Training IDs |
| [05e — Critical recovery verification](specs/05e-training-critical-path-and-recovery-verification.md) | Close focused training, publication and failure-recovery coverage gaps without changing scientific behavior | affected `IT-TRAIN-*`, `IT-RUN-*` |
| [05f — UI/chart/scale/CLI closeout](specs/05f-ui-chart-scale-and-cli-coverage.md) | Complete native control, exact Plot binding, large-Collection responsiveness and CLI ownership coverage | affected `UT-CLI-*`, `IT-UI-*`, `IT-COL-*`, `IT-TRAIN-*` |
| [05g — Long-running + safe exit](specs/05g-long-running-sessions-and-safe-exit.md) | Safe confirmed shutdown and owner-loss containment; explicit 10-minute real-Worker durability; truthful optional idle-sleep prevention | `UT-POWER-*`, `IT-POWER-*`, `IT-RUN-006`–`009` |
| [06 — macOS](specs/06-macos-release-and-installer.md) | Reproducible signed/notarized installable `.dmg`, installed native/scientific validation | `IT-MAC-*`, `IT-E2E-*` |
| [07 — Windows](specs/07-windows-release-and-installer.md) | Native Windows qualification and versioned `.exe` installer | `IT-WIN-*` |

**Applies to each phase:** TDD at the owning seam; native UX evidence if visible UI changes; generated real WAVs or approved local fixtures (never live HPC); versioned validated publication and non-mutation; accurate test results and blockers; reviewed Git commit with clean tree. The authoritative procedures are [integration testing](INTEGRATION_TESTING.md), [prototype acceptance](design/PROTOTYPE_ACCEPTANCE.md), and [Git delivery](agent/GIT_DELIVERY.md). Do not declare a case implemented from its listing here.
