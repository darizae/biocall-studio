# ST-11 unified qualification record

> Review-era supplement: [RV-08 whole-Studio qualification](RV-08_QUALIFICATION.md) re-homes the
> existing `IT-STU-007`, `IT-STU-008` and `IT-DET-022` ownership through the current
> Train→Detect→Review→Export path. This file retains the 2026-11-01 pre-Review evidence record.

Date: 2026-11-01. Branch: `detect-st11-qualification`, based on reviewed local `detect` at
`0d129575a44a32eaefd0538e928eaf5b214a2a73`. `main` was not changed.

## Outcome

Source-application ST-11 qualification passes on the tested native Mac. Release/installer
qualification remains blocked/deferred because no `.app`, `.dmg`, Windows installer, signing,
notarization, clean-machine install or uninstall was authorized or executed. The ≥600-second soak
was not initiated.

| Case | Status | Evidence |
|---|---|---|
| `UT-STU-002` | pass | Pure immutable ownership, duplicate-ID rejection, global scientific admission and shared exit decision. |
| `IT-STU-007` | pass | One native Studio process retained Train, built a real Dataset and genuine CPU CNN/RF Models through QProcess, ran Detect scan→CNN→Results→RF→export, restarted and relinked. IDs/timestamps/digests were distinct and source WAV bytes stayed unchanged. |
| `IT-STU-008` | pass | Real Qt/QProcess global admission, one safe keep-open/stop confirmation, hidden-work ownership, forced crash recovery, bounded cancellation and no orphaned Worker. |
| `IT-DET-022` | pass | Installed toolbox CNN reference frame/score parity, independent RF feature order/class/probability parity, exact source-frame→snippet/concat/Raven mapping, PCM and file SHA-256 checks, receipt reopen and immutable parent/child Results. |
| `IT-E2E-001`, `IT-MAC-001`…`004` | deferred-native | Require a separately approved installed macOS package stage. |
| `IT-WIN-001`…`005` | deferred-native | Require a real supported Windows machine and installed package. |
| ≥600-second soak | skipped | Separately initiated only; not requested for this run. |

Targeted missing-Model, changed/replaced source, controlled failure, process crash and cancellation
cases also passed in the ordinary suite. They remain negative boundary evidence and were not
misreported as successful whole-Studio runs.

## Executed commands

```text
dx test .venv/bin/python -m pytest -q 
PASS — 218 passed, 1 soak test deselected by the configured default marker

dx lint .venv/bin/python -m ruff check .
PASS

dx check .venv/bin/python scripts/audit_test_ids.py
PASS

dx check .venv/bin/python scripts/check_fixtures.py
PASS

git diff --check
PASS

.venv/bin/python scripts/capture_st11_screenshots.py
PASS — nine visible native Cocoa captures
```

The final full suite was rerun after the shared-exit fixes. The earlier full run exposed and led to
fixes for an obsolete immediate-close expectation and a duplicate asynchronous close callback; it
is not counted as passing evidence.

## Environment and scientific provenance

- macOS 26.6.2 build 25G83, Darwin arm64, native Qt Cocoa platform.
- Python 3.12.7; PySide6/Qt 6.11.2; `alp-ui` 0.1.0a0; toolbox 0.2.0; Torch 2.14.1;
  scikit-learn 1.9.1; librosa 0.11.0.
- `bioacoustics-dl-toolbox` source revision
  `22c1b342918b33c62288f23b660aa716f3e361e6`, matching `pyproject.toml`.
- `alp-ui` source revision `8cdc91f56005fcd0f3c4004b66016b3d237a10c3`, matching
  `pyproject.toml`; the runtime import came from the installed `.venv` package.
- The toolbox runtime import resolved to the exact sibling source checkout. This is valid
  development/scientific qualification evidence but remains a packaging blocker until a release
  stage builds, pins and tests an independent wheel from that commit.
- Fixed CPU settings, fixed Train/RF seeds and generated deterministic PCM fixtures make the
  numeric chain reproducible. Every run uses private temporary directories and deletes them after
  assertions.

Branding checksums used by the revised release specifications:

```text
a8ac55cbef988ac92b25bb6993a385c13718e56881d137b2f1705057efb85cce  icon.icns
7135f6a948f23aa650d8a7ffb9f3a483a4e7263556bee1fdc1d834d93a43193f  icon.ico
1b42e15366eb582f2be3e187fd71bd24f70bd68bacd499ffbc238fdbbec0c78c  bundled icon-256.png
```

## Native UX review

The reviewed captures are in [ST-11 native evidence](design/evidence/st-11-native/README.md).
Normal and compact Studio/Train/Detect/Review views retain the accepted hierarchy, permanently
light theme, readable copy, reachable actions and responsive stacking. The shared exit dialog names
the owning workflow and operation, keeps **Keep app open** focused by default and provides one
explicit destructive exit action. No new owner-review deviation was found.

These source-app Cocoa captures are not installed-app evidence. The revised existing
[macOS](specs/06-macos-release-and-installer.md),
[Windows](specs/07-windows-release-and-installer.md) and
[release process](RELEASE_PROCESS.md) documents keep all packaging, signing and promotion gates
explicitly deferred.
