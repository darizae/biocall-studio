# Unit testing — focused rule index

Use fast deterministic, Qt-free tests for pure behaviors: filename/path parsers, duration and frame arithmetic, exclusion-window math, Split grouping, configuration validation and state transitions. A parser test does not prove real WAV I/O, cache persistence, GUI responsiveness, QProcess or Training. `tests/unit/` is the initial CI suite; it must not need actual HPC, large LFS payloads or a running GUI.

## Naming and coverage

An indexed case appears **exactly** in the asserting test function docstring, e.g. `"""Case: UT-COL-001."""`. Table rows below define intended cases, **not completion**. A test counts as covered only after the exact behavior is asserted and an applicable run passes. Do not renumber an existing ID to reuse it for different behavior. Add edge variants under the same case where the invariant is unchanged; add an ID when the behavior is materially distinct.

| Case ID | Pure behavior and failure contrasts | Data class | Spec |
|---|---|---|---|
| `UT-PATH-001` | Portable relative segments reject absolute/traversal, invalid separators, reserved OS names | TD-PATH | 01 |
| `UT-PATH-002` | Unicode NFC/casefold filename collisions cannot silently resolve an identity | TD-PATH | 01 |
| `UT-COL-001` | Positive name parses anchored complete stem, integer ms and unique label; reject malformed/missing fields and overflow | TD-COL | 02 |
| `UT-COL-002` | Exact unique source-stem resolution; overlapping prefixes, duplicate names and same-source duplicate interval rejected | TD-COL | 02 |
| `UT-COL-003` | Half-open bounds `0 ≤ start < end ≤ source duration`, integer ms to sample frames and honest rounding tolerance | TD-WAV | 02 |
| `UT-COL-004` | Different WAV header/codec/frame facts yield explicit valid/invalid decisions and issue codes | TD-WAV | 02 |
| `UT-COL-005` | Cache/inventory change decision: added, removed, changed, absent and corruption are distinct | TD-CACHE | 02 |
| `UT-COL-006` | Versioned metadata/partition serialization rejects unsupported versions and unsafe refs | TD-CACHE | 02 |
| `UT-DB-001` | Protected positive spans merge/clip safely with margin; eligible noise windows never intersect them | TD-MINE | 03 |
| `UT-DB-002` | Seeded candidate window allocation is deterministic, bounded and reports underfill | TD-MINE | 03 |
| `UT-DB-003` | Source-group Split assignment is deterministic, no source leakage; impossible class/split balance reported | TD-SPLIT | 03 |
| `UT-DB-004` | Snippet/source interval/label provenance and manifest references are validated | TD-SPLIT | 03 |
| `UT-RUN-001` | Exactly one Active Run, terminal-state transition table, duplicate start and reservation conflicts | TD-RUN | 04 |
| `UT-RUN-002` | Orphan/restart/cancel policy and published-pointer validity decisions are conservative | TD-RUN | 04 |
| `UT-TRAIN-001` | CNN settings bounds and resolved config; label/split coverage checks | TD-TRAIN | 05 |
| `UT-TRAIN-002` | RF settings bounds, feature names/order/schema matching and threshold semantics | TD-TRAIN | 05 |
| `UT-TRAIN-003` | Family-specific metrics, positive-class selection, null/undefined ROC-AUC and validation counts | TD-TRAIN | 05 |
| `UT-TRAIN-004` | Model manifest ID/family/dataset/paths/checksums validation; unsupported format rejected | TD-TRAIN | 05 |

Do not add unit tests that instantiate a fake repository/GUI just to mirror an `IT-*` case. Conversely, if the algorithm truly depends on WAV decoder/frame reads, include a minimal actual WAV integration test for that boundary. See [`INTEGRATION_TESTING.md`](INTEGRATION_TESTING.md) and its indexed behavior plan.
