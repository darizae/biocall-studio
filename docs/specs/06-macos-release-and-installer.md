# 06 — Controlled macOS packaging, installable DMG and release pipeline

## User-visible outcome

A non-developer obtains a **versioned `.dmg`** and installs a usable `.app` to `/Applications` on a clean supported macOS system. It launches the Qt Trainer, uses the `alp-ui` native FolderPicker/help/plots, reads a real Collection, builds immutable Dataset and trains/reopens CNN/RF through bundled Worker with no source checkout, venv, shell, network or globally installed Python. Input WAV hashes are unchanged. Public distribution requires valid signing/notarization/stapling.

## Build/release implementation requirements

1. Design deterministic release metadata: tag/commit and clean tree, supported macOS/architecture matrix (Apple Silicon first, Intel policy documented), pinned Python/Qt + scientific binary wheels, `../alp-ui` wheel SHA, `../alpaca-pipelines` source SHA/adapter, Qt/fonts/icons/licenses and stable bundle ID. Use secure dependency lock/hashes. No hardcoded developer absolute paths or embedded HPC references.
2. Configure and test a real native freezer (evaluate PyInstaller one-folder `.app` as default, record actual compatibility with `PySide6-Essentials`, `alp-ui` resources and CNN/RF runtime). Worker launches the bundled entry via `--worker`, not the machine interpreter, inherited CWD or shell. Preserve writable app data outside signed bundle and portable per-Collection `.alpaca/` publication.
3. Reproducible candidate workflow: PR static/unit and appropriate macOS integrations; versioned tag/explicit dispatch builds release candidate; sign `.app` with Developer ID Application, hardened runtime with minimum justified entitlements, `codesign --verify --deep --strict`, package drag-to-Applications DMG, sign/notarize as applicable, staple and validate via `spctl`/Gatekeeper from downloaded/quarantined DMG. Never store Apple credentials or signing secrets in files/ZIP/log output.
4. Test clean-target install and first-run GUI plus Worker. On installed `.app`, execute `IT-E2E-001`, `IT-MAC-001`...`IT-MAC-004` on supported native Mac machines, using locally generated real WAV fixtures with correct source provenance. Exercise folder cancel, HelpHint keyboard, Plot values/text alternatives, Run cancel/restart, files with spaces/Unicode and artifact relinking. Do not consider dev environment launch packaged proof.
5. Publish release manifest with Git SHA, dependency/source digests, installer SHA-256, OS/arch, native test matrix, code-signing/notarization result, legal notices, SBOM where practical and explicit owner promotion. Retain previous released installer for rollback. No automated updates or unsigned public release.

## Failures and gates

- Missing credentials / macOS runner / proprietary distribution approvals => mark **blocked**, no invented `.dmg` or “release ready” status. Unsigned local QA builds must say `development-only`.
- Broken bundled fonts/icons/theme, `FolderPicker`, HelpHint, Plot, `QProcess`, scientific imports/checkpoints, quarantine first run, or read/write state inside sealed bundle => **fail**.
- Windows remains separate spec 07; it is not silently covered here.

## Blocking installed-app UX parity

**`IT-MAC-004`:** On a clean supported native Mac, open the **installed** `.app` from the `.dmg` and reproduce the user-visible route/state matrix, including `FolderPicker`, HelpHint, tables, `Plot`, fonts, icons, empty/error/busy/finished views, and narrow layout. Capture representative installed-app screenshots in `docs/design/evidence/spec-06-installed/`, compare to prototype and the pinned `alp-ui` Showcase, and record the six dimensions in [Prototype acceptance](../design/PROTOTYPE_ACCEPTANCE.md). Any missing resource, altered hierarchy or unapproved UX regression **fails installer promotion** even if signing succeeded.

## Tests / exit

`IT-E2E-001`, `IT-MAC-001`, `IT-MAC-002`, `IT-MAC-003`, `IT-MAC-004` and `TD-OS/UI/RUN/TRAIN`. All supported macOS architectures pass installed-app E2E and Gatekeeper checks; a tested, checksummed, notarized `.dmg` is promoted through explicit release approval. Update [release record](../RELEASE_PROCESS.md) with actual evidence and command logs.
