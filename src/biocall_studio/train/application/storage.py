"""Train-owned output-size planners for Dataset Build and Model Training."""

from __future__ import annotations

from collections.abc import Mapping

from biocall_studio.shared.storage import (
    MIB,
    ByteEstimate,
    EstimateConfidence,
    OperationSizePlan,
    pcm_wav_bytes,
    storage_input_digest,
)
from biocall_studio.train.domain.collection import ScanResult
from biocall_studio.train.domain.dataset import BuildConfig
from biocall_studio.train.persistence.datasets import DatasetArtifact
from biocall_studio.train.workflows.dataset_build import _mining_plan

_CNN_PARAMETERS = {
    18: 11_700_000,
    34: 21_800_000,
    50: 25_600_000,
    101: 44_500_000,
    152: 60_200_000,
}


def _nearest_frame(milliseconds: int, sample_rate_hz: int) -> int:
    return (milliseconds * sample_rate_hz + 500) // 1_000


def estimate_dataset_artifacts(
    scan: ScanResult,
    config: BuildConfig,
) -> tuple[OperationSizePlan, str]:
    """Plan preserved-PCM Snippets plus bounded manifests and split indexes."""
    selected_ids = set(config.selected_recording_ids)
    records = tuple(record for record in scan.records if record.id in selected_ids)
    positives = tuple(
        positive for positive in scan.positives if positive.source_recording_id in selected_ids
    )
    if len(records) < 2 or not positives:
        plan = OperationSizePlan(
            ByteEstimate.unavailable(),
            None,
            EstimateConfidence.INSUFFICIENT_EVIDENCE,
            "A valid Dataset selection and Negative Mining plan are required.",
            "Can't estimate the output size yet. Check the selected files and settings.",
        )
        return plan, storage_input_digest(
            {"operation": "train.dataset_build", "config": config.to_dict()}
        )
    records_by_id = {record.id: record for record in records}
    noise = _mining_plan(records, positives, config)
    audio_bytes = 0
    for positive in positives:
        if (
            positive.source_recording_id is None
            or positive.start_ms is None
            or positive.end_ms is None
        ):
            raise ValueError("Positive Example is missing source-time facts.")
        header = records_by_id[positive.source_recording_id].fingerprint.header
        start = _nearest_frame(positive.start_ms, header.sample_rate_hz)
        end = _nearest_frame(positive.end_ms, header.sample_rate_hz)
        audio_bytes += pcm_wav_bytes(
            end - start,
            channels=header.channels,
            sample_width_bytes=header.sample_width_bytes,
        )
    for window in noise.windows:
        header = records_by_id[window.source_recording_id].fingerprint.header
        start = _nearest_frame(window.start_ms, header.sample_rate_hz)
        end = _nearest_frame(window.end_ms, header.sample_rate_hz)
        audio_bytes += pcm_wav_bytes(
            end - start,
            channels=header.channels,
            sample_width_bytes=header.sample_width_bytes,
        )
    snippet_count = len(positives) + len(noise.windows)
    metadata_ceiling = (
        32 * 1_024 + snippet_count * (2_048 + 256) + len(records) * 1_024 + len(positives) * 512
    )
    high = audio_bytes + metadata_ceiling
    plan = OperationSizePlan(
        ByteEstimate.range(audio_bytes, high),
        high + 8 * MIB,
        EstimateConfidence.ARITHMETIC,
        (
            "Planned nearest-frame PCM WAV payloads and headers with bounded Dataset manifest, "
            "entry, split, request, and diagnostic overhead."
        ),
    )
    digest = storage_input_digest(
        {
            "operation": "train.dataset_build",
            "config": config.to_dict(),
            "records": [
                {
                    "id": record.id,
                    "size_bytes": record.fingerprint.size_bytes,
                    "mtime_ns": record.fingerprint.mtime_ns,
                    "header": {
                        "sample_rate_hz": record.fingerprint.header.sample_rate_hz,
                        "channels": record.fingerprint.header.channels,
                        "sample_width_bytes": record.fingerprint.header.sample_width_bytes,
                        "frame_count": record.fingerprint.header.frame_count,
                    },
                }
                for record in records
            ],
            "positives": [
                {
                    "source_recording_id": positive.source_recording_id,
                    "start_ms": positive.start_ms,
                    "end_ms": positive.end_ms,
                }
                for positive in positives
            ],
            "noise_windows": [
                {
                    "source_recording_id": window.source_recording_id,
                    "start_ms": window.start_ms,
                    "end_ms": window.end_ms,
                }
                for window in noise.windows
            ],
        }
    )
    return plan, digest


