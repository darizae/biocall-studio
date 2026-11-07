# 05 — FINAL: BioCall Studio base suite on released upstream wheels, then release

**This is the final spec of the entire three-repository series. Execute after toolbox 03, alp-ui 03, BioCall Studio 01–03, and **both** completed native installer lanes of BioCall Studio 04. No earlier BioCall Studio spec should claim the final full-app regression suite or create the public app tag.**

## Strict input gate

1. Re-query **actual latest published GitHub Releases and tags** of [alp-ui](https://github.com/darizae/alp-ui) and [bioacoustics-dl-toolbox](https://github.com/darizae/bioacoustics-dl-toolbox), not merely version strings from `pyproject.toml` or spec branch commits. Expected candidate releases are `v0.1.0a1` for alp-ui and `v0.3.0` for toolbox **if those specs actually shipped**. Use the latest approved compatible published releases; if a newer release has appeared since installer build, reconcile compatibility, pins and hashes, rebuild installers if changed, then retest. Do not silently substitute mutable branch HEAD or an unpublished package.
2. Verify the exact immutable tag SHA, release download URL, wheel/sdist SHA-256, declared Python/Qt/toolbox dependency and redistribution terms for both libraries. Install **the released artifacts** into a fresh Python 3.11–3.13 supported environment for the source Studio test runner (prefer matching Studio's recorded candidate Python version); do not use editable sibling checkouts, a local source path, or an unverified registry build. Since toolbox uses GitHub Releases rather than PyPI, use an auditable wheelhouse or explicit approved artifact URL and install the matching `[rf]` dependencies. Show `importlib.metadata.version(...)` and `module.__file__` for both imports. Pin/compare to `pyproject.toml` and `[tool.biocall-studio.science]`; SHA mismatch is a stop.
3. Verify BOTH real installer lanes of [04](04-installer-gates.md) used **the exact same Studio candidate commit and exactly these released upstream artifact hashes**. Check native install/smoke/signatures, artifact SHA-256 and macOS/Windows platform evidence. If source/versions changed since either build, regenerate **both** installers rather than mixing release candidates.

## Execute the one final BioCall Studio base-suite run

Run, on that exact candidate in the isolated environment:

```bash
python scripts/run_tests.py background -q
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
python scripts/audit_test_ids.py
python scripts/verify_handoff.py
python scripts/check_fixtures.py
```

The `background` runner selects ordinary unit + integration tests with offscreen Qt and excludes `soak` / `native_cocoa`. It is **the single complete Studio source-suite gate** in this series; earlier Studio specs run only relevant focused checks. Keep invocations bounded and report exact test counts, skips, failures, duration and environment. Do **not** run `-m soak`, `tests/integration/test_long_running_runs.py`, 600-second durability checks, 50k reruns, large real-data performance qualification, compulsory new native screenshots, or physical audio-device proof. Do not invent passing results for an unavailable VM; arrange the same base-suite job in suitable CI and cite its actual result.

Also inspect Studio's built source/wheel metadata, README brand/logo image paths and correct MIT/GPL/Qt notices; confirm no executable-level regression from the upstream adapter. The native installer **smoke**, rather than an additional full native GUI suite, is the OS-specific check.

## Promotion decision after evidence

Only if **all** of the following are verified: final Studio suite green on **released** upstream artifacts, CI/format/audits green, both installers' genuine native minimal smoke green from exactly that candidate, compatible distribution licenses/notices, and explicit owner approval:

1. Confirm a clean reviewed Studio `main` release commit; set/verify version `0.1.0a1` (or separately approved final value), then create an immutable **annotated** `v0.1.0a1` tag **at the tested commit**.
2. Publish GitHub Release with the **exact** tested macOS `.dmg` and Windows installer binary, SHA-256 values, upstream tag/SHA and wheel checksums, supported OS notes and friendly screenshots already tracked in the README. Include source distribution/licenses as required. No PyPI assumptions or automatic promotion.
3. Verify public links, tag→commit, download hashes, installer release notes and no stale “Review placeholder” claim. Never move a release tag or quietly swap an installer. Block/publicly defer rather than label missing evidence complete.

## Execution environment / exit

**GitHub API:** inspect releases/tags/PRs, verify SHAs, source docs and release metadata. **ChatGPT VM or suitable CI runner:** fresh install from published release wheels, the **only** complete Studio base suite, build/import audits, hashes. **Native macOS/Windows:** no new work *unless* installer 04 evidence is missing or invalid; then return to the owning lane. This final spec does not require a new macOS capture, playback test, long-running suite or benchmark.

**Definition of done:** BioCall Studio's own ordinary unit/integration test suite has *actually passed* against the **latest approved released** alp-ui and toolbox, installers use those exact pinned artifacts, and only then is the Studio tag/release published. A failed/blocked gate means no tag or release, not an invented result.
