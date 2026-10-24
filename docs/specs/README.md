# Specs — indexed task router (7 sequential verticals)

**Mandatory UI acceptance:** [Prototype fidelity gate](../design/PROTOTYPE_ACCEPTANCE.md) applies to every spec that changes visible UI (including packaged installers). A missing screen/state, rearranged primary action, wrong navigation, unlabeled visual deviation or absent native screenshot evidence blocks that spec; using `alp-ui` alone is not proof of parity. Read only the active spec’s screen rows.

**Current next agent session = [Spec 01 closeout](SPEC_01_CLOSEOUT.md), no Spec 02 work until accepted.** On an untouched repository the first task is [Spec 01](01-shell-and-test-foundation.md). If unsure which reference to read, use [`docs/agent/ROUTING.md`](../agent/ROUTING.md). One branch/PR per spec; tests and real fixture changes are part of the same work, never postponed to an unindexed general cleanup.

| Order | Owning spec | Outcome |
|---|---|---|
| 01 | [Shell, `alp-ui` and test foundation](01-shell-and-test-foundation.md) + [acceptance closeout](SPEC_01_CLOSEOUT.md) | **OPEN:** screenshot/Showcase parity, README native evidence, `.venv` setup, Git/LFS/commit proof before 02 |
| 02 | [Collection Scan & metadata](02-collection-scan-and-metadata.md) | real WAV checks, actionable errors and rebuildable `.alpaca/` cache |
| 03 | [Dataset Build](03-dataset-build.md) | noise/target Snippets, grouped train/val and immutable artifact |
| 04 | [Worker & Runs](04-runs-and-worker.md) | real QProcess lifecycle, reservation, cancellation/recovery |
| 05 | [CNN & RF](05-cnn-and-rf-training.md) | real loadable Models, line/bar Plots with honest metrics |
| 06 | [macOS release/installer](06-macos-release-and-installer.md) | controlled, tested native `.app` and approved distributable `.dmg` |
| 07 | [Windows release/installer](07-windows-release-and-installer.md) | native Windows path/Qt/Worker validation and versioned `.exe` installer |

## Shared contracts (consult only where applicable)

- Core product: [`VISION`](../VISION.md), [`GLOSSARY`](../GLOSSARY.md), [`models/USER_WORKFLOWS_AND_DATA_MODEL`](../models/USER_WORKFLOWS_AND_DATA_MODEL.md), [`models/WORKFLOW_RULES`](../models/WORKFLOW_RULES.md) — read the sections impacted by active spec, not everything automatically.
- Qt UI: [prototype parity](../design/UX_PARITY_MATRIX.md) and [real `alp-ui` API mapping](../design/ALP_UI_CONSUMER_CONTRACT.md), sibling `../alp-ui` `gallery/showcase.py`. Prototype interactive HTML and PNGs are **bundled** under `docs/design/prototypes/training-first/`.
- Scientific source: [`docs/agent/SOURCE_MAP.md`](../agent/SOURCE_MAP.md) resolves `../alpaca-pipelines` and explains evidence/pinning. Read only its relevant algorithms before adapting.
- Artifacts, process and file safety: [`ARCHITECTURE`](../ARCHITECTURE.md); do not introduce web API, database, inference, review, annotation editor or queue.
- Tests: [`UNIT_TESTING`](../UNIT_TESTING.md) or [`INTEGRATION_TESTING`](../INTEGRATION_TESTING.md) plus **exact** `UT-*`/`IT-*` rows and relevant [`TD-*` data class](../INTEGRATION_TEST_DATA.md); HPC/fixtures only as needed.
- Release: [`RELEASE_PROCESS`](../RELEASE_PROCESS.md). Native tests, signing/installer tests and exact artifacts required, never claimed ahead of implementation.

**Implementation location guide:** pure `domain/`; bounded audio/science `computation/`; manifests, stage-and-publish `persistence/`; train/build orchestration `workflows/`; scan/settings/Run supervisor `application/`; Qt navigation/models/`alp-ui` consumer `gui/`. Add modules on demand, not in advance. The current checked-in Python code is scaffold; the prototype's scientific animations are simulated, not a back-end implementation.
