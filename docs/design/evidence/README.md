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

## Spec 05a — Training configuration and saved presets

**Status: COMPLETE — ready for owner review.** The compact CNN/RF baseline, detailed groups,
saved/unsaved preset states, destructive confirmation and narrow keyboard-focus state were
captured from the visible native macOS Cocoa app. The Dataset was built from generated real PCM
WAVs. No training Worker ran, no metric was invented and no Model was published.

### Capture provenance

- Recaptured 26 October 2026 on macOS 26.6.2 arm64, Python 3.12.7, PySide6/Qt 6.11.2,
  `alp-ui` 0.1.0a0 at `330aaab96a6b32dd2d83ae84a52a2a238446d264`.
- Cocoa primary screen: 1470×956 logical pixels, device pixel ratio 2.0, logical DPI 72; normal
  app capture 1280×807 and compact capture 700×780. PNGs preserve native compositor output.
- Scientific defaults were rechecked against the current `bioacoustics-dl-toolbox`
  `8e2e0528d4ce718005e194d426cde6e62fda0909` and `alpaca-pipelines`
  `91af5287dc18313f88902dc9696e8756274736b3`. Spec 05b advances the Trainer's recorded toolbox
  revision to that exact inspected sibling commit.
- The unchanged prototype was reviewed source-first at `openTraining`, `trainPage`, `setTrain` and
  `startTraining`, the relevant CSS and `rf-config-preview.png`. No controllable browser session was
  connected, so no live-browser interaction evidence is claimed. The actual current sibling
  Showcase was launched and captured as
  [alp-ui-showcase-current.png](spec-05-native/alp-ui-showcase-current.png).

### State-by-state review

Six-dimension key: **H** information hierarchy/CTA/panel order; **N** navigation/active state;
**C** terms/copy/feedback; **A** `alp-ui` components/theme/icons/accessibility; **I** interaction,
focus, scroll and resize; **S** scientific/disabled/error/completed-state fidelity.

