# Source map — task-specific ownership

Read only the relevant installed API and owning Studio source/tests. Neither a sibling source checkout nor a screenshot is proof of the installed version; consult [`pyproject.toml`](../../pyproject.toml) for released versions, tag target SHAs and wheel hashes.

| Concern | Source of truth |
|---|---|
| Studio launchpad, native controls, HelpHints | `src/biocall_studio/studio/`, `src/biocall_studio/*/gui/`, released public `alp_ui`, [consumer contract](../design/ALP_UI_CONSUMER_CONTRACT.md), [native Review evidence](../design/evidence/review-correction/README.md) |
| Train Collection/Dataset/Models | `src/biocall_studio/train/`, [workflow](../models/WORKFLOW_RULES.md), [training catalogue](../science/TRAINING_CONFIGURATION_CATALOG.md) |
| CNN and RF scientific features, predictions | Released `bioacoustics_dl_toolbox` and owning `src/biocall_studio/{train,detect}/`, [Model export](../science/MODEL_EXPORT_CONTRACT.md), [Detect contract](../PREDICTION.md) |
| Review spectrogram **display** API | Released `bioacoustics_dl_toolbox.visualization.spectrogram`; Studio-owned `src/biocall_studio/review/domain/spectrograms.py` and `review/workflows/spectrograms.py`; [decisions](../specs/review/SPECTROGRAM_DECISIONS.md) |
| Review labeling, source provenance, exports | `src/biocall_studio/review/`, [Review contract](../specs/review/README.md), [vision](../VISION.md) |
| Tests and sample files | [test skill](indexed-integration-tests/SKILL.md), [unit index](../UNIT_TESTING.md), [integration index](../INTEGRATION_TEST_BEHAVIORS.md), [fixture contract](../INTEGRATION_TEST_DATA.md) |
| Release source/CI/native qualification | [release process](../RELEASE_PROCESS.md) |

A reusable upstream defect needs its own library change, publication and downstream qualification. Do not silently patch library internals in Studio or change CNN feature semantics while modifying the Review display renderer. Never infer true model accuracy or installer approval from the example UI screenshots.
