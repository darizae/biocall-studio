# Local integration examples — tracked scientific data

This directory contains a **real, tiny synthetic WAV Collection**. It is **not sourced from HPC**,
not sensitive audio, and its synthetic metrics are not evidence of a useful field detector. The
six WAVs in `example_collection/` are source bytes delivered in the ZIP, **intended for Git LFS at
the first Git import**. File contents are checked by
[`scripts/check_fixtures.py`](../../scripts/check_fixtures.py); [`SHA256SUMS`](SHA256SUMS) is the
canonical per-file checksum list. It is sufficient for a small Dataset plus genuine CNN/RF smoke
workflow, but manual sessions should generate a disposable copy by following the
[manual end-to-end trial](../../docs/MANUAL_WORKFLOW.md) so `.alpaca/` outputs do not dirty this
tracked fixture.

## Versioned fixture register

| ID/revision | Paths and bytes | Source / rights / anonymization | Transformation / tested discriminant | Classes and expected future owners |
|---|---|---|---|---|
| **FX-SYN-001 r1** | `example_collection/recordings/REC_{A,B,C}.wav` (3 × 256044 B) and `example_collection/positives/REC_*__start-*ms__end-*ms__call*.wav` (3 × 32044 B); total **864264 B** | Produced by repo-local integer-only algorithm, **fully synthetic**; no identity, speech, recordings or HPC assets; project-owned fixture | `scripts/generate_example_collection.py`; mono signed PCM16, 16,000 Hz; three distinct 8 s source recordings; each has one exact 1 s source-time excerpt (A=1000–2000 ms, B=3000–4000 ms, C=5000–6000 ms), intentionally distinct waveforms | `TD-COL`, `TD-WAV`, `TD-MINE`, `TD-SPLIT`, `TD-TRAIN` (subset only); future `IT-COL-001`, `IT-DB-001`, `IT-TRAIN-*` when genuinely asserted |

**Revision discipline:** Never mutate bytes under an existing `FX-*` revision without creating a new explicit revision and updating hash register/test assumptions in same PR. The test index lists planned cases, not tests passed. At each implementing spec, verify the fixture **is scientifically sufficient** for the selected case; e.g. CNN/RF training might need expanded temporary generated data. If not sufficient, revise **generators and fixtures first**, then write/execute real integration tests rather than faking completeness.

## Regenerate safely

```bash
python scripts/check_fixtures.py
python scripts/generate_example_collection.py --write --output /tmp/trainer-generated-example
# Regenerating the tracked copy requires conscious revision + hash review:
# python scripts/generate_example_collection.py --write --replace --output tests/data/example_collection
```

The `--replace` option is deliberately explicit. Regeneration must update `SHA256SUMS`, validate with check_fixtures and be reviewed. Do not assume the checked-in demo alone proves trainer scientific metrics.

## Git LFS contract

Before `git add` or first commit, install and initialize **Git LFS** (`git lfs install`). `.gitattributes` routes every `tests/data/**/*.wav` and selected binary model formats through LFS. Verify:

```bash
git check-attr filter tests/data/example_collection/recordings/REC_A.wav  # lfs
git add .gitattributes tests/data/
git lfs ls-files                      # after staging/commit, WAV paths appear
git lfs fsck                          # verify local objects
git lfs pull                          # ensure binary content after remote clone
python scripts/check_fixtures.py     # verify SHA256 and source-time excerpts
```

Do not accidentally commit regular Git blobs if `git-lfs` is unavailable. `git check-attr` alone checks only the attribute declaration, **not** that a filter binary was installed or LFS pointers were actually staged.

## Optional permissioned HPC exemplar

`FX-HPC-*` IDs are **not included or available** in this handoff. To add one, follow [`docs/INTEGRATION_TEST_DATA.md`](../../docs/INTEGRATION_TEST_DATA.md), the untracked/private HPC skill in `docs/priv/` and the authorized read-only exact-file helper. A legitimate HPC-derived fixture requires privacy/rights approval, anonymization, exact neutral provenance/transform recipe, SHA256, separate new `FX-HPC-*` registration, binary Git LFS and dependent test evidence. HPC or credentials must never be needed at CI/runtime.
