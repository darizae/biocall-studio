# Git delivery — branch, tests and commits

Open when **starting or finishing** a task, not as a precondition for every code read. A transferred ZIP normally has no `.git`; never infer prior commits from its documentation. Never erase/rebase an existing branch without approval.

## Start

```bash
git rev-parse --is-inside-work-tree
git status --short --branch
git branch --show-current
git log -1 --oneline
```

If no repository exists, initialize Git **once**, after installing Git LFS and verifying `.gitattributes` for `tests/data/**/*.wav`; inspect ignored/private files before adding anything. If Git exists, preserve its branches/history and resolve unrelated uncommitted changes before starting. For Studio/Detect follow the [stage branches](../IMPLEMENTATION_SEQUENCE.md): `detect` from `main`, then `detect-stNN-purpose` from `detect`. For independent work use `docs/purpose` or `fix/purpose` as applicable. Continue an unmerged active spec branch rather than making a duplicate.

## Deliver

Run owning `UT-*`, actual `IT-*`, relevant static audits and native visual evidence checks. Document genuine failures/blockers, not inferred green status. Before committing:

```bash
git status --short --ignored
git ls-files docs/priv
git diff --check
git add <reviewed-paths>
git diff --cached --check
git diff --cached --stat
git commit -m "feat(specNN): implement verified scope"
git status --short
git rev-parse HEAD
```

Replace `<reviewed-paths>` and the example message with the actual scope. `git ls-files docs/priv` must be empty. Never stage credentials, `.venv`, unapproved WAVs or private HPC notes. If registered WAVs are tracked, verify `git lfs ls-files` and `git lfs fsck`; if transfer ZIP omits `tests/data/`, do **not** treat that as a regression. Check real native screenshots and README links when a UI spec owns them.

**Definition of handoff:** branch, actual full commit SHA, clean status, modified files, exact test commands/results, platform, covered/deferred cases, UX/HPC/fixture caveats and next review gate. Do not push, merge, publish or begin the next spec automatically.

## Multi-repository upstream fix

For [upstream workflow](UPSTREAM_TOOLBOX_WORKFLOW.md) or a pertinent scientific defect, follow the [upstream toolbox workflow](UPSTREAM_TOOLBOX_WORKFLOW.md). Commit independently in `../bioacoustics-dl-toolbox` and Trainer, reinstall/check the active `.venv`, rerun affected integration tests, and report **both** SHAs and import provenance. A release must package a wheel built from a committed toolbox revision, not depend on a sibling editable checkout.
