# ST-03 native Detect evidence

These eight PNGs are genuine visible-window captures from the source application on the native
macOS Cocoa Qt platform, not browser or offscreen renders. They were captured on macOS 26.6.2 with
Python 3.12.7, PySide6/Qt 6.11.2, `alp-ui` 0.1.0a0 from sibling revision
`5bb61e3a4c4bd7104ade4375cc32082ea44e1d14`, and the Alpaca Light theme.

Capture command:

```bash
.venv/bin/python scripts/capture_st03_screenshots.py
```

The `empty`, `available`, `missing`, and `relink` states are captured at 1180 × 790 normal and
700 × 780 compact sizes. Every bound state uses a real temporary directory; `missing` is captured
after moving that directory and `relink` after selecting its new same-filesystem location. No WAV
inventory, Model, Run, result, or fabricated count is displayed.

Visual review against the approved ST-01 `#detect/setup` and Relink hierarchy found:

- The native screen keeps the setup heading, `Setup` → `Recordings` route hierarchy, one source
  card, clear state badge, source path, `FolderPicker`, keyboard-accessible `HelpHint`, and visible
  Studio return. Future Run/Results/Export destinations are omitted because they would be dead
  actions in ST-03.
- Empty state has one primary source action. Available, missing, and relink copy distinguishes a
  readable source from unavailable input without describing missing input as empty.
- Relink shows old/new locations, the re-review consequence, explicit checkbox confirmation,
  Cancel, and a disabled primary action until confirmation. Both paths remain readable at compact
  width and the page scrolls if host font metrics require more height.
- The presentation uses public `alp-ui` components plus ordinary Qt layout primitives. It contains
  no prototype selector, illustrative scientific value, developer commentary, inventory count, or
  simulated completion.

The Cocoa captures qualify this local native source UI only. Windows-native, installed-app, and
150% DPI evidence remain deferred and are not claimed by ST-03.
