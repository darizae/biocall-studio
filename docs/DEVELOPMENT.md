# Development and local execution

BioCall Studio is one Python distribution, one PySide6 app and one public `biocall-studio` console command. Use **Python 3.11–3.13**. This guide installs the **published, hash-verified library wheels**, never a sibling editable `../alp-ui` or `../bioacoustics-dl-toolbox` checkout. Their exact versions, tag target source SHAs, wheel URLs and SHA-256 digests are recorded in [`pyproject.toml`](../pyproject.toml).

## Install from published wheels

From a clean BioCall Studio checkout on macOS or Linux with the GitHub CLI authenticated if required:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
mkdir -p .release-wheels
gh release download v0.1.0a1 --repo darizae/alp-ui \
  --pattern 'alp_ui-0.1.0a1-py3-none-any.whl' --dir .release-wheels
gh release download v0.3.0 --repo darizae/bioacoustics-dl-toolbox \
  --pattern 'bioacoustics_dl_toolbox-0.3.0-py3-none-any.whl' --dir .release-wheels
printf '%s  %s\n' \
  20590366d06591837c2567df1191b472b9db494e5440ce3a3fadfbf1b8d53d6c \
  .release-wheels/alp_ui-0.1.0a1-py3-none-any.whl | shasum -a 256 -c -
printf '%s  %s\n' \
  c0f7679cbf788c2900eff26b8db719941a513fc96b5f28348e2838c8df595b28 \
  .release-wheels/bioacoustics_dl_toolbox-0.3.0-py3-none-any.whl | shasum -a 256 -c -
.venv/bin/python -m pip install --no-deps .release-wheels/*.whl
.venv/bin/python -m pip install -e '.[test,integration]'
.venv/bin/python -m pip check
.venv/bin/python -m biocall_studio
```

For application use without contributor test tools, substitute `pip install -e .` after installing the wheels. The latter `-e` refers only to the **Studio checkout**, not an upstream sibling; neither published wheel is editable. If GitHub CLI cannot fetch an asset, use its exact public release URL from `pyproject.toml` and **verify the same SHA-256** before installation. A missing/mismatched wheel blocks the environment. On Windows, translate activation/path/hash steps on an actually verified native platform rather than claiming these Unix commands are qualified. No desktop installer is currently published.

Check actual installed versions/import origins:

```bash
.venv/bin/python -c 'from importlib.metadata import version; import alp_ui, bioacoustics_dl_toolbox; print(version("alp-ui"), alp_ui.__file__); print(version("bioacoustics-dl-toolbox"), bioacoustics_dl_toolbox.__file__)'
```

## Tests and audit

For owner-authorized development on an interactive macOS machine, `scripts/run_tests.py background` forces offscreen Qt. For a focused test (ordinary full suite is reserved for spec 05 during the current release series):

```bash
.venv/bin/python scripts/run_tests.py background tests/unit/test_review_spectrograms.py -q
.venv/bin/python scripts/run_tests.py background tests/integration/test_review_cache_generation.py -q
.venv/bin/python -m ruff check src tests scripts
.venv/bin/python scripts/audit_test_ids.py
.venv/bin/python scripts/audit_docs.py
.venv/bin/python scripts/verify_handoff.py
.venv/bin/python scripts/check_fixtures.py
```

The test-index audit verifies referenced ID names, **not** that tests pass. Qt offscreen tests, static audits and genuine native Cocoa/Windows execution are separate forms of evidence. Any visible native sessions require a scoped owner-approved task and must be closed after capture. Physical audio, accessibility, install/uninstall, platform-specific workers and signing cannot be inferred from offscreen tests.

Tests use deterministic local WAV fixtures; never run a write-capable manual session on tracked test data. Keep real/private field audio, HPC paths, tokens and staging artifacts out of Git. [Fixture index](INTEGRATION_TEST_DATA.md) and [test behavior index](INTEGRATION_TEST_BEHAVIORS.md) remain authoritative for scripted audits.

## Scientific and release responsibilities

Train/Detect/Review own their separate state and scientific outputs; [architecture](ARCHITECTURE.md), [model contract](science/MODEL_EXPORT_CONTRACT.md), [release process](RELEASE_PROCESS.md) and [current release route](IMPLEMENTATION_SEQUENCE.md) remain authoritative. The upstream spectrogram is a **Review display raster**, never the CNN feature representation. The full Studio suite, installer-source freeze, native packaging and release promotion belong to later release specs. No published Studio installer is claimed.
