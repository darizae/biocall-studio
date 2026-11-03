# RV-07 — Studio integration, application exit and Detect export retirement

> **Status:** Owner-approved planning; not implemented. Begin only after explicit stage authorization and the predecessor's owner gate.

## Strict ownership and exclusions

**Owner:** `studio/application` coordinator/shell/route and the minimal Detect UI/controller changes to remove *new* corpus-export actions; Review UI registration. **Entry:** approved RV-06. Do not delete old Detect exports, change immutable Results or rewrite historical receipts. This stage is a targeted shell + ownership migration, **not** full Train→Detect→Review scientific E2E (reserved for RV-08).

## Migration and application lifecycle contract

1. Replace Studio's Review placeholder with retained Review controller/view; keep Train and Detect controller/Worker lifetimes independent of Review navigation. Use explicit one-open-session admission policy and a narrow query into Review, not an import of its annotation persistence into Train/Detect.
2. Navigating from Review to Train/Detect leaves the Review session **Open**; returning restores item, filter, scroll/selection and work. Explicit Close saves/pauses, without finalizing; Resume still requires single-session admission. A finalized successor is a **new** session.
3. Every application exit route (window close, menu, from Train, Detect or Review) must query an open Review session even when Review is hidden. If open, use approved “A Review session is still open. Save and exit?” with **Keep app open / Save and Exit**. If open and processing active, use the approved combined message **once**, not stacked confirmations. Keep existing Train/Detect-only shutdown behavior when no Review session is open.
4. Save and Exit performs durable checkpoint and safe session closure, coordinates all running supervised operations/leases, then exits. If persistence or Worker cancellation fails, **remain open and report actionable failure**, never show false successful exit. Keep app open does not kill Worker or mutate session. Test rapid repeated quit, Escape/focus, stopping during cache/export, another workspace visible, restart and orphan-process safety.
5. Only after RV-06 Review export success: remove Detect export initiation buttons, routes, callbacks/controller entry and new-export writes. No deep link or stale action must launch a new Detect corpus export. Retain read-only historical Detect export listings/receipts and validation/reopen; preserve all prior output bytes and user data. Do not globally delete a legacy engine while older receipts still depend on it.
6. Update `docs/PREDICTION.md`, `docs/design/UX_PARITY_MATRIX.md`, relevant Studio/Detect routing docs and existing regression cases **in this stage** to reflect current ownership and real behavior. Do not duplicate the UX style guide or build an unapproved export shortcut.
7. Real native Qt from each workspace: open-session quit confirmation, combined Worker confirmation, Save and Exit success, cancel, blocked persistence, blocked stopping, same-session reopen; no impact on Train behavior. Run targeted `IT-STU-*`/`IT-DET-*` regressions. Whole-Studio source integration stays RV-08.


## Acceptance cases (register in existing test indexes during stage TDD)

| ID | Owner | Positive assertions | Negative / non-mutation assertions |
|---|---|---|---|
| `UT-REVW-012` | RV-07 | cross-workspace exit policy with Open Review, workers and no workers; only one dialog/exit action | Keep app open preserves Run/session; failure saving/stopping cannot permit false exit or mutate Train/Detect operations |
| `IT-REVW-011` | RV-07 | native Studio/Train/Detect/Review navigation with open session, quit from hidden Review, one combined dialog, Save and Exit | cancel/keep-open and worker-stop failure preserves state; no orphan process/incorrect timeout success |
| `IT-REVW-012` | RV-07 | Detect new-export actions/routes truly gone, Review export only; historical Detect exports/reports remain accessible | removed route cannot be reached by deep link/callback; no new writes under Detect export history; old artifacts unchanged |

**Gate:** Owner reviews real native quit/return from all workspaces, no duplicate dialog or dead Detect export path, old outputs still accessible and Train unchanged.

**Next:** RV-08 may be prepared only after this gate is explicitly approved.
