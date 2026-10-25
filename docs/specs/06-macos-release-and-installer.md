# 06 — Controlled macOS packaging, installable DMG and release pipeline

**Scoped references:** [release process](../RELEASE_PROCESS.md); [packaged Worker boundary](../ARCHITECTURE.md) §4; [native UX gate](../design/PROTOTYPE_ACCEPTANCE.md) (installed-app row); `IT-MAC-*` / `IT-E2E-*` in [integration index](../INTEGRATION_TEST_BEHAVIORS.md). Inspect [source map](../agent/SOURCE_MAP.md) only for packaging dependencies.

## User-visible outcome

A non-developer obtains a **versioned `.dmg`** and installs a usable `.app` to `/Applications` on a clean supported macOS system. It launches the Qt Trainer, uses the `alp-ui` native FolderPicker/help/plots, reads a real Collection, builds immutable Dataset and trains/reopens CNN/RF through bundled Worker **and structurally reloads each complete exported Model** with no source checkout, venv, shell, network or globally installed Python. Input WAV hashes are unchanged. Public distribution requires valid signing/notarization/stapling.

## Build/release implementation requirements

1. Design deterministic release metadata: tag/commit and clean tree, supported macOS/architecture matrix (Apple Silicon first, Intel policy documented), pinned Python/Qt + scientific binary wheels, `../alp-ui` wheel SHA, `../alpaca-pipelines` reference source SHA/adapter, **direct `../bioacoustics-dl-toolbox` package/SHA and built wheel digest**, Qt/fonts/icons/licenses and stable bundle ID. Use secure dependency lock/hashes. **If packaging exposes a toolbox defect or missing reusable capability, the agent may fix/test/commit `../bioacoustics-dl-toolbox` upstream and reinstall it in the Trainer `.venv` under [the upstream workflow](../agent/UPSTREAM_TOOLBOX_WORKFLOW.md); never hide the issue with a Trainer-only patched scientific copy.** Build an independently reproducible wheel from the identified **committed** toolbox revision; an editable checkout is not a release dependency. No hardcoded developer absolute paths or embedded HPC references.
2. Configure and test a real native freezer (evaluate PyInstaller one-folder `.app` as default, record actual compatibility with `PySide6-Essentials`, `alp-ui` resources and CNN/RF runtime from the pinned **direct toolbox** and RF stack). Worker launches the bundled entry via `--worker`, not the machine interpreter, inherited CWD or shell. Preserve writable app data outside signed bundle and portable per-Collection `.alpaca/` publication.
3. Reproducible candidate workflow: PR static/unit and appropriate macOS integrations; versioned tag/explicit dispatch builds release candidate; sign `.app` with Developer ID Application, hardened runtime with minimum justified entitlements, `codesign --verify --deep --strict`, package drag-to-Applications DMG, sign/notarize as applicable, staple and validate via `spctl`/Gatekeeper from downloaded/quarantined DMG. Never store Apple credentials or signing secrets in files/ZIP/log output.
4. Test clean-target install and first-run GUI plus Worker. On installed `.app`, execute `IT-E2E-001`, `IT-MAC-001`...`IT-MAC-004` **and `IT-TRAIN-008` / `IT-TRAIN-009` structural Model export/reload smoke cases** on supported native Mac machines, using locally generated real WAV fixtures with correct source provenance. Exercise folder cancel, HelpHint keyboard, Plot values/text alternatives, Run cancel/restart, files with spaces/Unicode and artifact relinking. Do not consider dev environment launch packaged proof.
5. Publish release manifest with Git SHA, dependency/source digests, installer SHA-256, OS/arch, native test matrix, code-signing/notarization result, legal notices, SBOM where practical and explicit owner promotion. Retain previous released installer for rollback. No automated updates or unsigned public release.

## Failures and gates

- Missing committed/verified toolbox source revision, built wheel or matching installed scientific runtime => **block promotion**; a green editable-checkout test cannot substitute for the shipped wheel.
- Missing credentials / macOS runner / proprietary distribution approvals => mark **blocked**, no invented `.dmg` or “release ready” status. Unsigned local QA builds must say `development-only`.
- Broken bundled fonts/icons/theme, `FolderPicker`, HelpHint, Plot, `QProcess`, scientific imports/checkpoints/**structural Model export/reload for both families**, quarantine first run, or read/write state inside sealed bundle => **fail**.
- Windows remains separate spec 07; it is not silently covered here.

## Blocking installed-app UX parity

**`IT-MAC-004`:** On a clean supported native Mac, open the **installed** `.app` from the `.dmg` and reproduce the user-visible route/state matrix, including `FolderPicker`, HelpHint, tables, `Plot`, fonts, icons, empty/error/busy/finished views, and narrow layout. Capture representative installed-app screenshots in `docs/design/evidence/spec-06-installed/`, compare to prototype and the pinned `alp-ui` Showcase, and record the six dimensions in [Prototype acceptance](../design/PROTOTYPE_ACCEPTANCE.md). Any missing resource, altered hierarchy or unapproved UX regression **fails installer promotion** even if signing succeeded.

## Tests / exit

`IT-E2E-001`, `IT-MAC-001`, `IT-MAC-002`, `IT-MAC-003`, `IT-MAC-004` and `TD-OS/UI/RUN/TRAIN`. All supported macOS architectures pass installed-app E2E and Gatekeeper checks; a tested, checksummed, notarized `.dmg` is promoted through explicit release approval. Update [release record](../RELEASE_PROCESS.md) with actual evidence and command logs.

**Installed config/preset acceptance:** include a real installed-app smoke verifying advanced CNN/RF controls, per-field `HelpHint`/Wiki links and saved configuration persistence/compatibility across app restarts, without access to `../TRAINING_REFERENCE` or sibling sources. See [configuration catalog](../science/TRAINING_CONFIGURATION_CATALOG.md), [presets](../science/TRAINING_PRESETS.md), existing native release UX test IDs. No prediction functionality.
