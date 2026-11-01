# ST-07 → ST-08 immutable Detection Result handoff

## Verified inference boundary

ST-07 consumes the installed public
`bioacoustics_dl_toolbox.prediction.predict_windows` API from toolbox revision
`e478ca5156a5d1018d0a7a61486bc85fe7c1e92d` (`bioacoustics-dl-toolbox` 0.2.0). The
active environment imports it from the clean sibling checkout at
`/Users/danie/repos/bioacoustics-dl-toolbox/src`. The inspected source was
`prediction/predictor.py` together with the audio dataset, preprocessing, I/O,
checkpoint, classifier and predictor tests at that revision. No toolbox change was needed.

The upstream call owns WAV decode, channel averaging, Kaiser-best resampling, shared deterministic
spectrogram/normalization, fixed-shape final-window padding, checkpoint reconstruction and CPU
forward inference. ST-07 passes the accepted Model artifact, an explicit hop, batch size and CPU
device. It then requires ordered binary outputs `noise=0,target=1`, finite softmax values summing
to one, and exact ordered half-open model-sample intervals. Scores have the frozen meaning
`binary_softmax_target_output_index_1; not_a_calibrated_probability`.

`DetectionSettings` contract `cnn-first-pass-v1` freezes minimum score, overlap percentage,
source-time combination gap and batch size. The native defaults are 0.50, 0% overlap, no
cross-gap combination and batch size 16. The 0.50 default is the binary softmax decision boundary,
not a claim of calibrated certainty. Hop samples use nearest-integer half-up rounding on
`window_samples × (100-overlap)/100`; threshold comparison is inclusive.

## Frozen `DetectionResult` v1

`DetectionResult` is a frozen, self-digesting metadata-only document. It contains no absolute
source path or audio bytes. Its top-level contract binds:

- Result, Run, request, Detect Collection and binding-revision identities;
- Inventory ID/digest and Model ID, ModelSnapshot ID/digest, manifest checksum and artifact
  checksum;
- exact settings, resolved window/hop/model sample rate, backend distribution/version/revision,
  UTC completion time, completeness and aggregate file/candidate counts; and
- sorted `RecordingOutcome` entries for every frozen included recording.

Each recording entry retains its portable key, deterministic recording reference, source checksum,
original sample rate, original frame count, channel count and explicit `succeeded` or `failed`
status. A successful entry may contain zero candidates. A failed entry contains no candidates and
one allowlisted code: `audio_decode_failed`, `inference_failed` or `unsupported_output`. A Result
is `partial` when at least one file failed and requires at least one successful file; an all-file
failure fails the Run with no Result.

Each `CandidateInterval` has a deterministic ID, parent recording reference, exact half-open
`[start_frame,end_frame)` interval in the original recording, integer nanosecond timestamps,
maximum target score and contributing-window count. Resampled starts map with floor, ends with
ceil, both clamp to the original frame count, and nanoseconds use nearest-integer half-up rounding.
Candidates are sorted, non-overlapping after merge and bounded by the original source frame count.
ST-08 must project these facts without recomputing time from float seconds or decoding audio as a
substitute for stored provenance.

## Run, failure and publication semantics

The scientific QProcess Worker reopens the exact ST-04 Inventory/ST-05 Model handoff and rechecks
each source immediately before use and again after inference. It rechecks the Model before and
after file processing. A changed source or Model is a Run-level `input_changed` or `model_changed`
failure and never becomes a zero-candidate outcome. Decode/inference errors remain per-file
outcomes when another recording succeeds.

Only a fully validated Result is staged. It is atomically renamed without overwrite to
`detect/v1/collections/<collection_id>/results/<result_id>/` as exactly `result.json` and
`publication.json`, then bound by the ST-06 outer receipt. Completion is accepted only after the
supervisor independently reopens receipt, publication checksums and the complete Result schema.
Cancellation, owner loss, process crash, stale inputs, destination collision or receipt collision
cannot publish a new committed Result; staging is removed. Source WAV and Train-owned bytes remain
unchanged.

## ST-08 consumer boundary

ST-08 owns Result browsing only. It should load through
`DetectRunRepository.load_detection_result(record)`, preserve `result_id`/`result_digest` in every
view selection, show zero-candidate success separately from failed recordings, expose partial
completeness and stored provenance, and never mutate or rewrite the Result. ST-08 does not rerun
CNN inference, change candidate boundaries, infer missing source as zero, or add waveform/playback
behavior outside its own specification.

Indexed evidence is `UT-DET-013`–`015` and `IT-DET-012`–`014`. Native Cocoa evidence and the
validation ledger are in `docs/design/evidence/st-07-native/`. Windows-native, installed-app,
ST-08 Result exploration, RF refinement, audio export, cross-workflow end-to-end behavior and the
separately initiated 600-second soak are not claimed by ST-07.
