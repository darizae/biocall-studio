# Controlled native releases — planned gates, not current outputs

**Owner:** specs [06 macOS](specs/06-macos-release-and-installer.md) and [07 Windows](specs/07-windows-release-and-installer.md). These are acceptance **plans**; the current ZIP is source/scaffold, **not** an installed app, `.dmg`, notarized Mac download, `.exe`, or completed release. Never mark a gate passed from a documentation checklist.

## Release candidate chain

1. **Identify** exact Git tag (`vX.Y.Z`), release commit, Python version, `alp-ui` sibling SHA + built wheel digest, alpaca-pipelines source SHA/adapter behavior, science dependency lock/wheel hashes, fixture revisions and minimum supported OS/CPU arch. Reject dirty tree, missing pin or unsupported architecture. No developer absolute paths in release manifest.
2. **Build once from clean checkout** and reproducible pinned dependencies in an isolated native job. Use a frozen bundler selected/verified in spec 06; prefer a one-folder `.app` with Worker executable entry in the same bundle, no `/usr/bin/python` or user's venv. Capture build tool and dependency metadata, bundle licenses/resources.
3. **Exercise installed output**, not only editable checkout: native folder chooser, app resource/theme/help/plot, embedded Worker launch/cancel/recovery, synthetic real Collection → Dataset → actual CNN and RF → reopen, untouched input hashes, local logs/config permissions. Standard smoke fixture is `tests/data/example_collection/` if its content supports the case; generate larger fit-for-training data in a temporary directory as needed.
4. **Mac**: create versioned drag-and-drop `.dmg` containing signed `.app` and Applications link; validate `.app` bundle identifier, icon, Apple Silicon and declared Intel policy, codesign verification, hardened runtime, notarization and stapling for externally distributable release. Apple signing credentials/notary secrets stay in secure release runner keychain/vault, not repo, ZIP or printed logs. Where credentials unavailable emit an explicitly **development-only** unsigned artifact and keep public-release gate blocked.
5. **Windows** (separate native qualification): package actual Windows app/Worker/resources; produce versioned `.exe` installer with appropriate uninstaller; native path/permission tests, clean Windows VM install/smoke/uninstall and security/signing evidence. No claim of Windows readiness on Mac.
6. **Promote explicitly**: require green tagged source/static/unit/native `IT-*`, full installer smoke, reviewed UI parity/screenshots, SPDX/license and dependency security review, SHA-256 checksums, release notes and operator approval. Upload only tested digests from candidate job (immutable artifact). No self-updater or auto-release in MVP.
7. **Rollback**: retain previous verified installer/digest; never rewrite a release tag or silently replace binaries. Migration/manifest version refusal and compatibility behavior must be tested before distribution. Document known limitations without claiming compatibility.

## Release record schema

A release report must show: tag/commit; dependency lock & sibling SHAs; OS+arch; generated `.app`/`.dmg` or `.exe` with SHA-256; code signing and notarization/stapling outcome; `IT-E2E`, `IT-MAC` or `IT-WIN` exact cases with commands/log locations and actual pass/fail; UI parity review; private data/payload scan; owner signoff. CI artifact success does **not** equal installed science success.

## First-session boundary

Spec 01 should provide packaging-aware entry points, resource path rules and test seams; **do not** implement the release pipeline in session one. Spec 06 implements Mac release controls after real Trainer science passes. Spec 07 is intentionally later and does not block development of Mac-only releases, but prevents advertising Windows installers until native qualification.
