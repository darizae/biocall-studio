# ST-05 Model intake and native evidence

## Native capture

These six PNGs are genuine visible-window captures from the source application on the native
macOS Cocoa Qt platform. They were captured on 2026-10-28 with macOS 26.6.2, Python 3.12.7,
PySide6/Qt 6.11.2, `alp-ui` 0.1.0a0 from sibling revision
`5bb61e3a4c4bd7104ade4375cc32082ea44e1d14`, and the Alpaca Light theme.

```bash
.venv/bin/python scripts/capture_st05_screenshots.py
```

The capture command builds a real WAV-backed Dataset, trains and publishes genuine tiny CNN and
Random Forest Models, then selects their Train Model directories through the real controller. It
does not inject example Model states or invoke prediction.

| File | Observed state |
|---|---|
| `model-empty-normal.png` | No Model selected; readiness asks for a compatible CNN. |
| `model-loading-normal.png` | Asynchronous manifest, checksum, runtime and structural inspection. |
| `model-compatible-normal.png` | Trusted CNN structure at 1180x790; numerical behavior is explicitly deferred. |
| `model-compatible-compact.png` | The same CNN at 700x780 with Model and Collection cards stacked. |
| `model-incompatible-rf-normal.png` | Trusted RF structure rejected as a primary detector and identified as interval refinement. |
| `model-missing-compact.png` | A previously selected CNN directory moved away; use remains blocked. |

Visual review confirmed the accepted ST-01 `#detect/setup` hierarchy, independently selectable
Model and recordings inputs, keyboard-accessible help and controls, normal/compact reflow, short
actionable states, and no runnable Detect action before ST-07. The UI uses public `alp-ui`
components plus ordinary Qt layout primitives. Windows-native, installed-app and 150% DPI evidence
are not claimed here.

## Source and runtime research ledger

The direct CNN dependency checkout was clean `bioacoustics-dl-toolbox` revision
`e478ca5156a5d1018d0a7a61486bc85fe7c1e92d`, distribution version 0.2.0. The active editable import
resolved to
`/Users/danie/repos/bioacoustics-dl-toolbox/src/bioacoustics_dl_toolbox/__init__.py`.
`IT-DET-006` additionally built its wheel, installed it into an isolated target and inspected both
genuine exports in a fresh process whose import origin was asserted inside that target. The
`alpaca-pipelines` checkout inspected only as an RF reference was revision
`91af5287dc18313f88902dc9696e8756274736b3`; its distribution was not installed. Its internal
`bioacoustics_dl_toolbox` copy was not imported. Intake rejects an import that resolves beneath that
repository or a source tree whose `pyproject.toml` identifies another distribution.

The verified runtime versions were Torch 2.14.1, joblib 1.6.0, scikit-learn 1.9.1, librosa 0.11.0
and resampy 0.4.3. Model manifests must declare exact matching family-relevant versions; a mismatch
is incompatible, not silently migrated.

