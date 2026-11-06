# RV-10 — Responsive spectrograms, truthful cache and short qualification

**Corrective specification; not implemented.** **Entry:** owner-approved RV-09 visual/sidebar, deletion, data-folder and upstream dependency handoff. **Owns:** asynchronous candidate/visible/nearby spectrogram work, normal-speed audio responsiveness, verified cache reuse, quota/eviction, calibrated REV-05 preflight, short user-journey tests and an additive RV-08 qualification update. No redesign of verified CNN/RF Results, source-frame arithmetic, annotations, immutable export publication or existing RV-01–RV-08 contracts.

## Concrete native integration defects

| Existing code | Problem | Required outcome |
|---|---|---|
| `workspace.py::_load_current` | Reads/hashes audio, computes STFT and publishes PNG synchronously on the Qt navigation path | Never do variable-cost whole-WAV verification, FFT, PNG compression/fsync or SQLite cache publication on the GUI thread. |
| `audio.py::read_candidate_audio` | Without the identity cache, hashes each full source WAV **twice** for every candidate visit | Background verified source identities reused safely by stable file facts/checksum epoch; invalidate on change, never trust stat alone for initial integrity. |
| `workspace.py::_gallery_thumbnail` | Returns `None` on cache miss, never schedules visible or nearby work | Empty-cache Gallery produces images on demand using the supervisor; no Generate all prerequisite. |
| `models.py` and `cache.lookup` | Gallery paint/data may synchronously read PNG, SHA verify and write SQLite last-access metadata | Bounded decoded thumbnail memory cache, background integrity reads, coalesced access updates and row-local repaints. |
| Detail images | Re-renders before checking for an existing detail image | Verify and reuse cache hit before STFT; stale/changed source still correctly blocks playback. |
| Gallery | `IgnoreAspectRatio` warps scientific image | Correct native geometry and accurate time/frequency overlay inherited from RV-09. |
| Cache | Hardcoded 512 MiB quota can evict early items while Generate all is still running | Define measured quota/retention policy and truthful “retained” status, avoiding endless generate/evict churn. |
| Preflight | UI passes `calibration=None`; nonzero generation estimate stays “Unknown” | Supply measured representative encoded-size/time cohort when possible, preserve honest Unknown otherwise. Use implemented REV-05. |
| Multi-select | GUI displays full selected count but stores up to 1,000 IDs | Exactly match selected and cleared items; bounded chunking or an explicit visible selection limit. |

## 1. True hybrid rendering and playback

1. **Current candidate:** selection/focus/label/navigation update immediately, stop previous audio safely and enqueue current clip verification and detailed spectrogram work at highest priority. Use bounded workers, versioned candidate/source/settings/render content keys and an epoch/selection token. Late jobs after Next/Previous, filter, session delete, settings change, data-folder move or exit must not paint the wrong spectrogram or play the wrong recording.
2. **Gallery:** queue only **visible missing thumbnails**, update rows when available, deduplicate pending/cached work, then prefetch a small nearby window at lower priority. Scrolling, filtering and session switching cancel/deprioritize stale prefetch. Blank initial Gallery with no cache must render. Don't materialize 50k Qt widgets or decode 50k PNGs.
3. **List:** keep indexed lazy metadata and make transition into One by one use the same high-priority current-candidate pipeline. Rapid keyboard label/undo/Previous/Next remains responsive while workers run. Audio remains normal speed with the original candidate interval highlighted inside clamped audible context.
4. **Generate all:** thumbnails only, bounded streaming queue and concurrency, dedup/cache hits, active priority fairness, cancellable progress. Do not starve current detail or visible Gallery requests. Distinguish attempted/generated/cached/retained/failed/cancelled; no infinite re-generation loop after automatic eviction. No incomplete cache publication is counted successful.
5. **Thread safety:** source SHA verification, bounded WAV reads, STFT, PNG encoding, checksums and file writes belong off the GUI thread. QPixmap/widget manipulation and presentation signals belong on Qt's GUI thread. Source identity cache must verify initial WAV content and revalidate on signature/path change; don't replace proof with a stale stat cache. Restore controls and cleanup temp files/leases on cancellation/disk-full/failed decoding.

## 2. Correct caching, eviction and sizing

