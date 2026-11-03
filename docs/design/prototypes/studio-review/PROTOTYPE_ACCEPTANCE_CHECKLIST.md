# Review prototype acceptance checklist

**Gate:** owner inspection is pending. This is a **browser design/prototype audit**, not a declaration that RV-01–RV-08 or native `alp-ui` GUI tests have passed. Native Review remains unimplemented.

## Investigation baseline

The archive's structure, `AGENTS.md`, `docs/agent/ROUTING.md`, `docs/IMPLEMENTATION_SEQUENCE.md`, Review index and all **eight sequential RV-01–RV-08 specifications** were inspected. The two mandatory owner-feedback documents (`docs/specs/manual_revision_specs/detect-revision-notes.txt` and `UI-pass-revision-spec.md`) were read in full. The parity matrix, prototype acceptance, `ALP_UI_CONSUMER_CONTRACT.md`, `docs/PREDICTION.md` and implemented `REV-05-output-size-preflight.md` were inspected. The actual native Studio shell, Train window, Detect workspace/results, public `alp-ui` imports, screenshot evidence and the earlier `studio-detect/` HTML/CSS/JS prototype were inspected; the latter was rendered in Chromium.

**Missing requested referenced files: none.** This prototype only adds files inside `docs/design/prototypes/studio-review/`; it does not change native code, scientific/persistence contracts, release work or test indexes.

## Scientific and workflow audit

| Requirement and specification | Prototype implementation / exercise | Status and limitation |
|---|---|---|
| Completed Detect Result only; no direct file import (`RV-01`, `RV-05`) | Choose Result lists completed CNN/RF Results; Start session; Empty Results scenario | **Verified** simulated Result intake; no real Result reader |
| RF acceptance gate (`RV-01`, `RV-07`) | Marsh RF-refined Result exposes **17 eligible accepted detections only**, no rejected/unscored tab | **Verified** fixture semantics; no actual RF inference |
| Three states, independent provenance (`RV-02`, `RV-05`, `RV-06`) | Distinct circle/check/cross shapes and labels; One by one origins; Finalized decisions show human-accepted vs model-only vs excluded | **Verified** browser state; no real provenance file |
| Accept all only changes unreviewed (`RV-02`, `RV-05`) | Accept all → approved confirmation → count/rejected unchanged; Undo | **Verified** including 50,000 scenario |
| Gallery dense, filter, multi-select, cache states (`RV-05`) | Gallery; filter; tile selection; bulk labels/clear cache; loading/uncached/error media | **Verified** headless Chromium; images are synthesized |
| List dense, sort, scalable (`RV-05`, `RV-08`) | List, filter/sort, bounded 35-row viewport; 50,000 scenario | **Verified** prototype responsiveness; no native 50k qualification |
| Individual spectroscopy and audio (`RV-03`, `RV-05`) | One by one: time/frequency axes, detected interval, 6s playable WAV, seek, buttons, C/X/U/Space/arrow keys, auto-advance | **Verified** local synthesized samples; no real source recordings |
| Only one Open session; Close ≠ Finalize (`RV-02`, `RV-05`) | Sessions → Close → Resume; Start blocked while another Open | **Verified** browser-state transitions |
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
| Accessibility | Text-plus-shape statuses, input labels, buttons, Escape confirmation dismissal, keyboard shortcuts, focusable controls | **Interaction-checked**; full assistive technology audit **not performed** |

## Interaction audit and actual test evidence

Executed headless **Chromium / Playwright** browser checks using local-route fulfillment (see README), with no JS runtime errors captured:

- **57 / 57 primary checks** recorded in [`evidence/browser-checks.txt`](evidence/browser-checks.txt): navigation, intake, RF count, Gallery/List filtering, sorts, multi-select, labels, Undo, Accept all, generated WAV playback/seek, cache clear/cancel/regeneration, finalize/export, successor, exit from Detect, bounded 50,000 rendering, 700/520 px layout.
- **22 / 22 recovery checks** recorded in [`evidence/browser-edge-checks.txt`](evidence/browser-edge-checks.txt): missing/changed recordings, relink, retry, insufficient/tight/unknown capacity, refusal/confirmation, simultaneous open+processing exit, export failure/retry, combined-WAV limit and individual-WAV fallback.
- **Inspection screenshots:** [`01-choose-result.png`](evidence/01-choose-result.png), [`02-gallery.png`](evidence/02-gallery.png), [`03-list.png`](evidence/03-list.png), [`04-one-by-one.png`](evidence/04-one-by-one.png), [`05-sessions.png`](evidence/05-sessions.png), [`06-spectrogram-storage.png`](evidence/06-spectrogram-storage.png), [`07-finalize-warning.png`](evidence/07-finalize-warning.png), [`08-export.png`](evidence/08-export.png), [`09-compact-gallery.png`](evidence/09-compact-gallery.png), [`10-compact-one-by-one.png`](evidence/10-compact-one-by-one.png), [`11-narrow-one-by-one.png`](evidence/11-narrow-one-by-one.png).

**Unverified / intentionally simulated:** direct localhost browser-navigation execution (restricted by runtime), restoration via real-origin browser page reload, real `alp-ui`/Qt operation, real filesystem/disk capacity, recording relocation and checksum validation, export artifact correctness and user filesystem opening, actual multi-worker generation, assistive technology screen-reader testing and 50,000-candidate **native** memory/latency benchmarks. The browser UI/logic checks are **not** scientific test evidence.

## Genuinely new UI copy proposed for owner approval

These are small additions beyond RV-05/REV-05's locked approved wording, not replacement workflows. The shared demo-only banner and Prototype controls are **not product copy** and do not require adoption in the native application.

| Surface | New wording / HelpHint / action to approve | Reason |
|---|---|---|
| Workspace navigation | **Sessions**, **Spectrograms**, **Exports** | Labels for direct access to approved functions |
| Single-open-session guard | “Close the open session before starting another.” / “Close the open session before resuming another.” | Explain disabled/conflicting session action |
| Source repair | **Relink recordings folder**; “Choose the restored recordings folder to continue.” | Action paired with the approved missing-recording warning; native relink will need a real picker |
| Spectrogram placeholder | “Spectrogram not generated”, “Recording unavailable”, “Generating…” | Short in-tile states when the approved full error text is unsuitable inside a small thumbnail |
| Session provenance | “Reviewed individually”, “Accepted in a batch”, “Model detection” | Distinguish individual human verification, batch acceptance and unreviewed predictions |
| Export/finalized summary | “Human accepted”, “Model only”, “Excluded”; “Finalize a session before exporting its corpus.” | Visible provenance and export prerequisite without an instructional panel |
| Recoverable operation notifications | “Spectrograms cleared.”, “Export cancelled.”, “Choose a destination to export.” | Concise action/error responses not enumerated by RV-05 |

**Approval status: pending.** No new wording above is represented as already owner-approved. Approved main workflow strings were not replaced, and no extra export-as-detected route was created.
