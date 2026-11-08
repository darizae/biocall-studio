# Spec 04A — reviewed native packaging source; no installer release

**Authority:** [04 installer gates](../docs/specs/release-preparation-2026-11/04-installer-gates.md) and
[VERSION_CONTROL](../docs/specs/release-preparation-2026-11/VERSION_CONTROL.md).
This implementation PR must merge to Studio `main` before choosing
`STUDIO_RELEASE_SHA`. Do not build the final OS binaries from this branch.
Do not change Studio source after freeze, run the complete suite, tag or release in spec 04A.

## Shared wheel + freezer contract

- Python **3.12**, native **macOS** or Windows **x86-64**. Install from a *clean frozen*
  `main` checkout in a fresh virtual environment. Use
  [build requirements](requirements-build.txt), the single Studio scientific
  dependency manifest in [pyproject.toml](../pyproject.toml) and the
  [native constraints baseline](constraints-native.txt). The last contains
  versions **observed in B3 Linux**, not cross-platform qualification. Capture
  the complete `pip freeze` and selected PyInstaller/native binary inventories
  in each real OS lane; do not claim this constraints file is a hash-locked
  transitive wheelhouse.
- The upstream wheels must be the **published release assets** referenced in
  `[tool.biocall-studio.science]`: `alp-ui==0.1.0a1` tagged commit
  `41bac72971b96d352da752cc0ff140afe3ac312a`, wheel SHA-256
  `20590366d06591837c2567df1191b472b9db494e5440ce3a3fadfbf1b8d53d6c`;
  `bioacoustics-dl-toolbox[rf]==0.3.0` tagged commit
  `7027bd84cc5a44a27bf201332af540f090c38365`, wheel SHA-256
  `c0f7679cbf788c2900eff26b8db719941a513fc96b5f28348e2838c8df595b28`.
  `verify_inputs.py` rejects altered wheels and editable/source-tree imports.
- Shared [entrypoint](shared/entrypoint.py) preserves
  `biocall_studio.cli.main` and multiprocessing freeze support. The
  [freezer manifest](shared/freezer.py) includes the five private
  Train Dataset/CNN/RF and Detect CNN/RF entrypoints, Studio/Train/Detect/Review,
  icon PNG/ICNS/ICO, JSON settings resource, published `alp-ui` fonts/OFL
  text, upstream third-party metadata/licenses and scientific modules. Qt,
  multimedia and Torch shared libraries still require validation in the
  actual OS bundle. No editable `../alp-ui` or `../bioacoustics-dl-toolbox`.
- Source workers launch `python -m biocall_studio --worker`. A frozen Mac app
  re-launches its bundled executable. Windows uses two EXEs from **one**
  PyInstaller Analysis / dependency folder: windowed
  `BioCall Studio.exe` for the GUI and console
  `BioCall Studio Worker.exe` for QProcess JSON stdout/stderr.

## Native lanes — after A's merge, source freeze and the local spec 05 suite

| Genuine runner | Build and artifact | Installed preflight |
|---|---|---|
| macOS | `STUDIO_RELEASE_SHA=<merged-main-sha> bash packaging/macos/build.sh` creates an unsigned development-only `.app` and `.dmg` using checked-in ICNS; developer must separately perform Developer ID hardened signing, notarization, stapling and Gatekeeper checks | Copy app from DMG into `/Applications` (outside source), then `bash packaging/macos/smoke.sh` |
| Windows x86-64 | Set `$env:STUDIO_RELEASE_SHA` to frozen main SHA; `& packaging/windows/build.ps1` creates onedir EXEs and Inno Setup 6 installer, both bearing ICO; separately Authenticode-sign under the approved distribution policy | Install under Program Files, then `& packaging/windows/smoke.ps1` |

These build scripts perform an actual compiled bundle and record actual asset hashes
only when invoked on their native OS; **neither is executed by spec 04A CI**.
The cross-platform `packaging/shared/native_smoke.py` checks installed CLI
version and branding, each **real** bundled worker's malformed-input/import
failure path without publishing data, and GUI startup with an isolated
writable data root. It is **not** a proof of successful scientific workers,
model loading, WAV/Raven export, safe shared quit or user-data-preserving
uninstall. Each native lane must additionally do a small **valid**
worker/load/export/restart/uninstall test on the installed app, record OS,
architecture, binary SHA-256, source-input hashes, per-user preservation
and exit/status evidence. Never infer Windows qualification from a Mac or Linux
build, or report a source build as an installed artifact.

## License, signatures and release block

The application has **no declared Studio license**. The toolbox is
**GPL-3.0-only**, alp-ui **MIT**, fonts **OFL**, Qt/PySide6 requires
redistribution and LGPL/GPL route review. The selected upstream tagged
LICENSE/NOTICE copies live under `packaging/legal/`; published wheel
dist-info licenses and font licenses are bundled too. Even if an unsigned
installer is technically created, mark it **development-only**. No public
signing, notarization, release, tag or distribution until all legal/licensing,
source availability, Qt replacement rights where applicable and owner gates
are explicitly cleared.

Installer/uninstaller owns **only installed binaries and shortcuts**, never
application data, Train Collections, source WAVs, Review sessions, Detect
Results or user-selected exports. Mac drag-to-Applications and Windows Inno
remove app binaries; neither declares deletion of user data. Actual clean
uninstall and data preservation remain native checks.

Prior [macOS 06](../docs/specs/06-macos-release-and-installer.md),
[Windows 07](../docs/specs/07-windows-release-and-installer.md) and
[release process](../docs/RELEASE_PROCESS.md) describe expanded older
qualification, including repeated complete science retraining, UI galleries,
soaks and hard performance runs. The approved November 2026 **spec 04**
reduces this stage to small native smoke and excludes new screenshots or
full retraining, without relaxing real install, worker/runtime, data ownership,
licenses, signatures or artifact hashes. The **one full Studio source suite runs first and locally under spec 05**.
Only then run both genuine native installer lanes (spec 04). The **tag,
publication and post-release Markdown retirement belong to spec 06**.
A native source defect triggers a new reviewed fix PR, a new frozen SHA,
a new **local spec 05 suite**, and **both** OS builds repeated.
