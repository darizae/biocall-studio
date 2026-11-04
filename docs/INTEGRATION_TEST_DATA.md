# Integration-test data — equivalence classes and fixture policy

## Source of test truth

Ordinary unit/integration tests use **tiny deterministic generated WAV files** and a small, audited set of fixed anonymized Git LFS fixtures only when a field encoding/checkpoint behavior cannot be generated convincingly. Never depend on a connected HPC system or the developer's private Collection. Test file names and bytes must make mistakes observably different (two distinct stems, signals, durations, temporal windows and labels); a fabricated JSON object is not a real WAV integration fixture.

The HPC is a **permissioned archive and scientific compatibility reference**, not an application runtime, training service or CI data source. The untracked private [`hpc-source-access` skill](priv/hpc-source-access/SKILL.md) and bounded read-only [`hpc-source.sh`](priv/hpc-source-access/scripts/hpc-source.sh) may inspect and stage exact approved source files only after generated/existing test material proves insufficient. The permitted archive can contain Source Recording examples, pipeline Dataset snippets/Splits, completed CNN checkpoints, RF estimators, run logs and deployed `alpaca-pipelines` source. Their archive naming/format **does not** change the Trainer's Collection/Model contracts. Never recursively download a directory or large merged index, attempt remote mutation, bypass an SSH error or infer consent to commit sensitive bytes.

### Fixture selection and governance

1. For each `UT-*`/`IT-*` row select the **minimum relevant `TD-*` classes** below; search generators and existing `tests/data/` first.
2. To sample HPC source, obtain authorized machine-local access. Check the private skill, use its scoped catalog/stat/pull helper into staging *outside the repo*, and check license/identity/metadata, speech/location risk, source sha256 and scientific relevance.
3. Crop/transform/strip identifying metadata and rename neutrally while preserving the discriminator tested. Prefer generated audio over external bytes where possible. Record a non-sensitive provenance key, transform recipe and file checksum; keep source paths/identity mappings out of tracked docs.
4. Commit approved minimal binary fixture through **Git LFS**, with its versioned `tests/data/README.md` fixture register and `tests/data/SHA256SUMS`. The register must state `FX-*` ID/revision, bytes, SHA-256, source category, neutral recipe, permissions, `TD-*` class and asserting tests. Validate actual LFS objects with `git lfs pull` / `git lfs fsck`; pointer presence is not byte availability. These register paths should be created only once real fixtures are approved.
5. Fixture amendments and relevant generator, active spec and case assumptions change **together**. Obtain explicit user approval before tracked fixture payload exceeds **1,000,000,000 bytes**. If permissions/HPC/LFS absent, mark affected case blocked or use deterministic generated alternative; never silently relax expectations.

**Archive inventory is not fixture registration**: do not cite unverified, missing local LFS assets as available. **Transfer archives intentionally may omit `tests/data/` entirely. This is expected and is not a defect in Spec 01 or a reason to copy fixtures from an old ZIP.** In an actual Git checkout, use registered, Git LFS-versioned `tests/data/example_collection/` (`FX-SYN-001`) **only if present and materialized**, or generate the smallest deterministic real WAV Collection in `tmp_path` using the repository generator. If a specific fixed fixture is necessary, obtain it through the proper Git LFS history/approval flow and mark that exact dependent test BLOCKED until its bytes exist; never report a fixed-fixture test as passed from a missing ZIP. `tests/data/README.md` and `SHA256SUMS` are authoritative when the fixture directory is available. No HPC-derived bytes are presumed present. The first approved HPC example would use a distinct `FX-HPC-*` ID and permissioned provenance.

## Test-data class index

