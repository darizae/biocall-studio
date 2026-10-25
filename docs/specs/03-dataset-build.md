# 03 — Dataset Build, protected Negative Mining and Splits

**Scoped references:** [Dataset rules](../models/WORKFLOW_RULES.md) §2; [binary labels](../science/BINARY_CLASSIFICATION_CONTRACT.md); [dataset UX row](../design/UX_PARITY_MATRIX.md); [indexed cases](../UNIT_TESTING.md) `UT-DB-*` / [integration](../INTEGRATION_TEST_BEHAVIORS.md) `IT-DB-*`. Use [source map](../agent/SOURCE_MAP.md) only to inspect a relevant upstream implementation.

## User behavior

From a **currently validated Collection**, configure participating Source Recordings, negative mining count/seed/margin and train/val source-grouped ratio; review estimated target/noise counts and create an immutable Dataset. Dataset page shows actual materialized Snippet counts, split membership, settings and provenance, plus **Train Model** and explicit **Delete**. A build that cannot find eligible negative windows explains why and publishes no Dataset.

## Scientific contracts

1. Revalidate selected input metadata/fingerprints and source containment at the start of Build. Use the Collection-derived `target` Annotations and selected sources, never interpret positive WAVs as directly reusable Dataset Snippets. Input WAVs remain read-only.
2. Form protected source-time union of positives with margin clipped to recording bounds. Sample noise windows only outside protected intervals; one deterministic seed/attempt budget, record availability and report underfill without silently lowering requested numbers.
3. Materialize `target` and `noise` Snippet WAVs using bounded seek/chunk reads of the Source Recording and an explicitly versioned channel/sample conversion policy. Record original source-time intervals, transformations, label, source fingerprint, producing Positive Example reference (targets) and seed/build config. **Binary single-label invariant:** every Snippet has exactly one of `target` or `noise` (never a class list or multiple labels), following [BINARY_CLASSIFICATION_CONTRACT](../science/BINARY_CLASSIFICATION_CONTRACT.md). Preserve a stable two-class mapping for later CNN/RF use.
4. Allocate `train` and `val` **by Source Recording** and prevent leakage; reject or honestly explain impossible class/split coverage. Manifest and split CSVs are immutable after publication and use path-contained portable refs.
5. Use workflow → staged output → verified manifest/Snippet/Split → exclusive publish. Integrate with one Active Run and Worker of spec 04 by a common handoff; do not create an alternate production “sync build” lifecycle.
6. Dataset deletion is explicit, checks input reservations, never removes Models or user input audio, and reports resulting provenance limitations if a dependent Model remains.

## Failure/correction paths

Change in source during Build, insufficient eligible noise, invalid split, missing WAV, symlink escape, write/codec/disk error, cancellation and output ID collision all leave **no completed Dataset** and preserve input bytes and any existing published Datasets. Repeating same config/seed over same inputs yields equivalent audio, labels and grouping even if IDs differ; changed settings produce a separate Dataset.

## UI and source-data acceptance

Use `alp-ui` `NumberInput`, `SelectInput`, `HelpHint` for margin, counts, seed and split explanation, with source selection via `DataTable` Qt model. The prototype Builder preview is the content/interaction reference, not scientific computation. Consult `../alpaca-pipelines` scientific source per `docs/agent/SOURCE_MAP.md` **only where there is a relevant algorithm**; record source SHA and adaptation rules. Exercise a tiny real synthetic Collection (checked-in Git LFS fixture if present; otherwise generate in a temp directory) before adding an anonymized HPC exemplar through the explicit staged approval/fixture register.

## Blocking prototype parity (native UI)

**`IT-DB-005`:** Match the actual prototype Builder interaction (`builder-preview.png`, `app.js`) including recording selection, grouped settings, labels/hints, source preview, target/noise estimate, underfill/disabled status, primary Build action and Dataset list/detail navigation. Do not implement a generic wizard or hide the prototype's breakdowns. Exercise real config changes, invalid/no-space cases, source-grouped splits and completed Dataset views with native `alp-ui` controls and `pytest-qt`; capture `spec-03-native/` views from the [Prototype acceptance](../design/PROTOTYPE_ACCEPTANCE.md) inventory. Keep scientific outcomes real rather than imitating JS demo values. Unapproved parity gaps block the spec. Any required fixture can be generated locally if omitted from ZIP.

## Tests / exit

- Unit: `UT-DB-001`…`UT-DB-004`, `TD-MINE`, `TD-SPLIT`.
- Integration: `IT-DB-001`…`IT-DB-004`, real generated distinguishable WAV windows, protected/noise nonintersection, actual Snippet bytes and split CSV, staged publication, reopen, deletion noncascade, failure/underfill. When delivered with spec 04, execute through real Worker; until then report process boundary pending rather than claiming `IT-RUN-*` covered.

## Implementation closeout — 25 October 2026

**Complete and ready for owner review.** The implementation uses Qt-free domain decisions,
bounded chunked PCM extraction, verified staged publication, a typed QProcess handoff and native
Builder/list/detail views. `UT-DB-001`…`UT-DB-004` and `IT-DB-001`…`IT-DB-005` are asserting tests,
not planned IDs. TDD began with missing-module failures for the new Dataset cases before the domain,
workflow, persistence and UI seams were added.

The scientific review used adjacent `alpaca-pipelines` commit
`91af5287dc18313f88902dc9696e8756274736b3`. The implementation adapts its seeded bounded-mining
intent while adding the Trainer's protected integer-millisecond unions, selected-source allocation,
nonoverlap, grouped Splits, bounded PCM I/O and portable verification. Its orchestration and schemas
are not reused automatically.

Verified commands on native macOS 26.6.2 arm64, Python 3.12.7 and Qt 6.11.2:

```text
.venv/bin/pytest -q                                      46 passed
.venv/bin/ruff check src tests scripts                  passed
.venv/bin/python scripts/audit_test_ids.py              passed
.venv/bin/python scripts/check_fixtures.py              passed
.venv/bin/python scripts/verify_handoff.py              passed
git lfs fsck                                             passed
unset QT_QPA_PLATFORM; .venv/bin/python -u scripts/capture_spec03_screenshots.py
                                                           six Cocoa captures reviewed
```

The native screenshots and six-dimension comparison are recorded in
[`../design/evidence/README.md`](../design/evidence/README.md). `IT-DB-005` executes the actual
QProcess Build and verifies the transient one-build-at-a-time UI boundary. Spec 04 still owns
persisted Run records, Run navigation, cancellation/recovery and reservation across all scientific
Runs; this closeout makes no `IT-RUN-*` claim. Native Windows and packaged-app qualification remain
their later owner specs.
