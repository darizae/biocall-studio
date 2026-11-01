# ST-04 → ST-05/07 recording inventory handoff

## Implemented contract for review

`InventorySnapshot` schema version `1` is immutable after publication and contains no absolute
source root. Its identity is `inv_` plus the first 32 hexadecimal characters of the SHA-256 over
the canonical complete contract. `digest` is the full SHA-256. Canonical content includes:

- Detect `collection_id`, ST-03 `binding_revision`, UTC `scanned_at`, the explicit freshness and
  conflict-policy strings, deterministic decision rules, diagnostic issues, and recording rows;
- NFC relative `recording_key` values in exact sorted order;
- `size_bytes`, `mtime_ns`, full-file `content_sha256`, bounded-header `sample_rate_hz`, `channels`,
  `frame_count`, `encoding`, and `duration_frames` (exactly the frame count);
- independent `decision`, `status`, `reason`, `decision_origin`, `decision_path`, and rescan
  `change` (`added`, `unchanged`, `replaced`, or `removed`).

`included_keys` contains only rows whose decision is `included` and whose status is `valid`. An
invalid or unreadable WAV is never converted to an empty or zero-detection recording.

## Inclusion and collision decisions

The recognized `recordings/` subtree defaults to included. WAVs elsewhere default to undecided.
Recognized generated/labeled locations (`positives`, `.alpaca`, `datasets`, `snippets`, `models`,
`runs`, `results`, and `exports`) are policy-excluded and cannot be overridden by a broad folder
rule. For other locations, an explicit file rule overrides the nearest explicit folder rule, which
overrides the default. Decision revisions retain the actual scan timestamp and create a new
content-derived immutable inventory identity.

Traversal does not follow symbolic links or Windows reparse points. NFC/casefold path conflicts and
multiple paths to one device/inode are preserved as observable conflicts, marked invalid and
excluded, and never silently collapsed into one recording. Removed rows remain as `missing`
tombstones. A full SHA-256 distinguishes replacement even when size and mtime are restored.

## Persistence and publication

Snapshots live only in app-owned
`detect/v1/collections/<collection_id>/inventories/<inventory_id>/`. Rows are partitioned into
checksum-indexed JSONL files; the public Collection pointer advances atomically only after the
complete immutable directory exists and the ST-03 root binding plus current source change tokens
are revalidated. Cancellation, scan failure, path change, or pointer publication failure leaves the
prior Collection pointer and prior snapshot unchanged. Relink retains the old pointer on its old
binding revision and therefore presents it as stale until a complete rescan publishes.

Bounds are 100,000 traversal entries/recording rows, 64 directory levels, one recording descriptor
at a time, 64 KiB of WAV header structure, 1 MiB hash chunks, 1,000 rows and 1 MiB per JSONL
partition, 64 KiB per row, 1,000 partitions, 1,000 explicit rules, 1,000 diagnostic issues, and 200
initial Qt model rows per page. Issue truncation is explicit. WAV bytes are hashed but never decoded
for discovery, and the source tree is never written.

## Downstream freeze and revalidation

ST-05 may consume the portable snapshot without a source path. A later Run must freeze the exact
`inventory_id` and `digest`, accept only `included_keys`, resolve the private ST-03 root binding,
then call `validate_recording_source(root, row)` for each selected row. That boundary reopens with
no-follow semantics, rechecks containment, regular-file identity, size, mtime, full SHA-256, and WAV
header facts. It fails on any change; ST-07 must not rescan to replace frozen facts.

## Evidence boundary

The indexed implementation cases are `UT-DET-004`–`006` and `IT-DET-003`–`005`. Native Cocoa
evidence is under `docs/design/evidence/st-04-native/`. Windows-native reparse/permission behavior,
installed-app qualification, 150% DPI, the separately initiated ≥600-second soak, classification,
Model intake, and whole-Studio end-to-end behavior are not claimed by ST-04.
