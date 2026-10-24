# Development and local execution

## Toolchain

- Python **3.11–3.13** with a project-local `.venv`, PySide6 and `pytest`, `pytest-qt`, `ruff` as defined by `pyproject.toml`.
- macOS is the day-to-day native implementation and integration-test platform. Windows is a target **only after a separate native qualification gate**.
- Install `../alp-ui` from its **native PySide6 sibling checkout or locally built wheel**. Do not substitute a PyPI package or the similarly named web UI project. Verify installed public Components/API from the checkout.
- When implementing CNN/RF, inspect the intended sibling `../alpaca-pipelines` after confirming its exact directory and commit; if unavailable, report it and resolve an owner-approved local checkout rather than silently assuming remote code. Install only the real training dependencies needed for that integration, pinned/tested as part of the Training spec. Do not assume the reference repository's CLI or output manifests are application contracts.

A scaffold-level local setup from repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[gui,test,integration]'
# When available, install/build the sibling PySide6 Widgets library:
python -m pip install -e ../alp-ui
python -m alpaca_desktop
```

**Status:** the checked-in executable is a development scaffold, not the specified full Trainer. Follow the numbered specs before interpreting existing UI behavior as product acceptance. Do not add an undocumented dependency or fake fallback if a required sibling checkout is unavailable.

## Tests and audit

```bash
python -m pytest tests/unit -q
python scripts/audit_test_ids.py
# On native macOS with Qt libraries and appropriate local fixtures:
python -m pytest tests/integration -q
python -m ruff check src tests scripts
```

The only initial CI-eligible suite is Qt-independent `tests/unit/` plus inexpensive static checks, without HPC access; CI pulls only the small versioned Git LFS synthetic fixture bytes when executing the integrity audit. Real Qt/application/filesystem and QProcess/in-process workflow integration executes locally on native macOS with test-specific temporary Collection roots and isolated Application Settings. Capture run commands/results by indexed ID. `pytest-qt` tests need a real compatible platform plugin; headless/offscreen Qt smoke is not a native-dialog or packaged-app qualification.

Test data: use short deterministic WAV generators and a generated many-row metadata index. If an actual field codec/checkpoint cannot be represented synthetically, consult the protected [`INTEGRATION_TEST_DATA.md`](INTEGRATION_TEST_DATA.md) policy; the untracked `docs/priv/hpc-source-access` skill is read-only and never required by CI. For binary fixtures maintained through Git LFS validate SHA-256 and object presence, not a pointer file.

## Implementation / platform gates

Check [`IMPLEMENTATION_SEQUENCE.md`](IMPLEMENTATION_SEQUENCE.md) and [`specs/README.md`](specs/README.md) for exact scope, local tests and publication rules. No Dataset or Model may be called produced until a real successfully validated Artifact exists. For Windows, document actual environment and native results; macOS path-unit success is not Windows qualification.

## Current `alp-ui` and visual workflow

Use the **public** updated UI library checkout at `../alp-ui`; install it locally in a test environment (`python -m pip install -e ../alp-ui`) where the sibling checkout exists. It exposes `FolderPicker`, `HelpHint`, and `Plot`, as detailed in [consumer contract](design/ALP_UI_CONSUMER_CONTRACT.md). Run sibling `python -m gallery.showcase` as native composition reference, then open checked-in `docs/design/prototypes/training-first/index.html` in a browser for interaction reference. Report absent sibling environments instead of downloading a new library silently. Use target UI screenshots and `pytest-qt`; offscreen does not replace native manual review.

## Test fixture/release preflight

Install `git-lfs` **before initializing/staging** this ZIP's `tests/data/example_collection/*.wav`. `python scripts/verify_handoff.py` checks tracked document references/private ignore/prototype in CI, while `--require-private` additionally checks ZIP-only HPC materials; `python scripts/check_fixtures.py` checks example WAV content/hashes; `python scripts/audit_test_ids.py` checks docstring indexes (not coverage). `tests/data/README.md` records real local synthetic WAVs; do not call them HPC downloads. Private HPC skill is shipped in ZIP but ignored in Git. Release plan and native `.dmg` / `.exe` gates: [RELEASE_PROCESS](RELEASE_PROCESS.md), [spec 06](specs/06-macos-release-and-installer.md), [spec 07](specs/07-windows-release-and-installer.md).
