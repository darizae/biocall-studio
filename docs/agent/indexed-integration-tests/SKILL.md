---
name: indexed-integration-tests
description: Plan, implement, review and audit real Trainer integration behaviors using stable IT-* cases and named TD-* equivalence classes.
argument-hint: "<plan-path> <test-data-guide-path> <scope>"
disable-model-invocation: true
---

# Indexed Integration Tests — Trainer

Default args: `docs/INTEGRATION_TEST_BEHAVIORS.md docs/INTEGRATION_TEST_DATA.md "IT-ID or spec scope"`. If a required parameter is missing in direct invocation, ask for it rather than inferring broad scope.

## Preflight

1. Read `AGENTS.md`, `docs/UNIT_TESTING.md` and relevant domain rules to choose the **real owner**. Put pure filenames, bounds, negative math, Split grouping, configuration and metrics in `UT-*`, not `IT-*`.
2. Read the selected `IT-*` index rows, their named `TD-*` equivalence classes, active spec, and `docs/INTEGRATION_TESTING.md`.
3. Search for existing test functions with exact IDs and examine assertions. Classify each selected row: **covered (passing real test)**, **uncovered**, or **blocked by missing implementation/dependency/data**. A docstring/static match alone is not coverage.
4. Inspect the minimum production path and matching test precedent; avoid unrelated broad refactors or speculative harnesses. Determine per case: owning seam, minimal differentiating fixtures, expected persisted/public effects, exact unchanged inputs, failure and cleanup.

## Implementation

- Use one temporary Collection root and isolated Application Settings per test. Real generated WAV bytes, deterministic distinguishable signals/stems/times and local test-owned `Collection/.alpaca/` are default. Reuse existing helpers first; do not create a factory abstraction for a single case.
- Qt needs genuine PySide6 controller/model and `pytest-qt`; Run needs **real QProcess**; scientific Train needs real CPU CNN/RF and published Model reload. No mocked Run artifacts for real integration claims, no HPC requests from tests.
- Repeat each intended exact ID in the **test function docstring**, e.g. `"""Cases: IT-COL-001, IT-COL-003."""`. Group IDs when setup/assertions genuinely overlap; split contrasting cancellation/error conditions as needed. Do not treat IDs in helpers or comments as coverage.
- Assert final public/persisted state, correct path/lineage, byte-identical input WAVs where required, no publish on failure, no overwrites, and correct conflict/refresh semantics. Signals/status bars alone do not prove persistence or verified Model outputs. Observe `run_state.json` **and** Artifact manifest/checksums for completed Run.
- Wait for observable state with finite timeout; avoid arbitrary sleeps; clean up Worker processes, Qt windows and temporary folders. Index list/table may require bounded paging evidence without full-array reads.
- New insufficient fixture? Recreate/modify deterministic generator, or follow `docs/INTEGRATION_TEST_DATA.md` for permissioned small HPC-derived, anonymized Git LFS fixture; update spec, `TD-*` register and impacted behavior plan in same PR. Stop/mark blocked when source rights/access/objects are unavailable; never guess or weaken checks.

## Verification and report

Run targeted tests on the actual owning platform, regress earlier cases, then `python scripts/audit_test_ids.py`. Record commands, OS, test/fixture source, `covered / planned / blocked / deferred-native` per selected ID, any untested assertions and manual packaged/native evidence. Browser prototype simulation, `QT_QPA_PLATFORM=offscreen`, passing unit tests and macOS portability checks never count as Windows-native or packaged QProcess coverage.

This skill does not introduce application network/backend services, a separate test registry, or arbitrary new user workflows.
