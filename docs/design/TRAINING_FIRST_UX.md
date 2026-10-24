# alpaca Desktop Trainer — Collection-first UX contract

**Target product:** native PySide6 application. **Design reference:** [interactive HTML prototype](prototypes/training-first/index.html) and screenshot assets in its folder. **Important:** the browser prototype validates selected WAV headers/names in its own limited sandbox but *simulates* Dataset Build, Training, Run progress, Dataset/Model publication and persisted collection metadata. The design does not establish scientific or native integration-test coverage. Requirements for actual behavior are in the canonical docs and numbered specs.

## 1. Primary journey

```text
Select Collection → Reading Collection → Collection overview
       → Build Dataset → Dataset Build Run → Dataset detail
       → Train Model (CNN | Random Forest) → Training Run → Model detail
```

Navigation includes Collections, Datasets, Models, Runs, a small Wiki and Settings. A compact Active Run indicator is accessible across pages. Each saved artifact page shows a **stable ID plus separate human-readable label** where applicable. The primary entry action is choosing an existing Collection folder; there is no file import/copy, source-audio standardization, annotation editor, prediction, review or external scheduler in this app.

## 2. Screens and acceptance states

| Screen | Information and controls | Failure/empty/loading |
|---|---|---|
| **Select Collection** | Native folder chooser, minimal `recordings/` + `positives/` instruction and Wiki link. | Cancel chooser → no state change; no Collection configured → start here. |
| **Reading Collection** | Nonblocking, cancellable directory and header inspection; counts, progress, inspected source/positive paths and issues-so-far. | Permission/cancel/invalid → no “ready” metadata publication. |
| **Collection** | File path, validity status, Source Recording/positive counts, total duration, recording→positive mapping, per-relative-file reasons and metadata freshness. | Build Dataset disabled while issues or stale state remain. Rescan after correction. |
| **Build Dataset** | Select/deselect Source Recordings; explicit candidate-negative count/ratio, seed, positive exclusion margin, allocation and source-group train/val ratio; preview estimated eligibility/class balance. | No selected source or insufficient protected-free windows → actionable block. Preview is not scientific output. |
| **Dataset Build Run** | Active stage, progress and cancellation through the Worker. | Crash/cancel/underfill never produces a complete Dataset. |
| **Dataset** | Immutable Snippet counts/labels, train/val membership, source-time provenance, source Collection link, settings, Train Model and explicit Delete. | Refuse delete when reserved by Active Run; no silent Model cascade. |
| **Train Model** | Dataset picker, CNN/RF family selection and context-specific configuration. | Validate before Run, no options with imaginary algorithm support. |
| **Training Run** | Genuine stage/metrics/progress. CNN may show epoch losses; RF shows feature extraction, fitting, validation, feature importance, no simulated epoch losses. | Failure does not publish Model or fictitious scores. |
| **Model** | Readable label, stable ID, family badge, source Dataset, resolved configuration, metrics/undefined reasons and saved file manifest. | Native loader/format error is visible and not masked as a successful Model. |
| **Collections / Datasets / Models / Runs** | Paginated summary lists and recent valid entries; navigate into detail. | Clear empty states; no eager loading of millions of rows. |
| **Wiki / Settings** | Folder naming examples, validation advice; machine-local Collection binding/relink preferences. | Rebind triggers revalidation rather than trusting stored path. |

## 3. Collection selection and scientific terms

The selected folder is the **Collection**. Source Recording WAVs live directly in `recordings/`; user-exported positive WAVs live directly in `positives/`, named:

`<complete-source-stem>__start-<integer>ms__end-<integer>ms__<unique-label>.wav`

Time is in integer milliseconds **relative to the original recording**, not the clipped file. Only WAV inputs are supported; support for specific PCM/float encodings is determined by the native reader. Reject unexpected nesting, missing folders, unsafe paths/symlink escape, collisions, source mismatches and invalid time/header checks. Each problem includes an exact relative path, stable category and corrective action. Positive Examples create derived `target` Annotations that define protected mining spans. The overview **does not verify waveform alignment**; do not call them waveform-verified positives.

