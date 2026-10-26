# BioCall Studio Train — Agent entrypoint

**Read narrowly.** Open [the task router](docs/agent/ROUTING.md), identify the *currently unaccepted* spec from the actual checkout (Git, code, tests and evidence), then read **that spec** and only the references it names. Do not pre-read the whole documentation tree, future specs, or sibling repositories. Do not infer progress from an archive date. If the task is only a bug fix or documentation change, follow its owning code/doc route rather than an unrelated numbered spec.

## Universal working rules

- Implement the specified local PySide6 Trainer, not a larger app. User-selected Collection inputs are read-only; `.alpaca/` outputs are versioned, validated and published without overwriting existing artifacts. Never invent working scientific results.
- Keep the root README for users: lead with the **BioCall Studio Train** name, purpose and branded banner; keep source-install commands, a plain-language Collection workflow, a small set of truthful native screenshots and the roadmap current; place concise contributor guidance last. Link to canonical detail instead of repeating agent rules or development status prose.
- Keep pure rules separate from Qt, filesystem publication and subprocess orchestration. Reuse the verified implementation at its correct owner; no speculative abstraction or downstream duplication of scientific algorithms.
- Use **test-driven development** at the real boundary. Match each asserting test to its indexed `UT-*` or `IT-*` case; record commands, failures and platform limits. A written test ID is not passing evidence.
- For **visible UI work**, follow the active spec's prototype/`alp-ui` acceptance links. The browser prototype illustrates interactions, not backend science. Capture/review real native screenshots.
- Keep visible copy sparse, plain and user-facing: do not expose internal IDs or implementation details, repeat labels, narrate the app as “we”, or add filler captions/cards/alerts. Put genuinely useful context in concise help or the Wiki; show editable names for artifacts. Destructive actions require clear confirmation and stay non-cascading; removing a Collection binding never deletes its files.
- Only use HPC data when the active test requires an authorized exemplar; private `docs/priv/` stays ignored and ordinary tests never connect to HPC. Missing `tests/data/` in ZIP handoffs is expected.
- Work on the correct Git branch, commit verified changes, and report the real commit SHA plus clean status. Do not silently merge, push upstream or advance to another spec. See [Git delivery](docs/agent/GIT_DELIVERY.md) when starting/finishing work.

**Navigation:** [router](docs/agent/ROUTING.md) · [phase order](docs/IMPLEMENTATION_SEQUENCE.md) · [spec index](docs/specs/README.md). Detailed domain, configuration, release and upstream rules belong to their **owning spec or canonical reference**, not this entrypoint.
