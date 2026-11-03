# Review specification coverage audit — prototype

**Basis:** original `biocall-studio-20261103-141026.zip`, specifically `docs/specs/review/README.md` and all `RV-01` through `RV-08` documents; inspected in full against the actual delivered HTML/CSS/JavaScript. **Status:** proposed design for owner inspection, not Review implementation or owner approval. **Only Review planning docs `README.md`, `RV-03`, `RV-05` and `RV-08` were updated to synchronize the owner-requested shortcut/tooltip proposal. No native code or test index was changed.**

## Stage-by-stage traceability

| Approved stage | Demonstrated in the interactive prototype | Not verified by this prototype; remains a native stage gate |
|---|---|---|
| **RV-01 — Result intake** | Completed-Result-only landing; independently selectable original Marsh CNN Result (**26 eligible**) and derived RF Result (**17 accepted-only**); separate Meadow CNN Result; model kind and eligible count; zero-Results demo; no general WAV import or RF-rejected filter. | Real `DetectionResult`/`DerivedResult` schema/digest/parent/lineage validation; source/frame identity, ordering/uniqueness, collection inventory and secure relink; corrupted/unsupported Result rejection; `review/v1` app-owned paths. |
| **RV-02 — Sessions/labels** | One Open session; editable name; Call/Not a call/Unreviewed; individual/bulk/model-only origins; Accept all preserves existing Call/Not a call; undo; Close→Resume preserves position/view; partial warning; Finalized read-only; independent successor; persistence-failure demo prevents label, Close, Finalize and Exit from pretending success. | Indexed transactional SQLite and crash recovery, reliable write/revision locks, multi-instance conflict prevention, atomic 50k batch + bounded undo history, immutable versioned digest-bearing snapshots and independent finalized artifact storage. Browser storage is illustrative. |
| **RV-03 — Audio/spectrograms** | Locally generated six-second audible WAV clips with reproducible corresponding illustrative spectrogram images, time/frequency axes and marked ~2-second pre-context interval; working Play/Pause/seek; Previous/Next and shortcuts; no interval editor or full-recording annotation. Missing/changed examples disable playback and surface the approved text. | Original-PCM frame-exact window reads and clamping, actual source sampling/stereo policy, numerical FFT reference checks, validated render settings/source content keys, Qt multimedia device tests, real playback/recording hashes. |
| **RV-04 — Hybrid cache/preflight** | On-demand thumbnails, nearby prefetch, bounded Gallery DOM, Generate all/progress/Cancel, Clear for item/selection/all regardless of label, logical eviction/regeneration, renderer Retry, tight/unknown/insufficient capacity scenarios; stale/missing input blocks bulk generation. | Real async supervised Worker/admission policy, rechecking actual REV-05 estimate before writes, disk-byte measurements, durable cache manifest, bounded queues/worker leases, safe path containment, crash/permission/disk-full recovery. |
| **RV-05 — Native UI** | Three coordinated views; dense sortable/filtered List and Gallery, multiple selection and bulk actions; sorted full-set One by one navigation that remains free to revisit previously labeled candidates; save-then-advance to the next Unreviewed without wrap-around; status shapes/text; progress and exact approved principal action/warning copy; 700/520 px browser captures. | Real PySide6 + installed public `alp-ui`, native focus/screen-reader/accessibility/150%-scale evidence, native model/view memory/timing measurements and `UT-REVW-009`/`IT-REVW-007/008`. Owner must review new wording separately. |
| **RV-06 — Corpus export** | Export only after Finalize; Call plus model-only Unreviewed counts included, Not a call excluded; three approved format choices; destination, preflight, progress/Cancel, failure/retry, repeat export and simulated Show in folder; simulated combined-WAV size guard. | **No actual WAV, Raven TSV, provenance manifest, receipt, or directory is generated.** 10,001/50,000 **real** candidate publications; exact PCM/source-frame boundaries, streaming JSONL/receipt, checksum reopen, RIFF limit and mixed PCM compatibility, atomic no-clobber staging, legacy Detect v1 verification. |
| **RV-07 — Studio/Detect migration** | Studio/Train/Detect/Review navigation; retained Open session; one combined open+active-job exit warning; Keep app open/Save and Exit; simulated failing save preserves running app; Review is the sole **active** demo corpus-export UI. Train/Detect are reference screenshot surfaces. | Native controller and exit coordination, safe Worker shutdown/no orphan processes, real Detect export initiation route removal after RV-06, read-only legacy Detect receipts/history and all old artifacts unchanged. Original native Detect screenshot may still show historical Exports navigation; it is **not** an implemented new export route in the demo. |
| **RV-08 — Qualification** | Integrated illustrative browser flow and bounded DOM in the 50,000-candidate scenario; 103 passing browser checks covering base, recovery, spec gaps and session resume. | Genuine Train→Detect→Review→Export E2E, real source WAVs/Models and 50k scientific outputs, original checksums, ST-11-owned test updates, installed dependency SHAs, Qt/audio/Worker/device tests, Test-ID/Ruff/regression and owner sign-off. |

