# Indexed integration-test behaviors — Trainer

All rows are **target acceptance criteria**, not claims of implementation or a passing test. Test functions that establish a row must contain its exact `IT-*` ID in the test-function docstring, cover each observable assertion, and execute successfully on the required real boundary. Detailed pure variants live in [`UNIT_TESTING.md`](UNIT_TESTING.md). Minimum differentiating resources are listed in [`INTEGRATION_TEST_DATA.md`](INTEGRATION_TEST_DATA.md).

## 1. Shell and native UI (spec 01)

| Case ID | Public seam / expected result | Data |
|---|---|---|
| `IT-UI-001` | Native Qt/`alp-ui` launches, Select Collection primary action and Wiki navigate; the app-owned Light color scheme prevents host Dark appearance from producing mixed/unreadable viewports, resources render and back/focus navigation survives page changes. | TD-UI |
| `IT-UI-002` | Test-isolated Application Settings retain valid Collection binding across restart and support explicit rebind; original input WAV bytes remain untouched. | TD-COL, TD-PATH |
| `IT-UI-003` | Updated public `alp-ui` `FolderPicker` is used in actual native Select UI: folderChanged routes pending selection, cancellation leaves previous path/verification unchanged and does not start scan; accessible full path and keyboard operate. | TD-UI, TD-COL |
| `IT-UI-004` | Prototype Select/Wiki/empty-state structure is exercised with real `alp-ui` Widgets, an accessible inline Wiki action, keyboard Tab/Space and HelpHint, and no demo scientific completions. **Separately required native macOS evidence:** persist real Trainer screenshots (not only pytest tmp files), compare side by side with both bundled prototype and sibling Showcase, log deviations and update README with truthful native shots before claiming UI acceptance. | TD-UI |
| `IT-UI-005` | The UI-pass revision uses readable `alp-ui` typography, concise non-redundant copy with no user-facing internal IDs, a top-right Run state, and top-to-bottom numbered preparation. A Training draft stays visibly reopenable until discarded or launched. Dataset/Model/Run names are editable; Collection unbind and Dataset/Model/terminal-Run delete actions are confirmed, contained, and non-cascading. Active Run activity sits beside progress and Output remains below. | TD-UI, TD-PATH, TD-RUN |


## 1a. Studio shell (ST-02)

| Case ID | Public seam / expected result | Data |
|---|---|---|
| `IT-STU-001` | New Studio entry creates one themed `QApplication`, shows branded launchpad; accessible cards, keyboard/focus and visible Studio identity use native Qt/`alp-ui`. | TD-UI |
| `IT-STU-002` | Studio → real Train → Studio → Train reuses controller/window, preserves current Train route and live training draft, and leaves Collection bindings and input WAV unchanged. Return control works at compact widths. | TD-UI, TD-COL |
| `IT-STU-003` | Real Train QProcess Run and scan remain active while visiting Studio; application Quit from either visible/hidden workspace preserves Train's single safe close/cancel/keep-open policy and releases Worker/lease/resources only after confirmed stop. | TD-RUN, TD-FAIL, TD-UI |
| `IT-STU-004` | Canonical Studio entry retains a validated Train binding under isolated suite data while supervised Train work launches through the canonical private Worker protocol. | TD-UI, TD-CACHE |
| `IT-STU-005` | Detect Collection setup and Review placeholder have reachable, keyboard-operable returns; Detect adds no invented Model, inventory, prediction, result, simulated value or enabled detection action. | TD-UI |
| `IT-STU-006` | Real native Studio/Train/Detect/Review screenshots at normal and compact widths show checked-in branding, focus and contrast; no Train layout regression or inaccessible switch; report unavailable native platforms separately. | TD-UI, TD-OS |

**Reported status:** ST-02 implements `IT-STU-001`–`006` in
`tests/integration/test_studio_shell.py`. Genuine macOS Cocoa evidence and its environment/deviation
record are under `design/evidence/st-02-native/`; installed and Windows qualification remain open.

## 1b. Stage-owned Detect integration cases (ST-03–ST-10)

ST-03 implements `IT-DET-001`–`002`; ST-04 implements `IT-DET-003`–`005`; ST-05 implements
`IT-DET-006`–`008`; and ST-06 implements `IT-DET-009`–`011` pending owner review. ST-07–ST-10
rows remain planned, unexecuted acceptance contracts. Each stage implements **only its own rows**,
using genuine
Qt/Worker/WAV/scientific boundaries where named. The whole-Studio E2E appears exclusively in ST-11.
No planned case counts as covered.

