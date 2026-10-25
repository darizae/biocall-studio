# alpaca Desktop Trainer — Ubiquitous language

Use these exact capitalized domain nouns in UI, code, docs, spec IDs and test descriptions. Prefer singular nouns for types and titles. Scientific source intervals use **integer milliseconds** unless a field explicitly says otherwise.

| Term | Definition / boundary |
|---|---|
| **Collection** | The user-selected, physically existing directory containing direct child `recordings/` and `positives/`. This is the source of scientific input truth, not an imported copy. A Collection can be invalid pending correction. |
| **Source Recording** | An original full-length readable WAV directly under `recordings/`. Its complete filename stem identifies the source of Positive Examples. Input stays user-owned and read-only. |
| **Positive Example** | User-exported cropped WAV in `positives/`, named with an unambiguous Source Recording stem, `start`/`end` source-time and unique label. A positive is not automatically a materialized Dataset Snippet. |
| **Annotation** | Derived `target` interval on a Source Recording, reconstructed from one validated Positive Example filename; includes source identity, start/end milliseconds and positive path for provenance. Annotations are not interactively edited in the Trainer. |
| **Source-time interval** | Half-open `[start_ms, end_ms)` range in the *original* Source Recording. Always `0 ≤ start_ms < end_ms ≤ duration` (with frame rounding handled as defined). |
| **Collection Scan** | Cancellable asynchronous directory/header/name validation and summary building. This is a local I/O activity, **not** a scientific Run. |
| **Collection Metadata** | Rebuildable `.alpaca/collection.json` summary plus bounded JSONL partitions, with relative references, observed file fingerprints and validation/schema version. WAV inputs remain authoritative. |
| **Dataset Build** | Configured scientific Run selecting Source Recordings, materializing Snippets and assigning reproducible Splits. |
| **Negative Mining** | Deterministic selection of eligible candidate-noise windows while excluding positive/protected intervals plus safety margin; does not establish ground-truth absence of a call. |
| **Snippet** | Materialized bounded-duration WAV owned by an immutable Dataset; label is `target` or `noise`. Contains provenance back to Source Recording and source-time interval. |
| **Split** | Immutable `train` or `val` membership assigned by source grouping so the same Source Recording does not cross Splits. |
| **Dataset** | Immutable published artifact of Snippets, Split lists, manifest, parameters, seeds and Collection/input provenance. Multiple Models can use the same Dataset. |
| **Training** | Scientific Run that fits one specified **Model Family** from a Dataset and publishes a Model after validating its output. |
| **Model Family** | Algorithm category `cnn` or `random_forest`; determines settings, transforms, serializer/loader and appropriate metrics. Not a separate workflow. |
| **Binary Single-Label Classification** | The **only** Trainer task: each Dataset Snippet is assigned exactly one of two mutually exclusive classes, `target` or `noise`. Model class mappings have exactly two indices. Library multi-label/multi-class capability is not enabled; see [binary scope](science/BINARY_CLASSIFICATION_CONTRACT.md). |
| **CNN** | Convolutional neural network trained on compatible audio-derived tensors; may have per-epoch train/validation loss and device selection. |
| **Random Forest (RF)** | Tabular feature classifier trained on a fixed versioned acoustic-feature schema. Report feature extraction, fitting, validation, feature importance and classifier metrics; not CNN loss curves. |
| **Model** | Immutable published trained family-specific weights/estimator and a portable manifest (ID, human-readable label, Dataset ID, config, schema, metrics, provenance **and versioned settings needed by a later Prediction consumer; structurally reloadable now**). |
| **Model Export Contract** | Versioned manifest, binary artifacts, exact CNN architecture/transforms or RF ordered features, class map, integrity and provenance; structurally checked during Training. |
| **Segment Scoring (future)** | Prediction-only operation on supplied bounded audio intervals using saved Model transforms; **not** a Trainer operation or acceptance test. See `docs/PREDICTION.md`. |
| **Run** | Persisted scientific execution of either Dataset Build or Training with state/progress/logs/input reservations and optional published output pointer. |
| **Active Run** | The single executing/starting/cancelling Run under Application Controller supervision; no queue. |
| **Worker Process** | Separate OS process launched by QProcess using the current application environment; does heavy Dataset Build/Training work, not GUI operations. |
| **Application Settings** | Machine-local UI preferences and Collection path bindings; can relink a moved Collection; never embedded as absolute paths in portable manifests. |
| **Artifact** | Published immutable Dataset or Model, distinguishable from user-owned input WAVs, mutable cache and Run State. |
| **Staging / Publication** | Write and verify on destination filesystem under a private temporary path, then atomically rename to a previously absent artifact directory; failed staging is not navigable. |
| **Provenance** | Resolvable Collection/source/positive/Dataset/Model identity, configuration and input fingerprints, recorded without machine-absolute paths in portable artifacts. |
| **`alpaca-pipelines`** | External scientific reference implementation and possible source of selectively reused audio, training and RF feature logic; its historical directories/formats are not automatically Trainer contracts. |
| **`TD-*` / `UT-*` / `IT-*`** | Test-data equivalence class / indexed pure unit behavior / indexed actual integration behavior. An ID in a document does not prove a test passed. |

## Terminology rules

- Say **Positive Example** for the input WAV, **Annotation** for its source-relative label, and **target Snippet** only for the Dataset's materialized audio.
- An unlabeled region is *eligible for candidate noise* only if mining constraints allow it; avoid “verified negative”.
- Say **Collection Scan**, not Run, for folder reading. Say **Dataset Build Run** or **Training Run** only for actual scientific work.
- Use `start_ms`/`end_ms` for integer millisecond boundaries; sample/frame indexing is internal. Define conversions/rounding at the audio boundary.
- A manifest should use `family: cnn` or `family: random_forest` consistently; user-facing names can be CNN / Random Forest.
- When a new noun is truly required, add it here and update the producing/consuming docs, data schema and tests in the same change. Avoid speculative synonyms.

## Training configuration terms

- **Training Configuration:** all resolved, typed scientific settings for one model family, including transforms, optimizer/forest features, execution resources and validation rules; defined in [configuration catalog](science/TRAINING_CONFIGURATION_CATALOG.md).
- **Saved Configuration / Training Preset:** user-named reusable **mutable** family-specific settings stored in OS application data, independent of any Dataset or Collection; [preset rules](science/TRAINING_PRESETS.md). Not a Model or a Run.
- **Training Draft:** unsaved editable form values; loading or editing a preset does not update an existing Run.
- **Resolved Run Configuration:** immutable, validated snapshot of all actual training parameters at Worker start; source of future-compatible Model metadata.
- **Field Help / Wiki Anchor:** focused `alp-ui.HelpHint` plus an exact user-facing [Training Wiki](wiki/TRAINING_CONFIGURATION.md) entry per configuration field.
