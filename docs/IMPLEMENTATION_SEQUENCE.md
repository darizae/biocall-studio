# BioCall Studio — current implementation status

**Source baseline:** ST-01–ST-11 and REV-01–REV-04 are merged into `main`. ST-02 is owner-approved; ST-01 remains the approved [prototype](design/prototypes/studio-detect/index.html) reference, but browser interactions were not automated. [ST-11 qualification](ST-11_QUALIFICATION.md) records native source-app evidence. None of this qualifies installers, signing, notarization or Windows execution.

Completed stage/revision **implementation specs and obsolete agent handoffs have been removed**. Their behavior is represented by the source code, [Detect domain contract](PREDICTION.md), [Model export contract](science/MODEL_EXPORT_CONTRACT.md), [UX matrix](design/UX_PARITY_MATRIX.md), and indexed [unit](UNIT_TESTING.md) / [integration](INTEGRATION_TEST_BEHAVIORS.md) cases. Historical stage IDs remain searchable in Git history and test indexes; do not recreate completed specs for routine maintenance.

**Proposed, not implemented:** [REV-05 — shared output-size and free-space preflight](specs/manual_revision_specs/REV-05-output-size-preflight.md) for Train and Detect with an extension point for Review. Implement only after explicit owner approval, including the proposed UI copy.

**Release work deferred:** existing [macOS](specs/06-macos-release-and-installer.md) and [Windows](specs/07-windows-release-and-installer.md) specs and [release process](RELEASE_PROCESS.md) remain outside current scope. The [ST-11 spec](specs/ST-11-unified-qualification.md) is retained solely because the pending macOS release spec references it.

## Work and acceptance rules

- **Git:** inspect the live baseline and branch first. New cross-workflow maintenance branches from reviewed `main`; a newly approved staged Detect feature follows the reviewed `detect`/stage-branch convention when that branch actually exists. Upstream `bioacoustics-dl-toolbox`/`alp-ui` work has its own branch, scoped tests and commit. No automatic merge, push, tag or release publication.
- **Tests:** register only owning `UT-*` and `IT-*` cases in the existing indexes, with minimal `TD-*` fixtures, meaningful failures/cancellation/non-mutation and real Qt/QProcess/WAV/Model boundary tests where needed. Run targeted and affected regressions, then the full feasible ordinary unit/integration suites, Ruff and test-ID audit before each implementation commit. Run the ≥600-second soak separately. Distinguish passed from skipped, blocked or deferred-native.
- **UI:** follow the approved prototype *principles* and current native Train/Detect behavior, using public `alp-ui`. Clear labels, one action when appropriate, short useful keyboard-accessible HelpHints; no ornamental captions, repeated instructions, developer jargon, fabricated data or inaccessible tooltip-only meaning. Verify actual native focus, keyboard and compact layouts. The only full Train→Detect→RF→Export scenario remains indexed under ST-11; narrowly scoped follow-up revisions test their own seams.
