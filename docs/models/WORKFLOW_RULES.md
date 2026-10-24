# Workflow rules — Collection, Dataset Build, Training

## 1. Collection input and validation

### 1.1 Folder boundary and file scope

The selected folder is the Collection. Require direct `recordings/` and `positives/` subdirectories; enumerate only their **direct file children**. Read input WAVs, never rewrite/rename/copy them. `.alpaca/` is exclusively app-owned and excluded from input scanning. Reject missing folders, nested unexpected entries, non-WAV input files, unreadable/empty/unsupported WAV formats, unknown files, symlink escape, traversal, dangerous/Windows-reserved names, and Unicode-normalized/case-insensitive collisions with a **relative path + actionable reason**. Reject zero usable Source Recordings or zero valid Positive Examples for Dataset Build. Scan can show invalid Collection details; it cannot unlock Build.

Accept case-insensitive `.wav`; actual PCM/float support must be enumerated against the chosen native decoder and tested before asserting support. An unsupported codec never becomes “valid” based solely on extension. No metadata is inferred from other sidecars. No directory-depth recursion or bulk/full recording decode for the Collection overview.

### 1.2 Filename contract (single supported grammar)

```text
<complete-source-stem>__start-<nonnegative-integer>ms__end-<positive-integer>ms__<unique-label>.wav
SITE_001__start-012500ms__end-014900ms__call01.wav
```

Parse the **entire** basename anchored, not by prefix splitting; preserve a full source stem even if it contains `__` outside reserved syntax. Document and reject ambiguous reserved delimiters; require a nonempty filesystem-safe unique label. Numeric fields are base-10 integer milliseconds, no sign/decimal; guard overflow. Case/Unicode normalization is for collision detection and portability, **never for silently choosing one of two candidate Source Recordings**. The stem must resolve uniquely to `recordings/<stem>.wav`. Enforce `0 ≤ start_ms < end_ms`, and bound end against the Source Recording's actual header-derived frame duration. Treat intervals as half-open `[start_ms,end_ms)`.

Compare positive WAV's decoded/header frame duration to interval duration within a **documented sample/frame rounding tolerance** derived from involved sample rates (e.g. at most one frame on each end after integer-ms quantization), not an arbitrary multi-second grace period. Reject duplicates of one source+interval and collisions in portable path normalization. Distinct labels may represent distinct time spans.

**Validation guarantee:** format/name/mapping/time/duration *consistency only*. The cropped WAV waveform is not routinely matched to the original audio. Error copy must never assert waveform verification. If exact waveform verification is implemented later it needs a separate explicit bounded spec and tests.

### 1.3 Safe scan, caching and freshness

A cancellable asynchronous I/O task enumerates entries, reads bounded WAV headers once per encountered input and builds a compact in-memory handoff; scan failure does not publish partial/corrupt metadata. Store small versioned `collection.json` plus bounded JSONL record/positive partitions (initial partition ceiling: **10,000 rows or 16 MiB**, whichever first). Canonical references are portable `/`-separated relative components, validated before resolution; machine-absolute bindings live only in Application Settings. Collection identity is a persistent random ID inside `.alpaca/collection.json`; relocating folder retains identity after explicit rebind and validation.

On reopen, compare source inventories and cheap fingerprints (relative path, size, `mtime_ns`, header frame/sample/channel data) to cache. Re-inspect added, removed or changed entries; refresh only stale partitions and atomically replace mutable metadata. Filesystem facts are authoritative, cache is rebuildable. A quick fingerprint does not establish cryptographic identity. **Immediately before Dataset Build**, verify referenced current inputs (and stream a content hash where stronger reproducibility is required) and fail if stale/changed. Cache hits enforce identical path authorization and containment as uncached reads. Handle permission error, symlink change, missing path and external modification without trusting stale cache. Scan cancellation must not leave a validated-but-stale state.

## 2. Dataset Build

### 2.1 Configuration and protected time

Choose a nonempty set of Source Recordings, including the sources of included positives, and show counts of target positives and available recording duration. Config includes sample/window/overlap policy (if needed by chosen trainer), negative count policy (per-positive or total), seed, exclusion margin, allocation, source-grouped Split proportion and balancing. Store a **resolved** configuration, no implicit random default.

The protected union consists of every Annotation on a participating Source Recording, each expanded by the configured safety margin and clipped to source duration. Candidate noise windows must fit entirely in the remaining intervals. Never mine from positive crops, cross file bounds, overlap protected spans or overrun duration. Noise is a *candidate class label*, not proven absence of target sound. No explicit user-supplied negative files in MVP. If requested windows cannot be found within a bounded attempt budget, fail clearly with per-source eligible-duration evidence rather than silently undersampling or weakening exclusion.

