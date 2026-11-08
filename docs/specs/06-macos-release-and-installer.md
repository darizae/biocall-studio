# 06 — Controlled macOS BioCall Studio packaging and installable DMG

**Status:** revised by ST-11; every installer, signing, notarization, clean-machine and
installed-app check below is **deferred** to a separately approved packaging stage. No `.app` or
`.dmg` was produced by ST-11.

**Scoped references:** [release process](../RELEASE_PROCESS.md),
[ST-11](ST-11-unified-qualification.md), `IT-E2E-*` / `IT-MAC-*` in the
[integration index](../INTEGRATION_TEST_BEHAVIORS.md), and the checked-in suite branding in
`assets/branding/`.

## Installed outcome

A non-developer installs one versioned **BioCall Studio** `.app` from a signed, notarized and
stapled `.dmg`. The app opens the Studio launchpad and the real Train and Detect workflows;
Review is implemented in the source application; this installer gate must qualify its native session, audio, spectrogram and reviewed export behavior on the installed build. A clean machine needs no source checkout, shell, venv,
network connection or global Python.

The installed app must run every bundled scientific boundary used by the source application:

- Train Dataset Build, CNN Training and Random Forest Training Workers;
- Detect CNN candidate detection and Random Forest refinement Workers;
- verified corpus export and reopen for WAV snippets, concatenated WAV and Raven TSV;
- shared safe quit and the global one-scientific-Run admission rule.

Train's source WAVs remain read-only while its immutable Dataset/Model/Run outputs retain the
existing Collection-owned contract. Detect never writes metadata into a recordings folder: its
versioned Collection, inventory, Run, Result, selection and history metadata stays under Qt's
per-user BioCall Studio application-data root (`train/v1` and `detect/v1`). Detect writes an
immutable export only to the destination explicitly chosen by the user.

## Build and release requirements

1. Build from one clean, reviewed and tagged BioCall Studio commit. Record the Python, PySide6,
   `alp-ui` and `bioacoustics-dl-toolbox` versions, committed upstream SHAs, wheel SHA-256 values,
   scientific lock, fixture revision and supported macOS/architecture matrix. Editable sibling
   checkouts and developer absolute paths are forbidden release inputs.
2. Use a validated native freezer. The default evaluation remains a one-folder `.app` with all Qt
   plugins, fonts, `alp-ui` resources and scientific runtimes bundled. Every Worker must launch the
   frozen app's `--worker` entry, never `/usr/bin/python`, a user venv, a shell or inherited CWD.
3. The bundle identifier and every Finder, Dock, menu and window surface must say **BioCall
   Studio** and use `assets/branding/icons/icon.icns`. Validate native ICNS sizes and record the
   asset digest; reject the former Train-only name and generic Qt/Python icons.
4. Keep writable state outside the sealed bundle using the standard per-user application-data
   directory. Exercise fresh state, existing state, restart, moved/relinked recording folders and
   uninstall. Uninstall must not delete Train Collections, source recordings, Detect exports or
   per-user data unless a separate explicit removal choice names those targets.
5. Sign the `.app` with Developer ID Application and hardened runtime using only justified
   entitlements. Verify with `codesign --verify --deep --strict`, sign the drag-to-Applications
   DMG, notarize, staple and validate a downloaded/quarantined copy with Gatekeeper. Credentials
   remain in the release runner keychain/vault and never enter files or logs.
6. Publish an immutable manifest containing source/dependency/brand digests, installer SHA-256,
   OS build and architecture, native test results, signing/notarization/stapling results, licenses,
   SBOM where practical, known limitations and explicit owner promotion. Retain the prior verified
   installer for rollback.

## Preserved native test IDs

- `IT-E2E-001`: from a clean installed app, launch Studio; create and reopen a real Train Dataset,
  CNN and RF Model; structurally reload both Models; use those Models in Detect CNN→RF; export and
  reopen WAV+TSV; restart/relink; confirm immutable provenance and unchanged inputs.
- `IT-MAC-001`: verify versioned BioCall Studio bundle identity, ICNS, embedded resources,
  signature, hardened runtime, notarization, stapling and Gatekeeper/quarantine launch.
- `IT-MAC-002`: prove bundled Train and Detect Workers launch without system Python, cancel and
  recover without orphans, use per-user writable state, and preserve safe shared quit.
- `IT-MAC-003`: reproduce the candidate from the recorded tag and dependency wheels, validate the
  manifest/digests and withhold promotion when credentials, legal clearance or evidence is absent.
- `IT-MAC-004`: on the installed app, exercise Studio/Train/Detect/Review normal and compact layouts,
  navigation, focus, keyboard HelpHints, copy, tables, plots, empty/error/busy/success states and
  Review session/export behavior. Save actual installed-app screenshots under
  `docs/design/evidence/spec-06-installed/`; offscreen Qt grabs are not native Cocoa evidence.

Installed configuration coverage must include representative basic and advanced CNN/RF fields,
keyboard-accessible HelpHints/Wiki links, saved preset persistence after restart, and exact resolved
settings in exported Models.

## Promotion blockers

Any missing committed toolbox source/wheel, bundled Worker/runtime, source/output checksum,
immutable-result verification, per-user write boundary, clean uninstall result, native screenshot,
signing/notarization evidence, dependency license/security review or owner approval blocks
promotion. An unsigned local build must be labelled `development-only`. Windows remains governed
by spec 07 and cannot be inferred from macOS evidence.
