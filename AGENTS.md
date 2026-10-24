# alpaca Desktop Trainer — Agent instructions

## Contract and reading order

Build **alpaca Desktop Trainer**, a local, Collection-first PySide6 training application. The source of truth is [`docs/VISION.md`](docs/VISION.md) + [`docs/GLOSSARY.md`](docs/GLOSSARY.md) + [`docs/models/USER_WORKFLOWS_AND_DATA_MODEL.md`](docs/models/USER_WORKFLOWS_AND_DATA_MODEL.md) + [`docs/models/WORKFLOW_RULES.md`](docs/models/WORKFLOW_RULES.md). [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) owns infrastructure boundaries. [`docs/specs/README.md`](docs/specs/README.md) routes a task to a numbered implementation spec. The clickable HTML prototype is **UX evidence**, not a backend or acceptance test. Keep the implementation and docs aligned with this model even if a checked-in code scaffold has additional features.

**Context-efficient preflight:** read [`docs/agent/ROUTING.md`](docs/agent/ROUTING.md) and **one active spec** first. Use its route to read only **relevant sections** of domain/Architecture/UX/test docs and exact `UT-*`/`IT-*`/`TD-*` rows. Do not load all Markdown files or entire sibling repositories. The first session is **only spec 01**. Follow the documented red → green → refactor loop at real seams; case IDs in docs are planned until asserting tests actually pass.

## Non-negotiable product boundaries

- **Collection = the folder selected by the user**, with direct child `recordings/` and `positives/` directories. It is not a copied/imported artifact. Source WAVs and positive WAVs are read-only.
- Positive input WAV filenames encode Source Recording stem and **integer millisecond source-time** start/end. Valid inputs produce derived `target` Annotations; Dataset Build produces new materialized `target`/`noise` Snippets.
- `Collection/.alpaca/` holds rebuildable collection metadata, immutable Datasets, immutable Models and persisted Runs. Local Application Settings hold machine-specific paths/bindings, not portable manifests.
- Only **Dataset Build** and **Training** are scientific Runs. Reading/validating a Collection is an asynchronous cancellable I/O activity, not a Run. At most **one Active Run** at a time; no queue.
- The same immutable Dataset can train a **CNN** or a **Random Forest**. Model family determines hyperparameters, loader, input transformation and metrics. Do not conflate RF feature importances with CNN epoch losses.
- Do not implement prediction, corpus filtering, review, annotation editing/promotion, Raven interchange, user-facing imports or arbitrary independent artifact roots as part of this product.
- Keep source filesystem access path-contained and safe against traversal, symlink escape, filename collisions, and platform-specific names. Never silently overwrite an artifact or mutate input WAVs.

## Architecture and libraries

Keep `domain/` and pure validators independent of Qt; `workflows/` own Dataset Build/Training orchestration; `computation/` own bounded audio/mining/model algorithms; `persistence/` owns portable manifests and transactional publication; `application/` owns Collection scan coordination, settings and QProcess Worker supervision; `gui/` owns navigation/Qt models only. Create files **only when an actual consumer needs them**.

Use local sibling `../alp-ui` PySide6 Widgets library installed from its checkout/wheel, not PyPI. **Current API exposes `FolderPicker` (native directory dialog), `HelpHint` (hover/keyboard accessible contextual help), `Plot` (native numeric line/categorical bar), DataTable and other themed components**; map these to the prototype with [`docs/design/ALP_UI_CONSUMER_CONTRACT.md`](docs/design/ALP_UI_CONSUMER_CONTRACT.md), [`docs/design/UX_PARITY_MATRIX.md`](docs/design/UX_PARITY_MATRIX.md) and sibling `gallery/showcase.py`. Use native Qt layout/navigation where the library has no component, never clone library internals. Recheck public API/SHA before coding. **Scientific sibling is intended at `../alpaca-pipelines`**, not an assumed pip package; consult [`docs/agent/SOURCE_MAP.md`](docs/agent/SOURCE_MAP.md) and verify its real location/source tests. No automatic schema compatibility.

Develop/test natively on **macOS**, design portable paths and launch for **Windows**. **Spec 06 must deliver a controlled, installable signed/notarized macOS `.dmg`; spec 07 separately delivers/qualifies a Windows `.exe` installer.** No public installer claims until native packaged real CNN/RF and security/release gates pass. Workers launch from the actual bundled app environment, never a shell or globally installed interpreter. See [`docs/RELEASE_PROCESS.md`](docs/RELEASE_PROCESS.md).

## Tests and data

Classify the test **before writing it**. Pure filename/WAV/interval/split/RF parameter decisions are fast `UT-*` cases; real file artifacts, Qt progress/reopen, selective cache freshness, real QProcess cancellation/recovery, and real CNN/RF training are `IT-*` cases. Implement both at their owning public seam, with the exact ID in each asserting test function's docstring. IDs in a spec or passing unit tests **do not imply** integrated coverage. Execute local macOS integration tests; early CI runs only independent unit/static tests. Log actual commands, pass/fail, and blockers, including native Windows.

Use versioned `tests/data/example_collection/` deterministic **real WAV** files first, then smallest permissioned anonymized HPC-derived Git LFS fixtures with recorded checksums (not yet present unless explicitly registered). HPC access is read-only, scoped and optional; ordinary tests **never** connect to the HPC. The **handoff ZIP includes** `docs/priv/hpc-source-access/SKILL.md`, its private site notes and read-only helper; `docs/priv/` is **untracked by design** and omitted from every Git commit. Its helper governs authorized sampling. Ordinary CI/tests never connect. Git LFS must be installed before the first `git add` of WAV files. Stop for owner guidance if absent. Never commit credentials, raw sensitive audio or private HPC paths. Get approval before tracked fixture payload exceeds **1,000,000,000 bytes**. See the fixture register/data guide.

## Change discipline

One numbered spec per branch/PR from updated main: `spec/NN-name`; documentation-only `docs/name`; independent fixes `fix/name`. Deliver production change, owned tests, fixture registry updates and relevant spec in the **same** PR. Avoid speculative helpers, compatibility facades, databases, web services and premature abstraction. Amend the Glossary whenever a new canonical concept is introduced. Enforce source-time units and manifest invariants at boundaries, not in every caller. Report out-of-scope existing scaffold behavior as implementation debt, not a requirement.

See [`docs/agent/SPEC_WRITING_AND_IMPLEMENTATION_PRINCIPLES.md`](docs/agent/SPEC_WRITING_AND_IMPLEMENTATION_PRINCIPLES.md) for the preflight/review checklist.
