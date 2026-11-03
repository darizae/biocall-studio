# RV-01 — Detect Result intake and eligibility

> **Status:** Owner-approved planning spec, NOT implemented. Do not start implementation or infer test passes from this document. Read [`AGENTS.md`](../../../AGENTS.md) and [`docs/agent/ROUTING.md`](../../agent/ROUTING.md), then this stage and only dependencies needed by its code. No push, merge, tag or release without the owner's separate authorization.

**Sequence:** RV-01 starts from reviewed `main` with REV-05 already implemented and owner-reviewed. RV-02 requires RV-01's explicit owner approval.

**Series:** [Locked scope, prerequisites and coverage](README.md) · [Status](../../IMPLEMENTATION_SEQUENCE.md)

## Strict ownership and exclusions

**Owner:** `review/domain` intake projection and `review/persistence` app-owned root, read-only consumption of Detect Results. **Entry:** completed/verified REV-05 reviewed base; no Review implementation exists yet. **Exit dependency:** RV-02 may start only after owner signs RV-01. No session labeling, spectrogram generation, corpus export, new Detect export removal, general WAV importing or new RF filtering options.

## Contract and implementation boundaries

- Read only **completed and verified** original CNN or RF-derived Detect Results; no generic recording, imported annotation or existing corpus-export input. Produce versioned, deterministic eligible-candidate index with stable `Result` reference/digest, recording source identity and original frame positions/times. Distinguish a legitimately zero-eligible Result from failure to load a Result or recording.
- CNN-only: **all** Result candidates eligible. RF-derived: **only RF-accepted** candidates eligible; rejected/unscored do not appear in any view/filter/export input, not even hidden selection. An original CNN parent may be selected separately; do not reinterpret RF scores as researcher decisions.
- Check Result schema/version, integrity, parent lineage, candidate ordering and uniqueness, inventory/collection identity and source-range validity. Detect stale/changed source, traversal/symlink attack and unsupported format without modifying Result/recording. Missing WAV should not erase the read-only Result or create zero candidates; expose a relink-needed state for later UI.
- Establish isolated `review/v1` under Studio's actual application-owned `SuiteDataPaths`. Prefer validated references plus lightweight paged projection/index over copying a huge Result; preserve parent SHA and source timeline. Keep Train/Detect data owners intact. Stable identity is not an on-screen UUID.
- The current placeholder remains a placeholder for this domain-only stage. No UI promises or scientific toolchain overhaul.


## Spectrogram preset handoff (owner decision 2026-11-03)

RV-01 continues to validate/projection-index **Detect Results only**. Do not accept the unrelated WAV selected by Review's future **Test WAV** settings action as a Result, candidate, recording relink or corpus source. Project verified recording sample rate/channels, source identity and exact original candidate frames needed for later RV-02 settings snapshot and RV-03 context; avoid computing a spectrogram or freezing a preset in RV-01. The actual default/selected preset is supplied at **RV-02 session creation**, not stored in the immutable Result. See [spectrogram pre-spec](SPECTROGRAM_GENERATION_INVESTIGATION.md) and [owner decisions](SPECTROGRAM_DECISIONS.md).

**Qualification extension:** existing `UT-REVW-002`/`IT-REVW-001` reject arbitrary test WAVs and retain valid original frame/rate identity; no extra intake test series.

## Owning acceptance cases (proposed; register in existing indexes before TDD)

These are stage scope definitions, **not registered or executed tests**. Validate IDs against [unit](../../UNIT_TESTING.md), [integration](../../INTEGRATION_TEST_BEHAVIORS.md), and [fixture index](../../INTEGRATION_TEST_DATA.md); register exact case text there before implementation. Never create a second test index.

| ID | Owner | Positive assertions | Negative / non-mutation assertions |
|---|---|---|---|
| `UT-REVW-001` | RV-01 | CNN-all / RF-accepted-only eligible order and counts, stable mapping to original frames/source identities | RF-rejected/unscored absent even in filters; duplicate or wrong-parent candidate never eligible |
| `UT-REVW-002` | RV-01 | versioned verified input projection and Result/parent digest validation; zero eligible distinguished from failed audio file | corrupt/unsupported/stale/path traversal/changed Result fails closed; Detect Result bytes untouched |
| `IT-REVW-001` | RV-01 | real persisted CNN and RF Result artifacts reopen, project correct eligible candidates, source provenance unchanged | corrupted/relinked/missing Result and unsafe source path show actionable unavailable states; original bytes unchanged |

**Gate:** Owner approves eligibility contract, artifact digest/lineage and sample Result projection, genuine missing/corrupt/empty distinctions and immutable originals.

## Verified repository baseline and source authority

