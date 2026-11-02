# ST-03 → ST-04 Detect workspace handoff

**Historical gate:** implemented on `detect-st03-workspace`; later included in the merged `main`
source baseline. This handoff remains implementation evidence, not installed-platform approval or
authority to begin new stage work.

## Accepted input boundary for review

- A Detect Collection ID is an opaque `det_` plus 32 lowercase hexadecimal characters. It is
  independent of every Train Collection ID and remains stable across an approved same-root move.
- Portable Collection metadata uses schema version `1` and the exact fields
  `schema_version`, `collection_id`, `display_label`, `created_at`, `updated_at`,
  `binding_revision`, `root_evidence`, `inventory_revision`, and
  `inventory_binding_revision`. It contains no source path or source URI.
- The private root binding uses schema version `1` and the exact fields `schema_version`,
  `collection_id`, `binding_revision`, and `source_root_uri`. The URI is a canonical local
  `file:` URI and exists only under per-user application data.
- Root evidence schema version `1` is `{schema_version, filesystem_id, file_id}` from the selected
  directory itself. It is root identity evidence, not a recording inventory or a recording hash.
- The application-owned layout is
  `<AppLocalDataLocation>/detect/v1/{settings.json,collections/<collection_id>/...}`. Each Collection
  owns `collection.json`, `binding.json`, `.last-good/` copies, and reserved `runs/`, `results/`, and
  `exports/` directories. The reserved directories have no ST-04+ artifact formats yet. With
  `--settings-dir`, that supplied directory is the isolated application-data root while Train keeps
  its established `settings.json` behavior.
- Application-owned directories are mode `0700` and metadata files mode `0600` on the tested macOS
  filesystem. Collection IDs and relative references are validated before path construction;
  symlinked Collection/metadata paths, traversal, absolute paths, Windows reserved names, unsafe
  characters, and NFC/casefold collisions fail closed. JSON reads are bounded to 1 MiB.

## Binding and freshness contract for ST-04

- `valid`, `missing`, `inaccessible`, and `changed` are distinct decisions. Missing or unreadable
  roots are never interpreted as an empty recording set.
- Selecting a relocated directory with the same verified root evidence yields
  `awaiting_confirmation`. Confirmation rechecks the evidence and binding revision, increments
  `binding_revision`, and atomically replaces the versioned documents. Cancel, picker cancellation,
  denied access, or a changed proposal preserves the existing binding.
- Different root evidence cannot take over a Collection. The UI offers creation of a new Collection
  instead. A cross-filesystem copy therefore remains a different Collection until a later,
  explicitly specified evidence contract can prove otherwise; ST-03 does not guess from names.
- New Collections start with both `inventory_revision` and `inventory_binding_revision` set to
  `null`. ST-04 may publish an immutable inventory reference only after it validates the selected
  source set; it must record the then-current `binding_revision` in
  `inventory_binding_revision`.
- Inventory freshness is exactly: no inventory when `inventory_revision is null`; current when
  `inventory_binding_revision == binding_revision`; stale when an inventory exists and the two
  binding revisions differ. Relink preserves the prior pointer and its original binding revision,
  so reassessment is mandatory without erasing historical lineage.
- Future recording references must remain portable relative paths validated by
  `validate_relative_reference`; ST-04 owns discovery, inclusion decisions, recording identity,
  hashes, and the immutable `InventorySnapshot`. ST-03 performs no recursive scan and writes
  nothing under the selected source root.

## Review evidence boundary

The indexed implementation cases are `UT-DET-001`–`003` and `IT-DET-001`–`002`. Native evidence is
stored under `docs/design/evidence/st-03-native/`. Exact commands, pass counts, platform, deferred
platforms, branch, and commit SHA are part of the owner-review delivery record. No Windows-native,
installed-app, 150% DPI, ≥600-second soak, ST-04 inventory, or whole-Studio end-to-end claim is made.