| Class | Discriminating variants / generated strategy | Consumers |
|---|---|---|
| **TD-UI** | Initial empty state, bound Collection, interrupted Scan/Run, keyboard FolderPicker cancel/HelpHint, native Plot with numeric summary, navigation/Qt screenshot parity, standalone theme assets, Review audio proof focus/shortcuts/paint geometry | 01, 05–07, Review RV-03 |
| **TD-PATH** | valid relative stems; traversal/absolute path; Windows-reserved names; casefold/NFC collision; symlink escape; relocation | 01–02, 06 |
| **TD-COL** | two distinct recordings, multiple timestamped positives; wrong source stem/prefix collision; duplicate interval; missing/nested folders; invalid format/non-WAV file; zero positives | 02 |
| **TD-WAV** | real mono/stereo PCM WAV with distinct waveform/frame rates; 8/16/24/32-bit PCM and phase-opposed channels where owned; float if decoder supports; short/truncated/unsupported header; mismatched clip duration; near-boundary source time | 02–03, Review RV-03 |
| **TD-CACHE** | first scan; warm reopen; added/removed/touched/replaced WAV; schema mismatch; corrupted/partially written JSONL; relocated binding; Review renderer/settings/source identity invalidation; valid/corrupt/staged PNG cache objects and measured encoded sizes | 02, Review RV-03–RV-04 |
| **TD-SCALE** | generated tens-of-thousands row/partition metadata, including a 50,000-candidate Review index and lazy cache-generation requests; short synthetic WAVs where necessary; paged reading/memory, queue and I/O counters | 02, Review RV-02, RV-04 |
| **TD-MINE** | multiple positives/merged protected windows; margin; sufficient eligible noise; zero space underfill; boundary/cross-chunk windows; repeat seed | 03 |
| **TD-SPLIT** | ≥2 distinct recording groups with train/val candidate target and noise; class balance feasible/infeasible; repeat seed and changed configuration | 03 |
| **TD-RUN** | startup/running/cancelled/failed/crashed/orphaned process; second Run; active input delete and stale output; collision; bounded Review generation, cancellation and retry | 03–06, Review RV-04 |
| **TD-FAIL** | permissions, disk full/injected write error, corrupt manifest, missing/deleted source, worker exit code, multimedia/device failure, interruption at staging/finalization/cache-publication transaction boundary, symlink escape and corrupt cached image | 02–05, Review RV-02–04 |
| **TD-TRAIN** | real small Dataset with train and val source groups, both `target` and `noise`; RF feature shape/schema mismatch; undefined val metric; minimal CPU CNN and RF with loadable outputs | 05–06 |
| **TD-CONFIG** | complete typed CNN and RF configurations, all legacy non-path mapping assertions, default and advanced nondefault settings, unsupported/derived options, invalid FFT/bands/ranges, unavailable device, per-field Wiki anchors and HelpHint inventory; no reference filesystem paths | 05–07 |
| **TD-PRESET** | temporary user preset store, two named CNN/RF presets, saved vs unsaved draft, conflicting names, rename/duplicate/delete/overwrite, invalid/obsolete schema, atomic write failure, reload after app restart and no original Dataset path in files | 05–07 |
| **TD-EXPORT** | genuinely fit small CNN and RF Model binaries, fresh-process trusted deserialization, wrong artifact digest/version, missing spectrogram/normalization or class map, RF ordered feature names/config/`classes_` mismatch and portability; generated real WAV-backed Dataset as training input. No inference or unseen-audio scoring. | 05–07 |
| **TD-OS** | actual native Windows/macOS paths, filesystem behavior, Qt/QProcess/installed native libs and signed/installed packaged resources | 06–07 |

## Concrete minimum generated Collection

```text
case-study/
  recordings/
    REC_A.wav         # distinct waveform, e.g. 12 s
    REC_B.wav         # distinct waveform, e.g. 12 s
    REC_C.wav         # optional third group for reliable split/validation
  positives/
    REC_A__start-01000ms__end-02000ms__callA.wav
    REC_B__start-03000ms__end-04000ms__callB.wav
```

Generate each positive WAV with matching source-time duration and appropriately distinguishable samples; `Collection Scan` itself does not compare samples, but scientific Dataset materialization tests **must** detect selection of wrong source/time. Use known sample counts and correct clipped intervals. For Training, add enough valid recording groups and balanced snippets to satisfy the family trainer and source-group split contract; tiny audio accuracy is not a model-quality claim. For **IT-TRAIN-008/009**, use the actual small WAV-backed training Dataset to produce real checkpoint/estimator bytes, then verify saved metadata and structural deserialization in a fresh process. Do not add inference-on-unseen-WAV tests to Trainer. Use separate invalid-artifact tests to establish failures. No bulk real recording in version control just to test scan pagination; generate index data.

## HPC helper safety and failure handling

The private site reference holds environment-specific SSH details and permitted source roots. The helper is explicitly **read-only** and limits `list`, `stat` and exact-file `pull` to allowlisted project locations, refuses overwrites and files above its cap, and stages outside the repo. Do not print or publish large sensitive catalog content. Permission, VPN, host-key, rights, missing source and LFS failures are blockers requiring owner attention, not requests to bypass SSH verification or broaden search. A pipeline source archive can inform sample/channel/RF feature contracts; it is not the Trainer input folder layout.

## A repeatable HPC → local Git LFS approval flow (not an implicit background task)

1. Identify an `IT-*` gap that deterministic sample `FX-SYN-001` cannot exercise (e.g., actual field WAV codec or loadable model serialization), record expected decoder/schema and **why** field bytes are needed. No speculative downloads.
2. Owner authorizes exact archive scope; read ignored `docs/priv/hpc-source-access/{SKILL.md,references/site.md}` locally, run `hpc-source.sh check`, `catalog`, `stat` and `pull` only for approved relative **files**. Stop on access or permission failure. Stage outside repo. Record source hash/size privately.
3. Check rights/confidentiality/voice/location; make smallest anonymized, metadata-stripped representatively encoded derived fixture; compare invariant with original and confirm publishing rights. Keep mapping from raw private source identity to neutral fixture **outside Git**.
4. Add approved derived `tests/data/fixtures/<FX-HPC-id>/...` WAV/checkpoint via Git LFS, `FX-HPC-*` record in `tests/data/README.md`, SHA256SUMS, relevant `TD-*` and asserting `IT-*` tests. Verify `git check-attr filter`, `git lfs ls-files`, `git lfs fsck`, fresh `git lfs pull` and actual tests from LFS bytes. Preserve old revisions needed for reproducibility (do not mutate bytes behind an existing FX ID).
5. Fail/mark blocked if HPC, permission, LFS, rights or genuine schema evidence absent. CI never authenticates to HPC; tested fixture is local Git/LFS content only.
