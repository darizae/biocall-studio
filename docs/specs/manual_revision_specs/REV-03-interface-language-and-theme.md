# REV-03 — Plain-language interface and light-only visual pass

**Branch:** `detect-rev03-ui-language`, created from the reviewed local `detect` after REV-02
acceptance. **Predecessor:** REV-02. **Successor:** ST-11. **Status:** proposed copy pending owner
approval; implementation must not begin until the tooltip table below is accepted or revised.

## Outcome and scope

Perform one manual, route-by-route content pass over the native Studio, Train and Detect UI. Keep
the controls, states and explanations a researcher needs to decide or recover; remove decorative
captions, repeated instructions, implementation commentary and machine-like reassurance. The
application is permanently light-themed. This revision does not add Train workflow behavior or
incorporate `UI-pass-revision-spec.md`; its source inputs are only `other-to-dos.txt` and
`detect-revision-notes.txt`.

Use **recordings folder** in Detect-facing copy. `DetectCollectionRef`, manifests, digests,
inventory revisions and publication receipts remain internal contracts and may still appear in
diagnostics or developer documentation, not routine researcher-facing prose. Preserve missing
versus empty, stale versus current, partial versus complete and failed versus cancelled semantics;
shorter copy is not permission to hide a real state.

## Content and visual rules

- Change the Studio launch title from `From recordings to evidence` to
  **From raw audio to corpora**. Remove `CHOOSE A WORKSPACE` and the subtitle `Train models,
  detect candidate calls, and review results in one workspace.` The three workspace cards already
  explain the available choices.
- Delete duplicate prompts such as `Choose a CNN Model published by Train.`, `Choose a Train Model
  folder.`, repeated selected paths and success prose that merely says validation occurred. Show a
  control label, its current value or state once, and one correction when necessary.
- Remove ornamental overlines, captions and Alerts that repeat a card title, nearby control,
  already visible value or invariant the user cannot act on. Keep units, actual counts, state,
  errors, consequences and recovery actions. Do not move deleted clutter wholesale into tooltips.
- Do not address the user as `we`. Avoid developer vocabulary including manifest, checksum,
  runtime structure, schema, digest, publication, immutable, provenance, source-time and Worker in
  ordinary UI copy. When a scientific term is essential, define what it changes in the first
  sentence and put deeper material in help/docs.
- A `HelpHint` exists only for a real concept or decision. It first answers “what is this?” or
  “what happens if I change it?”, uses one or two short sentences, and remains useful through
  hover, keyboard Space/What's This and assistive technology. Subjects use the visible control
  name. Full tutorials route to the Wiki.
- Force `Qt.ColorScheme.Light` and the approved `alp-ui` light theme before constructing any
  widget. Provide no theme preference, dark palette, automatic OS-theme following or isolated
  dark cards. Native macOS evidence must show the same readable light UI while the OS uses dark
  appearance.

Result availability becomes a compact state row rather than a persistent explanatory Alert:

| Result state | Visible status | Action |
|---|---|---|
| Available | No banner | Normal controls remain available. |
| Partial | `Some files failed` (`warning`) | `View file errors` |
| Empty | `No calls found` (`neutral`) | Recording outcomes remain reachable. |
| Stale | `Recordings changed` (`warning`) | `Review recordings` |
| Source unavailable | `Folder unavailable` (`danger`) | `Relink folder` |

## Tooltip approval table — contextual controls

`Decision` is the required implementation action. `Remove` means remove the HelpHint/Qt tooltip,
not merely blank its text. The current inventory contains 28 contextual HelpHints.

