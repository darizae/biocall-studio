# Review prototype acceptance checklist

**Gate:** owner inspection is pending. This is a **browser design/prototype audit**, not a declaration that RV-01–RV-08 or native `alp-ui` GUI tests have passed. At the time of this historical prototype audit, native Review had not been implemented. It is now present on Studio `main`; that later source implementation does **not** retroactively turn browser prototype checks into owner-approved native or installed-app proof.

## Investigation baseline

The archive's structure, `AGENTS.md`, `docs/agent/ROUTING.md`, `docs/IMPLEMENTATION_SEQUENCE.md`, Review index and all **eight sequential RV-01–RV-08 specifications** were inspected. The two mandatory owner-feedback documents (`docs/specs/manual_revision_specs/detect-revision-notes.txt` and `UI-pass-revision-spec.md`) were read in full. The parity matrix, prototype acceptance, `ALP_UI_CONSUMER_CONTRACT.md`, `docs/PREDICTION.md` and implemented `REV-05-output-size-preflight.md` were inspected. The actual native Studio shell, Train window, Detect workspace/results, public `alp-ui` imports, screenshot evidence and the earlier `studio-detect/` HTML/CSS/JS prototype were inspected; the latter was rendered in Chromium.

**Missing requested referenced files: none.** This deliverable updates prototype files inside `docs/design/prototypes/studio-review/` **and only four Review planning documents**: `docs/specs/review/README.md`, `RV-03`, `RV-05`, and `RV-08`. No native code, scientific/persistence contracts, release work or test indexes were changed. The new shortcut interaction and tooltip copy are an **owner-requested proposal pending final sign-off**, not retroactively approved baseline wording.

## Scientific and workflow audit

| Requirement and specification | Prototype implementation / exercise | Status and limitation |
|---|---|---|
| Completed Detect Result only; no direct file import (`RV-01`, `RV-05`) | Choose Result lists completed Meadow CNN, original Marsh CNN and RF-refined Marsh Results; Start session; Empty Results scenario | **Verified** simulated Result intake; no real Result reader |
| RF acceptance gate (`RV-01`, `RV-07`) | Original Marsh CNN Result exposes 26 candidates independently; Marsh RF-refined Result exposes **17 eligible accepted detections only**, no rejected/unscored tab | **Verified** fixture semantics; no actual RF inference |
| Three states, independent provenance (`RV-02`, `RV-05`, `RV-06`) | Distinct circle/check/cross shapes and labels; One by one origins; Finalized decisions show human-accepted vs model-only vs excluded | **Verified** browser state; no real provenance file |
| Accept all only changes unreviewed (`RV-02`, `RV-05`) | Accept all → approved confirmation → count/rejected unchanged; Undo | **Verified** including 50,000 scenario |
| Gallery dense, filter, multi-select, cache states (`RV-05`) | Gallery; filter; tile selection; bulk labels/clear cache; loading/uncached/error media | **Verified** headless Chromium; images are synthesized |
| List dense, sort, scalable (`RV-05`, `RV-08`) | List, recording-name search, filter/sort, bounded 35-row viewport; 50,000 scenario | **Verified** prototype responsiveness; no native 50k qualification |
| Individual spectroscopy and audio (`RV-03`, `RV-05`) | One by one: time/frequency axes, detected interval, 6s playable WAV, seek, buttons, fixed F/D/S + J/K/L home-row shortcuts, arrow/Space alternatives, Undo, tooltip disclosure, auto-advance | **Verified** local synthesized samples; no real source recordings |
| Only one Open session; Close ≠ Finalize (`RV-02`, `RV-05`) | Sessions → Close → Resume restores last focused item/view; Start blocked while another Open; Save failure demo prevents false commits | **Verified** browser-state transitions |
| Partial finalization warning, frozen parent, successor (`RV-02`, `RV-05`) | Finalize partial → exact approved warning → Exports; read-only Finalized; Continue in new session | **Verified** independent objects; no real immutable snapshot file |
| Navigate away without auto-close; global exit warning (`RV-05`, `RV-08`) | Studio/Train/Detect navigation; Exit Studio from Detect/Train with Open or Open + processing | **Verified** including combined warning; browser tab close uses ordinary `beforeunload` only |
| Hybrid cache, Generate all, cancel, eviction, clear/retry (`RV-03`, `RV-04`, `RV-05`) | Spectrograms; Gallery prefetch; Generate all/Cancel; single/selection/all clear; renderer retry; regenerate | **Verified** cache **logic**, not native generation/disk cache |
| REV-05 preflight (`RV-04`, `RV-06`, `REV-05`) | Storage estimates + free space, tight/unknown confirmations, insufficient blocks, Combined WAV error | **Verified** decision simulation; numeric estimates/capacity are illustrative |
| Export only after finalization; formats and exclusions (`RV-06`, `RV-07`) | Export corpus: 3 formats, destination input, progress/cancel/failure/retry, provenance, Show in folder | **Verified** flow; no real WAV/TSV export |

