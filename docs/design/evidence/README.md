# Native UX parity evidence

## Spec 01 — shell and test foundation

**Status: COMPLETE — ready for owner review.** The eight required Trainer views were captured
from a visible native macOS Cocoa window and reviewed against the checked-in interactive
prototype and current sibling `alp-ui` Showcase. No blocking mismatch or native exception remains.

## Capture provenance

- Command: `unset QT_QPA_PLATFORM; .venv/bin/python scripts/capture_spec01_screenshots.py`
- Host: macOS 26.6.2 (25G83), arm64; native Cocoa platform; 1470×956 screen
- App viewport: 1180×790 logical pixels for desktop views; 700×780 for narrow Select
- Stored PNGs: 1180×790 and 700×780; screen device-pixel ratio 2.0; logical DPI 72
- Runtime: Python 3.12.7; PySide6/Qt 6.11.2; `alp-ui` 0.1.0a0
- `alp-ui` sibling SHA: `330aaab96a6b32dd2d83ae84a52a2a238446d264`
- Data/privacy: isolated temporary Application Settings, no selected Collection, no user paths
- Capture mechanism: visible `QMainWindow` plus Cocoa `QScreen.grabWindow`; not Qt offscreen

The screenshot command rejects non-macOS and non-Cocoa platforms. `IT-UI-001`, `IT-UI-003`,
and `IT-UI-004` separately exercise navigation, the real FolderPicker cancel seam, Wiki/HelpHint
keyboard access, empty routes, active selection, and compact overflow. Screenshots are manual visual
evidence, not pixel-equality tests.

Native dialog check on the same host: clicked **Select folder** with a prior pending path, sent Escape
to the visible macOS directory dialog, and confirmed the pending path remained
`/tmp/selected-before-cancel`; no settings file or scan was created. The pytest seam repeats the
non-destructive result without requiring UI automation permissions.

## State-by-state review

Six-dimension key: **H** information hierarchy/CTA/panel order; **N** navigation/active state;
**C** terms/copy/feedback; **A** `alp-ui` components/theme/icons/accessibility; **I** interaction,
focus, cancel, scroll and resize; **S** empty/scientific state fidelity.

