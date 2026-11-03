# RV-03 — Exact audio context, spectrogram rendering and playback

> **Status:** Owner-approved planning; not implemented. Begin only after explicit stage authorization and the predecessor's owner gate.

## Strict ownership and exclusions

**Owner:** `review/workflows` source window reader and spectral calculation, a minimal native PySide6 playback/render proof surface, with separate upstream change only for verified reusable toolbox API gaps. **Entry:** approved RV-02. No production gallery, cache quota or storage adapter yet; RV-04/RV-05 own those. Render only *eligible* Result candidates, never raw recording annotation.

## Audio, spectrogram and interaction contract

**Input:** each *eligible* candidate's original WAV window around its original frame interval. Default initial context approximately 2 seconds before/after, clamped to `[0, recording.frame_count]`. Keep original `start_frame/end_frame`, rate and exact displayed time anchors; mark the detected interval on the spectrogram. Adjacent/overlapping candidates may share intermediate source reads/transforms if it improves measured performance, but each remains a distinct label and UI item. Do not accidentally export the *context* audio instead of the detected interval.

**Render:** use reproducible, explicit spectral settings (sample rate/channel handling, window, FFT, hop, frequency range, amplitude scaling, image dimensions, color scale, renderer version). Establish readable defaults with representative normal audible-call WAVs in RV-03; never silently borrow inference-time mel feature preprocessing if it is unsuitable for human inspection. If audio is multichannel, decide/test a display/playback channel policy without modifying stored source. Prefer CPU bounded decoding and small memory windows, not a GPU dependency. A lightweight thumbnail for Gallery and a high-detail view for One by one should share computation where justified and not require 50,000 full-resolution images. Provide distinct presentation resolutions without adding a full-recording timeline.

**Audio:** Play/Pause, basic seeking within the displayed candidate-context clip, explicit Previous/Next, stop/transition on navigation, single active playback and no overlap between rapidly switched items. Play the context clip at natural speed, highlight the detected interval; let users hear the full surrounding signal. Relinking/stale source and unsupported PCM/decoder errors must be visible and actionable; a missing source never implies silence. Audio playback and annotation remain responsive during background generation, eviction or export. Handle device unavailable, stream failure, cancellation, selection change and window closure with real Qt multimedia tests. Native media failures must not mutate labels.

**Playback handoff:** expose a bounded clip/player interface that reacts safely when the selected candidate changes. RV-05—not RV-03—owns Gallery/List/One by one, navigation, keyboard labeling and 50,000-item view virtualization. RV-03 measures real-WAV rendering/playback; RV-05 measures native view latency and memory.

## Acceptance cases (register in existing test indexes during stage TDD)

| ID | Owner | Positive assertions | Negative / non-mutation assertions |
|---|---|---|---|
| `UT-REVW-005` | RV-03 | exact frame clamping/context, start/end marking, duration/time units across rates/channels | underflow/overflow, missing/changed WAV and truncated frames are rejected; no mutated source window/metadata |
| `UT-REVW-006` | RV-03 | deterministic rendering spec, key invalidation by source/settings/version and correct thumbnail/detail identity | nonfinite/unsupported render settings, corrupt/old cache keys rejected; no metadata-as-audio fake success |
| `IT-REVW-004` | RV-03 | real mono/stereo WAV boundary/context PCM reads and spectrogram pixel/frequency/time reference checks | truncated/unsupported/stale WAV fails without silent zeros or source modifications |
| `IT-REVW-005` | RV-03 | actual Qt multimedia play, pause, seek, previous/next and focus under playback in a real event loop | device failure/rapid switching/close stops playback without overlap or a blocking GUI |

**Gate:** Owner reviews real original-WAV spectral screenshots, playback on a native Qt device and measured FFT/encoding/audio performance; no speculative toolbox or `Plot` API.

**Next:** RV-04 may be prepared only after this gate is explicitly approved.
