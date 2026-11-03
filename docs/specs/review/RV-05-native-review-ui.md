# RV-05 — Native researcher-facing Review workspace

> **Status:** Owner-approved planning spec, NOT implemented. Do not start implementation or infer test passes from this document. Read [`AGENTS.md`](../../../AGENTS.md) and [`docs/agent/ROUTING.md`](../../agent/ROUTING.md), then this stage and only dependencies needed by its code. No push, merge, tag or release without the owner's separate authorization.

**Sequence:** RV-05 begins only after RV-04 has passed its owner-reviewed gate.

**Series:** [Locked scope, prerequisites and coverage](README.md) · [Status](../../IMPLEMENTATION_SEQUENCE.md)

## Strict ownership and exclusions

**Owner:** `review/gui` and a narrow Review controller/view-state adapter. **Entry:** approved RV-04 (thus RV-01–03 complete). Use only public installed `alp-ui` primitives with native PySide6; no upstream UI changes without independent library branch and tests. Do not expose a second direct-export route, build an ad hoc full-recording annotator, add RF-rejected filters or move Detect exports here before RV-06/07. A Review UI may not advertise nonfunctional final-export actions before RV-06 completes.

## Native UI states, interactions and owner-approved wording

### Structure, navigation, and focus

1. **Review landing / no session:** show available verified completed Detect Results by recognizable name, Result kind (CNN/RF), date and eligible count. **Choose Result** then **Start session**; if existing Closed/Finalized sessions exist, make them accessible without a new route maze. If the Result is empty, use **No detections to review.** No random folders or standalone annotation imports.
2. **Open session header:** editable human session name, `Open` status, concise reviewed count/progress and session actions. One persistent switch between Gallery, List and One by one. `Close session` and `Finalize` should be findable without a cluster of competing buttons. The navigation path and saved view state must survive leaving Review for Train/Detect/Studio and returning.
3. **Gallery:** efficient thumbnail grid ordered by deterministic source recording/time (unless user selects a sort), row-local label symbol, contextual audio and keyboard navigation. Filter All/Unreviewed/Call/Not a call; multi-select and batch operations use one discoverable action area rather than per-tile buttons. Show a genuine placeholder/spinner only for images actually generating.
4. **List:** compact sortable, **recording-name searchable** model/view for tens of thousands; human-readable recording/time, duration, prediction information where genuinely useful, label status and availability. Select many for labeling/cache actions as appropriate; avoid hidden IDs and per-row heavy icons/widgets. No machine-generated explanation columns.
5. **One by one:** large detailed spectrogram with marked candidate interval, clip seek/play/pause, **Previous**, **Next** buttons, three states/actions and persistent reviewed progress. On Call/Not a call: persist first, then advance to next unreviewed. Previous/Next work regardless of label state, and the **fixed, non-configurable** keyboard shortcuts in the table below are discoverable through one **Keyboard shortcuts** listing plus concise action-button hover/focus tooltips (not captions per button). Disable impossible navigation clearly; no dead ends when all items are reviewed.
6. **Cache controls:** lightweight storage information near Generate all, the manual Clear spectrograms action reachable from multi-selection and single item; no repeated explanatory cards. Automatic eviction generally silent; if image unavailable, show retry/actionable failure without altering label. Cache deletion must not be mislabeled “Delete annotation”.
7. **Finalization/export:** explicit Finalize after session work. If Unreviewed >0, one warning; then show export destination, Storage estimate and format choice. Completed export offers **Show in folder**. New export from the same finalized session remains possible. On failure/cancel, navigate back to same finalized session, not to a blank workflow.
8. **Closed and Finalized:** Closed shows **Resume**; Finalized shows read-only labels/exports and **Continue in new session**. Starting a successor produces its own editable session, not an in-place toggle. Human-readable parent context may be included in details when genuinely necessary, never raw UUID/hash captions.
9. **Global exit:** exit initiated by macOS window close/menu, Studio, Train or Detect all invokes the same policy. Correct default/cancel focus, keyboard/escape, no double confirmation for simultaneous Worker and open session. Preserve existing operation text when no Review session exists.