| ID | Surface / control | Current text | Decision | Proposed text |
|---|---|---|---|---|
| CTX-01 | Detect · Minimum detection score | Includes windows whose binary target score meets this value. A score is not a certainty percentage; higher values usually return fewer candidates. | Rewrite | Only results at or above this score are kept. Higher scores usually return fewer results. |
| CTX-02 | Detect · Window overlap | Controls how often neighboring portions of a recording are examined. More overlap adds analysis windows and can increase processing time. | Rewrite | How much each scan window overlaps the next. More overlap takes longer. |
| CTX-03 | Detect · Combine nearby candidates | Joins candidate intervals when the source-time gap between them is no greater than the selected value. Overlapping candidates are always joined. | Rewrite | Joins nearby results when the gap between them is no larger than this value. Overlapping results are always joined. |
| CTX-04 | Detect · Detection Model | Detect verifies the Train manifest, checksums, binary class mapping, and runtime structure. Numerical prediction behavior is rechecked before a Run. | Rewrite | A model trained in BioCall Studio that searches your recordings for possible calls. |
| CTX-05 | Detect · Detect Collection | A Detect Collection keeps a stable identity if its recordings folder moves. A different recordings folder creates a different Collection. | Rewrite and rename subject to `Recordings folder` | The folder of WAV files you want to search. BioCall Studio remembers it so you can relink the folder if it moves. |
| CTX-06 | Detect · Recording inclusion | Included recordings are available to analysis. Excluded and undecided recordings are skipped. Inclusion never modifies source files. | Rewrite | Included recordings are searched. Excluded and undecided recordings are skipped. |
| CTX-07 | Detect · Corpus export formats | Snippets preserve each source WAV format. Concatenation is gap-free and is available only when selected PCM formats match; audio is never resampled or downmixed. Raven rows use concatenated output time and retain source frames. | Rewrite | Individual snippets creates one WAV per selected call. Concatenated creates one WAV and a Raven table, and requires matching audio formats. |
| CTX-08 | Detect · Result lineage | A Result is immutable. Candidate selections are saved separately and never change its intervals, scores, or provenance. | Remove | — |
| CTX-09 | Detect · RF refinement | A compatible Random Forest (RF) Model evaluates only the candidate intervals in the selected original Result. Accepted means its target score meets the Model's saved threshold; Rejected means it does not; Could not assess reports a specific feature or duration reason. | Rewrite | Optionally use a Random Forest model to check the calls found by the detection model. The original results stay unchanged. |
| CTX-10 | Detect · Result selection | Selections are saved only for this Result. Changing Results never copies or overwrites another Result's selection. | Rewrite | Selections are saved separately for each result. |
| CTX-11 | Train Collection · Source and positive mapping | Each labeled clip filename names its full recording and includes the clip's start and end time in milliseconds. | Rewrite | Each labeled clip name identifies its full recording and the clip's start and end times. |
| CTX-12 | Train Collection · Collection storage | Trainer stores its own files in .alpaca/ and doesn't copy or change your WAV files. | Rewrite | BioCall Studio stores datasets and models in this folder. It does not copy or change your WAV files. |
| CTX-13 | Dataset Build · Choose positive examples | Choose which recordings to use. Deselecting a recording also excludes its labeled clips and background audio. | Rewrite | Choose which recordings to use. Turning one off also removes its labeled clips and background examples. |
| CTX-14 | Dataset Build · Dataset preview | Preview counts update with these settings. Final counts are checked when the Dataset is built. | Remove | — |
| CTX-15 | Dataset Build · Negative Mining | Choose background clips from selected recordings without using labeled calls or the protected time around them. | Rewrite | Creates background examples from parts of the selected recordings that do not overlap labeled calls. |
| CTX-16 | Dataset Build · Negative amount | Use negatives per positive, or specify a total number of noise Snippets. | Rewrite | Choose a number for each labeled call or one total number for the dataset. |
| CTX-17 | Dataset Build · By Source Recording | Choose background clips in proportion to labeled clips, or spread them evenly across recordings. | Rewrite | Choose whether recordings with more labeled calls supply more background examples, or each recording supplies about the same number. |
| CTX-18 | Dataset Build · Training Split | Keeps clips from the same recording together so they don't appear in both training and validation. | Rewrite | Keeps every clip from one recording in the same group, so training and validation do not share a recording. |
| CTX-19 | Dataset Build · Seed | Using the same recordings, settings, and seed produces the same Dataset. | Rewrite | Use the same seed with the same inputs and settings to build the same dataset again. |
| CTX-20 | Dataset Build · Positive exclusion margin | Adds time before and after each labeled call that cannot be chosen as background. | Rewrite | Keeps background examples this far away from each labeled call. |
| CTX-21 | Dataset detail · train / val Splits | Keeps all clips from a recording in either training or validation. | Rewrite | Every clip from one recording stays in the same group. |
| CTX-22 | Train · Keep computer awake | When this is on, Trainer asks your computer to stay awake while the app is open. Your screen can still turn off. It may use more battery. Closing the lid or putting the computer to sleep yourself can still pause training. | Rewrite | Prevents inactivity sleep while BioCall Studio is open. The display can still turn off, and closing the lid or choosing Sleep still works. |
| CTX-23 | Train · Training Dataset | Choose the Dataset to train. Both model types use its existing training and validation groups. | Rewrite | The dataset supplies the labeled call and background examples used to train this model. |
| CTX-24 | Train · Model families | Choose CNN for spectrogram-based learning or Random Forest for acoustic features. | Rewrite | CNN learns from spectrograms. Random Forest learns from calculated sound features. |
| CTX-25 | Train · Start Training | Checks these settings, then starts training. | Remove | — |
| CTX-26 | Train select · Collection folders | Choose a folder with recordings/ and positives/. Trainer doesn't copy your WAV files. Each labeled clip filename includes when it occurs in the full recording. | Rewrite | Choose a folder containing `recordings/` and `positives/`. BioCall Studio reads the WAV files in place and does not copy them. |
| CTX-27 | Train Wiki · Clip times | Use whole milliseconds. 1000 ms equals 1 second. | Rewrite | Write start and end times in whole milliseconds. 1,000 ms equals 1 second. |
| CTX-28 | Train settings · Collection folders | This is the folder currently open in Trainer. Changing it doesn't move or copy files. | Remove | — |

