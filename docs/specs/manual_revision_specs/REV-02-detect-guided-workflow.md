# REV-02 — Guided Detect workflow and reachable corpus planning

**Branch:** `detect-rev02-guided-detect`, created from the reviewed local `detect` after REV-01
acceptance. **Predecessor:** REV-01. **Successor:** REV-03. **Status:** planned.

## Outcome and boundaries

Detect presents one understandable sequence: **Setup → Recordings → Run → Results → Export**.
Researchers can see where they are, move backward or forward, prepare a Run only after reviewing
inputs, bulk-include valid recordings and inspect corpus-export choices before selecting
intervals. Use **recordings folder** everywhere in the native UI; `DetectCollectionRef` remains an
internal identity and persistence contract.

This revision changes navigation and presentation-state ownership only. Preserve Model validation,
inventory provenance, inclusion persistence, Run/Worker behavior, candidate/RF decisions, Result
immutability, export freezing/publication and source-WAV non-mutation. Do not change scientific
defaults, artifact schemas, source-time calculations or failure classification. REV-03 owns the
final whole-application wording pass.

## Ordered route behavior

Replace the flat group of unrelated buttons with a keyboard-operable stepper whose labels and
visible chevrons read `Setup → Recordings → Run → Results → Export`. The current step is conveyed
by checked state, accessible name and focus, not color alone. Each page has at most one primary
forward action and one unobtrusive Back action; both use the same route decision as the stepper.
Normal and compact layouts preserve the order without horizontal scrolling.

All five routes are inspectable. Missing prerequisites disable mutating actions and show one
honest empty/readiness state; they do not silently redirect to a different route. Relink proposals
or an active inventory scan may focus Recordings when first raised, but subsequent explicit user
navigation is respected. Folder-picker cancellation preserves the current route and verified
binding.

| Route | Owns | Forward behavior |
|---|---|---|
| Setup | Detection Model and recordings-folder selection only | Continue to Recordings after a folder is bound; scanning may continue there. |
| Recordings | Inventory status, hierarchy and inclusion decisions | Continue to Run; readiness there explains any remaining blocker. |
| Run | Candidate settings, readiness, Start detection, then active/terminal Run detail | Starting stays on Run; a completed Result enables the Results primary action. |
| Results | Result history, recording/candidate exploration, selection and optional RF refinement | Continue to Export with or without a current selection. |
| Export | Format and destination planning, frozen-selection review and export execution | Back returns to Results without discarding presentation choices. |

Move minimum score, window overlap, combine-nearby settings and `Start detection` out of Setup.
Before a Run, the Run page shows those controls plus a compact summary of the selected Model,
included recording count and any single actionable blocker. During and after a Run, the same page
shows progress, cancellation, activity and log/output actions. Starting a Run freezes the same
verified inputs as today and does not require returning to Setup.

## Inventory bulk decision

Add `Include all valid recordings` beside the existing per-selection decisions. It applies an
explicit Included decision to every currently valid WAV in the accepted inventory, including WAVs
previously excluded. Invalid, unsupported, inaccessible and non-WAV entries remain unavailable and
must not be made valid by the bulk action. Directories are not counted as recordings.

Compute the complete replacement decision set outside Qt, validate it against the same inventory
revision, then publish once through the existing atomic decision store. A stale inventory,
cancelled confirmation or write failure leaves every prior decision and readiness state intact.
After success, counts, rows, detail state and Run readiness update from the persisted revision.
The action requires confirmation only when it will replace one or more explicit exclusions; the
dialog states the number affected and defaults to Cancel.

## Model status and `alp-ui` prerequisite

Both CNN intake and optional RF refinement use the same semantic state mapping:

| State | Badge intent | Required visible behavior |
|---|---|---|
| Not selected | `neutral` | No error styling; picker is available. |
| Checking | `warning` | Picker is temporarily disabled and progress is stated. |
| Compatible | `success` | Model name is shown once; redundant verification prose is absent. |
| Incompatible | `danger` | One correction-oriented reason is shown. |
| Missing files | `danger` | Missing/incomplete status is distinct from incompatibility. |

Text and accessible descriptions carry the status independently of color. The installed public
`alp-ui` 0.1.0a0 `Badge` can set intent only during construction, so add and test a public,
validated `Badge.setIntent(intent)` method on a separate
`biocall-studio-dynamic-badge-intent` branch in `../alp-ui`. It must refresh semantic colors and
accessible intent without replacing the widget. Commit and review that repository independently,
reinstall the exact approved SHA, verify `alp_ui.__file__`, and rerun downstream Qt tests. Do not
use application-local badge QSS or patch library internals.

## Export planning without a selection

The Export step is always reachable. With no selected Result or intervals it still shows the
available formats and destination picker, retains those presentation choices for the current app
session, and shows a single disabled export action. It must not create an `ExportSnapshot`, stage
files or claim a frozen selection. If an available Result has selected intervals, entering Export
prepares the existing frozen-selection plan and enables publication only after all current checks
pass. Stale or unavailable sources remain visible as blockers and never become zero candidates.

Changing the Result or its saved selection invalidates a previously prepared plan through the
existing digest/revision rules. Back to Results never mutates the Result selection. Existing
collision, cancellation, stale-source, format-compatibility and no-overwrite behavior remains
authoritative.

## TDD and native verification

- `UT-DET-024` — bulk inclusion includes every and only valid WAV, replaces explicit exclusions
  only after confirmation, rejects stale inventory revisions and preserves the complete prior
  decision document on cancel/validation/write failure.
- `IT-DET-023` — real Qt exercises stepper and Back/forward focus, folder-picker cancel,
  Setup→Recordings→Run preparation, Start detection without returning to Setup, active/completed
  Run transition, bulk inclusion confirmation, CNN/RF dynamic badge intent, and an accessible
  Export page with no selection and no artifact publication. Repeat at normal/compact widths with
  keyboard-only operation and real temporary files.

Add the indexed cases first, then update affected existing Detect integration assertions rather
than weakening them. Run the focused pure/Qt/upstream tests continuously and, before each commit,
all feasible ordinary suites, ruff, test-ID audit and `git diff --check`. Capture native screenshots
for Setup, Recordings, pre-Run, incompatible Model and selection-free Export at normal and compact
width. Record both repository SHAs and installed `alp-ui` origin. No ST-11 whole-Studio E2E or
installer claim belongs here.

## Exit gate

Close when the five-step flow is understandable and keyboard reachable; detection starts from its
own Run page; bulk inclusion is atomic and honest; incompatible Models are visibly and accessibly
dangerous; Export can be planned without a selection but cannot publish; and all existing
scientific/non-mutation contracts still pass. Integrate the reviewed Studio and prerequisite
`alp-ui` commits only under their separate local approval gates, never push, and do not start
REV-03 automatically.
