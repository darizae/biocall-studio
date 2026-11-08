# Agent routing — task-owned context

Open [AGENTS.md](../../AGENTS.md) and the exact active contract only. Verify `main` SHA, branch, installed upstream wheels and actual source before changing anything. Historical RV/ST planning text does not supersede merged implementation.

| Need | Owning route |
|---|---|
| Product identity and user journey | [Vision](../VISION.md), [README](../../README.md), [architecture](../ARCHITECTURE.md) |
| Train Collection, Dataset, Models | [workflow rules](../models/WORKFLOW_RULES.md), [model export](../science/MODEL_EXPORT_CONTRACT.md), [training catalog](../science/TRAINING_CONFIGURATION_CATALOG.md), owning Train source/tests |
| Detect inference/results | [Detect contract](../PREDICTION.md), [model export](../science/MODEL_EXPORT_CONTRACT.md), owning Detect source/tests |
| Review sessions/labels/export | [Review contract and decision table](../specs/review/README.md), [spectrogram decisions](../specs/review/SPECTROGRAM_DECISIONS.md), Review source/tests |
| Native UI | [accepted prototype](../design/prototypes/studio-detect/index.html), [native evidence](../design/evidence/review-correction/README.md), [public alp-ui consumer contract](../design/ALP_UI_CONSUMER_CONTRACT.md) |
| Science / upstream changes | [source map](SOURCE_MAP.md), [actual installed toolbox/alp-ui SHAs](../../pyproject.toml), owning tests |
| Tests, fixtures and audits | [unit index](../UNIT_TESTING.md), [integration index](../INTEGRATION_TEST_BEHAVIORS.md), [fixture index](../INTEGRATION_TEST_DATA.md), [test skill](indexed-integration-tests/SKILL.md), [Development](../DEVELOPMENT.md) |
| Current staged release | [Status](../IMPLEMENTATION_SEQUENCE.md), [series spec index](../specs/release-preparation-2026-11/README.md), [VERSION_CONTROL](../specs/release-preparation-2026-11/VERSION_CONTROL.md) |
| Native installers and promotion | [Release process](../RELEASE_PROCESS.md), [macOS spec](../specs/06-macos-release-and-installer.md), [Windows spec](../specs/07-windows-release-and-installer.md); not a source-stage pass |

**Review implementation is on `main`.** Existing visible native evidence does not substitute for the outstanding owner/installed-app/platform release approvals. Keep the image files and JSON provenance. Complete cross-workflow Studio ordinary-suite qualification and post-release 2026 spec retirement are deferred to spec 05.

For GitHub API PR delivery in this series, use [VERSION_CONTROL](../specs/release-preparation-2026-11/VERSION_CONTROL.md), not historical local-merge/no-push text. Never infer passing tests from their index.
