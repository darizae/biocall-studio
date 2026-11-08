# 07 — Controlled Windows BioCall Studio installer and native qualification

**Status:** revised by ST-11; Windows freezing, installer production, signing, clean-machine tests
and publication are **deferred** to a separately approved packaging stage. macOS or offscreen Qt
evidence cannot satisfy this specification.

## Installed outcome

On a clean supported Windows x86-64 machine, a non-developer installs one versioned **BioCall
Studio** `.exe`, opens the Studio launchpad, runs real Train and Detect workflows, restarts/relinks
and uninstalls cleanly. Review is source-implemented; actual installed Windows Review sessions, spectrogram/audio and export behavior still require platform qualification. No Python, venv, source checkout,
shell, network access or sibling repository is required.

The package includes Qt/`alp-ui`, fonts, icons and every Train Dataset/CNN/RF and Detect CNN/RF
Worker runtime. Workers launch through the frozen `--worker` entry. Train inputs and Detect source
recordings remain byte-identical; immutable Models, Results and exports are reopened and verified.
Detect's versioned metadata stays in the standard per-user BioCall Studio application-data root,
outside source folders, while exports go only to the user-selected destination.

## Build, install and security requirements

1. Build from one clean reviewed tag with pinned Python, PySide6, `alp-ui`, direct
   `bioacoustics-dl-toolbox` and scientific wheels. Record source SHAs and wheel/lock/branding
   SHA-256 values. Editable checkouts and machine-specific absolute paths are forbidden.
2. Select and license a maintained Windows freezer and installer tool (for example Inno Setup),
   then bundle the exact GUI/Worker/science resources tested. No global interpreter or shell
   fallback is allowed.
3. Installer, Add/Remove Programs, Start menu, taskbar and windows must say **BioCall Studio** and
   use `assets/branding/icons/icon.ico`; validate its embedded sizes and digest. Reject the former
   Train-only name and generic Qt/Python icons.
4. Install binaries under Program Files and keep mutable application data under the standard
   per-user location with separate `train/v1` and `detect/v1` ownership. Test drive letters,
   Unicode/NFC/case collisions, reserved names, long paths, read-only paths, file locks, UNC where
   supported and reparse/junction containment.
5. Exercise fresh install, upgrade, restart, moved/relinked recordings and uninstall. Uninstall
   must remove installed binaries/shortcuts without deleting source recordings, Train Collections,
   Detect exports or per-user data unless an explicit separately reviewed removal option identifies
   them.
6. Sign executables and installer according to the distribution policy, verify signatures and
   SHA-256, run dependency/license/security review, publish an immutable manifest and require
   explicit owner promotion. Missing credentials or legal approval blocks distribution.

## Preserved native test IDs

- `IT-WIN-001`: real Windows path, case/Unicode collision, reparse containment, file-lock and
  atomic-update coverage for both workflow-owned data boundaries.
- `IT-WIN-002`: native Qt/`alp-ui` folder pickers, keyboard HelpHints, bundled Train/Detect
  QProcess launch, global admission, cancel/crash recovery and shared safe quit.
- `IT-WIN-003`: installed Studio builds/reopens a real Dataset and CNN/RF Models, structurally
  reloads both, runs Detect CNN→RF, reviews candidates, exports/reopens WAV+TSV from Review,
  restarts/relinks and preserves exact provenance with byte-identical inputs.
- `IT-WIN-004`: clean install/upgrade/uninstall, BioCall Studio ICO/identity, per-user data,
  manifest/digest/security/signing evidence and preservation of user-owned Collections/exports.
- `IT-WIN-005`: installed Studio/Train/Detect normal and compact UI at 100%/150% DPI, keyboard and
  focus order, accessible HelpHints, plots and numeric alternatives, empty/error/busy/success
  states, the Review workspace and owner-reviewed native differences. Save native screenshots under
  `docs/design/evidence/spec-07-installed/`.

Installed configuration coverage must include representative basic and advanced CNN/RF fields,
HelpHint/Wiki access, saved preset persistence and exact resolved Model settings.

## Promotion blockers

Missing native hardware/VM evidence, committed scientific dependency wheels, bundled Worker
coverage, immutable/checksum verification, path-containment results, clean uninstall evidence,
screenshots, signing/security/legal review or owner approval blocks promotion. Do not advertise a
Windows installer from a successful source-tree or macOS run.
