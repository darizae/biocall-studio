# Training a Model — settings and saved configurations

This user-facing guide describes every training control in the Trainer. Open it from **Train Model → Model configuration → Read training settings guide**, or from the help link alongside an individual field. CNN and Random Forest both train using the same immutable Dataset, but they transform audio differently. The Settings dialog in a future installer must not introduce new filesystem-path fields from the reference training script.

## How to choose a model

A **CNN** learns patterns from a spectrogram: a picture of audio frequencies over time. A **Random Forest** first computes numerical acoustic features for each Snippet, then learns decision-tree rules. Both produce a Model and validation metrics, but RF has no CNN-style epochs or loss curve.

**Start with the default configuration** and a valid Dataset. The main panel deliberately presents only a few important controls: for CNN, sequence length, maximum epochs, batch size, learning rate and training device; for RF, number of trees, maximum depth and minimum samples per leaf. An optional Run name is common to both families. Open **More settings** to inspect or change the complete additional configuration in small, collapsed categories. Each detailed row shows **Current**, **Default**, and **Suggested starting value**. For now, the suggested starting value is the same as the backend default; that makes it a reproducible baseline, **not a guarantee of best accuracy**. If the Dataset or available hardware makes a default unsuitable, the app explains why rather than silently changing it. Settings computed by the app are labeled **Automatically determined**. You may reset an individual setting or the detailed group to defaults; closing More settings never discards edits. Use the main controls for the first experiment, then open More settings only when you have a reason to tune them. Review validation warnings before running. The training Run stores an immutable snapshot; later changes to a preset do not change a finished Model.

## Saved configurations

Name and save a configuration to reuse hyperparameters later. A saved configuration is a **preset**, not a trained Model or a Dataset. Loading a preset fills its model-family fields; it does not replace the selected Dataset, select files or create a Run. Presets are stored in the local app user-data area, contain no source paths, and can be renamed, duplicated or deleted; deletion does not modify Runs or Models. Loading an incompatible preset produces a clear warning and requires explicit resolution. See [saved configuration rules](../science/TRAINING_PRESETS.md).

## Defaults and recommendations

Each setting below lists the **backend default**. The current proposed **recommended starting value** for every editable setting is **that same default**; it is a tested-API-aligned baseline *subject to compatibility validation*, not a dataset-specific or research-backed recommendation. **More settings** labels it explicitly as “Suggested starting value (backend default)”. When an item is derived from Dataset/model structure, its recommendation is **Automatically determined**. Refer to each parameter's explanation and compatibility constraints rather than assuming a default is ideal for your audio. The exact typed baseline and recommendation provenance appear in [the field index](../science/TRAINING_CONFIGURATION_FIELDS.json).

## Every setting, with units and defaults

The HelpHint beside each field is a short version of the explanation below. Clicking its Wiki link opens the exact heading.

### Common settings

#### Identity

##### Run name (`run_name`)

<a id="run-name"></a>

Optional descriptive label for this training Run; the Model receives its own name after training. Default: ``. This setting is validated before training and saved in the immutable Run record.

#### Execution

##### Log detail (`logging_level`)

<a id="logging-level"></a>

Choose standard or detailed Worker logs; debug does not change scientific results. Default: `info`, supported values: `info`, `debug`. This setting is validated before training and saved in the immutable Run record.

##### Spectrogram cache (`spectrogram_cache`)

<a id="spectrogram-cache"></a>

Reuse generated training spectrograms when compatible. Cache location is managed by the Trainer; it never takes a freeform path. Default: `False`. This setting is validated before training and saved in the immutable Run record.

### CNN settings

#### Basics

##### Sequence length (ms) (`sequence_length_ms`)

<a id="sequence-length-ms"></a>

Fixed audio window duration used for training; choose enough temporal context for the target vocalization. Default: `400`. This setting is validated before training and saved in the immutable Run record.

##### Maximum epochs (`training.max_epochs`)

<a id="training-max-epochs"></a>

Maximum passes through the training Split; early stopping may finish earlier. Default: `500`. This setting is validated before training and saved in the immutable Run record.

##### Batch size (`training.batch_size`)

<a id="training-batch-size"></a>

Training Snippets per gradient update. Larger values use more memory. Default: `16`. This setting is validated before training and saved in the immutable Run record.

