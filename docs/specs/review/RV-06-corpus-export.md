# RV-06 — Review-owned corpus export and large-scale publication

> **Status:** Owner-approved planning; not implemented. Begin only after explicit stage authorization and the predecessor's owner gate.

## Strict ownership and exclusions

**Owner:** Review frozen export projection/publisher, versioned metadata/receipts, history and REV-05 export-sizing adapter, reusing verified scientific WAV/Raven routines without moving predictions or mutating old data. **Entry:** approved RV-05. This stage builds **new Review export capability** while legacy Detect paths remain readable and, until RV-07, existing Detect UI is not prematurely removed. RV-07 alone removes new-export entry points and updates shell routing. No packaging, Train data ingestion or feature extraction changes.

## Export semantics, formats, migration and scalability

**Owner rule:** new exports can only start from an immutable **Finalized Review session**. There is one export flow; no separate as-detected route. A Result can be accepted en masse via **Accept all**, finalized, then exported normally. Or a partially reviewed session may be finalized after warning and exported with Unreviewed included as model-only. Export format choice appears at the last step: **Individual WAV files**, **Combined WAV + Raven TSV**, **Both**. A session can yield multiple independent exports.

**Export selection:** compute ordered `Call ∪ Unreviewed` eligible candidates, exclude `Not a call` and all ineligible RF candidates, verify frozen Result/session integrity, source bindings and format compatibility. Always record **the whole decision inventory** in frozen Review provenance (including rejected and ineligible counts or references where appropriate) even if WAV payload contains only included candidates. Annotations and export status must distinguish `human_individual`, `human_bulk` and `model_only`; do not call a model-only row human-verified. Preserve candidate/recording ID and original frame/time/source hash in metadata; user-facing UI uses names, not IDs.

**Scientific invariants to preserve:** snippet samples and headers exactly match original PCM source window; source boundaries are original Result intervals, not context; no silent resample/downmix/channel merge; deterministic order and collision-safe names; concatenated WAV uses its own frame offsets, Raven TSV represents those concat offsets and provenance maps back to original source/time; existing mono/identical-format constraints for concatenation remain; every published file is hashed and verified; destination outside source recordings, no overwrite, private same-volume staging, exclusive publication; Show in folder only after verified success. Unsupported mixed formats produce an actionable choice; never silently coerce data.

**Scalable publishing is a mandatory engineering change**, not `MAX_EXPORT_CANDIDATES = 50_000`:

1. Remove the old fixed **10,000 candidate** limit from the *new Review export format*, replacing it with justified arithmetic, filesystem and serialization/resource constraints; explicitly qualify **at least 50,000** valid candidate rows. Keep old schema constraints for reading historical artifacts if needed.
2. Revisit `MAX_DOCUMENT_BYTES = 64 MiB` and in-memory tuple/list materialization in snapshot/receipt and TSV construction. Propose a **versioned** large-export metadata format (e.g., bounded streaming JSONL rows + compact manifest/index and digest-bearing receipt) with streamed validation, bounded row sizes, deterministic canonical hashing and no loss of provenance. Exactly decide names/versions in RV-06 with format tests; don't silently mutate v1 documents.
3. Stream source WAV slices with bounded buffers and file descriptors; avoid redundant whole-recording hashes on every candidate and quadratic `candidate × recording` scans. Cache verified per-recording identity within the frozen operation only, with safe rechecks on use. Keep cancellation points in copying, writing, verification and history persistence.
4. Ensure `Both` materialization does not accidentally double-read or recompute all source content when safely avoidable. Measure realistic disk I/O; performance optimization may not alter PCM bytes or ordering.
5. Guard file and total size overflow before publication. Conventional RIFF/WAV has a practical ~4 GiB limit; if projected concatenation cannot fit, block that mode with the approved message: **“The combined WAV would be too large. Choose individual WAV files instead.”** Do not silently split/upgrade format without owner-approved format/version change. Consider other WAV implementation/header constraints from actual `wave` writer.
6. Scale receipt verification and reopen with bounded memory, deduplicated work, streaming checksums and cancellation; no output counted successful until snapshot/receipt plus all declared files verify. Tests exercise corrupted or missing rows midway/late in a 50,000-item output.
7. Keep no-clobber atomic publish on destination volume, isolated staging, disk-full recovery, collision guards, incomplete cleanup and crash reconciliation. Post-publication history-write failure must keep verified output recoverable without fabricating a second export or overwriting it.
8. Add Review-owned export histories with lineage to Result and finalized session. Preserve old Detect export directories/receipts/history read-only. If historical export history remains reachable from Detect for compatibility, show it as history only; Detect can no longer start a new corpus export. Do not rewrite/migrate old WAV bytes or remove legacy readers until their documented compatibility obligation has been met.

**Migration sequence within RV-06/RV-07:** add Review-owned frozen export adapter/publisher with compatibility tests first; then expose Review UI; then remove Detect's export planning button/sidebar and controller initiation route, while retaining legacy history/open/verify paths. Update `docs/PREDICTION.md`, `docs/design/UX_PARITY_MATRIX.md`, relevant existing tests and minimal navigation docs to reflect ownership. Do not discard `IT-DET-019`–`021` scientific invariants or turn old input artifacts into writable new-session artifacts.

## Acceptance cases (register in existing test indexes during stage TDD)

| ID | Owner | Positive assertions | Negative / non-mutation assertions |
|---|---|---|---|
| `UT-REVW-010` | RV-06 | reviewed+unreviewed inclusion, human vs model-only provenance, RF-only eligible selection, correct frozen order | `Not a call` and ineligible RF candidate never in payload; changed/unfinished source or unfrozen session cannot export |
| `UT-REVW-011` | RV-06 | large snapshot/receipt serialization, WAV/Raven frame/size arithmetic, new-version/legacy-version compatibility | 50k no fixed 10k cap; bad large row, >4 GiB combined WAV, mixed channel/rate, collision or digest mismatch fail closed |
| `IT-REVW-009` | RV-06 | >10k and >=50k real-WAV-backed candidate export, streamed snapshot/receipt, successful verification/reopen and actual resource measurements | injected corruption near end, cancellation, crash, disk-full, multi-volume/stale space and output collision do not create false success |
| `IT-REVW-010` | RV-06 | all three PCM/Raven formats and mixed human/model-only receipt provenance; old Detect v1 outputs still verify/read | sample/frame/TSV offset mismatch, incompatible mono/format, 4 GiB, changed WAV, history-write failure do not corrupt originals or finalized session |

**Gate:** Owner accepts measured >10k/≥50k output plan/write/reopen/verification including complete scientific files, memory/timing data, v1 compatibility and publisher failure recovery; changing the constant alone is explicitly insufficient.

**Next:** RV-07 may be prepared only after this gate is explicitly approved.
