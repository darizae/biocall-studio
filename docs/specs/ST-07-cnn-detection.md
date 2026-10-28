# ST-07 — CNN first-pass candidate detection

**Branch:** `detect-st07-cnn-detection` from reviewed `detect`. **Predecessors:** ST-04 inventory, ST-05 trusted CNN Model, ST-06 Worker. **Successor:** ST-08. **Status:** planned.

## Scope and ownership

Run the selected, proven-compatible **CNN** over frozen included Source Recordings, produce time-local candidate intervals and publish one immutable, metadata-only Result. Own validated scoring options, window/hop processing, candidate threshold, merge/clamp logic, per-file failures and provenance. Do not crop/export audio (ST-10), refine by RF (ST-09), add waveforms/playback (out of scope), or modify Train.

Before implementation, inspect exact current toolbox inference/checkpoint/transform source and tests. Establish numerical parity against reference forward-pass outputs on deterministic **real WAV** (including resample, mono handling, FFT/hop, normalization, window alignment, padding and output interpretation). `score` is not advertised as calibrated probability without evidence; `target` column must be proven. Determine scientific thresholds/defaults only from confirmed source/config plus signed-off behavior; document and test source-time rounding for windows and merged candidates.

## Contract and handoff

`DetectionResult` (versioned immutable): Result/Run/Collection/inventory/Model IDs+digests, resolved settings+scientific backend revision, recording refs and original recording frame/time base, individual `[start_frame,end_frame)` candidate intervals mapped to source timestamps, score semantics and per-file status. A failed/stale/unreadable recording is **not** a zero-candidate success. Completeness/error semantics must be explicit; only successfully validated Result can be published. Recheck each file and binary against frozen snapshot at Worker use; do not silently process a changed file. Preserve original recording timestamps rather than elapsed Run or clipped snippet times.

Output is metadata and checksums under app-owned Detect Results, published via ST-06 receipt; no source write, no embedded absolute source paths, no mutable rewrite of prior Result. If partial-file completion is allowed, specify explicit status and per-file outcomes, never label as unqualified full success. Cancellation produces no new committed Result.

## Native parity

`#detect/setup` score/window-overlap/nearby-candidate controls with validated values and functional `HelpHint`; `#detect/run` real progress/failure states. Use prototype layout/hierarchy, not its illustrative science values. Plain-language researcher labels; no unexplained metrics, tiny detached captions or nonfunctional tooltips. Actual Results exploration remains ST-08; a minimal completion transition is acceptable.

## TDD and boundary verification

- `UT-DET-013` — exact source-frame/window/hop/overlap arithmetic, resample/padding boundary and invalid config rejection.
- `UT-DET-014` — target score/threshold semantics, interval merge/clamp, non-finite or ambiguous outputs fail.
- `UT-DET-015` — candidate source timestamps, deterministic IDs, immutable Result schema, per-file status validation.
- `IT-DET-012` — real-WAV CPU CNN inference compared numerically to verified upstream reference output, class order and frame intervals (`TD-WAV`, `TD-EXPORT`, `TD-TRAIN`).
- `IT-DET-013` — real Run→checksum-valid metadata Result reopen; source non-mutation, zero candidates vs failed-file contrast, worker/GUI progress (`TD-WAV`, `TD-RUN`, `TD-UI`).
- `IT-DET-014` — stale/replaced WAV/Model, unsupported shape, cancelled Worker, crash, invalid receipt, atomic failure (`TD-FAIL`, `TD-CACHE`, `TD-RUN`).

Fail test first, implement via verified toolbox APIs (upstream feature/fix branch and independent commit when necessary), retest upstream and downstream. No synthetic pass/fake CNN. Run targeted, affected Train compatibility and full feasible ordinary suites before implementation commit; explicit scientific or platform blockers remain unsatisfied gates.

## Gate

Reference numerical parity, source-time correctness, real Worker/Result reopen, negative cases and native controls reviewed. Record a frozen Result contract for ST-08/09/10. Integrate locally to `detect` after review; no push.
