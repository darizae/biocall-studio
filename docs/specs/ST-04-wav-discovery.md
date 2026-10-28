# ST-04 — Safe recording discovery and inventory

**Branch:** `detect-st04-wav-discovery` from reviewed `detect`. **Predecessor:** ST-03 Collection contract. **Successor:** ST-05. **Status:** planned.

## Scope and ownership

Detect owns read-only recursive WAV enumeration below an approved ST-03 source root, explicit inclusion decisions (file/folder), deterministic inventory revision, header validation, rescan/progress/cancel and inventory UI. This is a background **Scan**, not an inference Run. No model, classifier, extraction, export or edits to Train's scanner.

Use `recordings/` as a *default candidate* under recognizable Train layout; do not auto-include all unknown WAVs. Avoid recognized generated Train datasets/snippets and `positives/`, app-owned locations and export outputs. Unknown WAVs require explicit approval. Distinguish `included`, `excluded`, `undecided`, `invalid`, `missing` and `stale`; keep reasons and inherited folder decisions observable. Do not follow symlinks/reparse points by default; resolve and revalidate containment at I/O and later Worker boundaries, not only on listing.

## Contract and handoff

`InventorySnapshot` (versioned, immutable after publication): Collection ID/root-binding revision, inventory ID/digest, deterministic relative-path recording keys, per-file metadata (`size_bytes`, `mtime_ns` or available change token, optional content fingerprint, PCM/header `sample_rate_hz`, `channels`, `frame_count`, encoding, duration in **frames**), decision/status/reason and scan timestamp. Include explicit per-file freshness strategy and conflict policy for duplicate paths, hardlinks, casefold/NFC ambiguity and replacement after rescan. Keep private absolute root binding out of published portable Results. A downstream Run freezes a validated snapshot and rechecks each selected source; do not rescan in ST-07 to recover dropped facts.

Bound traversal, file-descriptor use, JSONL rows/bytes and Qt model paging; do not decode whole WAV to enumerate. An invalid/unreadable WAV must never become a valid zero-detection row. A cancelled or failed scan leaves last-good snapshot intact, with its stale status shown; rescan publishes only a complete verified revision.

## Native parity

`#detect/recordings`: visible hierarchy, selected folder/file detail, inclusion decision, counts, issue status, progress, cancel/rescan and stale/missing/empty states, matching the prototype's information hierarchy. No gratuitous fine-print captions or status badges without a state; concise `HelpHint` for inclusion implications. Verify real `alp-ui.DataTable` pagination, focus, layout at normal/compact widths, and preservation of selection on rescan when stable keys still exist.

## TDD and boundary verification

- `UT-DET-004` — inclusion precedence, generated-data exclusions, undecided versus invalid, deterministic decisions and count aggregation.
- `UT-DET-005` — normalized identity, traversal/symlink/reparse and duplicate/hardlink/casefold collisions cannot silently collapse rows.
- `UT-DET-006` — header/freshness interpretation, add/remove/replace, cancellation and snapshot validation.
- `IT-DET-003` — real nested mono/stereo WAVs; nested generated snippets, symlink loop/escape and path collision; correct deterministic included inventory and no source writes (`TD-WAV`, `TD-PATH`, `TD-COL`).
- `IT-DET-004` — truncated/unsupported headers, permissions, edited/missing files, many-row bounded scan, cancel/restart/rescan without false completion (`TD-WAV`, `TD-CACHE`, `TD-SCALE`, `TD-FAIL`).
- `IT-DET-005` — genuine Qt selection, folder decisions, count updates, paging, keyboard, canceled picker, native screenshots and state transitions (`TD-UI`, `TD-SCALE`).

Tests first; only scanner/Qt seams are asserted here, not classifier/Worker/corpus E2E. Targeted + affected ST-03 regression + complete feasible ordinary suites before commit. Real WAV and native Qt evidence mandatory for those claims; skips remain blockers.

## Gate

Review a versioned, complete `InventorySnapshot`, exclusion policy, staleness/relink invalidation and bounded real-WAV scan/native UX. Only then integrate locally to `detect` and start ST-05 from reviewed `detect`. No push.
