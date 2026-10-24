# Unzip → Git checkout → agent session (current: Spec 01 closeout)

The archive is a **source/specification scaffold**, not a built/trained application or installer. Keep a clean parent-directory layout with these actual sibling checkouts:

```text
repos/
  alpacaDesktopTrainer/         # unzip this ZIP; repository root with AGENTS.md
  alp-ui/                       # existing native widgets library checkout
  alpaca-pipelines/             # existing scientific project; spelling/case intentional
```

The scientific sibling is exactly **`../alpaca-pipelines`** (lowercase with hyphen); verify it before scientific implementation. Do not silently download, rename or overwrite. Spec 01 does not need pipeline/HPC access.

## Preflight for a NEW Git checkout (macOS)

**If this project already has a `.git/` repository, do not run `git init` or create a second initial commit.** Instead open the existing repository and follow [Git delivery](agent/GIT_DELIVERY.md) for the Spec 01 closeout branch. The following block is only for a fresh extracted snapshot without Git history.

```bash
cd 'repos/alpacaDesktopTrainer'
brew install git-lfs          # if not already installed; alternatives available for your OS
git lfs install
git init -b main
python scripts/verify_handoff.py --require-private
## Optional: only after pulling materialized registered fixtures in a real Git checkout:
# python scripts/check_fixtures.py
git check-attr filter tests/data/example_collection/recordings/REC_A.wav
# Must say: ... filter: lfs
# Review ignored private content before publishing:
git add .
git status --short --ignored
git ls-files docs/priv       # must return nothing
git lfs ls-files           # only if this checkout actually tracks WAV fixture objects
git commit -m 'chore: import Trainer Spec 01 implementation snapshot'
git switch -c fix/01-ux-and-delivery-closure
```

Do not commit if Git LFS was unavailable or generated binary WAVs were staged as ordinary Git objects. Ensure `docs/priv` appears as ignored, not staged. **The ZIP contains private HPC connection guidance** and must be shared only with trusted agents/users. No credentials should be present in tracked Git or release assets.

## Next agent task after first Spec 01 pass

> Read `AGENTS.md` and `docs/agent/ROUTING.md`, then **`docs/specs/SPEC_01_CLOSEOUT.md`**. Do not begin Spec 02 yet. Review current `README.md`, native `window.py`, real `alp-ui` Showcase and the bundled Select/Wiki prototype. Add test-first UX fixes, persist real native macOS screenshots and design parity ledger, verify `.venv` install/run commands and Git LFS examples. Finish on the right branch with a real commit, clean tree, exact SHA and native-test report. For detailed branch and commit commands see [`docs/agent/GIT_DELIVERY.md`](agent/GIT_DELIVERY.md). A ZIP archive has no history; it cannot attest to earlier commits.

## What is deliberately NOT inside Git

- `docs/priv/`: site-specific read-only SSH/HPC instructions and helper, present in this **ZIP only** and ignored once Git starts.
- `tests/data/` **is deliberately not shipped in transfer ZIPs**, even if versioned by Git/Git LFS in the active repository. Use the existing checkout's LFS objects if available or generate small real WAVs in temporary test folders. Omitted ZIP payload does not mandate fixture restoration.
- HPC audio/checkpoints without explicit owner permission and anonymization: not invented or packaged. Synthetic fixtures, where present, are *not* HPC evidence.
- `../alp-ui` and `../alpaca-pipelines` sources: kept in their **own adjacent** repositories; referenced, not bundled/duplicated.
- `.dmg` / `.exe`: only produced after release specs and native test gates pass.
