# BioCall Studio — final downstream integration and installer-gated release specs

**Planning series, not an implementation/release claim.** Inspected baseline `main@2b2137d8db8bb504a57d835aff46a65a73eaccf2`, `biocall-studio==0.1.0a0`; upstream declarations at baseline are `alp-ui==0.1.0a0` and `bioacoustics-dl-toolbox[rf]==0.2.0`. Check current real SHAs and latest **published** upstream versions before executing. Do not confuse new spec branches with released libraries.

Ordered within **this** repository (cross-repository dependency graph below):
1. [01 — Adopt released upstream spectrogram API](01-upstream-ownership.md). Starts only **after** the toolbox's actual release and any required Alp UI release.
2. [02 — Human-facing branded README and Markdown diet](02-human-readme-and-docs.md). Do after 01 for accurate live examples; use authentic release-real-data captures and retain concise agents/vision/architecture.
3. [03 — Source/package candidate, focused checks](03-base-suite-and-release-candidate.md). Prepares immutable pins, docs, release metadata and *scoped* regressions; not the final Studio suite.
4. [04 — Prepare two native installers](04-installer-gates.md). macOS and Windows implementation/installer smoke can execute in parallel on real respective runners, against the **same candidate**; no tag/promotion yet.
5. [05 — FINAL integrated base suite and promotion](05-final-upstream-release-qualification.md). **Only this last spec executes the full BioCall Studio ordinary suite, against actual latest approved released `alp-ui` and `bioacoustics-dl-toolbox` wheels.** Verify both installers refer to that candidate; tag/release only if every gate passes.

Parallelism, mildly conservative: toolbox [01→02→03](https://github.com/darizae/bioacoustics-dl-toolbox/tree/spec/2026-11-release-preparation/docs/specs/2026-11-release-preparation) **in parallel with** [alp-ui 01→02→03](https://github.com/darizae/alp-ui/tree/spec/2026-11-release-preparation/docs/project/specs/2026-11-release-preparation). Wait for **both** released library artifacts before Studio 01. Within Studio, 01→02→03 are sequential. Two native OS lanes of Studio 04 can run in parallel, then Studio 05 is last across **all three repositories**.

**Explicit exclusions:** no new generic Cocoa capture requirement (real captures exist), no mandatory physical audio-device proof, soak, ≥600-second/long-run test, 50k candidate rerun or large real-data performance qualification. Existing actual screenshots remain README proof, not installed-app proof. App/Qt native installers still require their own small installation/worker/launch smoke on their OS.

**Execution:** GitHub API for Git/code/Markdown/release records; ChatGPT VM for static checks, package wheels and bounded tests; actual native macOS/Windows workers for installer/freezing/signing/install/uninstall checks. No release tag or installer claimed by merely writing these specs.

These owner-directed GitHub API spec commits supersede historical no-push guidance **only for planning branches**; implementation merges and releases remain separately gated. Preserve genuine science, safe immutable sources and the minimum agent routing/architecture/vision after documentation reduction.
