# Agent routing — read less, implement one vertical

**Entry point** when the user asks to start the first agent session: `AGENTS.md` → this page → `docs/specs/01-shell-and-test-foundation.md`. **Do not pre-read every Markdown file.** This page is the short routing index; the active spec selects only the needed reference sections and case IDs.

| Task trigger / question | Open only | Do not open by default |
|---|---|---|
| First session / shell / folder picker / help / visual foundation | `docs/specs/01-shell-and-test-foundation.md`; `docs/design/UX_PARITY_MATRIX.md` §§ baseline, Select; `docs/design/ALP_UI_CONSUMER_CONTRACT.md`; `IT-UI-*` in `docs/INTEGRATION_TEST_BEHAVIORS.md` | Science pipeline and HPC private material |
| Collection scanning/errors/cache | Spec 02; `docs/models/WORKFLOW_RULES.md` § input; `docs/wiki/SELECTING_A_COLLECTION.md`; relevant `UT-COL-*`, `IT-COL-*` and `TD-COL/WAV/CACHE/PATH` rows | Training, packaging |
| Dataset/mining/split | Spec 03; Workflow Rules § mining/split; `docs/agent/SOURCE_MAP.md` § Pipeline; matching `UT-DB-*`, `IT-DB-*` and `TD-MINE/SPLIT` | Windows release |
| QProcess Runs/publication | Spec 04; `docs/ARCHITECTURE.md` relevant worker/persistence sections; `IT-RUN-*`, `TD-RUN/FAIL` | All visual reference images |
| Model/training/charts | Spec 05; `docs/design/UX_PARITY_MATRIX.md` §§ training/model; `docs/agent/SOURCE_MAP.md` § Pipeline; `IT-TRAIN-*`, `TD-TRAIN` | HPC private access unless a missing example requires it |
| Mac installer and controlled release | Spec 06; `docs/RELEASE_PROCESS.md`; `IT-MAC-*`, `IT-E2E-*` | Windows-specific tests |
| Windows installer / qualification | Spec 07; `docs/RELEASE_PROCESS.md`; `IT-WIN-*` | macOS packaging implementation unless shared need |
| Need fixed scientific fixture that cannot be synthesized | `docs/INTEGRATION_TEST_DATA.md` § permissioned fixture flow; *then* `docs/priv/hpc-source-access/SKILL.md` locally; relevant source map entry | SSH access or bulk archive browsing by default |
| New domain term/schema | `docs/GLOSSARY.md`; the relevant model doc | All specs |
| Test design/ID | `docs/UNIT_TESTING.md` **or** `docs/INTEGRATION_TESTING.md`, exact ID rows, corresponding `TD-*` rows; `docs/agent/indexed-integration-tests/SKILL.md` for indexed integration | Unrelated test classes |

## Minimal session protocol

1. Inspect `git status`, active branch, target spec, relevant existing code and current public sibling API. Log dependency availability; **do not scan entire docs tree or sibling repositories**.
2. Consult the short [spec-writing principles](SPEC_WRITING_AND_IMPLEMENTATION_PRINCIPLES.md) as a checklist, not as an invitation to open all docs. Read domain invariants **at the boundary being changed**; use `rg` for a glossary term instead of bulk-loading everything.
3. Remove stale scaffold UI/tests when they contradict the prototype during spec 01; keep only reusable architectural seams with newly justified assertions. Follow test-first red → green → cleanup for the active vertical, with an observable `IT-*` seam and no mocked substitute for scientific work. Mark missing native/HPC evidence as blocked, not green.
4. Update owned spec, precise test ID rows and fixture register as needed in the same branch. Record screenshots/prototype parity evidence when UI changes.
5. Summarize modified files, commands/actual results, remaining gaps and next spec. Do **not** begin the next numbered spec automatically.

## Reference resolution, no implicit downloads

- `../alp-ui`: checkout of the **current native Qt Widgets library**. Public API: `src/alp_ui/components/__init__.py`, `docs/components.md`; composition exemplar: `gallery/showcase.py` and `docs/images/showcase.png` (one snapshot also bundled at `docs/design/references/alp-ui-showcase.png`). If missing, report a local setup blocker, do not replace with a parallel widget library.
- `../alpaca-pipelines`: **intended sibling checkout name**, with spaces and capitals. On case-sensitive systems verify it exactly. If the checkout is named `../alpaca-pipelines` instead, state the resolved path and verify it deliberately; do not assume either exists or clone automatically. Never execute training in the HPC.
- `docs/design/prototypes/training-first/index.html`: checked-in interactive **UX source of truth** for visible journey; its JavaScript simulates scientific work. Screenshot references are stored beside it. Crosswalk in `docs/design/UX_PARITY_MATRIX.md`.
- `docs/priv/`: included in private handoff ZIP, **ignored by Git**. Never `git add -f docs/priv` or copy a private hostname/path into tracked materials.

**Priority for a conflict:** required user prototype workflow and target specs > stale scaffold; Trainer domain/security rules govern scientific correctness; `alp-ui` public API governs how native controls are composed. Log unavoidable platform-specific visual divergences rather than silently changing the interaction.
