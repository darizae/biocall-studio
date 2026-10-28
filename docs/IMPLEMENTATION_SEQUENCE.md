# BioCall Studio — implementation sequence

**Approved baseline:** ST-01 interactive prototype is the owner-approved design reference; browser automation remained unexecuted. ST-02 native Studio shell is **owner-approved as a stage** (not a claim that unavailable native/platform tests passed). Preserve Train as implemented. Next stage is **ST-03**. The ST-03–ST-11 specifications below exist **now**, but their scientific implementation details are finalized only from accepted predecessor contracts and actual upstream source evidence. Work on exactly **one** active stage.

**Branch policy:** inspect Git first; establish local `detect` from `main` only if needed and approved. Each `detect-stNN-purpose` branch starts from the **reviewed current `detect`**, not another unreviewed stage branch. Review, commit and locally integrate the accepted stage back into `detect`; never merge automatically. After **ST-11** qualification and explicit owner approval, locally merge reviewed `detect` into `main`. No pushing, tagging or release publication in this plan. Upstream `bioacoustics-dl-toolbox`/`alp-ui` changes use their own branches, tests, commits and owner-approved local integration in those repos, with downstream revalidation.

| Order | Active-stage specification and required acceptance handoff |
|---|---|
| [ST-01](specs/ST-01-prototype.md) — approved | Approved HTML design reference; no scientific/browser-interaction qualification claim. |
| [ST-02](specs/ST-02-native-shell.md) — approved | Native Studio/Train switching; review existing evidence/actual branch, do not redo. |
| **[ST-03](specs/ST-03-detect-workspace.md)** | Detect Collection IDs, app-owned metadata outside source, safe Relink and versioned root binding → ST-04. |
| **[ST-04](specs/ST-04-wav-discovery.md)** | Read-only bounded discovery, explicit inclusion, validated/stale `InventorySnapshot` → ST-05/07. |
| **[ST-05](specs/ST-05-model-intake.md)** | Trusted Train CNN/RF Model intake, source-inspected versions and `ModelSnapshot` → ST-06/07/09. No scoring. |
| **[ST-06](specs/ST-06-detect-workers.md)** | Detect Run/QProcess lifecycle, private staging/receipts, cancellability, privacy-safe logs → ST-07. |
| **[ST-07](specs/ST-07-cnn-detection.md)** | Numerically verified CNN candidates and immutable source-time `DetectionResult` → ST-08/09/10. |
| **[ST-08](specs/ST-08-results-ux.md)** | Real native recording/candidate Results exploration and independent selection → ST-09/10. |
| **[ST-09](specs/ST-09-rf-refinement.md)** | Numerically verified optional RF per-candidate assessment and immutable linked `DerivedResult` → ST-10. |
| **[ST-10](specs/ST-10-corpus-export.md)** | Frozen selection → verified independent WAV/snippet + Raven TSV export, explicit destination → ST-11. |
| **[ST-11](specs/ST-11-unified-qualification.md)** | **Only whole-Studio E2E** + combined safe quit/native parity; revise *existing* macOS/Windows release specs in place. No installer claim. |

**Every implementation stage:** tests first in owned `UT-DET-*`/`IT-DET-*` (and ST-11 `UT-STU-*`/`IT-STU-*`) rows of the existing [unit](UNIT_TESTING.md) and [integration](INTEGRATION_TEST_BEHAVIORS.md) indexes. Entries are **planned**, not passing. Use the fewest discriminating [TD data classes](INTEGRATION_TEST_DATA.md). Verify unit rules at pure seams; real WAV, actual QProcess, real Qt and scientifically accurate CPU Model cases at their correct owner stage; meaningful negative/cancellation/reopen tests and unchanged source bytes. Run owning targeted + affected Train regressions continuously, and **all feasible ordinary unit/integration suites plus ruff and test-ID audit before each implementation commit**. Report skipped/blocked/native-only distinctly; ≥600-second soak is separately initiated. **Do not run or claim full Train→Detect→RF→Export integration before ST-11.**

**UI policy:** accepted [ST-01 prototype route/state matrix](design/UX_PARITY_MATRIX.md) + native Train + public `alp-ui` are the authority. Match state, hierarchy, action order, keyboard focus, normal/compact layouts, readable labels, meaningful keyboard-accessible `HelpHint`/tooltip and error recovery. No arbitrary micro-captions, duplicate hints, dead controls, simulated results or developer-facing text. Native screenshots and actual interactions are required in each owning UI stage. Prototype browser-automation gap does not block native stage work or become a claimed test pass.

**Release boundary:** [`06-macos-release-and-installer.md`](specs/06-macos-release-and-installer.md), [`07-windows-release-and-installer.md`](specs/07-windows-release-and-installer.md) and [release process](RELEASE_PROCESS.md) remain **unexecuted** until revised at ST-11; installed app, signing and promotion need a separate explicit stage.
