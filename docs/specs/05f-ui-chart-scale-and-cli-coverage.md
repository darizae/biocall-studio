# 05f — UI, chart, scale and CLI coverage closeout

**Status: verification hardening complete; owner review pending.** This work began after 05e's
recorded handoff and strengthens the *existing* acceptance contracts without another pass over
already proven science or a broad UI redesign. The HTML prototype is unchanged.

**Scoped references:** `IT-TRAIN-005`/`006`/`010`/`011`, `IT-COL-007`, `IT-UI-001` in [integration behaviors](../INTEGRATION_TEST_BEHAVIORS.md); `UT-CLI-001` in [unit index](../UNIT_TESTING.md); `TD-UI`, `TD-CONFIG`, `TD-TRAIN`, `TD-SCALE` in [fixture guide](../INTEGRATION_TEST_DATA.md). Begin with `tests/integration/test_training_ui.py`, `test_cnn_training.py`, `test_rf_training.py`, `test_collection_scan.py`, `test_shell.py` and `tests/unit/test_cli.py`. For native-only changes consult the **relevant** [UX parity rows](../design/UX_PARITY_MATRIX.md), [prototype acceptance](../design/PROTOTYPE_ACCEPTANCE.md) and [configuration extension](../design/SPEC05_CONFIGURATION_EXTENSION.md); use `../alp-ui` Showcase as required. Source-first prototype lookup hints are optional, not a restriction on inspection. [Git delivery](../agent/GIT_DELIVERY.md) applies at handoff.

## Coverage to close, in order

1. **Advanced native fields (`IT-TRAIN-010`/`011`).** Current tests verify catalog/widget presence and selected keyboard/HelpHint/reset paths, not **each** detailed editable field. Use parameterized native interactions across both families: typed control/value; actual default, current and suggested display with basis; focusable HelpHint/tooltip and correct Wiki anchor; changed indicator, per-field and section reset, collapse/reopen preservation, cross-field/unsupported-selection blocking. Exercise representative keyboard navigation through actual widgets, rather than asserting only static metadata. Cover derived/noneditable fields as such. Keep tests maintainable by driving the canonical field catalog instead of copying 67 expectations into this spec.
2. **Scientific values represented in plots (`IT-TRAIN-005`/`006`).** Compare native `alp-ui.Plot` line-series values/epoch axis and ordered RF importance/bar labels directly against measured persisted Run/Model facts; verify accessible numeric alternatives report the same numbers. Confirm undefined/nonfinite values are **absent**, not replaced with zero, and RF never displays epoch loss. Inspect the real public `alp-ui` API or the narrow data-binding seam; do not invent Plot internals or satisfy the test with mocked chart content.
3. **Responsive large Collection (`IT-COL-007`).** The current 10,001-row test checks metadata and Qt model paging, but not a live window's responsiveness. Exercise a real Qt window/model during paging/filter/navigation while event-loop sentinel events continue to run; instrument actual header reads and peak/paged allocation where feasible. Use repeatable, justified budgets drawn from existing [integration strategy](../INTEGRATION_TESTING.md) and the implementation; record measured environment and thresholds rather than asserting arbitrary machine-specific wall time or requiring HPC files.
4. **Index ownership for existing CLI tests (`UT-CLI-001`, `IT-UI-001`).** The four pre-existing `tests/unit/test_cli.py` functions lack test-ID docstrings; assign `UT-CLI-001` (version, help/settings isolation, import without Qt, invalid-option early failure) without changing their behavior. Map the existing console-startup test in `test_shell.py` to `IT-UI-001` and confirm it actually asserts isolated settings and real Qt startup. Do not create four extra IDs or duplicate CLI test implementations.

## Acceptance and exit

- Extend the listed tests **at their owning seam** and correct only observable defects. Every indexed ID included in a test docstring must be backed by assertions, not just mention. Reuse existing `TD-*` fixtures and small generated WAVs; preserve non-mutation, binary `target`/`noise` scope, presets and Model integrity.
- Run focused Qt/chart/scale/CLI cases plus impacted regression suites, `scripts/audit_test_ids.py`, Markdown/link handoff audits and real native screenshot comparison **if any visual behavior changes**. Preserve 05e and 05d evidence. Record failures/blockers and honest per-ID coverage in the current evidence ledger and commit with verified status.
- **Exit:** meaningful per-field interaction, exact plotted-data fidelity, observable large-Collection event-loop responsiveness and CLI index consistency are verified. Native installed-app qualification still belongs to 06/07.

## Completion record

- Catalog-driven, family-parameterized Qt interactions cover every detailed editable and derived
  field, including current/default/suggested provenance, HelpHint/tooltip/Wiki anchors, changed and
  reset state, keyboard disclosure, collapse preservation and existing invalid/unsupported gates.
- A narrow consumer-owned binding seam records the exact ordered values passed to the real public
  `alp-ui.Plot` setters. Genuine CNN/RF Worker cases compare that data, axes and numeric summaries
  to persisted Run/Model facts; nonfinite Run values are rejected and RF has no epoch-loss output.
- The 10,001-record Collection case now mounts the model in a visible `MainWindow`, verifies
  200-row bounded pages, event-loop sentinel delivery, mid-page route navigation, live filtering
  and exact header-read counts without decoding full recordings or using HPC data.
- Existing CLI tests are mapped to `UT-CLI-001`; real console startup is mapped to `IT-UI-001`.
  The full suite passes with 104 tests, and the test-ID/native-evidence/static audits pass.
- No visible state or rendering changed, so the existing original-resolution Spec 02/05 native
  screenshots were reviewed and retained. Installed `.app` and Windows qualification remain in
  Specs 06/07. See the [05f evidence ledger](../design/evidence/README.md#spec-05f--ui-chart-scale-and-cli-coverage-closeout).
