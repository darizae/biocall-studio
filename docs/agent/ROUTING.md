# Task router — one spec, scoped references

**Session start:** inspect `git status --short --branch`, latest commit, relevant source, test results and native evidence. Determine the actual next unaccepted phase; never assume the ZIP's timestamp or an old closeout note reflects live progress. Open **one spec** from this table. For phase 05, use [the 05 overview](../specs/05-cnn-and-rf-training.md) only if you need to identify the next unaccepted sub-spec; do not load all three. Each spec lists its additional references; follow those links **only when needed for the part being implemented**.

| Work being done | Start here |
|---|---|
| Native shell, Select Collection, Wiki, Settings, startup, initial empty states | [01](../specs/01-shell-and-test-foundation.md) |
| Verified outstanding shell acceptance gap only | [01 closeout](../specs/SPEC_01_CLOSEOUT.md) |
| Collection scan, WAV validation, metadata/cache | [02](../specs/02-collection-scan-and-metadata.md) |
| Dataset snippets, negative mining, splits | [03](../specs/03-dataset-build.md) |
| Run lifecycle, QProcess, cancellation/recovery | [04](../specs/04-runs-and-worker.md) |
| Extract reusable PCM/WAV computation upstream | [04.5](../specs/SPEC_04_5_UPSTREAM_AUDIO_EXTRACTION.md) |
| Training configuration, detailed native UI, presets (**05a first**) | [05a](../specs/05a-training-configuration-and-presets.md) |
| Real CNN training, shared Model publication/reload (**after 05a**) | [05b](../specs/05b-cnn-training-and-model-foundation.md) |
| Real RF training, both-family qualification (**after 05b**) | [05c](../specs/05c-rf-training-and-cross-family-acceptance.md) |
| Local logging, Worker diagnostics and support export (**after 05c**) | [05d](../specs/05d-end-to-end-logging-and-diagnostics.md) |
| Critical training-path and recovery verification (**after 05d**) | [05e](../specs/05e-training-critical-path-and-recovery-verification.md) |
| UI, chart, scale and CLI coverage closeout (**after 05e**) | [05f](../specs/05f-ui-chart-scale-and-cli-coverage.md) |
| Long-running Runs, safe exit and optional keep-awake (**after 05f**) | [05g](../specs/05g-long-running-sessions-and-safe-exit.md) |
| macOS app and signed/notarized DMG | [06](../specs/06-macos-release-and-installer.md) |
| Native Windows qualification and installer | [07](../specs/07-windows-release-and-installer.md) |

**Conditional lookups (not startup reading):**

| If the active work needs… | Open |
|---|---|
| A new domain term or invariant | [Glossary](../GLOSSARY.md) and relevant section of [workflow rules](../models/WORKFLOW_RULES.md) |
| Cross-layer storage/worker ownership | Relevant section of [Architecture](../ARCHITECTURE.md) |
| An indexed test, fixture class or HPC source | Exact rows in [unit index](../UNIT_TESTING.md), [integration index](../INTEGRATION_TEST_BEHAVIORS.md) and [fixture guide](../INTEGRATION_TEST_DATA.md); private HPC helper **only if authorized and necessary** |
| Native UI work | Active spec's row in [UX matrix](../design/UX_PARITY_MATRIX.md) and [prototype acceptance](../design/PROTOTYPE_ACCEPTANCE.md); actual `../alp-ui` Showcase |
| Scientific sibling implementation/source inspection | [Source map](SOURCE_MAP.md), restricted to affected symbols and tests |
| Reusable library defect or upstream extraction | [Upstream toolbox workflow](UPSTREAM_TOOLBOX_WORKFLOW.md) |
| First/last step of a spec or docs-only delivery | [Git delivery](GIT_DELIVERY.md) |
| Design of a **new** spec (not ordinary implementation) | [Specification principles](SPEC_WRITING_AND_IMPLEMENTATION_PRINCIPLES.md) |
| Future Prediction application planning only | [PREDICTION](../PREDICTION.md) — never an active Trainer implementation task |

**Execution:** inspect existing behavior → write failing owned test(s) → implement smallest correct change → run real integration where required → update only impacted docs/evidence → commit and report. Do not read non-implicated `UT-*`, `IT-*`, or `TD-*` rows; do not scan entire sibling repos. A missing sibling dependency is a setup blocker, not permission to invent an alternative library.
