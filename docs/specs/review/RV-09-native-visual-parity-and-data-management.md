# RV-09 — Review visual parity, session deletion and data-folder selection

**Corrective specification; not implemented.** Start from the current reviewed `review` baseline, retaining RV-01–RV-08 scientific, annotation and export contracts. **Owns:** Studio/Review native visual parity, sidebar/navigation, safe session deletion, in-app Review-data-directory selection, and reusable upstream `alp-ui` components. RV-10 depends on this stage and a separate explicit owner approval.

## The identified failures — mandatory, not optional

The existing `WorkspaceCard` styles Open Review as outline, but Open Train and Open Detect as primary; Review also uses a different Studio header. The native Review omits the prototype's persistent sidebar and uses generic stacked tables, cards, toolbar buttons and distorted Gallery thumbnails. There is **no Delete session operation** and **no in-app Review data-folder chooser**. Functional/offscreen test passes do not constitute visual acceptance. Inspect the current code and the real design before editing.

**The visual contract is concrete:** [versioned prototype PNGs and native-before evidence](../../design/evidence/review-correction/README.md), the original [interactive Review HTML prototype](../../design/prototypes/studio-review/index.html), its CSS and evidence, the accepted native Train/Detect screens, and both owner UI feedback documents. Prototype-only mock data and banners must **not** be copied. The latest owner instruction overrides the prototype where necessary: all three Studio Open buttons must look and behave consistently.

## A. Rebuild the actual native Review navigation and layout

**Required permanent left sidebar:** Sessions, Choose Result, Review, Spectrograms, Exports, with active-route indication, coherent header/back/exit controls, readable icons and accessible keyboard/focus order. This is mandatory. The current QStackedWidget may remain an internal page router, but cannot replace the visible sidebar. Session state and playback/Worker lifecycle survive switching views or visiting Train/Detect/Studio. Sidebar actions must work, not lead to placeholders. Don't introduce another Result intake, direct-as-detected export, unapproved selective bulk labeling or an additional model-filter workflow.

**Additional minimal Settings destination:** place a subtle Settings entry on the Review sidebar for the required Review data folder configuration. Do not hide application storage under the spectrogram's FFT/preset Settings; the existing Spectrograms → Settings stays dedicated to the approved preset controls. Preserve one coherent information architecture and exact approved normal labeling/format copy.

**Launchpad parity:** remove the workspace-name conditional `variant="primary" if featured or workspace == "Train" else "outline"`. Open Train, Open Detect and Open Review should have identical action variant/size/focus/hover/placement while preserving established Train/Detect behavior. Review's old HTML screenshot highlighted Open Review differently: record the deliberate exception to the screenshot because the current owner explicitly asked for consistent buttons. Harmonize the Studio/Review/Detect header hierarchy without duplicate Back bars or changing Train's retained separate window.

**Screen composition:** match the screenshots' sidebar/main-content proportions, whitespace, typography, panel dimensions, Gallery cards, List readability, One by one's large spectrogram/audio emphasis, status icons, selected tabs, and grouped actions. Don't imitate screenshot pixels while ignoring source audio; the native plot uses real renderer data, correct axes and highlighted interval. Fix the native Gallery's 320×120 → 284×70 `IgnoreAspectRatio` distortion. Normal, compact (~700 px) and narrow (~520 px) designs must remain legible without clipped controls, tiny text, hidden essential actions or unnecessary scrolling. Keep one Result→Review→Finalize→Export flow; preserve Close/Resume/Finalized successor, Accept all, keyboard shortcuts and explicit Previous/Next.

**Native implementation rule:** pure Review-specific layout/labels remain in BioCall Studio; general-purpose reusable Qt presentation belongs in public `alp-ui` if verified missing. Do not embed web HTML, fork CSS into local ad hoc styles, monkeypatch private widget APIs, add global changes to Train/Detect, or introduce a second UI framework. Refactor the monolithic Review GUI into comprehensible page/view components as needed, without moving scientific or persistent contracts.

## B. Delete session — all states, safe and discoverable

Add **Delete session** to the Sessions page, for Open, Closed or Finalized sessions. Selection plus visible action, meaningful descriptive confirmation, **Cancel** default, no silent one-click destruction. Deletion is genuine (not hidden/archived indefinitely).

- Open: stop or cancel associated generation/playback/export setup, safely checkpoint/Close, then delete; failure must leave a coherent resumable state. Never leave a Worker writing to deleted state.
- Closed: transactional deletion of owned candidate rows, labels, undo/operation history, view state, source/settings snapshots and session record. Preserve other sessions, presets used elsewhere and the one-open-session invariant.
- Finalized: permit deletion of the selected finalized record and snapshot **if no dependent successor**. If it has descendants, show an actionable message and require explicitly deleting dependent successors first; never cascade silently or orphan child references.
- Preserve original WAVs, Detect CNN/RF Results, shared cache objects, other sessions and **all already published corpus files**. Immutable export receipts and independent export-history records must remain readable and identify the now-deleted source session without a broken navigation link. Never delete export destinations as a side effect of deleting a session.
- Correctly order SQLite foreign-key deletions within one checked transaction; verify atomic rollback on IO/transaction failure and restart. At 50k candidates avoid blocking the UI on bulk deletion; keep the database consistent on cancellation/crash.
- Update sidebar counts, Sessions selection and current page; after deleting the active session land on Sessions. No in-flight result can resurrect deleted data.

**Proposed minimal copy to review:** Delete session; Cancel; Delete; “Delete ‘{name}’ and its saved reviews? This can't be undone. Existing exported files won't be deleted.” If dependencies exist: “Delete its linked successor sessions first.” No decorative safety notices.

## C. Choose the Review data directory **inside the app**

