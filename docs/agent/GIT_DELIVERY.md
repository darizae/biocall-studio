# Git / branch / commit contract — agent delivery

Read this **only when beginning or finishing a spec/closeout**, not for ordinary scientific implementation. A ZIP extraction is not a Git repository; `.git` is commonly omitted from shared archives. Never claim a commit without inspecting the actual checkout. Never commit `docs/priv/`, secrets, `.venv/`, or platform-specific app settings.

## Before changing files

```bash
git rev-parse --is-inside-work-tree
git status --short --branch
git branch --show-current
git log -1 --oneline
```

If Git is already initialized, work from owner-approved `main` (or the branch that contains the previous accepted spec), and verify no unrelated uncommitted changes. Use `spec/NN-short-name` for a new numbered spec, `fix/01-ux-and-delivery-closure` for this specific closeout, `fix/short-name` for independent bugs, `docs/short-name` for docs-only. Avoid deleting/changing user branches or rebasing without approval.

If the extracted ZIP has **no `.git`**, create a new repository once; do not fake a past history. Install Git LFS **first**, then:

```bash
git lfs install
git init -b main
git check-attr filter tests/data/example_collection/recordings/REC_A.wav
# Must print: ... filter: lfs (even if payload was omitted from the transfer ZIP)
# Only if registered fixed fixtures are actually present in the Git checkout:
# python scripts/check_fixtures.py
python scripts/verify_handoff.py
git add .
git status --short --ignored
# Ensure docs/priv/ is ignored and no unplanned bytes are staged
git diff --cached --check
git commit -m "chore: import Trainer Spec 01 implementation snapshot"
git switch -c fix/01-ux-and-delivery-closure
```

If `.git` exists and spec 01 was not yet merged, use the **existing** `spec/01-shell-and-test-foundation` branch to finish it, rather than creating two partial feature branches. If changes were already performed on main, create a fix branch from that state before making the closure changes. Do not make a false claim that the initial import was a Spec 01 feature commit.

## Before handoff / PR

- Run focused red → green tests, broader native tests and static checks; record commands, failures, platform and what was not run. Do not weaken an assertion to achieve green.
- Inspect intended source/test/docs/screenshots/fixture changes. Ensure `docs/priv` is not tracked (`git ls-files docs/priv` empty). If registered WAV fixtures are tracked, `git lfs ls-files` and `git lfs fsck` verify their objects; otherwise record that this transfer omitted `tests/data/`; `git diff --check` is clean. Avoid binary outputs other than sanctioned evidence PNGs and versioned LFS fixtures.
- Stage **explicitly reviewed** paths (or `git add .` only after scrutinizing `git status --short --ignored`), then commit with an imperative subject tied to the scope, e.g.:

```bash
git add README.md docs/ src/ tests/ scripts/
git diff --cached --check
git diff --cached --stat
git commit -m "fix(spec01): align native UX and document local setup"
git status --short
git branch --show-current
git log -1 --format='%h %s'
git rev-parse HEAD
```

- **Done means a real commit exists on the expected branch and the working tree is clean**, with screenshots/tests available for review. State the actual full SHA, branch, commands/results, remaining blocked cases, and whether the spec is ready for review/merge. Never auto-merge or automatically begin the next spec.
- On platforms lacking Git LFS, do not stage WAVs as ordinary blobs: report blocking setup and defer commit until LFS is installed.

Recommended conventional subjects: `feat(spec02): scan and validate Collections`, `feat(spec03): build immutable Datasets`, `feat(spec04): supervise worker Runs`, `feat(spec05): train CNN and RF models`, `build(spec06): package notarized macOS installer`, `build(spec07): qualify Windows installer`. A subject alone is not proof: the SHA and clean `git status` matter.
