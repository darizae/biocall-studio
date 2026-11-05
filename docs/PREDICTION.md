# Detect — data and scientific contract

## Ownership and artifact lineage

- A **Detect Collection** represents an approved, independently identified set of Source Recordings under a selected root. Its manifest, inventory and Runs are distinct from Train's `collection.json`/`.alpaca/`. Store Detect metadata in an app-owned workspace outside the source root. Support explicit relinking; compare stable inventory facts before accepting moved/changed sources.
- **Detection Run** freezes Model identity/integrity, selected source inventory, resolved preprocessing/window/threshold settings, software versions and outcomes. Persist state/diagnostics separately from published, immutable result metadata. Run success requires verified publication, not only process exit.
- **Detection Result** describes source-recording paths/identities and intervals in **original source time**, with score meaning, class mapping, provenance and non-successful-file status. Do not copy WAV data into a Result.
- **Derived Result** references one input Result and its frozen RF Model/settings, stores accepted/rejected/unscored decisions, never overwrites its parent and remains metadata-only even though RF processing reads WAV samples.
- **Historical Detect Corpus Export v1** freezes a chosen Result plus selection/settings and remains immutable and readable for compatibility. New reviewed-corpus publication is Review-owned: it starts only from a verified Finalized Review session, can be repeated independently, and preserves lineage to this Result without modifying it. Detect's existing new-export entry remains only until the separately gated RV-07 route migration.

## Source discovery

Recurse deterministically, with bounded work and no symlink following by default. Exclude app-owned/Train-generated directories and recognized `positives/` snippets; `recordings/` is the default inclusion candidate in a recognizable Train Collection. Unknown WAVs are candidates for explicit folder/file approval, not automatically accepted. Separate **excluded**, **invalid** and **undecided**. Validate header/format, path containment, duplicates/collisions and staleness; do not turn an unreadable input into a zero-detection recording. The implemented Detect storage and inventory contracts live in the owning source code and indexed tests; do not copy Train metadata.

## Scientific order

1. **CNN** first-pass sliding-window inference over approved WAVs. Maintain verified Train package loading, sample rate/resampling, normalization, spectrogram/config parity, class order, window/hop, threshold meaning, merge/clamp behavior and real-WAV numerical outputs across changes. A score is not automatically a calibrated probability.
2. **Optional RF** second-layer assessment of candidate intervals, never automatically a stand-alone full-recording detector. Maintain numerical parity of the exact ordered feature schema, preprocessing, estimator class order and score/threshold semantics. Preserve accepted/rejected/unscored and the original CNN Result. Do not load arbitrary untrusted Torch/joblib files without an explicit trust boundary.

Ground interoperability in [Train Model export](science/MODEL_EXPORT_CONTRACT.md), [binary classification](science/BINARY_CLASSIFICATION_CONTRACT.md) and inspected `../bioacoustics-dl-toolbox` / `../alpaca-pipelines` source, not assumed APIs.

## Reviewed corpus export

- **Individual WAV files:** origin-linked collision-safe names recording source identity and start/end in source time.
- **Concatenated WAV + Raven TSV:** selection rows refer to offsets in the **concatenated** waveform; a separate provenance map records original source/interval.
- **Both:** the same frozen Review inventory produces both representations without changing scientific bytes or order.

Review includes Call and Unreviewed candidates, excludes Not a call from audio, and records individual human, bulk human, model-only and rejected status across the complete eligible decision inventory. Its v2 metadata uses bounded canonical JSONL rows plus compact digest manifests/file indexes/receipts, with streamed verification and no fixed 10,000-row ceiling. Honor the implemented PCM-preserving format checks, original Result frame/time provenance, deterministic order, Raven concatenation offsets, filename/collision policy, practical RIFF size guard and same-volume no-partial publication. Never silently resample, downmix or merge channels. **Show in folder** is available only after the receipt and every declared file verify. Historical Detect v1 readers and bytes remain unchanged.

## Cross-cutting operations

Use explicit unavailable/incompatible Model states; plain-language errors; background scanning and workers; cancellable Runs; per-file failure reporting; privacy-safe, bounded application/Worker JSONL logs consistent with Train diagnostics, without creating shared Run identity. Real inference and export acceptance is recorded in [ST-11 source qualification](ST-11_QUALIFICATION.md); it does not qualify installed releases.

**Implementation authority:** the current [status and work policy](IMPLEMENTATION_SEQUENCE.md), owning source code and indexed tests; this page records stable scientific/domain invariants without duplicating completed implementation specs.
