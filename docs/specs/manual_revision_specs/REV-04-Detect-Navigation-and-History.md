# REV-04 — Detect Navigation and History

## Summary

- Create `detect-rev04-navigation` from reviewed `detect` commit `feff56b`; update
  routing/sequence with REV-04 before ST-11.
- Replace Detect's horizontal five-step strip with a persistent Train-style sidebar: New
  detection, Recordings, Models, Runs, Results, Exports.
- Preserve the guided workflow through explicit Back/Continue actions while allowing direct
  navigation to history and current selections.
- Do not alter Train, detection science, source WAVs, immutable Results, or export formats.

## UI and Navigation

- Give Detect a full-height sidebar and right-hand content area matching Train's responsive
  behavior. Hide Studio's duplicate global header while Detect is open; use a slim Detect header
  for Back to Studio and the active Run.
- At compact width, convert the sidebar to a horizontally scrollable top navigation bar without
  introducing page-level horizontal scrolling.
- Make New detection adaptive:
  - Open Models when no compatible detection model is selected.
  - Open Recordings when the recording review is incomplete.
  - Open the settings/start page when inputs are ready.
  - Open the active Run when one already exists.
- Guided actions remain: Models → Recordings → New detection settings; starting detection opens
  the new Run detail. Remove the old step buttons and chevrons.
- Models: show and change the current detection model and optional Random Forest model. Remove
  duplicate model pickers from Setup/Results; those pages show concise summaries with a Change
  model action.
- Runs: add a newest-first DataTable and nested detail view. Historical selection must not
  replace or mutate the active Run. Completed rows can open their Result; only the active row
  exposes cancellation.
- Results: retain the existing Result history/explorer and route it directly from the sidebar.
- Exports: add a history table, detail page, and nested new-export planner. Results opens the
  planner; successful publication offers Show in folder and View in Exports.
- Add no sidebar tooltips, overlines, section captions, decorative badges, or redundant helper
  paragraphs. Preserve only the nine approved plain-language Detect HelpHints. Use danger styling
  plus one corrective sentence for incompatible or unavailable inputs.

## Interfaces and Persistence

- Add typed Detect routes for the six sidebar destinations and nested Run/export detail/planner
  routes, including a single mapping from nested routes to their active sidebar item.
- Add controller-level `selected_run_id`/`selected_run` selection without persisting it; preserve
  selection across refresh when the Run still exists.
- Introduce versioned `ExportHistoryRecord` containing: collection ID, export ID,
  receipt/snapshot digests, Result ID/digest, mode, completion time, selected-call count,
  published-file count, and private destination URI.
- Store one atomic, strict-schema record per completed export under the active Detect Collection's
  existing app-owned `exports/` namespace. Bound loading to 10,000 newest-first records, reject
  symlinks/escapes, and retain valid records when another entry is corrupt.
- Treat the external `ExportReceipt` as authoritative. Opening an export detail verifies it
  asynchronously and distinguishes available, missing, inaccessible, and changed outputs; Show
  in folder is enabled only after verification.
- If external publication succeeds but local history writing fails, keep the export marked
  completed, show one inline warning, and offer Retry saving to history. Never delete or report
  the published corpus as failed.
- Do not backfill, scan for, relink, import, rename, or delete pre-REV-04 exports. Existing output
  folders remain untouched.

## Test Plan

- Add UT-DET-025 for route validation, adaptive New detection entry, nested-route highlighting,
  and invalid-route rejection.
- Add UT-DET-026 for export-history schema, ordering, duplicate identity, containment, strict
  loading, and atomic-write recovery.
- Add IT-DET-025 for real Qt sidebar navigation, Models/Recordings/New detection flow, Runs
  list/detail, active-run indicator, keyboard focus, and normal/compact layouts.
- Add IT-DET-026 for multiple exports from one Result, restart persistence, background
  verification, missing/inaccessible/changed destinations, symlink/corrupt records, cancellation,
  and post-publication history-write failure without source mutation.
- Update IT-DET-023 only to replace obsolete stepper assertions with the same guided-flow
  invariant through sidebar plus Back/Continue; retain IT-DET-024 as the exact copy/HelpHint
  regression.
- Capture native REV-04 screenshots for New detection, Models, Runs list/detail, and Exports
  list/detail at normal and compact widths. Run targeted tests first, then all feasible
  unit/integration suites, Ruff, and the test-ID audit before committing; do not run ST-11's
  whole-Studio E2E.

## Assumptions

- Runs, Results, and Exports are scoped to the active Detect Collection; the two current Model
  selections remain Detect-wide as implemented.
- The existing uncommitted README and development-guide changes are user-owned and remain
  untouched.
- Use `.venv/bin/python -m pytest` until the stale `.venv/bin/pytest` interpreter path is rebuilt;
  the two relevant current UI baseline tests pass through that invocation.
- Delivery is a reviewed local commit and merge to `detect` only after approval; never push.
