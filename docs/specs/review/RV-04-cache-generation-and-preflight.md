# RV-04 — Hybrid generation, storage preflight and cache lifecycle

> **Status:** Implementation handoff prepared on `review-rv04-cache-generation-and-preflight` from reviewed base `eadc9f1`; owner code/evidence review and local integration remain pending. Test results must come from the current handoff, never from this contract. Read [`AGENTS.md`](../../../AGENTS.md) and [`docs/agent/ROUTING.md`](../../agent/ROUTING.md), then this stage and only dependencies needed by its code. No push, merge, tag or release without the owner's separate authorization.

**Sequence:** RV-04 begins only after RV-03 has passed its owner-reviewed gate.

**Series:** [Locked scope, prerequisites and coverage](README.md) · [Status](../../IMPLEMENTATION_SEQUENCE.md)

## Strict ownership and exclusions

**Owner:** Review background generation supervision, private spectrogram cache persistence, quota/eviction/flush, and **Review-only estimate adapter**. **Entry:** approved RV-03; shared REV-05 is already part of RV-01's reviewed baseline. Do not recreate `shared/StorageEstimate`, Train/Detect output estimates or a second filesystem capacity service. RV-05 owns researcher-facing integration/UI; RV-06 owns export estimate inputs and corpus publication.

## Detailed hybrid generation, cache and capacity contract

Cache key must incorporate a validated stable source content identity (recording SHA/facts, not just current path), candidate frame bounds/context, stereo/channel policy, rendering settings, resolution tier and renderer version. Store derived files outside source trees, with a contained versioned cache manifest, checksums/size, generation state and last successful access. Existing valid files may be reused across sessions where the inputs/settings truly match; never cache a stale source under its previous key. Check contained paths and symlink escapes on lookup, generation and deletion. No human decision is stored inside the cache.

**Hybrid generation:** visible missing thumbnail first, bounded prefetch nearby; detail render on item entry; explicit **Generate all** requests all missing eligible thumbnails (possibly detail only on demand). Use bounded concurrency and queue backpressure, deduplicate concurrent requests and drop low-priority prefetch on rapid navigation. Workers must report actual completed/failed counts and user cancellation without blocking event loop. Finished valid files may remain after cancellation; incomplete staged files are cleaned and never presented as complete. Retry only failures/missing files and avoid rehashing identical unchanged sources per item if a validated source identity can be safely shared.

**Storage:** Review-specific size adapter calls the **implemented** shared REV-05 `StorageEstimate` preflight. Distinguish exact known sizes (existing files) from estimated output sizes (codec/compression dependent); report about/range/unknown, peak extra staging usage, free bytes on the actual cache/output filesystem, headroom and confidence. For bulk generation: display before starting and recheck at admission. On-demand and prefetch: avoid a modal prompt for every thumbnail, but enforce a real capacity budget; for tight/unknown persistent cases surface one useful action/decision, and on insufficient capacity disable further writes while keeping the review/labels usable. A preflight is never a disk reservation. No extra standalone estimation framework and no hidden claim that the cache is free.

**Eviction:** configurable bounded cache limit, default chosen by measured disk cost (not an invented number), automatic least-recently-used or similarly defensible policy with protected current/visible/in-flight entries. Evict only valid regenerable image files. Manual **Clear spectrograms** supports one item or selected items, including Call/Not a call/Unreviewed; no separate label status logic controls deletion. Optionally provide filters to select batches. Clear action never modifies session database, finalized snapshot, original WAVs, source hashes or prior exports. A missing/evicted image is regenerated on demand. Handle cache full, permission-denied delete, symlink/path attack, simultaneous renderer/evictor and file corruption deterministically. Avoid unnecessary confirmations when only regenerable cache is being deleted.

**Quota and boundedness:** track actual cache bytes and bounded generated-file metadata without scanning every cached file on every UI refresh. Defer expensive integrity reconciliation to controlled background/launch points. Limit open file handles/PCM buffer counts and Worker memory. Prefer reversible, cache-local repair over global resets. Queue and cache state have no scientific authority and may be reconstructed without affecting annotation history.

## Preset-aware cache changes, safe regeneration and calibrated sizing (owner decision 2026-11-03)

