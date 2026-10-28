# BioCall Studio — agent instructions

One Python/PySide6/`alp-ui` desktop application: **Train** (preserve scientific/GUI/Worker behavior), **Detect** (ST-03–ST-10), **Review** (placeholder). ST-01 prototype and ST-02 native shell are **owner-approved**; browser automation was not completed and does not count as test evidence. The approved ST-01 prototype is the design requirement for new native Studio/Detect screens.

## Minimal entry route

1. Read [ROUTING](docs/agent/ROUTING.md), then **only the one active stage spec** from [the sequence](docs/IMPLEMENTATION_SEQUENCE.md). Nine future specs are prepared, not nine simultaneous assignments.
2. Verify file paths and real branch/checkout/installed dependency state before changing anything. A ZIP, screenshot, spec or test index is not an executed test.
3. Execute one stage on `detect-stNN-purpose` from reviewed local `detect`. Do not implement later stages, reorganize Train or load all sibling repositories. On reviewed acceptance, local merge policy is in [Git delivery](docs/agent/GIT_DELIVERY.md). **Never push**.

## Non-negotiable boundaries

- Each workflow owns its data, UI, Runs, logs, tests and immutable outputs; share only demonstrated infrastructure with clear ownership. Detect metadata is per-user application-owned **outside source directories**; source WAVs and Train's Collection/Models/Workers remain read-only to Detect.
- Keep pure domain/interval decisions out of Qt/Workers. Inspect the actual upstream source before making scientific inference, RF features or WAV-transform assumptions. If a missing function belongs in `bioacoustics-dl-toolbox`, or a presentation primitive in `alp-ui`, fix/test/commit on a **separate branch in that repository**; never hide it in a BioCall Studio workaround. Verify downstream import origin, compatibility and both repos' real SHAs.
- Native UI follows accepted ST-01 route/state hierarchy and the current Train reference, using the installed **public** `alp-ui` API. Native interactive behavior, focus, normal/compact layouts, tooltips and accessible `HelpHint`s must be exercised with real Qt. No decorative captions, invented placeholder values, developer commentary, dead actions, inaccessible hover-only meaning or unexplained technical terms in researcher-facing copy. Only display a hint when it explains a real decision; longer explanations belong in help/docs.
- Treat paths/models as untrusted until validated. Use versioned handoffs, bounded reads, safe contained staging, checksums, explicit relinking, source-time provenance and immutable results. Never report cancelled/failed work as complete or missing source as zero candidates. Store diagnostics with allowlisted privacy-safe fields.
- **TDD per stage:** add its indexed cases first (pure `UT-*`, real-boundary `IT-*`), assert meaningful failure/cancel/non-mutation, use minimum `TD-*` fixtures, real WAV/Qt/QProcess/Model only where the owned seam requires it. Run scoped tests while implementing, then the full feasible ordinary unit + integration suites, lint and audit **before each implementation commit**. The ≥600-second soak is separately initiated. Record exact pass/fail/skip/block evidence. **ST-11 alone owns the complete cross-workflow Studio end-to-end integration test.**

Routing and stage gates are authoritative over incidental broken links to old historical notes; do not reconstruct missing legacy files. **Active next stage: [ST-03](docs/specs/ST-03-detect-workspace.md)** after checking reviewed `detect` branch state.
