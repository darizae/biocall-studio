# Indexed integration-test behaviors — Trainer

All rows are **target acceptance criteria**, not claims of implementation or a passing test. Test functions that establish a row must contain its exact `IT-*` ID in the test-function docstring, cover each observable assertion, and execute successfully on the required real boundary. Detailed pure variants live in [`UNIT_TESTING.md`](UNIT_TESTING.md). Minimum differentiating resources are listed in [`INTEGRATION_TEST_DATA.md`](INTEGRATION_TEST_DATA.md).

## 1. Shell and native UI (spec 01)

| Case ID | Public seam / expected result | Data |
|---|---|---|
| `IT-UI-001` | Native Qt/`alp-ui` launches, Select Collection primary action and Wiki navigate; theme/resources render and back/focus navigation survives page changes. | TD-UI |
| `IT-UI-002` | Test-isolated Application Settings retain valid Collection binding across restart and support explicit rebind; original input WAV bytes remain untouched. | TD-COL, TD-PATH |
| `IT-UI-003` | Updated public `alp-ui` `FolderPicker` is used in actual native Select UI: folderChanged routes pending selection, cancellation leaves previous path/verification unchanged and does not start scan; accessible full path and keyboard operate. | TD-UI, TD-COL |
| `IT-UI-004` | Prototype Select/Wiki/empty-state structure is exercised with real `alp-ui` Widgets, an accessible inline Wiki action, keyboard Tab/Space and HelpHint, and no demo scientific completions. **Separately required native macOS evidence:** persist real Trainer screenshots (not only pytest tmp files), compare side by side with both bundled prototype and sibling Showcase, log deviations and update README with truthful native shots before claiming UI acceptance. | TD-UI |

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
| `IT-RUN-002` | Second requested Run conflicts while one active; locked input deletion/rebind conflicts; read-only browsing proceeds; terminal state releases reservation. | TD-RUN |
| `IT-RUN-003` | Real cancellation and forced process loss produce cancelled/interrupted state after bounded reconciliation, no false published artifact and no eternal Active Run after restart. | TD-RUN, TD-FAIL |
| `IT-RUN-004` | Artifact/staging name collision, corrupt publication or worker nonzero exit fails without overwriting a published Dataset/Model or promoting a stale output pointer. | TD-RUN, TD-FAIL |
| `IT-RUN-005` | Native Run detail/history/Active Run sidebar reflect prototype section ordering, progress, cancel, conflict and terminal states through real Worker events; keyboard navigation and native evidence pass six-dimension review. | TD-UI, TD-RUN, TD-FAIL |

Spec 04 implementation evidence: `tests/integration/test_run.py` asserts all five rows through real
QProcess, persistence, restart, reservation and native-widget seams. The tracked Cocoa comparison
set and six-dimension review are in
[`design/evidence/spec-04-native/`](design/evidence/spec-04-native/) and the
[evidence ledger](design/evidence/README.md). Packaged Worker launch remains owned by Spec 06.

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

Future Prediction inference cases are **reserved exclusively** in [PREDICTION](PREDICTION.md), outside this Trainer test index or any Trainer release gate.

## 6. Native macOS installer and release gates (spec 06)

| Case ID | Public seam / expected result | Data |
|---|---|---|
| `IT-E2E-001` | **Installed** native macOS package launches bundled UI/Worker, selects folder, builds Dataset, trains CNN/RF, restarts, opens published artifacts and **structurally reloads both Model formats using trusted local binary files** while leaving inputs intact. | TD-TRAIN, TD-UI |
| `IT-MAC-001` | Versioned signed `.app` and installer `.dmg` verify correct bundle ID/embedded Qt and `alp-ui` resources, Developer ID signature/hardened runtime, notarization + stapling, Gatekeeper/quarantine first launch on supported Mac architecture. | TD-OS, TD-UI |
| `IT-MAC-002` | Clean Mac installed-app launches its **bundled** Worker (not system Python), survives cancellation/restart and writes user state outside sealed app; folder chooser/help/plots/theme/resources work. | TD-OS, TD-RUN, TD-UI |
| `IT-MAC-003` | Controlled release from exact tagged/approved commit emits installer with checksums/recorded dependency/SHA provenance and tested native E2E scientific outputs; missing signing/approval blocks promotion rather than advertising a public installer. | TD-OS, TD-TRAIN |
| `IT-MAC-004` | Installed `.app` retains prototype route/state layout and pinned `alp-ui` styling, icons, themes, picker/help/plot at normal and narrow sizes; actual installed screenshots and six-dimension review pass before DMG promotion. | TD-OS, TD-UI |

## 7. Windows installer/qualification gates (spec 07)

| Case ID | Public seam / expected result | Data |
|---|---|---|
| `IT-WIN-001` | Real Windows input paths, case/Unicode collision, reparse containment, file locks and atomic updates honor same Collection contract. | TD-OS, TD-PATH |
| `IT-WIN-002` | Windows native Qt/`alp-ui` file picker/scan and packaged QProcess/Worker launch, cancel, recovery and theme/assets function. | TD-OS, TD-RUN |
| `IT-WIN-003` | **Installed** Windows native package builds and reopens one real Dataset and both CNN/RF Models, **structurally reloads both Model formats**; verified portable relative provenance. | TD-OS, TD-TRAIN |
| `IT-WIN-004` | Clean Windows installation/uninstallation of versioned `.exe` retains user Collection; packaged resources, release digest/security/signing and native Windows keyboard/DPI help/plot parity are verified. | TD-OS, TD-UI |
| `IT-WIN-005` | Installed Windows app retains prototype layout/interaction and native `alp-ui` styling at 100%/150% DPI plus keyboard/focus, with screenshots and explicit owner-reviewed native exceptions before installer promotion. | TD-OS, TD-UI |

## Audit rules

- Do not claim any `IT-*` row covered merely because it appears in documentation, a mock UX, test docstring, scaffold test or CI report.
- Report **covered / planned / blocked / deferred-native** by ID in implementation PRs, based on actual test assertions/results. Keep indexes stable; when adding behavior, first decide whether it is pure `UT-*` or real `IT-*`.
- Run `python scripts/audit_test_ids.py` to locate undocumented IDs; inspect the tests and run them to establish coverage. Requirements for each spec are linked from [`specs/README.md`](specs/README.md).
