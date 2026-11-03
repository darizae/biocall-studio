# BioCall Studio — Review interactive prototype

**Status:** design prototype for owner review; **not owner-approved** and **not a native Review implementation**. Scientific decisions and native implementation sequencing remain governed by `docs/specs/review/README.md` and `RV-01` through `RV-08`.

## Launch

From the extracted `docs/design/prototypes/studio-review/` directory:

```bash
python3 -m http.server 8000
```

Open **http://localhost:8000/** in a current Chromium, Firefox, or Safari desktop browser. No installation, bundling, API keys, external network, or Python scientific packages are required **to run** the prototype. Keep `index.html`, `styles.css`, `prototype.js`, and `assets/` together. Opening `index.html` directly may also work, but a local HTTP server is recommended for WAV seeking and browser storage consistency.

**State persistence:** labels, sessions, their lifecycle, export receipts, and simulated cache inventory are kept in browser `localStorage` under `biocall-review-prototype-v4` and survive a normal refresh in browsers permitting local storage. Each session also stores its last view, filter, sort, focused item and a bounded selection/scroll snapshot; Close → Resume restores that context. The URL hash retains the active route. Real-origin browser-refresh restoration has not been tested in the constrained browser harness. To start over, expand **Prototype controls** and choose **Reset example data**. This resets example records, not actual files.

## What is real and simulated

| Aspect | Representation |
|---|---|
| Studio shell / Review interface | Functional standalone HTML, CSS and vanilla JS; styled against the repository's actual Train and Detect native evidence and existing Studio/Detect prototype |
| Train and Detect | Navigation and **reference screenshots** of native interfaces, **not** runnable Train/Detect applications; Exit Studio operates on the shared prototype session state |
| Review labels / sessions | Functional browser-state transitions and persistence model, not a database or immutable native snapshot on disk |
| Results and recordings | Fictional Meadow CNN Result (28 detections), Marsh original CNN Result (26 detections) **independently selectable** alongside its RF-refined Result (17 **eligible accepted only**), 50,000-detection CNN stress case; no genuine research recordings or predictions |
| Spectrogram and sound | 20 paired **locally synthesized 6-second WAV files and deterministic time-frequency spectrograms**; browser playback/seek is real, but example intervals and candidate scores are illustrative |
| Generation and storage | On-demand reveal, bounded prefetch, logical cache eviction, cancellation, regeneration, progress and illustrative capacity/preflight decisions; no real background scientific renderer or disk-space measurement |
| Exports / Show in folder | Format, provenance, staging and recoverable progress **simulated**; no WAV corpus, Raven TSV, or filesystem folder is created or opened |

The one prototype-level notice across the app marks these distinctions. The samples were designed to show a plausible audible signal and foreground event, **not to validate biological detection accuracy**.

## Navigation and exercises

**Start at Studio.** Choose **Open Review** to enter the seeded partially reviewed Open session. The sidebar provides **Sessions**, **Choose Result**, **Review**, **Spectrograms**, and **Exports**. The Gallery, List and One by one buttons switch coordinated views of the same candidate set. One by one traverses the full eligible set in the selected sort order, independently of Gallery/List filtering, so previously labeled items remain revisitable; returning to Gallery/List preserves the filter. A single selected candidate or click on a recording/time opens One by one. Filters and sorting apply to Gallery/List; selection exposes bulk labels and **Clear spectrograms**. The **Accept all** action changes only Unreviewed eligible detections.

**Session lifecycle.** From Review, **Close session** saves and pauses; **Sessions → Resume** reopens a Closed session. With the seed's Open session first closed, **Choose Result → Start session** creates a session for an existing Detect Result. The seed also includes a Finalized session and a separate Closed successor. **Finalize** with Unreviewed detections gives the locked warning; after confirmation, exported candidates include **Call** and **Unreviewed** with distinct human/model-only provenance, and exclude **Not a call**. A Finalized session is read-only; **Continue in new session** creates a new editable session without altering its parent. Navigate into Train or Detect without closing: the same open session remains. **Exit Studio** from any workspace prompts **Save and Exit** when an Open Review session exists.

**Sound and cache.** In One by one, Play/Pause, 0–6 s seek and the highlighted detection window are interactive. In Gallery and List, click a recording to inspect it. The Spectrograms page offers **Generate all**, **Cancel** and **Clear spectrograms**, with logical cache state maintained separately from annotations. Open Prototype controls to simulate low or unknown free space, or missing/changed recordings and a renderer error. For a renderer error, enter candidate 4 (index 3) from Gallery and press **Retry**. To see per-item cache regeneration, clear its spectrogram from One by one; it will be regenerated on demand. Clearing all removes generated thumbnail state without changing any labels.

**Corpus export.** Open a Finalized session from Sessions; choose **Export corpus**. Select Individual WAV files, Combined WAV + Raven TSV, or Both, edit the example destination, and run/cancel an export. The Export failure scenario fails the first attempt, leaves the Finalized session unchanged, and permits **retry**. The Combined WAV limit scenario disables combined formats while leaving individual files available. **Show in folder** opens a simulated receipt, not the operating system's file manager.

**Large set.** Close any Open session, expand Prototype controls and choose **50,000 detections**. This creates (or selects) the illustrative large CNN session. Scroll Gallery/List, search recording names, filter, sort, and use Accept all; the UI keeps a **bounded number of cards/rows in the DOM**, not 50,000 spectrogram elements. The browser retains a sparse label representation for bulk acceptance. The recording search field is scoped to Gallery/List; One by one always traverses the full sorted eligible candidate sequence.

