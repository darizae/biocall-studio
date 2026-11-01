# REV-03 native evidence

These captures were produced with native macOS Cocoa while the host used **Dark** appearance.
The evidence command fails unless `defaults read -g AppleInterfaceStyle` reports `Dark`, then
asserts that BioCall Studio has forced `Qt.ColorScheme.Light` and installed `ALPACA_LIGHT` before
capturing any window. Every image shows the resulting light-only application UI.

The captures cover:

- the Studio launchpad at 1180×790 and 700×790;
- the real Train configuration route at both widths;
- Detect's incompatible-model correction at both widths, shown once without a duplicate readiness
  message;
- a genuine partial Result at both widths;
- genuine compact available, empty, stale and source-unavailable Result states. Available has no
  banner; the other images show the approved status, intent and recovery action.

The capture builds a genuine one-epoch Train CNN Model from temporary WAV files, opens that real
Dataset in Train, passes the Model through Detect intake, and runs real detection to create the
partial, populated and zero-call Results. It changes recording inclusion to make the earlier Result
stale and moves the temporary recordings folder to exercise relinking. No prototype or production
fixture data is displayed.

Capture command:

```bash
.venv/bin/python scripts/capture_rev03_screenshots.py
```

The capture used macOS 26.6.2 in Dark appearance, Python 3.12.7, PySide6/Qt 6.11.2, native Cocoa,
and the installed `alp-ui` 0.1.0a0 wheel with SHA-256
`de818d029bc96ee3be02b62ae85725c912e8eb23bcf28afd149f02ab53d54327`. The Studio branch was
created from reviewed local `detect` commit `f21b95c5b2446c4896a842c2d9e56cb8d7b7c91c`; its installed
editable `bioacoustics-dl-toolbox` dependency was at the separately committed numerical SNR-bound
fix `22c1b342918b33c62288f23b660aa716f3e361e6`.

The PNGs were visually reviewed for normal/compact layout, light-palette readability, duplicate
copy, internal identifiers and the five Result availability presentations. Automated behavior and
accessibility remain owned by `IT-UI-006`, `IT-TRAIN-015` and `IT-DET-024`; these images are visual
evidence, not a substitute for those tests.
