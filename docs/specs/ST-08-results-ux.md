# ST-08 — Native Results exploration

**Branch:** `detect-st08-results-ux` from reviewed `detect`. **Predecessor:** verified immutable ST-07 Results. **Successor:** ST-09. **Status:** planned.

## Scope and ownership

Detect owns native Results listing/history, recording-specific candidate interval table, selection per Result, Run status, provenance and missing-source/error/empty presentations. **Read** immutable Results; keep selection/filters/navigation as app-owned mutable UI state, clearly separate from the scientific artifact. No waveform/player, detector changes, export materialization or RF inference. Do not redesign Train.

## Contract and handoff

`ResultViewProjection` uses published Result ID/digest, `recording_id`, source-relative recording name, stable candidate IDs, `[start_frame,end_frame)` source-time positions and score/quality/status semantics; it must not invent scores or intervals when a source is stale. `ResultSelection` stores per-Result stable candidate ID sets with an explicit selection revision and current Result digest; any missing/different candidate ID invalidates/reconciles visibly. ST-09 refers to original parent Result, ST-10 freezes selected IDs **only when export begins**. No Result overwrite to save checkbox state.

Per-file failure and no-detection are different states. Missing source must not erase provenance or make the original Result unreadable. Very large candidate tables must be paged/lazy without full recording decoding. Native pages must preserve Run/header and return path while navigating away; focus order and selection change should update interval detail deterministically.

## Prototype alignment

Mirror `#detect/results`: changing selected recording updates only that recording's intervals; per-Result selection survives navigation, toggling original/refined Result is **prepared** but RF logic deferred to ST-09. Distinct populated/empty/error/partial data views, original recording timestamps and clear provenance links. Use `alp-ui.DataTable` model/view and appropriate public components; no hover-only controls, detached decorative micro-captions, speculative charts or developer text. Tooltips/HelpHints must answer a genuine user question, support keyboard focus and not repeat visible labels. Capture genuine native normal/compact screenshots and deviations.

## TDD and boundary verification

- `UT-DET-016` — immutable Result-to-view projection, stable selection/Result digest mapping, no cross-Result bleed.
- `UT-DET-017` — zero/no-source/file-error/partial/completed statuses and provenance visibility decisions.
- `IT-DET-015` — real Qt Result selection, recording switch, interval IDs, history and keyboard navigation on genuine ST-07 Result (`TD-UI`, `TD-RUN`, `TD-SCALE`).
- `IT-DET-016` — corrupted/unavailable source, empty/error/partial Result, persisted selection and actual normal/compact native screenshots without artifact mutation (`TD-UI`, `TD-CACHE`, `TD-FAIL`).

First tests at model/projection and real Qt seams; use actual persisted Results, not hardcoded production mock candidates. Run targeted and impacted ST-07 tests plus full feasible ordinary suites before commit. No full Train/Detect integration until ST-11.

## Gate

Owner-reviewed prototype hierarchy/typography/action parity, native focus/accessibility, accurate source-time selection and original metadata immutability. Integrate locally to `detect` only after review; no push.
