# RV-05 — Native researcher-facing Review workspace

> **Status:** Owner-approved planning; not implemented. Begin only after explicit stage authorization and the predecessor's owner gate.

## Strict ownership and exclusions

**Owner:** `review/gui` and a narrow Review controller/view-state adapter. **Entry:** approved RV-04 (thus RV-01–03 complete). Use only public installed `alp-ui` primitives with native PySide6; no upstream UI changes without independent library branch and tests. Do not expose a second direct-export route, build an ad hoc full-recording annotator, add RF-rejected filters or move Detect exports here before RV-06/07. A Review UI may not advertise nonfunctional final-export actions before RV-06 completes.

## Native UI states, interactions and owner-approved wording

### Structure, navigation, and focus

1. **Review landing / no session:** show available verified completed Detect Results by recognizable name, Result kind (CNN/RF), date and eligible count. **Choose Result** then **Start session**; if existing Closed/Finalized sessions exist, make them accessible without a new route maze. If the Result is empty, use **No detections to review.** No random folders or standalone annotation imports.
2. **Open session header:** editable human session name, `Open` status, concise reviewed count/progress and session actions. One persistent switch between Gallery, List and One by one. `Close session` and `Finalize` should be findable without a cluster of competing buttons. The navigation path and saved view state must survive leaving Review for Train/Detect/Studio and returning.
3. **Gallery:** efficient thumbnail grid ordered by deterministic source recording/time (unless user selects a sort), label symbol and clear access to the individual audio player. Filter All/Unreviewed/Call/Not a call; multi-select is for **Clear spectrograms**, not another bulk-label workflow. Keep **Accept all** as the only approved bulk-label action in the session action area. Show a placeholder only for images actually generating.
4. **List:** virtualized, sortable model/view for at least 50,000 candidates; human-readable recording/time, duration, prediction information where genuinely useful, label status and availability. Measure cold/warm scroll, filter and sort latency, memory and event-loop responsiveness without constructing per-row widgets. Multi-select for cache clearing; **Accept all** independently applies to eligible Unreviewed candidates. Do not add selective bulk-label buttons, hidden IDs or per-row heavy widgets. No machine-generated explanation columns.
5. **One by one:** large detailed spectrogram with marked candidate interval, clip seek/play/pause, **Previous**, **Next** buttons, three states/actions and persistent reviewed progress. On Call/Not a call: persist first, then advance to next unreviewed. Previous/Next work regardless of label state, and keyboard shortcuts are discoverable in a single appropriate place (e.g. application shortcut listing, not captions per button). Disable impossible navigation clearly; no dead ends when all items are reviewed.
6. **Cache controls:** lightweight storage information near Generate all, the manual Clear spectrograms action reachable from multi-selection and single item; no repeated explanatory cards. Automatic eviction generally silent; if image unavailable, show retry/actionable failure without altering label. Cache deletion must not be mislabeled “Delete annotation”.
7. **Finalization/export:** explicit Finalize after session work. If Unreviewed >0, one warning; then show export destination, Storage estimate and format choice. Completed export offers **Show in folder**. New export from the same finalized session remains possible. On failure/cancel, navigate back to same finalized session, not to a blank workflow.
8. **Closed and Finalized:** Closed shows **Resume**; Finalized shows read-only labels/exports and **Continue in new session**. Starting a successor produces its own editable session, not an in-place toggle. Human-readable parent context may be included in details when genuinely necessary, never raw UUID/hash captions.
9. **Global exit:** exit initiated by macOS window close/menu, Studio, Train or Detect all invokes the same policy. Correct default/cancel focus, keyboard/escape, no double confirmation for simultaneous Worker and open session. Preserve existing operation text when no Review session exists.

**Presentation standards:** native PySide6 + public `alp-ui` components. Use real Qt screen sizes/normal and compact widths, 100%/150% display scaling where available, light theme compatibility, readable text, accessible names/focus and correct tab order. Status icons must differ in shape/text as well as color. Investigate installed API/owner-approved showcase before proposing new `alp-ui` public components. No custom global CSS/styling that bypasses the library. The owner feedback in [Detect revision notes](../manual_revision_specs/detect-revision-notes.txt) and [UI pass revision](../manual_revision_specs/UI-pass-revision-spec.md) prohibits unnecessary subtitles, overlines, generic success/immutability cards, tiny captions, repeated names, developer jargon/IDs and unreadable tooltips. Any HelpHint must explain what an operation *does for a researcher*, not its stored IDs or Worker implementation. Important information remains visible, not tooltip-only.

### Approved wording inventory (owner approved 2026-11-02)

| Surface | Visible text / controls | HelpHint if approved/useful |
|---|---|---|
| Result intake | **Choose Result** · **Start session** | none |
| Session list | **Open** · **Closed** · **Finalized** · **Resume** | none |
| Finalized successor | **Continue in new session** | none |
| Session identity | **Session name** | none |
| View switch | **Gallery** · **List** · **One by one** | none |
| Filters | **All** · **Unreviewed** · **Call** · **Not a call** | none |
| Individual labels | **Call** · **Not a call** · **Clear label** | none |
| Bulk labels | **Accept all** | “Marks all unreviewed detections as calls. Existing labels won't change.” |
| Playback/navigation | **Play** · **Pause** · **Previous** · **Next** | none |
| Spectrogram generation | **Generate all** · **Cancel** · **Retry** | none |
| Cache management | **Clear spectrograms** | “Frees disk space by deleting generated images. Your labels and recordings stay unchanged.” |
| Storage | **Estimated size** · **Space needed while generating** · **Free space** | Use **implemented REV-05** wording for actual capacity decision; don't contradict its approved copy |
| Session lifecycle | **Close session** · **Finalize** | none |
| Export | **Export corpus** · **Destination** | none |
| Export choices | **Individual WAV files** · **Combined WAV + Raven TSV** · **Both** | none |
| Completed export | **Show in folder** | none |

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

## Acceptance cases (register in existing test indexes during stage TDD)

| ID | Owner | Positive assertions | Negative / non-mutation assertions |
|---|---|---|---|
| `UT-REVW-009` | RV-05 | filter/sort/keyboard/auto-advance/explicit back-forward view selection; approved copy state map | no jumping past filtered valid item, disabled action in empty view, label-save failure does not advance |
| `IT-REVW-007` | RV-05 | real Qt Gallery/List/One by one, access labels/icons/HelpHints, auto-advance, explicit prev/next, keyboard, view persistence and normal/compact screenshots | inaccessible/disabled/missing/failed states honest; navigation away and back retains open Review work |
| `IT-REVW-008` | RV-05 | 50k Result rows, virtual scroll/filter/sort/load, measured latency/memory and real event-loop responsiveness | no 50k eager widgets/thumbnails, no unbounded queues, no frozen UI under cache churn |

**Gate:** Owner accepts real Qt screenshots (normal/compact), focus/keyboard/a11y and exact approved copy. Submit only any new/changed copy in one compact delta table for explicit approval.

**Next:** RV-06 may be prepared only after this gate is explicitly approved.
