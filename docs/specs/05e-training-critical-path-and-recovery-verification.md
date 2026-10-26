# 05e — Critical training-path and failure-recovery verification

**Status: verification hardening complete; owner review pending.** This remains test/evidence work,
not a new training feature. It ran **after 05d** and **before 05f**. Previous 05c acceptance
evidence remains historical. The new assertions passed against the actual checkout, so no runtime
repair was made.

**Read only where relevant:** `IT-TRAIN-003`/`004`/`009`/`012`/`014` and `IT-RUN-002`/`003`/`004` in [integration behaviors](../INTEGRATION_TEST_BEHAVIORS.md); `TD-TRAIN`, `TD-FAIL`, `TD-RUN`, `TD-PRESET` in [fixtures](../INTEGRATION_TEST_DATA.md). Start with `tests/integration/test_training_ui.py`, `test_cnn_training.py`, `test_rf_training.py`, and `test_run.py`; inspect their owning Controller/Worker/Model seams only as needed. Consult the [source map](../agent/SOURCE_MAP.md) if an actual dependency boundary is implicated, and the [upstream workflow](../agent/UPSTREAM_TOOLBOX_WORKFLOW.md) **only** for a proven upstream defect. Follow [Git delivery](../agent/GIT_DELIVERY.md) at handoff.

## Coverage to close, in order

1. **Real native Start → Worker → Model.** Current native Start testing substitutes `controller.start_training`, while real family tests call the Controller directly. Extend `IT-TRAIN-012`/`014` with a Qt-driven Start action (loaded preset/nondefault config as relevant) that launches a **real QProcess Worker** and publishes a validated CNN Model and an RF Model. Keep dialogs test-controlled without substituting the scientific or supervision path. Assert resolved configuration equality at native form → frozen Run → executor → Model, actual terminal status, saved metrics and unchanged input WAVs. Use the same local generated-WAV-backed Dataset where practical; don't create a second fake training pipeline.
2. **Train-family failure integrity.** Extend `IT-TRAIN-004`/`009` and `IT-RUN-003`/`004` with **both CNN and RF** cases for a forced Worker loss before publication and deterministic staging/publication failure. Check terminal/restart reconciliation, released active reservation, no stale completed Model/pointer, unchanged previously published Models and source WAVs, and no partial artifact promoted. Use real process/filesystem seams, not only domain mocks or Dataset Build analogues. Keep this distinct from 05d's diagnostic-log checks.
3. **Models after native restart.** Extend `IT-TRAIN-003`: shut down the Qt window/controller and reconstruct them from the same persisted Collection/settings. Navigate the actual Models list/detail, showing both saved family labels, identifiers, Dataset references, truthful metrics and unavailable states; independently retain the existing fresh-process **structural** reload tests. Do not add inference.
4. **Multi-instance boundary decision, not feature creep.** `IT-RUN-002` currently establishes a controller-scoped single Active Run. Search the existing contracts for an explicit *cross-application-process* guarantee. If absent, document the tested scope in the existing owning test/evidence and **do not** introduce global locking or claim cross-process exclusivity. If an existing requirement explicitly demands it, document the contradiction and test the smallest supported two-process case; obtain a scope decision before enlarging the application contract.

## Acceptance and exit

- The tests must assert the **actual public seam** and use their existing indexed IDs in function docstrings; adding new ID rows is unnecessary unless a distinct behavior is established. Cover each family with real Worker transitions and inspect preserved Model/Dataset manifests and source hashes where applicable. Preserve 05d stdout/logging behavior and all scientific contracts.
- Run the new focused cases and affected existing CNN/RF, Run and 05d regressions in the real environment; record commands, results, native evidence if the UI changes, platform/dependency limitations and verified Git SHAs in the existing evidence ledger. No HTML prototype changes, new training controls, inference, or installer work.
- **Exit:** real native-to-Model flow for both families, crash/publication no-false-success cases, and GUI-restarted Model history are demonstrated by assertions and passing runs. Unverified cross-process expectations remain explicitly unresolved, not silently implemented.

## Completion record

- `IT-TRAIN-012`/`014` now click the real native Start action for loaded nondefault CNN and RF
  presets, retain the frozen `request.json` snapshot after preset mutation/deletion, cross-check the
  published Model configuration and preserve source WAV bytes.
- `IT-TRAIN-004`/`009` and `IT-RUN-003`/`004` now kill real CNN and RF QProcesses before
  publication and force the shared exclusive publication seam to fail with a real filesystem lock.
  Terminal/restart state, released reservation, absent output/pointer/staging, preserved prior
  Model bytes and unchanged source WAVs are asserted.
- `IT-TRAIN-003` now closes the original native window/controller, reconstructs both from the same
  settings, and inspects the persisted CNN/RF list and detail views, including a truthful undefined
  metric reason. Existing fresh-process structural reload checks remain independent.
- Repository contracts contain no cross-application-process single-Run guarantee. `IT-RUN-002`
  is therefore explicitly controller/application-process scoped; cross-process exclusivity remains
  unverified and was not implemented.
- No visible UI or interaction changed, so the previously accepted Spec 05/05d native screenshots
  remain applicable and no new screenshot was captured.