- Distinct deterministic, versioned **thumbnail** and **detail** cache keys; reuse valid image before recalculation. Keep axes separate from data PNG and original frame mapping exact, no warped display. Cache can be entirely removed/regenerated without touching labels, recordings, Results or frozen export provenance.
- Protect visible/current/in-flight keys using the existing automatic pin capability; LRU-evict only unpinned disposable images. Avoid repeated full PNG integrity work in the paint hot path while verifying in background on opening/recovery. Manual Clear (one, multiple, all) also cancels pending matching jobs so they cannot regenerate just-cleared entries.
- Reconcile Generate all's **complete-thumbnail retention** with chosen safe quota and actual cache volume. Before work, estimate missing thumbnails, verified hits, expected final storage, peak temporary bytes, and available space. If safe retention is not feasible, present an actionable small choice rather than running and claiming all images remain. Do not silently raise a fixed 512 MiB quota without measured evidence.
- Reuse **completed REV-05** `StorageEstimate`, per-volume admission and recheck; populate Review `CacheSizeCalibration` using locally measured encoded PNGs, metadata overhead, staging and generation timings with recorded renderer/source SHA and cohort. If the cohort is insufficient or field-audio distribution unknown, be honest (“Unknown”) rather than creating fake estimates. Revalidate inputs immediately before writing. Only RV-10 Review-specific adapters; no shared preflight reimplementation.
- Honor RV-09's new Review data directory: all cache paths/locks/threads must use the selected root after safe migration, never an abandoned root. Honor session deletion: cancel work for deleted session and prevent late callbacks from recreating its state, while shared cache content remains reusable by other sessions.
- Disk-full, corrupted cache, interrupted staging, stale settings epochs, source relinks/changes, rapid navigation, eviction and restart must not publish incomplete entries or modify original WAVs/immutable Results, labels/finalizations, independent export receipts or other sessions.

## 3. Short actual user-journey tests

Register proposed IDs **during implementation** in existing unit/integration indexes:
- `UT-REVW-015`: queue priority/dedup/stale epochs, verified source identity reuse, cache hits, pins, capacity/retention admission, selection count.
- `IT-REVW-015`: **empty-cache Gallery** opens with actual WAV, visible thumbnails appear without Generate all, nearby prefetch, scroll-away cancellation and row-local paint.
- `IT-REVW-016`: rapid One by one navigation plus F/D/S/Play while instrumented WAV verification/STFT is deliberately delayed; no event-loop stall, wrong audio/image, repeat full-file hash or unnecessary rerender.
- `IT-REVW-017`: small realistic cache-pressure/eviction/retained-count test, calibrated/Unknown REV-05, multi-selection clear, disk-full/restart, and safe concurrent session deletion/data-root migration.

Use minimal actual PCM WAVs, controlled latency, event-loop heartbeat measurement, source hash count, render/read/SQLite write counts, bounded memory, image identity and source/Result/label nonmutation. The existing 50k Qt **model** test is not evidence of smooth spectrogram navigation. Natural field-call readability remains a separate owner approval gate if no consented representative sample is available.

**Strict no-long-tests:** each focused command including fixture setup has an enforced **≤120-second timeout**; stop/mark incomplete otherwise. No full ordinary suite, 50k stress rerun, ≥600-second soak, broad end-to-end RF retraining, browser mega-suite or installed-platform tests without separate owner authorization. Don't disguise a long run as many repeated invocations. Ruff, small targeted unit/Qt tests, test-ID audit and diff checks are acceptable. All unrun/deferred checks must be documented.

## 4. Upstream and final native gate

If RV-10 reveals another **genuinely reusable** Qt presentation defect, use RV-09's independent `alp-ui` public branch/test/**commit there** → owner-reviewed latest local revision → `.venv/bin/python -m pip install -e ../alp-ui` → verify actual import/version/SHAs → focused Train/Detect/Review compatibility checks. Do not use private API fallbacks. Pure sound/STFT/candidate logic stays Review-owned unless an independently justified scientific toolbox gap emerges.

Capture **actual visible PySide6 native-after screenshots** corresponding to all [committed prototype targets](../../design/evidence/review-correction/README.md), including sidebar, correctly shaped thumbnails and full One by one plots; compare at normal, compact/narrow and available higher display scales. Physical playback and hover/focus should be owner-authorized; offscreen tests remain insufficient. Append (do not overwrite) a dated corrective record to `docs/RV-08_QUALIFICATION.md` with real Studio and upstream SHAs, installed path, focused command results/durations, visual comparison and outstanding blockers. No claim of owner sign-off without the owner.

**RV-10 gate:** Gallery renders visible thumbnails with empty cache, One by one navigation/labels never do unbounded I/O on Qt, detail reuses valid cache and only current work paints/plays, cache quota/preflight and completed-vs-retained figures are truthful, 50k metadata doesn't create eager widgets, delete/move does not corrupt work, and focused native/audio tests pass within budget. Owner visually approves the screenshots. Until then **Review remains not qualified for integration into main**.