| State | Prototype target | Native evidence | Showcase and interaction evidence | Six dimensions | Difference / disposition |
|---|---|---|---|---|---|
| Select Collection | [Landing target](../prototypes/training-first/landing-preview.png) | [select.png](spec-01-native/select.png) | Showcase icon nav/Card density; real `FolderPicker`; direct Wiki action; `IT-UI-001/003/004` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Public native FolderPicker retains its accessible read-only path field beside the primary action. Prototype sample cards and DEMO DATA are omitted as required by the scientific-safety contract. |
| Selecting a Collection Wiki | [Wiki target](../prototypes/training-first/wiki-preview.png) | [wiki.png](spec-01-native/wiki.png) | Two-column Card hierarchy; source-time HelpHint via Tab/Space; Select Collection returns to landing | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Native labels replace web-only code styling; all guidance, validation groups and CTA order remain present. |
| Settings | [Interactive Settings route](../prototypes/training-first/index.html#settings) | [settings.png](spec-01-native/settings.png) | Card pair, HelpHint and selected Settings icon; machine-local binding copy is visible | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Browser-export footnote is omitted because it is not a native-product capability. No fake rebind or scan action is exposed. |
| Empty Collections | [Interactive Collections route](../prototypes/training-first/index.html#collections) | [empty-collections.png](spec-01-native/empty-collections.png) | `EmptyState`, primary Select Collection action and selected folder nav; `IT-UI-004` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Required initial state replaces prototype mock Collections; no simulated validation result. |
| Empty Datasets | [Interactive Datasets route](../prototypes/training-first/index.html#datasets) | [empty-datasets.png](spec-01-native/empty-datasets.png) | `EmptyState`, primary Select Collection action and selected grid nav; `IT-UI-004` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Required initial state replaces prototype mock Datasets; no fabricated Build output. |
| Empty Models | [Interactive Models route](../prototypes/training-first/index.html#models) | [empty-models.png](spec-01-native/empty-models.png) | `EmptyState`, primary Select Collection action and selected model nav; `IT-UI-004` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Required initial state replaces prototype mock Model; no training result or metric is fabricated. |
| Empty Runs | [Interactive Runs route](../prototypes/training-first/index.html#runs) | [empty-runs.png](spec-01-native/empty-runs.png) | `EmptyState`, global No Active Run/Idle header and selected list nav; `IT-UI-004` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Required initial state replaces prototype mock Runs; no fake progress or completion exists. |
| Select narrow viewport | [Landing responsive target](../prototypes/training-first/landing-preview.png) | [select-narrow.png](spec-01-native/select-narrow.png) | 700×780 viewport; horizontal icon nav scrolls; CTA, Wiki and help remain visible/tabbable | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Native horizontal scrollbar makes all seven destinations reachable without clipping the page content. |

[The bundled Showcase snapshot](../references/alp-ui-showcase.png) was reviewed for nav icons,
selected/hover/focus treatment, typography, Cards, control density and Alpaca Light spacing. The
live sibling `gallery/showcase.py` at the recorded SHA was also inspected.

## Spec 02 — Collection Scan and metadata

**Status: COMPLETE — ready for owner review.** Reading, invalid, corrected/rescanned valid and
narrow Collection views were captured from a visible native macOS Cocoa window with a generated
real PCM WAV Collection. No blocking mismatch or native exception remains.

### Capture provenance

- Command: `unset QT_QPA_PLATFORM; .venv/bin/python scripts/capture_spec02_screenshots.py`
- Host: macOS 26.6.2 (25G83), arm64; native Cocoa platform; 1470×956 screen
- App viewport/stored PNG: 1180×807 for desktop views; 700×780 for narrow Collection
- Screen device-pixel ratio 2.0; logical DPI 72
- Runtime: Python 3.12.7; PySide6/Qt 6.11.2; `alp-ui` 0.1.0a0
- `alp-ui` sibling SHA: `330aaab96a6b32dd2d83ae84a52a2a238446d264`
- Data/privacy: generated temporary mono PCM WAVs; isolated Application Settings; no user paths
- Capture mechanism: visible `QMainWindow` plus Cocoa `QScreen.grabWindow`; not Qt offscreen

This closure recapture was reviewed at original resolution on 25 Oct 2026 after widening the
Reading panel to the prototype's comparable desktop hierarchy. The checked-in prototype
`showScan()` / `collectionPage()` state functions, their reachable valid/invalid transitions and
the current sibling Showcase composition were re-inspected before capture.

The screenshot flow selects an invalid real-WAV Collection, captures Reading and its exact filename
issue, renames that existing positive WAV to the required source-time grammar, clicks **Rescan
Collection**, and captures the valid result. `IT-COL-001` and `IT-COL-008` separately assert the
progress/cancel controls, navigation, CTA gating, keyboard activation, repair/rescan transition and
compact layout. Screenshot capture is visual evidence, not a pixel-equality test.

### State-by-state review

Six-dimension key: **H** information hierarchy/CTA/panel order; **N** navigation/active state;
**C** terms/copy/feedback; **A** `alp-ui` components/theme/icons/accessibility; **I** interaction,
focus, cancel, scroll and resize; **S** empty/error/progress/scientific-state fidelity.

| State | Prototype target | Native evidence | Showcase and interaction evidence | Six dimensions | Difference / disposition |
|---|---|---|---|---|---|
| Reading Collection | [Reading target](../prototypes/training-first/scanning-preview.png) | [scanning.png](spec-02-native/scanning.png) | `ProgressBar`, `Badge`, secondary Cancel; full-width 780 px content bound; `IT-COL-001/005/008` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Native worker progress replaces browser timing; Reading remains a cancellable I/O activity, never an Active Run. |
| Validation errors | [Validation target](../prototypes/training-first/validation-preview.png) | [summary](spec-02-native/validation-summary.png) · [exact issue detail](spec-02-native/validation-errors.png) | `Card`, warning `Alert`, paged `DataTable`; exact relative path/correction; disabled Build; `IT-COL-002/008` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Native Rescan is explicit beside Choose another folder. A second scrolled capture records the issue row because the native desktop height is shorter than the prototype preview. Browser-only manifest download is omitted because native metadata is published under `.alpaca/`. |
| Corrected/rescanned valid Collection | [Collection target](../prototypes/training-first/collection-preview.png) | [summary](spec-02-native/collection-valid.png) · [validation detail](spec-02-native/collection-valid-detail.png) | Four-card summary, source→positive table, Folder and Fast reopening cards, Passed rows, primary Build; `IT-COL-001/003/004/008` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Counts/duration come from real WAV headers; cache says Ready only after manifest-last publication. The detail capture records all Passed rows. Waveform identity is expressly not claimed. |
| Narrow Collection | [Responsive interactive target](../prototypes/training-first/index.html#/collection/c001) | [collection-narrow.png](spec-02-native/collection-narrow.png) | 700×780 viewport; two-by-two summary; stacked content; horizontal navigation and vertical page scroll; `IT-COL-008` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | The native horizontal scrollbar keeps all seven destinations reachable without clipping page content. |

The [bundled Showcase snapshot](../references/alp-ui-showcase.png) and live sibling
`gallery/showcase.py` were reviewed for Card density, DataTable headers/rows, status colors, focus
treatment, control sizing and application-shell spacing.

## Spec 03 — Dataset Build

**Status: COMPLETE — ready for owner review.** Builder ready, deterministic underfill, busy,
Dataset list/detail and narrow Builder views were captured from a visible native macOS Cocoa
window. The flow used generated real PCM WAVs and a real QProcess Dataset Build; no prototype
science or fabricated artifact was carried into the native app. No blocking mismatch or native
exception remains.

### Capture provenance

- Command: `unset QT_QPA_PLATFORM; .venv/bin/python -u scripts/capture_spec03_screenshots.py`
- Host: macOS 26.6.2 (25G83), arm64; native Cocoa platform; 1470×956 screen
- App viewport/stored PNG: 1280×895 for Builder/detail, 1280×900 for list; 700×780 narrow
- Screen device-pixel ratio 2.0; logical DPI 72
- Runtime: Python 3.12.7; PySide6/Qt 6.11.2; `alp-ui` 0.1.0a0
- `alp-ui` sibling SHA: `330aaab96a6b32dd2d83ae84a52a2a238446d264`
- Scientific sibling SHA: `91af5287dc18313f88902dc9696e8756274736b3`
- Data/privacy: three generated 8 s mono PCM Source Recordings plus timestamped Positive WAVs in a
  temporary Collection; isolated Application Settings; no user paths or HPC data
- Capture mechanism: visible `QMainWindow` plus Cocoa `QScreen.grabWindow`; not Qt offscreen

The checked-in interactive prototype's `buildPage()`, `refreshBuildSummary()`, `runBuild()`,
`datasetsPage()` and `datasetPage()` states plus `builder-preview.png` and responsive CSS were
reviewed against the native flow. The current sibling Showcase source and snapshot were rechecked
for `DataTable`, `NumberInput`, `SelectInput`, `HelpHint`, `ProgressBar`, Card, disabled/loading and
focus conventions. The in-app browser runtime had no available browser instance, so this review
used the actual checked-in HTML/JS/CSS state implementation rather than claiming a live browser
click-through.

The scientific adaptation retains the sibling's seeded bounded-mining intent and Source Recording
grouping, while adding protected positive unions, integer-millisecond source time, deterministic
nonoverlap, bounded chunked PCM extraction and portable verified manifests required here. Sibling
orchestration/schema were not copied. `IT-DB-001`…`IT-DB-005` cover the public native and artifact
seams. Persisted Run records, cancel/recovery and Run pages remain Spec 04; no `IT-RUN-*` result is
claimed by this evidence.

### State-by-state review

Six-dimension key: **H** information hierarchy/CTA/panel order; **N** navigation/active state;
**C** terms/copy/feedback; **A** `alp-ui` components/theme/icons/accessibility; **I** interaction,
focus, busy, scroll and resize; **S** error/progress/scientific-state fidelity.

| State | Prototype target | Native evidence | Showcase and interaction evidence | Six dimensions | Difference / disposition |
|---|---|---|---|---|---|
| Builder ready | [Builder target](../prototypes/training-first/builder-preview.png) | [builder.png](spec-03-native/builder.png) | Real `DataTable` selection model; `NumberInput`, `SelectInput`, `HelpHint`, class meter and primary Build; `IT-DB-005` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | The native table has three generated Source Recordings instead of twelve demo rows; all counts and feasibility are computed from their actual headers/Annotations. |
| Underfill and disabled Build | [Interactive Builder state](../prototypes/training-first/index.html#build) | [builder-underfill.png](spec-03-native/builder-underfill.png) | Real config change requests 60 noise Snippets; warning reports 15 available plus per-recording eligible milliseconds; Build is disabled; `UT-DB-002`, `IT-DB-003/005` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Native preflight exposes the exact deterministic shortfall rather than silently reducing the requested count. |
| Busy Build | [Interactive Build action](../prototypes/training-first/index.html#build) | [builder-busy.png](spec-03-native/builder-busy.png) | Disabled config/table, loading primary action and global Dataset Build/Working state during the real QProcess; `IT-DB-005` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Persistent Run navigation/cancel belongs to Spec 04; the Spec 03-owned busy Builder state remains truthful and blocks a second Build. |
| Dataset list | [Interactive Datasets route](../prototypes/training-first/index.html#datasets) | [datasets.png](spec-03-native/datasets.png) | Published manifest supplies readable Dataset/Collection, actual Snippet count/date and Open navigation; `IT-DB-004/005` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | The native row is a verified local artifact, not the prototype's in-memory demo Dataset. |
| Dataset detail | [Interactive Dataset route](../prototypes/training-first/index.html#datasets) | [dataset-detail.png](spec-03-native/dataset-detail.png) | Real counts, class meters, source-grouped Splits, provenance, generated-file tree, explicit Delete; `IT-DB-001/004/005` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | `dataset.json` follows the architecture contract. Train Model is visibly disabled with explanatory copy until Spec 05 supplies real Training, as required by the scientific-safety gate. |
| Narrow Builder | [Responsive Builder target](../prototypes/training-first/index.html#build) | [builder-narrow.png](spec-03-native/builder-narrow.png) | 700×780 viewport; horizontal navigation remains reachable; Builder cards stack in prototype order with vertical scroll; `IT-DB-005` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Native vertical scrolling exposes the settings below the captured first viewport without horizontal content clipping. |

## Spec 04 — Runs and supervised Worker

**Status: COMPLETE — ready for owner review.** Active, cancelling, failed and completed Run detail,
persisted history and narrow Run detail were captured from a visible native macOS Cocoa window.
Progress and terminal outcomes came from actual QProcess Worker events and verified Dataset bytes;
no browser timer, demo record or invented scientific result appears. No blocking mismatch or native
exception remains.

### Capture provenance

- Command: `unset QT_QPA_PLATFORM; .venv/bin/python -u scripts/capture_spec04_screenshots.py`
- Host: macOS 26.6.2 (25G83), arm64; native Cocoa platform; 1470×956 screen
- App viewport/stored PNG: 1280×807 for desktop views; 700×780 for narrow Run detail
- Screen device-pixel ratio 2.0; logical DPI 72
- Runtime: Python 3.12.7; PySide6/Qt 6.11.2; `alp-ui` 0.1.0a0
- `alp-ui` sibling SHA: `330aaab96a6b32dd2d83ae84a52a2a238446d264`
- Scientific sibling SHA: `91af5287dc18313f88902dc9696e8756274736b3`; its orchestration/schema
  was not reused for this local Worker lifecycle
- Data/privacy: three generated mono PCM Source Recordings plus timestamped Positive WAVs in a
  temporary Collection; isolated Application Settings; no user paths or HPC data
- Capture mechanism: visible `QMainWindow` plus Cocoa `QScreen.grabWindow(window.winId())`; not Qt
  offscreen

The prototype has no Run preview PNGs. Its actual `globalRun()`, `createRun()`, `advanceRun()`,
`cancelRun()`/`confirmCancel()`, `runPage()` and `runsPage()` implementations plus the Run-related
CSS were therefore the direct content, hierarchy, transition and responsive reference. The current
sibling Showcase source and component composition were rechecked for icon navigation, Cards,
`DataTable`, status color, buttons, progress, focus and compact density. The in-app browser runtime
had no available browser instance, so this review used the normative checked-in interactive source
instead of claiming a live browser click-through.

The capture flow starts a real delayed Worker, records actual stage progress, requests cancellation
and captures the durable cancelling state. A separately published Dataset ID forces a real
no-clobber Worker failure without changing its bytes. A final real Worker publishes and reopens a
verified Dataset before the completed, history and narrow views are captured. `IT-RUN-001`…`005`
separately assert persisted transitions, reservations, cancellation/forced loss, restart cleanup,
failure integrity, keyboard focus, navigation and responsive width. Screenshots are visual
evidence, not pixel-equality tests.

### State-by-state review

Six-dimension key: **H** information hierarchy/CTA/panel order; **N** navigation/active state;
**C** terms/copy/feedback; **A** `alp-ui` components/theme/icons/accessibility; **I** interaction,
focus, cancel, scroll and resize; **S** error/progress/terminal/scientific-state fidelity.

| State | Prototype target | Native evidence | Showcase and interaction evidence | Six dimensions | Difference / disposition |
|---|---|---|---|---|---|
| Active Dataset Build Run | [Interactive Run route](../prototypes/training-first/index.html#/run/train-0081) | [run-active.png](spec-04-native/run-active.png) | Actual Worker stage/progress; global Active Run track and View Run; selected Runs navigation; `ProgressBar`, `Badge`, `Alert`, `Button`; `IT-RUN-001/005` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Native progress is persisted structured Worker output rather than the prototype timer. Output remains explicitly unpublished and inputs read-only. |
| Cancelling Run | [Interactive cancel transition](../prototypes/training-first/index.html#/run/train-0081) | [run-cancelling.png](spec-04-native/run-cancelling.png) | Real cancel marker, persisted `cancelling`, disabled Cancel action, warning output feedback and bounded terminate/kill fallback; `IT-RUN-003/005` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Canonical native status uses “cancelled/cancelling”; no partial Dataset is exposed. |
| Failed Run | [Interactive terminal Run structure](../prototypes/training-first/index.html#/run/train-0081) | [run-failed.png](spec-04-native/run-failed.png) | Real pre-existing output collision, danger Badge/Alert, 0% stage state and exact portable correction; `IT-RUN-004/005` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | The prototype does not simulate failure; the native view preserves its hierarchy while showing the required truthful no-clobber result. |
| Completed Run | [Interactive completed Run](../prototypes/training-first/index.html#/run/train-0081) | [run-completed.png](spec-04-native/run-completed.png) | Verified manifest/Snippet/Split reopen precedes completed state; finished stages, Dataset ID and Open Dataset actions; `IT-RUN-001/004/005` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Counts are available on the real Dataset detail rather than repeated as prototype demo values. Completion requires both receipt and validated output. |
| Runs history | [Interactive Runs route](../prototypes/training-first/index.html#/runs) | [runs-history.png](spec-04-native/runs-history.png) | Real `DataTable` model; semantically colored completed/failed/cancelled status cells; Inspect navigation and keyboard focus; `IT-RUN-002/005` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Status cells use the public `DataTable` model/delegate surface rather than illegal per-row widgets; Run detail uses actual `Badge` components. |
| Narrow Run detail | [Responsive interactive Run](../prototypes/training-first/index.html#/run/train-0081) | [run-narrow.png](spec-04-native/run-narrow.png) | 700×780 viewport; Runs destination centered in scrollable icon navigation; stacked Run panels, preserved CTA and zero horizontal page overflow; `IT-RUN-005` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Vertical scrolling exposes Output/details below the first captured viewport while all content remains reachable. |

## Spec 04.5 — upstream PCM extraction regression review

**Status: COMPLETE — ready for owner review.** Spec 04.5 owns no new screen or prototype state.
At the user's request, the accepted Run surface was recaptured from real post-migration QProcess
Dataset Builds to prove that the scientific ownership change did not alter visible behavior. The
current native `alp-ui` Showcase was also captured and reviewed; no HTML, Qt layout, component or
copy change was made for this backend-only spec.

### Capture provenance

- Trainer command: `unset QT_QPA_PLATFORM; .venv/bin/python -u scripts/capture_spec04_screenshots.py --output-dir docs/design/evidence/spec-04.5-native`
- Showcase: current sibling `gallery/showcase.py` composition, captured from visible Cocoa at
  1180×790 logical / 2360×1580 device pixels
- Host: macOS 26.6.2, arm64; native Cocoa; screen device-pixel ratio 2.0; logical DPI 72
- Trainer viewport/stored PNG: 1280×807 desktop; 700×780 narrow
- Runtime: Python 3.12.7; PySide6/Qt 6.11.2; `alp-ui` 0.1.0a0
- `alp-ui` SHA: `330aaab96a6b32dd2d83ae84a52a2a238446d264`
- toolbox SHA/version: `0fce0d4fa3d0931c5731e8b868f705e0a2120835` / `0.1.1`
- unshipped verification wheel: `bioacoustics_dl_toolbox-0.1.1-py3-none-any.whl`, SHA-256
  `472769c9567e01ed5e009b5faaeca501c87c9d508f16f04586593f398b2d8e7c`; release gates
  must build and record their own candidate wheel from the same committed revision
- scientific reference SHA: `alpaca-pipelines@91af5287dc18313f88902dc9696e8756274736b3`
- Data/privacy: generated mono PCM recordings and timestamped positives in a temporary Collection;
  no user Collection or HPC data
- Capture mechanism: visible Cocoa windows; Trainer uses `QScreen.grabWindow`, Showcase uses
  `QWidget.grab`; neither uses the Qt offscreen platform

The in-app browser had no available instance. Per the source-first acceptance contract, the actual
bundled `globalRun()`, `runPage()`, cancellation transition, `runsPage()` and Run CSS remained the
normative prototype review. No live-browser interaction evidence is claimed. `IT-AUDIO-003/004`
exercise the real post-migration Dataset Build and Worker while `IT-RUN-001/005` retain interaction,
focus, navigation and responsive assertions.

### State-by-state review

| State | Prototype target | Post-migration native evidence | Six dimensions | Review result |
|---|---|---|---|---|
| Current `alp-ui` composition | [Showcase contract](../ALP_UI_CONSUMER_CONTRACT.md) | [alp-ui-showcase-current.png](spec-04.5-native/alp-ui-showcase-current.png) | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Compact density, focus ring, selected navigation, Card/form/table hierarchy, Badge and button styling are intact at the current sibling SHA. |
| Active Build | [Interactive Run](../prototypes/training-first/index.html#/run/train-0081) | [run-active.png](spec-04.5-native/run-active.png) | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Real Worker reports input validation and an unpublished output; the toolbox extraction path is reached later in the same Run. |
| Cancelling Build | [Interactive cancel transition](../prototypes/training-first/index.html#/run/train-0081) | [run-cancelling.png](spec-04.5-native/run-cancelling.png) | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Disabled Cancel, warning output and no-publication promise remain visible; cancellation cleanup is asserted at the toolbox, adapter and workflow boundaries. |
| Failed Build | [Run terminal hierarchy](../prototypes/training-first/index.html#/run/train-0081) | [run-failed.png](spec-04.5-native/run-failed.png) | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Real no-clobber collision produces a truthful failed Run and preserves the existing Dataset. |
| Completed Build | [Interactive completed Run](../prototypes/training-first/index.html#/run/train-0081) | [run-completed.png](spec-04.5-native/run-completed.png) | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Completion follows toolbox-backed PCM extraction, staged checksum validation, immutable publication and reopen. |
| Runs history | [Interactive Runs](../prototypes/training-first/index.html#/runs) | [runs-history.png](spec-04.5-native/runs-history.png) | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Completed/failed/cancelled rows and Inspect affordances remain unchanged. |
| Narrow completed Run | [Responsive interactive Run](../prototypes/training-first/index.html#/run/train-0081) | [run-narrow.png](spec-04.5-native/run-narrow.png) | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Horizontal navigation, stacked panels, primary output action and vertical scroll remain reachable without horizontal content clipping. |

## Every subsequent spec: mandatory ledger

Use [Prototype acceptance](../PROTOTYPE_ACCEPTANCE.md) for the full screenshot inventory and six
dimensions. Each implementing spec adds: reference route/state, native screenshot, actual `alp-ui`
SHA/OS/Qt/DPI/viewport, interaction `IT-*` evidence, six-dimension assessment and any
owner-accepted platform-only exception. Installed `.app`/`.exe` views get their own evidence
folders rather than reusing these development captures.
