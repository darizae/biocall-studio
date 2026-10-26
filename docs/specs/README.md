# Numbered implementation specs

The authoritative **sequence and exit outcomes** are in [Implementation sequence](../IMPLEMENTATION_SEQUENCE.md). To start an agent session, use the [task router](../agent/ROUTING.md), then open **only the active spec** and its scoped references. Test indexes and the prototype acceptance gate are consulted at the point they are needed, not during every session.

Order: **01 → 02 → 03 → 04 → [04.5](SPEC_04_5_UPSTREAM_AUDIO_EXTRACTION.md) → [05a](05a-training-configuration-and-presets.md) → [05b](05b-cnn-training-and-model-foundation.md) → [05c](05c-rf-training-and-cross-family-acceptance.md) → [05d](05d-end-to-end-logging-and-diagnostics.md) → [05e](05e-training-critical-path-and-recovery-verification.md) → [05f](05f-ui-chart-scale-and-cli-coverage.md) → [05g](05g-long-running-sessions-and-safe-exit.md) → 06 → 07**.