### Spectrogram presets, Advanced and independent WAV preview (owner decision 2026-11-03)

**Placement:** **Review → Spectrograms → Settings** is the home for preset configuration, with compact **Spectrogram preset** selector at **Start session**. The Spectrograms cache page retains its Generate all, Cancel, Retry, Clear spectrograms and REV-05 storage presentation. **One protected Default preset** initially selected; researcher creates uniquely named user presets. All *user* presets allow an unsaved draft **Edit**, Rename, Save changes, Delete; built-in Default must be duplicated with New preset before modification. Avoid extra app-wide navigation, dashboards, long explanatory cards and per-item setting widgets. [Owner decision log](SPECTROGRAM_DECISIONS.md) and [scientific pre-spec](SPECTROGRAM_GENERATION_INVESTIGATION.md) govern exact control/copy and the unqualified native defaults.

**Five simple selectors:** Frequency range (default 4.2 kHz; 3/4.2/8 kHz), Sound detail (Fast changes/Balanced/Close pitches), Time around call (1/2/3 s *on each side*, default 2), Contrast (40/50/65 dB, default 50) and Colors (Magma/Viridis). **Advanced** is collapsed by default and contains **only three** proposed researcher-oriented controls: Exact sound window (Use Sound detail choice or custom 20–100 ms), Window overlap (50/75%) and Lowest frequency (0/100/300 Hz). An advanced custom window overrides Sound detail visibly; never show contradictory simultaneous values. Clamp/validate against source sample rate/Nyquist, reject frequency floor ≥ top frequency, and explain unrenderable/short WAV rather than fabricate an image. Present human-readable short HelpHints for all eight controls (the pre-spec is the copy register); provide pointer and keyboard focus, with correct `alp-ui` use and accessible selector semantics. Exact advanced numeric caps and output tiers are experimental qualification targets, not a waiver of owner approval for later visible changes.

**Try before saving:** **Test WAV** opens a native local WAV picker *only for transient settings comparison*, completely separate from Review/Detect ingestion and from source relinking. In a bounded preview show axes outside the image, a side-by-side **Compare** against the saved version/Default, and **Save example** (explicit user action, stored derivative only in app-owned limited storage; not the WAV). An unsaved preview is not persisted as an example automatically. Show a few saved examples by preset and revision; after edit, label old examples as created with an **earlier version**, do not misrepresent them as current. No local absolute WAV path in portable saved preset or diagnostics. Prototype demo values and static sample assets are clearly illustrative; in native tests use genuine WAV-derived samples.

**Save/edit consequences:** `Save changes` opens one confirmation showing how many Open/Closed/Finalized sessions refer to that preset or older revision. **Save preset** affects future uses only; existing sessions and caches do not regenerate. When the current Open session uses this preset, offer explicit **Save and use in this session**, with the cache invalidation statement and REV-05 incremental time/size/free-space information, then atomically switch **only that Open session**. Otherwise use **Change preset** from the Open session header or Spectrograms page; show old→new preset, affected images, cost and one confirmation. Closed must Resume; Finalized is read-only, successor inherits prior effective settings independently. Confirm Delete and note saved examples go away, not session settings. Preserve approved concise copy and shortcut mapping without adding modal overload for routine test/preview operations.

**Axes:** One by one uses data-only image with UI-generated time and frequency axes/ticks and detection overlay from exact metadata; Gallery uses a compact overlay, List need not show an image. Neither status nor sample content may imply an unmeasured live scientific render in the browser prototype. Native Qt handles HiDPI resizing from RV-03 geometry. Bounded preview work, focus return, error/retry, validation, save rollback and 50k model performance require real Qt qualification.

