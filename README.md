<p align="center">
  <img src="assets/branding/on-background/readme-header.png" width="880" alt="BioCall Studio logo and name">
</p>

# BioCall Studio

**Train, detect, and review animal vocalizations in one desktop application.**

BioCall Studio helps bioacoustics researchers work with field recordings—from training models on labeled calls to finding vocalizations in new audio and reviewing the results with spectrograms and playback.

## Explore the workflow

### Train

Create datasets from your recordings and labeled examples, train CNN or Random Forest classifiers, and follow training progress and results.

<img src="docs/design/evidence/release-real-data/02a-train-training-in-progress.png" width="920" alt="BioCall Studio Train workspace showing a CNN training run with progress and loss charts">

### Detect

Analyze recordings with a trained model. Browse detected vocalizations, see where they occur in the source audio, and optionally refine predictions with a Random Forest classifier.

<img src="docs/design/evidence/release-real-data/05-detect-results.png" width="920" alt="BioCall Studio Detect workspace showing detected call candidates in a results table">

### Review

Explore detections in a spectrogram gallery or inspect them individually. Listen to audio, label candidates, manage review sessions, and export reviewed WAV audio with Raven-compatible annotations.

<img src="docs/design/evidence/release-real-data/09-review-one-by-one.png" width="920" alt="BioCall Studio Review workspace showing an alpaca-call spectrogram, playback, and labeling controls">

## Getting started

The first macOS and Windows installers have been built for testing, but **no publicly downloadable BioCall Studio release assets are available yet**. Download links will appear here after a clearly labeled unsigned test pre-release is actually uploaded. For now, use Python **3.11–3.13** and follow the [installation guide](docs/DEVELOPMENT.md#install-from-published-wheels) to run from source.

Launch it from your checkout:

```bash
.venv/bin/python -m biocall_studio
```

## Documentation

[Selecting a Collection](docs/wiki/SELECTING_A_COLLECTION.md) · [Training configuration](docs/wiki/TRAINING_CONFIGURATION.md) · [Example workflow](docs/MANUAL_WORKFLOW.md) · [Screenshot gallery](docs/design/evidence/release-real-data/README.md) · [Development](docs/DEVELOPMENT.md)

## License

**BioCall Studio's original application source is licensed under [GNU GPL-3.0-only](LICENSE).** Upstream dependencies keep their own licenses: see the [third-party redistribution notices](docs/legal/THIRD_PARTY_NOTICES.md) for the GPL-3.0-only scientific toolbox, MIT alp-ui, Qt/PySide6 and bundled-font terms. A testing label does not waive the requirement to provide corresponding source and applicable notices when distributing installers.
