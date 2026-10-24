# Spec 01 acceptance closeout — native UX, onboarding and Git delivery

**Status: COMPLETE (implemented and natively reviewed 2026-10-24).** This remained a **bounded
completion task within Spec 01**: no Collection scanner or Spec 02 capability was added. The work
was completed on `spec/01-shell-and-test-foundation` because the original Spec 01 changes had not
been committed or merged; see [Git delivery](../agent/GIT_DELIVERY.md).

## Closeout evidence

- Red: focused `IT-UI-001/004` parity assertions failed for absent navigation icons and the
  non-prominent Collection action before the native shell change.
- Green: native Cocoa runs passed 13 unit tests, 6 integration tests and 19 combined tests. The
  integration suite covers `IT-UI-001…004`; unit docstrings cover `UT-PATH-001/002`.
- Fresh setup: a temporary clean checkout with Python 3.12.7 installed from the documented commands
  after upgrading pip; module and console-script GUI launches both stayed alive until deliberately
  terminated, and the fresh unit suite passed 13 tests.
- Native evidence: all eight required views at 1180×790 and 700×780 logical pixels are tracked in
  [`spec-01-native/`](../design/evidence/spec-01-native/), with Retina/DPI/runtime/SHA provenance
  and the six-dimension review in the [evidence ledger](../design/evidence/README.md).
- Static/artifact gates: Ruff check and format, test-ID audit, handoff audit, native-UX handoff gate,
  fixture integrity, Git LFS listing and LFS fsck passed. The scientific sibling was verified at
  `../alpaca-pipelines` but not imported or executed for this UI-only closeout.

## Read only

`AGENTS.md` → `docs/agent/ROUTING.md` → **this file** → [`01-shell-and-test-foundation.md`](01-shell-and-test-foundation.md) (only its UI and test acceptance) → [Prototype acceptance](../design/PROTOTYPE_ACCEPTANCE.md) (Spec 01 row and evidence rules) → [UX parity](../design/UX_PARITY_MATRIX.md) (Select/Wiki/Settings/empty states) → [public `alp-ui` crosswalk](../design/ALP_UI_CONSUMER_CONTRACT.md). Open *images/code*, not all Markdown, for `docs/design/prototypes/training-first/{landing-preview.png,wiki-preview.png,index.html}` and `../alp-ui/{gallery/showcase.py,docs/images/showcase.png}`. Review exact `IT-UI-001`, `IT-UI-003`, `IT-UI-004`, `TD-UI` only. For setup, open `README.md`, `docs/DEVELOPMENT.md` and `pyproject.toml`. For Git delivery, open `docs/agent/GIT_DELIVERY.md`.

## Audit facts from the submitted ZIP

- Real PySide6 native shell, Select/Wiki/Settings/empty screens, `FolderPicker`, `HelpHint` and theme exist in source. Prior developer reported passing 19 tests and native screenshots, but **the ZIP has no `.git`, saved native image evidence or test log**; those historical claims are not independently authenticated.
- `src/alpaca_desktop/gui/window.py` Select uses a generic left-aligned vertical layout rather than the prototype's prominent centered area/structure diagram, and has no direct **How should my folder look?** Wiki action. The sidebar is plain text, while prototype and native `alp-ui` showcase use consistent nav icons/selected styling. Brand icon/footer and layout hierarchy also need comparison, not blind copying.
- `tests/integration/test_shell.py` saves screenshot PNGs under pytest `tmp_path` and merely checks nonzero size; no permanent native baseline, side-by-side review or explicit mismatch ledger is delivered. It cannot claim exact design parity from that assertion.
- The submitted transfer ZIP intentionally omitted `tests/data/`. **This is expected, not a regression or Spec 01 acceptance failure.** The actual Git checkout may have LFS-backed test fixtures; verify them only where present and where a case needs them. Tests may generate deterministic WAVs in temporary locations.
- The README previously had no screenshots and did not prominently show `.venv` install/run commands. The revised README includes **clearly labeled prototype previews** and tested-command-shaped setup instructions; replace/add **actual native app images** only after capturing them on macOS.

## Work requirements and ownership

**Strict design blocker:** follow [Prototype acceptance](../design/PROTOTYPE_ACCEPTANCE.md), not a generic interpretation of the `alp-ui` Showcase. Every required Select/Wiki/Settings/empty-list/narrow view and its interaction must match the prototype's layout and language, using `alp-ui` theme/components. Any missing screen/major panel/navigation/CTA or unapproved material deviation fails this closeout. The [evidence ledger](../design/evidence/README.md) must cover the full Spec 01 screenshot inventory.

