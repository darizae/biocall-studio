# RV-02 — Durable sessions, human labels and finalization

> **Status:** Owner-approved planning spec, NOT implemented. Do not start implementation or infer test passes from this document. Read [`AGENTS.md`](../../../AGENTS.md) and [`docs/agent/ROUTING.md`](../../agent/ROUTING.md), then this stage and only dependencies needed by its code. No push, merge, tag or release without the owner's separate authorization.

**Sequence:** RV-02 begins only after RV-01 has passed its owner-reviewed gate.

**Series:** [Locked scope, prerequisites and coverage](README.md) · [Status](../../IMPLEMENTATION_SEQUENCE.md)

## Strict ownership and exclusions

**Owner:** `review/domain` and `review/persistence`, with a Qt-free Review session controller. **Entry:** approved RV-01. **Output:** reliable persisted editable/closed/finalized states consumed by RV-05/RV-06. Do not build audio, a gallery or exporting here. Studio-wide visual quit dialogue is RV-07's owner.

## Detailed session, label and recovery contract

### Session states

| State | Allowed actions | Persistence & transition |
|---|---|---|
| **Open** | Review, annotate, Accept all, undo, filter/navigate, generate/flush, Close, Finalize | Exactly one Open session; each label transaction commits promptly. Navigation to another workspace does **not** change state. |
| **Closed** | Resume, view history, start successor only if finalized (not here) | Explicit Close saves current state and resumes later as the same session; no implicit finalization. |
| **Finalized** | Read-only inspect, export/re-export, **Continue in new session** | Final snapshot has independent digest and immutable parent lineage. No in-place edit, no retroactive annotation mutation. |

**Start session:** choose one valid Result; propose editable sensible name (no internal ID), freeze eligibility and create transactionally. If an Open session already exists, require the user to Close it before opening another; do not silently close it. Resume a Closed session transitions it to Open only after store checks and source/Result validation; missing audio may be noted without discarding existing annotations.

**Label transaction:** key `(session, candidate)`, one of `unreviewed/call/not_call`; store decision origin `individual|bulk` where relevant, last-modified timestamp and monotonically increasing session revision. `Unreviewed` is the absence/default of a human decision, not an artificial acceptance. Save the label before advancing and do not display committed success on failed persistence. `Clear label` restores Unreviewed. Undo/redo scope should be bounded and predictable (at least last action, including a batch); never leave partial batch results on disk. Changing a bulk label individually changes its decision origin accordingly. Use unique keys and explicit concurrency/revision guards to avoid lost writes across windows/processes.

**Accept all:** atomic update of all eligible currently Unreviewed decisions only; user sees the approved count-dependent confirmation. Existing rejections/acceptances remain. Recording a compact batch operation plus per-candidate provenance is preferable to keeping an enormous undo blob in GUI memory. Undo is allowed only while session remains editable; finalize blocks it. On tens of thousands, updates must be incremental/transactional at the storage layer and keep the Qt event loop responsive without an uncommitted partial state advertised as completed.

**Finalize:** read a consistent committed snapshot, count Call/Not a call/Unreviewed and apply the approved partial-review warning if necessary. Commit an immutable versioned finalization manifest/snapshot (eligibility, ordered decisions, Result/parent lineage, thresholds/score semantics, source identities and snapshot digest). Do not include cache pixel data or transient UI navigation. Validate no active conflicting label write. Return a finalized session that stays available even if export fails, cancels or never starts.

**Continue in new session:** create a new session, parented to the finalized session's ID and digest, seeded with the finalized decisions and their provenance; the original never changes. New edits receive new timestamps/origins and the successor has its own future finalization. The original can be used to re-export at any time. Never reuse session IDs/digests or overwrite prior export receipts.

**App exit:** Review session Open is a suite-level exit concern even when the visible route is Train or Detect. Show **one** coordinated confirmation for Open session and any running Train/Detect/Review operations. The approved session-only text is “A Review session is still open. Save and exit?”; combined work text is “A Review session is open and processing is still running. Exit will save the session and stop the running work.” Buttons: **Keep app open**, **Save and Exit**. On affirmative exit, checkpoint/commit session, stop/cancel permitted Workers safely, wait for owned leases/process completion, then close; on save/stop failure, do **not** quit and pretend success. A clean Close session before app exit removes that specific warning. Existing Train/Detect exit behavior must remain intact when no Review session is open.

### Crash recovery / concurrency

