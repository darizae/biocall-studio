# Implementation specs — one stage at a time

[Sequence and gates](../IMPLEMENTATION_SEQUENCE.md) governs order, branches and acceptance. **Owner-approved:** [ST-01 prototype](ST-01-prototype.md) (design approval, not browser-automation qualification) and [ST-02 shell](ST-02-native-shell.md). **Next active implementation:** [ST-03 workspace](ST-03-detect-workspace.md). Prepared future specs are **not permission** to implement them before predecessor review.

| Stage | Spec |
|---|---|
| 03 | [Collection identity, storage and relink](ST-03-detect-workspace.md) |
| 04 | [WAV inventory](ST-04-wav-discovery.md) |
| 05 | [Model intake](ST-05-model-intake.md) |
| 06 | [Workers and logs](ST-06-detect-workers.md) |
| 07 | [CNN detection](ST-07-cnn-detection.md) |
| 08 | [Results UX](ST-08-results-ux.md) |
| 09 | [RF refinement](ST-09-rf-refinement.md) |
| 10 | [Corpus export](ST-10-corpus-export.md) |
| 11 | [Whole-Studio qualification](ST-11-unified-qualification.md) |

Run only the owning indexed `UT-*`/`IT-*` behaviors plus affected regressions during a stage. Whole-Studio E2E belongs exclusively to ST-11. The existing macOS/Windows release specifications are revised there, not duplicated.
