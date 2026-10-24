# Review principles — Trainer specs and implementation

**Mandatory UI acceptance:** [Prototype fidelity gate](../design/PROTOTYPE_ACCEPTANCE.md) applies to every spec that changes visible UI (including packaged installers). A missing screen/state, rearranged primary action, wrong navigation, unlabeled visual deviation or absent native screenshot evidence blocks that spec; using `alp-ui` alone is not proof of parity. Read only the active spec’s screen rows.

These are **operational checks**, not a demand for generic infrastructure. Apply only to task-owning seam; do not build unneeded abstractions to satisfy a checklist. Start from [`../GLOSSARY.md`](../GLOSSARY.md), [`../ARCHITECTURE.md`](../ARCHITECTURE.md), active spec and owned tests.

## 1. Identify authoritative producer and consumer

For each requested field, ask: **What raw input produces it? Which stage derives it? Who owns persisted copy? Who consumes it? What invalidates it?** Example: WAV header frame count is a Source Recording fact in Collection Metadata; positive source-time interval is derived from positive filename; a Dataset owns its *snapshotted* input fingerprint and materialized Snippet reference; Model owns derived feature schema/metrics. Do not store a field on an unrelated global object because it's convenient for one UI panel. Scientific artifact and transient UI view are different authority levels.

Before adding types/helpers, search existing source and sibling `alpaca-pipelines` for real reusable code. An algorithm moved between wrappers should delegate to its authoritative implementation unless a measured/tested replacement is intended. A Python method made public solely so a test can call it is usually the wrong seam.

## 2. Preserve the Collection trust boundary

User-selected paths and filenames are untrusted input. Parse/canonicalize once with explicit reject rules, **then** resolve relative references under the approved Collection root; cache hits, rebinds and Worker launch must enforce identical containment/permissions checks. Normalize representation for stable identity/collision detection but never silently merge two distinct files into one row. Detect Unicode NFC/casefold and Windows-reserved names without pretending macOS and Windows filesystem behavior is identical. Clarify missing versus empty, absent versus inaccessible and unchanged versus stale.

Define the filename grammar and millisecond units at a single parser/encoder boundary; reject precision/overflow mistakes at that boundary. A `start_ms` in original source time is different from an index into a cropped WAV. Trust in timestamp metadata is **not waveform verification**. Any claimed content match needs its own explicit algorithm and test evidence.

## 3. Stage once, pass canonical handoff

For a multistage operation choose one typed handoff object with versioned validated facts: Scan → publication; Build config/source inventory → selected windows/materialized Snippets/Splits; Train input manifest → family transform/Model. Avoid doing a second directory parse or full-source read because the downstream step lost the first stage's output. State byte/row/file-descriptor budgets and enforce them at actual I/O seams. Start with ≤10,000 JSONL rows or 16 MiB/partition and bounded WAV seek/chunk reads; relax only with profiling evidence.

A **scientific Run is not the same as a Scan**. Worker writes and verifies in private staging on the destination volume, then makes a new immutable directory visible atomically. Separately persist Run State and reconcile it with output validity, including crash/cancellation. No overwrite, implicit resume or optimistic success based on a process exit signal alone.

## 4. Keep domain/computation/GUI responsibilities narrow

`domain` computes pure parsers, intervals, mining constraints, Split plan/config checks. `computation` loads WAV frames and trains; `workflows` orchestrates scientific outputs; `persistence` publishes and reloads; `application` owns background scan and one Active Run; `gui` renders and navigates. New cross-layer data contract belongs with the interface owner and uses meaningful names/units. Avoid duplicating logic in Qt callbacks, Worker, and test fixtures.

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

## Implementing-agent PR checklist

- [ ] Search current project and relevant `alpaca-pipelines` source before adding code; cite inspected versions/signatures in PR.
- [ ] Use glossary terms and canonical units across code/manifest/UI/test.
- [ ] Enforce all invariants at the source/output boundary and cache authorization equivalence.
- [ ] Record measured file-read/memory/page budget where I/O changes.
- [ ] Verify stage → validated immutable publish, failure recovery, input unchanged and no silent overwrite.
- [ ] Run focused `UT-*` and real macOS `IT-*`, audit exact IDs with `scripts/audit_test_ids.py`, report actual commands/results and uncovered/native-deferred gaps.
- [ ] Maintain generated/fixed fixture policy, SHA-256/LFS provenance and the active spec in same PR.
- [ ] For UX changes, persist native app screenshots and a prototype + `alp-ui` Showcase parity ledger, then update README with **truthful** native shots and `.venv` run commands.
- [ ] Deliver a real branch/commit SHA with clean Git status, verified ignored private files and Git LFS; see [`GIT_DELIVERY.md`](GIT_DELIVERY.md).

## Context efficiency and release obligations

- Read `docs/agent/ROUTING.md`, **one active spec** and only the `UT-*`/`IT-*`/`TD-*` rows implicated by the work; use targeted searches rather than reading every Markdown or whole sibling repo. In first session, implement spec 01 only.
- For GUI specs compare native Qt screenshots/interaction with bundled browser prototype and local `alp-ui` Showcase; use public `FolderPicker`, `HelpHint`, `Plot` as specified. Treat prototype fake science as illustrative only.
- All scientific test-data changes update `tests/data/README.md` + `SHA256SUMS`, `FX-*` registry, Git LFS binary filters and affected case IDs. Never confuse synthetic WAV example with HPC-sourced provenance; use read-only private helper only on an approved gap.
- Design frozen app/Worker launch for Mac `.dmg` and Windows `.exe` from the outset; only specs 06/07 establish sign/install/clean-machine gates. Never claim an installer exists because a packaging spec exists.
