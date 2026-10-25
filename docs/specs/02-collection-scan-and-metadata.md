# 02 — Collection Scan, source-time validation and metadata

## User behavior

**Select Collection → Reading Collection → Collection overview.** The chosen user folder contains direct `recordings/` and `positives/`. Display counts/durations, Source Recording-to-positive association, progress/cancel, and per-path **fixable** validation messages. The user can correct existing WAVs then rescan; Build Dataset is disabled unless the currently scanned inputs validate. Cache is stored at `Collection/.alpaca/`, not in a copied input tree.

## Contract and handoff

- Read [`../wiki/SELECTING_A_COLLECTION.md`](../wiki/SELECTING_A_COLLECTION.md) and [`../models/WORKFLOW_RULES.md`](../models/WORKFLOW_RULES.md). Parse anchored `<complete-source-stem>__start-<integer>ms__end-<integer>ms__<unique-label>.wav`; uniquely associate stem with Source Recording. Enforce valid WAV, duration agreement with quantization/frame tolerance, safe names, no collisions, `0 ≤ start < end ≤ duration` and no duplicate source interval.
- A scan object passes discovered normalized relative paths, WAV header metadata, derived `target` Annotations, issues, fingerprints and schema version to **one** metadata writer. Positive WAV is a provenance input, not a Dataset Snippet. Source-time labels are trusted for mapping but **not** waveform-verified.
- Run scan in cancellable bounded I/O worker, with read budget: nonrecursive input enumeration and **one header read per WAV** initially; no full decode/copy. Ensure Qt model paging and counts are updated without flooding event loop. Reading is not a scientific Run.
- Publish successful `collection.json`, `records/*.jsonl`, `positives/*.jsonl` using safe same-filesystem staged/atomic update. Partition at ≤10,000 rows or 16 MiB. Freshness on reopen compares complete input inventory and cheap fingerprints; only changed/new WAV headers need rereading. A cache miss/relink must pass the same containment/permissions checks. Before Dataset Build, revalidate selected current inputs.
- Stable Collection ID persists under `.alpaca/`; Application Settings store machine-local absolute folder binding and handle explicit relink after verifying contents/identity. Missing or moved folders do not silently adopt unrelated files.

## Failure acceptance

Report for each failure an exact relative path and correction: missing folder, unexpected nested input, unsupported file/codec, malformed header, bad timestamp grammar/overflow, ambiguous source, invalid bounds, positive duration mismatch, symlink escape, name normalization collision, duplicate interval. Cancel, permission exception or interrupted cache update never leaves a newly validated cache or bad “ready to build” state; old valid cache cannot hide changed inputs. Source and positive WAV bytes unchanged, including on successful scan.

## UI and fixture acceptance

Compose Collection overview/error tables with `alp-ui` `Card`, `Badge`, `Alert`, `DataTable` and a real Qt model. The `FolderPicker` remains owned by spec 01; its pending choice must not become a verified binding until scan succeeds. Compare Reading/Collection/validation states with `docs/design/UX_PARITY_MATRIX.md` and prototype previews. For a complete local demonstration, load `tests/data/example_collection/` **if materialized in the actual Git checkout**; otherwise generate a deterministic real-WAV Collection using the fixture factory in a temporary directory and verify source/positive counts and non-mutation. The transfer ZIP intentionally may omit `tests/data/`. Review `docs/INTEGRATION_TEST_DATA.md` for HPC-derived **permissioned** exemplar decision; never connect to HPC during test execution.

## Blocking prototype parity (native UI)

**`IT-COL-008`:** Before changing this view inspect the prototype's `scanning-preview.png`, `collection-preview.png`, `validation-preview.png`, their underlying HTML/JS routes and the `alp-ui` Showcase. The native Reading/Collection/Validation screens must preserve the prototype's panel order, summary count hierarchy, source/positive mapping, per-file issue list, corrections, progress and cancel controls, disabled Build state, navigation and narrow layout. Do not substitute a generic table-only overview. With a real generated valid/invalid/corrected Collection, test route/CTA/focus/error transitions using `pytest-qt` (red first), save the minimum `spec-02-native/` screenshots and pass the six-dimension [Prototype acceptance](../design/PROTOTYPE_ACCEPTANCE.md) review. An unapproved difference is BLOCKED even when scanner tests pass. Missing transfer-ZIP fixtures do not count as a scanner failure: generated WAVs are valid test inputs.

## Tests / exit

- Unit `UT-PATH-001`, `UT-PATH-002`, `UT-COL-001`…`UT-COL-006` (`TD-COL`, `TD-WAV`, `TD-CACHE`, `TD-PATH`).
- Integration `IT-COL-001`…`IT-COL-007` (`TD-SCALE`, `TD-FAIL` additionally), with real WAV files and actual Qt controller/reopen. Demonstrate bounds, cancellation/repair, invalidation of removed entries, `size+mtime` freshness limitations, no input mutation, and paged large metadata, not simply an in-memory parser result.

## Implementation evidence

Implemented on `spec/02-collection-scan-and-metadata` with a typed Scan result shared by the
application controller and one metadata publisher. The bounded native reader currently accepts
nonempty mono/stereo PCM WAV with 8/16/24/32-bit samples; unsupported codecs are explicit
per-path failures. First scan reads one header per encountered WAV. Reopen reuses header facts only
when relative path, size and `mtime_ns` match; the documented cheap-fingerprint limitation remains
visible and Dataset Build must add its stronger pre-publication verification.

The application uses a cancellable `QThread` I/O task, manifest-last atomic cache publication,
10,000-row/16 MiB JSONL partition ceilings, stable Collection identity, verified local binding,
and paged Qt models. Metadata schema 2 records SHA-256 for every bounded partition, validates the
typed Scan handoff again on load, and compares the complete cheap input inventory both before
staging and immediately before manifest replacement. A changed input therefore cannot publish a
false valid cache; JSON-valid partition corruption is rejected and rebuilt. Replacing a folder
choice while a Scan is active cancels and transfers to the newest choice without binding the old
folder. Source and positive WAVs remain unchanged. The scientific sibling was inspected at
`91af5287dc18313f88902dc9696e8756274736b3`; its full-decode `soundfile` loaders do not fit this
header-only boundary and were not copied or wrapped.

Native macOS evidence and the six-dimension review are recorded in
[`docs/design/evidence/README.md`](../design/evidence/README.md). Focused red failures were recorded
for stale publication, cache corruption, scan replacement, portable control characters and Reading
width before their green passes. The full suite, static checks, fixture verification and screenshot
command are the executed evidence for this branch. `IT-COL-007` now scans 10,002 real generated PCM
WAVs before publishing and paging two record partitions rather than constructing an in-memory Scan
result. Windows and packaged-app qualification remain Specs 07 and 06 respectively.
