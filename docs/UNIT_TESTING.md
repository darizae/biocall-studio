# Unit testing — focused rule index

Use fast deterministic, Qt-free tests for pure behaviors: filename/path parsers, duration and frame arithmetic, exclusion-window math, Split grouping, configuration validation and state transitions. A parser test does not prove real WAV I/O, cache persistence, GUI responsiveness, QProcess or Training. `tests/unit/` is the initial CI suite; it must not need actual HPC, large LFS payloads or a running GUI.

## Naming and coverage

An indexed case appears **exactly** in the asserting test function docstring, e.g. `"""Case: UT-COL-001."""`. Table rows below define intended cases, **not completion**. None is covered merely by being listed or by existing in the merged baseline. A test counts as covered only after the exact behavior is asserted and an applicable run passes. Do not renumber an existing ID to reuse it for different behavior. Add edge variants under the same case where the invariant is unchanged; add an ID when the behavior is materially distinct.

| Case ID | Pure behavior and failure contrasts | Data class | Spec |
|---|---|---|---|
| `UT-PATH-001` | Portable relative segments reject absolute/traversal, invalid separators, reserved OS names | TD-PATH | 01 |
| `UT-PATH-002` | Unicode NFC/casefold filename collisions cannot silently resolve an identity | TD-PATH | 01 |
| `UT-CLI-001` | Version/help and invalid-option handling complete without importing optional Qt/`alp-ui`; real GUI startup remains owned by `IT-UI-001` and uses isolated Application Settings | TD-UI | 01, 05f |
| `UT-CLI-002` | Canonical `biocall-studio` argument parsing and private Worker dispatch accept only the five REV-01 modes; missing/invalid Worker arguments fail without GUI import and version lookup uses the unified distribution. | TD-UI, TD-RUN | REV-01 |
| `UT-DEV-001` | Repository test-runner modes force invisible offscreen Qt for ordinary/quick runs, keep package exclusion explicit, and refuse visible Cocoa execution or marker overrides without acknowledgement. | TD-UI | Test infrastructure |
| `UT-SIZE-001` | Exact PCM/WAV/TSV byte arithmetic, binary unit formatting/round-up, overflow and unsupported formats. | TD-WAV, TD-FAIL | [REV-05 proposed](specs/manual_revision_specs/REV-05-output-size-preflight.md) |
| `UT-SIZE-002` | Train/Detect size adapters: verified exact vs ranged/unknown estimates, historical-cohort confidence and no fake precision. | TD-CACHE, TD-RUN | [REV-05 proposed](specs/manual_revision_specs/REV-05-output-size-preflight.md) |
| `UT-SIZE-003` | Per-volume free/peak/reserve decisions, stale inputs, unknown capacity and confirmation policy. | TD-PATH, TD-FAIL | [REV-05 proposed](specs/manual_revision_specs/REV-05-output-size-preflight.md) |
| `UT-STU-001` | Pure workspace-route policy: Studio is the startup route; Train/Detect/Review and return transitions are explicit; unknown routes fail closed; navigation decisions do not mutate Train context or imply runnable Detect features. | TD-UI | ST-02 |
| `UT-DET-001` | unique identity, schema migration/rejection, app-data ownership and root-reference serialization (no original path in exported metadata). | TD-PATH, TD-CACHE | ST-03 |
| `UT-DET-002` | valid/missing/inaccessible/changed/relink state decisions, confirmation and stale inventory invalidation; reject unrelated-root takeover. | TD-PATH, TD-CACHE | ST-03 |
| `UT-DET-003` | containment, Unicode/casefold/Windows-reserved path policy, atomic update and recovery decisions. | TD-PATH, TD-CACHE | ST-03 |
| `UT-DET-004` | inclusion precedence, generated-data exclusions, undecided versus invalid, deterministic decisions and count aggregation. | TD-WAV, TD-PATH | ST-04 |
| `UT-DET-005` | normalized identity, traversal/symlink/reparse and duplicate/hardlink/casefold collisions cannot silently collapse rows. | TD-WAV, TD-PATH | ST-04 |
| `UT-DET-006` | header/freshness interpretation, add/remove/replace, cancellation and snapshot validation. | TD-WAV, TD-PATH | ST-04 |
| `UT-DET-007` | immutable manifest schema/checksum/class mapping, family-specific required fields and rejected mismatch. | TD-EXPORT, TD-TRAIN | ST-05 |
| `UT-DET-008` | trusted artifact policy, safe path/version/import semantics; binary not deserialized on untrusted/malformed input. | TD-EXPORT, TD-TRAIN | ST-05 |
| `UT-DET-009` | precise compatibility state/reason and normalized typed handoff; unproven numerical parity remains flagged. | TD-EXPORT, TD-TRAIN | ST-05 |
| `UT-DET-010` | state machine, Run input freeze, one-Active-Run reservation and terminal transitions. | TD-RUN, TD-FAIL | ST-06 |
| `UT-DET-011` | cancellation, crash, receipt/staging reconciliation and orphan recovery decisions. | TD-RUN, TD-FAIL | ST-06 |
| `UT-DET-012` | bounded diagnostics schema, privacy allowlist, rotation/read/symlink policy. | TD-RUN, TD-FAIL | ST-06 |
| `UT-DET-013` | exact source-frame/window/hop/overlap arithmetic, resample/padding boundary and invalid config rejection. | TD-WAV, TD-EXPORT | ST-07 |
| `UT-DET-014` | target score/threshold semantics, interval merge/clamp, non-finite or ambiguous outputs fail. | TD-WAV, TD-EXPORT | ST-07 |
| `UT-DET-015` | candidate source timestamps, deterministic IDs, immutable Result schema, per-file status validation. | TD-WAV, TD-EXPORT | ST-07 |
| `UT-DET-016` | immutable Result-to-view projection, stable selection/Result digest mapping, no cross-Result bleed. | TD-UI, TD-RUN | ST-08 |
| `UT-DET-017` | zero/no-source/file-error/partial/completed statuses and provenance visibility decisions. | TD-UI, TD-RUN | ST-08 |
| `UT-DET-018` | exact ordered RF feature schema and class/probability-column validation; reject mismatch/nonfinite values. | TD-EXPORT, TD-TRAIN | ST-09 |
| `UT-DET-019` | per-candidate accepted/rejected/unscored status and short/stale/error decisions. | TD-EXPORT, TD-TRAIN | ST-09 |
| `UT-DET-020` | immutable parent→child lineage, candidate identity, time/provenance and checksum rules. | TD-EXPORT, TD-TRAIN | ST-09 |
| `UT-DET-021` | exact frame/byte/TSV offset arithmetic and output representation without rounding drift. | TD-WAV, TD-PATH | ST-10 |
| `UT-DET-022` | frozen selected IDs/digests, parent lineage and reproducible provenance ordering. | TD-WAV, TD-PATH | ST-10 |
| `UT-DET-023` | collision-safe names, mixed-format decision and conservative publish/overwrite policy. | TD-WAV, TD-PATH | ST-10 |
| `UT-DET-024` | Bulk inclusion includes every and only valid WAV, replaces exclusions only after confirmation, rejects stale inventory revisions and leaves the complete prior decision document unchanged on cancel/validation/write failure. | TD-WAV, TD-CACHE, TD-FAIL | REV-02 |
| `UT-DET-025` | Typed Detect route validation, adaptive New detection entry, nested-route sidebar highlighting, and fail-closed invalid-route rejection. | TD-UI | REV-04 |
| `UT-DET-026` | Versioned export-history schema, newest-first bounded ordering, duplicate identity, containment, strict partial loading, and atomic-write recovery. | TD-PATH, TD-FAIL | REV-04 |
| `UT-STU-002` | Pure cross-workspace quit/admission policy and independent Train/Detect ownership; no duplicate Run IDs, hidden Worker's lifetime not inferred from visibility. | TD-UI, TD-RUN | [ST-11](specs/ST-11-unified-qualification.md) |
| `UT-STU-003` | Unified-package ownership audit rejects the removed namespace, forbidden reverse dependencies and workflow-specific code under `shared`; canonical app-data decisions yield separate contained Train and Detect roots. | TD-PATH, TD-CACHE | REV-01 |
| `UT-COL-001` | Positive name parses anchored complete stem, integer ms and unique label; reject malformed/missing fields and overflow | TD-COL | 02 |
| `UT-COL-002` | Exact unique source-stem resolution; overlapping prefixes, duplicate names and same-source duplicate interval rejected | TD-COL | 02 |
| `UT-COL-003` | Half-open bounds `0 ≤ start < end ≤ source duration`, integer ms to sample frames and honest rounding tolerance | TD-WAV | 02 |
| `UT-COL-004` | Different WAV header/codec/frame facts yield explicit valid/invalid decisions and issue codes | TD-WAV | 02 |
| `UT-COL-005` | Cache/inventory change decision: added, removed, changed, absent and corruption are distinct | TD-CACHE | 02 |
| `UT-COL-006` | Versioned metadata/partition serialization rejects unsupported versions and unsafe refs | TD-CACHE | 02 |
| `UT-DB-001` | Protected positive spans merge/clip safely with margin; eligible noise windows never intersect them | TD-MINE | 03 |
| `UT-DB-002` | Seeded candidate window allocation is deterministic, bounded and reports underfill | TD-MINE | 03 |
| `UT-DB-003` | Source-group Split assignment is deterministic, no source leakage; impossible class/split balance reported | TD-SPLIT | 03 |
| `UT-DB-004` | Snippet/source interval/label provenance and manifest references are validated; reject conflicting/multiple Snippet labels and any class set other than `target`/`noise` | TD-SPLIT | 03 |
| `UT-RUN-001` | Exactly one Active Run, terminal-state transition table, duplicate start and reservation conflicts | TD-RUN | 04 |
| `UT-RUN-002` | Orphan/restart/cancel policy and published-pointer validity decisions are conservative | TD-RUN | 04 |
| `UT-UI-001` | Mutable Dataset/Model display names are validated and atomically stored outside immutable manifests; Run renaming preserves stable identity and history | TD-UI, TD-PATH, TD-RUN | UI pass |
| `UT-POWER-001` | Application Settings v2→v3 migration and strict boolean validation; keep-awake request/effective-state idempotence, retryable acquisition failure and unsupported-platform distinction | TD-FAIL | 05g |
| `UT-AUDIO-001` | PCM frame-interval and desktop adapter compatibility; see `tests/unit/test_audio.py` | TD-WAV | 04.5 |
| `UT-AUDIO-002` | Manifest metadata, integrity hashing and exception policy; see `tests/unit/test_audio.py` | TD-WAV, TD-FAIL | 04.5 |
| `UT-TRAIN-001` | CNN settings bounds and resolved config; strict binary single-label `target`/`noise` mapping and split coverage; reject multi-label/multi-class config, extra classes, multi-hot targets or editable `num_classes` | TD-TRAIN | 05 |
| `UT-TRAIN-002` | RF settings bounds, feature names/order/schema matching and threshold semantics | TD-TRAIN | 05 |
| `UT-TRAIN-003` | Family-specific metrics, positive-class selection, null/undefined ROC-AUC and validation counts | TD-TRAIN | 05 |
| `UT-TRAIN-004` | Model manifest ID/family/dataset/paths/checksums validation; unsupported format rejected | TD-TRAIN | 05 |
| `UT-TRAIN-005` | Required two-class single-label CNN head/objective/output and binary mapping; reject checkpoint/schema cardinality or multi-label mismatch; resolved architecture/spectrogram/normalization/class mapping vs exported config, train-only augmentation separation, tensor/state format and package revision metadata | TD-EXPORT | 05 |
| `UT-TRAIN-006` | RF exactly two `classes_` with saved explicit binary probability-column order; reject multi-output/multi-class estimator and mapping mismatches; exact ordered feature/schema/preprocess and `classes_` vs metadata, corrupt/checksum path/version/namespace mismatch refused, relative portability of binary references | TD-EXPORT, TD-PATH | 05 |
| `UT-TRAIN-007` | Primary visibility roster is restricted to the documented small family-specific set; every field has `ui_tier`, typed `recommended_starting_value` and `recommendation_basis`, with derived fields noneditable and backend-baseline suggestion explicitly non-empirical. Config catalog completeness: all non-path reference keys accounted for (including automatic/unsupported dispositions), both family schemas and per-field unique HelpHint + Wiki anchors; preset-independent defaults/units | TD-CONFIG | 05 |
| `UT-TRAIN-008` | Collapsed/expanded presentation never changes resolved scientific values; per-field/section reset explicitly updates draft only. Default/suggested values are provenance-backed; incompatible backend defaults produce validation, not silent correction. Numeric and cross-field validation, unsupported device/feature gating, known-typed effective defaults, RF null depth/feature schema; no source path inputs and no imaginary toggle behavior | TD-CONFIG | 05 |
| `UT-TRAIN-009` | User saved presets: reject multi-label/multi-class/extra class settings; per-family values, create/load/duplicate/rename/delete/overwrite, draft vs stored vs immutable Run spec, no Collection/Dataset paths, stable IDs | TD-PRESET, TD-CONFIG | 05 |
| `UT-TRAIN-010` | Preset schema migration/incompatible toolbox revision, corrupt JSON, unsafe/duplicate names, atomic failure and no silent field loss | TD-PRESET, TD-FAIL | 05 |
| `UT-LOG-001` | Versioned JSONL record schema, level filtering, stable component/event names, correlation IDs and strict allowlisted context | TD-RUN, TD-FAIL | 05d |
| `UT-LOG-002` | Portable privacy normalization excludes absolute/home/HPC/UNC/drive paths, WAV basenames, credentials, controls, arbitrary exception text and overlong values | TD-PATH, TD-FAIL | 05d |
| `UT-LOG-003` | App/Run log containment rejects traversal and symlink escapes; diagnostics readers/exporters revalidate records and never copy corrupt or unknown fields verbatim | TD-PATH, TD-FAIL | 05d |
| `UT-LOG-004` | App/Worker byte budgets, bounded rotation, age/total pruning, stderr storm bounds and non-recursive degraded-sink fallback | TD-RUN, TD-FAIL | 05d |

Historical implementation notes belong to their owning specs and tests; this index lists contracts, not fresh execution evidence.

Do not add unit tests that instantiate a fake repository/GUI just to mirror an `IT-*` case. Conversely, if the algorithm truly depends on WAV decoder/frame reads, include a minimal actual WAV integration test for that boundary. See [`INTEGRATION_TESTING.md`](INTEGRATION_TESTING.md) and its indexed behavior plan.
