# ST-03 — Detect workspace identity, metadata and relinking

**Branch:** `detect-st03-workspace`, created from reviewed local `detect`. **Predecessor:** owner-approved ST-02. **Successor:** ST-04. **Status:** planned; nothing here establishes implemented behavior.

## Scope and ownership

- Detect owns an independently addressable **Collection** and application-owned, versioned workspace metadata **outside any recording/source root**. Preserve Train's Collection, `.alpaca/` store, preferences, Worker and CLI exactly; never treat a Train Collection ID as a Detect ID.
- Define a stable opaque Collection ID, creation/update metadata, schema version, display label, canonical source-root binding and latest validated inventory *reference*. Keep relative recording references for later stages, and reserve app-owned namespaces for Detect Runs, Results and Exports without creating their substantive formats now.
- Store under an OS-appropriate per-user application-data directory; inspect `biocall_studio_train.persistence.settings`, existing app identity and platform behavior before selecting exact layout. Keep Detect application settings separate from scientific immutable artifacts. The selected recording tree is read-only, including when it contains Train metadata.
- Build native Detect source selection, current Collection summary, missing/stale binding state, explicit **Relink** confirmation and return/navigation. No WAV recursive inventory (ST-04), Model intake (ST-05), Worker (ST-06), or Results.

## Contract and handoff

`DetectCollectionRef` (versioned): `collection_id`, display label, source-root URI **only in private local binding**, root fingerprint/evidence, schema revision, and inventory-revision pointer (initially absent). `RootBindingDecision`: `valid | missing | inaccessible | changed | awaiting_confirmation`; keep root-level identity separate from specific recording hashes (ST-04). Document creation, relocation, explicit rebind versus new Collection, and how an outdated inventory becomes stale. Files owned by Detect must be contained under its app-owned root and validated on each read and publish; arbitrary user paths must not be accepted as artifact IDs.

**Invariants:** No silent identity transfer to an unrelated directory; no automatic discovery or file creation under the source root; missing != empty; unreadable != missing. Relink requires user confirmation and comparison of available verified root evidence, and *always* marks prior inventory freshness for ST-04 reassessment. Atomic versioned writes; corrupt/unsupported metadata does not overwrite last-good state. Preserve prior Runs/Results after stale binding (future stages); they may display missing-source status.

## UI parity

Reference `#detect/setup` root states and `#detect/recordings` Relink flow in the [UX matrix](../design/UX_PARITY_MATRIX.md). Native folder picker cancel preserves verified binding; show previous/new locations and consequences before confirmation. Show one clear empty state and one primary action; do not add stray captions, prototype scenario selectors, developer notes or unverified counts. Use public `alp-ui` and concise researcher-facing `HelpHint` only where choice is ambiguous. Verify keyboard, compact width and ordinary app restart.

## TDD and boundary verification

- `UT-DET-001` — unique identity, schema migration/rejection, app-data ownership and root-reference serialization (no original path in exported metadata).
- `UT-DET-002` — valid/missing/inaccessible/changed/relink state decisions, confirmation and stale inventory invalidation; reject unrelated-root takeover.
- `UT-DET-003` — containment, Unicode/casefold/Windows-reserved path policy, atomic update and recovery decisions.
- `IT-DET-001` — real temporary directory create→reopen→move→explicit relink via native Qt; cancel/denied access keep prior Collection intact (`TD-UI`, `TD-PATH`, `TD-CACHE`).
- `IT-DET-002` — actual app-owned files and permissions, corrupt/unsupported manifest, interrupted write, symlink escape and untouched recording bytes (`TD-PATH`, `TD-FAIL`).

Write tests first for each owning seam; execute targeted tests, relevant existing shell/Train settings regression, actual Qt integration, static checks, and full feasible ordinary unit/integration suites **before implementation commit**. No whole-Studio E2E before ST-11; no soak without separate initiation. Record exact evidence/blocked native platforms.

## Entry and exit gate

Inspect `AGENTS.md`, routing, this spec, relevant persistence/settings/Qt code and exact indexed cases only. ST-02 approval is an owner decision, not retroactive proof of any unexecuted check. **Close when** persisted Collection identity, safe Relink, privacy/non-mutation, native states and scoped tests are reviewed; record field names/versions and storage layout as the ST-04 handoff. Commit on this branch; reviewed local integration to `detect` only, never push or start ST-04 without the stage gate.