## Corrections made after this cross-check

1. **Original/derived Result relationship:** added an independent Marsh CNN original alongside its RF-refined Result; made Result kind explicit and corrected RF demo recording names.
2. **View-state restoration:** returning from Train/Detect retains Review scroll/selection; Close→Resume restores view, filter, sort and focused item. Lightweight state is also written to browser storage where available.
3. **Focused traversal:** Previous/Next follows the selected **sort order** rather than internal candidate indices. Gallery/List filter persists on return; One by one traverses the full sorted eligible set so previously labeled detections remain revisitable. A labeling action advances only to a *later* Unreviewed item; no unexpected wrap to the beginning.
4. **Missing/changed source safeguards:** playback, export and bulk spectrogram generation cannot produce a fake success when the relevant illustrative source is absent or changed.
5. **Failed-write behavior:** added a collapsed **Save failure** demo. Label/Accept all/Close/Finalize/Resume/Start/Exit roll back or remain in their prior state when saving is injected to fail. Display remains on the valid session.
6. **Bulk-origin correctness:** a single candidate labeled through a bulk action retains bulk provenance; individually confirming an already batch-accepted Call updates its origin and Undo restores the previous origin. Image eviction remains bounded even when many candidates are selected.
7. **Score display:** uses an illustrative numeric score rather than a misleading percentage that could suggest a calibrated biological probability.

## Shared REV-05 prerequisite

The original ZIP **does contain** a real shared preflight service in `src/biocall_studio/shared/storage.py` (`StorageEstimate`, `StorageDecision`, admission policy), Train and Detect consumers, `UT-SIZE-*` test definitions and a reviewed handoff in `docs/IMPLEMENTATION_SEQUENCE.md`. The Review index's caution about a 2026-11-02 snapshot is **historical**, not evidence that the current supplied ZIP lacks REV-05. No shared native preflight was reproduced in this prototype. Its example storage headings follow the *implemented* Detect/Train UI (`Estimated output`, `Space needed while running`, `Free on ...`), which takes precedence over an isolated wording variant in RV-05.

## Browser evidence and remaining approval boundary

Existing **57/57** main checks and **22/22** edge checks passed after the corrections; **20/20** additional spec regression checks, **1/1** Close/Resume view-state check and **3/3** additional provenance checks also passed. No JavaScript page/runtime errors were reported in these executions. See `evidence/browser-checks.txt`, `evidence/browser-edge-checks.txt`, and `evidence/browser-spec-audit.txt`.

**No remaining contradiction in the *interactive workflow* was found during this review.** That statement does not qualify the native data model, scientific output, free-space policy, actual 50k export, real integrity checks or application migration. The constrained Chromium environment still did not allow direct browser navigation to localhost or validation of a genuine-origin refresh; the owner's normal local-browser inspection is still required. The new-copy approval table remains in `PROTOTYPE_ACCEPTANCE_CHECKLIST.md`.


## Re-audit: fixed shortcuts, HelpHints and complete prototype-to-spec synchronization (2026-11-03)

**Source of truth:** [`RV-05`](../../../specs/review/RV-05-native-review-ui.md), with `RV-03` owning source/audio and `RV-08` owning native qualification. The original repository RV-01, RV-02, RV-04, RV-06 and RV-07 contracts were rechecked and **not changed**. The four changed documents (`README`, `RV-03`, `RV-05`, `RV-08`) are included in the synchronized deliverable; they do not assert that RV-01–RV-08 have been implemented. The owner-requested new shortcut/tooltips remain pending owner design approval.

