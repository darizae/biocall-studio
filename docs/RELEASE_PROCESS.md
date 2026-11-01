# Controlled BioCall Studio native releases

**Status after ST-11:** this is the release gate, not a release record. No installer was built,
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
   run Detect scan→CNN→Results→RF→WAV+Raven export; restart/reopen/relink; exercise source
   replacement, missing Model, crash, cancel, global Run admission and one confirmed safe quit.
   Review remains a placeholder.
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
   license/security review, brand/name redistribution clearance, SBOM where practical, known
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
