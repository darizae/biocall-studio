# 07 — Controlled Windows installer and native qualification (later phase)

**Scoped references:** [release process](../RELEASE_PROCESS.md); [native UX gate](../design/PROTOTYPE_ACCEPTANCE.md) (Windows row); `IT-WIN-*` in [integration index](../INTEGRATION_TEST_BEHAVIORS.md); [path/OS fixtures](../INTEGRATION_TEST_DATA.md) as needed.

## User-visible outcome

On a clean supported Windows x86-64 machine, the user installs a **versioned `.exe` installer**, launches native PySide6/`alp-ui` Trainer, selects a Collection, creates a Dataset, trains/reopens CNN+RF with bundled Worker **and verifies both published Models structurally reload**, and uninstalls cleanly. No Python/venv or sibling checkout required. Publication is explicitly **deferred** until native gates pass.

## Implementation

1. In actual Windows x86-64 CI/VM and one clean-install target, freeze Windows binaries (GUI/Worker, Qt plugins/fonts/icons and model runtimes) using validated packaging choice; produce reproducible installer via a maintained explicit tool (e.g., Inno Setup, review selected license and reproducible scripting). No shell or global interpreter fallback.
2. Test drive-letter, Unicode/NFC/case collisions, reserved names, relative containment, UNC where supported, reparse/junction escape, long paths, read-only and file-sharing/locked replacement. Install into Program Files as standard app but save application config/logs in user-writable standard locations, Collection `.alpaca/` next to selected data subject to permission checks.
3. Native UI: FolderPicker dialog and cancellation, keyboard HelpHint, plots with numeric accessible alternatives, 100%/150% DPI, scroll/focus, DataTable and no missing resources; perform Windows-specific accessibility review rather than citing macOS screenshots.
4. Run installed app and real Worker cancellation/restart, Dataset and both Models **plus both trusted new-process Model export/reload checks** under the [Model export contract](../science/MODEL_EXPORT_CONTRACT.md). Confirm the **direct toolbox scientific training runtime** and all other dependencies are bundled; any pertinent toolbox defect encountered during Windows qualification may be fixed/tested/committed upstream following [the shared workflow](../agent/UPSTREAM_TOOLBOX_WORKFLOW.md), then reinstalled and re-tested on Windows. Build the release from a pinned toolbox revision/wheel, **never** a local editable path or Trainer-only scientific patch; no sibling checkout is needed. No inference imports or scoring are required. Validate clean install/upgrades/uninstall, no deleted user Collection, installer permissions and dependency licensing/security.
5. Sign installer and executables if distribution policy requires, verify digest, record dependency/source SHAs, release manifest, Windows-specific tests/logs and approval; if signing/build infrastructure absent, report blocker and withhold public distribution. No automatic promotion from macOS build. Record actual toolbox commit SHA and Windows-compatible wheel identity; if the upstream fix is uncommitted, unavailable or unverified in the shipped environment, block release.

## Blocking installed-app UX parity

**`IT-WIN-005`:** Run the actual installed app on supported native Windows. Check all navigation/action patterns, `FolderPicker`, HelpHint, plots and numeric alternatives, empty/invalid/progress/done states and 100%/150% DPI + narrow width against the prototype and current pinned `alp-ui` Showcase. Save `docs/design/evidence/spec-07-installed/` screenshots plus keyboard/DPI report and use the [Prototype acceptance](../design/PROTOTYPE_ACCEPTANCE.md) review. Explicitly document native-platform differences and seek owner acceptance; a changed main layout/CTA or missing screen **blocks** installer release even if the package launches.

## Tests / exit

`IT-WIN-001`…`IT-WIN-005`, `TD-OS/UI/PATH/RUN/TRAIN`; capture native run IDs, installer hash, OS build/arch/DPI/privileges, signing outcome. At least one clean Windows installed-app run produces real Dataset and both Model formats and leaves input WAVs byte-identical. This spec follows completed Mac release as the next numbered vertical unless the owner changes platform priority.

**Installed config/preset acceptance:** include a real installed-app smoke verifying advanced CNN/RF controls, per-field `HelpHint`/Wiki links and saved configuration persistence/compatibility across app restarts, without access to `../TRAINING_REFERENCE` or sibling sources. See [configuration catalog](../science/TRAINING_CONFIGURATION_CATALOG.md), [presets](../science/TRAINING_PRESETS.md), existing native release UX test IDs. No prediction functionality.
