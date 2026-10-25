# Review principles — Trainer specs and implementation

These are **operational checks**, not a demand for generic infrastructure. Apply only to task-owning seam; do not build unneeded abstractions to satisfy a checklist. For a new cross-cutting specification, consult only affected terms in the [glossary](../GLOSSARY.md), boundaries in [architecture](../ARCHITECTURE.md), and owned tests.

## 1. Identify authoritative producer and consumer

For each requested field, ask: **What raw input produces it? Which stage derives it? Who owns persisted copy? Who consumes it? What invalidates it?** Example: WAV header frame count is a Source Recording fact in Collection Metadata; positive source-time interval is derived from positive filename; a Dataset owns its *snapshotted* input fingerprint and materialized Snippet reference; Model owns derived feature schema/metrics. Do not store a field on an unrelated global object because it's convenient for one UI panel. Scientific artifact and transient UI view are different authority levels.

Before adding types/helpers, search existing source and sibling `alpaca-pipelines` for real reusable code. An algorithm moved between wrappers should delegate to its authoritative implementation unless a measured/tested replacement is intended. A Python method made public solely so a test can call it is usually the wrong seam.

## 2. Preserve the Collection trust boundary

User-selected paths and filenames are untrusted input. Parse/canonicalize once with explicit reject rules, **then** resolve relative references under the approved Collection root; cache hits, rebinds and Worker launch must enforce identical containment/permissions checks. Normalize representation for stable identity/collision detection but never silently merge two distinct files into one row. Detect Unicode NFC/casefold and Windows-reserved names without pretending macOS and Windows filesystem behavior is identical. Clarify missing versus empty, absent versus inaccessible and unchanged versus stale.

Define the filename grammar and millisecond units at a single parser/encoder boundary; reject precision/overflow mistakes at that boundary. A `start_ms` in original source time is different from an index into a cropped WAV. Trust in timestamp metadata is **not waveform verification**. Any claimed content match needs its own explicit algorithm and test evidence.

## 3. Stage once, pass canonical handoff

For a multistage operation choose one typed handoff object with versioned validated facts: Scan → publication; Build config/source inventory → selected windows/materialized Snippets/Splits; Train input manifest → family transform/Model. Avoid doing a second directory parse or full-source read because the downstream step lost the first stage's output. State byte/row/file-descriptor budgets and enforce them at actual I/O seams. Start with ≤10,000 JSONL rows or 16 MiB/partition and bounded WAV seek/chunk reads; relax only with profiling evidence.

A **scientific Run is not the same as a Scan**. Worker writes and verifies in private staging on the destination volume, then makes a new immutable directory visible atomically. Separately persist Run State and reconcile it with output validity, including crash/cancellation. No overwrite, implicit resume or optimistic success based on a process exit signal alone.

## 4. Keep scientific libraries, domain and UI responsibilities narrow

`domain` computes pure parsers, intervals, mining constraints, Split plan/config checks. Reusable WAV extraction and CNN algorithms belong in `../bioacoustics-dl-toolbox` after Spec 04.5; `workflows` adapt verified scientific libraries and orchestrate app-specific outputs; `persistence` publishes and reloads; `application` owns background scan and one Active Run; `gui` renders and navigates. New cross-layer data contract belongs with the interface owner and uses meaningful names/units. Avoid duplicating logic in Qt callbacks, Worker, and test fixtures.

Do not add repositories, ORM layers, HTTP, web endpoints, database migrations, distributed job/scheduler infrastructure, concurrency queues or decorative compatibility adapters. Specialized backend conventions may inform a principle but do **not** become app implementation requirements. Extract a shared helper on the second real consumer unless strong correctness evidence requires earlier sharing.

## 5. Scientific honesty and reuse

`alpaca-pipelines` provides candidates for reliable source audio reading, negative-window selection, sample/channel transforms, CNN and RF feature extraction/classifier behavior. Inspect the current exact functions/tests before using them; document source version and any changed representation, metric, label or feature-order assumptions. Train/val grouping must prevent source leakage. Noise mined from unlabeled intervals is only a candidate negative. Handle undefined metrics as undefined. A model file and `model.json` are distinct and both must be validated to publish/reopen.

## 6. Test at the owning seam

- Pure parsing, frame arithmetic, interval merging, seeded allocation, Split assignment, config and metric choice → `UT-*` direct pytest.
- Real selected folder, WAV loader, cache freshness, staging and Snippet bytes → workflow `IT-*` with generated actual WAVs.
- Real Qt responsive Scan, file/dialog cancellation and table paging → desktop `IT-*` with `pytest-qt`.
- Real QProcess launch, Active Run, cancel/recovery and package Worker → process/packaged `IT-*`.
- Actual CPU CNN and RF Models from one Dataset → scientific integration, not stubs.

Read [`../UNIT_TESTING.md`](../UNIT_TESTING.md) before declaring a case integration. Pick `TD-*` data classes from [`../INTEGRATION_TEST_DATA.md`](../INTEGRATION_TEST_DATA.md), then exact owned `UT-*`/`IT-*` IDs. Each covering test's **test-function docstring** repeats exact IDs and asserts **all** required side effects and non-mutation; only passing appropriate native execution supports coverage. Never infer coverage from a planning table, scaffolding UI or HTML simulation. Missing authorized fixtures/HPC is a blocker, not an excuse to weaken tests. Keep data revisions, case indexes, spec and code synchronized.

## Spec-author checklist

- [ ] User action, observable output, implementation owner and **out-of-scope** effects are explicit.
- [ ] Every source/derived field names raw origin, stage, persisted owner, consumer, units, cardinality and freshness check.
- [ ] Trusted vs untrusted path/filename inputs, parse order, symlink/collision handling and read budgets are named.
- [ ] The single handoff object between scan/build/train stages is defined and reused, not reparsed.
- [ ] Failure/cancel/collision and unchanged input artifacts are specified, including recovery.
- [ ] Scientific invariants are grounded in inspected code or deliberately specified with measurable tests.
- [ ] Unit behaviors are distinguished from real integration seams; IDs and `TD-*` classes are linked.
- [ ] New UI Components use actual local `alp-ui` API, not imagined library exports.
- [ ] No unowned dependencies, artifact formats, user-facing workflows or compatibility assumptions slipped into scope.

For ordinary implementation, follow the [active spec](ROUTING.md), exact [test indexes](../INTEGRATION_TESTING.md) and [Git delivery](GIT_DELIVERY.md); do not load this checklist as a mandatory startup reference. Scientific upstream modifications follow the [toolbox workflow](UPSTREAM_TOOLBOX_WORKFLOW.md) only if justified.
