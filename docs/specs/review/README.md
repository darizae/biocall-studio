# Review — ordered, owner-approved implementation specifications

**Status:** approved planning, not source implementation. **Sequence:** completed REV-05 baseline → RV-01 → RV-02 → RV-03 → RV-04 → RV-05 → RV-06 → RV-07 → RV-08. Each stage is isolated, sequential and requires an explicit owner review gate. No stage may be silently skipped, co-implemented with a later stage, or begun from an unreviewed predecessor. These documents supersede the earlier single-file Review planning proposal; do not keep or publish `docs/specs/REVIEW-workspace-plan.md` as a competing authority.

## Additive spectrogram planning (owner choices recorded, native research pending)

[Owner decisions / researcher copy](SPECTROGRAM_DECISIONS.md) · [Separate scientific and performance investigation pre-spec](SPECTROGRAM_GENERATION_INVESTIGATION.md). These two documents **augment rather than supersede** the eight sequential RV stages. The owner approved a 4.2 kHz adjustable default, compact + minimal Advanced settings, relative intensity/contrast, per-channel-power stereo, protected Default with user editable presets/impact confirmation, Review-local Settings, session-specific safe cache invalidation and thumbnail-first generation on 2026-11-03. Numerical parity, representative device calibration, quota and final native pixel tiers require the pre-spec gate before native implementation. Do not change Review eligibility, fixed shortcuts, approved label/session/export contracts, or reimplement shared REV-05. The supplied ZIP lacks `.git` and two root UX design documents; their historical provenance/sign-off is not verified by these planning edits.

## REV-05 prerequisite — satisfied on reviewed `main`

