# Prediction — future application plan (**not part of BioCall Studio Train MVP**)

**Status: design only; no implementation or release acceptance in Trainer Specs 01–07.** This page preserves the intended interoperability requirements for a **separate future Prediction application**. It must not be used to justify adding prediction routes, buttons, inference workers, segment scoring APIs or inference tests to the Trainer. The current native UX remains exactly the [training-first prototype](design/prototypes/training-first/index.html). When a Prediction project is initiated, author its own UX prototype, numbered specs, package/release gates, threat model and test index.

## Product objective and boundaries

The Prediction app will initially accept only **binary single-label `target`/`noise` Models** from BioCall Studio Train ([current contract](science/BINARY_CLASSIFICATION_CONTRACT.md)); multi-class/multi-label expansion would require an explicitly approved future schema/UX/test plan. It will accept compatible, **immutable Models** exported by BioCall Studio Train, select source audio independently of the Trainer's Dataset, and produce reproducible predictions with source-time provenance. It may later support a CNN candidate detector plus optional RF refinement. Predictions and review artifacts belong to the **future app**, not to Trainer `.alpaca/` training runs by assumption.

**Training-time prerequisite (implemented by Spec 05):** both CNN and RF save complete, versioned, integrity-checked model packages. See [MODEL_EXPORT_CONTRACT](science/MODEL_EXPORT_CONTRACT.md) for required architecture/weights, preprocessing, class order, RF ordered feature schema and provenance. **Prediction-only verification is deferred**; simply reopening a checkpoint does not validate scores on real unseen WAV.

## Upstream code to study when Prediction work begins

Reference [`../alpaca-pipelines`](agent/SOURCE_MAP.md) at a **fresh local commit** (previously inspected `973866102726556f844877d1fe38978fe06eda4b`; not an API lock):

| Future capability | Existing upstream reference | Compatibility question |
|---|---|---|
| CNN load & frame/segment classification | `src/alpaca_pipelines/prediction/executor.py`, `src/bioacoustics_dl_toolbox/training/checkpoints.py` as shipped in inspected pipeline | Replace embedded toolbox with the **separately installed** `../bioacoustics-dl-toolbox` library; verify checkpoint configuration fields, model architecture, class map and numerical transform parity. |
| CNN recording-wide event detection | `src/alpaca_pipelines/prediction/{audio_sources.py,executor.py}` | Sliding-window length/hop, sample-rate conversion, target threshold, overlapping detection merges, bounded reads and source-relative timestamps. |
| RF feature extraction and RF model loading | `src/alpaca_pipelines/rf/{config.py,audio_preprocess.py,audio_features/,executor.py}` | Resample/padding, band limits, robust/MFCC names/order, numeric equivalence, estimator class-order and threshold policy. Do not silently substitute toolbox RF feature defaults. |
| RF postprocessing of CNN candidates | `src/alpaca_pipelines/rf_inference/{config.py,executor.py}` | Existing RF inference expects **CNN prediction intervals**; it is not independently a full-recording RF event detector. Preserve accepted/rejected/unscored semantics. |

The dedicated `../bioacoustics-dl-toolbox` checkout is the intended **direct scientific dependency** for the CNN implementation; its current API/version must be inspected locally before using it. Both packages may export the same Python namespace if pipeline bundles an older copy—record and resolve this explicitly. Distributed Prediction installers must not depend on developer checkout paths.

## Future interoperability and scientific contracts

1. **Model intake:** accept only documented `model.json` schema/format versions and compatible signed or checksum-verifiable artifact contents; refuse modified files, unknown class maps, missing preprocess schema, incompatible toolbox or feature extractor versions. Loading Torch/joblib artifacts may execute code: enforce a trust policy (prefer Trainer-generated, provenance-verified artifacts), consider safer formats/migration tooling before third-party model import. Do not infer compatibility from `.pt`/`.joblib` extension alone.
2. **Preprocessing equivalence:** CNN must reconstruct model architecture and state, use `eval()`/no-gradient, exact sample rate, channel policy, spectrogram and normalization used during validation (training augmentation excluded). RF must reapply exact resample/padding/band and **ordered** acoustic features; align estimator probability columns using the saved class mapping, never assume index 1 equals `target`.
3. **Input and semantics:** define bounded waveform reading, explicit source path/identity, source-time half-open `[start_ms, end_ms)` intervals, per-window probability, raw score vs decision threshold, calibrated-vs-uncalibrated interpretation and invalid/unscorable outcomes. No fabricated zeros for errors or undefined outputs. Decide separately whether users supply short candidate intervals or whole recordings.
4. **Optional two-stage detector:** CNN proposes intervals; RF may rerank those *specific* excerpts; accepted/rejected/unscored outputs keep original CNN scores and provenance. An RF Model trained directly from Trainer Snippets can classify **provided** excerpts; it does not automatically generate recording-wide candidate event times. Independent RF scanning would be a separately specified windowing/detection feature.
5. **Prediction artifacts:** future owner chooses an immutable Prediction Run/Manifest schema, source fingerprinting, time/score fields, model IDs/hashes, method/thresholds and per-file failure details. Avoid coupling trained Model artifacts to fixed Dataset filename layouts or machine-absolute paths.
6. **Operations/UI:** define its own UX, resource usage, progress, cancellation, model selection, batch input, output navigation and platform release controls. No automatic HPC dependency; use small generated real WAVs with authorized Git LFS samples only when essential.

## Proposed future TDD index — **reserved, NOT Trainer acceptance**

When the Prediction app is scoped, migrate/refine these IDs to *its* test documents; do not include them in Trainer `docs/UNIT_TESTING.md`, `docs/INTEGRATION_TEST_BEHAVIORS.md`, Specs 05–07 or their release gates.

| Future ID | Evidence to require in Prediction app |
|---|---|
| `UT-INFER-001` | Source-time bounds, score schema and explicit class/probability order |
| `UT-INFER-002` | Threshold logic separated from raw probability, invalid/unscorable states |
| `UT-INFER-003` | CNN transform/class-map versioning and RF exact ordered feature/schema parity |
| `UT-INFER-004` | Contained/model version/checksum/trust and incompatibility refusal |
| `IT-INFER-001` | Fresh-process CNN load and CPU score **real WAV** using exact exported transforms |
| `IT-INFER-002` | Fresh-process RF load and CPU score **real WAV** with exact feature schema |
| `IT-INFER-003` | Compare saved validation/reference probabilities with independent reloaded scores within specified tolerance; include WAV outside training Dataset |
| `IT-INFER-004` | Corrupted/incompatible Model, altered class map, bad/short/unsupported WAV fail explicitly |
| `IT-INFER-005` | Multiple bounded intervals preserve order, provenance and resource limits; no checkout dependency |

**Future acceptance prerequisite:** train and export **both** model families in Trainer using real WAV-backed Snippets; import them into an isolated Prediction environment (no Trainer checkout), load and score both against an independent WAV, prove transform/class-map parity with a justified tolerance, and test rejected/unsupported formats. This is **not** a gating test for today's Trainer or installer.

## Trigger for implementation

Only after the owner explicitly authorizes the Prediction application's scope and UX: establish a separately versioned interoperability contract (including migration), assign implementation ownership and new specs, then move the reserved cases into its active test registry. Trainer Spec 05 remains solely responsible for **export integrity and structural reload**, not the consumer's algorithm.
