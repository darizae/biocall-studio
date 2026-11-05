# RV-05 native-widget background evidence

These PySide6 captures exercise the RV-05 Review workspace at normal (`1180×720`)
and compact (`700×720`) logical widths:

- One-by-one view with a genuine generated-WAV spectrogram, axes, detected interval,
  playback, labels, progress, navigation, and fixed-shortcut actions.
- Gallery with checksum-verified generated thumbnails.
- Searchable List in the compact layout.
- The protected Default preset and the eight-selector Settings page.

The indexed `IT-REVW-007` test writes these images only when
`BIOCALL_RV05_EVIDENCE_DIR` points to this directory. The same test asserts source
WAV and label non-mutation, cache checksums, preset revision switching, bounded saved
examples, keyboard scope, accessibility surfaces, and normal/compact state.

Capture command:

```text
BIOCALL_RV05_EVIDENCE_DIR=docs/design/evidence/rv-05-background \
  .venv/bin/python scripts/run_tests.py background \
  tests/integration/test_review_workspace.py -q
```

This is invisible offscreen Qt evidence from the owner workstation, as required for
ordinary tests. It is not a visible Cocoa/device-interaction claim. A visible native
capture remains an owner-run approval gate because starting it would interrupt the
interactive desktop.

## Researcher-visible copy delta for owner approval

| Surface | New/changed copy | Why it appears |
|---|---|---|
| Review navigation | **Spectrograms** · **Settings** · **Back to Review** | Opens cache controls, then preset configuration, and returns without losing session state. |
| Preset actions | **New preset** · **Edit** · **Rename** · **Save changes** · **Delete** · **Save preset** · **Save and use in this session** · **Change preset** | Implements protected Default, editable named presets, future-only saves, and explicit Open-session switching. |
| Preset consequences | “{open} open, {closed} closed and {finalized} finalized sessions use this preset or an earlier version. Their settings won't change.” · “Delete this preset and its saved examples? Session settings won't change.” · “Change {old} to {new}? {count} spectrograms will need to be generated. Your labels won't change.” | Makes revision, deletion, cache, and label effects explicit before committing. |
| Cache availability | “Checking spectrogram availability…” · “{cached} of {total} spectrograms available” | Reports verified cache state while the bounded scan runs and after it finishes. |
| Preset preview | **Test WAV** · **Compare** · **Save example** · “Preview ready.” · **Saved example** · **Saved example · earlier version** | Supports transient WAV comparison and explicit derivative-only examples without retaining the WAV path. |
| Advanced override | “Overridden by Exact sound window.” | Explains why Sound detail is disabled while a custom window is active. |
| New failure recovery | “Couldn't check spectrogram storage. Try again.” · “Couldn't save your changes. Try again.” · “Couldn't delete this preset. Try again.” · “Couldn't save this example. Try again.” | Gives a compact retry action without exposing storage or database implementation details. |
| Selector HelpHints | “Uses the Sound detail choice or a precise sound window for this preset.” · “Higher overlap adds more time slices without changing pitch resolution.” · “Hides low rumble below this frequency and may also hide low calls.” | Researcher-facing explanations for the three Advanced controls. |

All other session, label, shortcut, cache, storage, finalization, missing/changed
recording, and renderer wording is the frozen RV-05 inventory.
