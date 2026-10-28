# Detect — data and scientific contract

## Ownership and artifact lineage

- A **Detect Collection** represents an approved, independently identified set of Source Recordings under a selected root. Its manifest, inventory and Runs are distinct from Train's `collection.json`/`.alpaca/`. Store Detect metadata in an app-owned workspace outside the source root. Support explicit relinking; compare stable inventory facts before accepting moved/changed sources.
- **Detection Run** freezes Model identity/integrity, selected source inventory, resolved preprocessing/window/threshold settings, software versions and outcomes. Persist state/diagnostics separately from published, immutable result metadata. Run success requires verified publication, not only process exit.
- **Detection Result** describes source-recording paths/identities and intervals in **original source time**, with score meaning, class mapping, provenance and non-successful-file status. Do not copy WAV data into a Result.
- **Derived Result** references one input Result and its frozen RF Model/settings, stores accepted/rejected/unscored decisions, never overwrites its parent and remains metadata-only even though RF processing reads WAV samples.
- **Corpus Export** freezes a chosen Result plus selection/settings, publishes materialized audio at an explicit user-visible destination, records checksums and maps exported snippets/concatenation offsets back to original source and timestamps. Present **Show in folder** after success. A result can have multiple exports.

## Source discovery

Recurse deterministically, with bounded work and no symlink following by default. Exclude app-owned/Train-generated directories and recognized `positives/` snippets; `recordings/` is the default inclusion candidate in a recognizable Train Collection. Unknown WAVs are candidates for explicit folder/file approval, not automatically accepted. Separate **excluded**, **invalid** and **undecided**. Validate header/format, path containment, duplicates/collisions and staleness; do not turn an unreadable input into a zero-detection recording. Exact app-data schema/layout and discovery snapshot schema are scoped to [ST-03](specs/ST-03-detect-workspace.md)/[ST-04](specs/ST-04-wav-discovery.md); finalize their values against tests and verified platform behavior, not by copying Train metadata.

## Scientific order

1. **CNN** first-pass sliding-window inference over approved WAVs. Verify Train package loading, sample rate/resampling, normalization, spectrogram/config parity, class order, window/hop, threshold meaning, merge/clamp behavior and real-WAV numerical outputs before claiming availability. A score is not automatically a calibrated probability.
2. **Optional RF** second-layer assessment of candidate intervals, never automatically a stand-alone full-recording detector. Verify the exact ordered feature schema, preprocessing, estimator class order and score/threshold semantics. Preserve accepted/rejected/unscored and the original CNN Result. Do not load arbitrary untrusted Torch/joblib files without an explicit trust boundary.

Ground interoperability in [Train Model export](science/MODEL_EXPORT_CONTRACT.md), [binary classification](science/BINARY_CLASSIFICATION_CONTRACT.md) and inspected `../bioacoustics-dl-toolbox` / `../alpaca-pipelines` source, not assumed APIs.

## Export behavior to specify and verify in [ST-10](specs/ST-10-corpus-export.md)

- **Individual snippets:** origin-linked collision-safe names recording source identity and start/end in source time.
- **Concatenated WAV + Raven TSV:** selection rows refer to offsets in the **concatenated** waveform; a separate provenance map records original source/interval.
- **Both:** same frozen selection, independent verified materializations.

Define sample-rate/channel mismatches, interval/frame rounding, ordering, gaps, TSV coordinate conventions, filename encoding, destination collisions, cancelled/stale-source publication and multi-file atomicity before implementing. Never silently resample or merge channels without an approved policy.

## Cross-cutting operations

Use explicit unavailable/incompatible Model states; plain-language errors; background scanning and workers; cancellable Runs; per-file failure reporting; privacy-safe, bounded application/Worker JSONL logs consistent with Train diagnostics, without creating shared Run identity. No claim of implemented detection until real inference tests pass.

**Implementation authority:** the [ST-03–ST-11 sequence](IMPLEMENTATION_SEQUENCE.md) and one active stage spec own detailed acceptance and test IDs. This page records stable scientific/domain invariants only; do not add competing stage specs or whole-Studio tests here.
