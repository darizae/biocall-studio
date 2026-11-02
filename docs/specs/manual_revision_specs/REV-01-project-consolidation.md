# REV-01 — BioCall Studio project consolidation

**Historical branch:** `detect-rev01-project-consolidation`. **Predecessor:** ST-10.
**Successor:** REV-02. **Status:** implemented and included in the current merged `main` source
baseline.

## Outcome and boundaries

BioCall Studio is one application and one Python distribution named `biocall-studio`. Train and
Detect become workflow-owned packages inside `biocall_studio`; the separate
`biocall_studio_train` package, distribution identity, direct application and console command are
removed. This is an intentional breaking migration: do not add import aliases, command shims,
legacy producer-name readers, application-data migration or dual package layouts.

Preserve Train and Detect scientific decisions, source-WAV non-mutation, artifact immutability,
Worker cancellation/publication rules and current GUI behavior. This revision changes ownership,
imports, launch routing and product identity; it does not change algorithms, thresholds, WAV
transforms, Model formats or workflow semantics. Do not create empty Review layers. Until Review
owns real behavior, its placeholder remains part of the Studio shell.

## Package and ownership contract

The installed wheel contains one top-level package with this responsibility map:

```text
src/biocall_studio/
  __init__.py, __main__.py, cli.py
  studio/                 # application bootstrap, shell, navigation, coordination
  shared/                 # proven workflow-neutral infrastructure only
  train/
    application/ domain/ persistence/ workflows/ gui/ data/
  detect/
    application/ domain/ persistence/ workflows/ gui/
  resources/branding/     # one suite-owned brand resource set
```

- Move the existing Train layers intact under `biocall_studio.train`. Move Studio shell files out
  of the generic top-level `gui` namespace and Detect presentation files under
  `biocall_studio.detect.gui`. Keep pure Detect decisions separate from controller, persistence,
  Worker and Qt modules rather than reproducing the current flat Detect package.
- `shared` is not a dumping ground. Extract only infrastructure with two demonstrated consumers:
  portable relative-path/collision validation, cancellation-aware streamed integrity hashing,
  and kernel-released owner leases/Worker guards. Suite bootstrap, theme installation and branding
  remain Studio-owned. Workflow storage layout, diagnostics records, domain types, artifact schemas
  and UI state stay with their owner.
- Train remains the authoritative producer of Dataset and Model contracts. Detect may import
  those public Train contracts through `biocall_studio.train`; it must not duplicate them in
  `shared` merely to avoid a workflow-to-workflow dependency.
- Replace product/component identifiers in new metadata and diagnostics with `biocall-studio` or
  the owning `biocall_studio.<workflow>` component. Existing metadata that requires the old
  producer identifier is unsupported; do not silently reinterpret or rewrite it.

Use this source-to-target map rather than choosing a new structure during implementation:

| Current source | Target ownership |
|---|---|
| `biocall_studio.__main__`, `cli` | Remain package-root public launch/hidden Worker dispatch only. |
| `biocall_studio.gui.app`, `coordinator`, `navigation` | `biocall_studio.studio.application` |
| `biocall_studio.gui.shell`, `branding`, suite resources | `biocall_studio.studio.gui` and package-root `resources/branding` |
| Every `biocall_studio_train/<layer>` module | `biocall_studio.train/<same layer>`; do not collapse the existing layer boundaries. |
| Detect pure identities, settings, inventory decisions, Run/Result/export contracts and arithmetic | `biocall_studio.detect.domain` |
| Detect controller, scan/intake orchestration and use-case coordination | `biocall_studio.detect.application` |
| Detect metadata stores, diagnostics, receipts, staging/publication and Run repositories | `biocall_studio.detect.persistence` |
| Detect CNN/RF/export execution and supervised Worker entry modules | `biocall_studio.detect.workflows` |
| Current Studio-level `gui.detect*` modules | `biocall_studio.detect.gui` |
| Portable path rules, streamed hash helper and duplicated owner-lease mechanics | `biocall_studio.shared`; workflow-specific messages/storage paths remain in adapters. |

When one current Detect module mixes rows from this table, split it at those responsibilities; do
not move the mixed module wholesale and call the directory domain-driven. Domain and shared modules
must remain Qt-free, and GUI modules must not become artifact or scientific authorities.

## Entry points, Workers and local data