1. **Reproduce setup from a fresh `.venv`** using README's commands, with verified `../alp-ui`; test both `.venv/bin/python -m alpaca_desktop` and the installed script `.venv/bin/alpaca-desktop`. Explicitly document dependency/path blockers. Never import `alpaca-pipelines` for this task.
2. **Test-first native UX parity.** Add failing `pytest-qt` assertions for real user-facing needs, then implement the smallest changes: centered Select content and clear hierarchy, equivalent structure guidance, prominent primary `FolderPicker` action, direct keyboard-accessible Wiki link, sidebar icon/text/selected/focus styling comparable to sibling Showcase, clean empty routes and header. Preserve actual `FolderPicker` native-dialog/cancel semantics and accessible `HelpHint`. An honest native UX may differ in widget geometry; log intentional differences. Do **not** copy browser CSS or render web UI in Qt. Do not add sample Collections, fake training or new data flows.
3. **Capture persistently on native macOS** (actual window server, not `QT_QPA_PLATFORM=offscreen`), with real running app and installed `alp-ui`: `docs/design/evidence/spec-01-native/` with all filenames required by [Prototype acceptance](../design/PROTOTYPE_ACCEPTANCE.md): `select.png`, `wiki.png`, `settings.png`, `empty-collections.png`, `empty-datasets.png`, `empty-models.png`, `empty-runs.png`, `select-narrow.png`. Additional screenshots capture meaningful selection/cancel/keyboard states. Screen captures must be produced by a repeatable documented command/process with no private paths or test-sensitive contents. Confirm images show the Trainer, not the browser or `alp-ui` Showcase. A temporary pytest screenshot is insufficient.
4. **Compare** native screenshot vs checked-in `landing-preview.png`/`wiki-preview.png`, and library theme/nav/control density vs native `../alp-ui/docs/images/showcase.png`. Record a short [parity evidence report](../design/evidence/README.md) with a row per Select/Wiki/Settings/each empty-state/narrow view: prototype target, Qt screenshot, `alp-ui` characteristic, interaction checks (mouse/keyboard/folder cancel), observed difference, disposition (fixed/intentional/open). Include library commit/version and OS, Qt, DPI and viewport resolution. Blocking mismatch stays OPEN.
5. **Promote README from prototype preview to app evidence** once real shots exist. It must remain **user-facing first**, with actual native screenshot(s), short what-is-it description, currently working vs coming later, Collection format/limits, macOS `.venv` prerequisite/install/run/test commands, and links into developer docs. Keep provenance captions; prototype screenshots may stay in a separately marked design reference section, never presented as product shots. Verify each relative image link and launch command.
6. **Verify fixture policy, not transfer-ZIP contents**: run `scripts/verify_handoff.py` (use `--require-private` only for a private archive that actually includes those notes). The ZIP may deliberately omit all `tests/data/`, so do not recreate or stage WAVs just to make a handoff audit green. When the **actual checkout** contains registered LFS WAV fixtures and the test needs them, check `git check-attr filter`, `git lfs pull`, `git lfs ls-files`, `git lfs fsck` and `scripts/check_fixtures.py`. Otherwise use temp-generated real WAVs and record fixed-fixture-dependent tests as blocked/unavailable, not passed. CI/docs run without `docs/priv`.
7. **Run focused and broad checks**: indexed `IT-UI-*` on native macOS and all unit tests; run `ruff check` and `ruff format --check`, `scripts/audit_test_ids.py` and handoff script (fixture script only if fixed bytes are available in the actual checkout). Once genuine native evidence exists, run `python scripts/verify_handoff.py --require-native-ux` as a **static artifact gate**, plus human visual comparison. Include explicit command, exit status, native/offscreen distinction and visible deviations. Update the specific IT-UI-004 assertions for reachable wiki CTA, focus/Tab and UI state; screenshots require **separate manual parity evidence**, not fake automatic pixel equality.
8. **Commit on a branch**: no uncommitted work at handoff; record `git branch --show-current`, `git status --short`, `git log -1 --oneline`, and the exact commit SHA. Recommended commit subject: `fix(spec01): align native UX and document local setup`. Don't invent a commit if ZIP has no `.git`; if only a ZIP is available, report no Git proof and let the receiving agent initialize the repository.

## Acceptance checklist (blocking before Spec 02)

- [x] Fresh `.venv` setup, help/version, GUI launch and instructions confirmed on native macOS.
- [x] `FolderPicker` remains real public `alp-ui` API; native cancel is non-destructive; accessible direct Wiki route and icon-based native nav work by keyboard.
- [x] Select/Wiki/Settings/all four empty list states/narrow viewport reviewed against **both** bundled prototype **and** sibling Showcase, with all six acceptance dimensions and no native exceptions.
- [x] Real macOS Trainer PNGs, viewport/density metadata and side-by-side evidence are tracked; README embeds truthful **native** images and clearly labels remaining design prototypes.
- [x] Missing `tests/data/` from a transfer ZIP is accepted; fixtures present in this Git checkout are registered, LFS-backed and verified. No HPC data or private files are staged.
- [x] `UT-PATH-*` and `IT-UI-001…004` assertions/results are recorded; native tests and lint are green.
- [x] The expected Spec 01 branch and final commit exist with a clean working tree; the delivery report records the exact SHA and command results.

If any box is not satisfied, label **Spec 01: open** and do not proceed automatically to Spec 02.
