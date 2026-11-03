# RV-02 — Durable sessions, human labels and finalization

> **Status:** Owner-approved planning; not implemented. Begin only after explicit stage authorization and the predecessor's owner gate.

## Strict ownership and exclusions

**Owner:** `review/domain` and `review/persistence`, with a Qt-free Review session controller. **Entry:** approved RV-01. **Output:** reliable persisted editable/closed/finalized states consumed by RV-05/RV-06. Do not build audio, a gallery or exporting here. Studio-wide visual quit dialogue is RV-07's owner.

## Detailed session, label and recovery contract

### Session states

| State | Allowed actions | Persistence & transition |
|---|---|---|
| **Open** | Review, annotate, Accept all, undo, filter/navigate, generate/flush, Close, Finalize | Exactly one Open session; each label transaction commits promptly. Navigation to another workspace does **not** change state. |
| **Closed** | Resume or view history | Explicit Close saves current state and resumes later as the same session; no implicit finalization. |
| **Finalized** | Read-only inspect, export/re-export, **Continue in new session** | Final snapshot has independent digest and immutable parent lineage. No in-place edit, no retroactive annotation mutation. |

**Start session:** choose one valid Result; propose editable sensible name (no internal ID), freeze eligibility and create transactionally. If an Open session already exists, require the user to Close it before opening another; do not silently close it. Resume a Closed session transitions it to Open only after store checks and source/Result validation; missing audio may be noted without discarding existing annotations.

**Label transaction:** key `(session, candidate)`, one of `unreviewed/call/not_call`; store decision origin `individual|bulk` where relevant, last-modified timestamp and monotonically increasing session revision. `Unreviewed` is the absence/default of a human decision, not an artificial acceptance. Save the label before advancing and do not display committed success on failed persistence. `Clear label` restores Unreviewed. Undo/redo scope should be bounded and predictable (at least last action, including a batch); never leave partial batch results on disk. Changing a bulk label individually changes its decision origin accordingly. Use unique keys and explicit concurrency/revision guards to avoid lost writes across windows/processes.

**Accept all:** atomic update of all eligible currently Unreviewed decisions only; user sees the approved count-dependent confirmation. Existing rejections/acceptances remain. Recording a compact batch operation plus per-candidate provenance is preferable to keeping an enormous undo blob in GUI memory. Undo is allowed only while session remains editable; finalize blocks it. On tens of thousands, updates must be incremental/transactional at the storage layer and keep the Qt event loop responsive without an uncommitted partial state advertised as completed.

**Finalize:** read a consistent committed snapshot, count Call/Not a call/Unreviewed and apply the approved partial-review warning if necessary. Commit an immutable versioned finalization manifest/snapshot (eligibility, ordered decisions, Result/parent lineage, thresholds/score semantics, source identities and snapshot digest). Do not include cache pixel data or transient UI navigation. Validate no active conflicting label write. Return a finalized session that stays available even if export fails, cancels or never starts.

**Continue in new session:** create a new session, parented to the finalized session's ID and digest, seeded with the finalized decisions and their provenance; the original never changes. New edits receive new timestamps/origins and the successor has its own future finalization. The original can be used to re-export at any time. Never reuse session IDs/digests or overwrite prior export receipts.

**App exit boundary:** expose durable Open-state reporting and safe checkpoint/Close for Studio's global quit coordinator. RV-07 owns the single application-wide confirmation and Worker shutdown policy, using the approved wording in RV-05. Navigating away must never implicitly Close a session.

### Crash recovery / concurrency

Committed labels survive power interruption. Partial database transactions roll back; interrupted finalization never creates a partially valid finalized snapshot; interrupted cache generation leaves no valid cache record until checksum/atomic rename; interrupted exports reconcile staging/publication and history without changing the frozen session. Reopening checks schema, integrity, last committed revision, lease owner and finalized snapshot digests. Recoverable stale Worker leases cannot imply finished work. A second Studio instance must not silently write competing active sessions; use the project's existing owner-lease/locking patterns at the appropriate scope, with a tested user-readable conflict path.

## Acceptance cases (register in existing test indexes during stage TDD)

| ID | Owner | Positive assertions | Negative / non-mutation assertions |
|---|---|---|---|
| `UT-REVW-003` | RV-02 | all three label transitions, Clear label, Accept all limited to Unreviewed, batch provenance, undo | existing human rejections unchanged by batch; invalid candidate/revision conflict/write failure leaves prior transaction intact |
| `UT-REVW-004` | RV-02 | Open→Closed→Open, Finalized→new child, immutable snapshot and accurate partial counts | cannot write finalized/second Open session; inconsistent snapshot/digest rejected; no accidental close on navigation |
| `IT-REVW-002` | RV-02 | SQLite (or reviewed alternative) commits labels/bulk/undo; restart with 50k candidate index, close/resume and current position | forced process loss/second writer doesn't lose committed labels; source Result and source WAV hash unchanged |
| `IT-REVW-003` | RV-02 | real transaction/finalize/child persistence and immutable digest across restart | failed disk write/corruption/lock/kill mid-finalization leaves old valid state; no partial finalized session |

**Gate:** Owner reviews actual session schema, one-open policy, 50k reopen, atomic batch undo, crash/lock behavior and finalized lineage.

**Next:** RV-03 may be prepared only after this gate is explicitly approved.