## UX audit against native evidence and owner feedback

| Review item | Outcome | Status |
|---|---|---|
| Native integration | Light sidebar/top bar, dense rows, restrained green primary control, typography/surface styling informed by actual Train/Detect evidence and existing Studio/Detect prototype | **Visually inspected** at 1280 px and 700 px, screenshots in `evidence/` |
| No unwanted onboarding or dashboard UI | Single global prototype notice; no welcome tutorial in Review, repeated explainer cards, IDs, hashes, raw paths or technical config exposed as primary content | **Inspected** |
| Approved RV-05 wording | Approved action labels and main consequential confirmations used; REV-05 storage wording shown in the storage area | **Inspected**; genuinely new labels collected below for owner review |
| Three cohesive views | Same session labels/progress in Gallery, List and One by one; a single selection action area; contextual large spectrogram and few focused controls | **Inspected and exercised** |
| Compact and constrained widths | 700 px Gallery/detail and 520 px detail with scrollable but reachable controls | **Browser-checked** for overflow and visibility; 150% native Qt scaling **not tested** |
| Accessibility | Text-plus-shape statuses, input labels, focusable controls, fixed shortcuts, hover/focus readable HelpHints, single reference dialog, Escape/back-focus and dialog Tab trap | **Browser-checked** at 1280/700/520 px; full screen-reader/native `alp-ui` audit **not performed** |

## Interaction audit and actual test evidence

Executed headless **Chromium / Playwright** browser checks using local-route fulfillment (see README), with no JS runtime errors captured:

