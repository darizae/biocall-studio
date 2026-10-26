# 01 — Prototype-faithful native shell and test foundation

**Scoped references:** [native component API](../design/ALP_UI_CONSUMER_CONTRACT.md); [prototype state matrix](../design/UX_PARITY_MATRIX.md) (01 rows); [acceptance procedure](../design/PROTOTYPE_ACCEPTANCE.md) (01 rows); [indexed UI cases](../INTEGRATION_TEST_BEHAVIORS.md) (`IT-UI-*`). [Closeout](SPEC_01_CLOSEOUT.md) only for a verified unresolved defect.

**Historical evidence (2026-10-24):** [Spec 01 closeout](SPEC_01_CLOSEOUT.md) documents prototype parity and native screenshots from that implementation stage. Verify the current checkout before assuming this remains accepted.

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
## Blocking native-UX deliverables

Spec 01 is not done until the **entire** screen set for 01 in [Prototype acceptance](../design/PROTOTYPE_ACCEPTANCE.md) has been exercised: Select, Wiki, Settings, all four empty lists, selected sidebar route and compact-width layout. Preserve prototype composition (icon-bearing navigation, centered Select hierarchy, in-card folder structure guide, prominent CTA and direct Wiki link), not just similar text. Capture, review and record each required native screenshot and its interaction assertion; native-platform exceptions require explicit owner approval. Do not advance to 02 when any item is still BLOCKED.



Unavailable sibling `alp-ui` is a recorded dependency blocker, not permission to silently replace its components. Native folder-dialog cancel cannot trigger a scan or erase a valid pending binding. App settings failure must be actionable. Path invalidity must never write selected source files. Prototype-only fake data never appears as real Dataset/Model or metrics.

## UX and handoff contract (required for Spec 01 acceptance)

- Match the **prototype's** centered Select Collection focal hierarchy, folder structure summary and direct **How should my folder look?** Wiki action. Use public `alp-ui` FolderPicker for the native picker; do not clone dialogs or turn selection into a real Scan. The library Showcase supplies native sidebar **icons**, active/hover/focus styling, typography, cards and spacing conventions; do not merely import its widgets without visual comparison.
- Review **actual** native Select, Wiki, empty routes, compact width, tab order and help interaction against the bundled prototype plus sibling Showcase. Where HTML cannot map identically to Qt, document why and which native behavior compensates. Disabled science remains honest.
- `README.md` is a **user-facing front door**: current functionality/status, native application screenshots once captured, clearly distinguished UX prototype previews, example Collection, prerequisites, `.venv` install and *direct* `.venv/bin/python -m biocall_studio_train` launch command, test commands, and developer/spec routing. Keep launch commands synchronized with `pyproject.toml`.
- Record reproducible macOS screen evidence in `docs/design/evidence/spec-01-native/` and a state-by-state report in `docs/design/evidence/README.md`. Temporary test `tmp_path` screenshots are not deliverable screenshots. Real app screenshots replace the README's provisional design-only screenshots after native verification.
- Source checkout and branch are deliverables. `docs/agent/GIT_DELIVERY.md` defines branch, exact commit message, clean status, real SHA, LFS verification, and red/green execution report. A ZIP without `.git` **does not prove a commit happened**. No next-spec work without a verified completed spec branch and review.

## Tests & completion gate

- `UT-PATH-001`, `UT-PATH-002` (`TD-PATH`)
- `IT-UI-001`...`IT-UI-004` (`TD-UI`, `TD-COL`, `TD-PATH`); all applicable asserting tests actually pass on native macOS, with explicit native screenshots/keyboard review.
- Native Select/Wiki/empty-state look-and-flow matches prototype and `alp-ui` Showcase composition **with persistent native macOS screenshots, recorded differences and README native images**. Fresh `.venv` setup/run commands, optional LFS fixture check when bytes exist in this checkout, actual branch/commit SHA and clean working tree are verified. **Do not implement spec 02** until all [Spec 01 closeout](SPEC_01_CLOSEOUT.md) gates pass. Record outstanding native Windows checks and disabled science paths rather than marking them complete.

## Historical implementation report — 2026-10-24

- Replaced the incompatible independent-artifact-root scaffold with Collection-first Select, empty Collections/Datasets/Models/Runs, Wiki, Settings and an honest global `No Active Run` placeholder. Dataset Build and Training remain unavailable; no demo records, metrics or progress are rendered.
- Selection uses the installed public `FolderPicker`; its signal records a pending path only. The machine-local `settings.json` can hold only a verified Collection binding, as called by future Collection Scan work. It does not read or migrate the retired root-based settings document.
- Inspected `alp-ui` `0.1.0a0` at `330aaab96a6b32dd2d83ae84a52a2a238446d264`. The native shell uses its theme, `FolderPicker`, `HelpHint`, `Card`, `Text`, `EmptyState`, `DataTable`, `Badge` and `Button` public APIs; sidebar routing remains ordinary Qt composition as required.
- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/unit tests/integration` passed: 19 tests. The test captures real Qt Select and Wiki widget screenshots into its isolated temporary directory; offscreen output is preparatory evidence only.
- **Implementer-reported**, not independently reproduced here: native macOS `tests/integration/test_shell.py` passed after using the native window server: Select/Wiki route focus, the real `FolderPicker` cancellation seam, Settings binding/rebind and native Qt Select/Wiki screenshots were exercised. Windows has not been run and remains a release-gate check.
