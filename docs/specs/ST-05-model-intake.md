# ST-05 — Trusted CNN/RF Model intake and scientific compatibility

**Historical branch:** `detect-st05-model-intake`. **Predecessor:** ST-04 inventory contract. **Successor:** ST-06. **Status:** implemented and included in the current merged `main` source baseline; **no new-audio prediction belongs to this stage**.

## Scope and ownership

Detect reads existing immutable **Train-published** Model directories as a consumer; no Train export refactor without a proven incompatibility. Support CNN and RF family-specific structural validation, read-only manifest/binary checksum verification, portable path containment, trust decision, local Model selection and native compatible/incompatible/missing/loading states. `model.json` is not proof of a working inference transform. No scoring, no inferencing Run, no RF refinement.

Inspect actual `src/biocall_studio/train/persistence/models.py`, [Model export contract](../science/MODEL_EXPORT_CONTRACT.md), [binary class contract](../science/BINARY_CLASSIFICATION_CONTRACT.md) and **current source/tests** in `../bioacoustics-dl-toolbox` (direct CNN library); inspect only implicated RF preprocessing/estimator source in `../alpaca-pipelines`. Record checked-out SHAs, installed module `__file__`, version, serialization/torch/joblib loader and test vectors. The pipeline's copy of `bioacoustics_dl_toolbox` must not accidentally shadow the direct package. Missing checkout/source is an explicit scientific blocker, not a guessed adapter.

## Contract and handoff

`ModelSnapshot`: `model_id`, `family`, manifest version, immutable verified binary+manifest SHA-256, exact two-class `target`/`noise` mapping, positive-class output/index or RF probability column, required sample rate/channel/window/normalization/transform order, ordered RF feature names/schema, loader/runtime/source version and `trusted` compatibility state + reason. Freeze full verified Model reference for ST-07/09 and recheck immediately before Worker use. Separate `valid structure`, `runtime loadable`, and `numerically prediction-compatible`; do not label the latter passed until ST-07 or ST-09 reference parity. No arbitrary untrusted Torch/joblib deserialization: only explicitly trusted locally produced Models after containment/checksum and format checks.

**Research ledger in stage handoff:** source file:function + upstream SHA, observed import origin, exact sample/channel/resampling and spectrogram/window semantics, CNN output/logit/probability class order and RF preprocessing/feature order/estimator class order. Record each unresolved decision as blocking the consuming inference stage; do not invent default thresholds/calibration or promise any binary is universally safe to load.

## Native parity

`#detect/setup` independently reflects compatible, loading, empty, missing and incompatible Models and a selected folder. No runnable Detect action before ST-07 and all prerequisites valid. Actionable short error and small `HelpHint` for technical compatibility; no developer stack traces or unsupported feature switches.

## TDD and boundary verification

- `UT-DET-007` — immutable manifest schema/checksum/class mapping, family-specific required fields and rejected mismatch.
- `UT-DET-008` — trusted artifact policy, safe path/version/import semantics; binary not deserialized on untrusted/malformed input.
- `UT-DET-009` — precise compatibility state/reason and normalized typed handoff; unproven numerical parity remains flagged.
- `IT-DET-006` — trusted genuinely Train-exported CNN and RF Models load/inspect in fresh process via verified installed toolbox, without source-tree runtime dependency (`TD-EXPORT`, `TD-TRAIN`).
- `IT-DET-007` — missing/corrupt/checksum-swapped binary, extra class, feature-order mismatch, unsupported runtime, unsafe path, explicit untrusted user artifact denied (`TD-EXPORT`, `TD-FAIL`, `TD-PATH`).
- `IT-DET-008` — real Qt Model selection/reopen states and readiness gating without Worker launch (`TD-UI`, `TD-EXPORT`).

Tests first and at real trust/loader boundaries; scoped existing Model structural tests may be reused as regressions, not relabeled as prediction parity. Run full feasible ordinary suites before commit. A missing upstream or actual Models block relevant integration cases; do not substitute synthetic manifest-only success.

## Upstream and gate

A missing scientific API belongs in the owning toolbox (or verified RF library): use a dedicated feature/fix branch, upstream failing test, commit, verify import provenance, then downstream integration. For a missing `alp-ui` component use an independent UI library branch and consumer regression. Follow [upstream workflow](../agent/UPSTREAM_TOOLBOX_WORKFLOW.md) and [Git delivery](../agent/GIT_DELIVERY.md); integrate locally after review, **never push**. **Close when** both Model families have trustworthy structural intake, source-inspection evidence, clear unresolved inference questions, safe UX and indexed tests; ST-07/09 remain scientific gates.
