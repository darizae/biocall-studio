# Review correction — visual baseline and visible native evidence

The `targets/` files are unchanged, byte-for-byte copies of the tracked HTML prototype screenshots from the `review` branch. The `native-before/` files are the earlier RV-05 offscreen Qt captures. The `native-after/` files are the final RV-09 screenshots captured from the **visible PySide6 application on Cocoa** after screenshot-driven corrections.

## Final capture provenance

- Capture: 2026-11-06 15:02:41 UTC, deliberately authorized visible desktop session.
- Application revision: `48d9ba92dd1c0f0b90065090d12570b3dc4814a3` on `review-rv09-native-visual-parity`.
- `alp-ui`: sibling revision `8cdc91f56005fcd0f3c4004b66016b3d237a10c3`; installed distribution `0.1.0a0` imported from `.venv/lib/python3.12/site-packages/alp_ui/__init__.py`.
- Platform: macOS 26.6.2 (25G83), arm64; Qt 6.11.2 using the Cocoa platform plugin.
- Display: Built-in Retina Display, scale 2.0; 1470×956 total and 1470×835 available logical pixels.
- Capture method: `QScreen.grabWindow` over the visible, focused Studio client area. This is composited Cocoa output, including native modal dialogs—not `QWidget.grab()` or offscreen Qt.
- Viewports: normal 1280×807 logical / 2560×1614 pixels (the maximum 1280-wide client height available below the macOS menu bar); compact 700×790 / 1400×1580; narrow 520×790 / 1040×1580.
- Fixture: generated 10-second, mono 8 kHz PCM WAV `woodland-dawn-2026-11-05.wav`, SHA-256 `d8911051699554d746a44c4b90d839529e85fb6d0b8147d6fc9efa5ed25fdafa`; 12 deterministic eligible candidates and Open, Closed and Finalized sessions. The fixture exercises real intake/session/cache/rendering UI boundaries but is not scientific qualification data.
- Machine-readable dimensions and fixture details: [`native-after/capture-metadata.json`](native-after/capture-metadata.json).

The capture command was bounded by the RV-09 120-second limit and passed:

```text
BIOCALL_RV09_EVIDENCE_DIR=.../native-after \
  perl -e '$t=shift; alarm $t; exec @ARGV' 120 \
  .venv/bin/python scripts/run_tests.py native --allow-visible \
  tests/integration/test_review_rv09_native_evidence.py -q
1 passed
```

## Paired evidence and comparison

| Screen | Prototype target | Earlier native | Visible Cocoa after | Comparison and deliberate deviations |
|---|---|---|---|---|
| Launchpad | [`targets/00-studio.png`](targets/00-studio.png) | none | [`native-after/00-studio.png`](native-after/00-studio.png) | Three equal cards retain the target hierarchy. All Open actions are identical outline/large buttons; this deliberately replaces the target's uniquely filled Review button per the later owner requirement. |
| Choose Result | [`targets/01-choose-result.png`](targets/01-choose-result.png) | none | [`native-after/01-choose-result.png`](native-after/01-choose-result.png) | Persistent sidebar, page title, preset, result selection and Start session hierarchy match. Native table selection replaces web-demo radio decoration. |
| Sessions | [`targets/02-sessions.png`](targets/02-sessions.png) | none | [`native-after/02-sessions.png`](native-after/02-sessions.png) | Dedicated Sessions route shows Open, Closed and Finalized state, counts, selection and contextual action. Required Delete session is visible. |
| Gallery | [`targets/03-gallery.png`](targets/03-gallery.png) | [`native-before/gallery.png`](native-before/gallery.png) | [`native-after/03-gallery.png`](native-after/03-gallery.png) | Three-column normal gallery, filters, controls and progress follow the target. Real renderer thumbnails now preserve aspect ratio; prototype-only illustrative calls and checkboxes were not copied. |
| List | [`targets/04-list.png`](targets/04-list.png) | [`native-before/list-compact.png`](native-before/list-compact.png) | [`native-after/04-list.png`](native-after/04-list.png) | Readable source time, duration, prediction and label columns sit under the same Review controls and persistent sidebar. |
| One by one | [`targets/05-one-by-one.png`](targets/05-one-by-one.png) | [`native-before/one-by-one.png`](native-before/one-by-one.png) | [`native-after/05-one-by-one.png`](native-after/05-one-by-one.png) | Large real spectrogram/audio card and grouped labeling actions match the target emphasis. Axis labels and detected interval come from renderer metadata. Irrelevant bulk footer actions are hidden in this view. |
| Spectrograms | [`targets/06-spectrograms.png`](targets/06-spectrograms.png) | none | [`native-after/06-spectrograms.png`](native-after/06-spectrograms.png) | Dedicated route shows preset, storage, generation actions and verified 12-of-12 cache availability. Native storage estimation retains the existing scientific/storage contract. |
| Finalize | [`targets/07-finalize.png`](targets/07-finalize.png) | none | [`native-after/07-finalize.png`](native-after/07-finalize.png) | Native Cocoa modal states the seven unreviewed detections and model-detection consequence; Cancel is the default and Finalize remains explicit. |
| Export | [`targets/08-export.png`](targets/08-export.png) | none | [`native-after/08-export.png`](native-after/08-export.png) | Finalized-decision summary and previous exports restore the target's information balance beside real format/destination and preflight controls. |
| Compact Gallery | [`targets/09-compact-gallery.png`](targets/09-compact-gallery.png) | none | [`native-after/09-compact-gallery.png`](native-after/09-compact-gallery.png) | Exact 700×790 logical viewport, compact sidebar and a readable two-column gallery with essential controls visible. |
| Compact One by one | [`targets/10-compact-one-by-one.png`](targets/10-compact-one-by-one.png) | none | [`native-after/10-compact-one-by-one.png`](native-after/10-compact-one-by-one.png) | Exact 700×790 viewport stacks the large spectrogram above the label card without the unrelated bulk footer. |
| Narrow One by one | [`targets/11-narrow-one-by-one.png`](targets/11-narrow-one-by-one.png) | none | [`native-after/11-narrow-one-by-one.png`](native-after/11-narrow-one-by-one.png) | Exact 520×790 viewport uses icon-only persistent navigation and keeps session state, core actions, plot, audio and labeling legible. |
| Spectrogram settings | Historical prototype HTML only | [`native-before/settings.png`](native-before/settings.png) | [`native-after/12-settings.png`](native-after/12-settings.png) | Existing preset/settings contract is retained as a dedicated Spectrograms child page with accessible help and Test WAV controls. |
| Delete session | Owner-required addition | none | [`native-after/13-delete-session.png`](native-after/13-delete-session.png) | Native destructive confirmation uses the approved copy, names the selected Closed session, preserves exports, and defaults to Cancel. Open and Finalized behavior are covered by indexed tests. |
| Review data folder | Owner-required addition | none | [`native-after/14-review-data-folder.png`](native-after/14-review-data-folder.png) | Subtle Settings route exposes the current Review-owned location and Change folder action without conflating it with spectrogram presets. Migration/failure/restart behavior is covered separately. |

