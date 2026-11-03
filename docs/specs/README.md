# Current specifications

Completed ST-01–ST-10 and REV-01–REV-04 implementation specs were removed after source integration; the [current status](../IMPLEMENTATION_SEQUENCE.md), [domain contract](../PREDICTION.md), [native UX matrix](../design/UX_PARITY_MATRIX.md) and [indexed tests](../INTEGRATION_TEST_BEHAVIORS.md) remain authoritative. Do not restore the old specs for maintenance.

- **Implemented and owner-reviewed:** [REV-05 — output-size and free-space preflight](manual_revision_specs/REV-05-output-size-preflight.md). Shared `StorageEstimate`, Train/Detect consumers and indexed `UT-SIZE-*` / `IT-SIZE-*` coverage are present on the reviewed `main` baseline; see its [completed handoff](manual_revision_specs/REV-05-output-size-preflight.md#mandatory-final-handoff-to-review-rv-01).
- **Approved planning, not implemented:** [Review — ordered RV-01–RV-08 specifications](review/README.md). RV-01 inherits completed REV-05 from the reviewed base; every subsequent stage requires its predecessor's explicit owner gate. Review must not reimplement shared preflight.
- **Retained qualification reference:** [ST-11](ST-11-unified-qualification.md) for existing installed-release traceability; results are in [ST-11 qualification](../ST-11_QUALIFICATION.md).
- **Deferred installed releases:** [macOS](06-macos-release-and-installer.md) and [Windows](07-windows-release-and-installer.md). They are unchanged by this cleanup.

Test definitions stay in the existing [unit](../UNIT_TESTING.md) and [integration](../INTEGRATION_TEST_BEHAVIORS.md) indexes, not in a new plan.
