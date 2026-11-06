# RV-08 whole-Studio qualification record

Date: 2026-11-06. Branch: `review-rv08-qualification`, based on reviewed local `review` at
`570adc72e4b6dd6918cce3b6640d3535a3b26c0e`. No merge, push, tag, package or release was
performed.

## Outcome

The feasible source-app automation passes. The existing ST-11-owned end-to-end cases now cover a
genuine current Train Dataset/CNN/RF Model → Detect CNN/RF Result → Review → Review-owned export
chain in place. The final owner sign-off remains **blocked**, not failed, on visible native
Review/audio/accessibility review, a representative consented field-call cohort and the two absent
root UX parity documents. Installed macOS and Windows qualification remains deferred.

The ≥600-second soak was not initiated. At the owner's request, long tests were not repeatedly
run. One broad ordinary suite was stopped after six minutes while an unrelated Train RF test was
still active; it is recorded as incomplete and is not counted as a pass.

## Executed source-app matrix

| Cases | Status | Evidence |
|---|---|---|
| `UT-REVW-001`…`012`, `UT-SIZE-001`…`003` and affected Studio policy units | pass | One grouped background unit run covered Review intake, sessions, exact STFT/context, cache/preflight, view/shortcuts, export v2/4-GiB guard and shared storage decisions. |
| `IT-REVW-001`, `003`…`007`, `010` | pass | One grouped background Review integration run covered real WAV/SQLite/Qt/multimedia/cache/Worker/export boundaries, all three export formats and history recovery. |
| `IT-REVW-002`, `008`, `009` | pass | One isolated 50,000-candidate batch passed in 2 minutes 4 seconds: transactional restart/ownership, paged Qt models/event-loop bounds and streamed real-WAV combined publication/reopen with the asserted `<512 MiB` traced-memory ceiling. |
| `IT-STU-007`, `IT-DET-022` | pass | One 16-second focused run built a real Dataset and current CPU CNN/RF Models through QProcess, published CNN/RF Results, checked independent CNN/RF numeric parity, admitted CNN-all/RF-accepted-only Review choices, generated detail plus all thumbnails, saved mixed labels, exercised Accept all/undo and the partial warning, finalized, wrote Both output, reopened its receipt, restarted/relinked and verified unchanged WAV/Result/finalization bytes. |
| `IT-STU-008` | pass | One 11-second focused run retained an Open Review session while a real Detect QProcess was hidden, kept work open once, recovered a crashed Worker, then used one combined Save-and-Exit path, durably closed Review and left no Worker. |
| RV-07 exit/navigation and retained Detect v1 export regressions | pass | Focused `IT-REVW-011`/`012` and Detect export integration run passed, including failed stop/save paths, restart ownership and historical receipt reading. |
| Full ordinary background suite | incomplete | Intentionally interrupted after six minutes to honor the requested test-time limit; no pass is claimed. Focused owning and affected cases above completed independently. |
| ≥600-second soak | skipped | Separately initiated only; not requested and deliberately omitted under the long-test constraint. |

## Commands

```text
dx test .venv/bin/python scripts/run_tests.py background \
  tests/integration/test_studio_qualification.py::test_cross_workspace_admission_crash_recovery_and_one_safe_exit_dialog -q
PASS

dx test .venv/bin/python scripts/run_tests.py background \
  tests/integration/test_studio_qualification.py::test_genuine_studio_train_detect_rf_export_restart_relink_round_trip -q
PASS

dx test .venv/bin/python scripts/run_tests.py background \
  tests/unit/test_review_cache.py tests/unit/test_review_export.py \
  tests/unit/test_review_intake.py tests/unit/test_review_sessions.py \
  tests/unit/test_review_spectrograms.py tests/unit/test_review_view_state.py \
  tests/unit/test_storage_estimates.py tests/unit/test_studio_operations.py -q
PASS

dx test .venv/bin/python scripts/run_tests.py background \
  tests/integration/test_review_sessions.py::test_sqlite_annotations_restart_scale_close_resume_and_process_loss \
  tests/integration/test_review_workspace.py::test_50k_native_models_page_without_eager_widgets_and_keep_event_loop_responsive \
  tests/integration/test_review_export.py::test_fifty_thousand_row_streamed_combined_publication -q
PASS

dx test .venv/bin/python scripts/run_tests.py background tests/integration/test_review_*.py \
  -k 'not sqlite_annotations_restart_scale_close_resume_and_process_loss and not 50k_native_models_page_without_eager_widgets_and_keep_event_loop_responsive and not fifty_thousand_row_streamed_combined_publication' -q
PASS

dx test .venv/bin/python scripts/run_tests.py background \
  tests/integration/test_studio_shell.py::test_open_review_survives_navigation_and_one_exit_policy_fails_closed \
  tests/integration/test_studio_shell.py::test_restart_recovers_the_same_open_review_session_after_owner_loss \
  tests/integration/test_studio_shell.py::test_detect_new_export_entry_is_gone_while_history_reader_and_review_export_remain \
  tests/integration/test_detect_export.py -q
PASS

dx lint .venv/bin/python -m ruff check .
PASS

dx check .venv/bin/python scripts/audit_test_ids.py
PASS

dx check .venv/bin/python scripts/check_fixtures.py
PASS

dx check .venv/bin/python scripts/verify_handoff.py
PASS

git diff --check
PASS
```

