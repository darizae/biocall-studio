# 05 — CNN and Random Forest training (phase router)

**Scoped references:** [05a — Configuration and presets](05a-training-configuration-and-presets.md) → [05b — CNN training and Model foundation](05b-cnn-training-and-model-foundation.md) → [05c — RF training and cross-family acceptance](05c-rf-training-and-cross-family-acceptance.md). **Prerequisite:** Start only after [04.5 — upstream audio extraction](SPEC_04_5_UPSTREAM_AUDIO_EXTRACTION.md) has **verified** acceptance; assess the actual checkout rather than inferring completion from this roadmap.

This file is a **stable entry point** for older Spec 05 links, not an additional implementation assignment. Route an agent to **only the first unaccepted sub-spec**, then follow that sub-spec's scoped references. Finish its tests, evidence and commit before starting the next; do not read all three as a default startup bundle.

| Stage | Independent handoff | Deferred until later |
|---|---|---|
| [05a](05a-training-configuration-and-presets.md) | Native binary CNN/RF configuration, fully resolved typed drafts, detailed settings and user presets | Real training, Model publication, end-to-end preset-to-Worker checks |
| [05b](05b-cnn-training-and-model-foundation.md) | Real CPU CNN through the Worker; common versioned Model publication and trusted CNN structural reload | RF execution and **joint** CNN/RF acceptance IDs |
| [05c](05c-rf-training-and-cross-family-acceptance.md) | Real RF, complete both-family Model contract, plots, preset/Worker integration and Spec 05 qualification | Nothing in Spec 05 may be marked accepted until all applicable indexed gates pass |

**Global boundary:** exactly two mutually exclusive `target`/`noise` classes, single-label CNN/RF Training only. Preserve the HTML UX prototype; native additions use `alp-ui`. Published Models must retain the complete scientific configuration for **future** Prediction, but this phase performs **no new-WAV inference/scoring**; see [future Prediction](../PREDICTION.md). Canonical field, UX, export, science and test requirements are linked by the **owning sub-spec**, not repeated here.
