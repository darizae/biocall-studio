# User workflows and data model

## User-directed flow

```text
Select folder ──> Collection Scan / validation ──> Collection overview
                         │ (rebuildable .alpaca cache)       │
                         │                                   v
                         └────────────────────────── Build Dataset configuration
                                                         │
                                                  Dataset Build Run
                                                         │
                                               immutable Dataset
                                                  /          \
                                           CNN Training   RF Training
                                                \           /
                                                 Training Run
                                                      │
                                               immutable Model
```

Invalid Collection → exact file/folder issue → user repairs existing inputs → rescan. Cancel Scan → no published new metadata. A failed/cancelled Run → no published Dataset/Model. One Active Run can be visited from any page; collection scanning is not part of that singleton.

## Source and derived ownership

```text
<Collection>/                                 [user-selected]
  recordings/<source-stem>.wav                 [read-only input]
  positives/<stem>__start-<ms>ms__end-<ms>ms__<label>.wav  [read-only input]
  .alpaca/                                    [app-managed]
    collection.json                           [mutable, rebuildable cache manifest]
    records/part-0001.jsonl                   [indexed Source Recordings]
    positives/part-0001.jsonl                 [derived target Annotations]
    datasets/<dataset-id>/
      dataset.json                            [immutable manifest]
      snippets/<snippet-id>.wav                [materialized audio]
      splits/train.csv
      splits/val.csv
    runs/<run-id>/run_state.json               [mutable persisted lifecycle]
    runs/<run-id>/logs/...                     [bounded execution diagnostics]
    models/<model-id>/
      model.json                              [immutable family-specific manifest]
      ...                                     [CNN checkpoint OR RF estimator/schema]
```

The diagram describes canonical logical files, not preapproved Python class names. The `collection.json` schema owns identity, input inventories, partition references and version; records/positive partitions own row facts. A Dataset manifest owns its own selected input fingerprints, mining/Split decisions and materialized file references. Model manifest owns Dataset pointer, family, resolved config, feature/transform schema, metrics and model file references. Run State owns lifecycle and output pointer, **not** proof of artifact validity.

## Cardinality and identity

- One Collection owns zero or more Source Recordings and Positive Examples. A valid Collection for Dataset Build requires at least one positive and participating source; exact validation rules reside in [`WORKFLOW_RULES.md`](WORKFLOW_RULES.md).
- Every Positive Example resolves to **exactly one** Source Recording using its full stem. Multiple positive intervals may reference the same source; the same source interval may not be duplicated ambiguously.
- Each Positive Example gives one `target` Annotation; the input WAV and source interval are both retained as provenance. Dataset Build may yield one or more target Snippets according to a specified resample/window policy; never infer an unstated mapping.
- One Dataset contains many Snippets and exactly two named Splits `train` and `val`; each Snippet belongs to one Split. No Source Recording crosses Splits.
- Many Dataset Build Runs may produce distinct immutable Datasets from the same Collection. Many Training Runs may produce Models from one Dataset. One published Model has exactly one family and training Dataset.
- A Collection's persisted machine-local binding may change when the folder moves without rewriting portable relative references; relinking requires full containment and input freshness revalidation.

## Implementation separation

`gui` displays selections and progress; `application` controls scan activity and one Active Run; `domain` decides identity/interval/validation/split rules; installed `bioacoustics_dl_toolbox` owns reusable PCM/audio extraction and CNN algorithms; Trainer Qt-free workflows adapt these and verified RF scientific libraries; `workflows` constructs immutable outputs; `persistence` owns cache and atomic publications. Worker receives explicit versioned validated inputs, returns a staged/published result and does not reach into Qt widgets. No additional top-level scientific workflow exists.
