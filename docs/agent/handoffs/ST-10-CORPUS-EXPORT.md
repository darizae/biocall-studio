# ST-10 → ST-11 verified corpus export handoff

## Frozen request and exact frame convention

ST-10 consumes the ST-08 `FrozenResultSelection` v2 for either an original
`DetectionResult` or ST-09 `DerivedResult`. `ExportSnapshot` v1 freezes the exact
Result ID/digest, optional parent ID/digest, selection revision, deterministically
ordered candidate IDs, portable recording keys, source SHA-256 values, original
sample rate/frame/channel facts, inspected PCM sample width, exact source
frames/times, output mode, destination, collision policy and planned output paths
and concatenation offsets. Changing the Results selection after start cannot alter
this request.

All source intervals are half-open `[start_frame, end_frame)` in the original WAV.
The Result already owns clipping to the available source frame count; export
requires `0 <= start < end <= frame_count` and rejects disagreement rather than
silently clipping again. A snippet maps to output `[0, end-start)`. Concatenated
offsets are an ordered prefix sum of integer frame counts with zero inserted gap.
PCM byte count is exactly `(end-start) * channels * sample_width_bytes`.

## Audio and Raven policy

Individual snippets preserve each source WAV's uncompressed PCM sample rate,
channel count, sample width and interleaved frame bytes. Mixed formats are allowed
only because those files remain independent. Concatenated and both-mode export
requires every selected source to have the same sample rate, channel count and
sample width, and the current verified Raven path requires mono. Incompatible
selections are blocked with guidance to choose snippets or a uniform selection.
There is no resampling, downmixing, normalization or dtype conversion.

`corpus.wav` has no inserted gaps. `corpus.Table.1.selections.txt` uses the Cornell
Raven default columns first, in documented order, followed by candidate ID, source
file and original start/end frame columns. Time bounds are decimal seconds relative
to `corpus.wav`, calculated independently from exact concatenated frame offsets and
verified to round back to those frames. Low/high bounds are `0` and output Nyquist.
The authoritative original-source relationship remains separately present in the
snapshot and receipt. The verified reference is Cornell's
[selection-table guidance](https://www.ravensoundsoftware.com/knowledge-base/error-opening-selection-table/);
opening the output in a Raven installation was unavailable and is not claimed.

## Publication and reproducible `ExportReceipt`

Before any output staging is opened, ST-10 rechecks source containment, symlink
safety, complete source SHA-256, WAV decode/header/frame count, destination
containment, permission and final-name collision. Destinations inside the source
recordings tree are rejected so exports cannot feed later discovery. A hidden,
mode-0700 staging directory is created on the selected destination volume. All
payload files and the receipt are written there, source fingerprints are checked a
second time, every checksum/header/frame/TSV mapping is reopened, and files and
directories are flushed before one platform-native atomic no-replace directory
rename. Existing external files are never overwritten. Failure or cancellation
removes only the exact private staging directory.

`ExportReceipt` v1 is the reproducible handoff in every published export as
`export-receipt.json`. Its self-digest binds:

- export, snapshot, Result and optional parent lineage;
- explicit final destination, mode, format and collision policy;
- sorted payload relative paths, SHA-256 values, byte sizes and kinds;
- per-snippet source frames/times, output frames, PCM format and PCM SHA-256;
- per-candidate source-to-concatenated frame offsets and Raven selection number;
  and
- exact Raven rows, including integer output frames and zero-gap assertion.

`verify_export_directory(path)` performs a bounded, non-mutating reopen of the
receipt, snapshot, exact file allowlist, checksums, every WAV header/PCM mapping and
the regenerated Raven TSV. Multiple exports from the same Result receive new
export identities and self-contained collision-safe directories; prior exports
are never rewritten.

## Native control and state handoff

`DetectWorkspaceController.prepare_export_plan()` freezes the current selection.
`start_export()` runs source validation/materialization off the UI thread with
cooperative cancellation. The native Export route presents the frozen Result/count,
`snippets | concat | both`, a public `alp-ui` `FolderPicker`, exact planned source
and output frames, sensitive-content confirmation, `ready`, `running`, `conflict`,
`stale`, `cancelled`, `error` and `success`, plus a genuine platform
**Show in folder** action only after a successful receipt can be reopened. Normal
and compact Cocoa evidence is in `docs/design/evidence/st-10-native/`.

## ST-11 qualification boundary

ST-11 may drive the public controller seams above and must independently reopen the
returned `ExportReceipt`; it must not infer success from a Worker/thread exit or
folder existence. The complete Train→Detect→optional RF→Export scenario, combined
Train/Detect export-time quit behavior, cross-workflow ownership, Windows native
parity and installed-application behavior remain ST-11-owned and were not executed
here. ST-10 adds no scientific Result and writes no Detect metadata, Train Dataset,
Model or source WAV.

Indexed evidence is `UT-DET-021`–`023` and `IT-DET-019`–`021`. Ordinary suites,
ruff and test-ID audit results are recorded with the native evidence. The separate
≥600-second soak remains explicitly unexecuted.
