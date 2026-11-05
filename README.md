# BioCall Studio

BioCall Studio is a native desktop application for bioacoustics research. Its Train workflow
builds reproducible Datasets and CNN or Random Forest Models from labeled recordings. Detect
validates those Models, inventories unseen WAV files, and finds and refines candidate calls.
Review opens verified Detect Results, records reproducible Call/Not a call decisions, renders
source-linked audio and spectrograms, and publishes finalized reviewed corpora as individual WAVs,
a combined WAV with Raven TSV, or both.

BioCall Studio supports Python **3.11–3.13**. Source development requires Git and adjacent,
owner-reviewed checkouts of:

- `../bioacoustics-dl-toolbox` at the revision recorded in `pyproject.toml`;
- `../alp-ui` at the revision recorded in `pyproject.toml`.

## Install and launch from source

From a BioCall Studio checkout with those siblings in place, create a clean environment:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '../bioacoustics-dl-toolbox[rf]'
.venv/bin/python -m pip install -e ../alp-ui
.venv/bin/python -m pip install -e '.[test,integration]'
```

Run the local application from the command line with:

```bash
.venv/bin/python -m biocall_studio
```

The equivalent installed console command is:

```bash
.venv/bin/biocall-studio
```

These commands intentionally address the virtual environment directly, so they also work when
an existing `.venv` has stale shell-activation metadata. It is the only public application
command. Windows source and packaging commands remain
unqualified until they are exercised on native Windows; see
[development guidance](docs/DEVELOPMENT.md).

For test commands, dependency checks, and platform status, see
[Development](docs/DEVELOPMENT.md). For a genuine local workflow using deterministic audio, see
[Manual workflow](docs/MANUAL_WORKFLOW.md).