Read `AGENTS.md` and `docs/agent/ROUTING.md` first on every implementation stage; then read only the stage's owning sections and concrete dependencies. The earlier planning inspection used a 2026-11-02 snapshot; current implementation planning must use the updated reviewed `main` baseline (`c00d8808a2d1` on 2026-11-03) and verify its actual checkout SHA at RV-01 entry. All requested documentation exists: `docs/PREDICTION.md`, `docs/IMPLEMENTATION_SEQUENCE.md`, `docs/design/{UX_PARITY_MATRIX,PROTOTYPE_ACCEPTANCE,ALP_UI_CONSUMER_CONTRACT}.md`, `docs/specs/manual_revision_specs/{REV-05-output-size-preflight.md,detect-revision-notes.txt,UI-pass-revision-spec.md}`, `docs/{UNIT_TESTING,INTEGRATION_TEST_BEHAVIORS,INTEGRATION_TEST_DATA}.md`, and `AGENTS.md`/`docs/agent/ROUTING.md`.

Observed current source-of-truth seams:

- `src/biocall_studio/studio/application/{coordinator,operations,storage}.py`, `studio/gui/shell.py`: one Qt application, retained workspace controllers, global Worker admission and coordinated exit; Review is still a placeholder. The current `SuiteDataPaths` exposes `train/v1` and `detect/v1` only.
- `detect/domain/{results,rf_refinement,result_views}.py`: immutable CNN Result and RF-derived Result with accepted/rejected/unscored model decisions, candidate identities, original recording frame/time bounds, source identity, integrity and lineage. Result selections are **not** human annotations; `result_views.py` has `MAX_SELECTED_CANDIDATES=100_000`, while selection persistence has `MAX_SELECTION_BYTES=1_048_576`.
- `detect/domain/exports.py`, `detect/workflows/exports.py`, `detect/persistence/export_history.py`, `detect/gui/{results,export,workspace}.py`, `detect/application/controller.py`: existing PCM-preserving snippets/concatenation, Raven TSV, checksums, source validation, histories, atomic publication, Qt export route and Results entry. `MAX_EXPORT_CANDIDATES=10_000` and `MAX_DOCUMENT_BYTES=64 * 1024 * 1024` are real current limits. Multiple export structures materialize large candidate/file collections and verification repeats file traversal/hashing; raising the limit alone is inadequate.
- `src/biocall_studio/cli.py` has a closed list of supervised Worker modes. Review generation/export execution must follow the canonical owner-lease and Worker protocol rather than inventing an unsupervised thread/process path.
- `docs/design/ALP_UI_CONSUMER_CONTRACT.md` verifies `alp-ui` `DataTable`, `Button`, `HelpHint`, `ProgressBar`, etc.; public `Plot` only supports line/bar and does not implement a spectrogram. Use native PySide6 for Review-specific audio/spectral interactions; upstream changes only for truly generic missing primitives.

**REV-05 is implemented and owner-reviewed on the reviewed `main` baseline (`c00d8808a2d1`).** Its Qt-free `src/biocall_studio/shared/storage.py` implements `StorageEstimate`, `OperationSizePlan`, `assess_storage`, `query_filesystem_capacity` and `require_storage_admission`. Train/Detect adapters and indexed `UT-SIZE-*` / `IT-SIZE-*` cases are present. RV-01 must not duplicate shared preflight. At RV-04/RV-06, implement only Review-specific sizing inputs/adapters against that existing API and verify the actual dependency versions; if a different checkout lacks REV-05, recover the reviewed base instead of reimplementing it.

Other useful authority: `docs/ARCHITECTURE.md`, `docs/agent/GIT_DELIVERY.md`, `docs/agent/SPEC_WRITING_AND_IMPLEMENTATION_PRINCIPLES.md`, and the existing test/fixture indexes. `docs/PREDICTION.md` and `docs/design/UX_PARITY_MATRIX.md` are *historical* on Detect corpus-export ownership and must be updated during migration, not used to overrule the owner decision. The prototype at `docs/design/prototypes/studio-detect/` is a **visual-principles** reference, never a predefined Review workflow.

## Delivery and evidence gate

Record reviewed baseline SHA and branch, actual implementation files, focused and full feasible ordinary test commands and pass/fail/skip/block results, Ruff, `scripts/audit_test_ids.py`, `git diff --check`, source/Result checksum non-mutation, and current dependency import origins/SHAs. Capture real native Qt/audio/Worker evidence only for boundaries owned here; do not claim whole-Studio qualification before RV-08. Confirm a clean narrowly scoped diff and hand the branch/commit SHA to the owner. No automatic merge or push.

**Next:** RV-02 may be prepared only after this gate is explicitly approved.