**Qualification extension:** `UT-REVW-009`/`IT-REVW-007/008` validate every new selector/HelpHint, preset creation/edit/confirmation, copy, deletion, session-switch and no mutation to labels, Test WAV independence, saved-example disposal, keyboard/modal focus, responsive normal/compact Qt and existing fixed F/D/S/J/K/L shortcut regressions. New copy in [decision register](SPECTROGRAM_DECISIONS.md) requires native owner UX sign-off rather than being silently presented as historical approved wording.

### Fixed Review keyboard shortcuts and tooltip contract — owner-requested design clarification, pending prototype sign-off

This additive RV-05 interaction proposal is reflected in the `studio-review` prototype. It changes **no scientific or session rules** and remains subject to the owner's design-approval gate. The key map is **fixed**: do not expose a remapping preference, hotkey editor or alternate keyboard layout. Assume a conventional English QWERTY keyboard and favor two hands resting on adjacent home-row keys: left-hand `S/D/F` for labels; right-hand `J/K/L` for previous/play/next. The common Call action uses the index finger (`F`), Not a call the middle finger (`D`), and clearing a label the ring finger (`S`); navigation and listening stay under the other hand without reaching for the arrow cluster or mouse.

| Key (fixed) | Action in One by one | Hover/focus tooltip on its visible button |
|---|---|---|
| **F** | **Call**; save, then advance to the next eligible Unreviewed candidate if one exists | **Call · F** |
| **D** | **Not a call**; save, then advance likewise | **Not a call · D** |
| **S** | **Clear label**; change this candidate back to Unreviewed; do not auto-advance | **Clear label · S** |
| **J**, or **←** | **Previous**; move in the current deterministic sorted eligible sequence, including labeled candidates | **Previous · J or ←** |
| **K**, or **Space** | **Play / Pause** the current context clip, respecting missing audio | **Play / Pause · K or Space** |
| **L**, or **→** | **Next**; move in the same sequence, including labeled candidates | **Next · L or →** |
| **Ctrl+Z** (Windows/Linux), **⌘Z** (macOS) | **Undo** the last successful label/bulk Accept all change in the Open Review session | **Undo last label action · Ctrl/⌘+Z** |
| **Esc** | Cancel/close an open dialog without committing an action | No recurring tooltip; native dialog convention |

The **Keyboard shortcuts** button in One by one opens one compact listing of these **same exact bindings**. Label buttons, Previous/Next, Play/Pause and Undo display their specified tooltips on both pointer hover and keyboard focus, with readable contrast and text size and accessible names/shortcut metadata. No permanent tiny `F`, `D`, `S` hints beside every button; no hidden-only shortcut that users must guess. Existing approved **Accept all** and **Clear spectrograms** HelpHint wording remains unchanged (see inventory). A disabled command must not trigger when its shortcut is pressed; any disabled button's shortcut meaning remains available in the single shortcut listing. Only these actions have keyboard-shortcut tooltips; do not flood every UI control with redundant help.

**Scope, focus and safety:** Plain letter shortcuts work only with the One by one view active, and labeling/Undo only when its session is **Open**. Previous/Next and playback may still work in read-only Finalized inspection. Do not intercept letters, Space, ←/→ or Undo while an input, searchable field, combo box, text editor, audio seek slider, accessible textbox or modal has focus. Do not intercept modified letter shortcuts (`Ctrl`, `⌘`, `Alt`) except the documented Undo; ignore key auto-repeat and IME composition. Undo must not hijack Train/Detect/Studio keyboard behavior. Do not auto-advance after a failed save or when clearing a label. Explicit Previous/Next traverses the full sorted *eligible* Result set, independently of the Gallery/List-only filter/search; on returning to Gallery/List, restore those filters/search, selection and scroll position. No RF-rejected/unscored candidate enters that sequence.

