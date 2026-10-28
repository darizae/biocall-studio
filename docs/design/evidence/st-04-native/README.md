# ST-04 native recording inventory evidence

Captured from real visible macOS Cocoa windows with:

```text
macOS 26.6.2
Python 3.12.7
PySide6 / Qt 6.11.2
alp-ui 0.1.0a0, sibling checkout 5bb61e3a4c4bd7104ade4375cc32082ea44e1d14
Qt platform cocoa
```

The reproducible command is:

```bash
.venv/bin/python scripts/capture_st04_screenshots.py
```

The capture uses actual generated PCM mono/stereo WAV files and the real scanner, controller,
app-owned inventory publication, Qt model/view, `alp-ui.DataTable`, and native window. It does not
inject example inventory rows.

| File | Observed state |
|---|---|
| `recordings-ready-normal.png` | Ready inventory at 1180×790: counts, hierarchy, selected-folder detail, explicit decisions, root and Rescan. |
| `recordings-ready-compact.png` | Ready inventory at 700×780: compact margins and the detail card stacked below the paged table. |
| `recordings-scanning-normal.png` | Live background Scan with determinate progress surface, disabled Rescan and keyboard-operable Cancel scan. |
| `recordings-cancelled-normal.png` | Cancellation state with no partial snapshot and an explicit rescan recovery action. |
| `recordings-invalid-compact.png` | Invalid included WAV state, distinct from a valid zero-candidate result. |
| `recordings-stale-normal.png` | Previously published inventory after a real source-file edit; browsing remains visible and use is blocked pending rescan. |
| `recordings-missing-compact.png` | Missing root with the accepted ST-03 relink control and preserved inventory counts. |

Visual review against the approved `#detect/recordings` prototype confirmed the same information
order: route heading and Rescan, state feedback/progress, inclusion counts, visible hierarchy and
decision actions, then selected item detail. The native implementation deliberately uses one paged
`DataTable` with folder summary rows instead of HTML nested buttons, and hides the large root/relink
card while the binding is healthy so the inventory remains visible. The relink card returns for
missing/changed states. At compact width, detail moves below the table rather than becoming a narrow
side column.

Automated `IT-DET-005` additionally exercised native keyboard table navigation, Space activation of
decision controls and the accessible inclusion `HelpHint`, canceled native folder picker, 200-row
paging, live count updates, normal/compact reflow, and stable-key selection preservation after
rescan. Browser automation is not claimed as test evidence.