## Scientific, scale and ownership conclusions

- Review accepts completed Detect Results only. The genuine chain asserts all CNN candidates and
  only RF-accepted candidates are offered; original and derived Result bytes remain unchanged.
- The existing stage-owned cases cover exactly three persistent labels, individual/bulk/model-only
  provenance, atomic undo, close/resume, one Open session, frozen finalization and independent
  successor behavior. The RV-08 chain adds mixed native actions and partial finalization without a
  duplicate E2E ID.
- Detail spectrograms are generated on demand and Generate all creates thumbnails. Existing
  scientific cases cover frame clamping, the independent symmetric-Hann/R-reference values,
  phase-opposed stereo channel-power, Balanced 2,000/2,048/1,000 at 48 kHz, data-only images,
  metadata axes, cache containment, quota/eviction/clear/regeneration, stale epochs and REV-05
  admission. Labels, Result bytes and sources remain independent of cache changes.
- The scale batch uses 50,000 distinct candidate IDs and real generated WAV boundaries. Review v2
  streams rows, receipts and Raven data without the former 10,000-row ceiling; invalid RIFF payload
  sizes above the supported 4-GiB boundary fail before publication. Historical Detect v1 readers
  remain covered and no current Detect writer route is exposed.
- The source-app tests use current public `alp-ui`; no upstream UI or toolbox change was required.

## Environment and dependency provenance

- macOS 26.6.2 arm64; Python 3.12.7; PySide6/Qt 6.11.2.
- `alp-ui` 0.1.0a0 imports from the installed `.venv` package. Its source checkout is
  `8cdc91f56005fcd0f3c4004b66016b3d237a10c3`, matching `pyproject.toml`.
- `bioacoustics-dl-toolbox` 0.2.0 imports from the sibling editable source checkout at
  `22c1b342918b33c62288f23b660aa716f3e361e6`, matching `pyproject.toml`. This is valid source-app
  evidence, not independent packaged-wheel evidence.
- The registered synthetic WAV LFS objects were present; `git lfs fsck` passed.

## Blocked and deferred evidence

- **Blocked — visible native Review qualification:** ordinary tests used the required invisible
  offscreen mode. No visible Cocoa run was authorized, so physical playback, real device failure,
  hover/focus inspection, assistive technology, 100–200% display scale and owner review of current
  normal/compact Review copy are not claimed. The RV-05 captures remain explicitly background
  evidence.
- **Blocked — representative science/calibration:** no consented natural field-call cohort is
  bundled. Generated WAVs prove numerical and source-boundary behavior, not field readability or
  production cache time/byte calibration.
- **Blocked — complete historical UX parity:** `docs/design/UX_PARITY_MATRIX.md` and
  `docs/design/PROTOTYPE_ACCEPTANCE.md` are still absent. Existing prototype evidence is retained,
  but its browser harness source is not part of this checkout and was not rerun as native evidence.
- **Deferred — installed platforms/releases:** no `.app`, DMG, signing, notarization,
  clean-machine macOS install or native Windows run was authorized. Installer/release gates are
  unchanged.

## Manual owner trial

An ignored, disposable pack is prepared at `work/manual-review`. It contains fresh current-contract
Train Models, two verified Detect Results, three immutable source WAVs and isolated application
data. Launch with:

```text
.venv/bin/python -m biocall_studio --settings-dir work/manual-review/app-data
```

The pack's README gives the Review labels/spectrogram/finalize/export/exit walkthrough. Its source
checksum verification passes. It is local manual evidence material, not a tracked test fixture or
field-data claim.

## Additive owner-raised correction gate — 2026-11-06

After the tests above, the owner inspected the actual Review UI and **did not approve its appearance**. Source review identified a missing persistent prototype sidebar, a mismatched Open Review button/header, non-parity Gallery/One-by-one presentation, synchronous detail WAV/FFT on the Qt path, no empty-cache Gallery generation wiring, repeated source hashing, uncalibrated cache preflight and potential fixed-quota eviction churn. The owner additionally requires **Delete session** (including safe finalized/successor/export handling) and an **in-application Review data-folder picker/migration**. These were not qualified by the historical tests.

The corrective route is [RV-09](specs/review/RV-09-native-visual-parity-and-data-management.md) then [RV-10](specs/review/RV-10-spectrogram-interactivity-and-qualification.md). The [committed prototype target PNGs and native-before captures](design/evidence/review-correction/README.md) must be paired with **real visible native-after screenshots** and explicit owner visual approval; offscreen captures are insufficient. Reusable generic UI primitives are to be committed independently in `alp-ui`, then the latest approved local revision reinstalled/verified in Studio before use. **No new tests or visible app screenshots have been executed for this docs-only corrective handoff.** Owner forbids long test runs during these corrections; only short targeted commands up to 120 seconds each are authorized without further agreement. Prior evidence remains historically accurate, but RV-08 sign-off and merge into `main` stay **blocked**.
