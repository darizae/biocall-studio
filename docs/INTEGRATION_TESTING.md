# Integration testing strategy — native Trainer

**Mandatory UI acceptance:** [Prototype fidelity gate](design/PROTOTYPE_ACCEPTANCE.md) applies to every spec that changes visible UI (including packaged installers). A missing screen/state, rearranged primary action, wrong navigation, unlabeled visual deviation or absent native screenshot evidence blocks that spec; using `alp-ui` alone is not proof of parity. Read only the active spec’s screen rows.

## Purpose and evidence levels

Each vertical must prove its **real owning boundary** and observable published outcome, not merely that pure logic or a mock GUI worked. Index integration cases in [`INTEGRATION_TEST_BEHAVIORS.md`](INTEGRATION_TEST_BEHAVIORS.md); choose equivalence classes in [`INTEGRATION_TEST_DATA.md`](INTEGRATION_TEST_DATA.md). The test-level choice precedes writing code: a complete answer from in-memory values belongs in [`UNIT_TESTING.md`](UNIT_TESTING.md).

| Level | Owner and actual boundary | Assertions that matter |
|---|---|---|
| `unit` | pure domain / computation decision, no Qt/filesystem requirement | exact grammar, time/interval/exclusion/split semantics, seed determinism |
| `workflow IT` | real filesystem WAVs, native loader, staging/persistence, Dataset/Model artifacts | exact output bytes/schema, provenance, unchanged inputs, cancel/failure and reopen |
| `desktop IT` | actual PySide6 controller / Qt model/file picker interaction and background scan | responsive UI/progress, file-level errors, bounded paging, persistent correct navigation |
| `process IT` | actual QProcess child Worker + Run State | start/end/cancel/orphan, one active Run, staged publication, reservations and logs |
| `packaged IT` | real installed app + built worker on native OS | resources, local library, environment-aware launch, persistence and scientific workflow |

The browser prototype's simulated Build/Training is a **design smoke only**, never workflow, process or scientific integration evidence.

## Harness / isolation

Implement a reusable `pytest`/`pytest-qt` harness with **per-test temporary Collection roots** and machine-local Application Settings override. Generate valid little-endian PCM WAV data using a deterministic fixture factory; construct positives with recognizably different source-time segments. Generate invalid WAVs, missing/changed files and symlink escapes in the same temp root; never scan private home folders. Use `QApplication` only in desktop tests, with `qtbot.waitUntil` or bounded signals rather than arbitrary `sleep`. Process cases launch actual Worker from the test's installed environment, pass isolated settings and own input roots, and cleanly terminate children.

Test expected **negative side effects** as explicitly as successful output: `recordings/` and `positives/` bytes unchanged; no `.alpaca/` cache considered valid after incomplete scan; no Dataset/Model published after failure; no duplicate directories after replay/collision; Model remains when Dataset is deleted. Where assertions involve time or progress, wait for observable state transitions with finite deadlines, never assume exact thread scheduling.

Use an actual Dataset containing reproducible `target` and `noise` with train/val groups for Training integration. One real CPU CNN and one real RF must run from the **same published Dataset**; report training shape/metrics/file integrity, not strong accuracy claims from toy audio. Do not fake a Model to satisfy a Training integration claim. Check read budgets/partition ceilings and at least one generated large-index fixture to prove paging without shipping huge binaries.

## Index and coverage protocol

1. Select a named `IT-*` case and its `TD-*` dimensions. Verify there is no cheaper pure owner that should be `UT-*` instead.
2. Search for the exact ID in existing `tests/` and inspect its assertions; a docstring alone does not imply coverage.
3. Implement through public workflow/controller/worker seam, verify all listed outputs and failure/non-mutation conditions. Repeat exact `IT-*` ID in the **test function docstring**.
4. Run the owning suite on a real suitable platform; record commands and results. Only then mark case covered in an evidence/PR report (not by annotating index status prematurely).
5. When a fixture is insufficient, revise it and its register/spec data assumptions in the same PR; do not weaken assertions. See the repo-local [`indexed-integration-tests` skill](agent/indexed-integration-tests/SKILL.md).

Run `python scripts/audit_test_ids.py` to catch unknown IDs and find referenced cases. The script is **static**, not a pass/coverage detector. It does not substitute for pytest and manual ID-to-assertion audit. A test function can cover multiple compatible IDs, or one ID may need multiple test cases for variants.

## macOS/CI/Windows division

CI starts with Qt-free unit and static checks. Run workflow, GUI and process suites on **native macOS** with explicit dependencies/fixtures. `QT_QPA_PLATFORM=offscreen` may support fast model tests but cannot qualify dialogs or a packaged app. Native macOS **installed DMG** tests and native Windows **installed EXE** tests are separate release gates; `IT-MAC-*` must verify Gatekeeper/signing/Worker and `IT-WIN-*` the real Windows installer. Native Windows tests remain release gates and run on actual Windows: path case behavior, reserved names/reparse points, write locks, QProcess/`alp-ui`/packaging, and a real Dataset + both Model families. No emulation or macOS-only portability test may claim `IT-WIN-*` passed. HPC and network are never used as ordinary test resources.
