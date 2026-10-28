# Git delivery — branch, tests and commits

Open when **starting or finishing** a task, not as a precondition for every code read. A transferred ZIP normally has no `.git`; never infer prior commits from its documentation. Never erase/rebase an existing branch without approval.

## Start

```bash
git rev-parse --is-inside-work-tree
git status --short --branch
git branch --show-current
git log -1 --oneline
```

If no repository exists, initialize Git **once**, after installing Git LFS and verifying `.gitattributes` for `tests/data/**/*.wav`; inspect ignored/private files before adding anything. If Git exists, preserve its branches/history and resolve unrelated uncommitted changes before starting. For Studio/Detect follow the [stage branches](../IMPLEMENTATION_SEQUENCE.md): establish `detect` from reviewed `main` when appropriate; each active `detect-stNN-purpose` starts from **reviewed current `detect`**, not from a preceding unreviewed feature branch. Continue an existing unmerged active-spec branch rather than creating a duplicate. Separate upstream toolbox/`alp-ui` changes require their own focused branches in those checkouts.

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

**Definition of handoff:** branch, actual full commit SHA, clean status, modified files, exact test commands/results, platform, covered/deferred cases, UX/upstream/fixture caveats and next review gate. Do not push, publish or begin the next spec automatically.

## Reviewed LOCAL integrations — never push

After the owner accepts a stage and its exact evidence: review the destination branch/working tree and actual diff, then **locally** integrate `detect-stNN-purpose` into `detect` using an explicit review-approved merge. Verify the merged tree, record actual merge SHA/status and rerun relevant validation if the merge changed code. The next stage branches only from that reviewed `detect`. Do not infer that a ZIP contains Git history; do not invent SHAs; never force-update or auto-merge divergent histories. **ST-11 only:** after complete unified qualification, updated existing macOS/Windows requirements and owner approval, locally merge reviewed `detect` into `main`. A failed test/blocked gate keeps `main` unchanged. No `git push`, tags, package publication, signing or releases in this delivery workflow.

If a stage requires a toolbox or `alp-ui` fix, commit on its **independent** library branch, run its own tests and record a real SHA. Review/approve local merge into that library's `main` before treating it as the downstream dependency; reinstall/verify runtime and affected BioCall Studio integration. Do not push any repository. If library checkout/rights/evidence are absent, mark the active stage blocked instead of changing a different repo or copying unverified internals.

## Multi-repository upstream fix

For [upstream workflow](UPSTREAM_TOOLBOX_WORKFLOW.md) or a pertinent scientific defect, follow the [upstream toolbox workflow](UPSTREAM_TOOLBOX_WORKFLOW.md). Commit independently in the owning sibling library and BioCall Studio; verify/reinstall the active `.venv`, rerun affected integration tests and report **both** SHAs and module import provenance. The same ownership discipline applies to `../alp-ui` UI primitives; do not patch its internals in the desktop consumer. A release must package a wheel built from a committed toolbox revision, not depend on a sibling editable checkout.
