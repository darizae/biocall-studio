# ST-08 native Result exploration evidence

## Native capture

These seven PNGs are genuine visible-window captures from the source application on the native
macOS Cocoa Qt platform. They were captured on 2026-10-29 with macOS 26.6.2, Python 3.12.7,
PySide6/Qt 6.11.2, `alp-ui` 0.1.0a0 from sibling revision
`5bb61e3a4c4bd7104ade4375cc32082ea44e1d14`, and the Alpaca Light theme.

```bash
.venv/bin/python scripts/capture_st08_screenshots.py
```

The capture builds a real WAV-backed Train Dataset, trains and accepts a genuine one-epoch CNN,
publishes one populated partial ST-07 Result and one complete zero-candidate ST-07 Result through
the production QProcess boundary, then drives the native ST-08 controls. The corrupted state is
created only in the temporary evidence workspace after the valid states have been captured. The
script proves that selecting a candidate does not change the selected Result bytes.

| File | Observed state |
|---|---|
| `results-history-partial-normal.png` | Persistent Run header, original Result history, partial-file alert and immutable lineage at 1180×790. |
| `results-candidates-selected-normal.png` | Recording navigation, one checked stable candidate ID, source time, exact half-open frames, score and selection revision. |
| `results-candidates-selected-compact.png` | The recording and candidate cards stacked at 700×780 without page-level horizontal overflow. |
| `results-stale-normal.png` | An older Result remains readable after a later inventory revision; source navigation is disabled. |
| `results-empty-normal.png` | A genuine complete zero-candidate Result retains recording outcomes and provenance. |
| `results-source-unavailable-compact.png` | The source folder is missing, but candidate metadata and Result history remain readable. |
| `results-corrupt-normal.png` | A changed Result fails verification and is shown as unavailable, never as zero candidates or success. |

Visual review against the approved `#detect/results` prototype confirmed the same information
order: persistent Run context and route return, Result history, state alert, lineage/provenance,
recording list, recording-scoped interval table and selected-interval detail. Native tables use the
public `alp-ui.DataTable`; the candidate model exposes only 200 rows initially and pages further
metadata without decoding a recording. The native surface deliberately omits the prototype's RF
action card and export action because ST-09 and ST-10 own those behaviors. A disabled
`Refined Result · not created` history entry preserves the planned lineage location without adding
a dead action.

## Frozen selection handoff

Checkbox state is a separate atomic document below the app-owned Detect Collection's
`result-selections/` directory. `ResultSelection` schema version 1 contains only the Result ID and
digest, a monotonically increasing selection revision, stable candidate IDs and a UTC update time.
It never rewrites `result.json`. A digest change clears the selection visibly; IDs absent from the
same Result are removed visibly; corrupt selection metadata is reported instead of being treated as
an empty user choice.

`FrozenResultSelection` schema version 1 is the explicit successor handoff:

```text
schema_version, result_id, result_digest, selection_revision, candidate_ids
```

The controller returns this immutable value only when a successor explicitly asks to freeze the
currently selected original Result. ST-09 must retain the original Result ID/digest as parent
lineage when refinement begins. ST-10 must call the freeze boundary when export begins; ordinary
checkbox edits and route navigation do not create or mutate an export snapshot.

## Validation ledger

Validation was performed from `detect-st08-results-ux` on the native environment above.

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest -q tests/unit/test_detect_result_views.py tests/integration/test_detect_detection.py -k 'result_projection_selection or result_status_and_provenance or result_history_recording or large_candidate or result_empty_partial'` | 5 passed, 4 deselected in 14.36 s; one upstream Torch deprecation warning. |
| `.venv/bin/python -m pytest -q tests/unit/test_detect_detection.py tests/integration/test_detect_detection.py` | 10 affected ST-07/ST-08 tests passed in 32.58 s; the same upstream warning. |
| `.venv/bin/python -m pytest -q` | 189 ordinary tests passed; 1 explicitly initiated soak test deselected; one upstream warning; 172.00 s. |
| `.venv/bin/python -m ruff check .` | Pass. |
| `.venv/bin/python scripts/audit_test_ids.py` | 124 referenced case IDs; 0 unknown. |
| `.venv/bin/python scripts/check_fixtures.py` | 6 real WAV fixtures verified by hash, header and source-time excerpt identity. |
| `.venv/bin/python scripts/capture_st08_screenshots.py` | Pass on Cocoa; seven PNGs visually reviewed. |
| `.venv/bin/python scripts/verify_handoff.py` | Blocked by the same 43 pre-existing legacy handoff errors recorded by ST-06/ST-07: absent historical SPEC-01–05/prototype assets and already-broken links. No error identifies an ST-08 file, and routing prohibits reconstructing those files. |

The first full run had 188 passes and one failure in the ST-02 shell regression because it still
expected only the two setup combo boxes. ST-08 intentionally adds the disabled Result-history
combo; the regression now asserts all three controls and its accessible disabled initial state. Its
focused rerun and the complete 189-test rerun passed. No failure was waived.

## Qualification boundary

ST-08 reads existing Result metadata and source freshness facts only. It does not decode audio,
change candidate scores or intervals, run RF inference, materialize export audio, or modify Train.
The native evidence qualifies the local macOS source UI. Windows-native, installed-app, ST-09 RF,
ST-10 export, complete Studio end-to-end integration and the separately initiated 600-second soak
remain outside this stage.