| Case ID | Public seam / expected result | Data | Spec |
|---|---|---|---|
| `IT-DET-001` | real temporary directory create→reopen→move→explicit relink via native Qt; cancel/denied access keep prior Collection intact | TD-UI, TD-PATH, TD-CACHE | [ST-03](specs/ST-03-detect-workspace.md) |
| `IT-DET-002` | actual app-owned files and permissions, corrupt/unsupported manifest, interrupted write, symlink escape and untouched recording bytes | TD-PATH, TD-FAIL | [ST-03](specs/ST-03-detect-workspace.md) |
| `IT-DET-003` | real nested mono/stereo WAVs; nested generated snippets, symlink loop/escape and path collision; correct deterministic included inventory and no source writes | TD-WAV, TD-PATH, TD-COL | [ST-04](specs/ST-04-wav-discovery.md) |
| `IT-DET-004` | truncated/unsupported headers, permissions, edited/missing files, many-row bounded scan, cancel/restart/rescan without false completion | TD-WAV, TD-CACHE, TD-SCALE, TD-FAIL | [ST-04](specs/ST-04-wav-discovery.md) |
| `IT-DET-005` | genuine Qt selection, folder decisions, count updates, paging, keyboard, canceled picker, native screenshots and state transitions | TD-UI, TD-SCALE | [ST-04](specs/ST-04-wav-discovery.md) |
| `IT-DET-006` | trusted genuinely Train-exported CNN and RF Models load/inspect in fresh process via verified installed toolbox, without source-tree runtime dependency | TD-EXPORT, TD-TRAIN | [ST-05](specs/ST-05-model-intake.md) |
| `IT-DET-007` | missing/corrupt/checksum-swapped binary, extra class, feature-order mismatch, unsupported runtime, unsafe path, explicit untrusted user artifact denied | TD-EXPORT, TD-FAIL, TD-PATH | [ST-05](specs/ST-05-model-intake.md) |
| `IT-DET-008` | real Qt Model selection/reopen states and readiness gating without Worker launch | TD-UI, TD-EXPORT | [ST-05](specs/ST-05-model-intake.md) |
| `IT-DET-009` | real short QProcess worker, progress, bounded cancellation, forced loss and restart; no success without verified receipt | TD-RUN, TD-FAIL | [ST-06](specs/ST-06-detect-workers.md) |
| `IT-DET-010` | genuine Qt event-loop responsiveness, Run header, keyboard cancel and large stderr/log privacy checks | TD-UI, TD-RUN, TD-PATH | [ST-06](specs/ST-06-detect-workers.md) |
| `IT-DET-011` | actual staging/publication failure, permissions/collision, source reservation and reconciliation of valid versus incomplete output | TD-FAIL, TD-RUN | [ST-06](specs/ST-06-detect-workers.md) |
| `IT-DET-012` | real-WAV CPU CNN inference compared numerically to verified upstream reference output, class order and frame intervals | TD-WAV, TD-EXPORT, TD-TRAIN | [ST-07](specs/ST-07-cnn-detection.md) |
| `IT-DET-013` | real Run→checksum-valid metadata Result reopen; source non-mutation, zero candidates vs failed-file contrast, worker/GUI progress | TD-WAV, TD-RUN, TD-UI | [ST-07](specs/ST-07-cnn-detection.md) |
| `IT-DET-014` | stale/replaced WAV/Model, unsupported shape, cancelled Worker, crash, invalid receipt, atomic failure | TD-FAIL, TD-CACHE, TD-RUN | [ST-07](specs/ST-07-cnn-detection.md) |
| `IT-DET-015` | real Qt Result selection, recording switch, interval IDs, history and keyboard navigation on genuine ST-07 Result | TD-UI, TD-RUN, TD-SCALE | [ST-08](specs/ST-08-results-ux.md) |
| `IT-DET-016` | corrupted/unavailable source, empty/error/partial Result, persisted selection and actual normal/compact native screenshots without artifact mutation | TD-UI, TD-CACHE, TD-FAIL | [ST-08](specs/ST-08-results-ux.md) |
| `IT-DET-017` | genuine WAV segments and trusted RF Model, reference feature-vector/probability parity; original/derived persisted independently and native selection works | TD-TRAIN, TD-EXPORT, TD-WAV, TD-UI | [ST-09](specs/ST-09-rf-refinement.md) |
| `IT-DET-018` | wrong feature order/Model, missing/short/stale recording, cancelled/crashed Worker and atomic failure; original Result bytes unchanged | TD-FAIL, TD-RUN, TD-WAV | [ST-09](specs/ST-09-rf-refinement.md) |
| `IT-DET-019` | compare real snippet PCM samples, headers, checksums and original timestamps byte-by-byte/frame-by-frame | TD-WAV, TD-PATH | [ST-10](specs/ST-10-corpus-export.md) |
| `IT-DET-020` | real concatenated WAV plus Raven TSV offsets and both-mode receipt on distinct sources; reopen all outputs | TD-WAV, TD-FAIL | [ST-10](specs/ST-10-corpus-export.md) |
| `IT-DET-021` | real stale/permission/collision/disk error/cancel and destination Show in folder in native Qt; no partial visible success or source mutation | TD-UI, TD-PATH, TD-FAIL, TD-RUN | [ST-10](specs/ST-10-corpus-export.md) |