| State | Prototype / extension target | Native evidence | Showcase and interaction evidence | Six dimensions | Difference / disposition |
|---|---|---|---|---|---|
| Collapsed CNN | [Interactive Training route](../prototypes/training-first/index.html#train) | [train-cnn.png](spec-05-native/train-cnn.png) | Public `SelectInput`, `NumberInput`, `HelpHint`, `Card`, `Alert`, primary `Button`; `IT-TRAIN-010/011` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Dataset left, compact configuration right and Start Training left-bottom match the prototype hierarchy. The primary roster adds Run name and sequence length per the native extension; unavailable CUDA/MPS choices now carry concise visible reasons and full option tooltips without displacing More settings. |
| Collapsed RF | [RF target](../prototypes/training-first/rf-config-preview.png) | [train-rf.png](spec-05-native/train-rf.png) | Family switch preserves the CNN draft; nullable depth displays Unlimited semantics; `IT-TRAIN-010` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Prototype threshold moves into More settings as explicitly required; fixed feature family remains visible as derived in details instead of a fake editable basic. |
| Detailed CNN | [Native extension](../SPEC05_CONFIGURATION_EXTENSION.md) | [train-cnn-advanced.png](spec-05-native/train-cnn-advanced.png) | Scrolled Spectrogram group shows current 2048, backend default/suggestion 4096, modified badge, reset and Wiki/help; `UT-TRAIN-007/008`, `IT-TRAIN-010/011` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | The capture intentionally scrolls the in-page detail content; the paired collapsed capture records the baseline header and CTA. Only one subgroup is open. |
| Detailed RF | [Native extension](../SPEC05_CONFIGURATION_EXTENSION.md) | [train-rf-advanced.png](spec-05-native/train-rf-advanced.png) | Forest group shows decision policy separately from fitting fields and a non-default seed with reset; typed numeric/null feature modes are retained; `UT-TRAIN-008` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | RF threshold is explicitly described as validation/recorded policy, not an estimator fit parameter or future inference control. |
| Saved configurations | [Preset extension](../../science/TRAINING_PRESETS.md) | [presets-list.png](spec-05-native/presets-list.png) | Native dialog exposes Rename, Duplicate, Overwrite and Delete; user-level storage copy explains that Dataset/Collection paths are absent; `UT-TRAIN-009/010`, `IT-TRAIN-013` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Presets are intentionally native-only and remain inside Model configuration rather than becoming a navigation destination. |
| Unsaved draft | [Preset extension](../../science/TRAINING_PRESETS.md) | [presets-unsaved.png](spec-05-native/presets-unsaved.png) | Selector reads Unsaved changes after batch-size edit; stored preset is unchanged; Start summary reflects batch 32; `IT-TRAIN-013` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Draft state is explicit and never saves or starts training implicitly. |
| Confirm delete | [Preset extension](../../science/TRAINING_PRESETS.md) | [presets-confirm-delete.png](spec-05-native/presets-confirm-delete.png) | Native macOS confirmation states Dataset/Run non-effects; cancel preserves the preset; `IT-TRAIN-013` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Platform-native Yes/No button labels are used by `QMessageBox`; the destructive consequence is explicit in the message. |
| Narrow advanced focus | [Native responsive extension](../SPEC05_CONFIGURATION_EXTENSION.md) | [train-cnn-narrow-focus.png](spec-05-native/train-cnn-narrow-focus.png) | 700×780 stacked page, horizontally reachable nav, focused FFT field, vertical detail scroll and no page horizontal overflow; `IT-TRAIN-010` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | The capture is deliberately scrolled to the focused detailed field; Dataset, configuration and Start cards remain ordered 1→2→3. |

`IT-TRAIN-010` asserts the full CNN/RF field, section, HelpHint and Wiki-anchor inventory plus
keyboard disclosure and family-draft isolation. `IT-TRAIN-011` asserts non-clamping validation,
reset, unavailable capabilities and frozen configuration without Worker launch. `IT-TRAIN-013`
asserts real atomic files and CRUD/restart persistence in an isolated user directory. The successful
At the 05a closeout the Start action only froze the future Worker input. Spec 05b supersedes that
temporary boundary for CNN while `IT-TRAIN-012/014` remain cross-family-open until 05c.

Verified on the capture platform with `5 passed` for the owned unit module, `3 passed` for the
owned integration module and `74 passed` for the full suite. Ruff check/format, the indexed-ID,
fixture, native-handoff and Git LFS audits passed. `capture_spec05_screenshots.py` produced the nine
reviewed Cocoa PNGs, and a no-dependency wheel build contained the packaged 67-field JSON catalog.

## Spec 05b — Real CNN training and common Model foundation

**Status: implementation recorded; owner acceptance pending.** The macOS record reports a real
CPU CNN Worker, measured train/validation loss, immutable checksummed Model, trusted fresh-process
structural reload and native naming/Run/Model screens. No inference was implemented or claimed.

### Capture provenance

- Command: `unset QT_QPA_PLATFORM; .venv/bin/python -u scripts/capture_spec05_screenshots.py`
- Recaptured 26 October 2026 on macOS 26.6.2 arm64; native Cocoa; 1470×956 logical primary screen,
  device pixel ratio 2.0 and logical DPI 72
- Runtime: Python 3.12.7; PySide6/Qt 6.11.2; `alp-ui` 0.1.0a0 at
  `330aaab96a6b32dd2d83ae84a52a2a238446d264`
- Stored PNGs: 1280×807 desktop, 700×780 narrow Model detail, and 1180×790 current Showcase
- Direct scientific dependency: editable `bioacoustics-dl-toolbox` 0.1.1 imported from
  `../bioacoustics-dl-toolbox/src` at `8e2e0528d4ce718005e194d426cde6e62fda0909`, not the package
  copy inside `../alpaca-pipelines`; targeted pipeline reference
  `91af5287dc18313f88902dc9696e8756274736b3`
- Data/privacy: generated mono PCM Source Recordings, timestamped positives and a real published
  target/noise Dataset in an isolated temporary Collection; no user or HPC data
- Capture mechanism: visible `QMainWindow`, native `QInputDialog` and Cocoa `QScreen.grabWindow`;
  the command rejects Qt offscreen/non-Cocoa rendering

Prototype functions and CSS were inspected source-first; the sibling Showcase was captured as
[alp-ui-showcase-current.png](spec-05-native/alp-ui-showcase-current.png). The native Run uses
public `Plot.setLines` with selectable numeric loss values.

Scientific publication requires a final Model label inside the immutable, exclusively published
manifest. The native app therefore collects the same 80-character display name immediately after
**Start Training**, before the Worker begins, instead of holding completed but unpublished weights
for the prototype's later **Name and save Model** action. This is the smallest safety-driven timing
change: the modal content, stable ID/readable-label result and Run→Model journey remain intact, and
cancellation/failure never exposes partial weights. Likewise, the prototype's illustrative
Prediction link is replaced by an explicit **Prediction not included** boundary as required by the
Trainer scope.

### State-by-state review

Six-dimension key: **H** information hierarchy/CTA/panel order; **N** navigation/active state;
**C** terms/copy/feedback; **A** `alp-ui` components/theme/icons/accessibility; **I** interaction,
focus, scroll and resize; **S** real scientific/disabled/error/completed-state fidelity.

| State | Prototype target | Native evidence | Showcase and interaction evidence | Six dimensions | Difference / disposition |
|---|---|---|---|---|---|
| Model naming | `nameModel()` / `saveModel()` | [model-name.png](spec-05-native/model-name.png) | Native modal, focused bounded label, validated frozen config and one-Active-Run gate; `IT-TRAIN-001/012/014` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Naming occurs immediately after Start so the supervised Worker can publish one final immutable Model; no orphan trained weights or later manifest rewrite is introduced. |
| Completed CNN Run and Plot | `runPage()` / `lossChart()` | [run-cnn-plot.png](spec-05-native/run-cnn-plot.png) | Real QProcess completion; two measured series via public `Plot`, exact selectable numeric alternative, Model output CTA; `IT-TRAIN-001/005/007` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Browser mock curves/metrics are replaced by the one real bounded epoch captured here; the chart is sparse because no values are invented. |
| Model list | `modelsPage()` | [models.png](spec-05-native/models.png) | Real `DataTable` model populated only after verified publication; label, stable ID, family, Dataset/date and Inspect navigation; `IT-TRAIN-007` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | “Available to Prediction” copy is omitted because this Trainer does not establish inference support. |
| Model detail | `modelPage()` / `model-preview.png` | [model-detail.png](spec-05-native/model-detail.png) | Real validation metrics, Dataset/Run links, immutable file tree, package/SHA provenance and explicit no-Prediction boundary; `UT-TRAIN-004/005`, `IT-TRAIN-007/008` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Real checksum-verified `model.json` + `model.pt` replace proposed/demo files; the browser's external Prediction CTA is intentionally absent. |
| Narrow Model detail | responsive `modelPage()` | [model-detail-narrow.png](spec-05-native/model-detail-narrow.png) | 700×780 viewport, horizontally reachable navigation, readable four-stat row, vertical detail stack and preserved Run/Dataset actions | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Content remains vertically reachable without horizontal page clipping; the navigation strip scrolls by design. |

**Recorded 05b checks (macOS, 25 October 2026):**

- `.venv/bin/pytest -q tests/unit/test_training_config.py tests/unit/test_model.py` — **9 passed**.
- `.venv/bin/pytest -q tests/integration/test_cnn_training.py` — **2 passed**.

These are prior-session reports, not reruns from this ZIP. Tests exercise Dataset → QProcess →
CNN → Model, preset independence, trusted fresh-process reload, cancellation/no-publication,
measured numeric Plot values and native navigation.

At this 05b checkpoint, shared `UT-TRAIN-003` and `IT-TRAIN-004`–`009`/`012`/`014` awaited RF and
wheel verification, subsequently reported in 05c below. Installed qualification remains in 06/07.

## Spec 05c — Real RF training and phase 05 acceptance

**Status: 05c implementation and macOS tests reported complete; owner sign-off not established by this ZIP.** The recorded RF Worker fits/evaluates real Dataset Snippets and publishes a structurally reloadable, checksummed binary Model through the common CNN/RF boundary. The macOS record reports `UT-TRAIN-001`–`010` and `IT-TRAIN-001`–`014` passing. No Prediction/new-WAV inference was added.

### Capture and scientific provenance

- Command: `.venv/bin/python scripts/capture_spec05_screenshots.py --output-dir
  docs/design/evidence/spec-05-native`
- Captured and reviewed 26 October 2026 on macOS 26.6.2 arm64; native Cocoa; Python 3.12.7;
  PySide6/Qt 6.11.2; `alp-ui` 0.1.0a0 at
  `330aaab96a6b32dd2d83ae84a52a2a238446d264`
- App/stored desktop PNGs: 1280×807; current Showcase: 1180×790; device-pixel ratio 2.0
- Scientific reference: targeted `../alpaca-pipelines` RF implementation at
  `91af5287dc18313f88902dc9696e8756274736b3`; direct reusable extractor dependency:
  `bioacoustics-dl-toolbox` 0.1.1 at `8e2e0528d4ce718005e194d426cde6e62fda0909`
- Data/privacy: generated mono PCM Source Recordings, timestamped positives and one real immutable
  target/noise Dataset used by both genuine CNN and RF Runs; no user or HPC data
- Capture mechanism: visible `QMainWindow`, native `QInputDialog` and Cocoa
  `QScreen.grabWindow`; the capture command rejects non-Cocoa/offscreen rendering

The pipeline's RF feature/preprocess code and tests were inspected at the recorded SHA before the
toolbox helper was reused. The Trainer adapter retains the exact ordered pipeline names while the
toolbox owns robust/MFCC calculation. Its loader's Kaiser resampler was not reused because it is
not equivalent to the inspected pipeline. The Trainer instead records and applies the pipeline's
current explicit `librosa` SOXR-HQ, fixed-length, unscaled policy before centered constant
zero-padding, with the `librosa` version, FFT/hop/band/MFCC/delta settings, float policies,
extractor revision, `classes_`, target probability column, threshold and ordered fitted
importances. No upstream source change was necessary.

Prototype `trainPage`, `rfChart`, `startTraining`, `modelPage`, relevant CSS/previews and the live
sibling Showcase were reviewed source-first. The latter was captured as
[alp-ui-showcase-current.png](spec-05-native/alp-ui-showcase-current.png); native images were reviewed at original resolution.

### State-by-state review

Six-dimension key: **H** information hierarchy/CTA/panel order; **N** navigation/active state;
**C** terms/copy/feedback; **A** `alp-ui` components/theme/icons/accessibility; **I** interaction,
focus, progress and resize; **S** real scientific/undefined/error/completed-state fidelity.

| State | Prototype target | Native evidence | Showcase and interaction evidence | Six dimensions | Difference / disposition |
|---|---|---|---|---|---|
| RF naming and launch | `startTraining()` / `nameModel()` | [model-name-rf.png](spec-05-native/model-name-rf.png) | Frozen loaded-preset config, family-specific stages and one-Active-Run gate; `IT-TRAIN-002/012/014` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | As for CNN, the final label is collected before the Worker so atomic publication never leaves unnamed/orphan trained bytes. |
| Completed RF Run and Plot | `runPage()` / `rfChart()` | [run-rf-plot.png](spec-05-native/run-rf-plot.png) | Real extract→fit→validate→verify stages; public `Plot.setBars`; exact selectable numeric alternative; `IT-TRAIN-005/006/007` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Browser demo bars are replaced by the fitted estimator's ordered values. RF never shows fictional epoch loss. Zero importances remain truthful numeric measurements. |
| Both-family Model list | `modelsPage()` | [models.png](spec-05-native/models.png) | One CNN and one RF genuinely trained from `dataset-training-evidence`; family, stable ID, readable label, Dataset/date and Inspect action; `IT-TRAIN-003/007/008` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | “Available to Prediction” remains omitted because structural reload does not authorize inference. |
| RF Model detail | `modelPage()` / `model-preview.png` | [model-detail-rf.png](spec-05-native/model-detail-rf.png) | Saved threshold, actual metrics/undefined reason, Dataset/Run links, immutable files and exact toolbox/scikit-learn provenance; `IT-TRAIN-003/006/007/008` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | The tiny evidence Dataset truthfully produced undefined F1 in this capture; the reason is displayed instead of a fictitious zero. The external Prediction CTA is replaced by the explicit scope boundary. |

### Verification record

- Red-first evidence: RF unit collection initially failed because the domain module did not exist;
  RF integration initially failed because no structural RF loader existed.
- `.venv/bin/pytest -q tests/unit/test_training_config.py tests/unit/test_model.py
  tests/unit/test_rf_training_domain.py` — **12 passed**.
- `.venv/bin/pytest -q tests/integration/test_training_ui.py
  tests/integration/test_cnn_training.py tests/integration/test_rf_training.py
  tests/integration/test_training_packaging.py` — **8 passed**.
- `.venv/bin/pytest -q` — **86 passed** in 53.17 s.
- `.venv/bin/ruff check src tests scripts` and `ruff format --check` — passed.
- `scripts/audit_test_ids.py`, `scripts/check_fixtures.py`, native `verify_handoff.py` and
  `git lfs fsck` — passed.
- `IT-TRAIN-009` built committed toolbox and Trainer wheels, installed their artifacts into an
  isolated target, and imported the RF workflow/extractor from those installed wheels rather than
  either sibling source tree. Rebuilt wheel SHA-256 values were
  `6aebdfe8aed86376691e34669e6213a314cc451f79541d0b4edaace1062b1f3e` (Trainer) and
  `ef98db07ba6e5cf320c62d0d5f6f3386c554d98cfd522df68d86fbb1a770dc1f` (toolbox).

These are recorded macOS development-app results, not an independent rerun or owner sign-off.
Installed `.app` and Windows qualification remain in Specs 06/07.

## Spec 05d — Local logging and diagnostics

**Status: implementation and native macOS development-app review complete; owner acceptance
pending.** The completed Dataset Run, Settings support actions, privacy confirmation and responsive
states were captured from the visible Cocoa app after a real QProcess Worker wrote its contained
JSONL log. The browser prototype was not changed; these are the secondary native-only controls
specified by 05d.

### Capture provenance

- Command: `unset QT_QPA_PLATFORM; .venv/bin/python scripts/capture_spec05d_screenshots.py`
- Captured and reviewed 26 October 2026 on macOS 26.6.2 arm64; native Cocoa; 1470×956 logical
  primary screen, device-pixel ratio 2.0 and logical DPI 72
- Runtime: Python 3.12.7; PySide6/Qt 6.11.2; `alp-ui` 0.1.0a0 from the sibling checkout at
  `330aaab96a6b32dd2d83ae84a52a2a238446d264`
- Stored PNGs: 1280×807 desktop, 700×780 narrow and 1180×790 current Showcase
- Scientific dependency was unchanged: editable `bioacoustics-dl-toolbox` 0.1.1 from sibling SHA
  `8e2e0528d4ce718005e194d426cde6e62fda0909`; the supplied `alpaca-pipelines` reference remained
  `91af5287dc18313f88902dc9696e8756274736b3`
- Data/privacy: generated mono PCM WAVs, isolated `/tmp` Collection and Application Settings, no
  user/HPC data; logs and exported ZIP assertions reject the temporary absolute path and WAV names
- Capture mechanism: visible `QMainWindow`, native `QMessageBox` and Cocoa `QScreen.grabWindow`;
  non-Cocoa/offscreen execution is rejected

Prototype `runPage()` and `settingsPage()`, their reachable states and responsive CSS were reviewed
source-first. The live sibling Showcase was launched and captured as
[alp-ui-showcase-current.png](spec-05d-native/alp-ui-showcase-current.png). All PNGs were inspected
at original resolution. The first narrow review exposed a two-column Settings mismatch; the native
cards were then made to stack at the prototype breakpoint, retested and recaptured.

### State-by-state review

Six-dimension key: **H** information hierarchy/CTA/panel order; **N** navigation/active state;
**C** terms/copy/feedback; **A** `alp-ui` components/theme/icons/accessibility; **I** interaction,
focus, confirmation, scroll and resize; **S** diagnostic/error/completed-state fidelity.

| State | Prototype / 05d target | Native evidence | Showcase and interaction evidence | Six dimensions | Difference / disposition |
|---|---|---|---|---|---|
| Completed Run log access | Baseline `runPage()` plus secondary 05d action | [run-open-log.png](spec-05d-native/run-open-log.png) | Existing activity/progress/output hierarchy is unchanged; contained log is revalidated immediately before native open; `IT-LOG-004` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | **Open log** is secondary to **Open Dataset** and appears only for a safe existing Worker log. Older Runs show explanatory copy instead of migration or fake evidence. |
| Diagnostics Settings | Baseline `settingsPage()` plus native support card | [settings-diagnostics.png](spec-05d-native/settings-diagnostics.png) | Public `Card`, `Text`, `Button` and `Alert` follow current Showcase density; Collection/read plan cards and route remain in prototype order; `IT-LOG-004` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | The additive card is below the complete baseline and introduces no primary route, configuration dashboard or upload action. |
| Export privacy confirmation | Explicit 05d consent contract | [export-privacy-confirmation.png](spec-05d-native/export-privacy-confirmation.png) | Native modal defaults to No and states local-only, revalidation/redaction, review-before-sharing and selected-Run scope; `IT-LOG-004` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Platform-native Yes/No labels are retained; no file chooser or overwrite occurs without affirmative consent. |
| Narrow completed Run | Responsive `runPage()` plus Open log | [run-open-log-narrow.png](spec-05d-native/run-open-log-narrow.png) | 700×780 stacked Run cards, horizontally reachable nav, both secondary log and primary output actions visible; keyboard focus asserted | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Native vertical scrolling retains all baseline content; no horizontal page clipping. |
| Narrow Settings hierarchy | Prototype responsive single-column Settings | [top](spec-05d-native/settings-stacked-narrow.png) · [diagnostics card](spec-05d-native/settings-diagnostics-narrow.png) | 700×780 cards stack Collection → reading plan → diagnostics; actions remain focusable and visible; `IT-LOG-004` | H **MATCH** · N **MATCH** · C **MATCH** · A **MATCH** · I **MATCH** · S **MATCH** | Two captures record the tall native page at top and bottom; ordinary vertical scroll connects them. |

`IT-LOG-004` separately activates Open log through the contained path, tabs to Export, accepts the
privacy confirmation, creates a new ZIP, verifies its inventory/selected Run scope, and checks
missing-log feedback. Screenshot evidence is not used as a substitute for those assertions.

### Verification record

- Red-first unit collection initially failed because the diagnostics module did not exist; native
  integration initially failed because stderr draining and log/export controls did not exist.
- `UT-LOG-001`–`004` exercise schema/levels/correlation, adversarial privacy normalization,
  containment/export revalidation, rotation/pruning, stderr bounds and degraded sinks.
- `IT-LOG-001`–`004` exercise real GUI/session/Scan, Dataset/CNN/RF QProcesses, identical
  `info`/`debug` scientific metrics and Model payload hashes, stderr storm failure, native access
  and sanitized export.
- Installed `.app`/Windows log locations, bundled Worker launch and platform dialogs remain the
  explicit Spec 06/07 gates; they are not claimed by these development-app captures.

## Spec 05e — Critical training-path and failure-recovery verification

**Status: verification complete; owner review pending.** No visible UI changed and no new
scientific feature was added, so the reviewed Spec 05/05d native screenshots remain the visual
record. The new integration assertions use the native Qt Start action, real supervised QProcesses,
real filesystem publication, persisted settings and generated PCM WAVs. They passed without an
application-code repair.

### Verification provenance and scope

- Verified from Trainer base SHA `f84e7bc663bd26d4cdcf43948e6cf38ede02d26d` on branch
  `spec/05e-training-verification`; the delivery commit SHA is reported at handoff.
- Host: macOS 26.6.2 (25G83), arm64; Python 3.12.7; PySide6/Qt 6.11.2; `alp-ui`
  0.1.0a0 from sibling SHA `330aaab96a6b32dd2d83ae84a52a2a238446d264`.
- Scientific dependency: editable `bioacoustics-dl-toolbox` 0.1.1 from recorded sibling SHA
  `8e2e0528d4ce718005e194d426cde6e62fda0909`. No upstream change was needed.
- Data/privacy: temporary generated mono PCM WAVs, one real immutable Dataset and isolated
  settings; no user Collection, private/HPC data or external connection.
- `IT-TRAIN-012`/`014`: loaded nondefault CNN and RF presets flow through the actual native Start
  button into the immutable request, real Worker executor and validated Model manifest. Editing or
  deleting each preset after launch cannot change the frozen snapshot; source WAV bytes remain
  unchanged.
- `IT-TRAIN-004`/`009` and `IT-RUN-003`/`004`: both Workers are forcibly killed before
  publication, and both are independently driven through a deterministic exclusive-publication
  lock failure. Restart reconciliation retains non-success state, releases the reservation, leaves
  no published pointer or staging output, and preserves an existing valid Model byte-for-byte.
- `IT-TRAIN-003`: the original window/controller are shut down and reconstructed from the same
  Collection/settings. The native Models list/detail shows CNN and Random Forest labels, stable
  identifiers, Dataset references, saved metrics and the genuine undefined-F1 reason. Existing
  fresh-process structural binary reload assertions remain in place.
- Contract search found no cross-application-process exclusivity guarantee. `IT-RUN-002` is
  explicitly scoped to one `WorkspaceController`/application process; no global lock was added and
  cross-process exclusivity remains unverified.

### Verification record

- New focused cases:
  `.venv/bin/pytest -q tests/integration/test_cnn_training.py::test_real_cnn_worker_publishes_reloadable_model_and_native_views tests/integration/test_rf_training.py::test_real_rf_worker_publishes_reloadable_model_and_native_views tests/integration/test_rf_training.py::test_both_training_families_recover_from_worker_loss_and_publication_failure`
  — **3 passed** on their first run; this demonstrated no runtime defect.
- Affected CNN/RF, native configuration, Run and 05d regression group:
  `.venv/bin/pytest -q tests/integration/test_training_ui.py tests/integration/test_cnn_training.py tests/integration/test_rf_training.py tests/integration/test_run.py tests/integration/test_diagnostics.py`
  — **18 passed**.
- `.venv/bin/pytest -q tests/unit/test_diagnostics.py` — **10 passed**.
- The first repo-wide `.venv/bin/pytest -q` stopped during collection because the unit and
  integration diagnostics modules share the basename `test_diagnostics.py`. Adding pytest
  `--import-mode=importlib` fixed that demonstrated test-harness defect.
- Repo-wide rerun — **101 passed, 1 failed in 98.63 s**. The only failure was the existing
  `IT-TRAIN-009` packaging precondition that the sibling toolbox checkout be clean; that checkout
  contains owner changes (`AGENTS.md`, `README.md`, `assets/`) and was not modified or cleaned by
  this work. All collected Trainer tests outside that external cleanliness gate passed.
- `.venv/bin/ruff check` and `.venv/bin/ruff format --check` for the changed tests, plus
  `scripts/audit_test_ids.py` (**74 IDs, 0 unknown**) and `scripts/check_fixtures.py` (**6 WAVs
  verified**) passed. Repository-wide `ruff check`, `verify_handoff.py`, `git diff --check` and
  `git lfs fsck` also passed; no `docs/priv` file is tracked. Repository-wide `ruff format --check`
  remains limited by five unchanged 05d-era files reported as unformatted; none is in this change.

## Every subsequent spec: mandatory ledger

Use [Prototype acceptance](../PROTOTYPE_ACCEPTANCE.md) for the full screenshot inventory and six
dimensions. Each implementing spec adds: reference route/state, native screenshot, actual `alp-ui`
SHA/OS/Qt/DPI/viewport, interaction `IT-*` evidence, six-dimension assessment and any
owner-accepted platform-only exception. Installed `.app`/`.exe` views get their own evidence
folders rather than reusing these development captures.
