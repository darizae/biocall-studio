# 05a — Training configuration, native controls and saved presets

**Order:** after verified [04.5](SPEC_04_5_UPSTREAM_AUDIO_EXTRACTION.md); before [05b](05b-cnn-training-and-model-foundation.md). One agent assignment. Do not begin scientific fitting in this sub-spec.

**Read for this work:** [native-only configuration extension](../design/SPEC05_CONFIGURATION_EXTENSION.md) (visual acceptance), [field catalog](../science/TRAINING_CONFIGURATION_CATALOG.md) and [typed field roster](../science/TRAINING_CONFIGURATION_FIELDS.json) (field-by-field authority), [preset contract](../science/TRAINING_PRESETS.md), [binary scope](../science/BINARY_CLASSIFICATION_CONTRACT.md). Consult the [training Wiki](../wiki/TRAINING_CONFIGURATION.md) **only at affected field anchors**. For implementation tests, open only `UT-TRAIN-007`–`010` in the [unit index](../UNIT_TESTING.md), `IT-TRAIN-010`/`011`/`013` in the [integration index](../INTEGRATION_TEST_BEHAVIORS.md), and corresponding `TD-CONFIG`/`TD-PRESET`/`TD-UI`/`TD-FAIL` rows in the [fixture guide](../INTEGRATION_TEST_DATA.md). Resolve actual `../alp-ui` public controls/Showcase before native work.

## Deliverable and boundaries

- Implement a **Qt-independent typed draft → validated/resolved configuration** boundary for both families, consistent with the complete catalog (including supported, derived and explicitly unsupported dispositions). Reject invalid Dataset/device/cross-field combinations and anything other than binary single-label `target`/`noise`; never silently clamp values. Distinguish presentation/default/suggestion metadata from the effective Worker snapshot. Define the frozen Run input handoff needed by 05b/05c, but **do not simulate successful training or publish placeholder Models**.
- Implement the existing prototype's **Dataset → Model configuration → Start Training** hierarchy in the native app. Only the indexed `ui_tier=primary` roster is visible initially; a **collapsed More settings** disclosure contains the family-specific detailed groups. Each control has typed current/default/recommended values, honest recommendation provenance, `alp-ui.HelpHint`, a precise Wiki anchor and accessible errors; reset and collapse/family changes preserve independent drafts. Preserve the untouched HTML prototype. Follow the extension document for narrow layouts, keyboard use, field status and required native screenshots.
- Persist user-level, versioned **saved presets** separately from Collection artifacts; implement the contracted create/load/rename/duplicate/overwrite/delete and corruption/compatibility/atomic-write handling. Loading does not alter the Dataset or start a Run. Do not store source paths, mutable preset references as scientific configs, editable class count, or legacy launcher parameters.
- Keep the Start Training action/placement faithful to the prototype; validate and freeze the complete resolved input before eventual Worker dispatch. **Until a real family executor exists, do not report a Run as trained or render invented metrics.** The actual Worker→executor→Run/Model round-trip belongs to 05b/05c.

## Tests and exit

Start with failing asserting tests for **`UT-TRAIN-007`–`010`** (typed roster, validation/reset, draft/preset storage) and **`IT-TRAIN-010`/`011`/`013`** (real Qt and restart persistence). Use a redirected temporary preset directory, not real user settings; screenshots alone do not establish control behavior. Capture native collapsed/advanced CNN/RF, presets, and narrow/focus states under `docs/design/evidence/spec-05-native/`; record actual prototype/Showcase comparisons in the [evidence ledger](../design/evidence/README.md). Do not invent screenshots or alter the prototype.

**Deferred tests:** `IT-TRAIN-012` (observed real scientific Worker settings) and `IT-TRAIN-014` (preset-origin completed Run/Model) are **not** satisfied by mock dispatch or UI state; execute them after both families exist in 05c. The cross-family training and Model test IDs also remain open. Exit 05a only with its own executable tests, actual native evidence, source-preserving review and a real [Git handoff](../agent/GIT_DELIVERY.md); report missing dependencies/native platform as blockers, not green checks.

## Implementation closeout — 25 October 2026

**Complete and ready for owner review.** A Qt-free configuration boundary loads the authoritative
67-field roster, preserves independent CNN/RF drafts, rejects invalid numeric, cross-field,
Dataset, device and unsupported combinations without clamping, and freezes a complete immutable
binary `target`/`noise` snapshot. User presets are versioned and stored outside Collections with
atomic replace, restrictive permissions, strict revision/key/type checks and create/load/rename/
duplicate/overwrite/confirmed-delete behavior.

The native page follows the prototype's Dataset → Model configuration → Start Training hierarchy.
Only the indexed primary roster appears initially; one keyboard-operable More settings disclosure
contains the six CNN or three RF groups. Every catalog field has an observable typed value,
`alp-ui.HelpHint`, specific Training Wiki anchor and explicit default/suggestion provenance;
derived binary/classifier and RF feature fields are read-only. Family switching, collapsing,
validation and preset roundtrips preserve drafts. A valid Start Training action freezes the 05b/05c
handoff and truthfully states that no Run was started in this configuration-only phase.

TDD began with collection failures for missing `domain.training` and `gui.training` modules.
`UT-TRAIN-007`–`010` and `IT-TRAIN-010/011/013` now pass. `IT-TRAIN-012/014`, genuine fitting,
measured metrics and Model publication remain deferred exactly as specified. The scientific review
used `bioacoustics-dl-toolbox` `0fce0d4fa3d0931c5731e8b868f705e0a2120835` and
`alpaca-pipelines` `91af5287dc18313f88902dc9696e8756274736b3`; the native component review
used `alp-ui` `330aaab96a6b32dd2d83ae84a52a2a238446d264`.

Native macOS 26.6.2 arm64 captures and the six-dimension review are recorded in the
[evidence ledger](../design/evidence/README.md). Browser automation was unavailable in the session;
the unchanged prototype was inspected source-first through its checked-in `trainPage`, transition
functions, CSS and `rf-config-preview.png`, consistent with the acceptance procedure. No prototype
file was modified.

Verified commands:

```text
.venv/bin/python -m pytest -q tests/unit/test_training_config.py
                                                            4 passed
.venv/bin/python -m pytest -q tests/integration/test_training_ui.py
                                                            3 passed
.venv/bin/python -m pytest -q                              73 passed
.venv/bin/python -m ruff check src tests scripts           passed
.venv/bin/python -m ruff format --check src tests scripts  53 files formatted
.venv/bin/python scripts/audit_test_ids.py                 49 IDs, 0 unknown
.venv/bin/python scripts/check_fixtures.py                 6 WAVs verified
.venv/bin/python scripts/verify_handoff.py --require-native-ux
                                                            0 errors
git lfs fsck                                                OK
.venv/bin/python scripts/capture_spec05_screenshots.py     9 Cocoa captures reviewed
.venv/bin/python -m pip wheel --no-deps --wheel-dir <temp> .
                                                            packaged catalog verified
```
