# Controlled BioCall Studio native releases

**Active November 2026 release record:** the shipped `v0.1.0a1` unsigned alpha provenance is in [the release record below](#v010a1-unsigned-alpha-release-record-2026-11-08); it supersedes the older tag-first/full-installed-science requirements below for this alpha. The reviewed Mac+Windows packaging-source PR is merged; both native installers were built, smoke-tested and published as an owner-authorized unsigned pre-release. License/signing, data preservation and actual installer SHA-256 remain non-negotiable.


**Status (2026-11-08):** the owner-authorized **unsigned alpha `v0.1.0a1` pre-release is published**
(see the release record below). Train, Detect and Review source workflows are implemented on
`main`; the full interactive Windows GUI and installed Review GUI export checks remain
deferred/unverified — recorded as **known alpha limitations**, not passing claims. All `IT-MAC-*`,
`IT-WIN-*` and installed `IT-E2E-*` scope beyond the recorded native smoke checks remains
deferred until a separately approved packaging stage executes
[macOS spec 06](specs/06-macos-release-and-installer.md) or
[Windows spec 07](specs/07-windows-release-and-installer.md).

## v0.1.0a1 unsigned alpha release record (2026-11-08)

- **GitHub Release (pre-release, unsigned alpha):**
  https://github.com/darizae/biocall-studio/releases/tag/v0.1.0a1 — title
  *BioCall Studio v0.1.0a1 — Unsigned Alpha (Testing)*.
- **Annotated tag** `v0.1.0a1` → **exact tested binary-source commit**
  `8354089cc7f0878e3dd594ca3620e90c4f16b6f8` (not the later documentation commit).
- **GPL/documentation commit (later than the binaries):** GPLv3 root `LICENSE` merged via
  [PR #12](https://github.com/darizae/biocall-studio/pull/12); owner unsigned-alpha override via
  [PR #13](https://github.com/darizae/biocall-studio/pull/13); license/docs-only `main` advanced to
  `6cb43c1` before tagging and to `1c719d1` (README downloads, PR #14) after. These edits do not
  change the compiled binaries; the tag's auto-generated source archive predates the root LICENSE.
- **Installers (verified from bytes, unchanged):**
  `BioCall-Studio-0.1.0a1-windows-x86_64.exe` SHA-256
  `d91a7469117c208ee3c5807e08c2b05fd7c3ce26a9ee3043917a211a403f85bb`;
  `BioCall-Studio-0.1.0a1-macos.dmg` SHA-256
  `751bea1750710e423fb7a83752c9d27d7ddbd5db65503ae98d9707b60bb4347f`. Attached also:
  `biocall-studio-0.1.0a1-src.zip` (corresponding source at the binary SHA,
  `751a39505fb7d0d4746be4116d363c1af9148c8a2434e1e1c284df35c841f161`), `SHA256SUMS`,
  `SOURCE-AND-LICENSE.md`, full GPLv3, upstream license/notice texts and font OFL files.
- **Published upstream wheels (exact pins frozen in the build commit):** alp-ui `0.1.0a1`
  (`20590366d06591837c2567df1191b472b9db494e5440ce3a3fadfbf1b8d53d6c`, tag target
  `41bac72971b96d352da752cc0ff140afe3ac312a`); bioacoustics-dl-toolbox `0.3.0`
  (`c0f7679cbf788c2900eff26b8db719941a513fc96b5f28348e2838c8df595b28`, tag target
  `7027bd84cc5a44a27bf201332af540f090c38365`). Both upstream Releases verified accessible.
- **Local Studio suite receipt (original context preserved):** full suite at the **same exact SHA**
  in the repair worktree before the final merge — **302 passed, 1 skipped, 5 deselected**, with
  Ruff and test-ID audits passing. Accepted by the owner as the actual same-commit receipt; not
  relabeled as a post-merge run.
- **Native macOS evidence:** [Prompt 12 execution report,
  PR #9 comment](https://github.com/darizae/biocall-studio/pull/9#issuecomment-6726202566) —
  installed .app, real workers, workspaces, compatible export, restart, safe user-data and
  uninstall preservation. Ad-hoc app signature, no Developer ID, no notarization; installed Review
  GUI export unverified.
- **Native Windows evidence:** [Actions run
  #42510754053](https://github.com/darizae/biocall-studio/actions/runs/42510754053) — real
  `windows-2025` runner, Python 3.12 x64, PyInstaller + Inno Setup, installed positive Dataset
  worker/load, restart, silent uninstall with external marker. Unsigned (Authenticode
  `NotSigned`); interactive installer dialogs and Review GUI export not independently verified.
- **Signing and GUI limitations (known alpha limitations, not blockers):** installers are unsigned
  and unnotarized; macOS Gatekeeper and Windows SmartScreen may warn or block. Not claimed:
  Apple notarization, Developer ID signing, Windows code signing, full interactive Windows GUI
  verification, installed Review GUI export.
- **Licensing/source availability:** Studio is **GPL-3.0-only**; corresponding source attached at
  the exact binary SHA (the tag archive lacks the later root LICENSE). Third-party obligations
  preserved: toolbox GPL-3.0-only + ANIMAL-SPOT attribution (upstream rev
  `fee8b4ba789947a40b89c03eb6fc61e351115e90`), alp-ui MIT, Qt/PySide6 LGPLv3 (dynamically linked,
  replaceable), DM Sans/JetBrains Mono OFL 1.1. Repository made **public** (owner-authorized after
  a clean tree-and-history credentials/privacy audit) so Release assets are anonymously
  downloadable.
- **Process deviations (owner-accepted):** direct push of the tag/release outside a reviewed PR,
  and the same-SHA repair-worktree execution of the local suite. No history rewrite, no tag
  relocation, no installer rebuild.

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