def training_input_digest(artifact: DatasetArtifact, config: object) -> str:
    snapshot = getattr(config, "to_worker_snapshot", None)
    if not callable(snapshot):
        raise ValueError("Training storage estimate requires frozen settings.")
    return storage_input_digest(
        {
            "operation": "train.model",
            "dataset_id": artifact.dataset_id,
            "dataset_counts": artifact.manifest.get("counts"),
            "config": snapshot(),
        }
    )


def estimate_model_artifacts(
    *,
    family: str,
    effective_values: Mapping[str, object],
    snippet_count: int,
) -> OperationSizePlan:
    """Return conservative analytical bounds without treating them as measurements."""
    if type(snippet_count) is not int or snippet_count <= 0:
        return OperationSizePlan(
            ByteEstimate.unavailable(),
            None,
            EstimateConfidence.INSUFFICIENT_EVIDENCE,
            "A valid nonempty Dataset and resolved Model settings are required.",
            "Can't estimate the output size yet. Check the selected files and settings.",
        )
    if family == "cnn":
        resnet_size = effective_values.get("encoder.resnet_size")
        epochs = effective_values.get("training.max_epochs")
        if (
            type(resnet_size) is not int
            or resnet_size not in _CNN_PARAMETERS
            or type(epochs) is not int
            or epochs <= 0
        ):
            return OperationSizePlan(
                ByteEstimate.unavailable(),
                None,
                EstimateConfidence.INSUFFICIENT_EVIDENCE,
                "Resolved CNN architecture and epoch settings are unavailable.",
                "Can't estimate the output size yet. Check the selected files and settings.",
            )
        parameter_bytes = _CNN_PARAMETERS[resnet_size] * 4
        # The current Worker retains one selected state-dict checkpoint plus its
        # manifest. Serialization metadata varies by tensor layout and PyTorch.
        low = parameter_bytes + 256 * 1_024
        high = (parameter_bytes * 3 + 1) // 2 + 2 * MIB
        peak = high + 8 * MIB  # bounded request and diagnostic/log growth on the same volume
        return OperationSizePlan(
            ByteEstimate.range(low, high),
            peak,
            EstimateConfidence.ARITHMETIC,
            (
                "ResNet parameter storage with bounded state-dict serialization, Model "
                "metadata, request, and diagnostic overhead; no historical cohort calibration."
            ),
            "Output size varies with the Model architecture and settings.",
        )
    if family == "rf":
        trees = effective_values.get("n_estimators")
        depth = effective_values.get("max_depth")
        if (
            type(trees) is not int
            or trees <= 0
            or depth is not None
            and (type(depth) is not int or depth <= 0)
        ):
            return OperationSizePlan(
                ByteEstimate.unavailable(),
                None,
                EstimateConfidence.INSUFFICIENT_EVIDENCE,
                "Resolved Random Forest structure settings are unavailable.",
                "Can't estimate the output size yet. Check the selected files and settings.",
            )
        sample_nodes = max(1, 2 * snippet_count - 1)
        depth_nodes = (
            sample_nodes if depth is None else min(sample_nodes, 2 ** min(depth + 1, 62) - 1)
        )
        low = max(64 * 1_024, trees * 512)
        high = trees * depth_nodes * 128 + 2 * MIB
        peak = high + 8 * MIB
        return OperationSizePlan(
            ByteEstimate.range(low, high),
            peak,
            EstimateConfidence.ARITHMETIC,
            (
                "Random Forest tree-node ceiling from Dataset rows, tree count and depth, with "
                "bounded Model metadata, request, and diagnostic overhead; no historical cohort "
                "calibration."
            ),
            "Output size varies with the Model structure and settings.",
        )
    raise ValueError("Training storage estimate requires CNN or RF settings.")


__all__ = [
    "estimate_dataset_artifacts",
    "estimate_model_artifacts",
    "training_input_digest",
]