The Scan caches rebuilt metadata in `<Collection>/.alpaca/collection.json` and bounded partitions and verifies freshness at reopen/build; there is no input audio copy. Read one header per WAV initially (not whole recording), re-read only changed headers on warm reopen, and page large tables. See [`../models/WORKFLOW_RULES.md`](../models/WORKFLOW_RULES.md) for precise logic, [`../ARCHITECTURE.md`](../ARCHITECTURE.md) for process/I/O/storage boundaries and the [Selecting a Collection Wiki](../wiki/SELECTING_A_COLLECTION.md) for user guidance.

## 4. Dataset and Training UX

From validated sources, Dataset Build materializes immutable `target`/`noise` **Snippets** from original Source Recording audio using a protected positive union, explicit safety margin, bounded negative sampling and source-grouped `train`/`val`. Mining is not guaranteed ground-truth negativity. A Dataset is only listed after real staged output has passed verification. The same Dataset can train both families:

- **CNN**: device, epochs, batch size, learning rate, architecture/transform settings and measured train/validation loss. Begin with a bounded CPU smoke path.
- **Random Forest**: real acoustic feature extraction, tree count, minimum leaf count, max depth, threshold, deterministic seed and validation metrics; show feature importance and actual stage progress. Reuse/verify current `alpaca-pipelines` feature schema and fitting code rather than inventing an RF training API.

Model details distinguish family-specific format, feature/transform schema, Dataset provenance, actual metrics (including not-defined reasons), stable artifact ID and editable display label only where the storage contract explicitly supports such editing. A Model is a reusable trained artifact **for this training application**; publication alone is not a promise of a prediction workflow.

## 5. Native interaction and architecture constraints

Use native local `alp-ui` Widgets components on PySide6: **`FolderPicker`** wraps the native directory dialog, **`HelpHint`** provides accessible contextual help, **`Plot`** renders measured CNN line losses or RF feature importance bars alongside accessible exact numeric tables. Use QAbstractItemModel for paged lists, sibling `gallery/showcase.py` for native composition, clear accessible status, bounded background scan and one supervised QProcess Worker for scientific Runs. See [`ALP_UI_CONSUMER_CONTRACT.md`](ALP_UI_CONSUMER_CONTRACT.md) and [`UX_PARITY_MATRIX.md`](UX_PARITY_MATRIX.md). Collection Scan is not a scientific Run. Run progress remains visible across navigation, but no queue exists. Machine absolute paths are only Application Settings; portable `Dataset`/`Model`/Collection metadata references use safe relative segments. Stage/publish immutably, respect input reservations, never overwrite or modify source/positive WAVs.

The prototype demonstrates layout and copy, not a one-to-one native widget tree. It cannot save arbitrary `.alpaca/` files, access local directories outside user file-pick permissions, train either model family or guarantee OS process/permission semantics. Implement these at the native owners with tests.

## 6. Acceptance evidence routing

| Scope | Required docs/tests |
|---|---|
| Navigation, empty states, Settings | spec 01; `IT-UI-*`, `TD-UI` |
| Real folder selection, fast validation, cache | spec 02; `UT-COL-*`, `IT-COL-*`, `TD-COL`/`TD-WAV`/`TD-CACHE`/`TD-SCALE` |
| Protected mining, reproducible immutable Dataset | spec 03; `UT-DB-*`, `IT-DB-*`, `TD-MINE`/`TD-SPLIT` |
| One Active Run, real Worker, recovery | spec 04; `UT-RUN-*`, `IT-RUN-*`, `TD-RUN` |
| Real CNN/RF on identical Dataset, accurate metrics | spec 05; `UT-TRAIN-*`, `IT-TRAIN-*`, `TD-TRAIN` |
| Native packaged macOS and Windows gates | spec 06; `IT-E2E-*`, `IT-WIN-*`, `TD-OS` |

The browser smoke can confirm sample states and basic interaction flow, but every claimed scientific result must be independently produced by a passing real native test. The behavior ID indexes are a **plan** until such tests exist.