## Tooltip approval table — training configuration

These 67 rows correspond one-to-one with `TRAINING_CONFIGURATION_FIELDS.json`. Labels remain
unchanged unless a row explicitly requires a label change; the approved proposed text replaces
the `help` value and therefore both HelpHint and accessible description.

| ID | Field | Current text | Decision | Proposed text |
|---|---|---|---|---|
| CFG-01 | Run name | Optional descriptive label for this training Run; the Model receives its own name after training. | Rewrite | A name to help you recognize this training run. You can rename the finished model later. |
| CFG-02 | Log detail | Choose standard or detailed Worker logs; debug does not change scientific results. | Rewrite | Controls how much information is saved in the run log. It does not change training results. |
| CFG-03 | Spectrogram cache | Reuse generated training spectrograms when compatible. Cache location is managed by the Trainer; it never takes a freeform path. | Rewrite | Reuses spectrograms from an earlier compatible run to shorten setup time. |
| CFG-04 | Sequence length (ms) | Fixed audio window duration used for training; choose enough temporal context for the target vocalization. | Rewrite | Length of each audio example used for training, in milliseconds. Use a length that can contain the call. |
| CFG-05 | Maximum epochs | Maximum passes through the training Split; early stopping may finish earlier. | Rewrite | Maximum number of times the model sees the training data. Training may stop earlier when it stops improving. |
| CFG-06 | Batch size | Training Snippets per gradient update. Larger values use more memory. | Rewrite | Number of audio examples processed together. Larger batches use more memory. |
| CFG-07 | Learning rate | Step size of the optimizer. Changes the stability and speed of learning. | Rewrite | Controls how quickly the model changes while learning. Values that are too high can make training unstable. |
| CFG-08 | Training device | Run on CPU or a tested accelerator; unavailable CUDA/MPS selections must be disabled. | Rewrite | Chooses the processor used for training. Unavailable options are disabled. |
| CFG-09 | Sampling rate (Hz) | Sample rate to which audio is converted before spectrogram construction. | Rewrite | Sample rate used to create spectrograms. Audio is converted to this rate for training. |
| CFG-10 | Pre-emphasis | High-frequency emphasis before spectral analysis; preserve in the exported Model. | Rewrite | Boosts higher frequencies before creating the spectrogram. The same value is saved with the model. |
| CFG-11 | FFT window (samples) | Transform window length. Larger windows improve frequency resolution but reduce temporal resolution. | Rewrite | Number of audio samples in each spectral window. Larger windows show frequency more precisely but time less precisely. |
| CFG-12 | FFT hop (samples) | Audio samples between adjacent spectrogram frames; controls time resolution. | Rewrite | Number of audio samples between spectrogram frames. Smaller values show changes over time more closely. |
| CFG-13 | Frequency bins | Number of frequency bins after frequency compression. | Rewrite | Number of frequency bands kept in the spectrogram. |
| CFG-14 | Minimum frequency (Hz) | Lowest spectrogram frequency retained for the classifier. | Rewrite | Lowest frequency included in the spectrogram. |
| CFG-15 | Maximum frequency (Hz) | Highest spectrogram frequency retained; cannot exceed Nyquist frequency. | Rewrite | Highest frequency included in the spectrogram. It cannot be above half the sampling rate. |
| CFG-16 | Frequency compression | Frequency-axis representation: linear, mel, or MFCC; validate compatibility with chosen encoder. | Rewrite | Chooses how frequencies are represented: linear, mel, or MFCC. |
| CFG-17 | Spectrogram minimum dB | Lowest decibel level used to scale or clip the spectrogram representation. | Rewrite | Quietest level retained when scaling the spectrogram. Lower values keep a wider volume range. |
| CFG-18 | Spectrogram reference dB | Reference level for decibel scaling, separate from the normalization mode. | Rewrite | Reference level used when converting the spectrogram to decibels. |
| CFG-19 | Normalization mode | Choose dB-based or min–max normalization; a future consumer must use the exact saved mode. | Rewrite | Chooses how spectrogram values are scaled before training. The choice is saved with the model. |
| CFG-20 | Normalization minimum dB | Minimum dB applied when normalizing the spectrogram. | Rewrite | Quietest decibel value used during spectrogram normalization. |
| CFG-21 | Normalization reference dB | Reference dB applied by the selected normalization procedure. | Rewrite | Reference decibel value used during spectrogram normalization. |
| CFG-22 | Enable augmentation | Apply randomized training-only transformations; never apply them to validation. | Rewrite | Randomly changes training examples to add variety. Validation examples are not changed. |
| CFG-23 | Maximum gain (dB) | Largest randomized loudness increase for training examples. | Rewrite | Largest increase in volume applied during augmentation. |
| CFG-24 | Maximum attenuation (dB) | Largest randomized loudness decrease, expressed as a negative dB value. | Rewrite | Largest decrease in volume applied during augmentation. |
| CFG-25 | Time stretch minimum | Lower bound for training-time playback-speed/time stretching. | Rewrite | Slowest playback-speed change used during augmentation. |
| CFG-26 | Time stretch maximum | Upper bound for training-time playback-speed/time stretching. | Rewrite | Fastest playback-speed change used during augmentation. |
| CFG-27 | Pitch shift minimum | Lower bound for training-only pitch transformation; verify toolbox units. | Rewrite | Lowest pitch change used during augmentation. |
| CFG-28 | Pitch shift maximum | Upper bound for training-only pitch transformation; verify toolbox units. | Rewrite | Highest pitch change used during augmentation. |
| CFG-29 | Noise augmentation SNR A (dB) | One bound of noise-mixing signal-to-noise range. Confirm library direction and ordering before labeling min/max. | Rewrite and rename label to `Noise mix minimum SNR (dB)` after source verification | Lowest signal-to-noise ratio used when mixing background noise. Lower values make the added noise stronger. |
| CFG-30 | Noise augmentation SNR B (dB) | Other bound of the noise-mixing range. Do not silently reorder the upstream defaults. | Rewrite and rename label to `Noise mix maximum SNR (dB)` after source verification | Highest signal-to-noise ratio used when mixing background noise. Higher values make the added noise quieter. |
| CFG-31 | Noise augmentation source | Choose a vetted, readable Collection-local noise source. The user does not type a directory path. | Rewrite | Chooses the background sound mixed into training examples. Only available sources are listed. |
| CFG-32 | ResNet depth | Residual network depth; larger models usually need more memory and training time. | Rewrite | Size of the ResNet model. Deeper models usually take more memory and time to train. |
| CFG-33 | First convolution kernel | Size of the initial CNN convolution window. | Rewrite | Size of the first pattern-detection window in the CNN. |
| CFG-34 | Initial max-pooling mode | 0: no pooling with stride; 1: pooling; 2: no pooling and no added stride. Confirm exact encoder behavior. | Rewrite | Controls early downsampling in the CNN. Keep the preset value unless you are changing the model architecture. |
| CFG-35 | Input channels | Derived from the approved mono spectrogram channel policy; not an independent freeform setting. | Rewrite | Number of spectrogram channels supplied to the model. Set automatically for mono audio. |
| CFG-36 | Classifier pooling | Aggregate encoder features with average or maximum pooling. | Rewrite | Chooses whether the classifier summarizes learned features by their average or maximum value. |
| CFG-37 | Number of output classes | Derived from the immutable binary target/noise Dataset; cannot disagree with its class mapping. | Rewrite | Number of classes the model predicts. Set automatically from the dataset. |
| CFG-38 | Classifier input channels | Computed from the selected encoder output; cannot be independently edited. | Rewrite | Number of learned features sent to the classifier. Set automatically from the selected CNN. |
| CFG-39 | Data-loader workers | Parallel audio loading workers. Zero uses the main process; native packaging may impose a lower limit. | Rewrite | Number of background processes that load training audio. Zero loads audio in the main process. |
| CFG-40 | Adam β1 | Exponential decay for Adam optimizer’s first-moment estimate. | Rewrite | Controls how strongly Adam smooths recent gradient changes. Keep the default unless tuning the optimizer. |
| CFG-41 | LR scheduler patience | Validation patience before reducing learning rate; confirm effective evaluation cadence. | Rewrite | Number of validation checks without improvement before the learning rate is reduced. |
| CFG-42 | LR decay factor | Multiplicative learning-rate reduction when the plateau scheduler triggers. | Rewrite | Amount the learning rate is multiplied by when validation stops improving. |
| CFG-43 | Early-stopping patience | Stop if the monitored validation metric fails to improve for this many effective epochs. | Rewrite | Number of validation checks without improvement before training stops. |
| CFG-44 | Evaluate every N epochs | Frequency of validation passes during CNN training. | Rewrite | Number of training epochs between validation checks. |
| CFG-45 | Validation metric | Metric used to select the best checkpoint and control patience. | Rewrite | Measurement used to choose the best saved model and decide whether training is improving. |
| CFG-46 | Validation metric direction | Whether higher or lower validation scores are better; must match chosen metric. | Rewrite | Tells training whether a higher or lower value is better for the selected validation metric. |
| CFG-47 | Pin data-loader memory | Optional pinned host memory for faster supported accelerator data transfer. | Rewrite | Can speed up transfers to a supported GPU, while using additional system memory. |
| CFG-48 | Trees | Number of trees in the ensemble. More trees require more CPU/memory. | Rewrite | Number of decision trees in the forest. More trees take more time and memory. |
| CFG-49 | Minimum samples per leaf | Minimum samples allowed in a terminal leaf; larger values regularize the forest. | Rewrite | Smallest number of examples allowed in a final tree group. Larger values make the model less specific. |
| CFG-50 | Maximum tree depth | Maximum tree depth or unlimited. The UI may show unlimited as 0, but serialize as null. | Rewrite | Maximum number of levels in each tree. Choose Unlimited to let trees grow without this limit. |
| CFG-51 | Validation decision threshold | Threshold for target-class probability in held-out validation; saved as policy, not inference. | Rewrite | Minimum validation score counted as a target call. The value is saved with the model. |
| CFG-52 | Random seed | Controls reproducible tree bootstrapping and feature subsampling. | Rewrite | Use the same seed with the same data and settings to train the same forest again. |
| CFG-53 | Minimum samples to split | Minimum examples required before an internal tree node can split. | Rewrite | Smallest number of examples a tree group needs before it can divide. |
| CFG-54 | Features per split | Number or proportion of candidate acoustic features considered at each split. Advanced numeric modes require matching validation. | Rewrite | Number of sound features each tree considers when making a split. |
| CFG-55 | Class weighting | Compensates for target/noise imbalance during tree fitting. | Rewrite | Adjusts how strongly the forest learns from target calls and background examples when their counts differ. |
| CFG-56 | Training CPU workers | Number of CPU processes/threads used by the forest; −1 requests all available CPUs, subject to safe cap. | Rewrite | Number of CPU workers used to train the forest. −1 requests all safely available CPUs. |
| CFG-57 | Acoustic feature family | Fixed robust acoustic statistics plus MFCC summaries. Names and ordering are part of Model contract. | Rewrite | Set of calculated sound measurements used by the Random Forest. |
| CFG-58 | Feature sample rate (Hz) | Resample each RF segment to this sample rate before extraction. | Rewrite | Sample rate used when calculating Random Forest sound features. |
| CFG-59 | Minimum feature segment (s) | Short segments must be padded or explicitly rejected. | Rewrite | Shortest audio segment accepted for feature calculation. Shorter segments follow the padding setting. |
| CFG-60 | Pad short segments | Zero-pad shorter segments to the required minimum duration. | Rewrite | Adds silence to segments that are shorter than the minimum feature length. |
| CFG-61 | Padding mode | Current feature extractor uses constant padding; preserve the algorithm choice in export. | Rewrite | Chooses how extra audio is filled when a segment is too short. |
| CFG-62 | Feature FFT window | FFT window size for robust and MFCC statistics. | Rewrite | Number of audio samples in each spectral window used to calculate Random Forest features. |
| CFG-63 | Feature FFT hop | Hop between RF feature frames. | Rewrite | Number of audio samples between feature-analysis frames. |
| CFG-64 | MFCC coefficients | Number of mel-frequency cepstral coefficients summarized. | Rewrite | Number of MFCC sound-shape measurements calculated for each segment. |
| CFG-65 | Include MFCC deltas | Include first/second temporal MFCC differences in the feature vector. | Rewrite | Adds measurements of how MFCC values change over time. |
| CFG-66 | Feature minimum frequency (Hz) | Lower analysis band bound for robust acoustic descriptors. | Rewrite | Lowest frequency used when calculating Random Forest sound features. |
| CFG-67 | Feature maximum frequency (Hz) | Upper band bound for robust descriptors; ensure compatible with Nyquist. | Rewrite | Highest frequency used when calculating Random Forest sound features. It cannot be above half the feature sample rate. |

