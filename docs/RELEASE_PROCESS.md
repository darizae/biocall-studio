# Controlled BioCall Studio native releases

**Active November 2026 override:** [series index](specs/release-preparation-2026-11/README.md), [VERSION_CONTROL](specs/release-preparation-2026-11/VERSION_CONTROL.md), [spec 05 local suite](specs/release-preparation-2026-11/05-final-upstream-release-qualification.md), [spec 04 native installers](specs/release-preparation-2026-11/04-installer-gates.md), then [spec 06 release/cleanup](specs/release-preparation-2026-11/06-release-and-post-release-cleanup.md) supersede the older tag-first/full-installed-science requirements below for this alpha. The reviewed Mac+Windows packaging-source PR is merged. First freeze reviewed `main` and run the one **local** Studio ordinary base suite (05); **then** build/install/smoke both native OS installers in parallel (04), using that identical SHA; **only afterward** publish the release and retire completed specs (06). No new screenshot gallery, long-running suite or full retraining. License/signing, data preservation and actual installer SHA-256 remain non-negotiable.


**Status (2026-11-08):** this is the release gate, not a release record. Train, Detect and Review source workflows are implemented on `main`; Studio's final local suite and native installers are **not** qualified. No installer was built,
installed, signed, notarized, uploaded or promoted. All `IT-MAC-*`, `IT-WIN-*` and installed
`IT-E2E-*` checks remain deferred until a separately approved packaging stage executes
[macOS spec 06](specs/06-macos-release-and-installer.md) or
[Windows spec 07](specs/07-windows-release-and-installer.md).

## Candidate chain

1. **Identify.** Require a clean reviewed BioCall Studio release commit and immutable tag. Record
   Python/Qt, `alp-ui` and direct `bioacoustics-dl-toolbox` versions, committed upstream SHAs,
   independently built wheel/lock hashes, fixture revision, current suite-brand asset digests and
   supported OS/architecture. Editable siblings and developer paths are development-only.
2. **Build once natively.** Reproduce from a clean checkout and pinned wheels. Bundle one BioCall
   Studio GUI plus all `--worker` entries used by Train Dataset/CNN/RF and Detect CNN/RF. Bundle
   Qt plugins, fonts, public `alp-ui` resources, scientific runtimes, icons and licenses. Workers
   must not use system Python, shell lookup, user venvs or inherited CWD.
3. **Verify data ownership.** Mutable suite state uses Qt's per-user BioCall Studio data root with
   versioned `train/v1` and `detect/v1` ownership. Detect metadata never enters a source folder.
   Train and Detect inputs remain byte-identical. Immutable Dataset, Model, Result and export
   receipts/digests must reopen; exports are written only to an explicit destination.
4. **Exercise the installed app.** From a clean target: launch Studio; run genuine Train
   Dataset→CNN/RF; structurally reload both Models; retain Train state across workspace switching;
   run Detect scan→CNN→Results→optional RF-derived Result; then open a verified Result in
   Review, use native spectrogram/audio and human labels, Finalize, and publish/reopen the
   Review-owned WAV and/or Raven TSV corpus export. Restart/reopen/relink, test source replacement,
   missing Model, crash, cancel, global Run admission and one confirmed safe quit. Verify source
   hashes and partial-review provenance; historical Detect export readers remain supported.
5. **Verify native UX.** Check the accepted Studio/Detect hierarchy and current Train UI at normal
   and compact sizes, focus/keyboard order, accessible HelpHints, tooltips/copy, plots/tables and
   empty/error/busy/success states. Capture the actual installed application; offscreen grabs are
   supplemental only.
6. **Package and sign.** macOS uses the checked-in suite ICNS, Developer ID, hardened runtime,
   notarization, stapling and Gatekeeper/quarantine checks. Windows uses the suite ICO, maintained
   installer/uninstaller, native path/DPI/accessibility coverage and required executable/installer
   signatures. Every shell surface says **BioCall Studio**.
7. **Clean install and uninstall.** Validate fresh install, upgrade and removal. Uninstall removes
   app binaries and shortcuts but preserves recordings, Train Collections, Detect exports and
   per-user data unless a separate explicit removal option names and confirms those targets.
8. **Promote explicitly.** Require green native test IDs, installer and dependency SHA-256 values,
   resolved BioCall Studio application license (currently **not declared**), toolbox GPL-3.0-only and Qt/PySide6 redistribution compliance, security review, brand/name clearance, SBOM where practical, known
   limitations and owner signoff. Upload only the tested immutable digest. Never auto-promote.
9. **Rollback.** Retain the previous verified installer and manifest. Never rewrite a release tag
   or silently replace binaries; test migration refusal/compatibility before distribution.

## Release record schema

Each candidate report must record:

- tag and commit, clean-tree proof, build command and native runner identity;
- Python/Qt/scientific dependency lock, upstream SHAs and wheel SHA-256 values;
- suite ICNS/ICO digest, OS build/architecture/DPI/privileges;
- `.app`/`.dmg` or installed files/`.exe` SHA-256 and reproducibility comparison;
- signing, notarization/stapling or Windows signature verification results;
- exact `IT-E2E-*`, `IT-MAC-*` or `IT-WIN-*` commands and pass/fail/blocked results;
- installed Train→Detect scientific IDs, timestamps, source/result/export digests and unchanged
  source checksums;
- per-user path and clean uninstall evidence, native UX screenshots and reviewed deviations;
- privacy scan, licenses/security/SBOM, known limitations and explicit owner signoff.

A CI artifact, documentation checklist or source-tree test is never installed-app evidence.
Missing credentials, native runners, legal clearance or any required test is recorded as blocked;
it is not converted into a passing or public-release claim.
