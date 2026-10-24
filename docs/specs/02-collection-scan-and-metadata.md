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

Compose Collection overview/error tables with `alp-ui` `Card`, `Badge`, `Alert`, `DataTable` and a real Qt model. The `FolderPicker` remains owned by spec 01; its pending choice must not become a verified binding until scan succeeds. Compare Reading/Collection/validation states with `docs/design/UX_PARITY_MATRIX.md` and prototype previews. For a complete local demonstration, load `tests/data/example_collection/` (synthetic, versioned WAVs) and verify expected source/positive counts and non-mutation. Review `docs/INTEGRATION_TEST_DATA.md` for HPC-derived **permissioned** exemplar decision; never connect to HPC during test execution.

## Tests / exit

- Unit `UT-PATH-001`, `UT-PATH-002`, `UT-COL-001`…`UT-COL-006` (`TD-COL`, `TD-WAV`, `TD-CACHE`, `TD-PATH`).
- Integration `IT-COL-001`…`IT-COL-007` (`TD-SCALE`, `TD-FAIL` additionally), with real WAV files and actual Qt controller/reopen. Demonstrate bounds, cancellation/repair, invalidation of removed entries, `size+mtime` freshness limitations, no input mutation, and paged large metadata, not simply an in-memory parser result.
