# 01 — Prototype-faithful native shell and test foundation

## First session: required, bounded reading

`AGENTS.md` → [`docs/agent/ROUTING.md`](../agent/ROUTING.md) → **this file** → [`docs/design/UX_PARITY_MATRIX.md`](../design/UX_PARITY_MATRIX.md) (Select/Wiki/empty rows) → [`docs/design/ALP_UI_CONSUMER_CONTRACT.md`](../design/ALP_UI_CONSUMER_CONTRACT.md). Inspect `../alp-ui/src/alp_ui/components/__init__.py`, `../alp-ui/gallery/showcase.py`, `../alp-ui/docs/images/showcase.png` and the actual prototype `../design/prototypes/training-first/index.html` and landing/wiki preview. For tests, read exact `IT-UI-*`, `UT-PATH-*` and `TD-UI/PATH/COL` rows. **Do not load alpaca-pipelines, HPC private instructions, all specs or all Markdown files in session one.**

## User behavior and screen fidelity

Build a native PySide6 `QMainWindow` with the **same information hierarchy and navigation states** as the prototype: Select Collection landing, Collection/Datasets/Models/Runs lists with true empty-state routes, Wiki (Selecting a Collection), Settings and global Active Run placeholder. Only *real* application data may mark a scientific result complete. The UI uses `alp-ui` Alpaca Light theme and matching Showcase Cards/buttons/table density, without grafting the browser CSS into Qt. Compare real screenshot and keyboard behavior with prototype previews; record justified native OS differences. Disabled/incomplete scientific actions are honest until specs 02–05 exist.

## Ownership / test-first implementation

1. Check current native `../alp-ui` public API and version; install theme **once** per `QApplication`. Compose `FolderPicker` for folder selection (it internally opens native QFileDialog), use `HelpHint` for concise contextual clarification where visible; ordinary Qt widgets are allowed for sidebar/stacked routing because `alp-ui` has no navigation framework. Connect `folderChanged` to a pending-path intent only; scan validation belongs to spec 02. If user cancels, keep existing path/binding/UI unchanged. **Do not create a competing raw QFileDialog button.**
2. Build accessible `QMainWindow`/stacked-page navigation with correct headings, Tab/back/Enter/Space interaction, accessible labels, empty/list states and Wiki text/source-time example. Keep `DataTable` supplied by `QAbstractItemModel`, no per-row widget. Use `Text`/`Card`/`Badge`/`EmptyState`/`Button` and native Qt composition from Showcase.
3. Machine-local Application Settings with `--settings-dir` override for isolated tests; a recent folder is merely pending until validation establishes Collection identity. Robust relink/refresh later belongs to spec 02; no machine paths enter artifacts.
4. Retire/replace scaffold routes, actions and existing integration tests that assert product-irrelevant pages or independent storage roots. Keep only genuinely reusable Qt model/settings behavior after aligning it to Collection-first UX; update assertions so legacy tests cannot falsely demand out-of-scope features. Do not retain dead navigation behind disabled buttons.
5. Pure relative path/collision logic at domain boundary (traversal, absolute, UNC, unsafe platform names, NFC/case folding). Unit-tests **before implementation**; use minimal generated real Collection and Qt fixtures, never production HPC.
6. Add correctly indexed `pytest-qt` UI tests: real public FolderPicker signal/cancel behavior, screen routing, HelpHint hover/Space/accessibility, absence of simulated scientific content; inspect actual generated Qt screenshots against HTML prototype and sibling Showcase. Make separate native and offscreen test results explicit. Do not claim visual parity solely by an offscreen snapshot.

## Failure acceptance

Unavailable sibling `alp-ui` is a recorded dependency blocker, not permission to silently replace its components. Native folder-dialog cancel cannot trigger a scan or erase a valid pending binding. App settings failure must be actionable. Path invalidity must never write selected source files. Prototype-only fake data never appears as real Dataset/Model or metrics.

## Tests & completion gate

- `UT-PATH-001`, `UT-PATH-002` (`TD-PATH`)
- `IT-UI-001`...`IT-UI-004` (`TD-UI`, `TD-COL`, `TD-PATH`); all applicable asserting tests actually pass on native macOS, with explicit native screenshots/keyboard review.
- Native Select/Wiki/empty-state look-and-flow matches prototype and `alp-ui` Showcase composition. **Do not implement spec 02** in this PR. Record outstanding native Windows checks, as well as disabled scientific paths, rather than marking them complete.