The two SNR labels may change only after inspecting the exact installed toolbox function and tests.
If the stored A/B ordering does not equal numeric minimum/maximum, correct the owning scientific
contract and this table before implementation; do not relabel the fields optimistically.

## Tooltip approval table — disabled choices

The remaining three actual Qt item tooltips are state-dependent reasons, not HelpHints.

| ID | Choice | Current text | Decision | Proposed text |
|---|---|---|---|---|
| OPT-01 | CUDA device | CUDA is unavailable because it was not detected in this runtime. | Rewrite | CUDA is not available on this computer. |
| OPT-02 | MPS device | MPS isn't available for training yet. | Rewrite | Apple GPU training is not available in this version. |
| OPT-03 | Collection noise source | Collection noise isn't available for augmentation yet. | Rewrite | Using Collection audio as augmentation noise is not available in this version. |

## TDD and visual approval

- `IT-UI-006` — the real Studio launchpad uses only the approved title and workspace-card copy,
  installs one light theme even under native dark OS appearance, exposes no theme control and
  remains readable at normal/compact widths and 100%/150% scaling.
- `IT-TRAIN-015` — instantiate every Train page and all 67 configuration fields with real Qt;
  assert each approved contextual/configuration/disabled-choice tooltip, keyboard HelpHint access,
  accessible subject/description, removed hints and absence of rejected visible copy.
