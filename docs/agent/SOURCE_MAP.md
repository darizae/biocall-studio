# Source map — specific external reference and evidence routes

**This is a targeted index, not a mandate to read whole external repositories.** Find the active spec in [ROUTING](ROUTING.md); browse only relevant source + tests, record discovered paths and commit. Never infer interfaces from archive paths.

| Source | Resolve and verify | Use when | Rules |
|---|---|---|---|
| Native UI library | sibling `../alp-ui`; public `src/alp_ui/components/__init__.py`, `docs/components.md`; style example `gallery/showcase.py`, `docs/images/showcase.png` | spec 01 UI; 02/03/04 controls; 05 Plot; 06/07 bundle | Verify installed-wheel API and actual SHA; use `FolderPicker`, `HelpHint`, `Plot` from public exports, not private monkeypatching. [Contract](../design/ALP_UI_CONSUMER_CONTRACT.md) |
| Prototype | checked-in `docs/design/prototypes/training-first/index.html`, `app.js`, CSS and all previews | UI changes across 01–05, native packaged smoke | Follow screen/transition parity [matrix](../design/UX_PARITY_MATRIX.md); mock scientific JS outputs **not** reliable artifacts. |
| Scientific reference | canonical sibling checkout `../alpaca-pipelines` (lowercase, hyphenated; exact on case-sensitive systems) | 03 negative windows/audio/splits, 05 CNN + RF; 06 scientific packaging | Inspect local source/tree/test modules by `rg` for concepts before selecting an import. Pin `git rev-parse HEAD`, Python deps and actual adapted file paths. No wholesale pipeline app schema adoption. If unavailable, state blocker; don't invent module paths. |
| Permissioned HPC scientific archive | untracked `docs/priv/hpc-source-access/SKILL.md`, bounded helper and private site reference | Only when a test discriminant cannot be represented with generated fixture and approved archive data is needed | Use read-only scoped catalog/stat/exact-file pull into private staging *outside* repo. Scrub/approve before Git LFS. Tests/CI **never** access HPC. |
| Indexed integration-test practice | repo-local `docs/agent/indexed-integration-tests/SKILL.md` plus exact `IT-*`/`TD-*` | Any real boundary integration test | Expected real effects, negative effects, stable IDs in test docstrings; audit script does not establish coverage. |

## Scientific inspections (make paths concrete during implementing spec)

- **Spec 03:** locate source WAV/frame/channel conversion, protected windows or negative sampling where genuinely reusable, dataset and split serialization tests. Compare source-time units and our `target`/`noise` contract; use adapter or domain implementation only for verified overlap.
- **Spec 05 CNN:** locate architecture, preprocessing, epochs/training loop, persistence/load and scientific tests; define checkpoints and input tensor/label/split semantics with real run proof.
- **Spec 05 RF:** locate features and versioned feature order, model serialization/load, classifier probabilities/threshold and actual validation metrics; enforce schema/order rather than assuming checkpoint compatibility.
- **Spec 06/07:** document pinned scientific runtimes, CPU support and bundled worker imports; do not rely on source tree from installed app.

When actual paths/versions are confirmed, write a concise source-inspection record in the implementing PR; do not hardcode hypothetical references into core docs. HPC archive is optional *source evidence*, never a live test data dependency.

**Transfer note:** `tests/data/` payloads may be absent from the ZIP by design; look for registered Git LFS fixtures in the actual checkout or generate deterministic temporary WAVs. This has no bearing on the existence or path spelling of `../alpaca-pipelines`.