- **69 / 69 fixed-shortcut and tooltip checks** in [`evidence/browser-shortcut-checks.txt`](evidence/browser-shortcut-checks.txt): F/D/S labels and save-then-auto-advance, J/K/L and arrow/Space navigation/playback, Undo, legacy-key inactivity, modifier/input/seek/modal suppression, hover/focus and accessible key metadata, dialog listing, Gallery/List search and 700/520 px viewport bounds.
- **17 / 17 focused tooltip/spec-sync checks** in [`evidence/browser-tooltip-sync.txt`](evidence/browser-tooltip-sync.txt): both exact preapproved HelpHints, accessible hover/focus, dialog focus trap and dismissal, Finalized keyboard safety, search-view persistence and no script errors.
- **57 / 57 primary checks** recorded in [`evidence/browser-checks.txt`](evidence/browser-checks.txt): navigation, intake, RF count, Gallery/List filtering, sorts, multi-select, labels, Undo, Accept all, generated WAV playback/seek, cache clear/cancel/regeneration, finalize/export, successor, exit from Detect, bounded 50,000 rendering, 700/520 px layout.
- **22 / 22 recovery checks** recorded in [`evidence/browser-edge-checks.txt`](evidence/browser-edge-checks.txt): missing/changed recordings, relink, retry, insufficient/tight/unknown capacity, refusal/confirmation, simultaneous open+processing exit, export failure/retry, combined-WAV limit and individual-WAV fallback.
- **20 / 20 specification regression checks**, **1 / 1 session-resume check** and **3 / 3 provenance checks** recorded in [`evidence/browser-spec-audit.txt`](evidence/browser-spec-audit.txt): CNN/RF parent selection, restored scroll/view, sorted full-set focus navigation, preservation of Gallery filters, save/close/finalize/exit failure rollbacks, blocked playback/generation/export with invalid source, resumed focused item, single-item bulk origin, individual reconfirmation of batch acceptance and provenance undo.
- **Shortcut evidence:** [`12-shortcut-reference.png`](evidence/12-shortcut-reference.png), [`13-shortcut-tooltip-700.png`](evidence/13-shortcut-tooltip-700.png), [`13-shortcut-tooltip-520.png`](evidence/13-shortcut-tooltip-520.png).
- **Inspection screenshots:** [`01-choose-result.png`](evidence/01-choose-result.png), [`02-gallery.png`](evidence/02-gallery.png), [`03-list.png`](evidence/03-list.png), [`04-one-by-one.png`](evidence/04-one-by-one.png), [`05-sessions.png`](evidence/05-sessions.png), [`06-spectrogram-storage.png`](evidence/06-spectrogram-storage.png), [`07-finalize-warning.png`](evidence/07-finalize-warning.png), [`08-export.png`](evidence/08-export.png), [`09-compact-gallery.png`](evidence/09-compact-gallery.png), [`10-compact-one-by-one.png`](evidence/10-compact-one-by-one.png), [`11-narrow-one-by-one.png`](evidence/11-narrow-one-by-one.png).

For full RV-01–RV-08 coverage, see [`SPEC_COVERAGE_AUDIT.md`](SPEC_COVERAGE_AUDIT.md).

**Unverified / intentionally simulated:** direct localhost browser-navigation execution (restricted by runtime), restoration via real-origin browser page reload, real `alp-ui`/Qt operation, real filesystem/disk capacity, recording relocation and checksum validation, export artifact correctness and user filesystem opening, actual multi-worker generation, assistive technology screen-reader testing and 50,000-candidate **native** memory/latency benchmarks. The browser UI/logic checks are **not** scientific test evidence.

## Genuinely new UI copy proposed for owner approval

These are small additions beyond RV-05/REV-05's locked approved wording, not replacement workflows. The shared demo-only banner and Prototype controls are **not product copy** and do not require adoption in the native application.

| Surface | New wording / HelpHint / action to approve | Reason |
|---|---|---|
| Workspace navigation | **Sessions**, **Spectrograms**, **Exports** | Labels for direct access to approved functions |
| Intake and List table | **Kind** (CNN / RF-refined); **Score** (numeric, not a calibrated probability) | Researcher-readable Result type and compact candidate sorting |
| List/Gallery search | **Recording**, **Search recordings** | New compact recording-name filter; required List searchability in RV-03 |
| Shortcut reference & hints | **Keyboard shortcuts**, “Show the fixed Review keyboard shortcuts.”, “Call · F”, “Not a call · D”, “Clear label · S”, “Previous · J or ←”, “Play / Pause · K or Space”, “Next · L or →”, “Undo last label action · Ctrl/⌘+Z” | Owner-requested fixed home-row mapping; tooltips on hover/focus, not recurring captions |
| Open candidate | “Open in One by one” | Same action hint in Gallery and List |
| Disabled session actions | “Close the open session before starting another.” / “Close the open session before resuming another.” | Browser disabled-button title; also same wording in actionable dialog |
| Multi-selection | **Select filtered**, **Deselect** | Bulk selection operations across a filtered view |
| Single-open-session guard | “Close the open session before starting another.” / “Close the open session before resuming another.” | Explain disabled/conflicting session action |
| Source repair | **Relink recordings folder**; “Choose the restored recordings folder to continue.” | Action paired with the approved missing-recording warning; native relink will need a real picker |
| Spectrogram placeholder | “Spectrogram not generated”, “Recording unavailable”, “Generating…” | Short in-tile states when the approved full error text is unsuitable inside a small thumbnail |
| Session provenance | “Reviewed individually”, “Accepted in a batch”, “Model detection” | Distinguish individual human verification, batch acceptance and unreviewed predictions |
| Export/finalized summary | “Human accepted”, “Model only”, “Excluded”; “Finalize a session before exporting its corpus.” | Visible provenance and export prerequisite without an instructional panel |
| Storage confirmation | “Storage may run low while this runs. Continue?” | Illustrative tight/unknown capacity confirmation; native code must use actual REV-05 decision wording |
| Recoverable operation notifications | “Spectrograms cleared.”, “Export cancelled.”, “Choose a destination to export.” | Concise action/error responses not enumerated by RV-05 |

