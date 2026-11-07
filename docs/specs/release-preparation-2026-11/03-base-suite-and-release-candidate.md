# 03 — Base validation and a reproducible BioCall Studio release candidate

After upstream toolbox (and any justified `alp-ui`) changes have tested/released, update the package's `pyproject.toml` version pins **and** `[tool.biocall-studio.science]` exact revision metadata together. Never guess upstream SHAs or reference an unmerged spec branch.

**Proposed next version:** `0.1.0a1` / future tag `v0.1.0a1` if this remains a prerelease. If owner instead chooses a stable tag, use a separate recorded version decision with actual installer proof. Existing `0.1.0a0` has **no GitHub tag or release** as of baseline inspection. The tag is **not** to be created during planning.

## Test budget

- `python -m pytest -q tests/unit` + `python scripts/verify_handoff.py` + `python scripts/check_fixtures.py` + `python scripts/audit_test_ids.py` (existing CI base).
- `python scripts/run_tests.py background` for the ordinary non-soak project suite **if available inside a bounded VM runner**; exclude `soak`, `native_cocoa` and `packaged` for source-only validation; if the full ordinary integration suite is impractical in the VM, report the exact blocked subset and rely on actionable CI rather than unbounded local work.
- `python -m ruff check src tests scripts` and `python -m ruff format --check src tests scripts`; inspect build metadata, wheel contents/import origins, legal notices and referenced assets.
- **No** `-m soak`, 600-second runs, 50k candidate tests, large real-data qualification, new native screenshot capture or mandatory physical playback.

Use the small tracked deterministic fixture policy and existing Release real-data imagery **for marketing**, not as compulsory test input. Fail rather than silently skip an affected consumer regression. Record exact command/results in PR.

## Artifact plan

Build reproducible Python source/wheel packages in the VM if possible. Check worker `--worker` dispatch and package resource inclusion in standard tests. Prepare draft release notes, a release manifest template with `main` SHA, toolbox/alp-ui wheel hashes, PySide6 and license compliance, known supported targets and checksums. A source wheel is **not** the desktop installer.

**GitHub API:** audit/commit version-pins, notes, release workflow manifests, PRs and CI. **VM:** base suites, static/doc/link audits, wheel builds. **Local/native:** only the installer-specific gates in spec 04.

**Done:** all source-level tests actually reported, truthful release candidate provenance, dependency bump safe, existing real screenshot links work, and nothing tagged/publicly released before native installer acceptance.
