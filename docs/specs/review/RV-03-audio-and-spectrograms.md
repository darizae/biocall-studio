# RV-03 — Exact audio context, spectrogram rendering and playback

> **Status:** Owner-approved planning spec, NOT implemented. Do not start implementation or infer test passes from this document. Read [`AGENTS.md`](../../../AGENTS.md) and [`docs/agent/ROUTING.md`](../../agent/ROUTING.md), then this stage and only dependencies needed by its code. No push, merge, tag or release without the owner's separate authorization.

**Sequence:** RV-03 begins only after RV-02 has passed its owner-reviewed gate and the shared REV-05 prerequisite has been verified in the real checkout.

**Series:** [Locked scope, prerequisites and coverage](README.md) · [Status](../../IMPLEMENTATION_SEQUENCE.md)

## Strict ownership and exclusions

**Owner:** `review/workflows` source window reader and spectral calculation, a minimal native PySide6 playback/render proof surface, with separate upstream change only for verified reusable toolbox API gaps. **Entry:** approved RV-02. No production gallery, cache quota or storage adapter yet; RV-04/RV-05 own those. Render only *eligible* Result candidates, never raw recording annotation.

## Audio, spectrogram and interaction contract

**Input:** each *eligible* candidate's original WAV window around its original frame interval. Default initial context approximately 2 seconds before/after, clamped to `[0, recording.frame_count]`. Keep original `start_frame/end_frame`, rate and exact displayed time anchors; mark the detected interval on the spectrogram. Adjacent/overlapping candidates may share intermediate source reads/transforms if it improves measured performance, but each remains a distinct label and UI item. Do not accidentally export the *context* audio instead of the detected interval.

**Render:** use reproducible, explicit spectral settings (sample rate/channel handling, window, FFT, hop, frequency range, amplitude scaling, image dimensions, color scale, renderer version). Establish readable defaults with representative normal audible-call WAVs in RV-03; never silently borrow inference-time mel feature preprocessing if it is unsuitable for human inspection. If audio is multichannel, decide/test a display/playback channel policy without modifying stored source. Prefer CPU bounded decoding and small memory windows, not a GPU dependency. A lightweight thumbnail for Gallery and a high-detail view for One by one should share computation where justified and not require 50,000 full-resolution images. Native Qt UI should scale/zoom images legibly without a full recording timeline.

**Audio:** Play/Pause, basic seeking within the displayed candidate-context clip, explicit Previous/Next, stop/transition on navigation, single active playback and no overlap between rapidly switched items. Play the context clip at natural speed, highlight the detected interval; let users hear the full surrounding signal. Relinking/stale source and unsupported PCM/decoder errors must be visible and actionable; a missing source never implies silence. Audio playback and annotation remain responsive during background generation, eviction or export. Handle device unavailable, stream failure, cancellation, selection change and window closure with real Qt multimedia tests. Native media failures must not mutate labels.

**Navigation:** Gallery = lazy image grid plus visible status and human-readable recording/time; List = `alp-ui` DataTable/model-view/proxy with sorted searchable/filterable rows and bulk selection; One by one = largest spectrogram, audio controls, statuses and Previous/Next. Labeling Call/Not a call saves and auto-advances to the **next Unreviewed eligible candidate**; if none remain, keep user in a valid stable state rather than wrapping unexpectedly. Explicit Previous/Next traverse the current sequence and allow revisiting already reviewed candidates; keyboard shortcuts mirror buttons. Switching views preserves filters/current item/selection; selection labels operate on persistent candidate identities, not visual indices. In list/gallery, selection and bulk cache flush need safe multi-select, with no per-row Qt widgets. Plain status icons must be distinguished by shape and text as well as color.

**Scale:** >=50,000 candidates must use incremental indexed paging, bounded QAbstractItemModel/proxy updates, viewport-based thumbnail requests and bounded state. Never construct tens of thousands of heavyweight widgets/images on initial load. Filters/sort/search should rely on database/index or bounded model ranges, not decoding images. Scrolling, label updates, keyboard actions and audio controls must keep the real Qt event loop responsive under load. Establish measured latency/memory budgets on actual available hardware, reporting distribution, cold vs warm cache and model/recording scale.

## Owning acceptance cases (proposed; register in existing indexes before TDD)

These are stage scope definitions, **not registered or executed tests**. Validate IDs against [unit](../../UNIT_TESTING.md), [integration](../../INTEGRATION_TEST_BEHAVIORS.md), and [fixture index](../../INTEGRATION_TEST_DATA.md); register exact case text there before implementation. Never create a second test index.

| ID | Owner | Positive assertions | Negative / non-mutation assertions |
|---|---|---|---|
| `UT-REVW-005` | RV-03 | exact frame clamping/context, start/end marking, duration/time units across rates/channels | underflow/overflow, missing/changed WAV and truncated frames are rejected; no mutated source window/metadata |
| `UT-REVW-006` | RV-03 | deterministic rendering spec, key invalidation by source/settings/version and correct thumbnail/detail identity | nonfinite/unsupported render settings, corrupt/old cache keys rejected; no metadata-as-audio fake success |
| `IT-REVW-004` | RV-03 | real mono/stereo WAV boundary/context PCM reads and spectrogram pixel/frequency/time reference checks | truncated/unsupported/stale WAV fails without silent zeros or source modifications |
| `IT-REVW-005` | RV-03 | actual Qt multimedia play, pause, seek, previous/next and focus under playback in a real event loop | device failure/rapid switching/close stops playback without overlap or a blocking GUI |

**Gate:** Owner reviews real original-WAV spectral screenshots, playback on a native Qt device and measured FFT/encoding/audio performance; no speculative toolbox or `Plot` API.

## Delivery and evidence gate

Record reviewed baseline SHA and branch, actual implementation files, focused and full feasible ordinary test commands and pass/fail/skip/block results, Ruff, `scripts/audit_test_ids.py`, `git diff --check`, source/Result checksum non-mutation, and current dependency import origins/SHAs. Capture real native Qt/audio/Worker evidence only for boundaries owned here; do not claim whole-Studio qualification before RV-08. Confirm a clean narrowly scoped diff and hand the branch/commit SHA to the owner. No automatic merge or push.

**Next:** RV-04 may be prepared only after this gate is explicitly approved.
