# ST-07 CNN detection native evidence

## Native capture

These five PNGs are genuine visible-window captures from the source application on the native
macOS Cocoa Qt platform. They were captured on 2026-10-29 with macOS 26.6.2, Python 3.12.7,
PySide6/Qt 6.11.2, `alp-ui` 0.1.0a0 from sibling revision
`5bb61e3a4c4bd7104ade4375cc32082ea44e1d14`, and the Alpaca Light theme.

```bash
.venv/bin/python scripts/capture_st07_screenshots.py
```

The command creates deterministic real WAVs, builds a genuine Train dataset, trains and publishes
a real one-epoch CNN Model, accepts the Model and ST-04 inventory through production boundaries,
then runs the separate scientific CNN QProcess Worker. The completion state deliberately combines
four successful zero-candidate recordings with one decoder failure; it is a verified partial
metadata-only Result, not fabricated UI data.

| File | Observed state |
|---|---|
| `setup-overview-normal.png` | Accepted CNN Model and read-only recordings source at 1180×790. |
| `setup-settings-normal.png` | Score, overlap, merge-gap HelpHints and functional Start action in the normal three-column layout. |
| `setup-settings-compact.png` | The same controls stacked at 700×780 without horizontal clipping. |
| `run-cnn-running-normal.png` | Real scientific Worker progress, activity, cancellation and log actions. |
| `run-result-partial-compact.png` | Verified 100% completion stating zero candidates and one separately failed recording. |

Visual review confirmed the accepted Detect route hierarchy, researcher-facing score language,
keyboard-accessible public `HelpHint` controls, enabled Start action, real Worker progress and
completion, visible partial-file qualification, and normal/compact reflow. The capture review found
and fixed a width-cache defect that had clipped HelpHints at compact width; native Qt coverage now
asserts zero horizontal overflow after a normal-to-compact reflow.

## Validation ledger

Validation was performed from `detect-st07-cnn-detection` on the native environment above.

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest -q tests/unit/test_detect_detection.py tests/integration/test_detect_detection.py` | 7 passed in 20.45 s; one upstream Torch deprecation warning. |
| `.venv/bin/python -m pytest -q ../bioacoustics-dl-toolbox/tests/test_predictor.py` | 46 passed in 1.48 s at the pinned upstream source revision. |
| `.venv/bin/python -m pytest -q` | Pass: all 184 ordinary selected tests; 1 soak test deselected by repository configuration. Condensed-runner wall time was 146.9 s; the same upstream Torch warning remains. |
| `.venv/bin/python -m ruff check .` | Pass. |
| `.venv/bin/python scripts/audit_test_ids.py` | 120 referenced case IDs; 0 unknown. |
| `.venv/bin/python scripts/check_fixtures.py` | 6 real WAV fixtures verified by hash, header and source-time excerpt identity. |
| `git diff --check` and `git lfs fsck` | Pass; all tracked WAV fixtures remain valid LFS objects. |
| `.venv/bin/python scripts/capture_st07_screenshots.py` | Pass on Cocoa; five PNGs visually reviewed. |
| `.venv/bin/python scripts/verify_handoff.py` | Blocked by the same 43 pre-existing legacy handoff errors recorded by ST-06: absent historical SPEC-01–05/prototype assets and their already-broken links. No error identifies an ST-07 file, and routing prohibits reconstructing those legacy files. |

`IT-DET-012` compares downstream window scores to the verified upstream public reference with an
absolute tolerance of `1e-7` on a genuine stereo 8 kHz WAV, while also checking class order and
every half-open interval. `IT-DET-013` runs the real QProcess, independently reopens all checksums,
distinguishes zero candidates from decoder failure and proves source-byte non-mutation.
`IT-DET-014` covers replaced WAV/Model bytes, cancellation, process kill, destination collision,
invalid pre-existing receipt and staging cleanup. Upstream predictor tests at the pinned revision
cover rejected output shape and non-finite logits; accepted ST-05 Models structurally freeze two
binary outputs before a Run.

## Qualification boundary

The stage uses CPU inference and native macOS Qt. Windows-native, installed-app, large-collection
performance, ST-08 exploration, ST-09 refinement, ST-10 export, complete Studio end-to-end
integration and the explicitly initiated 600-second soak remain deferred to their owning gates.
