# Agent routing — minimum task context

Read [`AGENTS.md`](../../AGENTS.md), then **only the owning current contract and code/tests** for the request. Verify real paths, Git state and installed source. Completed ST-01–ST-10 and REV-01–REV-04 implementation specs/handoffs have been removed; do not look for or reconstruct them. Do not preload all documentation or sibling repositories.

| Task | Start here; open further material only for a concrete dependency |
|---|---|
| Detect domain, inference, historical export readers | [Detect contract](../PREDICTION.md), owning `biocall_studio` source and corresponding indexed test rows; [Model contract](../science/MODEL_EXPORT_CONTRACT.md) only for compatibility. New corpus exports are Review-owned. |
| Train behavior | Owning Train module/tests; [training catalog](../science/TRAINING_CONFIGURATION_CATALOG.md) only for configuration changes. Preserve existing Train scientific behavior. |
| Native UI/copy | [owner UI feedback](../specs/manual_revision_specs/UI-pass-revision-spec.md) and [native UI evidence](../design/evidence/st-11-native/README.md), actual native screens, accepted [prototype](../design/prototypes/studio-detect/index.html), [public alp-ui contract](../design/ALP_UI_CONSUMER_CONTRACT.md) only when controls are involved |
| REV-05 storage preflight (implemented) | [REV-05](../specs/manual_revision_specs/REV-05-output-size-preflight.md), shared storage contract, and owning Train/Detect adapters/tests. No full-Studio E2E. |
| Review (RV-01→RV-08 source implemented; RV-08 owner gate pending) | [Review index and locked decisions](../specs/review/README.md) → **only the active stage**. The local `review` baseline contains RV-01–RV-07 at `570adc7`; RV-08 has an isolated qualification handoff on `review-rv08-qualification` with [actual evidence](../RV-08_QUALIFICATION.md). Do not infer visible-native or release sign-off from background source-app passes. |
| Scientific/toolbox or UI-library change | [Source map](SOURCE_MAP.md) and [upstream workflow](UPSTREAM_TOOLBOX_WORKFLOW.md); inspect only the actual owning API/fixtures |
| Documentation or qualification | Exact affected files, [status](../IMPLEMENTATION_SEQUENCE.md), existing [test indexes](../UNIT_TESTING.md), [ST-11 evidence](../ST-11_QUALIFICATION.md) where relevant |
| Deferred installed release | Only after separate authorization: [macOS](../specs/06-macos-release-and-installer.md), [Windows](../specs/07-windows-release-and-installer.md), [release process](../RELEASE_PROCESS.md) |

**Tests on demand:** open [unit](../UNIT_TESTING.md), [integration](../INTEGRATION_TEST_BEHAVIORS.md), [fixtures](../INTEGRATION_TEST_DATA.md), or [test skill](indexed-integration-tests/SKILL.md) only for the owning rows. Follow [Git delivery](GIT_DELIVERY.md) at commit/integration time. Report actual execution evidence, never infer it from test indexes or historical screenshots. Do not automatically merge or push.
