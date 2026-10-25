# Upstream-first changes to `bioacoustics-dl-toolbox`

**Read only when implementing or packaging a scientific feature that needs the separate `../bioacoustics-dl-toolbox` checkout.** This authorizes **targeted code fixes and improvements in the library itself**, with local testing and a **real library Git commit**, instead of hiding library defects behind Trainer-only monkeypatches, copies, or workarounds. The sibling `../alpaca-pipelines` remains a separately owned reference; this permission is not permission to rewrite the Trainer UX, add prediction, or silently change pipeline algorithms.

## Decide where the fix belongs

- **Toolbox upstream:** shared CNN model, preprocessing, trainer, checkpoint, numerical correctness, stable serialization, or genuinely reusable RF feature helper is faulty or missing. First reproduce the failure through the **public toolbox API**. A supported extension can be developed here when it is scientifically reusable and does not break existing callers.
- **Trainer downstream:** Collection path policies, Dataset/Run/Model manifests, immutable artifact publication, Qt/`alp-ui` UI, worker lifetime, app-specific configuration/preset mapping and adapters stay in the Trainer. Put only the adapter here, not a duplicate scientific algorithm.
- **`alpaca-pipelines` reference:** its orchestration/RF code must be inspected for behavior, but importing/copying code blindly or changing this repo as a side effect is not the toolbox workflow. Resolve ownership explicitly when a bug is actually in that layer. **Do not alter `../alpaca-pipelines` merely to make the Trainer pass.**

## Required procedure for a pertinent upstream change

1. **Preflight both repositories:** inspect `git status --short --branch` and HEAD SHAs in **Trainer** and **toolbox**. Do not discard existing changes or overwrite someone else's branch. Record the source failing behavior, scope, dependency and public API. Create a focused toolbox branch, e.g. `fix/<scientific-issue>` or `feat/<scientific-capability>`; keep Trainer work on its own `spec/05-...` branch. If the toolbox checkout is absent, not writable, or has conflicting changes, record the blocker instead of vendoring it or silently falling back to another package.
2. **Test upstream first:** add a failing toolbox unit or integration regression test at the actual public seam using deterministic inputs and meaningful numerical/serialization assertions; implement the smallest sound fix; run focused tests, appropriate broader toolbox tests, lint/type checks and any existing compatibility tests. Do not weaken tests or change defaults/serialization compatibility without an explicit versioned migration and updated Trainer contract.
3. **Commit upstream:** inspect `git diff --check`, stage only scoped source/tests/docs, and `git commit -m "fix: <specific toolbox behavior>"` (or accurate `feat:` subject). Record the **actual full toolbox commit SHA**, branch, clean tree and test commands/results. An upstream SHA from a ZIP or a claimed commit without `.git` evidence is not proof. **Do not force-push, rebase, merge, or publish the library automatically.**
4. **Reinstall in the Trainer environment:** use the Trainer's existing `.venv` and the toolbox's actual build metadata. On macOS, from the Trainer repository root, the typical command is:

   ```bash
   .venv/bin/python -m pip install -e ../bioacoustics-dl-toolbox
   .venv/bin/python -c "import bioacoustics_dl_toolbox as m; print(m.__file__)"
   .venv/bin/python -m pip show bioacoustics-dl-toolbox
   ```

   Adjust the last command to the verified distribution name if different. Verify the import resolves to **the separate local toolbox checkout**, not `../alpaca-pipelines/src/bioacoustics_dl_toolbox`, an old wheel, or a vendored copy. In editable mode Python may reflect code changes immediately, but explicitly rerun the install/import check to validate metadata and dependencies. Never use a global `pip`.
5. **Retest downstream:** run the affected **real** Trainer scientific unit/integration cases in the actual `.venv`, including a real trained CNN/Model structural reload for checkpoint changes and precise feature-schema tests for any RF change. Verify other unchanged consumers where practical. Capture the dependency SHA/version and any resolved config changes in exported Model provenance. **No inference or new-audio scoring** is introduced by this workflow.
6. **Lock for shipping:** update the Trainer's declared dependency/version constraints and reproducible lock/build provenance as appropriate. Editable path installs are **development-only**; macOS/Windows releases must package a validated wheel built from an identified, **committed** toolbox revision. Run clean-environment and installed-app checks independent of sibling source paths. Coordinate any backwards-incompatible API/format change with a versioned artifact/compatibility policy; do not silently mutate prior Models or presets.
7. **Report both repositories:** provide the Trainer branch/commit SHA **and** toolbox branch/commit SHA, tests and logs for each, reinstall command, actual `bioacoustics_dl_toolbox.__file__`, selected package version/wheel digest when applicable, and blockers. A Trainer-only green suite is **not sufficient** to close an upstream change. If the upstream fix cannot be committed/tested, report the relevant spec as blocked rather than quietly patching downstream.

This permission is **scoped to pertinent scientific-library changes needed by the active spec**. Prefer a small compatible change over broad refactoring; do not open the entire upstream repository or change unrelated APIs. The owner still controls upstream publishing/releases and overall Trainer spec acceptance.