##### Learning rate (`training.learning_rate`)

<a id="training-learning-rate"></a>

Step size of the optimizer. Changes the stability and speed of learning. Default: `1e-05`. This setting is validated before training and saved in the immutable Run record.

##### Training device (`device`)

<a id="device"></a>

Run on CPU or a tested accelerator; unavailable CUDA/MPS selections must be disabled. Default: `auto`, supported values: `auto`, `cpu`, `cuda`, `mps`. This setting is validated before training and saved in the immutable Run record.

#### Spectrogram

##### Sampling rate (Hz) (`spectrogram.sample_rate`)

<a id="spectrogram-sample-rate"></a>

Sample rate to which audio is converted before spectrogram construction. Default: `44100`. This setting is validated before training and saved in the immutable Run record.

##### Pre-emphasis (`spectrogram.preemphasis`)

<a id="spectrogram-preemphasis"></a>

High-frequency emphasis before spectral analysis; preserve in the exported Model. Default: `0.98`. This setting is validated before training and saved in the immutable Run record.

##### FFT window (samples) (`spectrogram.n_fft`)

<a id="spectrogram-n-fft"></a>

Transform window length. Larger windows improve frequency resolution but reduce temporal resolution. Default: `4096`. This setting is validated before training and saved in the immutable Run record.

##### FFT hop (samples) (`spectrogram.hop_length`)

<a id="spectrogram-hop-length"></a>

Audio samples between adjacent spectrogram frames; controls time resolution. Default: `441`. This setting is validated before training and saved in the immutable Run record.

##### Frequency bins (`spectrogram.n_freq_bins`)

<a id="spectrogram-n-freq-bins"></a>

Number of frequency bins after frequency compression. Default: `256`. This setting is validated before training and saved in the immutable Run record.

##### Minimum frequency (Hz) (`spectrogram.f_min`)

<a id="spectrogram-f-min"></a>

Lowest spectrogram frequency retained for the classifier. Default: `500`. This setting is validated before training and saved in the immutable Run record.

##### Maximum frequency (Hz) (`spectrogram.f_max`)

<a id="spectrogram-f-max"></a>

Highest spectrogram frequency retained; cannot exceed Nyquist frequency. Default: `10000`. This setting is validated before training and saved in the immutable Run record.

##### Frequency compression (`spectrogram.freq_compression`)

<a id="spectrogram-freq-compression"></a>

Frequency-axis representation: linear, mel, or MFCC; validate compatibility with chosen encoder. Default: `linear`, supported values: `linear`, `mel`, `mfcc`. This setting is validated before training and saved in the immutable Run record.

##### Spectrogram minimum dB (`spectrogram.min_level_db`)

<a id="spectrogram-min-level-db"></a>

Lowest decibel level used to scale or clip the spectrogram representation. Default: `-100`. This setting is validated before training and saved in the immutable Run record.

##### Spectrogram reference dB (`spectrogram.ref_level_db`)

<a id="spectrogram-ref-level-db"></a>

Reference level for decibel scaling, separate from the normalization mode. Default: `20`. This setting is validated before training and saved in the immutable Run record.

#### Normalization

##### Normalization mode (`normalization.mode`)

<a id="normalization-mode"></a>

Choose dB-based or min–max normalization; a future consumer must use the exact saved mode. Default: `db`, supported values: `db`, `min_max`. This setting is validated before training and saved in the immutable Run record.

##### Normalization minimum dB (`normalization.min_level_db`)

<a id="normalization-min-level-db"></a>

Minimum dB applied when normalizing the spectrogram. Default: `-100`. This setting is validated before training and saved in the immutable Run record.

##### Normalization reference dB (`normalization.ref_level_db`)

<a id="normalization-ref-level-db"></a>

Reference dB applied by the selected normalization procedure. Default: `20`. This setting is validated before training and saved in the immutable Run record.

#### Augmentation

##### Enable augmentation (`augmentation.enabled`)

<a id="augmentation-enabled"></a>

Apply randomized training-only transformations; never apply them to validation. Default: `False`. This setting is validated before training and saved in the immutable Run record.

##### Maximum gain (dB) (`augmentation.amplitude_increase_db`)

<a id="augmentation-amplitude-increase-db"></a>

