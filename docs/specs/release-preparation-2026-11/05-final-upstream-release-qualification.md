# 05 — FINAL: BioCall Studio's one full base suite and public release gate

**Last spec across all three repositories.** Start only after both library releases, Studio specs 01–03 merged into `main`, and Studio spec 04's packaging-source PR merged and its **two native installer lanes verified against the same frozen SHA**. This spec is the **only full BioCall Studio source-suite gate**. Follow [VERSION_CONTROL.md](VERSION_CONTROL.md) for the exact branch/tag policy; do not create a new source branch merely to write passing evidence.

## Verify immutable inputs first

1. Re-query **real latest approved compatible GitHub Releases** for [alp-ui](https://github.com/darizae/alp-ui) and [bioacoustics-dl-toolbox](https://github.com/darizae/bioacoustics-dl-toolbox). Expected candidate tags are `v0.1.0a1` and `v0.3.0` **if actually published**. Verify each immutable annotated tag's **target commit SHA** (not just the tag object ID), wheel/sdist URL, actual SHA-256, version and license. Use the latest *approved released* versions compatible with Studio; a newer incompatible or unreviewed release is not silently substituted.
2. Install the **published wheel artifacts** and required `[rf]` dependencies into a fresh supported Python environment (matching the frozen Studio candidate where practicable). Toolbox uses GitHub Release assets rather than assumed PyPI. Record both distributions' `importlib.metadata.version(...)`, `module.__file__`, tag target SHAs, resolved dependency versions and wheel checksums. Neither an editable sibling checkout nor a mutable `main` import qualifies.
3. Check `STUDIO_RELEASE_SHA` from [04](04-installer-gates.md) equals a **real reviewed commit on BioCall Studio `main`** that already contains both the proposed Studio version `0.1.0a1` and release notes. Match it to Studio's `pyproject.toml` dependency pins and `[tool.biocall-studio.science]` upstream SHA fields. Both genuine macOS and Windows installer build receipts must name **this same exact SHA**, identical upstream wheel hashes and platform test/signed artifacts. Rebuild both if source/approved upstream versions/lock changed: no mixing releases from distinct SHAs.

## The single complete BioCall Studio ordinary base suite

At **exactly `STUDIO_RELEASE_SHA`**, in that released-wheel environment, run:

```bash
python scripts/run_tests.py background -q
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
python scripts/audit_test_ids.py
python scripts/verify_handoff.py
python scripts/check_fixtures.py
```

The background mode is the existing ordinary unit + integration suite using offscreen Qt while excluding `soak` and `native_cocoa`; earlier Studio specs run **only focused** regressions. Record exact runner/Python/Qt versions, tests passed/skipped/failed and durations; if unable to run in the ChatGPT VM, use the actual project CI runner and report its verified result, never assume passing status. Do **not** run `-m soak`, ≥600-second tests, 50k reruns, huge real-data performance qualification, new obligatory macOS screenshot capture, or physical audio playback proof. Native installed-app evidence is the **minimal** smoke from spec 04, not another exhaustive native GUI/science suite.

Audit the actual wheel/package metadata, worker/public entrypoints, brand/README image links and distribution legal notices. A test pass on the wrong library revision does **not** satisfy this spec.

## Tag/release — same tested `main` commit, no post-test changes

Only after **all** gates are truly green—final Studio base suite against released wheels, lint/audits, both actual native installers/signatures/worker smokes, correct GPL/Qt/application redistribution rights, complete immutable hashes, and explicit owner promotion approval—create the annotated **`v0.1.0a1`** tag **pointing to `STUDIO_RELEASE_SHA` on `main`**. **Do not** bump the version, merge another PR or change license/README/manifest source after tests/builds. Publish a GitHub Release attaching exactly the tested macOS `.dmg` and Windows installer with real SHA-256 digests, upstream versions/tag commit SHAs/wheel hashes, human release notes and supported-platform truth. Do not rewrite a tag or silently replace an installer.

If anything must change after freeze, create a separate reviewed fix PR, **merge it into `main`**, choose a **new** `STUDIO_RELEASE_SHA`, rebuild and re-qualify **both** native installers and rerun this entire base suite before tagging. Store machine-specific validation evidence in CI/PR/release artifacts without creating a new source commit; if a tracked manifest must change, it triggers the same new-SHA cycle. Missing native environment, sign-off or capability is a **blocked release**, not a reason to tag incomplete code.

## Final recorded handoff

Provide the genuine three repository `main`/tag target SHAs, exact GitHub Release URLs, published library-wheel and Studio-installer hashes, Studio `pyproject.toml`/science pins, final test command outputs, Mac/Windows native receipts, licenses and any outstanding limitations. Check each tag commit is reachable from the respective repository's `main`. After the last action, no unmerged implementation source is required for the advertised release. **Studio 05 must remain the final execution step.**
