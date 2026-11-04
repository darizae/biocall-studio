from __future__ import annotations

import os

import pytest

from biocall_studio.detect.application.discovery import discover_wavs
from biocall_studio.detect.domain.detection import DetectionSettings
from biocall_studio.detect.domain.results import (
    CandidateInterval,
    DetectionResult,
    RecordingOutcome,
    candidate_identity,
    recording_identity,
)
from biocall_studio.detect.domain.rf_refinement import (
    DerivedResult,
    RefinementDecision,
)
from biocall_studio.detect.domain.runs import DetectRunRequest, complete_run
from biocall_studio.detect.persistence import DetectWorkspaceStore
from biocall_studio.detect.persistence.publication import (
    publish_staged_artifact,
    stage_derived_result,
    stage_detection_result,
)
from biocall_studio.detect.persistence.runs import DetectRunRepository
from biocall_studio.review.persistence.intake import (
    IntakeAvailability,
    ReviewResultIntake,
)
from biocall_studio.studio.application.storage import SuiteDataPaths

pytestmark = pytest.mark.integration


def _request(
    *,
    token: str,
    collection_id: str,
    binding_revision: int,
    inventory_id: str,
    inventory_digest: str,
    recording_keys: tuple[str, ...],
    model_snapshot_id: str,
    model_digest: str,
    settings: dict[str, object],
) -> DetectRunRequest:
    return DetectRunRequest.create(
        run_id="drun_" + token * 32,
        request_id="dreq_" + token * 32,
        launch_id="launch_" + token * 32,
        reservation_owner_id="owner_" + "1" * 32,
        collection_id=collection_id,
        binding_revision=binding_revision,
        inventory_id=inventory_id,
        inventory_digest=inventory_digest,
        selected_recording_keys=recording_keys,
        model_snapshot_id=model_snapshot_id,
        model_digest=model_digest,
        settings=settings,
        artifact_id="pub_" + token * 32,
        created_at=f"2026-11-04T10:{int(token, 16):02d}:00.000Z",
    )


def _complete_publication(
    repository: DetectRunRepository,
    request: DetectRunRequest,
    result: DetectionResult | DerivedResult,
):
    record = repository.create(request, title="RV-01 persisted Result", stages=("Publish",))
    running = record.with_running_process(os.getpid(), now=request.created_at)
    repository.save_record(running)
    staging = repository.staging_path(request.launch_id)
    if isinstance(result, DetectionResult):
        stage_detection_result(repository.collection_root, staging, request, result)
    else:
        stage_derived_result(repository.collection_root, staging, request, result)
    identity = publish_staged_artifact(repository.collection_root, staging, request)
    receipt = identity.receipt()
    repository.write_receipt(receipt)
    completed = complete_run(running, receipt, now=receipt.published_at)
    repository.save_record(completed)
    return completed


