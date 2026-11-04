# Training configuration catalog — Trainer specification (Spec 05)

**Authority:** this is the field-level UI + validation + serialization crosswalk for training. Read with [training Wiki](../wiki/TRAINING_CONFIGURATION.md), [saved presets](TRAINING_PRESETS.md), [Model export](MODEL_EXPORT_CONTRACT.md), and [native UI evidence](../design/evidence/st-11-native/README.md) and [owner UI feedback](../specs/manual_revision_specs/UI-pass-revision-spec.md). **No inference is in scope.** The 2022 `../TRAINING_REFERENCE/config` is a semantic reference, **not an executable dependency**, command builder or source of filesystem paths. `../alpaca-pipelines` typed specs and the **actual installed** `../bioacoustics-dl-toolbox` APIs govern supported algorithm behavior. Check local versions/SHAs before implementation; no unverified switch may claim to work.

**Binary-only rule:** The Trainer supports precisely one mutually exclusive `target`/`noise` label per Snippet, and `classifier.num_classes = 2` is a fixed derived setting. **Do not expose multi-label, multi-class, per-class heads, selectable positive labels, or editable class counts** even if the toolbox accepts them; see [binary classification contract](BINARY_CLASSIFICATION_CONTRACT.md).

**Visibility rule:** The [machine-readable roster](TRAINING_CONFIGURATION_FIELDS.json) has `ui_tier=primary|details` on every entry. **Primary (shown immediately):** Common `run_name`; CNN `sequence_length_ms`, `training.max_epochs`, `training.batch_size`, `training.learning_rate`, `device`; RF `n_estimators`, `max_depth`, `min_samples_leaf`. **All other entries** (including execution and RF `rf_threshold`) are only under the collapsed **More settings** disclosure, in family-specific groups. The default view must not expose all entries or grow into an expert dashboard. The detailed extension is compact and expandable in place, not a new route or a generic 67-row form. Read-only/derived fields live in More settings and show their computed values.

**Recommendation contract:** Every editable entry has a typed `recommended_starting_value` and `recommendation_basis` in the roster. Initially the suggested value is **the catalog baseline verified against the pinned scientific library** (`backend_default_baseline`); it is a reproducible starting point, not proof of scientific superiority. A dynamically derived entry has `recommended_starting_value=null` and basis `derived_not_user_selectable`; render “Automatically determined”. In **More settings**, show the current value, reset/default and applicable recommendation without duplicating labels or adding fine-print captions; the Wiki owns supporting explanation. Validate backend, Dataset and available hardware; where that baseline is unsuitable, show a blocking validation error and a context-aware explanation, **not a silent override**. Future empirically supported suggestions require a new evidence-backed basis and synchronized updates to catalog, Wiki, typed defaults and tests. Reset-to-default is explicit and never secretly applied on collapsing, preset load or a family switch.

**Absolute rule:** Every user-editable training setting has a visible label, default/current value, accessible `alp-ui.HelpHint` with a short context explanation, and a deep link to its stable training-Wiki anchor. Each Wiki entry explains intuition, units, effect, constraints, applicability and recorded output semantics; a generic tooltip on the form section is insufficient. Presets, the frozen Run config, and the Model manifest use **canonical typed keys** (not legacy command-line names). Every field gets explicit validation, including interactions with other values; never silently clamp invalid inputs when starting.

**Layout:** keep Train’s existing Dataset → Model configuration → Start Training hierarchy and the small high-salience control roster above. Add `Saved configurations` in the same configuration panel and a compact collapsed **More settings** area containing collapsible sections (Spectrogram, Normalization, Augmentation, Architecture, Optimization for CNN; Forest, Acoustic Features for RF). No separate training route, generic property grid, reference-code path controls, or visual redesign. **Do not modify the bundled interactive prototype** to represent these new settings. Use the current Train interface and its native tests for advanced CNN, RF and saved preset states. The HTML prototype simulates basic training only. `../alp-ui` Showcase dictates native Qt presentation.

## Common training controls

