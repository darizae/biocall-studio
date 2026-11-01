# ST-11 native unified-Studio evidence

Captured from visible macOS Cocoa windows on macOS 26.6.2 (arm64), Python 3.12.7,
PySide6/Qt 6.11.2 and `alp-ui` 0.1.0a0. These are native source-application captures, not browser,
prototype or offscreen renders. They do not qualify an installed `.app`, DMG, Windows build,
signing or notarization.

Capture command:

```bash
.venv/bin/python scripts/capture_st11_screenshots.py
```

The `studio-*`, `train-*`, `detect-*` and `review-*` pairs cover 1180 × 790 normal and
700 × 780 compact windows. The review checked the accepted Studio hierarchy, retained native Train,
guided Detect navigation, the explicit Review placeholder, permanently light theme, readable copy,
keyboard-focusable actions and compact stacking without horizontal content loss. Existing
stage-owned evidence under `st-03-native` through `st-10-native` remains the detailed record for
Detect missing/stale/error/busy/results/RF/export states.

`shared-exit-confirmation.png` was captured with a real Dataset Build QProcess active while Train
was hidden. It shows the one Studio-owned confirmation, names the owning workflow and active work,
keeps **Keep app open** as the focused safe default, and offers one destructive **Stop work and
Exit** action. The capture script chose that action and waited until both Train and Detect owners
had completed supervised shutdown.

Scientific qualification is executed by `IT-STU-007` and `IT-DET-022`; QProcess contention,
crash recovery, keep-open/confirm and orphan prevention are executed by `IT-STU-008`. The
separately initiated ≥600-second soak was not run.