## 1c. Planned post-ST-10 revision integration (REV-01–REV-03)

These cases execute only after the owning revision's predecessor is reviewed. They remain scoped
package, workflow or widget-boundary checks; they do not introduce the whole-Studio scientific E2E
reserved for ST-11.

| Case ID | Public seam / expected result | Data | Spec |
|---|---|---|---|
| `IT-STU-009` | Build and clean-install the unified wheel; only `biocall_studio` and the canonical command are exposed, the removed package/command fail, the native shell starts, and real Train/Detect supervised Workers launch through canonical private modes with unchanged input WAV bytes and equivalent fresh artifacts. | TD-UI, TD-RUN, TD-WAV, TD-TRAIN, TD-EXPORT | [REV-01](specs/manual_revision_specs/REV-01-project-consolidation.md) |
| `IT-DET-023` | Real Qt sidebar plus Back/Continue focus exercise Models→Recordings→New detection settings, Start without returning to Models, active/completed Run transition, bulk inclusion confirmation, CNN/RF semantic states, and selection-free Export planning with no artifact publication at normal/compact widths. | TD-UI, TD-WAV, TD-RUN, TD-FAIL | [REV-02](specs/manual_revision_specs/REV-02-detect-guided-workflow.md), [REV-04](specs/manual_revision_specs/REV-04-Detect-Navigation-and-History.md) |
| `IT-UI-006` | Native Studio launch uses only approved launch copy and one readable light theme under host dark appearance, exposes no theme control and preserves keyboard/focus behavior at normal/compact widths and 100%/150% scaling. | TD-UI, TD-OS | [REV-03](specs/manual_revision_specs/REV-03-interface-language-and-theme.md) |
| `IT-TRAIN-015` | Every Train page and all 67 configuration fields expose the owner-approved contextual/configuration/disabled-choice tooltip decisions through real keyboard-accessible Qt HelpHints and descriptions; removed hints and rejected visible copy are absent. | TD-CONFIG, TD-UI | [REV-03](specs/manual_revision_specs/REV-03-interface-language-and-theme.md) |
| `IT-DET-024` | Every final Detect route/state uses approved HelpHints and recordings-folder terminology, removes duplicate prompts/alerts and renders concise actionable Model/Result states while preserving missing/empty/stale/partial distinctions. | TD-UI, TD-FAIL, TD-CACHE | [REV-03](specs/manual_revision_specs/REV-03-interface-language-and-theme.md) |
| `IT-DET-025` | Real Qt persistent Detect sidebar navigation, Models→Recordings→New detection flow, newest-first Runs list/detail, active-Run indicator, keyboard focus, and normal/compact layouts without page-level horizontal scrolling. | TD-UI, TD-WAV, TD-RUN | [REV-04](specs/manual_revision_specs/REV-04-Detect-Navigation-and-History.md) |
| `IT-DET-026` | Multiple exports from one Result, restart persistence, background verification of available/missing/inaccessible/changed destinations, corrupt/symlink history isolation, cancellation, and post-publication history-write failure without source mutation. | TD-UI, TD-WAV, TD-EXPORT, TD-PATH, TD-FAIL | [REV-04](specs/manual_revision_specs/REV-04-Detect-Navigation-and-History.md) |

## 1d. Planned whole-Studio integration (ST-11 ONLY)

