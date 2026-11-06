# Review correction — committed screenshot baseline

These files are **unchanged PNG byte-for-byte copies** of existing tracked HTML prototype screenshots and existing RV-05 offscreen Qt screenshots, from the `review` branch at `38fd5c5746d52cfcc722cc155c2ee412f2eac9db` (2026-11-06). They were copied by their exact Git blob SHA; **not freshly generated**, and no actual visible/native screenshot has been captured in this documentation commit.

**Purpose:** next agents must compare genuine design targets **as images**, not infer fidelity from CSS or a button inventory, then commit the real PySide6 screenshots under a future `native-after/` folder after authorized visible testing and owner review.

| Screen | Prototype target | Existing offscreen native-before (if available) | Required visible Qt-after |
|---|---|---|---|
| Launchpad | `targets/00-studio.png` | none | `native-after/00-studio.png` |
| Choose Result | `targets/01-choose-result.png` | none | `native-after/01-choose-result.png` |
| Sessions | `targets/02-sessions.png` | none | `native-after/02-sessions.png` |
| Gallery | `targets/03-gallery.png` | `native-before/gallery.png` | `native-after/03-gallery.png` |
| List | `targets/04-list.png` | `native-before/list-compact.png` | `native-after/04-list.png` |
| One by one | `targets/05-one-by-one.png` | `native-before/one-by-one.png` | `native-after/05-one-by-one.png` |
| Spectrograms | `targets/06-spectrograms.png` | none | `native-after/06-spectrograms.png` |
| Finalize warning | `targets/07-finalize.png` | none | `native-after/07-finalize.png` |
| Export | `targets/08-export.png` | none | `native-after/08-export.png` |
| Compact Gallery | `targets/09-compact-gallery.png` | none | `native-after/09-compact-gallery.png` |
| Compact One by one | `targets/10-compact-one-by-one.png` | none | `native-after/10-compact-one-by-one.png` |
| Narrow One by one | `targets/11-narrow-one-by-one.png` | none | `native-after/11-narrow-one-by-one.png` |
| Settings/presets | Historical prototype screenshot not in image set (inspect HTML source) | `native-before/settings.png` | `native-after/12-settings.png` |
| New deletion and directory controls | **Owner-required additions not present in old prototype** | none | `native-after/13-delete-session.png` and `14-review-data-folder.png` |

**Fidelity rules:** reproduce the **left sidebar** (Sessions, Choose Result, Review, Spectrograms, Exports), hierarchy, spacing, cards, navigation and spectrogram emphasis. The latest owner instruction demands consistent Open Train/Detect/Review button variants, even though the old prototype emphasized Review; document this deliberate exception. Do not copy prototype's illustrative banner, fictitious WAVs as scientific proof, or demo-only controls.

**Required later capture:** run the *actual* PySide6 application in visible mode **only when the owner authorizes interruption of their desktop**. Capture matching windows at appropriate dimensions and available screen scale, record OS/Qt version, Git SHAs and fixture provenance, add PNGs under `native-after/` and a screen-by-screen target-versus-native comparison with deviations/fixes. Headless/offscreen screenshots are historical regression evidence, **not final visual approval**. New Settings data-directory and Delete session screens require separate owner approval as sensible minimal extensions to the prototype.
