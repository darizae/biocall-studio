# ST-02 native Studio evidence

These are genuine visible-window captures from the source application, not browser or offscreen
renders. They were captured on macOS 26.6.2 with the Cocoa Qt platform, Python 3.12.7,
PySide6/Qt 6.11.2, `alp-ui` 0.1.0a0 at sibling revision
`5bb61e3a4c4bd7104ade4375cc32082ea44e1d14`, and the Alpaca Light theme.

Capture command:

```bash
.venv/bin/python scripts/capture_st02_screenshots.py
```

The `studio-*`, `train-*`, `detect-*`, and `review-*` files cover 1180 × 790 normal and
700 × 780 compact windows. Review against the accepted ST-01 composition and native Train baseline
found:

- Studio keeps the three-card hierarchy, copy, action priority, suite branding, and stacked compact
  composition. Public `alp-ui` line icons replace CSS-drawn prototype symbols.
- Train remains its real existing window and layout. The optional Back to Studio action is added to
  the Run header and remains visible at compact width.
- Detect is intentionally only an unavailable landing in ST-02; no Model picker, recording scan,
  Run action, result, or persisted Detect state is present.
- Review remains a Coming later landing with a keyboard-focusable return.

`IT-STU-006` also grabs all eight states during pytest. These Cocoa captures qualify the local
native source UI only; they do not qualify an installed macOS app, Windows, or 150% DPI behavior.
