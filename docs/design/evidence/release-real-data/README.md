# Release screenshots — verified real alpaca hums

This set is intended for release-facing use. It shows BioCall Studio working with the real, human-verified alpaca-hum cohort in `work/manual-review-real-hums`, not the generated RV-09/RV-10 visual-regression fixture.

## Recommended release images

| Story | Screenshot | Real state shown |
|---|---|---|
| Studio | [`00-studio.png`](00-studio.png) | Native launchpad for Train, Detect and Review. |
| Train Collection | [`01-train-collection.png`](01-train-collection.png) | Valid **Verified Alpaca Hums** Collection: 3 real-audio recordings and 24 positive examples. |
| Train Dataset builder | [`02-train-dataset-builder.png`](02-train-dataset-builder.png) | Dataset creation from that valid Collection. |
| Train in progress | [`02a-train-training-in-progress.png`](02a-train-training-in-progress.png) | Live CNN Run at 38% with measured train and validation loss through epoch 15 of 48. |
| Detect Runs | [`03-detect-runs.png`](03-detect-runs.png) | Completed run against the verified source recording. |
| Detect Run | [`04-detect-run.png`](04-detect-run.png) | Completed run details and immutable output. |
| Detect Results | [`05-detect-results.png`](05-detect-results.png) | Original Result with 64 candidates at source recording times. |
| Existing Review folder | [`06-review-data-folder.png`](06-review-data-folder.png) | The populated `work/manual-review-real-hums` Review store opened in place. |
| Review Sessions | [`07-review-sessions.png`](07-review-sessions.png) | The real-hum session, progress and session-management actions. |
| Review Gallery | [`08-review-gallery.png`](08-review-gallery.png) | Populated real spectrogram gallery with source-interval overlays. |
| Review one by one | [`09-review-one-by-one.png`](09-review-one-by-one.png) | Full real spectrogram, axes, detected interval, audio and labeling controls. |
| Spectrogram cache | [`10-review-spectrograms.png`](10-review-spectrograms.png) | Truthful completed state: 64 of 64 spectrograms available. |

## Data provenance

- Source WAV: `work/manual-review-real-hums/source/recordings/verified-real-hums.wav`
- Source SHA-256: `66ae94d75cd08c9e805f6ce7c7c993c9f9a68a8613c9740732fbb65a0b2eac86`
- Human-provenance manifest SHA-256: `8e456d3c941a61e307463e2e6a257ae2e84708cd815529c0773757fed5f5dbd4`
- Detect/Review cohort: 64 candidate intervals whose provenance rows are all human-positive.
- Review session: 18 candidates marked **Call**, 0 marked **Not a call**, and 46 deliberately left **Unreviewed**. No negative labels were invented to make the screenshots look complete.
- Train Collection: three actual-audio source segments and 24 exact positive WAV excerpts derived from the verified cohort. The derived Collection stays under ignored `work/release-evidence/`; only the screenshots and capture provenance are release artifacts.

The complete machine-readable record—including revision, platform, capture dimensions, hashes, counts and per-file dimensions—is [`capture-metadata.json`](capture-metadata.json).

The active-Training frame has its own [`training-capture-metadata.json`](training-capture-metadata.json). At capture time the genuine supervised Worker was **running** in “Train and validate CNN” at 38%. Measured training loss fell from 0.871 at epoch 1 to 0.063 at epoch 15; validation loss ended at 0.641, below its epoch-1 value of 0.694. After capture, the Worker was cancelled through the normal application boundary and its incomplete Model was not published.

## Populated folder behavior

Review now distinguishes between an empty destination and a populated, compatible Review data folder. A compatible folder is validated read-only for its expected top-level layout, bounded regular-file tree, supported SQLite schemas, database integrity and absence of a live owner. After native confirmation with **Use this data**, Review switches to that folder in place and preserves both the previously selected store and the newly selected store. Unrelated, corrupt, symlinked or actively owned folders remain rejected.

The capture exercised that route through the actual Settings folder control. [`06-review-data-folder.png`](06-review-data-folder.png) records the selected existing path and the resulting status: “Review data opened. Existing sessions and settings are ready.” Train and Detect likewise show their populated, contract-valid real example inputs rather than empty showcase states.

## Native capture provenance

- Captured 2026-11-07 from branch `review-release-evidence-real-data`, based on application revision `0a3feb80e9dc1cc3b75f14aef6b06d7aaadcae6a`; the metadata records the tracked working-tree diff hash used for the capture.
- Visible PySide6 application using Qt 6.11.2 on the Cocoa platform, not offscreen Qt or `QWidget.grab()`.
- `QScreen.grabWindow` captured the focused native client area on the Built-in Retina Display at device-pixel ratio 2.0.
- Every frame is 1280×807 logical / 2560×1614 pixels, the maximum clean 1280-wide client viewport available below the macOS menu bar.
- Installed `alp-ui` distribution: `0.1.0a0`.

The evidence can be rebuilt with bounded visible invocations:

```text
.venv/bin/python scripts/prepare_release_examples.py --replace

# Repeat only as needed until the script reports 64 of 64 valid thumbnails.
perl -e 'alarm 120; exec @ARGV' \
  .venv/bin/python scripts/capture_release_screenshots.py \
  --warm-review-cache-only --replace

perl -e 'alarm 120; exec @ARGV' \
  .venv/bin/python scripts/capture_release_screenshots.py --replace

perl -e 'alarm 120; exec @ARGV' \
  .venv/bin/python scripts/capture_release_training_screenshot.py --replace
```

These images establish representative native release material and make the real input provenance auditable. They do not replace installed macOS/Windows packaging qualification, physical playback/accessibility checks, or the owner's final visual approval.