| Case ID | Public seam / expected result | Data | Spec |
|---|---|---|---|
| `IT-DET-022` | end-to-end **scientific round trip** cross-checking source CNN→RF→export frame times, class/feature parity, checksums and TSV rows against reference numeric outputs | TD-WAV, TD-EXPORT, TD-TRAIN | [ST-11](specs/ST-11-unified-qualification.md) |
| `IT-STU-007` | **one genuine whole-Studio scenario**: retained Train and trusted Model, Detect Collection/scan/CNN/Results/RF/export, restart/relink/provenance, unchanged originals, native navigation and user-visible success | TD-UI, TD-RUN, TD-WAV, TD-TRAIN, TD-EXPORT | [ST-11](specs/ST-11-unified-qualification.md) |
| `IT-STU-008` | real Qt/QProcess cross-workspace active operation/exit contention, keep-open/confirm, crash recovery and no orphaned workers without altering Train's existing behavior | TD-RUN, TD-FAIL, TD-UI | [ST-11](specs/ST-11-unified-qualification.md) |

## 2. Collection Scan and metadata (spec 02)

| Case ID | Public seam / expected result | Data |
|---|---|---|
| `IT-COL-001` | Selecting a real valid folder starts nonblocking Reading Collection activity; progress and cancel are observable; overview shows correct counts/durations/source→positives mapping. | TD-COL, TD-WAV |
| `IT-COL-002` | Missing folder, unsupported/nested entry, malformed positive/time/source mapping, duplicate/collision, unreadable WAV each yields exact relative-path error and blocks Build; no source files modified. | TD-COL, TD-WAV, TD-PATH |
| `IT-COL-003` | Successful scan writes versioned `.alpaca/collection.json` and bounded JSONL partition metadata; reopens in a new app process/controller with identical validated facts. | TD-CACHE |
| `IT-COL-004` | Add/remove/change positive or recording invalidates only affected cached entries; changed headers are reread, removed facts disappear, and Build refuses stale inputs. | TD-CACHE, TD-WAV |
| `IT-COL-005` | Cancel, permission failure or interrupted metadata replacement cannot publish a false valid cache; next scan recovers; input bytes remain unchanged. | TD-CACHE, TD-FAIL |
| `IT-COL-006` | Symlink escape/path containment and a moved/rebound Collection cannot bypass checks on read or cache hit; portable references contain no host-absolute path. | TD-PATH, TD-CACHE |
| `IT-COL-007` | A generated large Collection index is paged through real Qt model; responsive navigation and bounded metadata/header I/O without full-recording decoding. | TD-SCALE |
| `IT-COL-008` | Native Qt Reading/Collection/Validation UI matches prototype section hierarchy, progress/cancel, issue guidance, CTA gating, navigation and resized view with real WAV scan state. `alp-ui` Showcase style, screenshots and six-dimension manual review are evidenced; no unapproved deviations. | TD-UI, TD-COL, TD-WAV |

## 3. Dataset Build (spec 03)

| Case ID | Public seam / expected result | Data |
|---|---|---|
| `IT-DB-001` | From validated Collection/config, actual Source Recording audio is seek-read into **single-label** target/noise Dataset Snippets (exactly one of the two labels per Snippet), with exact source intervals, labels, protected margins, manifest and reproducible grouped Splits. | TD-MINE, TD-SPLIT, TD-WAV |
| `IT-DB-002` | Same inputs/config/seed produce equivalent Snippets/Splits/provenance (excluding new IDs); changed settings publish an independent Dataset and never rewrite the original. | TD-MINE, TD-SPLIT |
| `IT-DB-003` | No eligible negatives, changed/missing source or invalid config fails cleanly; no completed Dataset appears, staged leftovers are safely identified, and originals remain byte-identical. | TD-MINE, TD-FAIL |
| `IT-DB-004` | Dataset detail reopens complete immutable manifest, split counts and materialized files; deletion is explicit, rejects active input reservation and does not erase any existing Model. | TD-SPLIT, TD-RUN |
| `IT-DB-005` | Native Builder/Dataset views match prototype recording selection, controls/hints, count preview, disabled/underfill and Dataset detail/list flows; real config/Run state, accessible Qt interactions and native evidence pass six-dimension review. | TD-UI, TD-MINE, TD-SPLIT |

Spec 03 implementation evidence: `tests/integration/test_dataset_build.py` asserts all five rows at
their real artifact, QProcess and native-widget seams. The tracked Cocoa comparison set and
six-dimension review are in [`design/evidence/spec-03-native/`](design/evidence/spec-03-native/) and
the [evidence ledger](design/evidence/README.md). Spec 04 still owns persisted Run lifecycle,
cancellation/recovery and every `IT-RUN-*` case.

