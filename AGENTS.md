# BioCall Studio — agent instructions

BioCall Studio is one PySide6/`alp-ui` desktop application with **Train**, **Detect**, and a placeholder **Review** workspace. Train already runs; protect its behavior and native visual design. Detect starts with CNN candidate detection, optional RF refinement, and metadata-first results. Review is not implemented.

## Start and scope

1. Read [task routing](docs/agent/ROUTING.md), then the **one active spec** and only its necessary references.
2. Inspect the actual Git tree, code, tests, dependencies, and available native screenshots. A spec, checklist, or ZIP is not proof of implementation.
3. Implement only the active spec. Do not move, rename, or refactor Train just to prepare for Detect.

## Engineering rules

- Keep scientific/domain rules separate from Qt, processes and persistence. Reuse existing code only at a justified ownership boundary; inspect real toolbox/pipeline APIs before scientific changes.
- Input recordings are read-only. Treat paths, symlinks and manifests as untrusted; publish derived artifacts safely and immutably with source-time provenance and validated checksums. Detection metadata lives in an app-owned workspace outside the selected source root.
- Use `alp-ui` public components and the existing **native Train** implementation/screenshots as the visual baseline. Use `/Users/danie/repos/BioCall-Studio` as the branding asset source; put only required, checked-in assets in this repository.
- Keep user-facing language concise; use contextual `HelpHint`/Wiki for detail. No simulated scientific results in native production code. Prototype-only simulated data must be visibly identified.
- Specify and run scoped indexed `UT-*`/`IT-*` tests; use real WAVs, a real Qt controller and real Workers wherever the claim requires them. Report exact passes, failures and skips. Do not run the 10-minute soak unless requested.
- Before an implementation-stage commit, run the feasible ordinary full suite (unit + integration, excluding explicit soak/installer-only cases), plus affected targeted tests. Record unavailable platforms as blockers, not passes.
- Follow [Git delivery](docs/agent/GIT_DELIVERY.md): real branch, clean status, reviewed diff, real commit SHA; never merge, push or start another stage without approval.

**Source of stage order:** [Implementation sequence](docs/IMPLEMENTATION_SEQUENCE.md). **Active spec:** [ST-01](docs/specs/ST-01-prototype.md).
