# Train — native workspace reference

Train's current PySide6 code and genuine native screenshots are authoritative for its existing workflow, navigation, copy, visual composition and failure states. Preserve behavior and local state when integrating with the Studio shell; do not rebuild Train from an HTML mockup.

**Journey:** Select Collection → Scan/validate → Build Dataset → Training (CNN or RF) → immutable Model and Run inspection. Existing sidebar routes include Collections, Datasets, Models, Runs, Wiki and Settings. Active Run remains accessible; navigational changes do not cancel it.

**Existing native evidence:**

- `docs/design/evidence/spec-01-native/select.png`
- `docs/design/evidence/spec-02-native/collection-valid.png`
- `docs/design/evidence/spec-03-native/builder.png`
- `docs/design/evidence/spec-05-native/train-cnn.png`
- `docs/design/evidence/spec-05-native/run-cnn-plot.png`

Inspect `src/biocall_studio_train/gui/`, `application/workspace.py` and relevant real tests for functional acceptance. [Studio UX matrix](UX_PARITY_MATRIX.md) owns *new* screen acceptance; [Model export contract](../science/MODEL_EXPORT_CONTRACT.md) owns Model facts. No changes to Train are authorized by ST-01.