## 4. Run and Worker boundary (spec 04)

| Case ID | Public seam / expected result | Data |
|---|---|---|
| `IT-RUN-001` | Real QProcess Worker for Dataset Build moves through persisted starting/running/completed and valid final Artifact; Active Run remains navigable. | TD-RUN |
| `IT-RUN-002` | Within one `WorkspaceController`/application process, a second requested Run conflicts while one is active; locked input deletion/rebind conflicts; read-only browsing proceeds; terminal state releases reservation. No cross-application-process exclusivity contract is established. | TD-RUN |
| `IT-RUN-003` | Real cancellation and forced process loss produce cancelled/interrupted state after bounded reconciliation, no false published artifact and no eternal Active Run after restart. | TD-RUN, TD-FAIL |
| `IT-RUN-004` | Artifact/staging name collision, corrupt publication or worker nonzero exit fails without overwriting a published Dataset/Model or promoting a stale output pointer. | TD-RUN, TD-FAIL |
| `IT-RUN-005` | Native Run detail/history/Active Run sidebar reflect prototype section ordering, progress, cancel, conflict and terminal states through real Worker events; keyboard navigation and native evidence pass six-dimension review. | TD-UI, TD-RUN, TD-FAIL |
| `IT-RUN-006` | Native close/quit during an Active Run presents one accessible safe-default confirmation; dismiss/Keep open preserves the exact Worker and progress, while confirmed exit requests stopping once. Idle/completed close has no warning and active Scan shutdown remains safe. | TD-UI, TD-RUN |
| `IT-RUN-007` | Confirmed exit during real Dataset Build/CNN/RF stops the supervised Worker before window exit, records an honest cancelled/interrupted result, removes incomplete stage/output/checkpoints, preserves inputs and prior artifacts, and retains a fully committed matching output at the receipt boundary. | TD-RUN, TD-FAIL, TD-TRAIN |
| `IT-RUN-008` | Actual GUI-process loss releases its kernel-owned lease so a genuine Worker cannot later publish; restart reconciles safely, cleans orphan stage only after stop and retains a fully committed provenance-matching artifact. | TD-RUN, TD-FAIL, TD-TRAIN |
| `IT-RUN-009` | Explicit opt-in ≥600-second real-QProcess CNN durability run remains event-loop responsive during native navigation, records bounded resource/log/stage observations, publishes and structurally reloads a checksum-valid Model, then completes a second short reuse Run without a stale Worker. | TD-RUN, TD-TRAIN, TD-UI |
| `IT-POWER-001` | Settings and Training expose synchronized accessible keep-awake controls, canonical Wiki/help, persistence/reacquisition and truthful On/Off/Not active states; toggling remains independent of a real Run and failed settings writes do not misstate OS state. | TD-UI, TD-RUN, TD-FAIL |
| `IT-POWER-002` | Actual macOS/Windows adapter acquires/releases automatic idle-sleep inhibition and abnormal GUI-process death releases OS-owned protection; unsupported platforms are not claimed. | TD-FAIL |

Spec 04 implementation evidence: `tests/integration/test_run.py` asserts all five rows through real
QProcess, persistence, restart, reservation and native-widget seams. The tracked Cocoa comparison
set and six-dimension review are in
[`design/evidence/spec-04-native/`](design/evidence/spec-04-native/) and the
[evidence ledger](design/evidence/README.md). Packaged Worker launch remains owned by Spec 06.