Largest randomized loudness increase for training examples. Default: `3`. This setting is validated before training and saved in the immutable Run record.

##### Maximum attenuation (dB) (`augmentation.amplitude_decrease_db`)

<a id="augmentation-amplitude-decrease-db"></a>

Largest randomized loudness decrease, expressed as a negative dB value. Default: `-6`. This setting is validated before training and saved in the immutable Run record.

##### Time stretch minimum (`augmentation.time_stretch_from`)

<a id="augmentation-time-stretch-from"></a>

Lower bound for training-time playback-speed/time stretching. Default: `0.5`. This setting is validated before training and saved in the immutable Run record.

##### Time stretch maximum (`augmentation.time_stretch_to`)

<a id="augmentation-time-stretch-to"></a>

Upper bound for training-time playback-speed/time stretching. Default: `2.0`. This setting is validated before training and saved in the immutable Run record.

##### Pitch shift minimum (`augmentation.pitch_shift_from`)

<a id="augmentation-pitch-shift-from"></a>

Lower bound for training-only pitch transformation; verify toolbox units. Default: `0.5`. This setting is validated before training and saved in the immutable Run record.

##### Pitch shift maximum (`augmentation.pitch_shift_to`)

<a id="augmentation-pitch-shift-to"></a>

Upper bound for training-only pitch transformation; verify toolbox units. Default: `1.5`. This setting is validated before training and saved in the immutable Run record.

##### Noise augmentation SNR A (dB) (`augmentation.noise_min_snr`)

<a id="augmentation-noise-min-snr"></a>

One bound of noise-mixing signal-to-noise range. Confirm library direction and ordering before labeling min/max. Default: `12`. This setting is validated before training and saved in the immutable Run record.

##### Noise augmentation SNR B (dB) (`augmentation.noise_max_snr`)

<a id="augmentation-noise-max-snr"></a>

Other bound of the noise-mixing range. Do not silently reorder the upstream defaults. Default: `-3`. This setting is validated before training and saved in the immutable Run record.

##### Noise augmentation source (`augmentation.noise_source`)

<a id="augmentation-noise-source"></a>

Choose a vetted, readable Collection-local noise source. The user does not type a directory path. Default: `none`, supported values: `none`, `collection-selected`. This setting is validated before training and saved in the immutable Run record.

#### Architecture

##### ResNet depth (`encoder.resnet_size`)

<a id="encoder-resnet-size"></a>

Residual network depth; larger models usually need more memory and training time. Default: `18`, supported values: `18`, `34`, `50`, `101`, `152`. This setting is validated before training and saved in the immutable Run record.

##### First convolution kernel (`encoder.conv_kernel_size`)

<a id="encoder-conv-kernel-size"></a>

Size of the initial CNN convolution window. Default: `7`, supported values: `3`, `5`, `7`, `9`. This setting is validated before training and saved in the immutable Run record.

##### Initial max-pooling mode (`encoder.max_pool`)

<a id="encoder-max-pool"></a>

0: no pooling with stride; 1: pooling; 2: no pooling and no added stride. Confirm exact encoder behavior. Default: `1`, supported values: `0`, `1`, `2`. This setting is validated before training and saved in the immutable Run record.

##### Input channels (`encoder.input_channels`)

<a id="encoder-input-channels"></a>

Derived from the approved mono spectrogram channel policy; not an independent freeform setting. Default: `1`. This setting is derived and cannot be edited.

##### Classifier pooling (`classifier.pooling`)

<a id="classifier-pooling"></a>

Aggregate encoder features with average or maximum pooling. Default: `avg`, supported values: `avg`, `max`. This setting is validated before training and saved in the immutable Run record.

##### Number of output classes (`classifier.num_classes`)

<a id="classifier-num-classes"></a>

Derived from the immutable **binary single-label** target/noise Dataset; it is always exactly `2` and cannot disagree with the two-class map. One Snippet belongs to `target` **or** `noise`, never both. This setting is derived and cannot be edited. Multi-label and multi-class modes available in scientific libraries are **not supported** in BioCall Studio Train; see [binary scope](../science/BINARY_CLASSIFICATION_CONTRACT.md).

##### Classifier input channels (`classifier.input_channels`)

<a id="classifier-input-channels"></a>

Computed from the selected encoder output; cannot be independently edited. Default: `derived`. This setting is derived and cannot be edited.

