# ST-09 native RF refinement evidence

Captured on macOS 26.0.1 with the Cocoa Qt platform, Python 3.12.7, PySide6/Qt
6.11.2, `alp-ui` 0.1.0a0, scikit-learn 1.7.2 and the project `.venv`. Images are
Retina captures (2× logical pixels) from genuine Train-produced CNN and Random
Forest Models plus generated PCM WAV recordings. They are not browser or mocked
prototype output.

## Scientific source inspection

- Direct runtime toolbox: `../bioacoustics-dl-toolbox` at
  `e478ca5156a5d1018d0a7a61486bc85fe7c1e92d`; installed import resolved to that
  checkout. Inspected `audio/io.py` and `rf/features.py`.
- RF reference pipeline: `../alpaca-pipelines` at
  `91af5287dc18313f88902dc9696e8756274736b3`; inspected
  `rf/audio_preprocess.py`, `rf/audio_features/{robust_features,mfcc_features}.py`
  and `rf/config.py`. It remained reference-only and was not imported by the app.
- Installed `alp-ui` resolved to `../alp-ui` at
  `5bb61e3a4c4bd7104ade4375cc32082ea44e1d14` through its public components API.

The executed contract uses toolbox mono averaging, librosa `soxr_hq` resampling
with fixed unscaled output, source-time slicing after full-recording resampling,
the Model's centered-zero-pad or explicit-reject short policy, toolbox
robust+MFCC extraction, the exact persisted canonical feature order, finite
`float64` vectors, and `estimator.classes_` to locate integer target class `1`.
[`rf-reference.json`](rf-reference.json) records the actual ordered 35-value
feature vector and probability comparison from a real 16 kHz WAV assessed by an
8 kHz RF Model: reference and persisted child target probability are both
`0.5833333333333334`, class order is `[0, 1]`, target column is `1`, and the saved
threshold is `0.55`.

## Native views

- `results-original-{normal,compact}.png`: selectable original Result and lineage.
- `results-refined-{normal,compact}.png`: independently selectable child Result.
- `results-{original,refined}-intervals-{normal,compact}.png`: stable source-time
  intervals; the refined table adds researcher-facing Accepted/Rejected/Could not
  assess while retaining the CNN detection score.
- `results-{original,refined}-detail-{normal,compact}.png`: the optional RF Model
  action and disabled re-refinement state on a child Result.
- `results-refined-unscored-normal.png`: a genuine short source interval reported
  as Could not assess, not silently rejected.

The RF folder visible in screenshots is a pytest-owned temporary Train Collection.
Absolute paths are selection UI state only; immutable Results contain relative
recording keys and checksums, and the tests assert that neither source-root paths
nor source mutations enter publication.

## Executed checks

```text
python -m pytest tests/unit/test_detect_rf_refinement.py
3 passed

python -m pytest tests/integration/test_detect_detection.py \
  -k 'real_rf_reference_probability or rf_wrong_model_unscored'
2 passed

python -m pytest tests/unit -q
96 passed

python -m pytest tests/integration -q
98 passed, 1 soak test deselected

python -m ruff check .
passed

python scripts/audit_test_ids.py
passed
```

The ordinary suites emit one upstream PyTorch `TypedStorage` deprecation warning.
The separately initiated ≥600-second soak was not run as part of this stage commit.

`IT-DET-017` compares real feature values and `predict_proba` output independently,
reopens original and derived publications, switches both native views, verifies
independent selections, and freezes the versioned ST-10 lineage handoff.
`IT-DET-018` covers wrong feature order, explicit short-candidate unscored status,
real Worker cancellation/crash, missing and changed source fingerprints, publication
collision, staging cleanup and byte-identical parent retention.
