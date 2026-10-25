# Prototype-fidelity acceptance gate — every visible vertical

**Mandatory, not advisory.** The executable [Trainer prototype](prototypes/training-first/index.html), its `app.js` interaction states, `styles.css` hierarchy and bundled `*-preview.png` screenshots define the **target user journey and screen composition**. The *current installed* sibling [`alp-ui` Showcase](ALP_UI_CONSUMER_CONTRACT.md) defines native Qt styling/component conventions. The [parity matrix](UX_PARITY_MATRIX.md) assigns individual screens/states to specs and test IDs. A coding agent may not replace the prototype with its own preferred layout, remove visible content, substitute a generic form, or declare "close enough" because it used `alp-ui` classes.

Prototype inspection is source-first. Follow the active spec's UX matrix rows and search only relevant functions, states, CSS selectors and previews in docs/design/prototypes/training-first/. Do not launch browser automation by default. Use it only when an important interaction cannot be established from the bundled source and references. Native Qt screenshot capture and visual acceptance remain mandatory.

## Focused prototype lookup — all implementation specs

The table provides **optional starting points**, not prescribed inspection paths. The active [UX matrix row](UX_PARITY_MATRIX.md) can help identify a relevant view; the listed `app.js` symbols, approximate lines, matching `styles.css` selectors and bundled previews can help locate its behavior and appearance. For example, `rg -n '^function runPage\(' docs/design/prototypes/training-first/app.js` may be useful, but agents are free to inspect other functions, surrounding code or entire files whenever needed to understand and implement the interface faithfully. Line numbers are approximate and may move.

| Spec | `app.js` starting points (approximate lines) |
|---|---|
| 01 — shell / empty views | `renderNav` (81), `empty` (96), `home` (97), `wikiPage` (274), `settingsPage` (275), `render` (282) |
| 02 — scan / Collections | `showScan` (100), `cancelScan` (101), `scanSample` (103), `validateCollectionFiles` (123), `collectionsPage` / `collectionPage` (177–178) |
| 03 — Dataset Build | `buildPage` (186), `setBuild` (190), `refreshBuildSummary` (191), `runBuild` (214), `datasetPage` / `datasetsPage` (244/248) |
| 04 — Runs / Worker UX | `globalRun` (83), `createRun` (196), `advanceRun` (204), `cancelRun` / `confirmCancel` (225/228), `runPage` (230), `runsPage` (273) |
| 05a — training config / presets | `openTraining` (253), `trainPage` (254), `setTrain` (257), `startTraining` (258); native-only extension is specified separately below |
| 05b — CNN / shared Model | `trainPage` (254), `startTraining` (258), `lossChart` (239), `nameModel` / `saveModel` (262/266), `modelPage` (269) |
| 05c — RF / both-family UX | `trainPage` (254), `rfChart` (238), `startTraining` (258), `modelPage` (269), `modelsPage` (272) |
| 06–07 — installed releases | No separate prototype route; recheck only the implemented views/states from the applicable rows above in the **installed native app**. |

**No Run-specific preview PNGs exist in this bundle.** For Spec 04, infer Run detail, active/cancelling/failed/completed states and Runs history from the relevant `app.js` functions and `styles.css`; use the existing preview PNGs only for the shared visual language. Do not search for or invent Run preview images. Spec 04.5 is upstream audio extraction and has no separate prototype view.

## Native-only Spec 05 extension

The HTML prototype remains unchanged and governs the baseline Training view. The **compact primary roster**, collapsed **More settings**, saved presets, current/default/recommended values and additive-state review are owned in [Spec 05 native configuration extension](SPEC05_CONFIGURATION_EXTENSION.md). For the new controls review the written brief and actual native evidence, **not imaginary prototype screens**. Material layout changes to the baseline require owner acceptance.

## Priority and acceptable differences

1. **Prototype wins** for page structure, navigation destinations, section ordering, user-facing labels, hierarchy, state-dependent CTAs, empty/error/progress/finished views, contextual hints and feedback. Use the actual HTML/JS to inspect interactions, not just the landing PNG. A screen's reference includes its reachable states.
2. **Current sibling `alp-ui` Showcase wins** for actual native `QWidget` APIs, theme tokens, typography, cards, control density, focus/hover/disabled behavior, `FolderPicker`, `HelpHint`, `Plot` and Qt idioms. Prefer public components. Plain Qt layout containers may recreate the prototype hierarchy when `alp-ui` has no navigation/layout primitive.
3. **Scientific and safety contracts win** over the browser's fake progress, demo records/metrics, filesystem capabilities and simulated computation. Before the owning feature is implemented, show a clearly disabled/empty state in the *prototype's design language*, never a fake completed record. Do not ship prediction/inference just because an illustrative prototype panel mentions it.
4. Exact CSS pixels or web-only browser effects are **not** required. But a changed placement, missing panel/link/help text, generic left-aligned replacement, missing nav icon, different primary CTA or unmatched state **is a blocking mismatch** unless the owner expressly accepts a documented native-platform constraint. An agent cannot approve its own material redesign.

