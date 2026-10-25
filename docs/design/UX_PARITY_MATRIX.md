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
| CNN / RF configuration (`rf-config-preview.png`) | family-specific parameters and explicit validation; context hints next to complex settings | `SelectInput`, `NumberInput`, `HelpHint` | 05: IT-TRAIN-001, 002, 005, 007 |
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

## Acceptance evidence, per UI spec

1. Capture actual Qt screenshots for the screen states **implemented** in the spec using installed `alp-ui` on native macOS; **commit sanitized PNGs** to `docs/design/evidence/spec-01-native/` (or the appropriate spec evidence subdirectory) and update [`evidence ledger`](evidence/README.md). Compare side-by-side to matching prototype preview and Showcase; explicitly record fixed, intentional, and unresolved differences. A screenshot saved under pytest `tmp_path` with nonzero filesize is *not* permanent parity evidence.
2. Verify data-dependent text/control states via `pytest-qt`, using `qtbot.waitUntil` and real widget accessible names/description. No HTML DOM-based app acceptance test.
3. Test native focus order, disabled action semantics, narrow resize/scroll and dialogs on target OS; `QT_QPA_PLATFORM=offscreen` is a preparatory smoke only.
4. `HelpHint` must be discoverable without a mouse; `FolderPicker` cancellation must not scan/reset; Plot needs readable tabular summary for exact values; undefined metrics stay undefined.
5. At each completed vertical, update this table if UX behavior changes. The **README must embed actual current native app screenshots** once a UI vertical is accepted, with separately labeled prototype design previews; do not pass off a simulated browser screenshot as native app. New interaction not in prototype requires explicit scope decision, not speculative implementation.

## How strict parity is enforced in the *subsequent* specs

The per-screen owner must deliver **both** the behavioral `IT-*` workflow proof **and** its native parity case: 02 → `IT-COL-008`; 03 → `IT-DB-005`; 04 → `IT-RUN-005`; 05 → `IT-TRAIN-007`; installer regressions → `IT-MAC-004` / `IT-WIN-005`. The [acceptance gate](PROTOTYPE_ACCEPTANCE.md) owns minimum screenshot filenames, dimensions, six-dimension review and the exception process. The current Spec 01 closeout is not accepted without its full screen inventory (including Settings/empty states), even when the first Select screenshot looks close.