**Other scenarios.** The collapsed **Prototype controls** menu has Empty Results, Missing recording, Changed recording, Spectrogram error, Generation in progress, Insufficient storage, Tight storage, Unknown capacity, Export failure, Combined WAV limit, 50,000 detections and Open session during exit. The **Save failure** scenario demonstrates an unsuccessful label, Close, Finalize, or Save and Exit without falsely committing the action. Missing/changed recordings block illustrative playback, generation, and export until the source state is restored. Some scenarios navigate directly to the relevant screen. Change to **Normal** to clear injected behavior. Reset restores the starting dataset.

## Keyboard shortcuts

The bindings are **fixed and cannot be changed**. They are designed for an English QWERTY keyboard: the left hand stays on **S/D/F** for labels; the right hand stays on **J/K/L** for navigation and listening. The **Keyboard shortcuts** button in One by one opens one concise listing. Hovering or keyboard-focusing a shortcut-enabled action also displays its key in an accessible tooltip (no persistent per-button shortcut caption).

| Key | One by one action | On-button tooltip |
|---|---|---|
| `F` | **Call**; save, then advance to next Unreviewed | Call · F |
| `D` | **Not a call**; save, then advance to next Unreviewed | Not a call · D |
| `S` | **Clear label**, without advancing | Clear label · S |
| `J` or `←` | **Previous** (including labeled candidates) | Previous · J or ← |
| `K` or `Space` | **Play / Pause** current six-second context clip | Play / Pause · K or Space |
| `L` or `→` | **Next** (including labeled candidates) | Next · L or → |
| `Ctrl+Z` or `⌘Z` | **Undo** last committed label or bulk acceptance operation | Undo last label action · Ctrl/⌘+Z |
| `Esc` | Cancel/dismiss dialog; return focus to the invoking control | Native dialog behavior |

Letters, playback and navigation are only active in **One by one**; Undo is scoped to an **Open Review session**. Label shortcuts are disabled in Closed/Finalized inspection. The UI leaves keyboard input, the audio seek slider, modal dialogs, modifier combinations and IME composition alone; typed input must never label a candidate. Previously documented `C/X/U` shortcuts are removed. Buttons retain distinct visible labels and shape-coded statuses without relying on tooltips to explain their meaning. The exact proposed native contract is in [RV-05](../../../specs/review/RV-05-native-review-ui.md#fixed-review-keyboard-shortcuts-and-tooltip-contract--owner-requested-design-clarification-pending-prototype-sign-off).

## Acceptance evidence and limitations

See [SPEC_COVERAGE_AUDIT.md](SPEC_COVERAGE_AUDIT.md) for the stage-by-stage RV-01–RV-08 audit and [PROTOTYPE_ACCEPTANCE_CHECKLIST.md](PROTOTYPE_ACCEPTANCE_CHECKLIST.md) for the scientific/workflow, UX and interaction audit, the executed check list, remaining limitations, and the proposed owner-approval copy delta. Actual browser renders are under [`evidence/`](evidence/), including normal Gallery/List/One by one, session management, preflight, finalize/export and compact 700 px / constrained 520 px views.

**New executed shortcut/tooltip checks:** **69/69** fixed-shortcut, pointer/focus tooltip and compact-layout checks; **17/17** additional HelpHint-copy, dialog/focus and read-only checks. Evidence: [`browser-shortcut-checks.txt`](evidence/browser-shortcut-checks.txt) and [`browser-tooltip-sync.txt`](evidence/browser-tooltip-sync.txt). Screenshots: [`12-shortcut-reference.png`](evidence/12-shortcut-reference.png), [`13-shortcut-tooltip-700.png`](evidence/13-shortcut-tooltip-700.png), [`13-shortcut-tooltip-520.png`](evidence/13-shortcut-tooltip-520.png). The previous primary, edge, spec, resume and provenance suites are retained and rerun after these changes.

**Validation detail:** the provided runtime environment prevented automated Chromium from navigating directly to local `localhost` or `file://` URLs (`ERR_BLOCKED_BY_ADMINISTRATOR`). The checks therefore rendered **unmodified HTML/JS/CSS in headless Chromium** with a Playwright local-asset fulfillment route (including byte-range WAV responses) and a storage shim for its opaque test document. This verifies actual browser layout and interactions, but **does not verify direct localhost navigation or automatic storage restoration across a real page reload**. Static files can be served normally with `python3 -m http.server`; testing on the owner's desktop browser is still part of approval. This prototype is not a scientific, filesystem, native Qt, platform-installation or 50k native performance qualification.

## Translation into future native PySide6 Review

The GUI implementation should use **public `alp-ui` primitives**, real Qt model/view virtualization, Qt audio playback, persisted Review repositories/snapshots, thread-safe asynchronous spectrogram workers with cancellation/generation identifiers, real disk-cache eviction and genuine REV-05 shared storage preflight. File relocation/source revalidation, WAV/TSV export, atomic output publication and native **Show in folder** must be implemented by their designated RV stages. The browser-only `localStorage`, mock destination input, hash navigation, timers, `Array` sort, synthesized audio and reference screenshots are **prototype substitutes**, not native implementation patterns or new scientific contracts.