REV-05 is **implemented and owner-reviewed** on the current `main` baseline (`c00d8808a2d1`, 2026-11-03). The source contains the Qt-free `StorageEstimate` contract in `src/biocall_studio/shared/storage.py`, Train/Detect sizing adapters, native preflight integration and indexed `UT-SIZE-*` / `IT-SIZE-*` cases. Its [completed RV-01 handoff](../manual_revision_specs/REV-05-output-size-preflight.md#mandatory-final-handoff-to-review-rv-01) is the authoritative transition; the historical 2026-11-02 missing-implementation warning no longer applies.

RV-01 begins on this **reviewed, REV-05-complete base**. Review must reuse the existing shared contract: only Review-specific spectrogram sizing/preflight belongs to RV-04 and export sizing/preflight to RV-06. Never re-plan or reimplement REV-05 in RV-01–RV-08. At implementation time verify the actual checkout/dependency versions; if the shared contract is absent from a different checkout, obtain the correct reviewed base rather than creating a replacement.

## Stage route (read only the active stage)

| Order | Owning specification | Completion gate / output |
|---|---|---|
| 1 | [RV-01 — Result intake](RV-01-result-intake.md) | Verified CNN-all/RF-accepted-only, stable versioned projection; immutable source |
| 2 | [RV-02 — Sessions and annotations](RV-02-sessions-and-annotations.md) | Transactions, only one Open session, bulk, undo, finalization/successor |
| 3 | [RV-03 — Audio and spectrograms](RV-03-audio-and-spectrograms.md) | Source-exact context, native audio, scientifically readable renderer |
| 4 | [RV-04 — Cache, Workers and preflight](RV-04-cache-generation-and-preflight.md) | Hybrid generation, REV-05 adapter, cancellation, eviction, flush |
| 5 | [RV-05 — Native Review UI](RV-05-native-review-ui.md) | Gallery/List/One by one, approved exact copy, 50k UI, real Qt |
| 6 | [RV-06 — Review corpus exports](RV-06-corpus-export.md) | All formats, mixed labels, 10k cap removed, 50k publication and receipts |
| 7 | [RV-07 — Studio and Detect migration](RV-07-studio-detect-migration.md) | Single exit policy, remove new Detect export route, legacy readers retained |
| 8 | [RV-08 — Whole-Studio qualification](RV-08-qualification.md) | Full Train→Detect→Review→Export and regression sign-off |

**Strict chain:** RV-01 starts from the reviewed REV-05-complete baseline. RV-02 waits for RV-01 sign-off, RV-03 for RV-02, and so forth, even if their internal contracts are independently testable. Tests/implementation may not be pulled into a sibling stage to bypass review. All stage branches start from the *latest reviewed* integration base; no automatic merges or pushes.

## Locked owner decisions and export truth table

| Topic | Owner-approved decision and implication |
|---|---|
| Purpose | Review validates true versus false positives from Detect, efficiently, with pleasant mature researcher UX. No comprehensive recording annotation, missing-call/false-negative search or interval correction. |
| Input | **Only a completed, verified Detect Result**. Never open an arbitrary WAV or imported annotation as a Review source; no Detect corpus export prerequisite. |
| Boundary | Detect owns inference, RF refinement, and original/derived immutable Results. **All new corpus exports belong to Review**. Remove Detect's new-export UI/entry/workflow after migration while preserving historical artifacts and readers. |
| CNN vs RF | CNN-only Result: all its candidates eligible. RF-derived Result: **only RF-accepted** candidates eligible; RF-rejected/unscored are not displayed in any Review filter/sequence or exported from that Result. Do not offer overrides or confusing hidden filters. Original Result remains independently selectable if the researcher wants its CNN candidate set. |
| Labels | Exactly **Unreviewed**, **Call**, **Not a call**. No custom class vocabulary, per-candidate confidence, manual boundary edits, timeline authoring or false-negative creation. |
| Batch | One dedicated **Accept all** action marks **currently unreviewed eligible candidates** as Call, retaining previous Call/Not a call labels. Record bulk versus individual provenance; provide undo before finalization. No second direct-export workflow. |
| Partial review | May finalize and export with Unreviewed candidates after an explicit warning. Export includes Call and Unreviewed, excludes Not a call. Unreviewed means **model-only**, not human-verified. |
| Audio | Ordinary audible calls; native playback at normal speed, each detection with a few seconds of surrounding audio (provisional initial context: ~2 s before and after), source interval visibly marked. No full-recording timeline, pitch shifting or ultrasonic features. |
| Views | Virtualized **Gallery**, **List**, **One by one**; same backing decisions and selection. Large individually playable spectrogram in One by one. Selecting a label auto-advances to next Unreviewed; visible **Previous** and **Next** controls still allow free navigation, including revisiting labeled items. Keyboard play/pause, labeling, previous/next, undo. |
| Sessions | One open Review session at a time (whole application). Explicit **Open / Close**; close = save and pause, not finalize. Switching to Train/Detect/Studio keeps Review session open. Exiting the application from **any** workspace shows the approved open-session warning; Save and Exit closes safely. |
| Finalization | Explicit **Finalize** freezes one reproducible snapshot. A finalized session cannot be edited; **Continue in new session** creates an editable successor linked to the frozen parent. Exports consume finalized snapshots, can be retried or repeated, never undo finalization. |
| Spectrograms | Hybrid on-demand + nearby prefetch + optional **Generate all** asynchronously. Estimate disk use before bulk generation via REV-05. Automatic bounded cache eviction plus manual individual/multi-item Clear spectrograms, independently of label state. Deleting cache must not delete annotations/recordings. |
| Scale | Tens of thousands of eligible candidates; acceptance must exercise >=50,000 candidate metadata plus real audio boundaries. No 10,000-candidate export ceiling. |
| Output | Preserve individual PCM WAV snippets, concatenated WAV + Raven TSV + provenance, and Both. One export interface after finalization with format selection and Show in folder. |
| Presentation | Minimal readable text; use recognizable accessible status icons, ideally existing public `alp-ui`, upstream generic primitive only if verified missing. No repetitive captions, dev language, fake progress/status. The approved wording is in [RV-05](RV-05-native-review-ui.md). |
| Releases | macOS/Windows installer/signing/distribution tasks untouched; no implicit packaging qualification. |

### Export truth table

| Selected Result / model state | Human decision | Eligible to be shown? | Export? | Meaning in export |
|---|---|---|---|---|
| Original CNN candidate | Unreviewed | Yes | Yes | model-only detection |
| Original CNN candidate | Call | Yes | Yes | human Call (individual or bulk origin preserved) |
| Original CNN candidate | Not a call | Yes | No | human rejection recorded in finalized review provenance |
| RF-accepted candidate | Unreviewed | Yes | Yes | RF model-only detection |
| RF-accepted candidate | Call | Yes | Yes | human Call (individual/bulk origin preserved) |
| RF-accepted candidate | Not a call | Yes | No | human rejection recorded in finalized review provenance |
| RF-rejected or RF-unscored candidate | Any | **No** | **No** | remains preserved only in immutable original/derived Result |

An **Accept all** operation on an RF Result never accepts RF-rejected/unscored items. Labeling all eligible candidates is not the same as proving every one was individually listened to; preserve the distinction in metadata. The `Not a call` action reverses an earlier human or bulk acceptance, until finalization. There must be no separate “Export as detected” route/button: the owner expressly rejected it.
## Shared architecture and ownership boundaries

Proposed package layout (names are a guide; exact class/function names follow stage tests and source conventions):

```text
src/biocall_studio/
  review/
    domain/         # Qt-free candidate eligibility, annotation/session/finalization/export rules
    persistence/    # private transactional sessions/indexes; cache manifest; history/reconciliation
    application/    # session controller, view state, job admission, navigation, relink decisions
    workflows/      # WAV window reads, spectrogram render, cache jobs, export adapter/publisher
    gui/            # native views and accessible actions
  studio/application/ # suite data root, one-active-operation coordinator and exit policy
  detect/           # remains the owner of predictions/results, old export reader during migration
  shared/           # only genuinely shared infrastructure, including implemented REV-05
```

**Producer/consumer:** immutable `DetectionResult | DerivedResult` -> validated **Review intake projection** -> persisted Review session/candidate index -> transactional human annotations -> immutable finalized session snapshot -> Review-owned frozen export specification -> existing scientifically checked PCM/Raven materialization and receipt verification. Source WAVs remain read-only and external to mutable app-owned metadata. No Train contracts move; any future feeding of reviewed outputs into Train is **not in this scope**.

- Result validation includes schema, digest, collection/inventory reference, result kind, provenance, candidate duplicates/order, available recording facts and source freshness (relink later if necessary); never mistake failed source files for zero detections. Result eligibility is a **versioned frozen set**, not a constantly drifting UI filter.
- For RF-derived Result, retain the RF/parent lineage in the session and export; source time, frame boundaries, score semantics and source SHA-256 remain those provided by Detect. Do not reinterpret CNN score as a calibrated probability.
- Persist Review metadata at an app-owned `review/v1` root under the same suite root, isolated from Train/Detect; add it to the canonical `SuiteDataPaths` and source ownership audits. Never write cache/labels to source folders.
- Review retains its own controller and route; Studio coordinates *visibility, global Worker admission, and application quit* without importing Review's annotation model into Train/Detect. The shell may expose a narrow session-open/exit-admission interface.
- Use a **transactional indexed store, recommended SQLite**, for session summaries, eligible candidate index, decisions and change history. No ORM, generic migration framework or duplicate JSON selection store; choose safe pragmas and database durability with targeted crash/lock tests. Enforce schema version, integrity and contained file ownership. Heavy arrays/images do not go in SQLite.
- Avoid duplicating complete Detect Results into Review storage: hold stable validated references plus a projection/index of fields needed for efficient sort/filter/reopen. Verify against source Result digest at open/export. Content fingerprints and source relink state must not be silently reassigned.
- Session display names are editable, sanitized and human-facing. Internal IDs are persisted but not prominent in UI. Reopening uses the last logical view, item, filter, scroll position and selection where reasonable, without making presentation state scientific provenance.
- Active session and Worker state are different: one session can remain open with no Worker; one Worker may generate/cache or export while the user navigates. Respect existing suite-wide scientific Worker admission; do not invent parallel operations that undermine ownership. Lightweight on-demand tasks may use a supervised bounded background executor if safe, but their cancellation/lifetime still must be explicit and tested.
## Complete requirement-to-owner coverage (no orphan decisions)

The owning stage must assert the requirement or link to an exact acceptance test. RV-08 audits every row below; a missing gate blocks qualification. Common invariants in this index apply to all stages, but implementation and tests belong **only** to the named stage.

| Locked requirement | Owning spec / gate |
|---|---|
| Detect Result only; CNN-all, RF-accepted only; RF rejected/unscored invisible | RV-01, RV-08 |
| Original Result/recording source-frame timestamps, digests, parent lineage immutable | RV-01, RV-02, RV-03, RV-06 |
| App-owned `review/v1` paths; protected source relinking and privacy | RV-01; RV-08 checks all stages |
| Exactly Unreviewed / Call / Not a call; individual versus bulk provenance | RV-02 |
| Accept all affects only unreviewed eligible; atomic bulk undo | RV-02, RV-05 |
| One explicitly Open session; Close pauses; Resume retains annotations | RV-02, RV-07 |
| Finalize freezes and can be followed by linked new editable session | RV-02 |
| No full-recording timeline, false-negative authoring, boundary editing, new classes | RV-01, RV-03, RV-05 |
| Audible clip and own spectrogram with context; detection marked; Prev/Next | RV-03, RV-05 |
| Fixed non-configurable English-keyboard home-row shortcuts F/D/S (labels), J/K/L (navigation/play), arrow/Space alternatives, Ctrl/⌘Z (undo); hover/focus action tooltips and one reference listing; focus safety and auto-advance after successful save | RV-03, RV-05; RV-08 qualifies |
| 50k-scale Gallery/List/One by one virtualized and persistent navigation state | RV-05 |
| Async on-demand/prefetch/Generate all, bounded queues and cancellation | RV-04 |
| REV-05 size/peak/free-space before bulk, retry/recheck, no reimplementation | REV-05 prerequisite, RV-04, RV-06 |
| Automatic cache eviction; individual/multi flush labeled or not; regenerate | RV-04 |
| Image cache never owns labels, source WAVs, Result or finalized data | RV-02, RV-04 |
| Mixed partial export includes unreviewed model-only; rejected excluded | RV-06 |
| One finalization/export path; no direct-export bypass; all three formats | RV-05, RV-06, RV-07 |
| Export owner moved Detect → Review; historical receipts/readers survive | RV-06, RV-07 |
| Remove 10,000 cap across plan/write/verify/reopen and scalable metadata at ≥50k | RV-06 |
| Frame-exact PCM, Raven, digest, atomic publication; >4GiB concat guarded | RV-06 |
| Open-session quit warning from any workspace, combined Worker prompt | RV-07 |
| Human-readable labels, no decorative information or developer jargon | RV-05 |
| Public `alp-ui` status icons or independent upstream generic change | RV-05 and upstream gate |
| Toolbox scientific transform only if proven needed; own upstream branch | RV-03 and upstream gate |
| Full Qt/audio/Worker validation at owning seams; whole app at final stage | RV-03–RV-08 |
| macOS/Windows installers untouched; no unapproved Git pushes/merges | Every gate, RV-08 |

## Cross-cutting failure, privacy and immutability guarantees

| Risk / event | Required enforceable guarantee | Primary stage |
|---|---|---|
| Source missing after Detect | Session/labels/finalized data remain readable; audio/render/export require explicit relink and validation | RV-01, RV-03, RV-06 |
| Source moved | Relink through Detect's validated inventory identity/revision contract; never automatically accept another folder's WAV | RV-01, RV-07 |
| Source changed | Recheck source hash, header, frame count/rate/channel and relevant inventory facts; block WAV-dependent work until original restored | RV-01, RV-03, RV-06 |
| Result corrupt or replaced | Reject unsupported schema/digest/lineage or invalid candidate set; do not silently treat as empty or rebase existing labels to new IDs | RV-01, RV-02 |
| Session save failure | Show approved actionable error; previous committed label remains authoritative; no auto-advance or false success | RV-02, RV-05 |
| App crash / forced exit | Transactional label persistence; recover committed state and reconcile interruption; source files and finalized snapshots unchanged | RV-02, RV-07 |
| Double session / competing process | One Open session, protected ownership/revision check; no second unsupervised write stream | RV-02, RV-07 |
| Spectrogram failure/cancel | No partially rendered image counted valid; retry/regenerate; labels unaffected | RV-03, RV-04 |
| Cache pressure/corruption | Bounded eviction/regeneration; no deletion outside cache containment; no scientific artifact loss | RV-04 |
| Unknown/tight/insufficient space | REV-05 per-destination decision, clear warning and recheck; disk-full still caught at Worker I/O | RV-04, RV-06 |
| Export invalid format/large WAV | Reject mode before publication and offer supported alternative; no silent resampling/downmix/truncation | RV-06 |
| Export failure/cancel/crash | Incomplete private staging cleaned/reconciled; finalization survives; never return false success or partially overwrite destination | RV-06 |
| Export succeeds, history write fails | Keep verified output, reconcile receipt/history idempotently, avoid duplicate publication | RV-06 |
| Reopening finalized session | Create linked independent child; parent content and provenance remain byte-for-byte unchanged | RV-02 |
| Quit from Train or Detect | One Review-aware confirmation; Save and Exit saves/closes, stops work safely; canceled exit retains everything | RV-07 |
| Untrusted paths/metadata | Bounded loads; strict relative references, traversal/symlink/collision/size checks, no unsafe arbitrary model deserialization | All |
| User privacy | Diagnostics allowlist portable non-identifying fields; no absolute/home/HPC paths, WAV basenames, raw recording content or secrets in logs; no telemetry feature | All |

**Immutability:** input Model, CNN Result, RF-derived Result, original WAV bytes, finalized Review snapshot and previously published exports are distinct independently verifiable artifacts. A Review session may mutate only its own still-Open annotation store; closed sessions resume for editing, finalized do not. Cache may be removed/regenerated without changing any of those scientific digests. Exported source intervals never use context/window boundaries; candidate source times persist from original Detect Result. Maintain stable source identities even if the user's recording folder moves after an explicit verified relink. Do not claim missing files had zero candidates, nor claim unreviewed were verified.

**Atomic publish:** stage same-volume with private permissions, validate format and capacity, checksum output, no overwrite, publish only on full success, record/reconcile state. A Worker process exit code is not sufficient proof. Follow the preexisting source-writer validation patterns; avoid new global recovery subsystems.
## Git and test-index discipline

- Read [Git delivery](../../agent/GIT_DELIVERY.md) and source checkout before each stage, confirm `git status`/branch/SHA, and start `review-rvNN-<purpose>` from the last owner-reviewed Review integration baseline (create it only after explicit owner approval). No editing unrelated Train behavior, installers or sibling libraries.
- Stage acceptance case identifiers are *proposals*: register owning cases in [unit](../../UNIT_TESTING.md) and [integration](../../INTEGRATION_TEST_BEHAVIORS.md) indexes during that stage's TDD, not in this planning-only patch. Use [fixture index](../../INTEGRATION_TEST_DATA.md), minimum real boundary samples and existing regression anchors. No duplicate test index.
- Before each implementation commit: owning cases + affected regressions + full feasible ordinary suites, Ruff, test-ID audit and source immutability check. Native screenshots and real audio/Worker acceptance at owning boundaries; >=600-second soak only with separate authorization. Exact pass/fail/blocked/deferred evidence and SHAs, no invented pass.
- Entire Train→Detect→Review→Export E2E test belongs to **RV-08 only**, updating existing ST-11-owned cases in place. Any `alp-ui` or scientific-toolbox gap needs a separate repository branch, test, commit, SHA and downstream requalification.
- Reviewed local integration requires separate owner approval. **Never automatically push, open a PR, merge, tag, publish or perform macOS/Windows release tasks.**