The native PySide6 implementation should use supported Qt shortcuts and public `alp-ui` tooltip/HelpHint facilities; visible focus, shortcut collisions and screen-reader exposure must be qualified with real native widget tests. No custom global key handler in unrelated workspaces.

**Presentation standards:** native PySide6 + public `alp-ui` components. Use real Qt screen sizes/normal and compact widths, 100%/150% display scaling where available, light theme compatibility, readable text, accessible names/focus and correct tab order. Status icons must differ in shape/text as well as color. Investigate installed API/owner-approved showcase before proposing new `alp-ui` public components. No custom global CSS/styling that bypasses the library. The owner revision notes explicitly prohibit unnecessary subtitles, overlines, generic success/immutability cards, tiny captions, repeated folder or Result names, developer jargon/IDs and unreadable tooltips. Any HelpHint must explain what an operation *does for a researcher*, not its stored IDs or Worker implementation. Important information remains visible, not tooltip-only.

### Wording inventory (2026-11-02 approved baseline; shortcut tooltip additions pending owner sign-off)

| Surface | Visible text / controls | HelpHint if approved/useful |
|---|---|---|
| Result intake | **Choose Result** · **Start session** | none |
| Session list | **Open** · **Closed** · **Finalized** · **Resume** | none |
| Finalized successor | **Continue in new session** | none |
| Session identity | **Session name** | none |
| View switch | **Gallery** · **List** · **One by one** | none |
| Filters | **All** · **Unreviewed** · **Call** · **Not a call** | none |
| Individual labels | **Call** · **Not a call** · **Clear label** | Fixed shortcut tooltips: “Call · F” · “Not a call · D” · “Clear label · S” (only in One by one) |
| Bulk labels | **Accept all** | “Marks all unreviewed detections as calls. Existing labels won't change.” |
| Playback/navigation | **Play** · **Pause** · **Previous** · **Next** | Fixed shortcut tooltips: “Play / Pause · K or Space” · “Previous · J or ←” · “Next · L or →” (only in One by one) |
| Shortcut reference/undo | **Keyboard shortcuts** · **Undo** | “Show the fixed Review keyboard shortcuts.” · “Undo last label action · Ctrl/⌘+Z” |
| Spectrogram generation | **Generate all** · **Cancel** · **Retry** | none |
| Cache management | **Clear spectrograms** | “Frees disk space by deleting generated images. Your labels and recordings stay unchanged.” |
| Storage | **Estimated size** · **Space needed while generating** · **Free space** | Use **implemented REV-05** wording for actual capacity decision; don't contradict its approved copy |
| Session lifecycle | **Close session** · **Finalize** | none |
| Export | **Export corpus** · **Destination** | none |
| Export choices | **Individual WAV files** · **Combined WAV + Raven TSV** · **Both** | none |
| Completed export | **Show in folder** | none |

**REV-05 display synchronization:** the Storage row describes the three required **concepts**. In the existing Train/Detect UI, the implemented shared REV-05 component renders them as **Estimated output**, **Space needed while running**, and **Free on [destination]**. Review and the prototype reuse those headings and the same capacity decisions; do not introduce a second storage wording or preflight policy. The new recording search placeholder in the prototype is **Search recordings** (proposed new text, owner sign-off pending).

| State/error | Exact approved wording |
|---|---|
| Empty Result | “No detections to review.” |
| Rendering progress | “Generating spectrograms: {completed} of {total}” |
| Render cancellation | “Generation stopped.” |
| Missing recording | “Recording not found. Relink the recordings folder to continue.” |
| Changed recording | “This recording has changed since detection. Restore the original file to continue.” |
| Playback error | “Couldn't play this recording.” |
| Renderer error | “Couldn't generate this spectrogram. Retry.” |
| Label persistence failure | “Couldn't save your change. Try again.” |
| Insufficient storage | “Not enough free space. Clear some spectrograms or free up disk space.” |
| Export failure | “Export failed. Your session is unchanged.” |
| Export complete | “Corpus exported.” |
| Combined WAV format limit | “The combined WAV would be too large. Choose individual WAV files instead.” (approved with planning baseline; retain separate source-format errors as needed) |

