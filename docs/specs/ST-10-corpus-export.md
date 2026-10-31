# ST-10 — Frozen corpus export (WAV and Raven TSV)

**Branch:** `detect-st10-corpus-export` from reviewed `detect`. **Predecessors:** ST-07 immutable Result, ST-08 selection, optional ST-09 derived Result. **Successor:** REV-01. **Status:** planned.

## Scope and ownership

Export is an explicit, independent **materialization job**, never an inference stage. Freeze selected intervals from one chosen (original or refined) Result, support **individual WAV snippets**, **one concatenated WAV with Raven TSV**, or **both**, at an explicitly chosen persistent, discoverable output destination. Do not alter Results, source WAVs, Train Datasets or Model files; no audio playback/editor.

## Contract and handoff

`ExportSnapshot` (versioned immutable request): Result ID/digest and parent lineage (if any), sorted stable candidate IDs and original recording frame/time intervals, original file fingerprints, selected output mode, approved format/channel/sample-rate handling, destination and name-collision policy. Once export begins, UI selection changes cannot mutate this frozen request. `ExportReceipt`: export ID, verified file list/checksums and byte sizes, individual snippet/source mapping, concatenation offset mapping and Raven TSV rows, immutable provenance record, explicit final destination. An export is **not** a new scientific Result.

Define and test exact half-open source frame arithmetic, frame rounding, clipping to available data, deterministic sort, zero-length rejection, encoder dtype, duplicate filenames, Windows-safe names and same-name collision. For mixed sample rates/channels, either block with actionable guidance or use a specifically approved scientifically verified explicit conversion; **never silently resample or downmix**. Raven TSV offsets refer to the *concatenated output*, with separate original source-time mapping. TSV units/columns and gaps must match a verified Raven reference. Multiple independent exports may derive from the same Result.

## Failure, cancellation and privacy

Validate frozen inputs before opening output; source changes, disk full, unwritable destination and collision cannot advertise success. Create private destination-volume staging, verify all files and receipt, then publish one self-contained collision-safe export directory atomically (not arbitrary partial multi-file overwrites). Cancel cleans or clearly marks private staging; reopening existing exports checks hashes without rewriting prior export. Never silently overwrite external files. Outputs contain selected audio and source-time provenance; destination confirmation must explain potential sensitive content. No source-root writes unless destination is explicitly approved and containment policy ensures no future discovery feedback loops (prefer external destination).

## Native parity

`#detect/export`: frozen selection count + source/output mapping, `snippets | concat | both`, explicit destination, `ready/conflict/stale/cancelled/error/success`, a genuine **Show in folder** action for successful existing destination. No tiny unlabeled captions, invalid promise of an output location, or developer notes; concise `HelpHint` for formats and provenance. Verify keyboard/compact width and accessible status.

## TDD and boundary verification

- `UT-DET-021` — exact frame/byte/TSV offset arithmetic and output representation without rounding drift.
- `UT-DET-022` — frozen selected IDs/digests, parent lineage and reproducible provenance ordering.
- `UT-DET-023` — collision-safe names, mixed-format decision and conservative publish/overwrite policy.
- `IT-DET-019` — compare real snippet PCM samples, headers, checksums and original timestamps byte-by-byte/frame-by-frame (`TD-WAV`, `TD-PATH`).
- `IT-DET-020` — real concatenated WAV plus Raven TSV offsets and both-mode receipt on distinct sources; reopen all outputs (`TD-WAV`, `TD-FAIL`).
- `IT-DET-021` — real stale/permission/collision/disk error/cancel and destination Show in folder in native Qt; no partial visible success or source mutation (`TD-UI`, `TD-PATH`, `TD-FAIL`, `TD-RUN`).

Tests first at real audio/storage/Qt boundaries. Inspect upstream PCM extraction API if reuse required; fix in owning toolbox with upstream regression and independent commit. Run full feasible ordinary suites before commit, explicit soak separate. Do **not** run complete Train→Detect chain until ST-11.

## Gate

Scientific frame/TSV convention documented and verified, outputs byte-correct, safe all-or-nothing publication, native destination discoverability and scoped tests reviewed. Local merge into `detect` after owner review; no push.
