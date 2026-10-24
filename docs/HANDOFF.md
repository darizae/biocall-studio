# Unzip → new Git repository → first coding agent session

The archive is a **source/specification scaffold**, not a built/trained application or installer. Keep a clean parent-directory layout with these actual sibling checkouts:

```text
repos/
  alpacaDesktopTrainer/         # unzip this ZIP; repository root with AGENTS.md
  alp-ui/                       # existing native widgets library checkout
  alpaca-pipelines/             # existing scientific project; spelling/case intentional
```

Verify and create sibling folders independently; do not silently download or overwrite. `../alpaca-pipelines` is intended, `../alpaca-pipelines` can be manually declared only if it is in fact the local checkout. The first spec does not require a working pipeline checkout/HPC.

## Preflight (macOS)

```bash
cd 'repos/alpacaDesktopTrainer'
brew install git-lfs          # if not already installed; alternatives available for your OS
git lfs install
git init -b main
python scripts/verify_handoff.py --require-private
python scripts/check_fixtures.py
git check-attr filter tests/data/example_collection/recordings/REC_A.wav
# Must say: ... filter: lfs
# Review ignored private content before publishing:
git add .
git status --short --ignored
git ls-files docs/priv       # must return nothing
git lfs ls-files           # after staging/initial commit: inspect tracked WAVs
git commit -m 'Initialize alpaca Desktop Trainer scaffold and specs'
```

Do not commit if Git LFS was unavailable or generated binary WAVs were staged as ordinary Git objects. Ensure `docs/priv` appears as ignored, not staged. **The ZIP contains private HPC connection guidance** and must be shared only with trusted agents/users. No credentials should be present in tracked Git or release assets.

## Exact first-session agent task

> Read `AGENTS.md`, `docs/agent/ROUTING.md` and `docs/specs/01-shell-and-test-foundation.md`. Inspect the current `../alp-ui` public API and Showcase, and the checked-in prototype landing/Wiki. Follow the active spec’s minimal routed reading set. Implement **only spec 01** using red/green/refactor, real native Qt tests and the indexed case IDs; verify native screen/keyboard/folder-cancel parity. Do not implement science from the browser JS, read the entire docs tree, touch HPC, or begin spec 02. Report actual commands, tests, screenshot parity, blockers and remaining scope; keep one branch `spec/01-shell-and-test-foundation`.

## What is deliberately NOT inside Git

- `docs/priv/`: site-specific read-only SSH/HPC instructions and helper, present in this **ZIP only** and ignored once Git starts.
- HPC audio/checkpoints without explicit owner permission and anonymization: not invented or packaged. Git LFS synthetic fixtures are local verified test examples, *not* HPC evidence.
- `../alp-ui` and `../alpaca-pipelines` sources: kept in their **own adjacent** repositories; referenced, not bundled/duplicated.
- `.dmg` / `.exe`: only produced after release specs and native test gates pass.
