# Implementation specifications

[Roadmap and current status](../IMPLEMENTATION_SEQUENCE.md) is the only stage-order authority. Historical ST-01–ST-11 and REV-01–REV-04 specs are retained as scoped implementation records, **not** invitations to repeat completed work. Use [agent routing](../agent/ROUTING.md) to open only the spec for the requested task. The current source baseline is recorded in the roadmap; macOS/Windows installed-release gates remain separate.

| Area | Owning documents |
|---|---|
| Detect stages | [ST-03](ST-03-detect-workspace.md) · [ST-04](ST-04-wav-discovery.md) · [ST-05](ST-05-model-intake.md) · [ST-06](ST-06-detect-workers.md) · [ST-07](ST-07-cnn-detection.md) · [ST-08](ST-08-results-ux.md) · [ST-09](ST-09-rf-refinement.md) · [ST-10](ST-10-corpus-export.md) |
| Subsequent refinements | [REV-01](manual_revision_specs/REV-01-project-consolidation.md) · [REV-02](manual_revision_specs/REV-02-detect-guided-workflow.md) · [REV-03](manual_revision_specs/REV-03-interface-language-and-theme.md) · [REV-04](manual_revision_specs/REV-04-Detect-Navigation-and-History.md) |
| Qualification | [ST-11](ST-11-unified-qualification.md) — source-app qualification; installed releases still deferred |
| Proposed shared capability | [REV-05 output-size preflight](manual_revision_specs/REV-05-output-size-preflight.md) — **spec only, not implemented or approved** |

Testing IDs belong in the existing [unit](../UNIT_TESTING.md) and [integration](../INTEGRATION_TEST_BEHAVIORS.md) indexes. Do not create a second test plan or run the full Train→Detect scenario in a narrowly scoped revision.
