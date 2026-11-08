from __future__ import annotations

import hashlib
import json
import os
import shutil
import wave
from pathlib import Path

import pytest

from biocall_studio.detect.application.controller import DetectWorkspaceController
from biocall_studio.detect.application.navigation import DetectRoute
from biocall_studio.detect.application.storage import estimate_export_artifacts
from biocall_studio.detect.domain.detection import DetectionSettings
from biocall_studio.detect.domain.export_history import (
    ExportAvailability,
    ExportHistoryRecord,
)
from biocall_studio.detect.domain.exports import (
    ExportCancelledError,
    ExportConflictError,
    ExportError,
    ExportMode,
    ExportStaleSourceError,
)
from biocall_studio.detect.domain.result_views import ResultSelection, freeze_result_selection
from biocall_studio.detect.domain.results import (
    CandidateInterval,
    DetectionResult,
    RecordingOutcome,
    candidate_identity,
    recording_identity,
)
from biocall_studio.detect.domain.runs import canonical_digest
from biocall_studio.detect.gui.workspace import DetectWorkspacePage
from biocall_studio.detect.workflows.exports import (
    freeze_export_snapshot,
    publish_export,
    verify_export_directory,
)
from biocall_studio.review.workflows.exports import (
    verify_export_directory as verify_compatible_export_directory,
)

pytestmark = [pytest.mark.integration]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pcm(path: Path) -> tuple[tuple[int, int, int, str], bytes]:
    with wave.open(str(path), "rb") as stream:
        facts = (
            stream.getframerate(),
            stream.getnchannels(),
            stream.getsampwidth(),
            stream.getcomptype(),
        )
        return facts, stream.readframes(stream.getnframes())


def _result_for_sources(
    root: Path,
    rows: tuple[tuple[str, tuple[tuple[int, int], ...]], ...],
) -> DetectionResult:
    inventory_id = "inv_" + "1" * 32
    outcomes = []
    for index, (key, intervals) in enumerate(rows):
        path = root / key
        digest = _sha256(path)
        with wave.open(str(path), "rb") as stream:
            rate = stream.getframerate()
            channels = stream.getnchannels()
            frames = stream.getnframes()
        recording_ref = recording_identity(inventory_id, key, digest)
        candidates = tuple(
            CandidateInterval.create(
                candidate_id=candidate_identity(
                    recording_ref, start, end, f"export-science-{index}-{candidate_index}"
                ),
                recording_ref=recording_ref,
                start_frame=start,
                end_frame=end,
                sample_rate_hz=rate,
                max_target_score=0.9 - candidate_index / 10,
                contributing_windows=candidate_index + 1,
            )
            for candidate_index, (start, end) in enumerate(intervals)
        )
        outcomes.append(
            RecordingOutcome.succeeded(
                recording_ref=recording_ref,
                recording_key=key,
                source_sha256=digest,
                sample_rate_hz=rate,
                frame_count=frames,
                channels=channels,
                candidates=candidates,
            )
        )
    settings = DetectionSettings(0.5, 50, 125, 8)
    return DetectionResult.create(
        result_id="pub_" + "a" * 32,
        run_id="drun_" + "b" * 32,
        request_id="dreq_" + "c" * 32,
        collection_id="det_" + "d" * 32,
        binding_revision=1,
        inventory_id=inventory_id,
        inventory_digest="2" * 64,
        model_id="model-cnn",
        model_snapshot_id="mdl_" + "3" * 32,
        model_manifest_sha256="4" * 64,
        model_artifact_sha256="5" * 64,
        model_snapshot_digest="6" * 64,
        settings=settings,
        window_length_samples=4_000,
        hop_samples=settings.hop_samples(4_000),
        model_sample_rate_hz=16_000,
        backend_distribution="bioacoustics-dl-toolbox",
        backend_version="0.2.0",
        backend_revision="e478ca5",
        completed_at="2026-10-29T12:00:00.000Z",
        recordings=tuple(outcomes),
    )


def _frozen(result: DetectionResult):
    ids = tuple(
        candidate.candidate_id
        for recording in result.recordings
        for candidate in recording.candidates
    )
    return freeze_result_selection(
        result,
        ResultSelection(
            1,
            result.result_id,
            result.result_digest,
            3,
            ids,
            "2026-10-29T12:01:00.000Z",
        ),
    )


def _freeze(
    result: DetectionResult,
    source_root: Path,
    destination: Path,
    mode: ExportMode,
    *,
    token: str,
):
    return freeze_export_snapshot(
        result=result,
        selection=_frozen(result),
        mode=mode,
        source_root=source_root,
        destination_parent=destination,
        export_id="exp_" + token * 32,
        created_at="2026-10-29T12:02:00.000Z",
    )