### 2.2 Materialize and split

Read/seek just the selected Source Recording segments; use bounded chunks and stable audio conversion if required by the model. Use input WAV positive files for provenance/validation; materialized target intervals are sourced consistently from their original recordings with recorded transform settings. Record each Snippet's `target`/`noise`, source path/ID, source-time start/end, format, transform and provenance. A Dataset is complete only with its manifest, snippet files, train/val membership and content/integrity checks.

Split **by Source Recording**, never independently by Snippet. Seeded assignment is reproducible for identical inputs/configuration and balances target/noise counts where feasible; impossible per-split coverage yields an explicit error or undefined evaluation state according to the Training contract, never concealed leakage. New settings or changed source inputs create a **new Dataset ID**, never modify an existing Dataset. Immutability covers manifest, Split membership and audio payloads.

### 2.3 Publication and deletion

Dataset Build is a Run. Stage on the same filesystem as `.alpaca/datasets/`, fsync/validate important outputs where supported, publish via a lock-protected no-clobber rename to a previously absent final path. On cancel, crash, collision, disk-full or invalid outputs, do not expose a Dataset in browsing. A Run State success label is insufficient without validated output. Deleting a Dataset is deliberate and blocked if an Active Run reserves it; Models referencing the Dataset are never silently removed. Before deletion show loss of Snippets and provenance consequences and maintain integrity of existing Model history.

## 3. Training

Both Model Families consume exactly the **same immutable Dataset contract**, but have separately versioned transforms/configs. One Training Run reads a Dataset, validates Split and class coverage, resolves input representations, fits on `train`, computes supported metrics on `val`, then publishes family-specific model bytes + `model.json`.

- **CNN**: configured tensor/audio preparation, CPU baseline (optional GPU when available), seed, epochs, batch size, learning rate, optimizer/architecture identity. Record per-epoch loss only if measured. Persist checkpoint with required loader metadata and manifest and test loading it with the application's own loader.
- **Random Forest**: reuse and adapt verified `alpaca-pipelines` RF feature extraction and fitting code where practical, with a fixed ordered feature schema and version. Expose tree count, minimum leaf samples, maximum depth, threshold and any actual supported feature parameters. Record feature extraction, fitting and validation stages; persist estimator (`joblib` only if safe and versioned for trusted local artifacts) and feature metadata. Do not show fake epoch-loss curves. RF pipeline code may originally assume a different sample contract; adapt input/feature mapping explicitly and prove compatibility using real Dataset Snippets.
- **Metrics**: distinguish accuracy, precision, recall, F1 and ROC-AUC, report label counts/threshold, and mark undefined metrics as null + explanation when a Split lacks the required classes; do not fabricate values. Invalid train/val coverage may block Training when metrics or fit cannot be defined.

Persist stable model ID, human-readable label distinct from ID, family, Dataset ID and root-contained relative provenance references, resolved parameters, seeds, feature/transform schema, metrics and checksums. Reopening must load published manifests even if the source Collection is rebound. No Prediction UI or generic inference promise is implied by Model publication.

## 4. Run ownership, execution and conflicts

Only Dataset Build and Training are Runs. QProcess launches an environment-aware Worker from the same application installation, not `python` on PATH or shell. Application Controller enforces **one Active Run** with persistently recorded state transitions (`created`, `starting`, `running`, `cancelling`, terminal `completed`/`failed`/`cancelled`/`interrupted`). Terminal success requires validating an output Artifact. Reserve Dataset/Collection inputs against conflicting deletion/rebinding during active usage; read-only browsing may continue. Progress is bounded and stage-aware. Cancellation is cooperative with timeout/forced termination fallback; orphaned Runs reconcile to `interrupted` on startup rather than remaining active forever. Never resurrect or auto-retry unexpectedly. Logs and diagnostics avoid embedding private absolute paths in portable artifacts.

See [`../ARCHITECTURE.md`](../ARCHITECTURE.md) for path/reservation/atomicity details and the `IT-*` behavior index for externally observable evidence.

## 5. Reuse discipline

Inspect the installed/sibling `alpaca-pipelines` code and tests for source seek reads, channel/resample transforms, negative-window generation, Split allocation, CNN architecture/trainer, acoustic feature vector schema, RF fitting/metrics and checkpoint formats. Reuse **algorithmic behavior** only after input/output contracts are reconciled and tests protect scientific equivalence. Do not wrap unrelated pipeline orchestration or assume archive outputs are compatible with the Trainer's canonical schemas.
