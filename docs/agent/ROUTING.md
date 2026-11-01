# Agent routing — read the minimum necessary

**Start:** `AGENTS.md` → [sequence and branch gate](../IMPLEMENTATION_SEQUENCE.md) → **one current stage spec**. Verify paths, real Git state and code. **Do not preload other specs, all Train docs, all test indexes or entire sibling repositories.** ST-01 and ST-02 are owner-approved; next implementation stage is ST-03 unless the real reviewed branch shows otherwise.

| Current work | Read only these authorities *when relevant* |
|---|---|
| ST-03 Collection/Relink | [ST-03](../specs/ST-03-detect-workspace.md), [Detect domain rules](../PREDICTION.md), actual settings/persistence + native shell |
| ST-04 WAV inventory | [ST-04](../specs/ST-04-wav-discovery.md), accepted ST-03 handoff, real WAV/path scanner sources |
| ST-05 Model intake | [ST-05](../specs/ST-05-model-intake.md), [Train Model export](../science/MODEL_EXPORT_CONTRACT.md), relevant producer code and **exact** upstream model/preprocessor functions |
| ST-06 Worker/log | [ST-06](../specs/ST-06-detect-workers.md), Train Worker/diagnostics seams, accepted ST-04/05 handoffs |
| ST-07 CNN | [ST-07](../specs/ST-07-cnn-detection.md), validated ST-04/05/06 handoffs, exact CNN toolbox source/tests |
| ST-08 Results UI | [ST-08](../specs/ST-08-results-ux.md), ST-07 Result contract, [UX matrix](../design/UX_PARITY_MATRIX.md) |
| ST-09 RF | [ST-09](../specs/ST-09-rf-refinement.md), RF Model/Result contracts, exact verified RF source/tests |
| ST-10 export | [ST-10](../specs/ST-10-corpus-export.md), selected Result contract, actual WAV extraction/Raven reference |
| REV-01 consolidation | [REV-01](../specs/manual_revision_specs/REV-01-project-consolidation.md), reviewed ST-10 handoff, actual package/build/import/Worker seams and live source instructions |
| REV-02 Detect workflow | [REV-02](../specs/manual_revision_specs/REV-02-detect-guided-workflow.md), accepted REV-01 layout, current Detect controller/Qt routes and installed public `alp-ui` source |
| REV-03 copy/theme | [REV-03](../specs/manual_revision_specs/REV-03-interface-language-and-theme.md), accepted REV-02 routes, exact tooltip inventory and owner-approved copy table |
| REV-04 navigation/history | [REV-04](../specs/manual_revision_specs/REV-04-Detect-Navigation-and-History.md), accepted REV-03 interface, current Detect controller/routes and export receipt verification seam |
| ST-11 full qualification | [ST-11](../specs/ST-11-unified-qualification.md), existing [macOS](../specs/06-macos-release-and-installer.md)/[Windows](../specs/07-windows-release-and-installer.md) requirements, [release process](../RELEASE_PROCESS.md) |

**Just-in-time references:** UI work → accepted [prototype](../design/prototypes/studio-detect/index.html), [UX parity matrix](../design/UX_PARITY_MATRIX.md), [public alp-ui contract](../design/ALP_UI_CONSUMER_CONTRACT.md), genuine Train screenshots; tests → **only owning rows** in [unit index](../UNIT_TESTING.md), [integration index](../INTEGRATION_TEST_BEHAVIORS.md), [TD fixtures](../INTEGRATION_TEST_DATA.md); upstream needed → [source map](SOURCE_MAP.md) and [upstream branch procedure](UPSTREAM_TOOLBOX_WORKFLOW.md); Git start/end → [delivery](GIT_DELIVERY.md). No broader reads unless a concrete dependency requires them.

**Per-stage execution:** inspect the seam → write exact scoped failing test(s) → implement → run owned real-boundary and affected regressions → full feasible ordinary suites/ruff/audit before commit → review evidence/UX → record real commit/branch. Stage branches integrate to `detect` locally **only after owner approval**; ST-11 approval permits reviewed local `detect` → `main` merge. **No pushes, automatic merges, stage-skipping, fake prototype data in production or whole-Studio E2E before ST-11.** Historical missing files do not trigger speculative reconstruction.