def test_real_snippet_pcm_headers_checksums_and_source_frames_are_exact(tmp_path, wav_factory):
    """Cases: IT-DET-019, IT-STU-009."""
    source = tmp_path / "source"
    mono = wav_factory(source / "recordings" / "mono.wav", frames=64, rate=8_000)
    stereo = wav_factory(source / "recordings" / "stereo.wav", frames=96, rate=16_000, channels=2)
    result = _result_for_sources(
        source,
        (
            ("recordings/mono.wav", ((3, 17),)),
            ("recordings/stereo.wav", ((11, 29),)),
        ),
    )
    destination = tmp_path / "exports"
    destination.mkdir()
    source_bytes = {path: path.read_bytes() for path in (mono, stereo)}
    snapshot = _freeze(result, source, destination, ExportMode.SNIPPETS, token="1")

    receipt = publish_export(snapshot, source_root=source)
    final = Path(receipt.final_destination)
    assert final == destination / snapshot.directory_name
    assert final.is_dir()
    assert len(receipt.snippets) == 2
    assert not receipt.concat_mappings
    for mapping in receipt.snippets:
        source_path = source / mapping.recording_key
        output_path = final / mapping.output_relative_path
        source_facts, source_pcm = _pcm(source_path)
        output_facts, output_pcm = _pcm(output_path)
        frame_bytes = source_facts[1] * source_facts[2]
        expected = source_pcm[
            mapping.source_start_frame * frame_bytes : mapping.source_end_frame * frame_bytes
        ]
        assert output_facts == source_facts
        assert output_pcm == expected
        assert mapping.output_start_frame == 0
        assert mapping.output_end_frame == mapping.source_end_frame - mapping.source_start_frame
        assert mapping.pcm_sha256 == hashlib.sha256(expected).hexdigest()
        file_record = next(
            item for item in receipt.files if item.relative_path == mapping.output_relative_path
        )
        assert file_record.sha256 == _sha256(output_path)
        assert file_record.byte_size == output_path.stat().st_size
    assert {path: path.read_bytes() for path in (mono, stereo)} == source_bytes
    assert verify_export_directory(final) == receipt


def test_both_mode_concat_pcm_raven_offsets_and_receipt_reopen_are_exact(tmp_path, wav_factory):
    """Cases: IT-DET-020, IT-SIZE-001, IT-REVW-010."""
    source = tmp_path / "source"
    first = wav_factory(source / "recordings" / "alpha.wav", frames=80, rate=8_000)
    second = wav_factory(source / "recordings" / "beta.wav", frames=90, rate=8_000)
    result = _result_for_sources(
        source,
        (
            ("recordings/alpha.wav", ((2, 9), (20, 31))),
            ("recordings/beta.wav", ((4, 17),)),
        ),
    )
    destination = tmp_path / "exports"
    destination.mkdir()
    snapshot = _freeze(result, source, destination, ExportMode.BOTH, token="2")
    storage = estimate_export_artifacts(snapshot)

    receipt = publish_export(snapshot, source_root=source)
    final = Path(receipt.final_destination)
    actual_output_bytes = sum(path.stat().st_size for path in final.rglob("*") if path.is_file())
    assert actual_output_bytes == storage.expected_final.high_bytes
    assert storage.peak_bytes == actual_output_bytes
    _, first_pcm = _pcm(first)
    _, second_pcm = _pcm(second)
    expected = first_pcm[2 * 2 : 9 * 2] + first_pcm[20 * 2 : 31 * 2] + second_pcm[4 * 2 : 17 * 2]
    concat_facts, concat_pcm = _pcm(final / "corpus.wav")
    assert concat_facts == (8_000, 1, 2, "NONE")
    assert concat_pcm == expected
    assert [(row.concat_start_frame, row.concat_end_frame) for row in receipt.concat_mappings] == [
        (0, 7),
        (7, 18),
        (18, 31),
    ]
    assert [(row.begin_frame, row.end_frame, row.gap_frames) for row in receipt.raven_rows] == [
        (0, 7, 0),
        (7, 18, 0),
        (18, 31, 0),
    ]
    tsv_lines = (final / "corpus.Table.1.selections.txt").read_text(encoding="utf-8").splitlines()
    assert len(tsv_lines) == 4
    assert tsv_lines[1].split("\t")[3:5] == ["0", "0.000875"]
    assert tsv_lines[-1].split("\t")[3:5] == ["0.00225", "0.003875"]
    assert len(receipt.snippets) == 3
    assert {item.kind for item in receipt.files} == {
        "snapshot",
        "snippet_wav",
        "concatenated_wav",
        "raven_tsv",
    }
    published_bytes = {
        path.relative_to(final): path.read_bytes() for path in final.rglob("*") if path.is_file()
    }
    reopened = verify_export_directory(final)
    assert reopened == receipt
    assert verify_compatible_export_directory(final) == receipt
    assert {
        path.relative_to(final): path.read_bytes() for path in final.rglob("*") if path.is_file()
    } == published_bytes
    receipt_path = final / "export-receipt.json"
    assert json.loads(receipt_path.read_text())["receipt_digest"]
    original_receipt = receipt_path.read_bytes()
    altered = json.loads(original_receipt)
    altered["snippets"][0]["recording_key"] = "recordings/altered.wav"
    altered_unsigned = dict(altered)
    altered_unsigned.pop("receipt_digest")
    altered["receipt_digest"] = canonical_digest(altered_unsigned)
    receipt_path.write_text(json.dumps(altered, sort_keys=True), encoding="utf-8")
    with pytest.raises(ExportError, match="mapping disagrees"):
        verify_export_directory(final)
    receipt_path.write_bytes(original_receipt)
    assert verify_export_directory(final) == receipt


