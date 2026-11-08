# Review spectrogram generation — owner decisions and copy register

**Decision source:** owner answers of 2026-11-03 to the eight Phase-1 questions. **Status:** implemented source renderer/settings/cache in Studio `main`; these approved decisions remain the scientific/researcher-copy contract. Numerical defaults are defined and tested in source rather than inferred from early proposed benchmarks. Final native install/owner field qualification is separate.

| ID | Decision / alternatives considered | Owner resolution and rationale | Changes governed |
|---|---|---|---|
| SP-01 | 4.2 kHz low-call default vs 3 or 8 kHz fixed | **Approved:** default 4.2 kHz, **researcher-selectable** limit. Low-frequency calls remain legible; higher-pitched work is supported on demand. | Pre-spec; RV-03/05; prototype axes/settings |
| SP-02 | Simple presets vs many processing controls | **Approved:** small friendly selectors **plus minimal collapsed Advanced**; researcher also controls spectrogram/context length. Avoid full DSP workbench. | RV-03/05; prototype settings/editor |
| SP-03 | Fixed between-file intensity vs historical within-image relative | **Approved:** peak-relative spectrum; **Contrast** exposed. Colours cannot be interpreted as absolute between-file loudness. | RV-03/05; compare/tooltip/tests |
| SP-04 | Historical stereo waveform mean vs channel-power average | **Approved:** per-channel FFT power averaged for display; preserve original audio for playback and export. Opposite-phase content must not cancel. | RV-03; scientific qualification |
| SP-05 | Mutable builtin vs protected default, user presets vs sessions | **Approved:** one non-editable, non-deletable **Default**, user creates editable presets; **saving an edit requires confirmation** and makes dependency on sessions intelligible. **Resolved safety policy:** existing sessions keep effective snapshots; no automatic bulk regeneration. Offer explicit current-Open-session update separately. | RV-02/04/05; prototype editor and session path |
| SP-06 | Suite-level route vs Review-specific Settings | **Approved:** **Review → Spectrograms → Settings**, with picker accessible during session start. | RV-05/07; prototype nav |
| SP-07 | Eager physical purge vs logical invalidate | **Approved:** when confirmed for an Open session, invalidate that session's image references; regenerate visible/on-demand, with bulk separately. Keep valid shared content until cache eviction. Never change labels. | RV-02/04/05/07; epoch/cache tests |
| SP-08 | Full-resolution images for every candidate vs hybrid | **Approved:** Generate all thumbnails only; large images on demand, fixed resolution tiers. | RV-03/04/05/08; benchmark/50k |

## Concrete interaction resolution from SP-05

- Selecting **Edit** on a named user preset opens an *unsaved draft*. Changing controls, Test WAV or Compare does **not** mutate the saved preset or existing session. **Save changes** opens an impact confirmation with the number and statuses of sessions originally based on this preset (include sessions using older revisions). **Save preset** creates a new revision for future uses only; old sessions continue with their frozen settings and existing valid caches. Renaming follows the same confirmation. Cancel discards the pending save, not the original.
- If the current Open session uses the preset, the confirmation can offer **Save and use in this session** as an **explicit alternative**; show incremental illustrative time/storage and the cache regeneration warning. It updates only that session after REV-05 admission and atomic settings switch. Other Open/Closed/Finalized sessions remain unchanged. If a different Open session is active, offer a separate Change preset path rather than silently binding it.
- **Delete** requires separate confirmation; removes the user preset from future selections and its explicitly saved example images, but does not change session snapshots/cache/labels or finalized provenance. Delete disabled on Default. The same name may be reused for a new *identity* and must not relink old sessions.
- A session may **Change preset** while Open. Closed must first Resume; Finalized cannot change (Continue in new session inherits settings and becomes independently editable). Edits to an old preset never mutate old snapshots. Never present regeneration as a requirement to save the global preset alone.

## Researcher controls and HelpHint text

The compact researcher controls and three Advanced controls retain the owner's approved scope. **Current implemented numeric bounds and defaults are defined by** `src/biocall_studio/review/domain/spectrograms.py` and the indexed spectrogram tests, not unverified historical benchmark estimates. Exact defaults/settings snapshots must remain versioned and source-auditable; existing keyboard and HelpHint behavior must not be silently rewritten.

