# Selecting a Collection

A **Collection** is the local folder you select in **alpaca Desktop Trainer**. It already contains the original WAV recordings and manually labeled **positive** WAV snippets. No import, standardization, or source-audio copy is required.

## The folder you select

```text
Rainforest-dawn/                            ← select this folder
├── recordings/
│   ├── SITE_001.wav                        ← Source Recordings
│   └── SITE_002.wav
└── positives/
    ├── SITE_001__start-012500ms__end-014900ms__call01.wav
    ├── SITE_001__start-070000ms__end-071500ms__call02.wav
    └── SITE_002__start-001200ms__end-003600ms__call01.wav
```

Only **WAV** files are accepted in `recordings/` and `positives/`. Keep WAVs directly inside their respective subfolders. Generated `.alpaca/` files are managed by the Trainer; do not create or edit them yourself. No explicitly labeled negative files are required: **Negative Mining** creates `noise` Snippets from source audio after excluding positive intervals.

## Naming positive snippets

Use this exact pattern for each positive WAV:

```text
<recording-stem>__start-<integer>ms__end-<integer>ms__<unique-label>.wav
```

Example:

```text
SITE_001__start-012500ms__end-014900ms__call01.wav
```

The positive comes from `recordings/SITE_001.wav`, starts at **12.500 seconds** in the *original Source Recording*, ends at **14.900 seconds**, and contains **2.400 seconds** of audio. The numeric values are integer milliseconds (1 second = 1000 milliseconds); zero padding is optional. The final label distinguishes snippets that would otherwise share a name. The full source stem before `__start-` must match one and only one Source Recording stem. This is the required Trainer input contract. Third-party clip export tools may need their output names adjusted to match it.

The timestamp describes the original recording, not the position within the cropped snippet. Preserve source-time offsets when manually exporting clips. Do not try to infer start time from the order of snippets or the filename prefix alone.

## What happens when you select the folder?

1. The Trainer shows a **Reading Collection** view with file counts, a progress bar and cancellation. The GUI remains responsive while a local I/O worker reads directory entries and WAV headers; audio is not fully decoded for the overview.
2. It checks folder names, WAV support, portable filenames/case collisions, a unique source match for every positive WAV, integer source timestamps, nonempty intervals, source-duration bounds and snippet-duration agreement.
3. It shows an overview with recording counts, positive counts, audio duration, snippet associations and **per-file reasons** for any failed checks.
4. After a successful scan, the native Trainer will write small, versioned metadata under `.alpaca/collection.json`, with bounded `records/*.jsonl` partitions if a large Collection needs them. Reopening uses this cached metadata and file fingerprints (size, modified time, WAV header/frame data), re-reading changed files as necessary. The cache is rebuildable, never the scientific source of truth. Before Dataset Build, inputs are revalidated for changes.

### Common messages

| Message | Why it appears | What to change |
|---|---|---|
| Missing `recordings/` or `positives/` | Expected folder not found | Create the required folder and select the Collection again |
| Only WAV files are allowed | Unsupported file under an input folder | Remove, relocate or convert the file to supported WAV |
| Invalid or unsupported WAV | Empty, malformed or unsupported WAV encoding | Re-export as supported PCM/float WAV |
| Unknown Source Recording | Filename stem does not identify a Source Recording | Use the exact source WAV stem before `__start-` |
| Positive has no timestamps | No properly formatted start/end fields | Add `__start-Nms__end-Nms` |
| Invalid time interval | Negative start or end not later than start | Correct source-time bounds |
| Snippet outside recording | End exceeds original WAV duration | Correct source selection or interval |
| Snippet duration disagrees with filename | Cropped WAV duration differs from `(end-start)` | Re-export the clip or correct the bounds |
| Filename collision / duplicate interval | Names collide across case/Unicode normalization, or same source span appears twice | Rename or remove duplicates |

**Important limitation:** Matching filenames, duration and time bounds establishes *metadata consistency*, not that the snippet waveform really matches the claimed interval in the raw WAV. The initial contract trusts correctly exported source-time labels. Optional bounded waveform verification can be added if field data shows a need; it must not be implied by the ordinary “Collection valid” message.

## After validation

Select Source Recordings, choose how many negative Snippets to mine, configure `train`/`val` Splits, and **Build Dataset**. The resulting **Dataset** is immutable. Use any Dataset to train either a CNN or a Random Forest **Model**. Training generates metrics and a reusable Model under a readable label and stable ID.

The browser [Training prototype](../design/prototypes/training-first/index.html) demonstrates these screens. It can inspect selected browser-visible WAV headers and offer a **downloadable manifest preview**, but browser security prevents it from silently writing `.alpaca/collection.json` into the selected folder. Dataset Build, Training, and persistent local metadata in the prototype are simulated; the native app will implement those operations.