def test_persisted_detect_results_intake_is_paged_safe_and_source_immutable(
    tmp_path, wav_factory
):
    """Case: IT-REVW-001."""
    suite_root = tmp_path / "suite-data"
    source_root = tmp_path / "field-recordings"
    source_wav = wav_factory(
        source_root / "recordings" / "dawn.wav",
        frames=16_000,
        rate=8_000,
        channels=2,
    )
    arbitrary_wav = wav_factory(tmp_path / "test-wav" / "unrelated.wav", frames=400)
    original_source_bytes = source_wav.read_bytes()
    arbitrary_bytes = arbitrary_wav.read_bytes()

    detect_store = DetectWorkspaceStore(suite_root)
    collection = detect_store.create_collection("RV-01 source", source_root)
    inventory = discover_wavs(
        source_root,
        collection_id=collection.ref.collection_id,
        binding_revision=collection.ref.binding_revision,
    )
    detect_store.publish_inventory(collection.ref.collection_id, inventory)
    inventory_row = inventory.recordings[0]
    assert inventory_row.content_sha256 is not None and inventory_row.wav is not None
    recording_ref = recording_identity(
        inventory.inventory_id,
        inventory_row.recording_key,
        inventory_row.content_sha256,
    )
    candidates = tuple(
        CandidateInterval.create(
            candidate_id=candidate_identity(
                recording_ref,
                start,
                end,
                f"rv01-integration-{index}",
            ),
            recording_ref=recording_ref,
            start_frame=start,
            end_frame=end,
            sample_rate_hz=inventory_row.wav.sample_rate_hz,
            max_target_score=0.9 - index / 10,
            contributing_windows=index + 1,
        )
        for index, (start, end) in enumerate(((800, 1_600), (3_200, 4_000), (6_400, 7_200)))
    )
    outcome = RecordingOutcome.succeeded(
        recording_ref=recording_ref,
        recording_key=inventory_row.recording_key,
        source_sha256=inventory_row.content_sha256,
        sample_rate_hz=inventory_row.wav.sample_rate_hz,
        frame_count=inventory_row.wav.frame_count,
        channels=inventory_row.wav.channels,
        candidates=candidates,
    )
    settings = DetectionSettings(0.5, 50, 125, 8)
    cnn_request = _request(
        token="a",
        collection_id=collection.ref.collection_id,
        binding_revision=collection.ref.binding_revision,
        inventory_id=inventory.inventory_id,
        inventory_digest=inventory.digest,
        recording_keys=inventory.included_keys,
        model_snapshot_id="mdl_" + "3" * 32,
        model_digest="6" * 64,
        settings=settings.to_mapping(),
    )
    cnn = DetectionResult.create(
        result_id=cnn_request.artifact_id,
        run_id=cnn_request.run_id,
        request_id=cnn_request.request_id,
        collection_id=collection.ref.collection_id,
        binding_revision=collection.ref.binding_revision,
        inventory_id=inventory.inventory_id,
        inventory_digest=inventory.digest,
        model_id="model-cnn",
        model_snapshot_id=cnn_request.model_snapshot_id,
        model_manifest_sha256="4" * 64,
        model_artifact_sha256="5" * 64,
        model_snapshot_digest=cnn_request.model_digest,
        settings=settings,
        window_length_samples=4_000,
        hop_samples=settings.hop_samples(4_000),
        model_sample_rate_hz=16_000,
        backend_distribution="bioacoustics-dl-toolbox",
        backend_version="0.2.0",
        backend_revision="22c1b342",
        completed_at="2026-11-04T10:00:30.000Z",
        recordings=(outcome,),
    )
    repository = DetectRunRepository(suite_root, collection.ref.collection_id)
    _complete_publication(repository, cnn_request, cnn)
    cnn_result_path = repository.result_path(cnn.result_id) / "result.json"
    cnn_result_bytes = cnn_result_path.read_bytes()

    first, second, third = candidates
    rf_request = _request(
        token="b",
        collection_id=collection.ref.collection_id,
        binding_revision=collection.ref.binding_revision,
        inventory_id=inventory.inventory_id,
        inventory_digest=inventory.digest,
        recording_keys=inventory.included_keys,
        model_snapshot_id="mdl_" + "8" * 32,
        model_digest="b" * 64,
        settings={
            "run_kind": "rf_refinement",
            "parent_result_id": cnn.result_id,
            "parent_result_digest": cnn.result_digest,
        },
    )
    rf = DerivedResult.create(
        result_id=rf_request.artifact_id,
        run_id=rf_request.run_id,
        request_id=rf_request.request_id,
        parent=cnn,
        rf_model_id="model-rf",
        rf_model_snapshot_id=rf_request.model_snapshot_id,
        rf_model_manifest_sha256="9" * 64,
        rf_model_artifact_sha256="a" * 64,
        rf_model_snapshot_digest=rf_request.model_digest,
        threshold=0.6,
        probability_class_order=(0, 1),
        target_probability_column=1,
        feature_family="robust-mfcc-v1",
        feature_names=("mfcc_mean_1", "mfcc_std_1"),
        feature_config=(("sample_rate_hz", 8_000), ("min_duration_s", 0.5)),
        preprocessing_order=("decode", "mixdown_mono", "resample"),
        backend_distribution="scikit-learn",
        backend_version="1.7.2",
        backend_revision="22c1b342",
        completed_at="2026-11-04T10:01:30.000Z",
        decisions={
            first.candidate_id: RefinementDecision.scored(0.9, threshold=0.6),
            second.candidate_id: RefinementDecision.scored(0.2, threshold=0.6),
            third.candidate_id: RefinementDecision.unscored("feature_extraction_failed"),
        },
    )
    _complete_publication(repository, rf_request, rf)

    paths = SuiteDataPaths.from_root(suite_root)
    intake = ReviewResultIntake(suite_root)
    cnn_inspection = intake.intake(collection.ref.collection_id, cnn.result_id)
    rf_inspection = intake.intake(collection.ref.collection_id, rf.result_id)
    cnn_prepared = intake.prepare_session(collection.ref.collection_id, cnn.result_id)
    rf_prepared = intake.prepare_session(collection.ref.collection_id, rf.result_id)

    assert cnn_inspection.availability is IntakeAvailability.READY
    assert cnn_inspection.manifest is not None
    assert cnn_inspection.manifest.eligible_candidate_count == 3
    assert rf_inspection.availability is IntakeAvailability.READY
    assert rf_inspection.manifest is not None
    assert rf_inspection.manifest.eligible_candidate_count == 1
    assert rf_inspection.manifest.parent_result_id == cnn.result_id
    assert rf_inspection.manifest.parent_result_digest == cnn.result_digest
    assert cnn_prepared.source.eligibility_threshold == pytest.approx(0.5)
    assert cnn_prepared.source.score_semantics == cnn.score_semantics
    assert tuple(row.candidate_id for row in cnn_prepared.candidates) == tuple(
        row.candidate_id for row in candidates
    )
    assert rf_prepared.source.eligibility_threshold == pytest.approx(0.6)
    assert rf_prepared.source.score_semantics == rf.score_semantics
    assert rf_prepared.source.parent_eligibility_threshold == pytest.approx(0.5)
    assert rf_prepared.source.parent_score_semantics == cnn.score_semantics
    assert tuple(row.candidate_id for row in rf_prepared.candidates) == (first.candidate_id,)
    assert (
        intake.intake(collection.ref.collection_id, rf.result_id).manifest
        == rf_inspection.manifest
    )
    assert paths.review == paths.root / "review" / "v1"
    assert intake.store.root == paths.review
    assert intake.store.database_path.is_file()
    assert not (source_root / "review").exists()
    page = intake.store.candidate_page(
        collection.ref.collection_id,
        rf.result_id,
        offset=0,
        limit=1,
    )
    assert len(page) == 1
    assert page[0].candidate_id == first.candidate_id
    assert page[0].recording_ref == recording_ref
    assert page[0].start_frame == 800
    assert page[0].end_frame == 1_600
    assert page[0].sample_rate_hz == 8_000
    assert page[0].channels == 2
    assert second.candidate_id not in {row.candidate_id for row in page}
    assert third.candidate_id not in {row.candidate_id for row in page}
    assert str(source_root).encode() not in intake.store.database_path.read_bytes()
    assert source_wav.read_bytes() == original_source_bytes

    arbitrary = intake.intake(collection.ref.collection_id, str(arbitrary_wav))
    assert arbitrary.availability is IntakeAvailability.UNSUPPORTED_INPUT
    assert arbitrary.manifest is None
    assert arbitrary_wav.read_bytes() == arbitrary_bytes

    saved_source = source_wav.with_suffix(".saved")
    source_wav.rename(saved_source)
    source_wav.symlink_to(arbitrary_wav)
    unsafe = intake.reopen(collection.ref.collection_id, rf.result_id)
    assert unsafe.availability is IntakeAvailability.SOURCE_UNSAFE
    assert unsafe.manifest == rf_inspection.manifest
    source_wav.unlink()
    saved_source.rename(source_wav)

    moved_root = tmp_path / "temporarily-offline"
    source_root.rename(moved_root)
    relink_needed = intake.reopen(collection.ref.collection_id, rf.result_id)
    assert relink_needed.availability is IntakeAvailability.RELINK_NEEDED
    assert relink_needed.manifest.eligible_candidate_count == 1
    moved_root.rename(source_root)

    result_directory = repository.result_path(rf.result_id)
    missing_directory = result_directory.with_name(result_directory.name + ".missing")
    result_directory.rename(missing_directory)
    missing = intake.reopen(collection.ref.collection_id, rf.result_id)
    assert missing.availability is IntakeAvailability.RESULT_UNAVAILABLE
    assert missing.manifest.eligible_candidate_count == 1
    missing_directory.rename(result_directory)

    result_path = result_directory / "result.json"
    result_bytes = result_path.read_bytes()
    result_path.write_bytes(result_bytes[:-1] + b" ")
    corrupt = intake.reopen(collection.ref.collection_id, rf.result_id)
    assert corrupt.availability is IntakeAvailability.RESULT_UNAVAILABLE
    assert corrupt.manifest.eligible_candidate_count == 1
    result_path.write_bytes(result_bytes)

    restored = intake.reopen(collection.ref.collection_id, rf.result_id)
    assert restored.availability is IntakeAvailability.READY
    assert source_wav.read_bytes() == original_source_bytes
    assert cnn_result_path.read_bytes() == cnn_result_bytes
    assert result_path.read_bytes() == result_bytes