| New interaction | Proposed visible wording |
|---|---|
| Settings entry | **Settings** (inside **Spectrograms**; not a global Studio page) |
| Preset controls | **Default** · **New preset** · **Edit** · **Save changes** · **Delete** · **Compare** · **Test WAV** · **Save example** |
| Advanced expander | **Advanced** (collapsed) |
| Session start | **Spectrogram preset**; default selected; user may choose another before Start session |
| Session change | **Change preset** · “Existing spectrogram images for this session will need to be generated again. Labels and recordings won't change.” |
| Save confirmation | **Save preset** · “{open} open, {closed} closed and {finalized} finalized sessions use this preset or an earlier version. Their settings won't change.” |
| Optional current-Open update | **Save and use in this session**; same regeneration warning; calibrated space/time shown before admission |
| Estimate disclaimer | **Illustrative estimate** in browser prototype; actual native Review range/unknown and REV-05 labels after calibration |
| Independent test | **Choose WAV** with native file picker in final application; browser test reads a local WAV without creating a Result or session |

## Implemented numeric rules and outstanding qualification

- The three Sound-detail modes and custom 20/25/30/40/50/60/80/100 ms, 50/75% overlap and 0/100/300 Hz advanced choices are implemented and validated by the current `SpectrogramSettings`/unit tests. Their exact sample-rate-dependent rounding, short-clip handling and image tiers are defined in source. Altering a researcher-visible choice still requires explicit scientific/owner review.
- Current fixed 320×120/1,200×450 tiers, source-time coordinate semantics, cropped-band relative-dB scaling, palette and cache-version contract are implemented. **Still not established** by the tests or existing screenshots: representative field-cohort timing and disk estimates, final physical-device playback/accessibility, installed macOS/Windows performance, and the final owner release qualification. Do not promote unmeasured benchmark rates or a UI screenshot into such evidence.
- The supplied early prototype materials did not contain `docs/design/UX_PARITY_MATRIX.md` or root `docs/design/PROTOTYPE_ACCEPTANCE.md`. Their missing historical sign-off cannot be retrospectively assumed; current [visible native evidence](../../design/evidence/review-correction/README.md) and future native release checks are separate.

**No approval** to change previously fixed F/D/S, J/K/L/Space/arrow/Undo mappings, label semantics, finalized immutability, source data, or shared REV-05. This log is the traceable source of the new decisions; do not silently substitute a later implementation agent's preferences.


## Retained scientific rationale from the implemented investigation

The historical R generator used a 2,000-sample **non-centered, non-border-padded** Hann analysis window at 48 kHz, 1,000-sample hop and 2,048-point FFT tail zero padding. Review instead averages **independent channel powers**, not stereo waveforms, so opposite-phase recordings do not cancel. Spectral power is one-sided unscaled `|rfft|²`; short one/two-sample windows use rectangular weights. Frequency bins have exact Hz centers/edges, and even-window timestamps preserve doubled source-frame centers for half-frame accuracy. Pixel interpolation uses **linear power** before conversion to `10 log10(power / cropped-band peak)`; `[-contrast_db, 0]` is a *relative* scale, not dB SPL or between-recording loudness. Qt overlays labels and axes; cache stores data-only RGB and little-endian float32 dB. No synthetic padding silence is inserted. Changing these scientific/pixel rules requires explicit renderer/cache-version migration and parity tests.

Current v1 tiers are 320×120 thumbnails and 1,200×450 detail images; the selected setting resolves `window_samples`, `hop_samples`, `n_fft`, Nyquist-clamped frequency bounds and `short_clip_window`. Studio's source-frame metadata, immutable cache key, channel policy, session/preset settings snapshots and playback are Studio-owned. The published toolbox `visualization.spectrogram` API owns only pure numerical STFT/raster DSP, **not** CNN/RF Model features. The older 2026-11 research questions about native timing/space calibration were hypotheses, not measured service-level guarantees.
