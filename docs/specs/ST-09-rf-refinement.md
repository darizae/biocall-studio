# ST-09 — Optional RF refinement and Result lineage

**Historical branch:** `detect-st09-rf-refinement`. **Predecessors:** ST-05 RF Model intake, ST-07 CNN Result, ST-08 Results UX. **Successor:** ST-10. **Status:** implemented and included in the current merged `main` source baseline.

## Scope and ownership

RF evaluates **only existing CNN candidate intervals** using the source WAV and a compatible trained RF Model. Produce an additional immutable metadata-only Result; never replace, rename or delete the original CNN Result and never scan entire recordings as a standalone RF detector. Own feature extraction invocation, target probability-column mapping, classification, `accepted | rejected | unscored`, lineage and native original/refined comparison.

Inspect current RF feature/preprocessing source and test vectors in actual `../alpaca-pipelines` and/or scientifically authoritative `../bioacoustics-dl-toolbox` (only verified APIs). Verify sample-rate/channel, min-duration padding, filter/MFCC/feature order, dtype, handling of NaN/inf, `estimator.classes_` and `predict_proba` column; no invented RF probability policy. If the authoritative algorithm lacks a callable API, implement/test/commit in owning upstream repository on its own branch and retest installed version before downstream consumption.

## Contract and handoff

`DerivedResult` (versioned): new Result ID/digest, original parent Result ID/digest, source Collection/Run, RF Model ID+digest, frozen settings/backend revision; for **each** parent candidate stable ID, RF score/label or explicit `unscored` reason, preserving original recording times and CNN score. Parent remains available and unmodified, including after a failed refinement. Revalidate parent, Model and recording fingerprints before scoring; source intervals retain frame/time provenance and are never recomputed from clipped snippet filenames.

Short/missing/stale/unsupported input yields a defined unscored decision or an explicit failed Run according to verified science policy, **never silently rejected**. Worker cancel, partial feature exceptions or publication failure do not create a partial child masquerading as success. Distinguish valid `unscored` outcome from process failure and user-visible summary accordingly.

## Native parity

`#detect/results` includes optional compatible RF action, clear incompatibility state, original/refined selector and a stable selection/interval view in both. Researcher-readable Accepted/Rejected/Could not assess, contextual `HelpHint` for why, and specific Model/provenance. No generic second "Detect all recordings" RF action and no extra score captions without definitions. Native QT normal/compact/keyboard evidence with genuine Results.

## TDD and boundary verification

- `UT-DET-018` — exact ordered RF feature schema and class/probability-column validation; reject mismatch/nonfinite values.
- `UT-DET-019` — per-candidate accepted/rejected/unscored status and short/stale/error decisions.
- `UT-DET-020` — immutable parent→child lineage, candidate identity, time/provenance and checksum rules.
- `IT-DET-017` — genuine WAV segments and trusted RF Model, reference feature-vector/probability parity; original/derived persisted independently and native selection works (`TD-TRAIN`, `TD-EXPORT`, `TD-WAV`, `TD-UI`).
- `IT-DET-018` — wrong feature order/Model, missing/short/stale recording, cancelled/crashed Worker and atomic failure; original Result bytes unchanged (`TD-FAIL`, `TD-RUN`, `TD-WAV`).

Test scientific feature vectors/probabilities against inspected current upstream, not fixture-only mock success. Full feasible ordinary suites before stage commit; no corpus export or whole-Studio E2E here.

## Gate

Upstream/source numeric RF parity, truthful unscored handling, immutable linked Results, real Worker cancellation and native prototype comparison reviewed. Integrate locally to `detect`, then ST-10; never push.
