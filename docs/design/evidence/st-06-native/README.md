# ST-06 Detect Run native evidence

## Native capture

These seven PNGs are genuine visible-window captures from the source application on the native
macOS Cocoa Qt platform. They were captured on 2026-10-28 with macOS 26.6.2, Python 3.12.7,
PySide6/Qt 6.11.2, `alp-ui` 0.1.0a0 from sibling revision
`5bb61e3a4c4bd7104ade4375cc32082ea44e1d14`, and the Alpaca Light theme.

```bash
.venv/bin/python scripts/capture_st06_screenshots.py
```

The capture command creates two real WAV sources, publishes a genuine ST-04 inventory, and drives
the real QProcess supervisor with the ST-06 non-scientific lifecycle fixture. The fixture produces
only a checksum-verified artifact marked `scientific_result: false`; it does not load a Model,
score audio, create candidates, or publish a Detect Result.

| File | Observed state |
|---|---|
| `run-idle-normal.png` | Reachable `#detect/run` empty state and persistent Detect Run header. |
| `run-running-normal.png` | Real supervised QProcess, progress, activity, cancellation, and safe log action. |
| `run-cancelling-normal.png` | Distinct persisted cancelling state while the stubborn fixture remains alive. |
| `run-cancelled-compact.png` | Bounded termination completed without publication at 700×780. |
| `run-failed-normal.png` | Controlled nonzero Worker failure with actionable, path-free guidance. |
| `run-interrupted-normal.png` | Actual crashing Worker reported as interrupted, never completed. |
| `run-completed-compact.png` | Receipt and immutable artifact verified before 100% completion at 700×780. |

Visual review confirmed the accepted ST-01 `#detect/run` hierarchy, persistent Detect-owned Run
header, distinct states, researcher-readable status/guidance, keyboard-accessible cancellation,
existing-log gating, normal/compact reflow without horizontal scrolling, and no fabricated
scientific metric or Result action. Automated native Qt coverage additionally observes the short
`preparing` state, Space-key cancellation, event-loop responsiveness during a large stderr storm,
privacy normalization, and missing-log gating.

## Validation ledger

Validation was completed on the native environment above from `detect-st06-workers` on
2026-10-28. The final code and tests produced:

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest -q tests/unit/test_detect_runs.py tests/unit/test_detect_diagnostics.py tests/integration/test_detect_runs.py` | 8 passed in 3.21 s. |
| `.venv/bin/python -m pytest -q` | Pass: all 177 ordinary selected tests; 1 soak test deselected by the repository configuration. One pre-existing Torch `TypedStorage` warning remains. |
| `.venv/bin/python -m ruff check .` | Pass. |
| `.venv/bin/python scripts/audit_test_ids.py` | 114 referenced case IDs; 0 unknown. |
| `.venv/bin/python scripts/check_fixtures.py` | 6 real WAV fixtures verified by hash, header, and source-time excerpt identity. |
| `git diff --check` and `git lfs fsck` | Pass; all 6 WAV fixtures remain valid LFS objects. |
| `.venv/bin/python scripts/verify_handoff.py` | Blocked by 43 pre-existing legacy handoff errors: absent historical SPEC-01–05 files/prototype assets and their already-broken links. No error identifies an ST-06 file. The routing instructions prohibit reconstructing those legacy files. |

The first repository-wide run exposed one non-reproducing inventory timeout and an assertion that
observed the coordinator before its deferred final Qt close. Both cases passed together after the
close assertion was synchronized with the final event-loop turn; the complete ordinary suite then
passed. No test failure was waived.

## Qualification boundary

`IT-DET-009`–`011` use actual QProcess, filesystem, Qt event-loop, permissions and atomic rename
boundaries. They cover cooperative and forced cancellation, process kill/crash, restart,
commit-before-crash receipt recovery, missing receipt/artifact non-success, collision, unwritable
publication storage, incomplete staging cleanup, one-Run/source reservation, symlink-safe log
access, bounded rotation/stderr and unchanged source WAV bytes. The ordinary Train/Studio
regressions remain separate and preserve Train's Worker behavior.

Windows-native, installed-app, CNN/scientific Result, cross-workflow arbitration and the explicitly
initiated 600-second soak are not claimed here.