#### Optimization

##### Data-loader workers (`training.num_workers`)

<a id="training-num-workers"></a>

Parallel audio loading workers. Zero uses the main process; native packaging may impose a lower limit. Default: `4`. This setting is validated before training and saved in the immutable Run record.

##### Adam β1 (`training.beta1`)

<a id="training-beta1"></a>

Exponential decay for Adam optimizer’s first-moment estimate. Default: `0.5`. This setting is validated before training and saved in the immutable Run record.

##### LR scheduler patience (`training.lr_patience_epochs`)

<a id="training-lr-patience-epochs"></a>

Validation patience before reducing learning rate; confirm effective evaluation cadence. Default: `8`. This setting is validated before training and saved in the immutable Run record.

##### LR decay factor (`training.lr_decay_factor`)

<a id="training-lr-decay-factor"></a>

Multiplicative learning-rate reduction when the plateau scheduler triggers. Default: `0.5`. This setting is validated before training and saved in the immutable Run record.

##### Early-stopping patience (`training.early_stopping_patience_epochs`)

<a id="training-early-stopping-patience-epochs"></a>

Stop if the monitored validation metric fails to improve for this many effective epochs. Default: `20`. This setting is validated before training and saved in the immutable Run record.

##### Evaluate every N epochs (`training.epochs_per_eval`)

<a id="training-epochs-per-eval"></a>

Frequency of validation passes during CNN training. Default: `2`. This setting is validated before training and saved in the immutable Run record.

##### Validation metric (`training.val_metric`)

<a id="training-val-metric"></a>

Metric used to select the best checkpoint and control patience. Default: `accuracy`, supported values: `accuracy`, `f1`, `loss`. This setting is validated before training and saved in the immutable Run record.

##### Validation metric direction (`training.val_metric_mode`)

<a id="training-val-metric-mode"></a>

Whether higher or lower validation scores are better; must match chosen metric. Default: `max`, supported values: `max`, `min`. This setting is validated before training and saved in the immutable Run record.

##### Pin data-loader memory (`training.pin_memory`)

<a id="training-pin-memory"></a>

Optional pinned host memory for faster supported accelerator data transfer. Default: `True`. This setting is validated before training and saved in the immutable Run record.

### RF settings

#### Basics

##### Trees (`n_estimators`)

<a id="n-estimators"></a>

Number of trees in the ensemble. More trees require more CPU/memory. Default: `800`. This setting is validated before training and saved in the immutable Run record.

##### Minimum samples per leaf (`min_samples_leaf`)

<a id="min-samples-leaf"></a>

Minimum samples allowed in a terminal leaf; larger values regularize the forest. Default: `2`. This setting is validated before training and saved in the immutable Run record.

##### Maximum tree depth (`max_depth`)

<a id="max-depth"></a>

Maximum tree depth or unlimited. The UI may show unlimited as 0, but serialize as null. Default: `None`. This setting is validated before training and saved in the immutable Run record.

##### Validation decision threshold (`rf_threshold`)

<a id="rf-threshold"></a>

Threshold for target-class probability in held-out validation; saved as policy, not inference. Default: `0.6`. This setting is validated before training and saved in the immutable Run record.

#### Forest

##### Random seed (`random_state`)

<a id="random-state"></a>

Controls reproducible tree bootstrapping and feature subsampling. Default: `1337`. This setting is validated before training and saved in the immutable Run record.

##### Minimum samples to split (`min_samples_split`)

<a id="min-samples-split"></a>

Minimum examples required before an internal tree node can split. Default: `2`. This setting is validated before training and saved in the immutable Run record.

##### Features per split (`max_features`)

<a id="max-features"></a>

Number or proportion of candidate acoustic features considered at each split. Advanced numeric modes require matching validation. Default: `sqrt`, supported values: `sqrt`, `log2`, `all`. This setting is validated before training and saved in the immutable Run record.

##### Class weighting (`class_weight`)

<a id="class-weight"></a>

Compensates for target/noise imbalance during tree fitting. Default: `balanced`, supported values: `balanced`, `balanced_subsample`, `none`. This setting is validated before training and saved in the immutable Run record.

##### Training CPU workers (`n_jobs`)

<a id="n-jobs"></a>

