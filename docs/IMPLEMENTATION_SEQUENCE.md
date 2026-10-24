# Implementation sequence — native Trainer

**Mandatory UI acceptance:** [Prototype fidelity gate](design/PROTOTYPE_ACCEPTANCE.md) applies to every spec that changes visible UI (including packaged installers). A missing screen/state, rearranged primary action, wrong navigation, unlabeled visual deviation or absent native screenshot evidence blocks that spec; using `alp-ui` alone is not proof of parity. Read only the active spec’s screen rows.

Implement **one numbered spec per branch**. **Current stage: finish [Spec 01 closeout](specs/SPEC_01_CLOSEOUT.md) and verify native UX, README and Git evidence before [02](specs/02-collection-scan-and-metadata.md).** New checkouts without any prior implementation start with [01](specs/01-shell-and-test-foundation.md). Branch from the merged predecessor; code + tests + fixture/documentation evidence belong in that branch. `AGENTS.md` → [`docs/agent/ROUTING.md`](agent/ROUTING.md) chooses the minimal reading set; avoid loading the complete documentation tree.

| Phase | Product exit and ownership | Tests |
|---|---|---|
| [01 — UI shell](specs/01-shell-and-test-foundation.md) | Visually faithful native Select Collection + Wiki, current `alp-ui` FolderPicker/HelpHint, named/keyboard accessible navigation, baseline scaffold test seams | UT-PATH, IT-UI-001...004 |
| [02 — Scan](specs/02-collection-scan-and-metadata.md) | Cancellable bounded WAV/positive validation, accurate Collection and stored rebuildable metadata; evaluated real-WAV sample; first permitted HPC exemplar *only if approved/needed* | UT-COL, IT-COL incl. 008, TD-WAV/COL/CACHE |
| [03 — Dataset](specs/03-dataset-build.md) | Protected noise mining, source-group split, source-time provenance, immutable materialized Dataset | UT-DB, IT-DB incl. 005, TD-MINE/SPLIT |
| [04 — Worker](specs/04-runs-and-worker.md) | Real QProcess Runs with one active, cancel/recovery and artifact publication | UT-RUN, IT-RUN incl. 005 |
| [05 — Training / plots](specs/05-cnn-and-rf-training.md) | Real CNN + RF from same Dataset, measured metrics, line/bar native `Plot`, detailed Model UI | UT-TRAIN, IT-TRAIN-001...007 |
| [06 — Mac release](specs/06-macos-release-and-installer.md) | Controlled candidate pipeline, installed-app native end-to-end and signed/notarized installable `.dmg` | IT-E2E, IT-MAC-001...004 |
| [07 — Windows release](specs/07-windows-release-and-installer.md) | Actual native Windows end-to-end, signed versioned `.exe` installer and qualification | IT-WIN-001...005 |

## Definition of done for every vertical

1. Read only the active spec and references routed from `docs/agent/ROUTING.md`; inspect current implementation, sibling API and relevant prototype screen; identify debt/blocked dependencies.
2. Write/exercise meaningful **failing** `UT-*` / native `IT-*` cases first; then implement and run focused green suite (red → green → refactor). Do not fake scientific artifacts or mark test coverage from static docstrings.
3. Test positive and negative side effects: original inputs unmodified, no partial cache/publication, no silent ID overwrite, actual persisted state, accessible messages. Use generated real WAV Collections first; use `tests/data/example_collection` only if the fixture is present and LFS materialized in this checkout. Its omission from a transfer ZIP is intentional. HPC is never accessed in tests.
4. Update targeted docs, cases, fixture register when behavior evolves. Compare implemented Qt screenshots to prototype and `alp-ui` Showcase for visible UI changes; record intended differences.
5. Report exact run commands/results and native blockers. For visible UI, save native macOS screenshots and compare with both prototype and `alp-ui` Showcase; README must show truthful current native app screenshots. Finish with a verified Git branch/commit SHA and clean `git status` per [Git delivery](agent/GIT_DELIVERY.md). Do not automatically proceed to next phase; review and merge.

Spec 03 can exercise a Qt-free synchronous scientific seam under test, but production Dataset Build must use the single Run contract implemented in spec 04. The scientific `alpaca-pipelines` source is a **sibling reference**, not an unseen runtime promise. The Mac public installer is **not** an outcome of the handoff ZIP; it is delivered only after spec 06 passes. Windows remains a separate native release gate, not implied by Mac success.
