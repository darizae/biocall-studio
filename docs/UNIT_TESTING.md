# Unit testing — focused rule index

Use fast deterministic, Qt-free tests for pure behaviors: filename/path parsers, duration and frame arithmetic, exclusion-window math, Split grouping, configuration validation and state transitions. A parser test does not prove real WAV I/O, cache persistence, GUI responsiveness, QProcess or Training. `tests/unit/` is the initial CI suite; it must not need actual HPC, large LFS payloads or a running GUI.

## Naming and coverage

An indexed case appears **exactly** in the asserting test function docstring, e.g. `"""Case: UT-COL-001."""`. Table rows below define intended cases, **not completion**. A test counts as covered only after the exact behavior is asserted and an applicable run passes. Do not renumber an existing ID to reuse it for different behavior. Add edge variants under the same case where the invariant is unchanged; add an ID when the behavior is materially distinct.

| Case ID | Pure behavior and failure contrasts | Data class | Spec |
|---|---|---|---|
| `UT-PATH-001` | Portable relative segments reject absolute/traversal, invalid separators, reserved OS names | TD-PATH | 01 |
| `UT-PATH-002` | Unicode NFC/casefold filename collisions cannot silently resolve an identity | TD-PATH | 01 |
| `UT-CLI-001` | Version/help and invalid-option handling complete without importing optional Qt/`alp-ui`; real GUI startup remains owned by `IT-UI-001` and uses isolated Application Settings | TD-UI | 01, 05f |
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
| `UT-AUDIO-001` | PCM frame-interval and desktop adapter compatibility; details/edge cases in [Spec 04.5](specs/SPEC_04_5_UPSTREAM_AUDIO_EXTRACTION.md) | TD-WAV | 04.5 |
| `UT-AUDIO-002` | Manifest metadata, integrity hashing and exception policy; [Spec 04.5](specs/SPEC_04_5_UPSTREAM_AUDIO_EXTRACTION.md) | TD-WAV, TD-FAIL | 04.5 |
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

**Reported status:** Spec 05c completes `UT-TRAIN-001`–`010`, including exact ordered RF feature
schema, explicit positive-probability mapping, undefined metrics and structural estimator rejection.
The [Spec 05 evidence](design/evidence/README.md#spec-05c--real-rf-training-and-phase-05-acceptance)
records the fresh commands and results; listing the IDs here is not independent passing evidence.

**Reported status:** Spec 05d implements `UT-LOG-001`–`004`; the
[native diagnostics ledger](design/evidence/README.md#spec-05d--local-logging-and-diagnostics)
records the red-first boundary and fresh verification. Listing the IDs is not passing evidence.

Do not add unit tests that instantiate a fake repository/GUI just to mirror an `IT-*` case. Conversely, if the algorithm truly depends on WAV decoder/frame reads, include a minimal actual WAV integration test for that boundary. See [`INTEGRATION_TESTING.md`](INTEGRATION_TESTING.md) and its indexed behavior plan.