## Corrections driven by the visible capture

The first visible pass was inspected rather than accepted as decoration. It exposed and led to these final changes:

- lowered the Studio shell minimum width from 640 to 520 so the required narrow native viewport is real;
- reserved right-axis paint space so the last spectrogram time label no longer clips;
- hid Gallery/List bulk actions while in One by one, recovering compact vertical space;
- tightened the compact sidebar and gallery grid to restore two columns at 700 px;
- hid the redundant session chip in compact mode;
- added Finalized decisions and Previous exports to the native Export screen;
- waited for cache availability before capturing Spectrograms, so the evidence records actual state rather than a transient check.

## `alp-ui` decision

No reusable `alp-ui` gap was found. RV-09 composes the documented ordinary-Qt sidebar pattern with installed public `Button`, `FolderPicker`, `Text`, theme-token and icon APIs. The sibling checkout was clean at the revision above and the installed package source was verified against it. No ceremonial upstream branch or commit was created.

The PNG set establishes real visible Cocoa evidence. Automated tests and this agent's pixel inspection do not substitute for the owner's final visual approval; the committed pairs above are the exact artifacts presented for that decision.

## RV-10 responsive spectrogram evidence — 2026-11-06

RV-10 was recaptured after the asynchronous Gallery/detail, cache-retention and local-calibration implementation was committed. The additive [`native-rv10/`](native-rv10/) set contains the same 15-screen normal, compact and narrow journey as RV-09; the target, native-before and RV-09 evidence above remain unchanged.

- Capture: 2026-11-06 20:57:07 UTC from committed application revision `27d94b870bb62e7accfdf6a68865934347b716ad` on `review-rv10-spectrogram-interactivity`.
- `alp-ui`: unchanged clean sibling revision `8cdc91f56005fcd0f3c4004b66016b3d237a10c3`; installed distribution `0.1.0a0` imported from `.venv/lib/python3.12/site-packages/alp_ui/__init__.py`.
- Platform and display: macOS 26.6.2 arm64, Qt 6.11.2 Cocoa, Built-in Retina Display at device-pixel ratio 2.0. Normal 1280×807, compact 700×790 and narrow 520×790 logical viewports were captured through `QScreen.grabWindow`.
- Fixture: the same generated 10-second mono 8 kHz PCM WAV and 12-candidate session set described above. It exercises the real WAV, cache, worker and native presentation boundaries but is not a representative natural field-call cohort.
- Machine-readable capture details: [`native-rv10/capture-metadata.json`](native-rv10/capture-metadata.json).

The bounded visible command closed all native windows and passed:

```text
BIOCALL_RV09_EVIDENCE_DIR=docs/design/evidence/review-correction/native-rv10 \
  perl -e 'alarm 120; exec @ARGV' \
  .venv/bin/python scripts/run_tests.py native --allow-visible \
  tests/integration/test_review_rv09_native_evidence.py -q
1 passed in 12.36s
```

The recaptured [`Gallery`](native-rv10/03-gallery.png) and [`compact Gallery`](native-rv10/09-compact-gallery.png) visibly contain populated, aspect-preserved thumbnails with source-interval overlays; no Generate all prerequisite is used. The [`One by one`](native-rv10/05-one-by-one.png), [`compact`](native-rv10/10-compact-one-by-one.png) and [`narrow`](native-rv10/11-narrow-one-by-one.png) screens show the full-size data plot with renderer-derived time/frequency axes and the detected interval. The [`Spectrograms`](native-rv10/06-spectrograms.png) screen records the truthful completed state, “Retained 12 of 12 thumbnails.” Persistent navigation and the RV-09 deletion/data-folder screens remain present throughout the additive set.

No reusable presentation-library defect emerged, so RV-10 made no upstream `alp-ui` change. Visual inspection of these artifacts found no aspect-ratio, clipping or hierarchy regression. Physical playback, hover/focus behavior, assistive-technology use, natural field-call readability and the owner's visual approval are not established by the screenshot automation and remain explicit gates.
