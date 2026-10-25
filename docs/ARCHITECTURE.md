# alpaca Desktop Trainer — Architecture

## 1. Layers and authoritative handoffs

```text
PySide6 GUI + public local alp-ui components
         | controller signals, paged models, readable errors
Application Controller ─── Application Settings (local bindings/preferences)
   |          |
   |          ├── Collection Scan (background I/O task, cancellable, NO Run)
   |          └── QProcess Worker Supervisor (one Active Run)
   |                         |
   |                  Worker entry point
   |                         |
   └──────────────> Qt-free workflows <─────────────
                              |
                       domain + verified scientific libraries
                              |
                       portable persistence
                              |
               Collection/.alpaca/ artifacts and Run State
```

`domain/` defines source-time/identity/validation/negative windows/splits and pure Model Family schemas; **reusable bounded audio extraction and CNN primitives are owned by the installed `bioacoustics_dl_toolbox`** after [Spec 04.5](specs/SPEC_04_5_UPSTREAM_AUDIO_EXTRACTION.md); Trainer's Qt-free `workflows/` adapt verified audio/scientific APIs and own Dataset Build and Training transaction handoffs; `persistence/` parses/version-checks/writes portable files and guarantees publication; `application/` owns settings, scan task, Worker supervision, lifecycle, reservations and recovery; `gui/` uses Qt/`alp-ui` but contains no scientific calculations. Create modules on demand; this is a responsibility map, not a request to fabricate an empty package tree.

## 2. Storage and identity

**Collection is the selected user-owned folder**, not a copy. The only required input dirs are `recordings/` and `positives/`; accepted WAV files live directly underneath. The app creates `.alpaca/` on validated successful metadata publication. Do not write outside `.alpaca/` during normal operation, and **never modify Source Recording or Positive Example WAV files**. App-owned directories are:

```text
.alpaca/
  collection.json                  # small mutable versioned cache/identity
  records/part-*.jsonl            # bounded source inventory/header facts
  positives/part-*.jsonl          # bounded derived Annotation metadata
  datasets/<dataset-id>/          # immutable Dataset
  models/<model-id>/              # immutable Model
  runs/<run-id>/                  # mutable Run State/logs
  .staging/<unique-id>/           # incomplete, never browse as published
```

Machine-local Application Settings (Qt standard writable app config location, overridable for tests) remember Collection folder path, stable Collection ID and GUI preferences. If a folder moves, the user explicitly relinks it; identity and paths are checked against current source files, not adopted on name similarity. All portable scientific artifacts store **relative normalized `/` paths**, an ID, schema versions and provenance/fingerprints, never absolute host drive paths. Cross-artifact links use **stable IDs** (e.g. `dataset_id`), never `../` navigation between Dataset and Model directories. Relative paths are resolved under a known Collection root after rejection of `..`, absolute prefixes, unsafe separators, reserved filenames, symlink escape and filesystem collisions. A cache hit may not skip these checks.

### Suggested logical fields

- `collection.json`: `schema_version`, `collection_id`, timestamps, scan/version, summarized counts/duration, references to partitions, input directory inventories and freshness status. All counts derive from published partitions.
- record JSONL: source `id`, `relative_path`, sample rate, channels, format, frames, duration and fingerprint.
- positive JSONL: `relative_path`, recording `id`, `start_ms`, `end_ms`, label, own WAV header/fingerprint.
- `dataset.json`: `schema_version`, Dataset ID, Collection ID, resolved build settings/seed, exact selected input references and fingerprints, Snippet manifest/part paths, per-source train/val group assignment, counts and checksums.
- `model.json`: `schema_version`, Model ID, readable label, family, Dataset ID/reference, seed, resolved settings, ordered feature/transform schema, actual metrics (including nullable unsupported values), produced file paths/checksums and provenance.
- `run_state.json`: `run_id`, kind, phase/status, input reservations, monotonic progress stage, bounded log references and output reference only after verified publication.

Schemas require explicit compatible version readers. A missing/unsupported schema is an actionable error, not permission to guess. Do not add a database or independent user-configurable artifact roots.

## 3. Bounded I/O and large Collections