A session's effective **settings snapshot** and scientific/rendering version, not merely the mutable preset ID or name, enter the content key. **Generate all** requests remaining **thumbnails only**; high-detail data-only images remain **on demand** and may reuse a verified intermediate computation only when measurement justifies it. Share valid cache objects across sessions only when complete source/context/settings/tier keys truly match. Display-only changes invalidate relevant rendered images without claiming a different recording or analysis. Do not generate tens of thousands of detail images speculatively.

**Change preset** only for Open session and only after explicit confirmation stating the affected images need generation again, estimated incremental time/bytes (range/unknown if not calibrated) and **unchanged labels/recordings**. Verify/recheck existing REV-05 admission rules on the cache filesystem before an admitted bulk swap. In a single guarded transaction update effective settings/epoch and point the session at the new cache namespace; never delete globally shared old images merely because they are no longer used by one session. Cancel/mark stale old workers and reject their late publication if session epoch, content digest or source identity mismatches. Stage privately, validate checksum/source/contained paths, commit atomically; a crash, disk-full event or late completion may not resurrect old settings as current. Visible thumbnail/current detail then bounded nearby prefetch regenerate; **Generate all** remains a separate optional action. Cancel keeps successfully compatible files; Retry operates on missing/failed entries. Preserve manual Clear spectrograms semantics and all labels.

**Sizing:** the Review-only adapter uses the *implemented* `shared.storage` `ByteEstimate`/`OperationSizePlan`/`StorageEstimate`/`assess_storage`/`require_storage_admission`, with existing cache-hit bytes distinguished from **additional output** and staging peak, uncertainty/capacity freshness and actual volume. Time estimation is Review-specific and experimentally calibrated; do not graft time onto REV-05 or hardcode Linux sandbox pilot rates. If insufficient evidence, show an honest range/unknown. Measure representative audio and 1–1000 item batches and analytical 10k/50k outcomes as specified in the separate pre-spec, then qualify model against actual bytes/latency.

**Qualification extension:** `UT-REVW-007/008`, `IT-REVW-006` cover multi-session reuse, global preset edit without invalidation, source/result unchanged after update, stale-epoch jobs, failed transaction/permission, storage headroom, cancellation/retry, exact-vs-estimated cache hits and bytes, 50k bounded worker scheduling.

## Owning acceptance cases (proposed; register in existing indexes before TDD)

These are stage scope definitions, **not registered or executed tests**. Validate IDs against [unit](../../UNIT_TESTING.md), [integration](../../INTEGRATION_TEST_BEHAVIORS.md), and [fixture index](../../INTEGRATION_TEST_DATA.md); register exact case text there before implementation. Never create a second test index.

| ID | Owner | Positive assertions | Negative / non-mutation assertions |
|---|---|---|---|
| `UT-REVW-007` | RV-04 | bounded queue priority, deduplication, LRU/limit policy, safe selected-item flush | never delete pinned/in-flight/source/label files; cancellation leaves valid completed entries only |
| `UT-REVW-008` | RV-04 | Review spectrogram sizing adapter, peak temporary-space arithmetic, per-volume REV-05 decision and recheck | stale/unknown/tight/insufficient treated accurately; injected overflow/impossible size rejects; no Worker on blocked preflight |
| `IT-REVW-006` | RV-04 | genuine supervised async generation/prefetch/cache reuse and measured output-vs-REV-05 estimates, actual eviction/regeneration | low disk/permission/disk-full/cancel/owner crash/symlink/corrupted image: safe recovery, label unchanged, no orphan Worker |

**Gate:** Owner verifies real REV-05 API consumption, measured cache output-versus-estimate, disk/full/unknown/low-space paths, Worker stop/restart and unchanged labels after flush/eviction.

## Delivery and evidence gate

Record reviewed baseline SHA and branch, actual implementation files, focused and full feasible ordinary test commands and pass/fail/skip/block results, Ruff, `scripts/audit_test_ids.py`, `git diff --check`, source/Result checksum non-mutation, and current dependency import origins/SHAs. Capture real native Qt/audio/Worker evidence only for boundaries owned here; do not claim whole-Studio qualification before RV-08. Confirm a clean narrowly scoped diff and hand the branch/commit SHA to the owner. No automatic merge or push.

**Next:** RV-05 may be prepared only after this gate is explicitly approved.