| Consequential action | Approved text | Buttons |
|---|---|---|
| Accept all | “Accept {count} unreviewed detections? Existing labels won't change.” | **Cancel** / **Accept all** |
| Finalize all reviewed | “Finalize this session? Further changes will require a new session.” | **Cancel** / **Finalize** |
| Finalize partial | “{count} detections haven't been reviewed. They'll be included as model detections. Finalize anyway?” | **Cancel** / **Finalize** |
| Application quit with Open session | “A Review session is still open. Save and exit?” | **Keep app open** / **Save and Exit** |
| Application quit with Open session and processing | “A Review session is open and processing is still running. Exit will save the session and stop the running work.” | **Keep app open** / **Save and Exit** |

**Do not show:** labels like “Candidate ID”, “Dataset ID”, raw checksums or source-frame offsets in primary screens; a second direct-export path; RF-rejected/unscored filters; “Scientific data stays on your computer”; “Immutable and reproducible”; “No sample or simulated artifacts are shown”; “Local only · source WAVs stay read-only”; “Backend default”; decoration about hidden implementation; routine per-label success toasts; extra workflow subtitles or repetitions of the session/Result name. Prohibit faux demo progress, unexplained status badges, tiny tooltip-only meanings, status banners that duplicate the actual action. Do not say “we” in UX copy. These are **omissions**, not strings to render in a disclaimer.

**Only genuinely new copy encountered during implementation** (e.g., corrupt database, second-instance conflict, incompatible WAV format, save failure while exiting) requires an owner-reviewed compact delta table before landing RV-05/RV-07; never quietly ship developer-oriented fallback wording. The approved table is the frozen baseline, not license to invent more cards.

## Owning acceptance cases (proposed; register in existing indexes before TDD)

These are stage scope definitions, **not registered or executed tests**. Validate IDs against [unit](../../UNIT_TESTING.md), [integration](../../INTEGRATION_TEST_BEHAVIORS.md), and [fixture index](../../INTEGRATION_TEST_DATA.md); register exact case text there before implementation. Never create a second test index.

| ID | Owner | Positive assertions | Negative / non-mutation assertions |
|---|---|---|---|
| `UT-REVW-009` | RV-05 | filter/sort/keyboard/auto-advance/explicit back-forward view selection; approved copy state map | no jumping past filtered valid item, disabled action in empty view, label-save failure does not advance |
| `IT-REVW-007` | RV-05 | real Qt Gallery/List/One by one, access labels/icons/HelpHints, auto-advance, explicit prev/next, keyboard, view persistence and normal/compact screenshots | inaccessible/disabled/missing/failed states honest; navigation away and back retains open Review work |
| `IT-REVW-008` | RV-05 | 50k Result rows, virtual scroll/filter/sort/load, measured latency/memory and real event-loop responsiveness | no 50k eager widgets/thumbnails, no unbounded queues, no frozen UI under cache churn |

**Gate:** Owner accepts real Qt screenshots (normal/compact), focus/keyboard/a11y and exact approved copy. Submit only any new/changed copy in one compact delta table for explicit approval.

## Delivery and evidence gate

Record reviewed baseline SHA and branch, actual implementation files, focused and full feasible ordinary test commands and pass/fail/skip/block results, Ruff, `scripts/audit_test_ids.py`, `git diff --check`, source/Result checksum non-mutation, and current dependency import origins/SHAs. Capture real native Qt/audio/Worker evidence only for boundaries owned here; do not claim whole-Studio qualification before RV-08. Confirm a clean narrowly scoped diff and hand the branch/commit SHA to the owner. No automatic merge or push.

**Next:** RV-06 may be prepared only after this gate is explicitly approved.
