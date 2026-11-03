# RV-08 — Whole-Studio source-app qualification and final sign-off

> **Status:** Owner-approved planning; not implemented. Begin only after explicit stage authorization and the predecessor's owner gate.

## Strict ownership and exclusions

**Owner:** final scientific and whole-application integration under existing **ST-11** qualification/test ownership, plus evidence review and final documentation. **Entry:** approved RV-07, with RV-01–06 gates already reviewed. **No new duplicate E2E test index**, no macOS/Windows packaging/signing/release work.

## Cross-workspace qualification scenarios

- One genuine source-app chain: Train Dataset/Model → Detect Collection/CNN Result → optional RF-derived Result (RF-accepted only in Review) → open Review session → on-demand and bulk spectrograms → human Call/Not a call/Unreviewed decisions and Accept all/undo → partial warning → Finalize → Review-owned WAV snippets/concatenation/Raven/both → receipt reopen, source-time and scientific checksum verification.
- Explicit closed-session pause/resume, finalized child session, multiple exports from same snapshot, cross-workspace navigation and exit warning when Review is hidden; busy Worker/cancellation/disk-full/recovery, missing/relinked/changed WAV and history-write interruption.
- Native Gallery/List/One by one at ≥50,000 candidates with real event loop and actual audio/playback; accessible statuses/buttons/HelpHints and exact owner-approved text in normal/compact layouts. Cache quota, eviction, individual/multi Clear spectrograms, regeneration and REV-05 measured-vs-estimated preflight; unchanged labels and source bytes.
- Scalable publication of 10,001 and ≥50,000 distinct valid candidates, verifying real WAV/Raven output files, metadata receipts, streamed verification/reopen, bounded resources, >4GiB concatenation guard and old Detect v1 export compatibility. Distinguish feasible generated row scale from source-audio/real native constraints; never invent results.
- Re-home the existing `IT-DET-022` and `IT-STU-007` / `IT-STU-008` **in place**, reflecting new export ownership, not cloning the same E2E path into Review-specific tests. Rerun affected `UT-DET`/`IT-DET`, `UT-STU`/`IT-STU`, `UT-SIZE`/`IT-SIZE` and new Review tests. Separate ≥600 s soak only when explicitly initiated.
- If current library SHAs, real device/native Qt, real Model, LFS fixture or source checkout is unavailable, record the exact **blocked** case, not a fictitious pass. Validate release work remains deferred and outside this plan.

## Final owner qualification checklist

- [ ] Review accepts **Detect Results only**; CNN-only all eligible, RF-derived accepted-only, no rejected/unscored UI; original/derived Results unchanged.
- [ ] Exactly three human labels, accessible non-color-only icons, no custom class or interval-edit surface.
- [ ] Single normal workflow including **Accept all**, mixed partial review warning and proper provenance of Call/Not a call/Unreviewed.
- [ ] One explicit Open session at a time; Close saves/pauses; finalization freezes; finalized successor independent; navigation preserves progress.
- [ ] Exit warning from any workspace with an Open session, one combined Worker confirmation, Save and Exit safe across failures.
- [ ] Gallery/List/One by one operate on same persistent labels at >=50k candidate scale; automatic advance and explicit Previous/Next and keyboard/undo all work.
- [ ] Playback uses real native Qt normal-speed audible context, detected interval highlighted, no full recording timeline and no false-negative authoring.
- [ ] Hybrid asynchronous cache generation, prior storage estimate/REV-05 recheck, background prefetch, cache eviction and multi-select clearing; regeneration cannot affect labels.
- [ ] All three corpus output modes preserved with frame-exact PCM/Raven/provenance and Show in folder; **Review is only new-export owner**.
- [ ] `MAX_EXPORT_CANDIDATES=10_000` is no longer a barrier in **new Review publication**, 50k materialization and reopen pass, metadata document/resource ceilings addressed with versioning, >4 GiB combined WAV safely blocked.
- [ ] Old Detect exports/receipts reopen, source/result/finalized bytes remain unchanged, relink and failures/cancel/crash/recovery exercised.
- [ ] Approved copy and forbidden UI noise inspected in real Qt normal/compact/accessibility; new wording delta reviewed rather than silently invented.
- [ ] Stage-owned indexed `UT-*`/`IT-*` tests, platform/native evidence and precise SHAs recorded; whole-Studio E2E only at RV-08/ST-11.
- [ ] No unapproved upstream refactors, no automatic push/merge/tag, no macOS/Windows release work.

---

**Planning completion boundary:** This is an approved specification, not evidence that Review is implemented. After explicit authorization to start RV-01 on the reviewed REV-05-complete base, the first implementation action is RV-01's stage-owned tests and Result intake—not a Train/Detect redesign or shared preflight reimplementation.

## Existing qualification test ownership (no new duplicate cases)

Update **existing** `IT-DET-022`, `IT-STU-007` and `IT-STU-008` in [integration](../../INTEGRATION_TEST_BEHAVIORS.md) in place to traverse Train→Detect→Review→Export and real cross-workspace shutdown. Rerun stage-owned `UT-REVW-*` / `IT-REVW-*` and affected existing Train/Detect/Studio/REV-05 regressions. Do not register a second whole-Studio suite.

**Gate:** Owner reviews complete ST-11-linked scientific/native matrix, actual pass/fail/blocked evidence and SHAs. Only after sign-off may source-app qualification be declared. Installed-platform releases remain deferred.

## Upstream and measurement audit

**`alp-ui`:** inspect *installed* public API and actual source SHA. If it already provides suitable accessible status icon/button/selection primitives, consume them. If it lacks a truly generic status icon presentation, propose a small upstream component (with no Review semantics), own tests/showcase and a separate commit/branch; install/verify its runtime import origin before Studio integration. Do not add a spectrogram to `Plot` by pretending a public heatmap API exists, or duplicate `alp-ui` styles in Qt sheets. Proprietary UI/logic for reviewing spectrograms stays under `review/gui`.

**Scientific toolbox:** inspect actual `bioacoustics-dl-toolbox` source and dependencies before reusing WAV/spectral utilities. Only upstream a numerical transform if genuinely reusable and the existing toolbox is the right owner. Keep separate branch, reference/numerical parity tests, commit SHA and downstream retesting; no speculative dependency upgrades, GPU frameworks or wholesale Train inference refactor.

**Measure/decide during owning stages, not as new product surveys:** CPU FFT/hop/color scale/frequency bounds and image resolution/encoding; mono/stereo playback/display policy; real Qt audio adapter supported on the test Mac; thumbnail/detail cache strategy; cache quota/eviction thresholds; SQLite synchronous/journal choice and bounded bulk undo log; 50k-view scroll/filter/sort latency; bounded export document format and RIFF writer capacity; estimates against actual cache and export byte counts; per-Worker concurrency and cancellation deadline. Report evidence and choices in the stage handoff; owner approves any *researcher-visible* deviation from this contract.

**Next:** No installer, release or subsequent implementation is implicitly authorized.
