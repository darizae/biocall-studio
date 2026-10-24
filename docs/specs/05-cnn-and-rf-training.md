# 05 — CNN and Random Forest Training, Models

## User behavior

Choose a published immutable Dataset and either **CNN** or **Random Forest** in one Train Model screen. Provide **family-specific** controls, show real progress/validation data, and after completion navigate to a Model detail page with readable label, stable ID, family, Dataset, resolved parameters, metrics and provenance. Reopen Models independently from their immutable directories. Do **not** expose inference/prediction as a target workflow.

## Implement in order

1. Resolve the intended **sibling** `../alpaca-pipelines` (or explicitly confirmed `../alpaca-pipelines`) using [`docs/agent/SOURCE_MAP.md`](../agent/SOURCE_MAP.md). Inspect **actual** present paths for audio input/channel/sample conversion, CNN trainer/checkpoint and RF features/ordered schema/estimator serialization; do not assume illustrative historical file paths exist. Pin source SHA, integration API/adapter and test scientific assumptions; never treat the reference pipeline Dataset format as identical to Trainer Snippets without proof.
2. Make Dataset reader validate complete Snippet/Split manifests, existence, labels and grouping. Define one family-neutral immutable training input handoff plus family-specific transform contracts. Train only from `train`, validate on `val`; reject missing/incompatible input up front.
3. CNN: bounded CPU baseline, optional actual GPU device, epoch count, batch size, learning rate, seed, architecture/preprocessing version; persist real checkpoint, loader metadata and **measured** per-epoch train/val losses.
4. RF: fixed ordered, versioned acoustic-feature vector derived from the Dataset's WAV Snippets; tree count, minimum leaf count, maximum depth, classification threshold, seed. Persist estimator, feature schema/config, real validation metrics and feature importances where supported. Do not simulate CNN-style epoch loss for RF. Avoid loading untrusted pickles/joblib without explicit trust boundary; Models produced locally are trusted only according to app policy.
5. Both family outputs use existing Run Worker/atomic publication and a portable `model.json` schema: `model_id`, label, `family` (`cnn`/`random_forest`), Dataset ID/portable relative refs, transformation schema/version, seed, exact resolved settings, class mapping, metrics (nullable undefined entries + reasons), model files/checksums and tool provenance. Test **actual reload** by the application's loader.
6. Prevent leaking private absolute paths, undefined metrics and fabricated accuracies. Undefined ROC-AUC when `val` has only one class is reported as unavailable, never `0.0` by fiat.

## Prototype-equivalent visual evidence with new `alp-ui` Plot

Use sibling library public `Plot(kind="line")` and `.setLines()` for **measured finite** CNN epoch train/validation loss (x = epoch, y = loss) and `Plot(kind="bar")`/`.setBars()` for RF feature importances in actual feature-schema order. Neither Plot computes metrics nor performs training. Show an accessible numeric summary/DataTable of exact values alongside each plot; represent missing/undefined/NaN/infinite values with explicit text and no fabricated bars or zeroes. RF progress is fit/validate stages, **not** CNN-style epochs. Compose `HelpHint` beside difficult hyperparameters, use `NumberInput` and `SelectInput` for validated family-specific settings. Compare `rf-config-preview.png`, Training and `model-preview.png` with real Qt screenshots and Showcase styling. Assert `IT-TRAIN-005`, `IT-TRAIN-006` with real training outputs; synthetic in-memory plot values may only be used for isolated presentation-component tests.

## Tests / exit

- Unit: `UT-TRAIN-001`…`UT-TRAIN-004` for bounds, ordered feature shape, label metrics and manifest formats (`TD-TRAIN`).
- Integration: `IT-TRAIN-001`…`IT-TRAIN-006`, with **one real published Dataset feeding both** real CPU CNN and real RF via QProcess; verify checkpoints/estimator reload, family-specific progress/metrics, error no-publish behavior and Model detail after restart. No mocked fit/Model artifact qualifies as these cases.