Committed labels survive power interruption. Partial database transactions roll back; interrupted finalization never creates a partially valid finalized snapshot; interrupted cache generation leaves no valid cache record until checksum/atomic rename; interrupted exports reconcile staging/publication and history without changing the frozen session. Reopening checks schema, integrity, last committed revision, lease owner and finalized snapshot digests. Recoverable stale Worker leases cannot imply finished work. A second Studio instance must not silently write competing active sessions; use the project's existing owner-lease/locking patterns at the appropriate scope, with a tested user-readable conflict path.

## Spectrogram settings snapshot and preset lifecycle (owner decision 2026-11-03)

At **Start session**, the researcher selects one existing spectrogram preset (default selected). Persist a *versioned immutable copy of all effective scientific/display settings*, algorithm/render contract versions, selected preset's stable ID, human name and revision. Session settings changes are atomic and independently revision-guarded; recording/candidate eligibility, three human labels, annotation undo, Result lineage and original frame positions are never rewritten. Session status and single-Open admission rules above remain authoritative. A saved preset may be edited, renamed or deleted later, but existing Open, Closed and Finalized sessions **retain their captured settings** and valid image references; such mutations are not automatic session migrations or invisible regeneration jobs.

Only **Open** can explicitly **Change preset**. Closed must Resume first; Finalized remains immutable and its read-only images/export remain available, while **Continue in new session** inherits the parent's effective settings *copy* and may choose another preset as an independently editable child. Record settings provenance/digest (not cached PNGs) in the frozen finalization manifest without altering corpus payload rules; a future deletion/rename of a preset must not make final snapshot validation depend on the global preset catalog. Version/migrate earlier session documents deterministically and never invent missing settings for truly unknown versions.

User preset **Save changes** requires an impact confirmation counting Open/Closed/Finalized sessions referencing any revision of that preset; **Save preset** changes future selections only. An optional **Save and use in this session** is a *separate explicit operation* available only when the current Open session uses it, after full RV-04 capacity/admission and cache invalidation disclosure; failure leaves the existing snapshot/cache active. The protected Default cannot be edited or deleted. Deleting user presets does not delete session annotations/settings or valid shared images. [Pre-spec research](SPECTROGRAM_GENERATION_INVESTIGATION.md) must qualify schema/identity before native stage implementation.

**Qualification extension:** `UT-REVW-004`, `IT-REVW-002/003` cover snapshot persistence, preset edits/renames/deletion, saved-example independence, atomic failed switches, Closed/Finalized/child lineage and changed-but-unchanged label/source digests.

## Owning acceptance cases (proposed; register in existing indexes before TDD)

These are stage scope definitions, **not registered or executed tests**. Validate IDs against [unit](../../UNIT_TESTING.md), [integration](../../INTEGRATION_TEST_BEHAVIORS.md), and [fixture index](../../INTEGRATION_TEST_DATA.md); register exact case text there before implementation. Never create a second test index.

| ID | Owner | Positive assertions | Negative / non-mutation assertions |
|---|---|---|---|
| `UT-REVW-003` | RV-02 | all three label transitions, Clear label, Accept all limited to Unreviewed, batch provenance, undo | existing human rejections unchanged by batch; invalid candidate/revision conflict/write failure leaves prior transaction intact |
| `UT-REVW-004` | RV-02 | Open→Closed→Open, Finalized→new child, immutable snapshot and accurate partial counts | cannot write finalized/second Open session; inconsistent snapshot/digest rejected; no accidental close on navigation |
| `IT-REVW-002` | RV-02 | SQLite (or reviewed alternative) commits labels/bulk/undo; restart with 50k candidate index, close/resume and current position | forced process loss/second writer doesn't lose committed labels; source Result and source WAV hash unchanged |
| `IT-REVW-003` | RV-02 | real transaction/finalize/child persistence and immutable digest across restart | failed disk write/corruption/lock/kill mid-finalization leaves old valid state; no partial finalized session |

**Gate:** Owner reviews actual session schema, one-open policy, 50k reopen, atomic batch undo, crash/lock behavior and finalized lineage.

## Delivery and evidence gate

Record reviewed baseline SHA and branch, actual implementation files, focused and full feasible ordinary test commands and pass/fail/skip/block results, Ruff, `scripts/audit_test_ids.py`, `git diff --check`, source/Result checksum non-mutation, and current dependency import origins/SHAs. Capture real native Qt/audio/Worker evidence only for boundaries owned here; do not claim whole-Studio qualification before RV-08. Confirm a clean narrowly scoped diff and hand the branch/commit SHA to the owner. No automatic merge or push.

**Next:** RV-03 may be prepared only after this gate is explicitly approved.