def test_stale_permission_collision_disk_error_and_cancel_publish_nothing(
    tmp_path, wav_factory, monkeypatch
):
    """Cases: IT-DET-021, IT-SIZE-003."""
    source = tmp_path / "source"
    wav = wav_factory(source / "recordings" / "bird.wav", frames=128, rate=8_000)
    result = _result_for_sources(source, (("recordings/bird.wav", ((4, 40), (50, 90))),))
    destination = tmp_path / "exports"
    destination.mkdir()

    stale = _freeze(result, source, destination, ExportMode.SNIPPETS, token="3")
    stale_bytes = wav.read_bytes()
    wav.write_bytes(stale_bytes + b"changed")
    with pytest.raises(ExportStaleSourceError, match="changed"):
        publish_export(stale, source_root=source)
    wav.write_bytes(stale_bytes)
    assert not (destination / stale.directory_name).exists()

    collision = _freeze(result, source, destination, ExportMode.SNIPPETS, token="4")
    existing = destination / collision.directory_name
    existing.mkdir()
    marker = existing / "keep.txt"
    marker.write_text("unchanged", encoding="utf-8")
    with pytest.raises(ExportConflictError):
        publish_export(collision, source_root=source)
    assert marker.read_text(encoding="utf-8") == "unchanged"

    permission = _freeze(result, source, destination, ExportMode.SNIPPETS, token="5")
    destination.chmod(0o500)
    try:
        with pytest.raises(ExportError, match="not writable"):
            publish_export(permission, source_root=source)
    finally:
        destination.chmod(0o700)

    disk = _freeze(result, source, destination, ExportMode.SNIPPETS, token="6")
    import biocall_studio.detect.workflows.exports as exports_module

    original_writer = exports_module._write_wave_segment

    def disk_full(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(exports_module, "_write_wave_segment", disk_full)
    with pytest.raises(ExportError, match="No space left"):
        publish_export(disk, source_root=source)
    monkeypatch.setattr(exports_module, "_write_wave_segment", original_writer)

    cancelled = _freeze(result, source, destination, ExportMode.BOTH, token="7")
    checks = 0

    def cancel_after_staging() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 4

    with pytest.raises(ExportCancelledError):
        publish_export(cancelled, source_root=source, cancel_requested=cancel_after_staging)
    assert wav.read_bytes() == stale_bytes
    assert not (destination / disk.directory_name).exists()
    assert not (destination / cancelled.directory_name).exists()
    assert not list(destination.glob(".*.staging-*"))


@pytest.mark.qt
def test_export_history_restart_verification_and_corrupt_record_isolation(
    qapp, qtbot, tmp_path, wav_factory
):
    """Case: IT-DET-026."""
    source = tmp_path / "history-source"
    wav = wav_factory(source / "recordings" / "bird.wav", frames=128, rate=8_000)
    source_bytes = wav.read_bytes()
    result = _result_for_sources(source, (("recordings/bird.wav", ((4, 30), (42, 80))),))
    destination = tmp_path / "history-exports"
    destination.mkdir()
    controller = DetectWorkspaceController(tmp_path / "application-data")
    controller.store.create_collection("History source", source)
    controller.refresh()
    snapshots = [
        _freeze(result, source, destination, ExportMode.SNIPPETS, token=token)
        for token in ("a", "b", "c")
    ]
    receipts = [publish_export(snapshot, source_root=source) for snapshot in snapshots]
    store = controller._export_history_store
    collection = controller.active_collection
    assert store is not None and collection is not None
    for receipt in receipts[:2]:
        store.save(
            ExportHistoryRecord.from_receipt(
                collection.ref.collection_id,
                receipt,
                selected_call_count=len(receipt.snippets or receipt.concat_mappings),
            )
        )
    controller.refresh()
    assert len(controller.export_history) == 2
    assert {item.result_id for item in controller.export_history} == {result.result_id}

    reopened = DetectWorkspaceController(tmp_path / "application-data")
    assert [item.export_id for item in reopened.export_history] == [
        item.export_id for item in controller.export_history
    ]
    available_id = receipts[0].export_id
    reopened.select_export(available_id)
    qtbot.waitUntil(
        lambda: reopened.export_verification_state is ExportAvailability.AVAILABLE,
        timeout=10_000,
    )
    qtbot.waitUntil(lambda: reopened._export_verification_thread is None, timeout=10_000)
    assert reopened.verified_export_receipt == receipts[0]

    changed_file = next(
        path for path in Path(receipts[1].final_destination).rglob("*.wav") if path.is_file()
    )
    changed_file.write_bytes(changed_file.read_bytes() + b"changed")
    reopened.select_export(receipts[1].export_id)
    qtbot.waitUntil(
        lambda: reopened.export_verification_state is ExportAvailability.CHANGED,
        timeout=10_000,
    )
    qtbot.waitUntil(lambda: reopened._export_verification_thread is None, timeout=10_000)
    shutil.rmtree(receipts[0].final_destination)
    reopened.select_export(receipts[0].export_id)
    qtbot.waitUntil(
        lambda: reopened.export_verification_state is ExportAvailability.MISSING,
        timeout=10_000,
    )
    qtbot.waitUntil(lambda: reopened._export_verification_thread is None, timeout=10_000)

    store.save(
        ExportHistoryRecord.from_receipt(
            collection.ref.collection_id,
            receipts[2],
            selected_call_count=len(receipts[2].snippets or receipts[2].concat_mappings),
        )
    )
    controller.refresh()
    inaccessible = Path(receipts[2].final_destination)
    inaccessible.chmod(0)
    try:
        controller.select_export(receipts[2].export_id)
        qtbot.waitUntil(
            lambda: controller.export_verification_state is ExportAvailability.INACCESSIBLE,
            timeout=10_000,
        )
        qtbot.waitUntil(
            lambda: controller._export_verification_thread is None,
            timeout=10_000,
        )
    finally:
        inaccessible.chmod(0o700)

    store = controller._export_history_store
    assert store is not None
    corrupt = store.exports_root / ("exp_" + "e" * 32 + ".json")
    corrupt.write_text("{", encoding="utf-8")
    unsafe = store.exports_root / ("exp_" + "f" * 32 + ".json")
    unsafe.symlink_to(store.path_for(receipts[1].export_id))
    controller.refresh()
    assert len(controller.export_history) == 3
    assert {path.name for path in controller.export_history_rejected} == {
        corrupt.name,
        unsafe.name,
    }

    cancelled = _freeze(result, source, destination, ExportMode.BOTH, token="9")
    with pytest.raises(ExportCancelledError):
        publish_export(cancelled, source_root=source, cancel_requested=lambda: True)
    assert cancelled.export_id not in {item.export_id for item in controller.export_history}
    assert wav.read_bytes() == source_bytes
    evidence_value = os.environ.get("BIOCALL_REV04_EVIDENCE_DIR")
    if evidence_value:
        evidence = Path(evidence_value)
        evidence.mkdir(parents=True, exist_ok=True)
        page = DetectWorkspacePage(controller)
        qtbot.addWidget(page)
        page.show()
        controller.select_export(receipts[2].export_id)
        qtbot.waitUntil(
            lambda: controller._export_verification_thread is None,
            timeout=10_000,
        )
        assert controller.export_verification_state is ExportAvailability.AVAILABLE, (
            controller.export_verification_message
        )
        for width, size_label in ((1180, "normal"), (700, "compact")):
            page.resize(width, 790)
            qtbot.waitUntil(lambda width=width: page.is_compact == (width < 820))
            qtbot.wait(50)
            for route, label in (
                (DetectRoute.EXPORTS, "exports-list"),
                (DetectRoute.EXPORT_DETAIL, "export-detail"),
            ):
                page._set_route(route)
                qtbot.wait(25)
                path = evidence / f"{label}-{size_label}.png"
                assert page.grab().save(str(path), "PNG")
                assert path.stat().st_size > 10_000
    reopened.shutdown()
    controller.shutdown()
