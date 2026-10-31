# ST-06 → ST-07 Detect Worker and publication handoff

## Frozen request and reservation

`DetectRunRequest` schema version 1 is immutable and path-free. It freezes the Detect Collection
ID and root-binding revision, complete Inventory identity and digest, exact sorted included
recording keys, ModelSnapshot identity and canonical digest, explicit scalar settings, prospective
artifact identity, request/launch identities, and the GUI process's reservation-owner identity.
The controller's `freeze_run_request()` builds this contract from the accepted ST-04/ST-05
handoffs. ST-07 owns the first scientific settings schema and must not infer omitted values.

Run state is stored only below the app-owned Detect Collection directory. An exclusive
`active-run.json` reservation permits one local Active Detect Run. `DetectRunRecord` persists
`preparing`, `running`, `cancelling`, `cancelled`, `interrupted`, `failed`, and `completed`, the
actual QProcess PID, bounded monotonic progress/activity, stable privacy-safe error codes, and a
verified publication pointer only for `completed`. Detect Run IDs never enter Train's Run store.

Each GUI process owns a unique kernel-locked lease. The Worker receives only its contained
app-owned request path, that lease path, and bounded protocol options. Its watchdog exits after
owner loss, and the supervisor terminates then kills within configured cancellation bounds. Input
relink, rescan, inclusion changes, and Model replacement are denied while the reservation is
active. Studio exit waits for the supervised Detect Worker to stop without changing Train's
existing close/Worker policy; simultaneous Train/Detect arbitration remains ST-11-owned.

## QProcess protocol

The process uses separate stdout/stderr channels. Newline-delimited stdout records are bounded to
4 KiB and use `schema_version: 1` with one of:

- `started`;
- `progress` with integer monotonic `progress` (0–99), valid `stage_index`, and an allowlisted
  researcher-facing message;
- `error` with a stable allowlisted `error_code`, never arbitrary exception text;
- `cancelled` or `completed`.

The GUI incrementally drains stdout and stderr; a 1 MiB pending stdout limit fails closed. Stderr
retention is bounded, privacy-normalized, and written as one allowlisted summary. Exit code zero is
not success by itself. The supervisor persists a terminal state only after verifying both the
receipt and immutable artifact identity. A crash after the atomic rename but before the outer
receipt is retained only when the embedded publication identity verifies; reconciliation then
materializes and validates the missing outer receipt.

## Staging, receipt, and immutable publication

Private staging is one contained `.staging/<launch_id>` directory. Every regular file is indexed
by relative name, byte count, and SHA-256; symlinks, unindexed entries, excess files/bytes, identity
mismatch, collision, or unsafe storage fail closed. `publication.json` binds run, request, launch,
artifact kind and artifact ID to the canonical aggregate digest. The complete directory is renamed
atomically into the immutable publication namespace without overwrite. `PublicationReceipt`
schema version 1 repeats the exact identities, artifact kind/digest, and publication time.

The ST-06 fixture publishes only `artifact_kind=lifecycle_fixture` beneath `publications/`; its
payload explicitly says `scientific_result: false`. It never writes `results/`, never scores a WAV,
and cannot be presented as candidate output.

## Required ST-07 consumer work

ST-07 must add a separate scientific Worker; do not put inference in
`biocall_studio.detect.workflows.fixture`. It must:

1. consume a `freeze_run_request()` built from the current ST-04 Inventory and ST-05 CNN
   ModelSnapshot plus the ST-07-owned explicit settings;
2. revalidate every frozen source row through `validate_recording_source()` and recheck current
   Model manifest/artifact hashes before decoding or scoring;
3. preserve the QProcess stdout/error/cancellation/lease contract above and keep diagnostics free
   of source roots and recording names;
4. stage a complete ST-07 `DetectionResult`, extend the publication identity with the ST-07-owned
   artifact kind/destination only after validating that Result's full schema and checksums, and
   atomically publish it to the app-owned `results/` namespace;
5. write the matching outer receipt after publication and let the GUI mark `completed` only after
   independently reopening both receipt and Result; and
6. report per-file failures truthfully in the scientific Result. Missing or failed source input is
   never converted to zero candidates.

ST-07 may extend the artifact-kind/destination allowlist, but it must not weaken the existing
containment, collision, byte/file bounds, receipt identity, recovery, cancellation, or terminal
state rules. No source or Train-owned bytes may be changed.

## Evidence boundary

The indexed cases are `UT-DET-010`–`012` and `IT-DET-009`–`011`. Native Cocoa evidence is under
`docs/design/evidence/st-06-native/`. The fixture proves lifecycle mechanics only. CNN inference,
scientific Results, per-file outcome semantics, cross-workflow contention, Windows-native behavior,
installed-app behavior, and the separately initiated 600-second soak are not claimed by ST-06.