- `IT-DET-024` — instantiate every Detect route/state from REV-02; assert its approved HelpHints,
  `recordings folder` terminology, concise Model/Result states and actions, removal of duplicate
  prompts and alerts, and retained missing/empty/stale/partial distinctions.

Add the indexed Qt cases before changing copy. Maintain a small audit that compares the approved
IDs above with the 28 contextual HelpHint call sites, 67 configuration records and three dynamic
item tooltips; additions or omissions fail with the owning surface/control name. The audit is a
completeness check, not a runtime parser or a second copy registry.

Run focused Qt cases during implementation, then all feasible ordinary unit/integration suites,
ruff, test-ID audit and `git diff --check`. Capture native normal/compact screenshots of the
launchpad and representative Train/Detect routes, including an incompatible Model and each compact
Result state. Record macOS dark-appearance evidence while the application remains light. Do not
claim unexecuted Windows, installer, soak or ST-11 whole-Studio qualification.

## Exit gate

First obtain owner approval or explicit edits for all 98 tooltip rows. Close only when approved
copy is present once, rejected clutter is absent, every real state remains actionable and
accessible, no dark UI is reachable, native evidence is reviewed, and the full feasible checks
pass. Commit on the revision branch, integrate locally into `detect` only after owner approval,
never push, and leave ST-11 blocked until its own gate is opened.
