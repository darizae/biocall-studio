# 05 — Local final Studio base suite BEFORE the native installer lanes

**Execution position: prompt 11**, immediately after the shared installer-source PR from [04](04-installer-gates.md) is reviewed and merged into BioCall Studio `main`. [Spec 06](06-release-and-post-release-cleanup.md) is now the **last release/publishing spec** and owns post-release Markdown retirement. No fresh full test suite is requested after the installer lanes unless source or approved dependencies change.

## Who executes what

**ChatGPT web: setup/coordination only.** It may inspect tags/hashes, write and submit the Windows Actions workflow PR, and prepare commands or analyze logs. **The owner's Mac: required executor of this full unit/integration suite.** The ChatGPT cloud VM, a GitHub Actions Linux job, or a Windows runner does not satisfy this explicitly local gate. If the agent cannot access the Mac, provide the exact local steps and leave the test **PENDING**.

**Before launching locally**, use **prompt 10B** to either merge the Windows GitHub Actions workflow into `main` or choose the interactive remote Windows VM path without a repository workflow change. A later workflow source commit invalidates the frozen SHA and requires repeating this local test.

## Freeze and verify the exact source/dependencies

1. Verify the already published [alp-ui](https://github.com/darizae/alp-ui/releases) and [bioacoustics-dl-toolbox](https://github.com/darizae/bioacoustics-dl-toolbox/releases) release wheel assets. The currently observed versions are `alp-ui v0.1.0a1` and `toolbox v0.3.0`, but inspect the live approved version/tag target commit, URL and wheel SHA-256 at execution. Verify the Studio `pyproject.toml` dependency constraints and `[tool.biocall-studio.science]` provenance, not just version labels.
2. Confirm specs 01–03 and spec 04's shared installer-source PR are **merged** into Studio `main`. **Before freezing:** decide how the Windows lane will run. If using the recommended GitHub-hosted `windows-2025` approach, ensure its `workflow_dispatch` workflow/source configuration is committed to reviewed Studio `main` **now**, even if the job will execute after this local test. The existing `.github/workflows/installer-source.yml` is Linux-only source preflight, not a native Windows build. A remote Windows x64 cloud VM can alternatively execute the existing PowerShell scripts without a new CI workflow. Do not commit extra workflow/packaging source after the local gate without repeating it. Then set **`STUDIO_RELEASE_SHA = main HEAD`** with version metadata, release notes, icons, legal notices, worker entrypoints and **both** platform packaging definitions already committed. Do not test a branch PR head and later tag a different SHA.
3. On the owner's **local Mac**, check out exactly `STUDIO_RELEASE_SHA` in a clean local Git worktree. Use an isolated local Python 3.12 virtual environment and hash-verified published upstream wheel artifacts, *not editable sibling checkouts*. Record Git SHA, clean status, Python/Qt, `pip check`, distribution versions, `module.__file__` import origins and wheel hashes. An agent without local machine access must provide an accurate local execution handoff and mark this gate **PENDING**, not claim that its own VM or remote CI passed.

## One complete local BioCall Studio ordinary test suite

With the local isolated virtual environment installed (adapt the path to the actual local interpreter), run:

```bash
.venv-release-check/bin/python -m pip check
.venv-release-check/bin/python scripts/run_tests.py background -q
.venv-release-check/bin/python -m ruff check src tests scripts
.venv-release-check/bin/python -m ruff format --check src tests scripts
.venv-release-check/bin/python scripts/audit_test_ids.py
.venv-release-check/bin/python scripts/verify_handoff.py
.venv-release-check/bin/python scripts/check_fixtures.py
.venv-release-check/bin/python scripts/audit_docs.py
```

The `background` runner is the ordinary unit/integration suite with offscreen Qt; do **not** run soak, native Cocoa campaign, ≥600-second tests, 50k, new large real-data performance qualification, mandatory physical playback or new screenshots. Report the actual passed/failed/skipped tests, commands, timing and any pre-existing formatting drift separately—do not silently call a failing check green. Stop on substantive failures.

Save the local command outputs, source and published upstream artifact hashes, import origins and environment provenance as immutable release-candidate evidence **outside** the tracked source tree (CI/PR notes or a checksumed external report). Do not create a source commit just to record results; a commit would invalidate the frozen SHA.

## Handoff BEFORE the installer builds

- Only after this **actual local** suite and audits are verified should the two **native** [spec 04](04-installer-gates.md) lanes build in parallel from the **identical** `STUDIO_RELEASE_SHA` and upstream wheel hashes. An already built but unverified installer is not automatically qualified.
- The local suite does **not** require completed native installers as a prerequisite. Conversely, no claim of released BioCall Studio, no Studio tag, and no stale-spec deletion follows from local tests alone.
- If **either** native lane discovers a source/dependency/packaging defect, create a focused reviewed fix PR into `main`, choose a **new** `STUDIO_RELEASE_SHA`, **rerun this local Studio base suite**, then rebuild/verify **both** native installers. If an installer is only rebuilt for environmental reasons with no source/dependency change, keep the same local test evidence and SHA.
- Once the native macOS and Windows checks are genuinely complete, execute **[06 — publish and retire verified specs](06-release-and-post-release-cleanup.md)**. That spec alone creates Studio's tag/release and initiates the three docs-only cleanup PRs.

**Execution:** local Mac required for the full Studio suite; GitHub API/VM can independently verify metadata/links and collect results but cannot substitute for the local run. No new code branch or release tag is required for passing this qualification.