| Source at the revision above | Observed contract |
|---|---|
| `bioacoustics_dl_toolbox/training/checkpoints.py:load_model` | CNN payload uses `torch.load(..., map_location="cpu", weights_only=True)`; Train then reconstructs the declared architecture and strictly loads both state dictionaries. |
| `bioacoustics_dl_toolbox/audio/io.py:load_audio_file` | SoundFile decodes float32, channel mean produces mono, and rate conversion uses resampy `kaiser_best`. |
| `bioacoustics_dl_toolbox/audio/preprocessing.py:build_feature_preprocessor` and `spectrogram_frames_for_samples` | Pre-emphasis, Hann power STFT with `center=False`, frequency compression, dB or 32-coefficient MFCC representation, then normalization. Fixed-window tail padding is in feature frames; signals shorter than the FFT yield one frame. |
| `bioacoustics_dl_toolbox/prediction/predictor.py:predict_windows` | The shared strided dataset supplies mono/resampling and fixed-frame geometry; a binary model returns two raw logits and categorical probabilities are `softmax(logits, dim=1)`. The persisted order is `noise=0`, `target=1`. |
| `biocall_studio.train/persistence/models.py:structurally_reload_cnn_directory` | Checkpoint fields, architecture, transform config, class mapping, input shape and tensor/head structure must agree with `model.json`. This is structural reload, not prediction parity. |
| `alpaca_pipelines/rf/audio_preprocess.py:prepare_rf_segment` | RF reference behavior is float32 mean-to-mono, librosa resampling, nearest-sample slicing and centered constant-zero padding to the declared minimum duration. |
| `alpaca_pipelines/rf_training/executor.py:_compute_features_for_file` | Robust features are followed by MFCC summary features; non-finite values are rejected and the trained DataFrame column order is persisted. |
| `bioacoustics_dl_toolbox/rf/features.py:raven_robust_features`, `mfcc_summary`, `mfcc_feature_schema` | Train's published RF manifest names the direct toolbox extractor and freezes the exact robust/MFCC configuration and ordered feature schema. |
| `biocall_studio.train/persistence/models.py:structurally_reload_rf_directory` | `joblib.load` runs only after trust, containment, size and SHA-256 checks; the restored object must be a `RandomForestClassifier` whose classes, feature count/order, hyperparameters and importances match the manifest. |
| `alpaca_pipelines/rf/executor.py:apply_rf_filter` | The reference implementation orders values by declared feature names before `predict_proba`, but hard-codes column 1. Detect must instead consume the Model's verified `target_probability_column`. |

The real integration vector has three 16 kHz mono PCM recordings and three WAV-backed positive
segments. It trains a 250 ms, 16 kHz CNN with a 256-sample FFT and 64-sample hop, and an RF extractor
at 8 kHz with 250 ms minimum duration, 256-sample FFT, 64-sample hop and four MFCC coefficients.
`IT-DET-006` proves both genuine Train exports are structurally loadable through the isolated direct
toolbox wheel and that source WAV bytes remain unchanged. `IT-DET-007` denies missing, corrupt,
checksum-swapped, extra-class, feature-order-mismatched, unsupported-runtime, path-escaping and
explicitly untrusted inputs before they can be treated as compatible.

No genuine upstream API or presentation gap was found, so neither upstream repository was changed.

## Frozen `ModelSnapshot` handoff

Schema version 1 is path-free and immutable. The private selection record separately owns the local
absolute Model root. The snapshot freezes Model identity/family/role, manifest and binary SHA-256,
artifact format/size/relative path, exact `noise=0` and `target=1` mapping, positive output index or
RF probability column, channel/rate/window/padding policy, transform order, CNN spectrogram and
normalization values, ordered RF feature schema/config, loader distribution/API/version, source
revision, and exact runtime versions. It records three independent evidence states:

| Family | Role in Detect | Structure | Runtime load | Numerical prediction parity |
|---|---|---|---|---|
| CNN | Primary candidate detection | `passed` | `passed` | `unproven` |
| Random Forest | Candidate interval refinement | `passed` | `passed` | `unproven` |

Snapshots are atomically persisted under app-owned `detect/v1/model-snapshots`; no source path is
written into them. The current manifest and artifact hashes are rechecked before any future Worker
use, and a byte or evidence change requires reselection. RF is therefore trusted for the future
ST-09 refinement role but is deliberately incompatible with ST-05 setup readiness as the only
Model. CNN may make setup inputs ready, but this does not authorize scoring.

Unresolved scientific gates are explicit:

- **ST-07:** establish real-WAV CPU parity for decode/resample/mono, source-sample window boundaries,
  feature-frame geometry, logits, softmax class order and tail behavior. The Trainer export does not
  define a scanning hop, so ST-05 invents neither hop nor threshold.
- **ST-09:** establish real-candidate RF parity for resampling, rounding, centered padding, robust
  and MFCC feature values/order, non-finite handling and the persisted probability column. Column 1
  is not assumed universally.
- **ST-06/07/09:** preserve the frozen snapshot and recheck bytes immediately before Worker use.
  Neither validation metrics nor a saved training threshold proves new-audio calibration; no
  default detection threshold or calibration promise is introduced here.
