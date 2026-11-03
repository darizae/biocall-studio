# Manual end-to-end trial

This is the shortest genuine BioCall Studio Train workflow for a person arriving with a
Collection. It uses real PCM WAV files and executes the real Dataset, Worker, CNN, Random Forest,
Run and Model code paths. The supplied audio signals are deterministic and synthetic, not field
recordings, so the resulting metrics prove that the workflow ran; they do **not** demonstrate a
scientifically useful animal-call detector.

## Prepare a fresh local Collection

From the repository root, create a disposable user Collection outside the tracked test fixtures:

```bash
.venv/bin/python scripts/generate_example_collection.py \
  --write \
  --output "work/manual-e2e/Forest Dawn – Grünspecht"

(
  cd "work/manual-e2e/Forest Dawn – Grünspecht"
  shasum -a 256 positives/*.wav recordings/*.wav
) > work/manual-e2e/input-SHA256SUMS
```

The generator refuses to overwrite existing WAVs. To repeat the trial from scratch, use a new
output folder name. Do not point the app at `tests/data/example_collection/`: a real session writes
versioned `.alpaca/` artifacts beside the selected inputs, and the tracked fixture should stay
clean.

The generated Collection is deliberately small:

```text
Forest Dawn – Grünspecht/                 ← select this folder
├── recordings/
│   ├── REC_A.wav                            # 8 s
│   ├── REC_B.wav                            # 8 s
│   └── REC_C.wav                            # 8 s
└── positives/
    ├── REC_A__start-01000ms__end-02000ms__callA.wav
    ├── REC_B__start-03000ms__end-04000ms__callB.wav
    └── REC_C__start-05000ms__end-06000ms__callC.wav
```

Each one-second positive is an exact source-time excerpt. Three distinct Source Recording groups
are enough to create nonempty `train` and `val` Splits containing both `target` and mined `noise`
Snippets.

## Start as a first-time source user

Use an isolated suite application-data root so this trial does not replace your usual Train or
Detect bindings:

```bash
.venv/bin/python -m biocall_studio \
  --settings-dir work/manual-e2e/app-settings
```

Then follow the native UI:

1. On **Select Collection**, choose
   `work/manual-e2e/Forest Dawn – Grünspecht`. Wait for validation. The Collection view should show
   **3 recordings**, **3 positives**, **24 seconds** and no issues.
2. Choose **Build Dataset**. Keep all recordings selected. For a small but representative build,
   use **2 negatives per positive**, **Proportional to positives**, **80% train / 20% val**,
   **seed 42**, **Keep class ratio across Splits**, and a **0.25 s** exclusion margin. The preview
   should show **3 target + 6 noise = 9 Snippets**. Build and wait for the completed Run, then open
   the Dataset.
3. Choose **Train Model** and select **CNN · Spectrogram**. Use the small smoke settings below,
   then **Save as…** with a name such as `Manual smoke · CNN`. Start training, accept or edit the
   Model display name, and wait for the Run to finish. Inspect the measured train/validation loss
   and open the published Model.

   | CNN section | Set these values |
   |---|---|
   | Main form | Sequence length `250`; Maximum epochs `1`; Batch size `2`; Learning rate `0.0001`; Training device `CPU` |
   | More settings → Spectrogram | Sampling rate `16000`; FFT window `256`; FFT hop `64`; Frequency bins `64`; Minimum frequency `100`; Maximum frequency `7000` |
   | More settings → Optimization | Data-loader workers `0`; Early-stopping patience `2`; Evaluate every N epochs `1`; Pin data-loader memory `Off` |

4. Return to that Dataset and choose **Train Model** again. Select **Random Forest · Acoustic
   features**, use the smoke settings below, then save as `Manual smoke · RF`. Start training,
   wait for completion, inspect the measured feature importance and open the published Model.

   | Random Forest section | Set these values |
   |---|---|
   | Main form | Trees `10`; Minimum samples per leaf `1` |
   | More settings → Basics | Validation decision threshold `0.55` |
   | More settings → Forest | Random seed `42`; Training CPU workers `1` |
   | More settings → Features | Feature sample rate `8000`; Minimum feature segment `0.25`; Feature FFT window `256`; Feature FFT hop `64`; MFCC coefficients `4`; Feature minimum frequency `100`; Feature maximum frequency `3500` |

5. Quit the app only after no Run is active. Launch it again with the same command. Open **Datasets**,
   **Runs**, and **Models** and reopen both Models. The Collection now contains immutable outputs
   under `.alpaca/`. Verify that its six input WAV files are unchanged:

   ```bash
   (cd "work/manual-e2e/Forest Dawn – Grünspecht" && \
     shasum -a 256 -c ../input-SHA256SUMS)
   ```

The endpoint is two structurally verified training Models with their Dataset, Runs, measurements,
configuration and provenance. Return to the Studio launchpad to use either Model in the Detect
workflow; Train and Detect keep separate state inside the same application.

## Check storage before writing output

Dataset Build, CNN and Random Forest Training, candidate detection, RF call checking, and corpus
export show a compact **Storage** section before they start. **Estimated output** describes the
finished files. **Space needed while running** also includes bounded staging, request, Run and log
overhead that may be removed after completion. A range means the output depends on the recordings,
Model structure, settings or candidates that survive detection; it is not a precise prediction.

Displayed KB, MB, GB and TB values use binary units: 1 KB = 1,024 bytes, 1 MB = 1,024 KB, and so
on. Estimates round upward so a positive amount is never shown as zero. BioCall Studio checks each
destination filesystem separately and keeps a reserve of the larger of 512 MB or 10% of estimated
peak use. Known free space below **peak + one reserve** is insufficient. Space from **peak + one
reserve** up to **peak + two reserves** is tight and requires confirmation; at or above **peak +
two reserves** is ready. An unknown capacity also requires confirmation. This deliberately keeps
the 512 MB floor on small volumes instead of making a small percentage look safe. The capacity is
checked again at start, but it is not reserved; other applications can still consume disk space.
Normal disk-full handling and private-staging cleanup remain active independently of the estimate.

## What this represents for actual field data

A researcher supplies original recordings in `recordings/` and manually exported known-call clips
in `positives/`. A positive filename records the clip's start and end in its Source Recording. The
Trainer validates those inputs, mines unlabeled source-time as `noise`, keeps whole recordings in
one Split to avoid leakage, publishes an immutable Dataset, and trains one or both Model families.
See [Selecting a Collection](wiki/SELECTING_A_COLLECTION.md) before replacing this sample with
field recordings.
