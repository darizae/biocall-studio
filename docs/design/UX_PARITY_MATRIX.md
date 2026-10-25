# UX parity contract — browser prototype → native Trainer

**Normative reference:** `docs/design/prototypes/training-first/index.html` (HTML/CSS/JS + checked-in `*-preview.png` screenshots). **Native presentation reference:** sibling `../alp-ui/gallery/showcase.py`, `../alp-ui/docs/images/showcase.png` (also [bundled snapshot](references/alp-ui-showcase.png)) and `../alp-ui/docs/components.md`. The prototype is **included in this repository**, not a remote service. The HTML preview simulates computation; never carry `DEMO DATA`, fake progress, fake metrics or browser file-handle semantics into released scientific views.

The bar for completion is **screen-by-screen faithful UX and working Python/Qt**, not HTML pixel identity. Follow the **blocking [Prototype fidelity gate](PROTOTYPE_ACCEPTANCE.md)** for all screens/states and native evidence. An agent may not waive a layout/navigation mismatch unilaterally. Compare screen hierarchy, words, controls, navigational transitions, responsive sizes, errors, empty/loading/completed/disabled states and keyboard accessibility. Use real `alp-ui` public components for controls (see [component mapping](ALP_UI_CONSUMER_CONTRACT.md)), plus ordinary Qt layouts when absent; do not vend an HTML `QWebEngineView` as the app.

| Prototype screen/state | Native requirement | `alp-ui` controls | Owner spec / tests |
|---|---|---|---|
| Landing / Select Collection (`landing-preview.png`) | Folder field & primary intent, short structure instruction, Wiki navigation, no simulated records | `FolderPicker`, `Button`, `Text`, `HelpHint` if appropriate | 01: IT-UI-001, 003, 004 |
| Reading/Scan (`scanning-preview.png`) | Nonblocking enumerating/header counts, cancel, accessible progress and visible specific issue | `ProgressBar`, `Text`, `Alert` | 02: IT-COL-001, 005, 008 |
| Collection + validation (`collection-preview.png`, `validation-preview.png`) | count/duration/positive mapping; exact per-path issues and fix suggestions; Build disabled on invalid/stale | `Card`, `Badge`, `DataTable`, `Alert`, `Button` | 02: IT-COL-001, 002, 007, 008 |
| Dataset Builder (`builder-preview.png`) | source selection, negative windows/margin/seed, grouped split ratio, intelligible help, feasible/underfill preview | `DataTable`, `NumberInput`, `SelectInput`, `HelpHint`, `Button` | 03: IT-DB-001, IT-DB-005 |
| Dataset Run, active navigation | real stage/progress/cancel; single active Run; safe interruption | `ProgressBar`, `Badge`, `Alert`, `Button` | 04: IT-RUN-001, 003, 005 |
| Dataset detail / lists | immutable counts/split provenance; explicit delete, no silent dependent Model removal | `Card`, `DataTable`, `Badge`, `EmptyState` | 03/04: IT-DB-005, IT-RUN-005 |
| CNN / RF configuration (`rf-config-preview.png`) | **Existing** prototype hierarchy and basic CNN/RF controls are mandatory. Extend **only in native app**, with only a handful of primary controls plus a compact, collapsed **More settings** extension showing current/default/suggested starting values on demand, and user presets per [Spec 05 extension](SPEC05_CONFIGURATION_EXTENSION.md); field-level `HelpHint` + Wiki anchors, validation and no reference-code paths. The browser prototype is **unchanged** and does not depict the added controls. | `SelectInput`, `NumberInput`, `HelpHint`, `Button` | 05: IT-TRAIN-001, 002, 007, 010–014 |
| Training Run | CNN measured train/val loss in native line Plot; RF fit/validation stages + actual importance bar Plot; no fictional epoch curve for RF | `Plot`, `ProgressBar`, `DataTable`, `Text` | 05: IT-TRAIN-005, 006, 007 |
| Model (`model-preview.png`) | stable ID, readable name, family and Dataset links, metric values/undefined reason, recorded schema | `Card`, `Badge`, `DataTable`, `Plot` only for meaningful values | 05: IT-TRAIN-003, 006, 007 |
| Wiki (`wiki-preview.png`) / Settings | collection naming examples and corrective advice; machine-only remembered folder/relink | `Text`, `Card`, `FolderPicker`, `Button` | 01/02 |
| Empty Collections/Datasets/Models/Runs | unambiguous next action; no rows or phantom success | `EmptyState`, `Button` | 01: IT-UI-001, 004 |

**Spec 01 evidence:** the Select, Wiki, Settings, four initial empty routes and narrow Select view
passed the six-dimension native review at the current sibling `alp-ui` SHA. See the tracked
[Cocoa screenshots and interaction ledger](evidence/README.md); `IT-UI-004` remains the behavioral
assertion seam rather than a pixel-similarity claim.

**Spec 02 evidence:** Reading, invalid Collection, corrected/rescanned valid Collection and narrow
Collection views passed the six-dimension native review at the current sibling `alp-ui` SHA. See
the tracked [Cocoa screenshots and interaction ledger](evidence/README.md); `IT-COL-008` asserts
the real-WAV route, CTA, focus, repair/rescan and compact-layout behavior.

**Spec 03 evidence:** Builder ready, underfill, disabled/busy, Dataset list/detail and narrow
Builder views passed the six-dimension native review at the current sibling `alp-ui` SHA. See the
tracked [Cocoa screenshots and interaction ledger](evidence/README.md); `IT-DB-005` asserts real
config changes, native controls/help, the QProcess Build handoff and Dataset navigation. Persisted
Run history/cancel/recovery remains owned by Spec 04 and no `IT-RUN-*` coverage is claimed.

**Spec 04 evidence:** Active, cancelling, failed and completed Run detail, persisted Runs history
and narrow Run detail passed the six-dimension native review at the current sibling `alp-ui` SHA.
See the tracked [Cocoa screenshots and interaction ledger](evidence/README.md); `IT-RUN-005`
asserts the real Worker-event hierarchy, Active Run navigation, cancellation, terminal feedback,
history, keyboard focus and responsive layout.

## Acceptance procedure

[Prototype acceptance](PROTOTYPE_ACCEPTANCE.md) owns native screenshot capture, the six-dimension review, exception handling and installed-app gate. [Evidence ledger](evidence/README.md) owns historical reviewed evidence. This matrix owns only **which prototype states/components belong to each spec**; update its rows as scoped behavior changes.
