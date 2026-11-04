# Agent routing — minimum task context

Read [`AGENTS.md`](../../AGENTS.md), then **only the owning current contract and code/tests** for the request. Verify real paths, Git state and installed source. Completed ST-01–ST-10 and REV-01–REV-04 implementation specs/handoffs have been removed; do not look for or reconstruct them. Do not preload all documentation or sibling repositories.

| Task | Start here; open further material only for a concrete dependency |
|---|---|
| Detect domain, inference, exports | [Detect contract](../PREDICTION.md), owning `biocall_studio` source and corresponding indexed test rows; [Model contract](../science/MODEL_EXPORT_CONTRACT.md) only for compatibility |
| Train behavior | Owning Train module/tests; [training catalog](../science/TRAINING_CONFIGURATION_CATALOG.md) only for configuration changes. Preserve existing Train scientific behavior. |
| Native UI/copy | [owner UI feedback](../specs/manual_revision_specs/UI-pass-revision-spec.md) and [native UI evidence](../design/evidence/st-11-native/README.md), actual native screens, accepted [prototype](../design/prototypes/studio-detect/index.html), [public alp-ui contract](../design/ALP_UI_CONSUMER_CONTRACT.md) only when controls are involved |
| REV-05 storage preflight (implemented) | [REV-05](../specs/manual_revision_specs/REV-05-output-size-preflight.md), shared storage contract, and owning Train/Detect adapters/tests. No full-Studio E2E. |
| Review (staged RV-01→RV-08; RV-04 awaiting owner gate) | [Review index and locked decisions](../specs/review/README.md) → **only the active stage**. REV-05 and RV-01–RV-03 are owner-approved on the reviewed local base; RV-04 has an isolated implementation handoff on `review-rv04-cache-generation-and-preflight`; RV-05 onward are not authorized. Reuse shared REV-05 preflight; no duplicate service or early corpus export UI migration. |
| Scientific/toolbox or UI-library change | [Source map](SOURCE_MAP.md) and [upstream workflow](UPSTREAM_TOOLBOX_WORKFLOW.md); inspect only the actual owning API/fixtures |
| Documentation or qualification | Exact affected files, [status](../IMPLEMENTATION_SEQUENCE.md), existing [test indexes](../UNIT_TESTING.md), [ST-11 evidence](../ST-11_QUALIFICATION.md) where relevant |
| Deferred installed release | Only after separate authorization: [macOS](../specs/06-macos-release-and-installer.md), [Windows](../specs/07-windows-release-and-installer.md), [release process](../RELEASE_PROCESS.md) |

**Tests on demand:** open [unit](../UNIT_TESTING.md), [integration](../INTEGRATION_TEST_BEHAVIORS.md), [fixtures](../INTEGRATION_TEST_DATA.md), or [test skill](indexed-integration-tests/SKILL.md) only for the owning rows. Follow [Git delivery](GIT_DELIVERY.md) at commit/integration time. Report actual execution evidence, never infer it from test indexes or historical screenshots. Do not automatically merge or push.