`biocall-studio = "biocall_studio.cli:main"` is the only public console entry, and
`python -m biocall_studio` is the only public module launch. Remove the `biocall-studio-train`
script and `python -m biocall_studio_train`. `--version` resolves the `biocall-studio`
distribution.

The canonical CLI privately dispatches these supervised Worker modes:

| Worker mode | Owner and existing request contract |
|---|---|
| `train-dataset-build` | Train Dataset Build |
| `train-cnn-training` | Train CNN training |
| `train-rf-training` | Train Random Forest training |
| `detect-cnn` | Detect first-pass CNN detection |
| `detect-rf-refinement` | Detect RF candidate refinement |

Keep `--request`, owner-lease, diagnostic-session and bounded test-delay arguments hidden and
structured. In development every supervisor launches `sys.executable -m biocall_studio
--worker <mode> ...`; a frozen build launches its current executable with the same arguments.
Unknown modes or missing Worker-only arguments fail before loading GUI or scientific code.

Qt's canonical `BioCall Studio/biocall-studio` application-data location contains separate
versioned `train/v1/` and `detect/v1/` roots. No workflow may read another workflow's private settings
by directory traversal. Do not search or migrate the prior `biocall-studio-train` settings path.
Collection-owned `.alpaca/` artifacts and Detect's app-owned immutable artifacts keep their
existing ownership and containment rules.

## Repository identity and documentation

- Rename the package metadata, tool tables, descriptions, active documentation, scripts, tests,
  diagnostic component names and build/resource inclusions to BioCall Studio. Historical Git
  commits and the raw manual notes are not rewritten.
- The repository host rename to `biocall-studio` is owner-coordinated. After the owner changes the
  remote, update the local `origin` URL and verify it read-only; never push, tag or publish.
- Replace the root README with a concise product description, supported Python range,
  prerequisites for the actual adjacent `alp-ui` and `bioacoustics-dl-toolbox` development
  sources, one clean-environment install path, the canonical launch command and links to
  `docs/DEVELOPMENT.md` and `docs/MANUAL_WORKFLOW.md`. Move troubleshooting, test matrices,
  screenshots, roadmap history and platform qualification details out of the README.
- Execute every advertised POSIX command in a newly created temporary virtual environment. Check
  Windows commands on native Windows before calling them verified; otherwise label them as
  unqualified and link to development guidance. A stale existing editable install is not evidence
  that a documented command works.
- Update live architectural, release and test documentation so future instructions do not direct
  agents to the removed package or entry point. When a historical stage clause conflicts with
  this revision, this revision is the explicit successor and authority.

## TDD and verification

- `UT-CLI-002` — canonical argument parsing and Worker dispatch accept only the five modes above;
  missing/invalid Worker arguments fail without GUI import, and distribution version lookup uses
  `biocall-studio`.
- `UT-STU-003` — an import/ownership audit rejects `biocall_studio_train`, forbidden reverse
  dependencies and workflow-specific modules under `shared`; canonical application-data
  decisions yield separate contained Train and Detect roots.
- `IT-STU-009` — build a wheel, install it into a clean temporary environment with the exact
  committed dependencies, verify the wheel exposes only `biocall_studio`, launch the canonical
  native shell, and exercise all Train/Detect Worker commands through real subprocesses. Importing
  `biocall_studio_train` and invoking `biocall-studio-train` must fail. Existing source WAV bytes
  and a freshly produced Dataset, CNN Model, RF Model, Detection Result and derived Result remain
  scientifically equivalent to the pre-move contracts apart from the declared product identity.

Write the indexed tests and static import audit before moving modules. During the migration, run
the affected unit/integration groups after each vertical slice rather than leaving the tree
unimportable until the end. Before commit, run all feasible ordinary suites, ruff, test-ID audit,
wheel-content inspection, README command smoke tests and `git diff --check`. Record dependency
SHAs/import origins and any native-platform block separately; no installer or whole-Studio E2E
claim is introduced before ST-11.

## Exit gate

Close only when one wheel, package, application identity and public command remain; the documented
source install works from a clean environment; all Workers launch through the canonical CLI; no
runtime code or live instruction imports the removed namespace; and Train/Detect ownership and
scientific behavior have been revalidated. Commit on the revision branch and integrate locally
into `detect` only after owner review. Never push or begin REV-02 automatically.
