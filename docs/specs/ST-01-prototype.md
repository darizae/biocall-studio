# ST-01 — Studio launchpad + Detect interactive prototype

**Branch:** `detect-st01-prototype`, created from the `detect` integration branch (which starts from `main`). **Status:** design/prototype; no Python source edits, backend implementation, Train view rewrites or installer work.

## Entry inspection (scoped)

1. Follow `AGENTS.md` and `docs/agent/ROUTING.md`; verify real Git status and the ST-01 branch base. Check actual files before following docs; historical paths may be absent.
2. Inspect current Train navigation/screen composition in `src/biocall_studio_train/gui/`, relevant controller state, and genuine native screenshots under `docs/design/evidence/spec-*-native/`. Read the smallest necessary slices of Model export, `docs/PREDICTION.md`, `docs/design/UX_PARITY_MATRIX.md`.
3. Inspect **`/Users/danie/repos/BioCall-Studio`** for the provided **full branding asset folder**. Compare it with the repository's existing `assets/branding/`; synchronize the supplied asset set into that established location, preserving its useful directory structure, updating matching files only after comparison, and avoiding duplicate copies. The prototype references the repository assets by relative path. Do not invent replacement branding. Inspect the installed `../alp-ui` public components/Showcase and existing Train styling.

## Deliverable

A self-contained HTML/CSS/JS prototype at `docs/design/prototypes/studio-detect/` with `index.html`, local CSS/JS and relative references to the synced `assets/branding/` folder. No CDN, backend requirement, scientific inference, file writes to source roots, Train UI edits or obsolete-prototype edits. State/navigation must work locally in a browser; all synthetic examples visibly say **Demo**. Use correct product branding and the existing native Train visual language.

### Screens and behavior

1. **Launchpad:** three prominent cards: Train, Detect, Review. Train opens a **reference to the actual native Train** experience (existing screenshots and clearly labelled reference/entry boundary), not a new imaginary training UI. Review opens a minimal Coming later state. Returning to Studio is always clear.
2. **Detect setup:** choose a Train CNN Model and recording root in either order. Display selected Model family and compatibility state, root path and draft readiness; provide loading/empty/incompatible/changed-path states. Do not claim to verify real Model files in JavaScript.
3. **Recordings:** demonstrate recursive folder hierarchy, recognizable `recordings/` default, exclusion of Train positives/derived WAVs, included/undecided/excluded/invalid rows, counts, folder-level include/exclude, duplicate/path errors, scan progress/cancel and changed-file/rescan state. Source files remain untouched.
4. **Settings:** concise default CNN controls with context-sensitive HelpHints and collapsed advanced section; Start stays disabled until the mocked prerequisites are explicitly valid. Do not expose RF as a stand-alone recording-wide detection option.
5. **Run:** demonstrate preparing, running, cancellation, cancelled, interrupted, failed, completed and nonfatal per-file failure. Show progress without implying real scientific processing; switching workspace must not discard run context.
6. **Results:** recording list + interval table in original recording time, result provenance, clear empty/error states and click-through to source; provide an entry for optional **RF second-layer** analysis. The RF action produces a new **metadata-only** derived result with explicit parent and accepted/rejected/unscored states; original remains selectable and unchanged.
7. **Corpus Export:** from a frozen result selection, offer **individual WAV snippets**, **concatenated WAV + Raven TSV**, or **both**. Display an explicit destination picker/field and planned filename/source-time mapping; demonstrate successful path + **Show in folder** behavior without actually writing audio. Show conflicts, stale source and cancel/error outcomes. Distinguish application-owned metadata location from export destination.
8. **Relinking:** indicate a missing/moved recording root and a proposed rebind/rescan flow that does not silently bless changed inputs.

Navigation should be a natural workspace with a small number of routes/views rather than a long wizard. Preserve input drafts across route switches, expose Help/Wiki only where valuable, and keep copy researcher-readable and sparse. Illustrative numbers, filenames and detections must never be presented as real Model output.

## Acceptance and evidence

- Update `docs/design/UX_PARITY_MATRIX.md` with the **actual implemented** prototype routes, states and any deliberate deviations; do not create a competing UX matrix.
- Exercise every meaningful primary navigation/action and representative failure/cancel/retry path in a browser. Use local browser automation only for **this new prototype** if available; otherwise provide exact manual checks. Test keyboard activation/focus and desktop/narrow desktop layouts. Save a few representative screenshots locally under the prototype's `evidence/` only if they add value.
- Validate local paths/assets, test demo state transitions (with automated JS smoke checks if feasible), and run relevant scoped repo documentation checks. **No Python production changes means no invented unit/integration science results**; report what was run, not what was assumed. Before commit run the feasible ordinary repository suite per `AGENTS.md`, or explicitly record environment blockers.
- Commit only ST-01 files, with a real SHA and clean status. Report modified paths, test commands/results, open UX/scientific decisions and next-stage handoff. **Stop for owner review; do not start ST-02.**
