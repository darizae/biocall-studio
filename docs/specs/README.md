# Numbered implementation specs

The authoritative **sequence and exit outcomes** are in [Implementation sequence](../IMPLEMENTATION_SEQUENCE.md). To start an agent session, use the [task router](../agent/ROUTING.md), then open **only the active spec** and its scoped references. Test indexes and the prototype acceptance gate are consulted at the point they are needed, not during every session.

Order: **01 → 02 → 03 → 04 → [04.5](SPEC_04_5_UPSTREAM_AUDIO_EXTRACTION.md) → [05a](05a-training-configuration-and-presets.md) → [05b](05b-cnn-training-and-model-foundation.md) → [05c](05c-rf-training-and-cross-family-acceptance.md) → 06 → 07**.