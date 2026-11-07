# Review Memory-Retention Hardening 
 
  ## Summary 
 
  • Fix three Review-owned retention issues on the current review baseline: 
      • Gallery clearing leaves metadata behind: reproduced with 6,400 metadata entries and zero pixmaps. 
      • Spectrogram failures accumulate indefinitely: reproduced with 10,000 retained messages. 
      • Completed generation batches retain all per-content state until history pruning, potentially retaining many 50k-key batches. 
 
  • Keep Train and Detect unchanged; their targeted worker/process cleanup tests passed. 
 
  • Preserve all scientific results, cache files, source WAVs, UI behavior, and GenerationProgress semantics. 
 
  ## Implementation Changes 
 
  • Replace the Gallery’s separate pixmap and metadata maps with one 64-entry LRU mapping from candidate ID to (QPixmap, SpectrogramMetadata). Clear and evict each pair
    atomically during filtering, session changes, explicit cache clearing, and model refresh. 
 
  • Bound diagnostic failure retention to the latest 64 messages, truncating each to 512 characters. Keep existing boolean/count-based test observability without retaining
    unlimited exception text. 
 
  • Compact a generation batch immediately when it becomes terminal: 
      • Preserve requested/completed/failed/cancelled/cache-hit counters. 
      • Mark the batch done and clear its per-content state and iterator. 
      • Keep progress() and wait() results available until normal batch-history eviction. 
      • Apply compaction after completion, cancellation, invalidation, and queue-drop paths. 

  • No public API, persisted schema, scientific type, or upstream alp-ui change.
  

## Test Plan

- Extend UT-REVW-015 to prove:
  - Pixmap and metadata LRU counts always match and remain at or below 64.
  - Repeated clear/refill cycles return both caches to zero.
  - Terminal batch compaction releases content-key state while preserving final progress counters.
- Extend the existing RV-10 Qt cases to exercise repeated Gallery search/filter/session switching and injected spectrogram failures, asserting fixed container bounds and no stale painting.
- Re-run the four passing lifecycle regressions for Review gallery generation, generation cancellation/50k streaming bounds, Detect QProcess restart, and Train scan shutdown.
- Run a short native Cocoa Review navigation loop with an actual WAV, draining deferred Qt deletions and recording RSS/tracemalloc as diagnostic evidence; exact cache/object bounds are the hard acceptance criteria.
- Keep every invocation under 120 seconds. Run scoped Ruff and test-ID audit only; defer the full suite, 50k stress rerun, and soak.

## Assumptions

- Work starts from review at ffa0c52, which contains RV-10 source 27d94b8, on a focused Review maintenance branch after authorization.
- Scope is Review browsing, as selected; no main merge, push, release, documentation qualification claim, or owner visual-approval claim.