Number of CPU processes/threads used by the forest; −1 requests all available CPUs, subject to safe cap. Default: `-1`. This setting is validated before training and saved in the immutable Run record.

#### Features

##### Acoustic feature family (`feature_family`)

<a id="feature-family"></a>

Fixed robust acoustic statistics plus MFCC summaries. Names and ordering are part of Model contract. Default: `robust-mfcc`. This setting is derived and cannot be edited.

##### Feature sample rate (Hz) (`feature_config.sample_rate_hz`)

<a id="feature-config-sample-rate-hz"></a>

Resample each RF segment to this sample rate before extraction. Default: `48000`. This setting is validated before training and saved in the immutable Run record.

##### Minimum feature segment (s) (`feature_config.min_duration_s`)

<a id="feature-config-min-duration-s"></a>

Short segments must be padded or explicitly rejected. Default: `0.5`. This setting is validated before training and saved in the immutable Run record.

##### Pad short segments (`feature_config.pad_short_segments`)

<a id="feature-config-pad-short-segments"></a>

Zero-pad shorter segments to the required minimum duration. Default: `True`. This setting is validated before training and saved in the immutable Run record.

##### Padding mode (`feature_config.pad_mode`)

<a id="feature-config-pad-mode"></a>

Current feature extractor uses constant padding; preserve the algorithm choice in export. Default: `constant`. This setting is derived and cannot be edited.

##### Feature FFT window (`feature_config.n_fft`)

<a id="feature-config-n-fft"></a>

FFT window size for robust and MFCC statistics. Default: `4096`. This setting is validated before training and saved in the immutable Run record.

##### Feature FFT hop (`feature_config.hop_length`)

<a id="feature-config-hop-length"></a>

Hop between RF feature frames. Default: `2048`. This setting is validated before training and saved in the immutable Run record.

##### MFCC coefficients (`feature_config.n_mfcc`)

<a id="feature-config-n-mfcc"></a>

Number of mel-frequency cepstral coefficients summarized. Default: `13`. This setting is validated before training and saved in the immutable Run record.

##### Include MFCC deltas (`feature_config.include_deltas`)

<a id="feature-config-include-deltas"></a>

Include first/second temporal MFCC differences in the feature vector. Default: `True`. This setting is validated before training and saved in the immutable Run record.

##### Feature minimum frequency (Hz) (`feature_config.fmin_hz`)

<a id="feature-config-fmin-hz"></a>

Lower analysis band bound for robust acoustic descriptors. Default: `50.0`. This setting is validated before training and saved in the immutable Run record.

##### Feature maximum frequency (Hz) (`feature_config.fmax_hz`)

<a id="feature-config-fmax-hz"></a>

Upper band bound for robust descriptors; ensure compatible with Nyquist. Default: `4500.0`. This setting is validated before training and saved in the immutable Run record.

## Understanding interdependent settings

- **Frequency band vs sample rate:** the upper spectral frequency cannot exceed half of the effective sample rate (the Nyquist limit). FFT size, hop, bins and sequence length must also produce input dimensions accepted by the selected model.
- **Normalization:** a spectrogram's decibel reference is related to but not interchangeable with the normalization method. The exported Model must preserve the exact pair.
- **Augmentation:** noise, pitch, time and amplitude changes must affect only training input. Validation must use deterministic production-compatible preprocessing. Disabled augmentation ignores its subfields during execution but presets retain them.
- **Validation and overfitting:** decreasing LR, stopping early or changing model depth changes training behavior. Some RF metrics are undefined when a class is missing from the validation split; the Trainer explains this rather than inventing a number.
- **Compatibility:** a saved preset may have been created with an older toolbox, feature extractor or schema. The Trainer checks compatibility before use; it does not silently drop options. Advanced settings displayed in the app depend on verified capabilities of your installed scientific packages.

## Not part of this Trainer

The historical `src_dir`, `data_dir`, `model_dir`, `checkpoint_dir`, `log_dir`, `summary_dir`, `cache_dir` and `noise_dir` **directory fields** do not belong in the GUI. The Trainer manages Collection inputs and generated artifact locations. Script-specific restart and TorchScript/JIT switches also are not editable promises; fresh Runs and the validated portable checkpoint format own those requirements. Predictions on new audio will belong to a separate app documented in [PREDICTION](../PREDICTION.md).
