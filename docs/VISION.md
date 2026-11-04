# BioCall Studio — product contract

One local PySide6/`alp-ui` desktop application with a **Studio launchpad** and three distinct workspaces:

- **Train:** select/validate recording + positives Collection; build immutable binary `target`/`noise` Datasets; train CNN/RF Models; inspect Runs and provenance. Preserve the current native implementation.
- **Detect:** select a compatible Train Model and independent source-recording Collection; discover WAVs recursively and safely; run CNN candidate detection; inspect immutable metadata results; optionally apply an RF second layer producing a new linked metadata result; export selected results as WAV snippets, concatenated WAV with Raven TSV, or both.
- **Review:** placeholder only. No review engine, labeling or annotation editing at this stage.

Studio owns application identity, launchpad and workspace switching. Each workspace owns its workflow, validation, metadata, persistence, UI and tests. Extract shared infrastructure only with established reuse. No network/HPC dependency or invented scientific capability.

Source WAVs remain read-only. Detect metadata/results live outside the recording root in app-owned storage. Audio is materialized only by an explicit Corpus Export to a visible user-selected destination. Both Train and Detect may reference the same recording files without sharing Collection identity or Run outputs.

[Detect contract](PREDICTION.md) · [implementation stages](IMPLEMENTATION_SEQUENCE.md) · [accepted Studio/Detect prototype](design/prototypes/studio-detect/index.html) · [native UI evidence](design/evidence/st-11-native/README.md).