A Scan must run off the GUI event loop. First scan: one bounded directory listing per input folder and one bounded header read for each encountered WAV; parse positive filenames in the same traversal. Avoid a full-audio decode, hashing every recording or copying input WAVs just to show an overview. Display file counts, progress, cancel and first relevant issues while work proceeds. Reopen: load a small manifest, compare current file inventory/stat fingerprints; reread changed/new WAV headers only, expunge removed facts and atomically rewrite affected partitions. Mutated inputs **invalidate** ready-to-build state until revalidated. Just before Dataset Build, revalidate referenced source facts and hashes as required by the reproducibility contract.

Start with JSONL partitions of at most **10,000 rows or 16 MiB each**, whichever first; cap each WAV/header read, open file descriptors, audio chunk, progress update and Qt table page. Record benchmarks on generated large-index fixtures; do not claim constant-time directory freshness. Use a lazy `QAbstractItemModel`/`alp-ui` DataTable model rather than materializing millions of Qt rows/widgets. Limit concurrent I/O and avoid scanning symlink trees. File fingerprint `size + mtime_ns + frame/header data` is a freshness heuristic, not a proof of byte identity; targeted streamed hashes may be recorded during scientific use.

Use a typed **scan result** handoff (discovered inventory, metadata, validation issues, fingerprints, cancel token/version) so GUI, persistence and Dataset Build do not independently reparse whole inputs. Canonical error reports include a relative path, a stable issue code and a correction. Partial or failed scans never publish a valid cache.

## 4. Execution, reservations and publication

**Scan** is a background I/O activity, separately cancellable; **Dataset Build/Training** are scientific Runs. Application Controller owns one Active Run; Worker runs separately via `QProcess`, launched from the application's current executable/environment. In development use the environment's interpreter with `-m alpaca_desktop --worker ...` (entry contract to implement); in packaged builds use the bundled executable `--worker ...`. Pass structured config/paths (not shell strings) and isolate settings when testing. The Worker cannot import or manipulate GUI widgets. Stage outputs on the same destination filesystem, verify manifests, referenced files/metrics/schema, then use an exclusive, lock-protected no-clobber publication into a previously absent ID directory (with native filesystem-specific tests). Crash/cancel/underfill never creates an apparently completed Dataset/Model.

Persist Run State at every meaningful lifecycle change using same-directory atomic replacement. Run completion requires **both** terminal state and validated output; reconcile orphaned/published-but-interrupted cases safely on startup. Cancellation is explicit and bounded. Worker progress is rate-limited and structured; check child exit code/log and actual output, not a Qt signal alone. No background daemon, queue, remote execution or auto-retry.

Use reservations keyed by stable Collection/Dataset ID and paths: refuse second Run, conflicting delete, relocation/rebind of active inputs and any write to active output. Read-only browsing can proceed. Locks must work with macOS filesystem behavior and be tested on native Windows before Windows distribution. Explicit Dataset deletion is blocked during a dependent Active Run, never recursively removes Models and must not mutate recording/positive inputs. Atomic staging cleanup is idempotent and only within `.alpaca/`.

## 5. Libraries and portability

- **UI:** local sibling `../alp-ui` native PySide6 Qt Widgets package, locally built/installed. Use its public components; QAbstractItemModel, file dialogs, threading/QProcess and navigation remain app responsibilities. No monkeypatching library internals or fetching a similarly named package as a replacement. See [`specs/README.md`](specs/README.md).
- **Scientific ownership:** `../bioacoustics-dl-toolbox` supplies reusable bounded audio extraction (after Spec 04.5), CNN training/model/checkpoint capabilities and any verified reusable scientific helpers. `../alpaca-pipelines` is a behavior/source reference for orchestration and RF features, **not** an automatic runtime dependency. Correct upstream library defects there, rather than leaving duplicated algorithms in Trainer. See [source map](agent/SOURCE_MAP.md). The Dataset/Model manifest schemas above are native contracts; a pipeline manifest or historical checkpoint is not automatically compatible.
- **Platforms:** macOS is the active development/integration platform. Use `pathlib`, portable relative segments, executable discovery from the actual install, explicit WAV decode decisions and resource-safe shutdown. Windows-native filesystem case/lock, paths, QProcess, audio decoding, local `alp-ui` assets and packaged startup must be tested on a real Windows runner **before distribution**.
- **Tests:** pure `UT-*` for rule decisions, actual `IT-*` for persistence, Qt, Worker, training and packaging. See the two indexes and `TD-*` class guide; documentation never implies tests have already passed.
