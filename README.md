# alpaca Desktop Trainer

**A local desktop application for preparing supervised bioacoustics datasets and training CNN or Random Forest models.** Designed for working with existing WAV collections on your computer, without importing or moving your recordings.

> **Development preview:** The PySide6 application currently implements the initial navigation and Collection-selection shell only. Collection scanning, Dataset building, CNN/RF training, and installers are still planned. Never interpret a selected folder as a validated Collection or a simulated browser run as scientific output.

## What you can do

Choose an existing folder with `recordings/` and `positives/`, read the built-in instructions for preparing positive examples, and navigate the Collection/Dataset/Model/Run views. Once the remaining specs are implemented, the app will validate inputs, assemble an immutable Dataset, and train a CNN or Random Forest locally with traceable artifacts.

**Input folder example:**

```text
Rainforest-dawn/
  recordings/
    SITE_001.wav
  positives/
    SITE_001__start-012500ms__end-014900ms__call01.wav
```

Positive filename timestamps refer to the *original Source Recording* and are expressed in integer milliseconds. See [Selecting a Collection](docs/wiki/SELECTING_A_COLLECTION.md) for the complete naming rules.

## Current native application

These are real PySide6 application captures from macOS using the sibling `alp-ui` checkout. They
show the currently implemented Spec 01 shell; no simulated Collection, Dataset, Model, Run or
scientific result is presented.

**Select a Collection — native macOS app**

![Native macOS alpaca Desktop Trainer Select Collection screen](docs/design/evidence/spec-01-native/select.png)

**Selecting a Collection guidance — native macOS app**

![Native macOS alpaca Desktop Trainer Wiki screen](docs/design/evidence/spec-01-native/wiki.png)

The complete [native evidence set and parity review](docs/design/evidence/README.md) also covers
Settings, all four initial empty routes, keyboard interactions and a narrow resized window.

## Interactive design reference

The checked-in browser prototype remains the normative journey for later specs. Its images are
**design targets**, not screenshots of the current native app, and its sample data/training progress
are simulated.

![Interactive UX prototype target for Select Collection](docs/design/prototypes/training-first/landing-preview.png)

Explore the [interactive UX prototype](docs/design/prototypes/training-first/index.html) and the
blocking [prototype acceptance gate](docs/design/PROTOTYPE_ACCEPTANCE.md).

## Run the current development app (macOS)

Prerequisites: Python **3.11–3.13**, an adjacent native [`alp-ui`](docs/design/ALP_UI_CONSUMER_CONTRACT.md) checkout at `../alp-ui`, and Git LFS for the versioned audio example. Use the repository root as your working directory. These instructions install to a **project-local `.venv`**; no global Python packages are needed.

```bash
# From your repos/alpacaDesktopTrainer directory
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[gui,test,integration]'
.venv/bin/python -m pip install -e ../alp-ui

# Start the native PySide6 app
.venv/bin/python -m alpaca_desktop
```

If you have already installed the package in `.venv`, **launch it directly**:

```bash
.venv/bin/python -m alpaca_desktop
# Equivalent installed console entry point:
.venv/bin/alpaca-desktop
```

Optional isolated Application Settings, useful during development:

```bash
.venv/bin/python -m alpaca_desktop --settings-dir /tmp/alpaca-trainer-settings
```

On Windows the development interpreter path is `.venv\Scripts\python.exe`; Windows native UI/release qualification is scheduled for Spec 07. This is a development setup, **not** a packaged installer. For environment troubleshooting and test commands, see [Development](docs/DEVELOPMENT.md).

## Run checks

```bash
# Git LFS is needed only for versioned binary test fixtures in the actual checkout:
git lfs install
# If the repo tracks registered fixtures and you need those exact bytes:
# git lfs pull
# .venv/bin/python scripts/check_fixtures.py
.venv/bin/python scripts/verify_handoff.py
.venv/bin/python -m pytest -q tests/unit
# On a native macOS desktop (not merely Qt offscreen):
.venv/bin/python -m pytest -q tests/integration
```

`docs/priv/` contains optional machine-specific HPC source instructions in the **private handoff archive**; it must never be tracked by Git. The optional `tests/data/example_collection/` in an actual Git checkout contains synthetic WAVs, **not** confidential HPC exports. The transfer ZIP intentionally omits `tests/data/`; generating temporary real WAV test cases is supported. Windows and packaged-app tests remain future qualification gates.

## Developer documentation (start here if you are a coding agent)

Read [AGENTS.md](AGENTS.md) → [agent routing](docs/agent/ROUTING.md) → **only the active spec** in [specs index](docs/specs/README.md). Do **not** read the entire documentation tree by default.

**Current milestone:** [Spec 01 acceptance closeout](docs/specs/SPEC_01_CLOSEOUT.md) is implemented
with native evidence and remains the review boundary for this branch. After it is accepted and
merged, the next implementation stage is [Collection scanning](docs/specs/02-collection-scan-and-metadata.md),
followed by the later Dataset, Training, macOS and Windows installer specs. This branch does not
contain Spec 02 work.

Reference map (open only for the task at hand): [vision](docs/VISION.md), [glossary](docs/GLOSSARY.md), [domain workflow](docs/models/USER_WORKFLOWS_AND_DATA_MODEL.md), [workflow rules](docs/models/WORKFLOW_RULES.md), [architecture](docs/ARCHITECTURE.md), [UX parity](docs/design/UX_PARITY_MATRIX.md), [scientific sibling source map](docs/agent/SOURCE_MAP.md), [unit testing](docs/UNIT_TESTING.md), [integration testing](docs/INTEGRATION_TESTING.md), [fixture policy](docs/INTEGRATION_TEST_DATA.md), [Git/branch delivery](docs/agent/GIT_DELIVERY.md). The scientific pipeline is referenced from the verified sibling `../alpaca-pipelines` checkout; it is not vendored here.
