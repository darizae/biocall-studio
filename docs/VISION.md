# BioCall Studio Train — Product vision

## Purpose and audience

A bioacoustics researcher with **existing Source Recording WAVs** and manually exported **positive example WAVs** should be able to select a Collection, verify its input quality, create reproducible supervised training Datasets and train a CNN or Random Forest locally without managing file import pipelines or scripts. The app is a **desktop trainer**, not an experiment platform or labeling suite.

## Canonical user journey

1. **Select Collection** opens a folder picker. The user selects a directory containing direct children `recordings/` and `positives/`. The Collection remains in that directory. The app never copies or alters input WAVs.
2. **Reading Collection** asynchronously checks the actual directory entries, audio headers and positive filenames. It shows progress, counts, cancellation, per-file errors and recovery instructions. A validated overview shows duration/counts and the Source Recording → positive mapping. Invalid inputs block Build Dataset. The app stores a rebuildable `.alpaca/collection.json` plus bounded record partitions, then checks freshness on reopen and before build.
3. **Build Dataset** selects participating Source Recordings, protected positive intervals, seeded negative-window settings and source-grouped `train`/`val` Splits. It materializes target/noise Snippets from Source Recordings and publishes an immutable Dataset on success. All other audio is *unlabeled*, not guaranteed negative; chosen eligible intervals become candidate `noise` Snippets only under explicit mining rules.
4. **Train Model** chooses one Dataset, selects CNN or Random Forest, edits family-specific parameters, and starts a supervised local scientific Run. Training produces metrics, configuration, immutable Model files, stable ID, descriptive label and Dataset provenance. Existing Datasets may be reused by either family.
5. **Inspect/reopen** Collections, Datasets, Models and Run history. Inspect published Dataset splits and Model provenance/metrics. Explicit Dataset deletion is possible only when no Active Run reserves it; deletion never cascades to Models.

## Screens / navigation

Select Collection, Reading Collection, Collection overview, Build Dataset, Dataset Run, Dataset detail, Train Model, Training Run, Model detail, and lightweight Collections/Datasets/Models/Runs lists. Include a simple **Wiki / Selecting a Collection** and local Settings for folder bindings. The **Active Run** remains accessible throughout navigation. See [`design/TRAINING_FIRST_UX.md`](design/TRAINING_FIRST_UX.md) and the browser prototype for layout and screen states.

## Product invariants

- **Collection** is externally chosen and user-owned; `.alpaca/` metadata and results are app-owned children of that folder. If `recordings/`/`positives/` are missing, nested or incorrect, show actionable errors. Input folder validation is read-only until successful metadata publication.
- Positive filenames declare **source-time** spans via the mandatory grammar. Filename matching and WAV header agreement do not establish true waveform/source identity; never claim waveform verification.
- No source-audio bulk copy, forced resampling on select, or long full-audio decode to show an overview. Path containment, symlink safety, portable names, bounded memory and cancellation apply to all stages.
- Derived collection cache is disposable; files remain authoritative. Immutable Dataset/Model artifacts require validated staging, atomic publication and collision protection; Run State is persisted separately.
- **One Active Run**, either Dataset Build or Training, using a supervised Worker Process; UI never blocks on CPU- or disk-intensive work.
- Algorithms, train/val labels, data transforms and metrics must be explicit and reproducible. Undefined metrics stay undefined, not fabricated. Training runs are local; there is no HPC scheduler dependency.

## MVP deliverables

A functional native macOS app implementing the full journey; deterministic unit and real integration tests; locally reproducible CPU CNN and RF smoke workflows; bounded large-Collection scans; documented binary/manifests; installable/packaged execution. Windows is a planned distribution target subject to native qualification.

## Non-goals

Audio annotation editing, importing/normalizing a separate batch, an annotation promotion loop, prediction/inference UX, Corpus, review queues, Raven interchange, remote/HPC execution, arbitrary root/workspace management, arbitrary audio-format support, multiple parallel Runs, job queues, data synchronization, web services and a database. `alpaca-pipelines` may provide internal algorithms and scientific reference behavior, but none of these capabilities becomes part of the UX simply because it exists upstream.
