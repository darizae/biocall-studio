# Development and local execution

## Toolchain and dependency provenance

Use Python **3.11–3.13**. BioCall Studio is one `biocall-studio` distribution and one
`biocall_studio` package. The adjacent dependency revisions are recorded under
`tool.biocall-studio.science` in `pyproject.toml`:

- `../bioacoustics-dl-toolbox` supplies bounded audio, CNN, and RF feature primitives;
- `../alp-ui` supplies the public native PySide6 widgets and theme.

Do not substitute similarly named packages or a copied toolbox inside another repository. Confirm
the installed imports before scientific or native UI work:

```bash
python -c "import alp_ui, bioacoustics_dl_toolbox; print(alp_ui.__file__); print(bioacoustics_dl_toolbox.__file__)"
```

Create a clean source environment from the repository root:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '../bioacoustics-dl-toolbox[rf]'
.venv/bin/python -m pip install -e ../alp-ui
.venv/bin/python -m pip install -e '.[test,integration]'
.venv/bin/python -m biocall_studio
```

`.venv/bin/biocall-studio` is the equivalent and only public console command. Worker arguments
are private. Train and Detect supervisors invoke the same `.venv/bin/python` interpreter with a
private `--worker <mode> ...` argument in development.

## Tests and audit

Use the repository runner instead of invoking the Qt suite directly on an interactive desktop. Its
default `background` mode selects Qt's offscreen platform, runs every ordinary non-soak test except
the explicitly Cocoa-only assertions, and never maps application windows onto the desktop:

```bash
.venv/bin/python scripts/run_tests.py background
.venv/bin/python scripts/run_tests.py background tests/integration/test_detect_runs.py -q
```

For a shorter TDD loop, `quick` additionally excludes wheel/install boundary tests marked
`packaged`. It is not the before-commit full suite:

```bash
.venv/bin/python scripts/run_tests.py quick tests/unit -q
```

Native Cocoa qualification remains separate because offscreen rendering cannot prove macOS color
scheme, window-manager, native-dialog or installed-app behavior. This command may cover or focus
the active desktop and therefore requires an explicit acknowledgement. Run it only with the
owner's agreement or in a dedicated macOS test session:

```bash
.venv/bin/python scripts/run_tests.py native --allow-visible
```

The background run and native run are complementary evidence; never report the background run as
native Cocoa, installed macOS or Windows qualification. Then run the non-pytest audits:

```bash
python -m ruff check src tests scripts
python scripts/audit_test_ids.py
python scripts/verify_handoff.py
python scripts/check_fixtures.py
git diff --check
```

Ordinary pytest excludes the durability marker. Initiate the soak separately:

```bash
BIOCALL_STUDIO_SOAK_REPORT=/tmp/biocall-studio-soak-observations.json \
  python -m pytest -m soak tests/integration/test_long_running_runs.py -q -s
```

Real Qt/application/filesystem and QProcess integration uses isolated temporary Collections and
application data in both modes. Offscreen rendering does not replace native visual or dialog
review. Windows commands, filesystem locking, QProcess behavior, packaging, and installers remain
unqualified until exercised on native Windows under the release gate.

## Data and release boundaries

Tests use deterministic short WAV generators and the policy in
[`INTEGRATION_TEST_DATA.md`](INTEGRATION_TEST_DATA.md). Never point a write-capable manual session
at tracked fixtures. Validate Git LFS objects where required and keep private HPC material
untracked.

Follow [`IMPLEMENTATION_SEQUENCE.md`](IMPLEMENTATION_SEQUENCE.md) and the active stage only.
Installer, signing, publication, and cross-workflow end-to-end claims remain owned by ST-11 and the
[`RELEASE_PROCESS.md`](RELEASE_PROCESS.md).
