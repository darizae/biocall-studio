# 03 — Dataset Build, protected Negative Mining and Splits

## User behavior

From a **currently validated Collection**, configure participating Source Recordings, negative mining count/seed/margin and train/val source-grouped ratio; review estimated target/noise counts and create an immutable Dataset. Dataset page shows actual materialized Snippet counts, split membership, settings and provenance, plus **Train Model** and explicit **Delete**. A build that cannot find eligible negative windows explains why and publishes no Dataset.

## Scientific contracts

1. Revalidate selected input metadata/fingerprints and source containment at the start of Build. Use the Collection-derived `target` Annotations and selected sources, never interpret positive WAVs as directly reusable Dataset Snippets. Input WAVs remain read-only.
2. Form protected source-time union of positives with margin clipped to recording bounds. Sample noise windows only outside protected intervals; one deterministic seed/attempt budget, record availability and report underfill without silently lowering requested numbers.
3. Materialize `target` and `noise` Snippet WAVs using bounded seek/chunk reads of the Source Recording and an explicitly versioned channel/sample conversion policy. Record original source-time intervals, transformations, label, source fingerprint, producing Positive Example reference (targets) and seed/build config.
4. Allocate `train` and `val` **by Source Recording** and prevent leakage; reject or honestly explain impossible class/split coverage. Manifest and split CSVs are immutable after publication and use path-contained portable refs.
5. Use workflow → staged output → verified manifest/Snippet/Split → exclusive publish. Integrate with one Active Run and Worker of spec 04 by a common handoff; do not create an alternate production “sync build” lifecycle.
6. Dataset deletion is explicit, checks input reservations, never removes Models or user input audio, and reports resulting provenance limitations if a dependent Model remains.

## Failure/correction paths

Change in source during Build, insufficient eligible noise, invalid split, missing WAV, symlink escape, write/codec/disk error, cancellation and output ID collision all leave **no completed Dataset** and preserve input bytes and any existing published Datasets. Repeating same config/seed over same inputs yields equivalent audio, labels and grouping even if IDs differ; changed settings produce a separate Dataset.

## UI and source-data acceptance

Use `alp-ui` `NumberInput`, `SelectInput`, `HelpHint` for margin, counts, seed and split explanation, with source selection via `DataTable` Qt model. The prototype Builder preview is the content/interaction reference, not scientific computation. Consult `../alpaca-pipelines` scientific source per `docs/agent/SOURCE_MAP.md` **only where there is a relevant algorithm**; record source SHA and adaptation rules. Exercise tiny checked-in synthetic Collection before adding an anonymized HPC exemplar through the explicit staged approval/fixture register.

## Tests / exit

- Unit: `UT-DB-001`…`UT-DB-004`, `TD-MINE`, `TD-SPLIT`.
- Integration: `IT-DB-001`…`IT-DB-004`, real generated distinguishable WAV windows, protected/noise nonintersection, actual Snippet bytes and split CSV, staged publication, reopen, deletion noncascade, failure/underfill. When delivered with spec 04, execute through real Worker; until then report process boundary pending rather than claiming `IT-RUN-*` covered.