Spec 05g extends the accepted lifecycle with `IT-RUN-006`–`009` and `IT-POWER-001`–`002`.
Its explicit soak is excluded from ordinary pytest selection and must be invoked with `-m soak`;
the [Spec 05g evidence ledger](design/evidence/README.md#spec-05g--long-running-runs-safe-exit-and-optional-keep-awake)
records the native platform, duration, resources, artifact hashes and UI review. Windows native
power and installed-app requalification remain owned by Specs 07 and 06/07 respectively.

## 4.5 Upstream PCM/WAV extraction — **Spec 04.5**

`IT-AUDIO-001`–`IT-AUDIO-004` are defined in [Spec 04.5](specs/SPEC_04_5_UPSTREAM_AUDIO_EXTRACTION.md): real-WAV byte equivalence, cancel/error cleanup, already-published Dataset compatibility and actual Worker import from the committed sibling toolbox. The spec is their **single detailed acceptance owner**; do not duplicate its cases here. Use `TD-WAV`, `TD-PATH`, `TD-SPLIT`, `TD-FAIL`.

| Case ID | Detailed owner | Data |
|---|---|---|
| `IT-AUDIO-001` | [Spec 04.5 exact acceptance case](specs/SPEC_04_5_UPSTREAM_AUDIO_EXTRACTION.md) | TD-WAV |
| `IT-AUDIO-002` | [Spec 04.5 exact acceptance case](specs/SPEC_04_5_UPSTREAM_AUDIO_EXTRACTION.md) | TD-WAV, TD-FAIL |
| `IT-AUDIO-003` | [Spec 04.5 exact acceptance case](specs/SPEC_04_5_UPSTREAM_AUDIO_EXTRACTION.md) | TD-WAV, TD-SPLIT, TD-FAIL |
| `IT-AUDIO-004` | [Spec 04.5 exact acceptance case](specs/SPEC_04_5_UPSTREAM_AUDIO_EXTRACTION.md) | TD-PATH, TD-FAIL |

## 5. CNN and RF Training + structurally reloadable Model exports (spec 05)

| Case ID | Public seam / expected result | Data |
|---|---|---|
| `IT-TRAIN-001` | Real CPU **binary single-label two-class** CNN Training via Worker on a published Dataset produces a loadable CNN Model/checkpoint, resolved config, train/val loss and valid Dataset provenance. | TD-TRAIN, TD-RUN |
| `IT-TRAIN-002` | Real two-class single-output RF Training via Worker on the **same** Dataset produces loadable estimator, ordered/versioned features, actual validation metrics and meaningful family-specific progress. | TD-TRAIN, TD-RUN |
| `IT-TRAIN-003` | Both Models reopen from manifests with stable IDs, readable labels, family display, Dataset reference, configurations and metrics; no inferred prediction support. | TD-TRAIN |
| `IT-TRAIN-004` | Bad Dataset Split/feature mismatch, missing input or undefined metric is blocked/reported accurately; failed Run does not publish a Model or fabricated metric. | TD-TRAIN, TD-FAIL |
| `IT-TRAIN-005` | Actual CNN epoch loss and actual RF ordered feature importance values reach `alp-ui` `Plot` using correct line/bar public APIs; plotted values/axes agree with saved real model/run metrics, with accessible numeric alternatives and family-specific meaning. | TD-TRAIN, TD-UI |
| `IT-TRAIN-006` | Undefined/NaN/missing metric or importance is not passed to Plot as fictitious zero; no RF epoch loss graph, HelpHint and family controls remain accessible; Model detail explains unavailability. | TD-TRAIN, TD-UI, TD-FAIL |
| `IT-TRAIN-007` | Native CNN/RF configuration, training charts, Model list/detail faithfully follow prototype structure/hints/actions with current `alp-ui` Showcase styling, real metrics and accessible Plot alternatives; native screenshots and reviewed exception ledger pass. | TD-UI, TD-TRAIN |

### Model export integrity (same Spec 05; no inference)

| Case ID | Public seam / expected result | Data |
|---|---|---|
| `IT-TRAIN-008` | From **genuinely trained binary single-label CNN and RF** artifacts, require both exactly-two-class export declarations/checkpoint-or-estimator cardinality and explicit class order; a fresh process reads each published manifest and structurally reloads only trusted local checkpoint/estimator bytes; saved resolved CNN architecture/state/class/spectrogram config and RF feature names/order/config/`classes_` match actual training; contents remain portable and intact. If the toolbox was changed upstream, exercise the **reinstalled, correctly resolved toolbox revision** in the Trainer `.venv` and record its SHA alongside both repo test results. **No new-WAV inference/scoring.** | TD-TRAIN, TD-EXPORT, TD-RUN |
| `IT-TRAIN-009` | Corrupt/omitted binary, changed hash, wrong model version, extra class, multi-label output/target schema, missing CNN transform/class, mismatched RF schema/class/feature order and unsafe path are rejected before publication or on reopening; no completed Model on failed Run and inputs unchanged. Packaged runtime never requires sibling source checkout; package-scoped tests use the wheel built from the recorded, committed toolbox SHA, not an editable developer install. | TD-EXPORT, TD-FAIL, TD-PATH |

### Extended training configuration and saved presets — Spec 05

| Case ID | Public seam / expected result | Data |
|---|---|---|
| `IT-TRAIN-010` | Real native Train Model page first shows **only** documented primary CNN/RF fields and Run name (no 67-field dashboard); keyboard-accessible **More settings** starts collapsed and reveals **all** other CNN/RF catalog sections as small expandable family-specific groups. For every detailed editable field it displays current, default and suggested starting values with honest recommendation basis; derived fields say “Automatically determined”, and reset/modified indicators work. Closing/reopening preserves non-default edits. Real native Train Model page displays every supported CNN/RF catalog section; each field has functional focusable `alp-ui.HelpHint`, readable per-field tooltip, matching training-Wiki anchor and typed value. Select Dataset/Start Training placement preserves the existing prototype; advanced sections follow the documented **native-only extension** in `docs/design/SPEC05_CONFIGURATION_EXTENSION.md`. Native screenshots of collapsed/advanced forms and keyboard traversal are committed; **no altered HTML prototype** is used as fake evidence for these additions. | TD-CONFIG, TD-UI |
| `IT-TRAIN-011` | Validate defaults that become unsuitable for a Dataset/device, and reject unsupported selections without silently changing suggested/current values. Confirm reset-to-default per field and for details, with controlled unsaved-edit feedback. Enter invalid numeric/cross-field/device/feature choices through native controls; error shown next to field, Worker cannot launch, typed values preserved for correction; no legacy source/data/model/noise path controls appear. | TD-CONFIG, TD-FAIL |
| `IT-TRAIN-012` | Advanced/nondefault CNN and RF settings are passed to real supervised Workers and observed in the scientific executor, immutable Run spec, and Model export; unsupported/derived options neither silently change behavior nor misreport support. | TD-CONFIG, TD-TRAIN, TD-EXPORT |
| `IT-TRAIN-013` | Save/load full detailed overrides while **More settings** is closed; after restart and switching families the overrides are retained and reappear on expansion. Qt create/load/rename/duplicate/overwrite/delete saved config, confirm destructive action, restart and restore actual user-settings files in isolated OS test directory, handle invalid/corrupt/incompatible config; current Dataset and family drafts remain correctly isolated. | TD-PRESET, TD-UI, TD-FAIL |
| `IT-TRAIN-014` | Start genuine training from loaded preset; snapshot resolved config into Run independently of later preset edits/deletion, confirm scientific execution and immutable Model export remain unchanged after restart. | TD-PRESET, TD-TRAIN, TD-EXPORT |

**Reported status:** Spec 05c completes `IT-TRAIN-001`–`014` with genuine CNN and RF Workers on
the same source-WAV-backed Dataset, trusted fresh-process reloads, package independence and reviewed
native evidence. See the [Spec 05c ledger](design/evidence/README.md#spec-05c--real-rf-training-and-phase-05-acceptance)
for the fresh commands and results; this index alone does not establish acceptance.

Spec 05e subsequently hardens the existing IDs at their actual public seams: both native Start
actions launch real Workers, both families cover Worker loss and publication failure, and the
Models UI is reconstructed from persisted settings. See the
[Spec 05e ledger](design/evidence/README.md#spec-05e--critical-training-path-and-failure-recovery-verification).

Spec 05f closes the existing UI/plot/scale ownership gaps: all detailed native fields are exercised,
exact persisted values are compared at the public Plot binding seam, the 10,001-record model runs in
a responsive live window, and CLI/startup tests carry their indexed IDs. See the
[Spec 05f ledger](design/evidence/README.md#spec-05f--ui-chart-scale-and-cli-coverage-closeout).

Detect inference cases are pre-registered **planned** in section 1b above and owned only by their ST-07/ST-09 stage; they are **not** Train acceptance cases. See [PREDICTION](PREDICTION.md) for the science contract.

## 5d. Local logging and diagnostics (pre-release)

| Case ID | Public seam / expected result | Data |
|---|---|---|
| `IT-LOG-001` | A real GUI/session and Collection Scan in isolated Application Settings produce correlated, bounded app JSONL with launch, settings/scan and safe count/status outcomes; shutdown is idempotent and deliberate path/WAV/credential strings are absent. | TD-UI, TD-PATH, TD-FAIL |
| `IT-LOG-002` | Real QProcess Dataset Build, CNN and RF Workers independently write correlated Run logs while stdout remains schema-v1 progress/measurement only; `info` versus `debug` changes diagnostic detail but not scientific metrics, artifact digests or CNN metric collection. | TD-RUN, TD-TRAIN |
| `IT-LOG-003` | Incremental QProcess stderr draining remains bounded during a storm; invalid protocol, cancellation, crash, nonzero exit, receipt mismatch and restart reconciliation retain accurate non-success Run states and sanitized diagnostics without deadlock or false publication. | TD-RUN, TD-FAIL, TD-PATH |
| `IT-LOG-004` | Native Run detail exposes keyboard-usable Open log only for a contained existing log and explains older missing logs; Settings exposes Open diagnostics folder and confirmed Export diagnostics actions, and the resulting new ZIP revalidates/sanitizes only current app plus explicitly selected Run records. Native screenshots and six-dimension review cover desktop and narrow additions. | TD-UI, TD-RUN, TD-PATH |

**Reported status:** Spec 05d implements `IT-LOG-001`–`004` in the macOS development app. See the
[native diagnostics ledger](design/evidence/README.md#spec-05d--local-logging-and-diagnostics) for
actual commands, privacy/stderr/scientific assertions and the installed-platform limits retained
for Specs 06/07.

## 6. Native macOS installer and release gates (spec 06)

| Case ID | Public seam / expected result | Data |
|---|---|---|
| `IT-E2E-001` | **Installed** native package launches Studio with bundled Train/Detect Workers; creates and structurally reloads real CNN/RF Models, runs Detect CNN→RF, exports/reopens WAV+TSV, restarts/relinks and leaves inputs byte-identical. | TD-TRAIN, TD-WAV, TD-EXPORT, TD-UI |
| `IT-MAC-001` | Versioned signed `.app` and `.dmg` verify **BioCall Studio** suite identity/ICNS, embedded Qt/`alp-ui` resources, Developer ID signature/hardened runtime, notarization/stapling and Gatekeeper/quarantine launch on every supported Mac architecture. | TD-OS, TD-UI |
| `IT-MAC-002` | Clean installed app launches bundled Train and Detect Workers without system Python, enforces global admission, survives cancellation/crash/restart, performs shared safe quit and writes versioned per-user state outside the sealed app and source folders. | TD-OS, TD-RUN, TD-UI |
| `IT-MAC-003` | Controlled release from the exact tag and pinned wheels emits a checksummed installer/manifest with dependency and scientific SHA provenance plus tested Train→Detect outputs; missing signing, legal or owner approval blocks promotion. | TD-OS, TD-TRAIN, TD-EXPORT |
| `IT-MAC-004` | Installed `.app` retains accepted Studio/Detect and native Train routes at normal/compact sizes with focus, keyboard HelpHints, copy, tables, plots and all states; actual installed screenshots pass before DMG promotion. | TD-OS, TD-UI |

## 7. Windows installer/qualification gates (spec 07)

| Case ID | Public seam / expected result | Data |
|---|---|---|
| `IT-WIN-001` | Real Windows drive/UNC paths, case/Unicode collisions, reparse containment, locks and atomic updates honor independent Train/Detect ownership and keep Detect metadata outside sources. | TD-OS, TD-PATH |
| `IT-WIN-002` | Native Qt/`alp-ui` pickers and bundled Train/Detect QProcesses enforce global admission, cancel/crash recovery and shared safe quit without system Python; suite theme/assets function. | TD-OS, TD-RUN, TD-UI |
| `IT-WIN-003` | **Installed** package builds/reopens real Dataset and CNN/RF Models, structurally reloads both, completes Detect CNN→RF→WAV+TSV, restarts/relinks and verifies portable immutable provenance. | TD-OS, TD-TRAIN, TD-EXPORT |
| `IT-WIN-004` | Clean install/upgrade/uninstall preserves user Collections, recordings, exports and per-user state; installer/Add-Remove/shortcut/taskbar/window show **BioCall Studio** with the suite ICO and verified digest/security/signing. | TD-OS, TD-UI |
| `IT-WIN-005` | Installed Studio/Train/Detect retains accepted layout and interactions at 100%/150% DPI and compact width with keyboard/focus, HelpHints, plots, screenshots and owner-reviewed native exceptions before promotion. | TD-OS, TD-UI |

## Audit rules

- Do not claim any `IT-*` row covered merely because it appears in documentation, a mock UX, test docstring, scaffold test or CI report.
- Report **covered / planned / blocked / deferred-native** by ID in implementation PRs, based on actual test assertions/results. Keep indexes stable; when adding behavior, first decide whether it is pure `UT-*` or real `IT-*`.
- Run `python scripts/audit_test_ids.py` to locate undocumented IDs; inspect the tests and run them to establish coverage. Requirements for each spec are linked from [`specs/README.md`](specs/README.md).
