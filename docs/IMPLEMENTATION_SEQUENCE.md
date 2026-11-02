# BioCall Studio — implementation sequence

**Current source baseline:** `main` contains the merged ST-01–ST-11 and REV-01–REV-04 implementation history. ST-01 remains the owner-approved design reference and its browser automation remained unexecuted. The merge is not installed macOS/Windows, signing, notarization or release evidence. No next implementation stage is declared; new stage work requires an explicit owner scope and still follows one owning specification at a time.

**Branch policy:** inspect Git first. Historical stage branches started from the reviewed `detect` baseline and were merged through ST-11 into `main`. New explicitly scoped stage work must branch from its reviewed baseline; cross-cutting maintenance uses a focused branch from current `main`. Never merge automatically. No pushing, tagging or release publication is authorized. Upstream `bioacoustics-dl-toolbox`/`alp-ui` changes use their own branches, tests, commits and owner-approved local integration in those repos, with downstream revalidation.

| Order | Active-stage specification and required acceptance handoff |
|---|---|
| [ST-01](specs/ST-01-prototype.md) — approved | Approved HTML design reference; no scientific/browser-interaction qualification claim. |
| [ST-02](specs/ST-02-native-shell.md) — approved | Native Studio/Train switching; review existing evidence/actual branch, do not redo. |
| [ST-03](specs/ST-03-detect-workspace.md) — merged baseline | Detect Collection IDs, app-owned metadata outside source, safe Relink and versioned root binding → ST-04. |
| [ST-04](specs/ST-04-wav-discovery.md) — merged baseline | Read-only bounded discovery, explicit inclusion, validated/stale `InventorySnapshot` → ST-05/07. |
| [ST-05](specs/ST-05-model-intake.md) — merged baseline | Trusted Train CNN/RF Model intake, source-inspected versions and `ModelSnapshot` → ST-06/07/09. No scoring. |
| [ST-06](specs/ST-06-detect-workers.md) — merged baseline | Detect Run/QProcess lifecycle, private staging/receipts, cancellability, privacy-safe logs → ST-07. |
| [ST-07](specs/ST-07-cnn-detection.md) — merged baseline | Numerically verified CNN candidates and immutable source-time `DetectionResult` → ST-08/09/10. |
| [ST-08](specs/ST-08-results-ux.md) — merged baseline | Real native recording/candidate Results exploration and independent selection → ST-09/10. |
| [ST-09](specs/ST-09-rf-refinement.md) — merged baseline | Numerically verified optional RF per-candidate assessment and immutable linked `DerivedResult` → ST-10. |
| [ST-10](specs/ST-10-corpus-export.md) — merged baseline | Frozen selection → verified independent WAV/snippet + Raven TSV export, explicit destination → REV-01. |
| [REV-01](specs/manual_revision_specs/REV-01-project-consolidation.md) — merged baseline | One `biocall-studio` distribution/package/entry, workflow-owned module tree and verified concise source instructions → REV-02. |
| [REV-02](specs/manual_revision_specs/REV-02-detect-guided-workflow.md) — merged baseline | Guided Setup → Recordings → Run → Results → Export flow, atomic bulk inclusion, semantic Model status and reachable export planning → REV-03. |
| [REV-03](specs/manual_revision_specs/REV-03-interface-language-and-theme.md) — merged baseline | Whole-app copy/tooltip inventory and permanently light native UI → ST-11. |
| [REV-04](specs/manual_revision_specs/REV-04-Detect-Navigation-and-History.md) — merged baseline | Persistent Detect navigation, independent Run selection, and verified completed-export history → ST-11. |
| [ST-11](specs/ST-11-unified-qualification.md) — merged source qualification | **Only whole-Studio E2E** + combined safe quit/native parity; revised existing macOS/Windows release specs in place. No installer claim. |

**Proposed separately (not implemented):** [REV-05 shared output-size preflight](specs/manual_revision_specs/REV-05-output-size-preflight.md). It is a scoped post-qualification Train/Detect feature with a future Review adapter, not a new full-Studio qualification stage. The owner must authorize the branch and approve its UI copy before implementation.

**Every implementation stage/revision:** tests first in its owned indexed `UT-*`/`IT-*` rows of the existing [unit](UNIT_TESTING.md) and [integration](INTEGRATION_TEST_BEHAVIORS.md) indexes. Entries are contracts, not passing evidence. Use the fewest discriminating [TD data classes](INTEGRATION_TEST_DATA.md). Verify unit rules at pure seams; real WAV, actual QProcess, real Qt and scientifically accurate CPU Model cases at their correct owner stage; meaningful negative/cancellation/reopen tests and unchanged source bytes. Run owning targeted + affected regressions continuously, and **all feasible ordinary unit/integration suites plus ruff and test-ID audit before each implementation commit**. Report skipped/blocked/native-only distinctly; ≥600-second soak is separately initiated. The complete Train→Detect→RF→Export integration scenario remains owned only by ST-11.

**UI policy:** accepted [ST-01 prototype route/state matrix](design/UX_PARITY_MATRIX.md) + native Train + public `alp-ui` are the authority. Match state, hierarchy, action order, keyboard focus, normal/compact layouts, readable labels, meaningful keyboard-accessible `HelpHint`/tooltip and error recovery. No arbitrary micro-captions, duplicate hints, dead controls, simulated results or developer-facing text. Native screenshots and actual interactions are required in each owning UI stage. Prototype browser-automation gap does not block native stage work or become a claimed test pass.

**Release boundary:** [`06-macos-release-and-installer.md`](specs/06-macos-release-and-installer.md), [`07-windows-release-and-installer.md`](specs/07-windows-release-and-installer.md) and [release process](RELEASE_PROCESS.md) remain **unexecuted** until revised at ST-11; installed app, signing and promotion need a separate explicit stage.