| Canonical UI key | Control | Default | Tooltip (short) / purpose | Wiki |
|---|---|---|---|---|
| `run_name` | text | `` | Optional descriptive label for this training Run; the Model receives its own name after training. | [Details](../wiki/TRAINING_CONFIGURATION.md#run-name) |
| `logging_level` | select | `info` | Choose standard or detailed Worker logs; debug does not change scientific results. | [Details](../wiki/TRAINING_CONFIGURATION.md#logging-level) |
| `spectrogram_cache` | bool | `False` | Reuse generated training spectrograms when compatible. Cache location is managed by the Trainer; it never takes a freeform path. | [Details](../wiki/TRAINING_CONFIGURATION.md#spectrogram-cache) |

## CNN controls

| Group | Canonical key | UI control | Default | Field-level tooltip | Wiki |
|---|---|---|---|---|---|
| Basics | `sequence_length_ms` | int | `400` | Fixed audio window duration used for training; choose enough temporal context for the target vocalization. | [Details](../wiki/TRAINING_CONFIGURATION.md#sequence-length-ms) |
| Basics | `training.max_epochs` | int | `500` | Maximum passes through the training Split; early stopping may finish earlier. | [Details](../wiki/TRAINING_CONFIGURATION.md#training-max-epochs) |
| Basics | `training.batch_size` | int | `16` | Training Snippets per gradient update. Larger values use more memory. | [Details](../wiki/TRAINING_CONFIGURATION.md#training-batch-size) |
| Basics | `training.learning_rate` | float | `1e-05` | Step size of the optimizer. Changes the stability and speed of learning. | [Details](../wiki/TRAINING_CONFIGURATION.md#training-learning-rate) |
| Basics | `device` | select | `auto` | Run on CPU or a tested accelerator; unavailable CUDA/MPS selections must be disabled. | [Details](../wiki/TRAINING_CONFIGURATION.md#device) |
| Spectrogram | `spectrogram.sample_rate` | int | `44100` | Sample rate to which audio is converted before spectrogram construction. | [Details](../wiki/TRAINING_CONFIGURATION.md#spectrogram-sample-rate) |
| Spectrogram | `spectrogram.preemphasis` | float | `0.98` | High-frequency emphasis before spectral analysis; preserve in the exported Model. | [Details](../wiki/TRAINING_CONFIGURATION.md#spectrogram-preemphasis) |
| Spectrogram | `spectrogram.n_fft` | int | `4096` | Transform window length. Larger windows improve frequency resolution but reduce temporal resolution. | [Details](../wiki/TRAINING_CONFIGURATION.md#spectrogram-n-fft) |
| Spectrogram | `spectrogram.hop_length` | int | `441` | Audio samples between adjacent spectrogram frames; controls time resolution. | [Details](../wiki/TRAINING_CONFIGURATION.md#spectrogram-hop-length) |
| Spectrogram | `spectrogram.n_freq_bins` | int | `256` | Number of frequency bins after frequency compression. | [Details](../wiki/TRAINING_CONFIGURATION.md#spectrogram-n-freq-bins) |
| Spectrogram | `spectrogram.f_min` | int | `500` | Lowest spectrogram frequency retained for the classifier. | [Details](../wiki/TRAINING_CONFIGURATION.md#spectrogram-f-min) |
| Spectrogram | `spectrogram.f_max` | int | `10000` | Highest spectrogram frequency retained; cannot exceed Nyquist frequency. | [Details](../wiki/TRAINING_CONFIGURATION.md#spectrogram-f-max) |
| Spectrogram | `spectrogram.freq_compression` | select | `linear` | Frequency-axis representation: linear, mel, or MFCC; validate compatibility with chosen encoder. | [Details](../wiki/TRAINING_CONFIGURATION.md#spectrogram-freq-compression) |
| Spectrogram | `spectrogram.min_level_db` | float | `-100` | Lowest decibel level used to scale or clip the spectrogram representation. | [Details](../wiki/TRAINING_CONFIGURATION.md#spectrogram-min-level-db) |
| Spectrogram | `spectrogram.ref_level_db` | float | `20` | Reference level for decibel scaling, separate from the normalization mode. | [Details](../wiki/TRAINING_CONFIGURATION.md#spectrogram-ref-level-db) |
| Normalization | `normalization.mode` | select | `db` | Choose dB-based or min–max normalization; Detect uses the exact saved mode. | [Details](../wiki/TRAINING_CONFIGURATION.md#normalization-mode) |
| Normalization | `normalization.min_level_db` | float | `-100` | Minimum dB applied when normalizing the spectrogram. | [Details](../wiki/TRAINING_CONFIGURATION.md#normalization-min-level-db) |
| Normalization | `normalization.ref_level_db` | float | `20` | Reference dB applied by the selected normalization procedure. | [Details](../wiki/TRAINING_CONFIGURATION.md#normalization-ref-level-db) |
| Augmentation | `augmentation.enabled` | bool | `False` | Apply randomized training-only transformations; never apply them to validation. | [Details](../wiki/TRAINING_CONFIGURATION.md#augmentation-enabled) |
| Augmentation | `augmentation.amplitude_increase_db` | int | `3` | Largest randomized loudness increase for training examples. | [Details](../wiki/TRAINING_CONFIGURATION.md#augmentation-amplitude-increase-db) |
| Augmentation | `augmentation.amplitude_decrease_db` | int | `-6` | Largest randomized loudness decrease, expressed as a negative dB value. | [Details](../wiki/TRAINING_CONFIGURATION.md#augmentation-amplitude-decrease-db) |
| Augmentation | `augmentation.time_stretch_from` | float | `0.5` | Lower bound for training-time playback-speed/time stretching. | [Details](../wiki/TRAINING_CONFIGURATION.md#augmentation-time-stretch-from) |
| Augmentation | `augmentation.time_stretch_to` | float | `2.0` | Upper bound for training-time playback-speed/time stretching. | [Details](../wiki/TRAINING_CONFIGURATION.md#augmentation-time-stretch-to) |
| Augmentation | `augmentation.pitch_shift_from` | float | `0.5` | Lower bound for training-only pitch transformation; verify toolbox units. | [Details](../wiki/TRAINING_CONFIGURATION.md#augmentation-pitch-shift-from) |
| Augmentation | `augmentation.pitch_shift_to` | float | `1.5` | Upper bound for training-only pitch transformation; verify toolbox units. | [Details](../wiki/TRAINING_CONFIGURATION.md#augmentation-pitch-shift-to) |
| Augmentation | `augmentation.noise_min_snr` | int | `12` | One bound of noise-mixing signal-to-noise range. Confirm library direction and ordering before labeling min/max. | [Details](../wiki/TRAINING_CONFIGURATION.md#augmentation-noise-min-snr) |
| Augmentation | `augmentation.noise_max_snr` | int | `-3` | Other bound of the noise-mixing range. Do not silently reorder the upstream defaults. | [Details](../wiki/TRAINING_CONFIGURATION.md#augmentation-noise-max-snr) |
| Augmentation | `augmentation.noise_source` | select | `none` | Choose a vetted, readable Collection-local noise source. The user does not type a directory path. | [Details](../wiki/TRAINING_CONFIGURATION.md#augmentation-noise-source) |
| Architecture | `encoder.resnet_size` | select | `18` | Residual network depth; larger models usually need more memory and training time. | [Details](../wiki/TRAINING_CONFIGURATION.md#encoder-resnet-size) |
| Architecture | `encoder.conv_kernel_size` | select | `7` | Size of the initial CNN convolution window. | [Details](../wiki/TRAINING_CONFIGURATION.md#encoder-conv-kernel-size) |
| Architecture | `encoder.max_pool` | select | `1` | 0: no pooling with stride; 1: pooling; 2: no pooling and no added stride. Confirm exact encoder behavior. | [Details](../wiki/TRAINING_CONFIGURATION.md#encoder-max-pool) |
| Architecture | `encoder.input_channels` | readonly (derived) | `1` | Derived from the approved mono spectrogram channel policy; not an independent freeform setting. | [Details](../wiki/TRAINING_CONFIGURATION.md#encoder-input-channels) |
| Architecture | `classifier.pooling` | select | `avg` | Aggregate encoder features with average or maximum pooling. | [Details](../wiki/TRAINING_CONFIGURATION.md#classifier-pooling) |
| Architecture | `classifier.num_classes` | readonly (derived) | `2` | Derived from the immutable binary target/noise Dataset; cannot disagree with its class mapping. | [Details](../wiki/TRAINING_CONFIGURATION.md#classifier-num-classes) |
| Architecture | `classifier.input_channels` | readonly (derived) | `derived` | Computed from the selected encoder output; cannot be independently edited. | [Details](../wiki/TRAINING_CONFIGURATION.md#classifier-input-channels) |
| Optimization | `training.num_workers` | int | `4` | Parallel audio loading workers. Zero uses the main process; native packaging may impose a lower limit. | [Details](../wiki/TRAINING_CONFIGURATION.md#training-num-workers) |
| Optimization | `training.beta1` | float | `0.5` | Exponential decay for Adam optimizer’s first-moment estimate. | [Details](../wiki/TRAINING_CONFIGURATION.md#training-beta1) |
| Optimization | `training.lr_patience_epochs` | int | `8` | Validation patience before reducing learning rate; confirm effective evaluation cadence. | [Details](../wiki/TRAINING_CONFIGURATION.md#training-lr-patience-epochs) |
| Optimization | `training.lr_decay_factor` | float | `0.5` | Multiplicative learning-rate reduction when the plateau scheduler triggers. | [Details](../wiki/TRAINING_CONFIGURATION.md#training-lr-decay-factor) |
| Optimization | `training.early_stopping_patience_epochs` | int | `20` | Stop if the monitored validation metric fails to improve for this many effective epochs. | [Details](../wiki/TRAINING_CONFIGURATION.md#training-early-stopping-patience-epochs) |
| Optimization | `training.epochs_per_eval` | int | `2` | Frequency of validation passes during CNN training. | [Details](../wiki/TRAINING_CONFIGURATION.md#training-epochs-per-eval) |
| Optimization | `training.val_metric` | select | `accuracy` | Metric used to select the best checkpoint and control patience. | [Details](../wiki/TRAINING_CONFIGURATION.md#training-val-metric) |
| Optimization | `training.val_metric_mode` | select | `max` | Whether higher or lower validation scores are better; must match chosen metric. | [Details](../wiki/TRAINING_CONFIGURATION.md#training-val-metric-mode) |
| Optimization | `training.pin_memory` | bool | `True` | Optional pinned host memory for faster supported accelerator data transfer. | [Details](../wiki/TRAINING_CONFIGURATION.md#training-pin-memory) |

## RF controls

| Group | Canonical key | UI control | Default | Field-level tooltip | Wiki |
|---|---|---|---|---|---|
| Basics | `n_estimators` | int | `800` | Number of trees in the ensemble. More trees require more CPU/memory. | [Details](../wiki/TRAINING_CONFIGURATION.md#n-estimators) |
| Basics | `min_samples_leaf` | int | `2` | Minimum samples allowed in a terminal leaf; larger values regularize the forest. | [Details](../wiki/TRAINING_CONFIGURATION.md#min-samples-leaf) |
| Basics | `max_depth` | nullable_int | `null / unlimited` | Maximum tree depth or unlimited. The UI may show unlimited as 0, but serialize as null. | [Details](../wiki/TRAINING_CONFIGURATION.md#max-depth) |
| Basics | `rf_threshold` | float | `0.6` | Threshold for target-class probability in held-out validation; saved as policy, not inference. | [Details](../wiki/TRAINING_CONFIGURATION.md#rf-threshold) |
| Forest | `random_state` | int | `1337` | Controls reproducible tree bootstrapping and feature subsampling. | [Details](../wiki/TRAINING_CONFIGURATION.md#random-state) |
| Forest | `min_samples_split` | int | `2` | Minimum examples required before an internal tree node can split. | [Details](../wiki/TRAINING_CONFIGURATION.md#min-samples-split) |
| Forest | `max_features` | select | `sqrt` | Number or proportion of candidate acoustic features considered at each split. Advanced numeric modes require matching validation. | [Details](../wiki/TRAINING_CONFIGURATION.md#max-features) |
| Forest | `class_weight` | select | `balanced` | Compensates for target/noise imbalance during tree fitting. | [Details](../wiki/TRAINING_CONFIGURATION.md#class-weight) |
| Forest | `n_jobs` | int | `-1` | Number of CPU processes/threads used by the forest; −1 requests all available CPUs, subject to safe cap. | [Details](../wiki/TRAINING_CONFIGURATION.md#n-jobs) |
| Features | `feature_family` | readonly (derived) | `robust-mfcc` | Fixed robust acoustic statistics plus MFCC summaries. Names and ordering are part of Model contract. | [Details](../wiki/TRAINING_CONFIGURATION.md#feature-family) |
| Features | `feature_config.sample_rate_hz` | int | `48000` | Resample each RF segment to this sample rate before extraction. | [Details](../wiki/TRAINING_CONFIGURATION.md#feature-config-sample-rate-hz) |
| Features | `feature_config.min_duration_s` | float | `0.5` | Short segments must be padded or explicitly rejected. | [Details](../wiki/TRAINING_CONFIGURATION.md#feature-config-min-duration-s) |
| Features | `feature_config.pad_short_segments` | bool | `True` | Zero-pad shorter segments to the required minimum duration. | [Details](../wiki/TRAINING_CONFIGURATION.md#feature-config-pad-short-segments) |
| Features | `feature_config.pad_mode` | readonly (derived) | `constant` | Current feature extractor uses constant padding; preserve the algorithm choice in export. | [Details](../wiki/TRAINING_CONFIGURATION.md#feature-config-pad-mode) |
| Features | `feature_config.n_fft` | int | `4096` | FFT window size for robust and MFCC statistics. | [Details](../wiki/TRAINING_CONFIGURATION.md#feature-config-n-fft) |
| Features | `feature_config.hop_length` | int | `2048` | Hop between RF feature frames. | [Details](../wiki/TRAINING_CONFIGURATION.md#feature-config-hop-length) |
| Features | `feature_config.n_mfcc` | int | `13` | Number of mel-frequency cepstral coefficients summarized. | [Details](../wiki/TRAINING_CONFIGURATION.md#feature-config-n-mfcc) |
| Features | `feature_config.include_deltas` | bool | `True` | Include first/second temporal MFCC differences in the feature vector. | [Details](../wiki/TRAINING_CONFIGURATION.md#feature-config-include-deltas) |
| Features | `feature_config.fmin_hz` | float | `50.0` | Lower analysis band bound for robust acoustic descriptors. | [Details](../wiki/TRAINING_CONFIGURATION.md#feature-config-fmin-hz) |
| Features | `feature_config.fmax_hz` | float | `4500.0` | Upper band bound for robust descriptors; ensure compatible with Nyquist. | [Details](../wiki/TRAINING_CONFIGURATION.md#feature-config-fmax-hz) |

## Complete legacy reference accounting

The following mapping is exhaustive for `TRAINING_REFERENCE/config`. Path placement and command execution **always remain the Trainer's responsibility**. Missing or inaccessible reference checkout is not permission to omit supported fields: this catalog is checked in.

| Legacy setting | New UI/config responsibility | Disposition |
|---|---|---|
| `src_dir` | Existing Trainer-owned Collection/Run/artifact layout | Intentionally excluded: never add a path field |
| `data_dir` | Existing Trainer-owned Collection/Run/artifact layout | Intentionally excluded: never add a path field |
| `model_dir` | Existing Trainer-owned Collection/Run/artifact layout | Intentionally excluded: never add a path field |
| `checkpoint_dir` | Existing Trainer-owned Collection/Run/artifact layout | Intentionally excluded: never add a path field |
| `log_dir` | Existing Trainer-owned Collection/Run/artifact layout | Intentionally excluded: never add a path field |
| `summary_dir` | Existing Trainer-owned Collection/Run/artifact layout | Intentionally excluded: never add a path field |
| `debug` | `logging_level` | editable |
| `cache_dir` | `spectrogram_cache` | capability; path excluded |
| `noise_dir` | `augmentation.noise_source` | selected source; path excluded |
| `start_from_scratch` | `fresh immutable Run` | automatic, no resume |
| `max_train_epochs` | `training.max_epochs` | editable |
| `jit_save` | `checkpoint format` | not supported: native checkpoint only; no fake control |
| `epochs_per_eval` | `training.epochs_per_eval` | editable |
| `batch_size` | `training.batch_size` | editable |
| `num_workers` | `training.num_workers` | editable |
| `no_cuda` | `device` | editable using detected CPU/CUDA/MPS |
| `lr` | `training.learning_rate` | editable |
| `beta1` | `training.beta1` | editable |
| `lr_patience_epochs` | `training.lr_patience_epochs` | editable |
| `lr_decay_factor` | `training.lr_decay_factor` | editable |
| `early_stopping_patience_epochs` | `training.early_stopping_patience_epochs` | editable |
| `filter_broken_audio` | `preflight audio validation` | automatically fail/exclude per safe Dataset rules; do not move original audio |
| `sequence_len` | `sequence_length_ms` | editable |
| `freq_compression` | `spectrogram.freq_compression` | editable |
| `n_freq_bins` | `spectrogram.n_freq_bins` | editable |
| `n_fft` | `spectrogram.n_fft` | editable |
| `hop_length` | `spectrogram.hop_length` | editable |
| `sr` | `spectrogram.sample_rate` | editable |
| `augmentation` | `augmentation.enabled` | editable |
| `resnet` | `encoder.resnet_size` | editable |
| `conv_kernel_size` | `encoder.conv_kernel_size` | editable |
| `num_classes` | `classifier.num_classes` | derived from Dataset; not editable |
| `max_pool` | `encoder.max_pool` | editable |
| `min_max_norm` | `normalization.mode` | editable |
| `fmin` | `spectrogram.f_min` | editable |
| `fmax` | `spectrogram.f_max` | editable |

## Typed behavior, applicability and validation

- Family switch changes only which family-specific section is visible; preserve *separate drafts* per family and do not carry `cnn` values into the RF schema. Switching Dataset must **not** change a saved preset or silently recalculate arbitrary paths. Training chooses a complete Dataset snapshot and creates a **frozen resolved Run spec** at Run start.
- Validation on field edit and at launch: finite numbers, positive epochs/batch/workers/FFT/hop, compatible FFT/hop and spectrogram dimensions, `0 <= f_min < f_max <= sample_rate/2`, min/max bounds, unit sanity, class mapping, valid CPU resource budget, compatible augmentation ranges, supported optimizer/validation metric directions and short-snippet policy. **Do not copy invalid defaults from old scripts or silently normalize legacy settings.** `max_depth=0` in prototype is serialized as `null` (unlimited), not an invalid estimator parameter.
- CNN execution configuration resolves CPU/CUDA/MPS to actual tested runtime: `no_cuda` is represented by explicit device selection, not independently editable. Verify MPS path against current toolbox: disable if unsupported. Unavailable library capabilities must be visibly disabled with correct reason, never silently accepted. Nonnegative data-loader-worker counts; on Windows use a tested safe default.
- Noise augmentation uses an explicit user-selected **Collection-scoped set of approved noise Snippets**, not a raw `noise_dir` path and not automatically mined-negative training labels. If upstream toolbox only accepts file references, adapt trusted resolved Dataset/Collection references internally. Do not move source audio. If not safely supported, gate that selectable option as disabled with a Wiki reason and an acceptance blocker for full reference parity; do not pretend it has effect.
- `jit_save` has **no demonstrated equivalent** in the inspected `alpaca-pipelines` typed TrainingRunSpec. The Trainer currently exports its structurally validated checkpoint format; document JIT as unsupported and not a fabricated checkbox. `start_from_scratch` is enforced by immutable fresh Runs; resume must be separately specified. `filter_broken_audio` must not move source files or bypass explicit Collection/Dataset validity checks. `num_classes`/encoder channels are derived; they are displayed for transparency but cannot be altered to contradict the binary Dataset.
- RF `max_features` upstream accepts string/numeric/None; represent numeric and `null` modes as typed advanced control (not `str` only). Upstream can also take custom class-weight dictionaries; expose safe typed values or a validated structured editor, and include tests for serialization/roundtrip. `rf_threshold` affects training validation and recorded policy only; no consumer inference entrypoint.
- Read-only/derived fields show a clear explanation and wiki link, but do not imply they can be edited. Record *all resolved* options, not just user-changed ones, in the Run and Model manifests (training-only options may be provenance rather than future preprocessing requirements). An unsupported setting must be identified in an auditable implementation checklist before Spec 05 can be signed off.

## Spec 05 test obligations

- Unit: `UT-TRAIN-007` field catalog coverage, type/units/defaults/tooltips/wiki anchors and family segregation; `UT-TRAIN-008` cross-field and derived/inapplicable validation, capability gating and reference coverage. Preset cases in [preset contract](TRAINING_PRESETS.md).
- Native integration: `IT-TRAIN-010` all field groups, `HelpHint`/Wiki focus and keyboard lookup; `IT-TRAIN-011` enter, reject and resolve invalid config, plus absence of path fields; prototype+Showcase screenshots. `IT-TRAIN-012` serialized worker inputs and resolved Model config reproduce current form; disabled unsupported settings never alter training.
- Real scientific smoke: `IT-TRAIN-001/002/008` exercise representative **nondefault** spectrogram, normalization, augmentation (where safely supported), architecture/optimizer and RF feature/forest settings and compare recorded values to execution. Tests never substitute fake training metrics or future prediction.
