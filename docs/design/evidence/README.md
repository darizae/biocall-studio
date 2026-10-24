# Native UX parity evidence — Spec 01

**Status: COMPLETE — ready for owner review.** The eight required Trainer views were captured
from a visible native macOS Cocoa window and reviewed against the checked-in interactive
prototype and current sibling `alp-ui` Showcase. No blocking mismatch or native exception remains.

## Capture provenance

- Command: `unset QT_QPA_PLATFORM; .venv/bin/python scripts/capture_spec01_screenshots.py`
- Host: macOS 26.6.2 (25G83), arm64; native Cocoa platform; 1470×956 screen
- App viewport: 1180×790 logical pixels for desktop views; 700×780 for narrow Select
- Captured PNGs: 2360×1580 and 1400×1560 at device-pixel ratio 2.0; logical DPI 72
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

## Every subsequent spec: mandatory ledger

Use [Prototype acceptance](../PROTOTYPE_ACCEPTANCE.md) for the full screenshot inventory and six
dimensions. Each implementing spec adds: reference route/state, native screenshot, actual `alp-ui`
SHA/OS/Qt/DPI/viewport, interaction `IT-*` evidence, six-dimension assessment and any
owner-accepted platform-only exception. Installed `.app`/`.exe` views get their own evidence
folders rather than reusing these development captures.