The current coordinator creates Review underneath the Detect/suite data root. Add a native folder picker from **Settings → Review data folder**, show the currently selected folder, and permit **Change folder** without CLI flags or editing configuration files.

- Decouple the *Review-owned data directory* (sessions SQLite, presets, cache, export-history) from the immutable *Detect Result catalog/source binding*. Moving Review must never move Detect, Train, recordings or published external corpora.
- Keep the current default initially. Store the selected Review-folder preference in a stable suite-owned settings location **outside the movable folder**, using a versioned, validated path; persist across restart. Validate symlinks, traversal/containment, permissions, disk capacity, incompatible/corrupt databases, destination already in use, and overlap with source or export directories.
- If existing Review data is present, the default change behavior is **Move existing data**, not starting empty. Block switching while a session is Open or a generation/export Worker active; explain why. Use REV-05 volume/free-space checks when moving a sizable database/cache. Stage a private bounded copy, validate DB/receipts/checksums/metadata, flush/atomically promote, update the preference *last*. On error preserve the original as authoritative, with no partial switch or misleading success.
- Optional starting empty is permitted only as a separate clearly acknowledged decision, never implicit from folder selection. Restart and reopen existing sessions, presets, labels, finalizations, source relinks and export history after moving; cached images may be regenerated but are not allowed to erase anything persistent. Release/recreate the Review lease, SQLite connections and cache supervisor safely before/after the switch.
- Use a native dialog and short text: Review data folder; Change folder; Move existing data; Cancel; “Close the open Review session before changing the folder.”; “Couldn't move Review data. Your original folder is unchanged.” Approve any additional copy at the visible UI gate.

## D. Reusable UI: real separate `alp-ui` commit, then local installation

Before writing a one-off widget, inspect the **installed public** `alp_ui` exports/version/import path, sibling `../alp-ui` git status/HEAD, theme tokens, gallery/showcase and existing public components. Candidates for upstream reuse include a generic responsive/sidebar navigation rail, consistent workspace card action/focus, reusable segmented tabs, accessible selected state/status icon and list/empty-state primitives. Only implement in the library if a **genuine reusable gap** is verified; app-specific Review labels, spectrogram logic, routing and session deletion stay downstream.

For any verified gap, in strict order:

1. Create a clean independent `fix/` or `feat/` branch **in `../alp-ui`**, add a failing focused public API/theme/accessibility regression and showcase, implement the reusable primitive, run **short focused** library tests/lint/screenshots, and **commit it there** with an actual SHA. No private API hacks, duplicated component source or unreviewed global visual restyling.
2. Obtain separate upstream owner review. Local upstream integration must be explicitly authorized; no push, library release or dependency republishing is implied.
3. Install the **latest owner-reviewed locally committed** revision into BioCall Studio's actual `.venv`, normally using `.venv/bin/python -m pip install -e ../alp-ui` (check the real checkout first). “Latest” means local approved commit, not PyPI's unpinned latest. Verify `alp_ui.__file__`, distribution version, public imported symbols, sibling Git SHA and stale-wheel absence. Update `pyproject.toml` dependency revision/pin and reproducible provenance when needed; editable installs are development-only.
4. Consume only the public upstream API in Studio, run short native Review **plus Train/Detect compatibility** checks, and commit downstream separately. Report both repositories' branch/SHAs, import provenance, exact commands and outcomes.
5. If the library is unavailable or compatibility cannot be verified, block that stage rather than invent a private fallback. If existing public `alp-ui` already suffices, document reuse; **do not create a ceremonial upstream commit**.

## E. Real screenshots are a mandatory acceptance gate

**Commit visual references:** target screenshot PNGs and before-state PNGs are in [review-correction evidence](../../design/evidence/review-correction/README.md). Match **Studio, Choose Result, Sessions, Gallery, List, One by one, Spectrograms, Settings, Export, Finalize and compact/narrow widths**. Capture real **visible PySide6 application** screenshots after correction and commit them as `native-after/*.png`, recording native viewport dimensions, screen scale, OS, Qt version, actual Studio/`alp-ui` SHAs, data fixture and time. Produce paired comparison notes identifying deviations and fixes, including new **Delete session** and **Review data folder** screens absent from the old HTML prototype. The screenshot evidence must drive corrections, not serve as decoration.

Owner must explicitly approve the real visible layout, not just a checklist or offscreen Qt capture. The owner's Mac visible-native session needs permission to interrupt their desktop; do not launch it by surprise. If unavailable, mark this gate **blocked** and leave Review unqualified.

**Proposed focused tests:** `UT-REVW-013` (transactional session delete, descendants, exports); `UT-REVW-014` (folder preference/move/restart/failure); `IT-REVW-013` (Qt launchpad/sidebar/active navigation and Train/Detect nonregression); `IT-REVW-014` (real Sessions delete, folder selection/migration, compact/keyboard screenshot). Register during implementation in existing indexes, not a new one; these are not claimed passes.

**NO LONG-RUNNING TESTS:** for RV-09 and RV-10 only, bound each targeted test command by **120 seconds including setup**. No entire ordinary suite, heavy 50k batch, ≥600-second soak, broad retraining, installer run or repetitive long test without separate owner authorization. Run targeted Qt/SQLite checks, lint/audit and short upstream tests; record all deferrals truthfully.

**RV-09 gate:** persistent prototype-style sidebar; visually consistent launchpad actions; screenshot-backed, owner-approved native hierarchy; working safe deletion in all states; working in-app directory change/migration; upstream independent committed/tested public `alp-ui` work if necessary and the newest approved local version actually installed; focused compatibility tests and scientific nonmutation. Do **not** start RV-10 or declare RV-08 complete until this gate is approved.