## Mandatory per-screen acceptance procedure (apply to specs 01–05 and installed release specs 06–07)

**Before implementation:** inspect only the active spec's [matrix](UX_PARITY_MATRIX.md) rows, prototype route/preview/CSS rules, and `../alp-ui/gallery/showcase.py` plus relevant public components. Enumerate screen states and transitions in the issue/PR, including initial, populated, invalid, busy/cancelled, disabled, completed and narrow layout **where applicable**. Do not load unrelated prototype routes or all Markdown files.

**Red tests first:** assert real Qt page/route identity, equivalent visible section headings, in-page action locations, user-facing control labels/help, enabled/disabled semantics, breadcrumb/sidebar transitions, navigation from CTA, keyboard/focus behavior and state transitions using `pytest-qt` and the real `alp-ui` control. Pure snapshot/PIL similarity cannot replace behavioral assertions. Keep normal scientific workflow tests too. Each spec owns its indexed UX integration case.

**Native review evidence:** run the actual app on the target OS with the installed sibling `alp-ui`; capture **persisted, sanitized native screenshots** for *each implemented reference view and consequential state* in `docs/design/evidence/spec-NN-native/` (`spec-06-installed/` or `spec-07-installed/` for release). Capture at the prototype's comparable desktop viewport and at an additional narrow/window-resized viewport where that screen can resize; record dimensions, scaling/DPI, OS, Python/Qt/`alp-ui` versions and sibling Git SHA. Place matching prototype reference and native screenshot links side by side in an evidence table. Screenshots from an HTML browser or pytest `tmp_path` are not native acceptance. An offscreen render is supplemental only.

**Review each row against six non-optional dimensions:** (a) information hierarchy, prominent CTA and panel order; (b) sidebar, breadcrumb, destinations and active state; (c) terms, labels, helper copy and feedback; (d) real `alp-ui` component choice, theme, icons, spacing and accessibility; (e) user interaction, focus/cancel/scroll and responsive width; (f) relevant empty/error/progress/disabled/completed states. For each dimension mark **MATCH / ACCEPTED NATIVE EXCEPTION / BLOCKED** and cite a screenshot + test or a short interaction recording/log. No blank dimensions and no self-approved exceptions. Reject screen signoff if any dimension remains BLOCKED, a reference state is absent or a screenshot is mislabeled. Automated test success by itself does not close the visual review.

**Before the spec's commit:** update [evidence ledger](evidence/README.md), [matrix](UX_PARITY_MATRIX.md), README (real **native** user screenshots, not only prototype previews), applicable `IT-*` rows and tested commands. Leave any incomplete visual item **OPEN** in the spec report; do not start the next spec. Review the same screens in an *installed* `.app`/`.exe` for specs 06/07. The `.zip` need not contain local test-data payloads; see [fixture policy](../INTEGRATION_TEST_DATA.md).

## Required screen groups and minimum images

| Owner | Target screens and states from prototype | Native evidence minimum (add more for substantive states) | Acceptance case |
|---|---|---|---|
| 01 + closeout | Landing/Select, Wiki, Settings, initial empty Collections/Datasets/Models/Runs, active/sidebar navigation | `select.png`, `wiki.png`, `settings.png`, `empty-collections.png`, `empty-datasets.png`, `empty-models.png`, `empty-runs.png`, `select-narrow.png` | `IT-UI-004` |
| 02 | Reading/Scan, Collection overview, validation issues, corrected/rescanned valid state | `scanning.png`, `collection-valid.png`, `validation-errors.png`, `collection-narrow.png` | `IT-COL-008` |
| 03 | Build config, estimate/underfill, Dataset list/detail, disabled/busy Build | `builder.png`, `builder-underfill.png`, `dataset-detail.png`, `builder-narrow.png` | `IT-DB-005` |
| 04 | Active Run and sidebar, Run detail while working/cancelling/failed/completed, Runs history | `run-active.png`, `run-cancelling.png`, `run-failed.png`, `runs-history.png` | `IT-RUN-005` |
| 05 | CNN/RF configuration, real training progress/plots, Model list/detail | `train-cnn.png`, `train-rf.png`, `train-cnn-advanced.png`, `train-rf-advanced.png`, `presets-list.png`, `presets-unsaved.png`, `presets-confirm-delete.png`, `run-cnn-plot.png`, `run-rf-plot.png`, `model-detail.png` | `IT-TRAIN-007` |
| 06 | Installed macOS app reproduces all implemented screen groups, native dialogs/theme/fonts/resources and narrow sizes | `spec-06-installed/` comparison set of representative screens plus installed smoke log | `IT-MAC-004` |
| 07 | Installed Windows app reproduces all implemented screens within native platform constraints (including DPI variants) | `spec-07-installed/` comparison set and DPI+keyboard review | `IT-WIN-005` |

A screenshot filename in this table is a **required future deliverable**, not an assertion that it currently exists. Screenshot sets may be expanded as interaction design reveals more relevant states; never populate them with fabricated Qt images. Owner-approved omissions of a *nonexistent scientific state* must be labeled **NOT IMPLEMENTED YET** and cannot be represented as a completed feature.
