# alpaca Desktop Trainer

**Target:** a local, Collection-first PySide6 application for preparing supervised bioacoustics Datasets and training CNN or Random Forest Models. The **product specification** is defined here; the checked-in Python application code is a development scaffold and is **not evidence that all target behaviors have been implemented**. Consult the numbered specs before extending that scaffold.

## Product flow

1. **Select Collection**: point to an existing folder containing `recordings/*.wav` and `positives/*.wav`. Files remain in place.
2. **Read Collection**: asynchronously validate directories, WAV headers, positive filenames and source-relative timestamps; show exact affected paths and corrections. Save rebuildable metadata under `.alpaca/` after a successful scan.
3. **Build Dataset**: select Source Recordings, choose protected Negative Mining and source-grouped `train`/`val` Splits; publish immutable materialized target/noise Snippets.
4. **Train Model**: choose the Dataset and a CNN or Random Forest configuration. Supervise one Active Run through a separate Worker Process. Publish a reusable, family-labelled Model and metrics.
5. **Inspect** Collections, Datasets, Models, Runs; delete a Dataset explicitly subject to input reservations.

The filename contract, explained with examples in [Selecting a Collection](docs/wiki/SELECTING_A_COLLECTION.md), is:

`<source-stem>__start-<integer>ms__end-<integer>ms__<unique-label>.wav`

The timestamps are in the *original Source Recording*, not the cropped WAV. Ordinary validation verifies metadata consistency, **not** waveform identity.

## Design reference

Open [`docs/design/prototypes/training-first/index.html`](docs/design/prototypes/training-first/index.html) in a browser to explore the interactive UX and sample states. The browser prototype simulates Dataset Build and Training; its output is **not a scientific implementation**. Its design contract and native behavior are described in [`docs/design/TRAINING_FIRST_UX.md`](docs/design/TRAINING_FIRST_UX.md).

## Documentation routing

Start with [`AGENTS.md`](AGENTS.md) → [`docs/agent/ROUTING.md`](docs/agent/ROUTING.md) → **only your active spec** in [`docs/specs/README.md`](docs/specs/README.md). First coding session is spec 01; follow routed links rather than reading all docs. Key owner references:

| Need | Authoritative reference |
|---|---|
| Domain purpose, in/out scope | [`docs/VISION.md`](docs/VISION.md) |
| Consistent names | [`docs/GLOSSARY.md`](docs/GLOSSARY.md) |
| Workflow and storage graph | [`docs/models/USER_WORKFLOWS_AND_DATA_MODEL.md`](docs/models/USER_WORKFLOWS_AND_DATA_MODEL.md) |
| Filename, audio, mining, split and family rules | [`docs/models/WORKFLOW_RULES.md`](docs/models/WORKFLOW_RULES.md) |
| GUI/process/storage/locking boundaries | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| Delivery gates and ordered specs | [`docs/IMPLEMENTATION_SEQUENCE.md`](docs/IMPLEMENTATION_SEQUENCE.md) and [`docs/specs/`](docs/specs/) |
| Testing decisions and traceability | [`docs/UNIT_TESTING.md`](docs/UNIT_TESTING.md), [`docs/INTEGRATION_TESTING.md`](docs/INTEGRATION_TESTING.md), [`docs/INTEGRATION_TEST_BEHAVIORS.md`](docs/INTEGRATION_TEST_BEHAVIORS.md) |
| Data classes, generators, HPC fixture policy | [`docs/INTEGRATION_TEST_DATA.md`](docs/INTEGRATION_TEST_DATA.md) |
| Build/test/local UI environment | [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) |
| Agent implementation and audit checklists | [`docs/agent/SPEC_WRITING_AND_IMPLEMENTATION_PRINCIPLES.md`](docs/agent/SPEC_WRITING_AND_IMPLEMENTATION_PRINCIPLES.md) and [`docs/agent/indexed-integration-tests/SKILL.md`](docs/agent/indexed-integration-tests/SKILL.md) |

Scientific code may be **selectively adapted** from sibling **`../alpaca-pipelines`** (verify the actual directory and commit; use [`source map`](docs/agent/SOURCE_MAP.md)) after checking precise current interfaces/tests. Pipeline artifact formats do not automatically define Trainer formats. HPC is an **optional permissioned source for small anonymized test fixtures**, never a runtime service. Details remain in the untracked private skill under `docs/priv/hpc-source-access/`.

## Development status

Target delivery steps and open gates are in [`docs/IMPLEMENTATION_SEQUENCE.md`](docs/IMPLEMENTATION_SEQUENCE.md). Existing tests may exercise only scaffolding; a green scaffold test does not imply Collection scanning, Dataset materialization, CNN/RF Training, or native packaging is complete.

## Supplied handoff, sibling checkouts and delivery targets

- The **entire interactive UX prototype is included** at `docs/design/prototypes/training-first/` (index.html, app.js, styles.css and preview PNGs). For native fidelity compare its [parity matrix](docs/design/UX_PARITY_MATRIX.md) with `../alp-ui/gallery/showcase.py` / `../alp-ui/docs/images/showcase.png` and the public [component API map](docs/design/ALP_UI_CONSUMER_CONTRACT.md), with a bundled [showcase screenshot](docs/design/references/alp-ui-showcase.png).
- In your repos folder keep this project beside `alp-ui` and **`alpaca-pipelines`**: `repos/alpacaDesktopTrainer/`, `repos/alp-ui/`, `repos/alpaca-pipelines/`. The pipeline sibling is a **source reference**, not code vendored into this handoff. Check actual checkout spelling and source SHA before scientific work.
- `tests/data/example_collection/` contains a **real, deterministic synthetic** WAV Collection, registered with SHA-256 and intended for Git LFS. An HPC-derived/permissioned fixture is **not claimed** until actually sampled, anonymized, approved, registered and checked in. See [fixture policy](docs/INTEGRATION_TEST_DATA.md).
- `docs/priv/` (HPC access skill, private site notes, read-only helper) is **shipped in this local ZIP but gitignored**. Never force-add it. If sharing the ZIP itself, treat it as private; remove `docs/priv` first before sharing outside trusted environments.
- Install **Git LFS before your first `git add`** (e.g. `brew install git-lfs && git lfs install` on macOS), then verify `git check-attr filter tests/data/example_collection/recordings/REC_A.wav` returns `lfs`. Do not initialize/commit with missing LFS filters. [Handoff checklist](docs/HANDOFF.md).
- Native app / controlled **macOS `.dmg`** delivery is a future result of [spec 06](docs/specs/06-macos-release-and-installer.md), with native Windows `.exe` in [spec 07](docs/specs/07-windows-release-and-installer.md), not output already present.
