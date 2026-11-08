# BioCall Studio architecture

BioCall Studio is one Python distribution, package, native application, and public command. The
package owns workflows explicitly:

```text
biocall_studio/
  cli.py, __main__.py
  studio/application/     bootstrap, navigation, workflow coordination
  studio/gui/             native shell and suite branding
  shared/                 paths, streamed integrity hashing, owner leases
  train/                  application, domain, persistence, workflows, gui, data
  detect/                 application, domain, persistence, workflows, gui
  review/                 application, domain, persistence, workflows, and native gui
  resources/branding/     one suite-owned resource set
```

`shared` contains only infrastructure used across workflows. Train remains the authoritative
producer of Dataset and Model contracts; Detect imports those public contracts and does not copy
them into shared code. Review consumes verified immutable Detect Results without taking ownership
of them. Domain and shared modules are Qt-free. Studio owns application identity, theme
installation, branding, navigation, and the canonical data-root decision.

## Storage and identity

Qt's `BioCall Studio/biocall-studio` application-data location is divided into contained,
versioned roots:

```text
<suite-data>/
  train/v1/               Train settings, diagnostics, and owner leases
  detect/v1/              Detect settings, metadata, Runs, Results, exports, and leases
  review/v1/              Review projections, sessions, cache, and export history
```

Train Collections remain user-owned directories. Train may publish versioned `.alpaca/` metadata,
Datasets, Models, Runs, and staging inside a validated Collection. Detect treats source recording
trees and Train artifacts as read-only and keeps its mutable metadata outside those trees. Detect
Results and historical Detect exports remain immutable, source-time-provenance-bearing artifacts.
Review keeps a digest-bound, paged eligible-candidate projection under its own root, freezes
finalized annotation/settings provenance, and owns new streamed corpus exports and their private
history. It never writes into Detect storage or source recording trees.

Portable artifact references are normalized relative paths. Absolute paths, traversal, symlink
escapes, platform collisions, unbounded reads, and silent relinking are rejected. Missing or
unsupported schema and producer identifiers fail closed; no legacy settings or metadata migration
is attempted.

## Execution and publication

The native process owns one `QApplication`. Each workflow owns its controller state and Worker
supervision. In development every scientific supervisor launches the current interpreter as:

```text
python -m biocall_studio --worker <private-mode> --request ... --owner-lease ...
```

A frozen build uses its current executable with the same private arguments. The canonical CLI
validates the five supported Worker modes and their bounded private arguments before importing GUI
or scientific code. Kernel-released owner leases prevent orphaned Workers from publishing.

Workers stage on the destination filesystem, verify inputs and output contracts, then publish with
exclusive no-clobber semantics. Cancellation, crashes, stale source/model evidence, collisions,
and incomplete output never become completed artifacts. Source WAV bytes are never modified.

## Dependencies and platforms

Released `bioacoustics-dl-toolbox` owns reusable scientific primitives (including **display-only**
headless spectrogram DSP); released `alp-ui` owns public native presentation primitives. Studio
retains source-time provenance, settings, Review display cache identities and metadata. Their exact
versions, annotated-tag *target commits*, wheel SHA-256 and installed import origins are tracked in
`pyproject.toml` and release test evidence. Editable sibling checkouts cannot qualify a Studio release.
Changes to either dependency belong on independent reviewed branches in those repositories.

macOS is the currently exercised native development platform. Native Windows filesystem, process,
UI, packaging, and installer behavior must be qualified on Windows before release. Full
cross-workflow Studio end-to-end qualification remains owned by ST-11.
