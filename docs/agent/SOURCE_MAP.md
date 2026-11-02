# Source map — inspect only what the task needs

This is a lookup aid, not a request to read entire repositories. Confirm real local checkouts, installed-module origins and commit SHAs before using an external API.

| When | Source to inspect | Boundary |
|---|---|---|
| Native UI control or HelpHint | `../alp-ui` public exports, `docs/components.md`, `gallery/showcase.py`; [consumer contract](../design/ALP_UI_CONSUMER_CONTRACT.md) | Use installed public components; fix/test/commit reusable primitives upstream, not in the app. Follow the [UX matrix](../design/UX_PARITY_MATRIX.md). |
| CNN training or Detect inference | Installed `bioacoustics-dl-toolbox` and corresponding sibling source/tests; [Model export contract](../science/MODEL_EXPORT_CONTRACT.md) | Verify architecture, WAV preprocessing, numerical parity, class/order and actual import origin. No assumptions from a manifest alone. |
| RF feature extraction/refinement | `../alpaca-pipelines` RF training/features/inference sources only when relevant | Verify ordered features, preprocessing, fitted classes and reference probabilities against actual code. Do not import a second workflow's persistence model. |
| Train configuration or audio processing | [configuration catalog](../science/TRAINING_CONFIGURATION_CATALOG.md), owning Train code and specific toolbox WAV functions | Existing Train behavior is protected. Any shared scientific fix uses the [upstream workflow](UPSTREAM_TOOLBOX_WORKFLOW.md). |
| Private HPC historical data | `docs/priv/hpc-source-access/SKILL.md` and approved site references, **only if authorized** | Read-only bounded metadata queries; redact sensitive paths; never require HPC for CI or ordinary app operation. |
| Integration tests | [test skill](indexed-integration-tests/SKILL.md) and the owning `IT-*`/`TD-*` rows | Validate real boundaries, cancellation and non-mutation; the audit alone is not passing test evidence. |

Keep source inspection notes concise in the *owning PR*. If an upstream change is necessary, record its separate branch/commit/test results and rerun affected BioCall Studio tests after reinstalling the library.
