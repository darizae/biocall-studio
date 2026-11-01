# ST-10 native frozen corpus export evidence

Captured on macOS 26.6.2 with the Cocoa Qt platform, Python 3.12.7,
PySide6/Qt 6.11.2, `alp-ui` 0.1.0a0 and the project `.venv`. The installed
public `alp-ui` import resolved to `../alp-ui` at
`5bb61e3a4c4bd7104ade4375cc32082ea44e1d14`. Images are genuine Retina native
captures from a real Train-produced CNN Model, real PCM WAV recordings, a real
completed Detection Result and a verified ST-10 publication. They are not browser
or mocked prototype output.

## Scientific and Raven convention

Source intervals are exact half-open original-recording frames already clipped by
the immutable Result: `[start_frame, end_frame)`. Export rejects any inconsistent,
zero-length or out-of-range mapping; it does not clip a second time. Snippet WAVs
retain source sample rate, channels, sample width and PCM bytes. Concatenation is
gap-free and accepts only identical uncompressed PCM formats; the current Raven
path is mono-only. No path resamples, downmixes or changes sample dtype.

`corpus.Table.1.selections.txt` follows Cornell Raven's documented default column
order (`Selection`, `View`, `Channel`, `Begin Time (s)`, `End Time (s)`,
`Low Freq (Hz)`, `High Freq (Hz)`) before appending candidate/source-frame
provenance. Begin/end seconds are derived independently from integer concatenated
frame offsets with an exact round-trip, never by accumulating float durations.
The table convention was checked against Cornell's
[selection-table guidance](https://www.ravensoundsoftware.com/knowledge-base/error-opening-selection-table/);
Raven itself was not installed or claimed as an executed compatibility test.

Every successful output contains `export-snapshot.json`, payload WAV/TSV files and
`export-receipt.json`. The receipt self-digest, sorted payload file SHA-256/size
index, snippet PCM digests, original source frames/times, concatenation frames and
Raven rows are reopened and verified without rewriting the publication.

## Native views

- `export-ready-normal.png`: frozen count, Result identity, format policy, review
  summary and enabled export action at normal width.
- `export-ready-actions-normal.png`: explicit persistent destination and planned
  original-frame/output-frame mapping.
- `export-ready-compact.png`: the same genuine destination, format and mapping in
  the single-column compact layout with no horizontal scrolling.
- `export-success-normal.png`: verified final destination with the genuine
  **Show in folder** action visible after atomic publication.

The absolute paths visible in screenshots are pytest-style temporary evidence
folders. Immutable provenance stores portable source keys and content checksums;
the destination is deliberately explicit because exported audio may be sensitive.

## Executed checks

```text
python -m pytest tests/unit/test_detect_export.py -q
3 passed

python -m pytest tests/integration/test_detect_export.py -q
4 passed

python -m pytest tests/unit -q
99 passed

python -m pytest tests/integration -q
102 passed, 1 soak test deselected

python -m ruff check .
passed

python scripts/audit_test_ids.py
passed
```

`IT-DET-019` compares real mono and stereo snippet PCM, headers, checksums and
half-open frame slices. `IT-DET-020` verifies both-mode snippets, a gap-free
concatenated WAV, Raven rows and complete receipt reopen. `IT-DET-021` covers real
source staleness, destination permissions/collision, injected disk-full failure,
cooperative cancellation, staging cleanup, source non-mutation, compact native
controls and Show in folder. The complete Train→Detect→RF→Export workflow and
combined safe-quit qualification remain ST-11-owned. The separately initiated
≥600-second soak was not run as part of this stage commit.