| Review contract or visible UI | Prototype behavior, source and coverage | Result / outstanding qualification |
|---|---|---|
| Fixed English-keyboard labels | F Call, D Not a call, S Clear; saved before advancing, no advancement for clear/failure; no rebind UI | **Browser verified**; native Qt pending |
| Fixed home-row movement and listening | J Previous, K Play/Pause, L Next, with arrow/Space alternatives; previously labeled items revisitable, audio stops on navigation | **Browser verified**; native device pending |
| Undo and excluded contexts | Ctrl/⌘Z for Open Review only; not in Train/Detect/Studio, while typing, seek-slider or modal; no auto-repeat/modified letter actions | **Browser verified**; native shortcuts pending |
| Shortcut discoverability | One `Keyboard shortcuts` listing; on-button hover/**keyboard-focus** tooltip; `aria-keyshortcuts` on bound controls | **Browser verified** at 1280/700/520 px; actual screen reader/native access pending |
| Existing owner-approved HelpHints | Accept all: “Marks all unreviewed detections as calls. Existing labels won't change.”; Clear spectrograms: “Frees disk space by deleting generated images. Your labels and recordings stay unchanged.” | **Verbatim checked** against RV-05, pointer and focus; no competing duplicate tooltip |
| Dialog focus and dismissal | A single concise shortcut reference, focus trapped, Escape dismisses and returns focus; confirmations retain approved text | **Browser verified** |
| Gallery/List search and sorting | Compact recording-name search added to both tabular views; consistent status/filter/sort/selection; focus mode intentionally traverses full *eligible* sorted set | **Browser verified**; native indexed model/search pending |
| Selected Result and RF boundary | CNN original independently accessible; RF-derived exposes accepted-only candidate set; filters/search/focus never expose rejected/unscored | **Simulated fixture checked**; real manifest integrity pending |
| Sessions and provenance | Open/Closed/Finalized/Continue in new session, state restore and bulk/individual/model-only origins; exact partial warning; no direct export | **Browser verified**; SQLite/immutable snapshots pending |
| Generation, failure and cache ownership | Generate all/Cancel/Retry, missing/changed WAV block, clear selected or all irrespective of label; cache regeneration retains labels | **Browser logic verified**; actual Workers/cache files pending |
| REV-05 estimates and capacity | Existing native `Estimated output` / `Space needed while running` / `Free on ...` display convention; no new preflight framework | **Illustrative values**; measured native preflight pending |
| Finalized corpus export and recovery | Three RV-06 formats, partial Call+model-only Unreviewed, Not a call excluded, failure/cancel/retry, simulated Show in folder | **Browser verified**; actual WAV/TSV, receipts, streaming 50k, atomic publication pending |
| Studio navigation and global exit | Review Open preserved when visiting Train/Detect; unified Open+Worker warning, save-failure rollback, Keep app open | **Browser verified**; native window/Worker shutdown pending |
| Large and compact data | 50,000-candidate bounded Gallery/List elements; no 50k heavyweight tiles; 700/520 px action/tooltip accessibility | **Browser verified**; native timing, scaling and full assistive-tech audit pending |

### Tooltip and interface-copy inventory

Only the following **researcher-action** tooltips remain in the prototype. This inventory explicitly distinguishes the **two approved HelpHints** from the **new owner-requested shortcut proposals** and the **new inspect action hint**:

| Category | Exact rendered tooltip wording | Approval boundary |
|---|---|---|
| Existing HelpHint | “Marks all unreviewed detections as calls. Existing labels won't change.” | Already approved RV-05 |
| Existing HelpHint | “Frees disk space by deleting generated images. Your labels and recordings stay unchanged.” | Already approved RV-05 |
| Fixed labeling keys | “Call · F”; “Not a call · D”; “Clear label · S” | Owner-requested addition, awaiting visual sign-off |
| Fixed navigation/audio keys | “Previous · J or ←”; “Play / Pause · K or Space”; “Next · L or →” | Owner-requested addition, awaiting visual sign-off |
| Fixed Undo/reference | “Undo last label action · Ctrl/⌘+Z”; “Show the fixed Review keyboard shortcuts.” | Owner-requested addition, awaiting visual sign-off |
| Inspect candidate | “Open in One by one” | Additional label for owner approval |
| Disabled session buttons (native browser `title`) | “Close the open session before starting another.”; “Close the open session before resuming another.” | Additional messages for owner approval |

Duplicate `title` hints on the session name, already-visible status/progress and session name pill were removed. Most controls use their readable action labels without any extra HelpHint. Tooltips do not contain implementation terms, raw IDs, hashes or hidden workflow explanations.

### Executed browser evidence and remaining scope boundary

**57/57 primary**, **22/22 recovery**, **20/20 specification-regression**, **1/1 close/resume**, **3/3 provenance**, **69/69 fixed-shortcut and hover/focus**, and **17/17 tooltip synchronization** assertions pass in rendered Chromium. These are *executed checks* (some scenarios overlap), **not** 189 unique scientific tests. No recorded page/JavaScript runtime errors. New screenshots: `evidence/12-shortcut-reference.png`, `evidence/13-shortcut-tooltip-700.png`, and `evidence/13-shortcut-tooltip-520.png`.

**Honest scope:** all approved researcher-facing *prototype flows* are represented consistently with the unchanged Review rules; this is not an assertion that every scientific/data-integrity/native requirement is implemented. The explicit RV-01–RV-08 stage gates in the original coverage table remain **unverified** wherever they require real Results, validated source WAVs, transactional persistence, Qt/`alp-ui`, Workers, filesystem preflight, actual exports, immutable receipts or native 50k qualification. Direct localhost browser navigation/real-origin refresh remains unverified due to sandbox restrictions. No spec changes declare the prototype owner-approved.


## Scientific spectrogram generation and settings — RV-01 through RV-08 synchronization (2026-11-03)

The prior shortcut re-audit above documents the earlier prototype revision. Owner approval of Q1–Q8 now adds the following **targeted planned obligations**; the full native Review subsystem remains unimplemented. The research specification `docs/specs/review/SPECTROGRAM_GENERATION_INVESTIGATION.md` requires measurements and numerical reference tests **before** final generator choices are locked.

| Stage | Planned specification location | Interactive representation | Required separate qualification |
|---|---|---|---|
| RV-01 | Spectrogram preset reference does not expand Result intake/eligible set | Choose Result → select preset; Test WAV restricted to settings | Candidate/Result boundary, invalid standalone WAV never creates Review record |
| RV-02 | Frozen effective session snapshot; edit/delete and Closed/Finalized/successor semantics | Save preset with usage counts; Save and use in this session; Change preset | SQLite durable snapshot, rollback, immutable Finalized, successor inheritance |
| RV-03 | Python STFT, power-average stereo, context boundaries, image-only pixels and Qt axes | Bounded Test WAV spectrum; Gallery/One-by-one mock axes | Golden numerical tone/impulse/stereo tests; Qt frame/pixel/HiDPI mapping |
| RV-04 | Revisioned content identity and safe cache invalidation; calibrated incremental sizing using REV-05 | Change preset estimate, image invalidation, Generate all thumbs, cancel/retry | Worker stale-publication/crash, cache-sharing, free-space unknown/full, calibration |
| RV-05 | Five simple controls, minimal Advanced, Default/user presets, HelpHints, saved examples | Spectrograms → Settings, Test WAV/Compare, edit/confirm/delete | Public `alp-ui`, accessible widgets, copy consistency, compact 520px |
| RV-06 | Frozen finalization provenance, no image dependency of corpus export | Finalized session read-only despite user preset changes | Export byte/truth-table parity after edits and cache deletion |
| RV-07 | Settings route under Review and supervised generation work on navigation/exit | Global shell, active Review session preserved | Worker lifetime, exit, source tamper and same-session concurrency |
| RV-08 | Cross-stage science/UX/stress qualification & prior shortcut preservation | 17 new browser checks; existing fixed bindings still present | Actual Python/Qt, representative 50k sizing, all native + previously approved regression cases |

**Verified here:** a *focused* 17/17 browser check run in a constrained Chromium environment with a local WAV numerical preview; source is `evidence/spectrogram-settings-browser-checks.txt`. Not verified: prior full browser suite rerun, Python/R scientific parity, Qt, disk and 50k workloads. The root-level `UX_PARITY_MATRIX.md` and `PROTOTYPE_ACCEPTANCE.md` were missing from this ZIP and remain explicit external parity blockers.