**Approval status: pending, including the fixed-key/tooltip additions.** No new wording above is represented as already owner-approved. Approved main workflow strings were not replaced, and no extra export-as-detected route was created.


## Spectrogram preset and WAV-preview acceptance addendum (2026-11-03)

The owner approved the eight product directions in `docs/specs/review/SPECTROGRAM_DECISIONS.md`; these are *not* permission to waive scientific numeric verification or native performance measurements. The prototype's 17 dedicated new smoke assertions (recorded in `evidence/spectrogram-settings-browser-checks.txt`) cover the following observable paths:

| Browser interaction | Observed / expected acceptance | Native obligation |
|---|---|---|
| Review → Spectrograms → Settings | Default is protected; five simple controls; collapsed Advanced has exactly three additional controls | Public `alp-ui` selectors and short HelpHints; real keyboard focus, screen reader and compact window |
| New/edit/discard/save preset | Unsaved settings have no effect until confirmed; unique user names; Default cannot edit/delete | Persistence rollback and durable preset revisions; unit-test invalid and malformed settings |
| Preset save impact | Open/Closed/Finalized usage counts; **Save preset** leaves *all* session snapshots and caches untouched | SQLite transactional boundary; explicit session reference counting, deletion and rename |
| Save and use in session / Change preset | Changes only the current Open session on deliberate choice; warning and illustrated time/storage costs; labels unchanged | REV-05 cache-volume admission, compare-and-swap epoch; reject late workers and preserve last valid snapshot on failure |
| Test WAV → Compare → Save example | Bounded real local WAV in-memory browser render; side-by-side; deliberate example image saving, enlargement and removal; no source WAV retained | Native Python STFT numeric parity and independent test-file lifecycle, no Detect/Review ingestion |
| Create/Resume/Finalized/successor | Preset at creation; snapshots survive editing/deletion; Finalized read-only | RV-02 and RV-06 restart/finalization and immutable export tests |
| Axes/thumbnail/detail and 50k work | Prototype labels derive from selected range/context; generated images remain mock assets; bulk uses thumbnails only | Frame-accurate Qt overlay/ticks; HiDPI and source-clamp measurements; cache calibration at 1k/50k |
| Label shortcuts and compact view | Focused F shortcut regression and 520 px no-horizontal-scroll regression passed | Full previously approved shortcut/HelpHint/native parity suite still due |

**Evidence boundary:** these 17 checks ran in an isolated, headless Chromium test harness, using an in-memory browser storage shim because direct navigation to localhost was not permitted. They are not native Review, lifecycle-disk or spectrogram-science qualification. The pre-existing broader browser regression suite was not rerun after this amendment. Missing `docs/design/UX_PARITY_MATRIX.md` and `docs/design/PROTOTYPE_ACCEPTANCE.md` in the provided ZIP prevent claiming parity against those two requested documents.
