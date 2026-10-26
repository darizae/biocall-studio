"""Genuine bounded CNN Training and immutable Model publication."""

from __future__ import annotations

import logging
import os
import random
import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from bioacoustics_dl_toolbox.audio.datasets import SpectrogramDataset
from bioacoustics_dl_toolbox.audio.preprocessing import spectrogram_frames_for_samples
from bioacoustics_dl_toolbox.config import (
    AugmentationConfig,
    ClassifierConfig,
    EncoderConfig,
    NormalizationConfig,
    SpectrogramConfig,
    TaskConfig,
    TrainingConfig,
)
from bioacoustics_dl_toolbox.metrics import Accuracy, F1Score, Precision, Recall
from bioacoustics_dl_toolbox.metrics.auc import AUCMeter
from bioacoustics_dl_toolbox.models import Classifier, ResidualEncoder
from bioacoustics_dl_toolbox.training.checkpoints import save_model
from bioacoustics_dl_toolbox.training.trainer import Trainer

from alpaca_desktop.domain.model import MODEL_SCIENTIFIC_REFERENCE, MODEL_TOOLBOX_REVISION
from alpaca_desktop.domain.paths import validate_relative_path
from alpaca_desktop.domain.training import (
    DeviceCapabilities,
    FrozenTrainingConfig,
    TrainingDataset,
    verify_frozen_training_config,
)
from alpaca_desktop.persistence.datasets import DatasetArtifact, load_dataset
from alpaca_desktop.persistence.integrity import sha256_file
from alpaca_desktop.persistence.models import (
    ModelArtifact,
    load_model,
    structurally_reload_cnn_directory,
)
from alpaca_desktop.workflows.model_publication import (
    publish_model_directory,
    write_model_manifest,
)


class CnnTrainingError(RuntimeError):
    pass


class CnnTrainingCancelled(CnnTrainingError):
    pass


@dataclass(frozen=True)
class CnnTrainingRequest:
    run_id: str
    request_id: str
    collection_root: str
    collection_id: str
    config: FrozenTrainingConfig
    model_id: str
    model_label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "run_id": self.run_id,
            "request_id": self.request_id,
            "collection_root": self.collection_root,
            "collection_id": self.collection_id,
            "config": self.config.to_worker_snapshot(),
            "model_id": self.model_id,
            "model_label": self.model_label,
        }

    @classmethod
    def from_dict(cls, raw: object) -> CnnTrainingRequest:
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise ValueError("Unsupported CNN Training request schema.")
        if set(raw) != {
            "schema_version",
            "run_id",
            "request_id",
            "collection_root",
            "collection_id",
            "config",
            "model_id",
            "model_label",
        }:
            raise ValueError("CNN Training request fields do not match its schema.")
        for field in ("run_id", "request_id", "collection_root", "collection_id", "model_id"):
            if not isinstance(raw[field], str) or not raw[field]:
                raise ValueError(f"CNN Training request {field} is invalid.")
        for field in ("run_id", "request_id", "collection_id", "model_id"):
            safe = validate_relative_path(raw[field])
            if "/" in safe:
                raise ValueError(f"CNN Training request {field} must be one path segment.")
        label = raw["model_label"]
        if (
            not isinstance(label, str)
            or not label.strip()
            or len(label.strip()) > 80
            or any(ord(character) < 32 for character in label)
        ):
            raise ValueError("CNN Model display name must be 1 to 80 printable characters.")
        root = Path(raw["collection_root"])
        if not root.is_absolute():
            raise ValueError("CNN Training request Collection root must be absolute.")
        config = FrozenTrainingConfig.from_worker_snapshot(raw["config"])
        if config.family != "cnn":
            raise ValueError("CNN Training request requires a CNN configuration.")
        return cls(
            raw["run_id"],
            raw["request_id"],
            raw["collection_root"],
            raw["collection_id"],
            config,
            raw["model_id"],
            label.strip(),
        )


class _HistoryCollector(logging.Handler):
    def __init__(self, callback: Callable[[dict[str, Any]], None] | None):
        super().__init__()
        self.callback = callback
        self.history: dict[str, list[dict[str, float | int]]] = {"train": [], "val": []}

    def emit(self, record: logging.LogRecord) -> None:
        parts = record.getMessage().split("|")
        if len(parts) < 3 or parts[0] not in self.history:
            return
        try:
            epoch = int(parts[1]) + 1
            values = {
                key: float(value)
                for part in parts[2:]
                if ":" in part
                for key, value in (part.split(":", 1),)
                if key in {"loss", "accuracy", "precision", "recall", "f1"}
            }
        except (TypeError, ValueError):
            return
        if "loss" not in values or any(not np.isfinite(value) for value in values.values()):
            return
        row: dict[str, float | int] = {"epoch": epoch, **values}
        self.history[parts[0]].append(row)
        if self.callback is not None:
            self.callback({"phase": parts[0], **row})


def _check_cancelled(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        raise CnnTrainingCancelled("CNN Training cancelled before Model publication.")


def _configs(values: dict[str, object]):
    spectrogram = SpectrogramConfig(
        sample_rate=int(values["spectrogram.sample_rate"]),
        preemphasis=float(values["spectrogram.preemphasis"]),
        n_fft=int(values["spectrogram.n_fft"]),
        hop_length=int(values["spectrogram.hop_length"]),
        n_freq_bins=int(values["spectrogram.n_freq_bins"]),
        f_min=int(values["spectrogram.f_min"]),
        f_max=int(values["spectrogram.f_max"]),
        freq_compression=str(values["spectrogram.freq_compression"]),
        min_level_db=float(values["spectrogram.min_level_db"]),
        ref_level_db=float(values["spectrogram.ref_level_db"]),
    )
    normalization = NormalizationConfig(
        mode=str(values["normalization.mode"]),
        min_level_db=float(values["normalization.min_level_db"]),
        ref_level_db=float(values["normalization.ref_level_db"]),
    )
    augmentation = AugmentationConfig(
        enabled=bool(values["augmentation.enabled"]),
        amplitude_increase_db=int(values["augmentation.amplitude_increase_db"]),
        amplitude_decrease_db=int(values["augmentation.amplitude_decrease_db"]),
        time_stretch_from=float(values["augmentation.time_stretch_from"]),
        time_stretch_to=float(values["augmentation.time_stretch_to"]),
        pitch_shift_from=float(values["augmentation.pitch_shift_from"]),
        pitch_shift_to=float(values["augmentation.pitch_shift_to"]),
        noise_files=[],
        noise_min_snr=int(values["augmentation.noise_min_snr"]),
        noise_max_snr=int(values["augmentation.noise_max_snr"]),
    )
    encoder = EncoderConfig(
        input_channels=int(values["encoder.input_channels"]),
        conv_kernel_size=int(values["encoder.conv_kernel_size"]),
        max_pool=int(values["encoder.max_pool"]),
        resnet_size=int(values["encoder.resnet_size"]),
    )
    training = TrainingConfig(
        max_epochs=int(values["training.max_epochs"]),
        batch_size=int(values["training.batch_size"]),
        num_workers=int(values["training.num_workers"]),
        learning_rate=float(values["training.learning_rate"]),
        beta1=float(values["training.beta1"]),
        lr_patience_epochs=int(values["training.lr_patience_epochs"]),
        lr_decay_factor=float(values["training.lr_decay_factor"]),
        early_stopping_patience_epochs=int(values["training.early_stopping_patience_epochs"]),
        epochs_per_eval=int(values["training.epochs_per_eval"]),
        val_metric=str(values["training.val_metric"]),
        val_metric_mode=str(values["training.val_metric_mode"]),
        use_cuda=values["device"] == "cuda",
        pin_memory=bool(values["training.pin_memory"]),
    )
    return spectrogram, normalization, augmentation, encoder, training


def _cache_directory(root: Path, dataset_id: str, enabled: bool) -> str | None:
    if not enabled:
        return None
    cache = root / ".alpaca" / "cache" / "spectrograms" / dataset_id
    if cache.is_symlink():
        raise CnnTrainingError("Spectrogram cache cannot use a symlink.")
    cache.mkdir(parents=True, exist_ok=True)
    if not cache.resolve(strict=True).is_relative_to((root / ".alpaca").resolve(strict=True)):
        raise CnnTrainingError("Spectrogram cache escapes app-owned storage.")
    return str(cache)


def _datasets(
    artifact: DatasetArtifact,
    spectrogram: SpectrogramConfig,
    normalization: NormalizationConfig,
    augmentation: AugmentationConfig,
    sequence_length: int,
    cache_dir: str | None,
):
    task = TaskConfig(task_type="binary")
    mapping = {"noise": 0, "target": 1}

    def create(split: str, aug: AugmentationConfig) -> SpectrogramDataset:
        rows = [row for row in artifact.snippets if row["split"] == split]
        return SpectrogramDataset(
            file_names=[row["relative_path"] for row in rows],
            working_dir=str(artifact.root),
            spec_config=spectrogram,
            norm_config=normalization,
            aug_config=aug,
            classes=["noise", "target"],
            sequence_length=sequence_length,
            labels=[row["label"] for row in rows],
            class_to_index=mapping,
            positive_class="target",
            cache_dir=cache_dir,
            dataset_name=split,
            task_config=task,
        )

    return create("train", augmentation), create("val", AugmentationConfig(enabled=False))


def _final_metrics(model, loader, device: torch.device, cancelled):
    loss_fn = nn.CrossEntropyLoss(reduction="sum")
    total_loss = 0.0
    total = 0
    labels: list[torch.Tensor] = []
    predictions: list[torch.Tensor] = []
    scores: list[torch.Tensor] = []
    model.eval()
    with torch.no_grad():
        for features, label in loader:
            _check_cancelled(cancelled)
            features = features.to(device)
            targets = label["call"].to(device, dtype=torch.int64)
            output = model(features)
            total_loss += float(loss_fn(output, targets).item())
            total += int(targets.numel())
            labels.append(targets.cpu())
            predictions.append(torch.argmax(output, dim=1).cpu())
            scores.append(nn.functional.softmax(output, dim=1)[:, 1].cpu())
    if not total:
        raise CnnTrainingError("Validation Split produced no examples.")
    actual = torch.cat(labels)
    predicted = torch.cat(predictions)
    probabilities = torch.cat(scores)
    accuracy = Accuracy()
    precision = Precision()
    recall = Recall()
    f1 = F1Score()
    for metric in (accuracy, precision, recall, f1):
        metric.update(actual, predicted)
    tp = int(((actual == 1) & (predicted == 1)).sum().item())
    fp = int(((actual == 0) & (predicted == 1)).sum().item())
    fn = int(((actual == 1) & (predicted == 0)).sum().item())

    def defined(value: float | None, reason: str | None = None) -> dict[str, Any]:
        return {"value": value, "reason": reason}

    precision_value = None if tp + fp == 0 else float(precision.get())
    recall_value = None if tp + fn == 0 else float(recall.get())
    f1_value = (
        None if precision_value is None or recall_value is None or tp == 0 else float(f1.get())
    )
    if set(actual.tolist()) == {0, 1}:
        auc = AUCMeter()
        auc.add(probabilities, actual)
        auc_value: float | None = float(auc.value()[0])
        auc_reason = None
    else:
        auc_value = None
        auc_reason = "Validation Split does not contain both classes."
    metrics = {
        "accuracy": defined(float(accuracy.get())),
        "precision": defined(
            precision_value,
            None if precision_value is not None else "No target predictions were produced.",
        ),
        "recall": defined(
            recall_value,
            None if recall_value is not None else "Validation contains no target examples.",
        ),
        "f1": defined(
            f1_value,
            None if f1_value is not None else "F1 is undefined without target true positives.",
        ),
        "roc_auc": defined(auc_value, auc_reason),
    }
    return total_loss / total, metrics


def _selected_epoch(history: dict[str, list[dict[str, Any]]], config: TrainingConfig) -> int:
    rows = history["val"]
    key = "loss" if config.val_metric == "loss" else config.val_metric
    candidates = [row for row in rows if key in row]
    if not candidates:
        return int(rows[-1]["epoch"])
    choose = min if config.val_metric_mode == "min" else max
    return int(choose(candidates, key=lambda row: float(row[key]))["epoch"])


def train_cnn_model(
    collection_root: Path,
    request: CnnTrainingRequest,
    *,
    cancelled: Callable[[], bool] | None = None,
    progress: Callable[[int, int, str], None] | None = None,
    measurement: Callable[[dict[str, Any]], None] | None = None,
) -> ModelArtifact:
    """Train, validate, stage, structurally reload, and exclusively publish one CNN Model."""
    root = collection_root.resolve(strict=True)
    if str(root) != str(Path(request.collection_root).resolve(strict=True)):
        raise CnnTrainingError("CNN Training request Collection path changed.")
    safe_model_id = validate_relative_path(request.model_id)
    if "/" in safe_model_id:
        raise ValueError("Model ID must be one portable path segment.")
    alpaca = root / ".alpaca"
    if alpaca.is_symlink() or not alpaca.is_dir():
        raise CnnTrainingError("Validated Collection metadata folder is missing or unsafe.")
    models_root = alpaca / "models"
    staging_root = alpaca / ".staging"
    for directory in (models_root, staging_root):
        if directory.is_symlink():
            raise CnnTrainingError("App-owned Model storage cannot use symlinks.")
        directory.mkdir(exist_ok=True)
    final = models_root / safe_model_id
    if final.exists():
        raise FileExistsError(f"Model already exists: {safe_model_id}")
    stage_container = staging_root / f"{safe_model_id}-{request.request_id}"
    stage = stage_container / safe_model_id
    if stage_container.exists():
        raise FileExistsError("CNN Model staging output already exists.")
    stage.mkdir(parents=True)
    try:
        _check_cancelled(cancelled)
        if progress is not None:
            progress(0, 3, "Validating immutable Dataset")
        artifact = load_dataset(root, request.config.dataset_id)
        dataset_digest = sha256_file(artifact.root / "dataset.json")
        dataset = TrainingDataset.from_artifact(artifact)
        capabilities = DeviceCapabilities.detect()
        verify_frozen_training_config(request.config, dataset, capabilities)
        values = dict(request.config.effective_values)
        if values["device"] not in {"cpu", "cuda"}:
            raise CnnTrainingError("Verified CNN executor supports CPU or CUDA only.")
        if values["device"] == "cuda" and not torch.cuda.is_available():
            raise CnnTrainingError("CUDA is unavailable in the CNN Worker.")

        seed = int(artifact.manifest["config"]["seed"])
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            pass
        spectrogram, normalization, augmentation, encoder_config, training_config = _configs(values)
        window_samples = round(int(values["sequence_length_ms"]) * spectrogram.sample_rate / 1_000)
        sequence_frames = spectrogram_frames_for_samples(window_samples, spectrogram)
        cache_dir = _cache_directory(root, artifact.dataset_id, bool(values["spectrogram_cache"]))
        train_dataset, val_dataset = _datasets(
            artifact,
            spectrogram,
            normalization,
            augmentation,
            sequence_frames,
            cache_dir,
        )
        generator = torch.Generator().manual_seed(seed)
        train_loader = torch.utils.data.DataLoader(
            train_dataset,
            batch_size=training_config.batch_size,
            shuffle=True,
            num_workers=training_config.num_workers,
            pin_memory=training_config.pin_memory,
            generator=generator,
        )
        val_loader = torch.utils.data.DataLoader(
            val_dataset,
            batch_size=training_config.batch_size,
            shuffle=False,
            num_workers=training_config.num_workers,
            pin_memory=training_config.pin_memory,
        )
        _check_cancelled(cancelled)
        if progress is not None:
            progress(1, 18, "Prepared train and val spectrogram batches")
        encoder = ResidualEncoder(encoder_config)
        classifier_config = ClassifierConfig(
            input_channels=encoder.output_channels,
            pooling=str(values["classifier.pooling"]),
            num_classes=2,
        )
        if classifier_config.input_channels != int(values["classifier.input_channels"]):
            raise CnnTrainingError("Resolved classifier input width disagrees with the encoder.")
        classifier = Classifier(classifier_config)
        model = nn.Sequential(encoder, classifier)
        device = torch.device(str(values["device"]))
        loss_fn = nn.CrossEntropyLoss()
        optimizer = torch.optim.Adam(
            model.parameters(),
            lr=training_config.learning_rate,
            betas=(training_config.beta1, 0.999),
        )
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer,
            mode=training_config.val_metric_mode,
            patience=training_config.lr_patience_epochs,
            factor=training_config.lr_decay_factor,
        )
        logger = logging.getLogger(f"alpaca_desktop.cnn.{request.run_id}")
        logger.handlers.clear()
        logger.propagate = False
        logger.setLevel(logging.DEBUG if values["logging_level"] == "debug" else logging.INFO)
        collector = _HistoryCollector(measurement)
        logger.addHandler(collector)
        trainer = Trainer(
            model=model,
            logger=logger,
            prefix=request.run_id,
            checkpoint_dir=None,
            summary_dir=None,
            start_scratch=True,
            task_config=TaskConfig(task_type="binary"),
        )

        def epoch_callback(current: int, total: int, phase: str) -> None:
            if progress is not None:
                progress(
                    2,
                    min(82, 18 + round(64 * current / max(1, total))),
                    f"Epoch {current} of {total} · {phase}",
                )

        model = trainer.fit(
            train_loader=train_loader,
            val_loader=val_loader,
            test_loader=None,
            loss_fn=loss_fn,
            optimizer=optimizer,
            scheduler=scheduler,
            n_epochs=training_config.max_epochs,
            val_interval=training_config.epochs_per_eval,
            patience_early_stopping=training_config.early_stopping_patience_epochs,
            device=device,
            metrics={
                "accuracy": Accuracy(device=device),
                "f1": F1Score(device=device),
                "precision": Precision(device=device),
                "recall": Recall(device=device),
            },
            val_metric=training_config.val_metric,
            val_metric_mode=training_config.val_metric_mode,
            checkpoint=lambda: _check_cancelled(cancelled),
            epoch_callback=epoch_callback,
        )
        if not collector.history["train"] or not collector.history["val"]:
            raise CnnTrainingError("CNN trainer did not emit measured train and val history.")
        _check_cancelled(cancelled)
        if progress is not None:
            progress(2, 84, "Evaluating selected CNN checkpoint on val")
        _final_val_loss, final_metrics = _final_metrics(model, val_loader, device, cancelled)
        selected_epoch = _selected_epoch(collector.history, training_config)

        checkpoint = stage / "model.pt"
        save_model(
            model,
            encoder,
            encoder_config,
            classifier,
            classifier_config,
            spectrogram,
            checkpoint,
            {"noise": 0, "target": 1},
            metadata={
                "schema_version": 2,
                "task_type": "binary",
                "normalization_config": asdict(normalization),
                "window_length_samples": window_samples,
                "sequence_length_frames": sequence_frames,
                "class_names": ["noise", "target"],
            },
        )
        with checkpoint.open("rb") as stream:
            os.fsync(stream.fileno())
        _check_cancelled(cancelled)
        reopened_dataset = load_dataset(root, artifact.dataset_id)
        if sha256_file(reopened_dataset.root / "dataset.json") != dataset_digest:
            raise CnnTrainingError("Dataset manifest changed during CNN Training.")
        manifest = {
            "schema_version": 1,
            "model_id": safe_model_id,
            "label": request.model_label,
            "family": "cnn",
            "created_at": datetime.now(UTC).isoformat(),
            "run_id": request.run_id,
            "request_id": request.request_id,
            "dataset_id": artifact.dataset_id,
            "dataset_reference": f"datasets/{artifact.dataset_id}",
            "dataset_manifest_sha256": dataset_digest,
            "task": {
                "type": "binary_single_label",
                "class_to_index": {"noise": 0, "target": 1},
                "positive_class": "target",
                "num_classes": 2,
                "output": "categorical_logits",
            },
            "input": {
                "channel_policy": "mixdown_mono",
                "sample_rate_policy": "resample_to_model_rate",
                "sample_rate_hz": spectrogram.sample_rate,
                "window_duration_ms": int(values["sequence_length_ms"]),
                "window_length_samples": window_samples,
                "sequence_length_frames": sequence_frames,
                "time_unit": "milliseconds",
                "sample_rounding": "nearest_integer_sample",
            },
            "resolved_config": request.config.to_worker_snapshot(),
            "cnn": {
                "architecture": {
                    "encoder": asdict(encoder_config),
                    "classifier": asdict(classifier_config),
                },
                "transforms": {
                    "spectrogram": asdict(spectrogram),
                    "normalization": asdict(normalization),
                    "augmentation": {
                        "training": asdict(augmentation),
                        "validation": {"enabled": False},
                    },
                    "preprocessing_order": [
                        "mono",
                        "resample",
                        "preemphasis",
                        "power_spectrogram",
                        "frequency_compression",
                        "normalization",
                        "fixed_window",
                    ],
                },
                "training": {
                    "seed": seed,
                    "device": str(device),
                    "optimizer": {
                        "name": "Adam",
                        "learning_rate": training_config.learning_rate,
                        "beta1": training_config.beta1,
                    },
                    "objective": "CrossEntropyLoss",
                },
            },
            "results": {
                "split_counts": {
                    split: {
                        label: artifact.manifest["counts"][split][label]
                        for label in ("noise", "target")
                    }
                    for split in ("train", "val")
                },
                "history": collector.history,
                "metrics": final_metrics,
                "selected_epoch": selected_epoch,
            },
            "artifact": {
                "path": "model.pt",
                "size_bytes": checkpoint.stat().st_size,
                "sha256": sha256_file(checkpoint),
                "format": "bioacoustics-dl-toolbox-pytorch",
                "format_version": 2,
            },
            "provenance": {
                "trainer": {
                    "distribution": "alpaca-desktop",
                    "version": version("alpaca-desktop"),
                },
                "toolbox": {
                    "distribution": "bioacoustics-dl-toolbox",
                    "version": version("bioacoustics-dl-toolbox"),
                    "revision": MODEL_TOOLBOX_REVISION,
                },
                "torch_version": torch.__version__,
                "scientific_reference": MODEL_SCIENTIFIC_REFERENCE,
            },
        }
        if progress is not None:
            progress(3, 91, "Verifying staged CNN Model")
        write_model_manifest(stage / "model.json", manifest)
        structurally_reload_cnn_directory(stage, safe_model_id)
        _check_cancelled(cancelled)
        if progress is not None:
            progress(3, 98, "Publishing verified CNN Model")
        publish_model_directory(stage, final)
        return load_model(root, safe_model_id)
    except InterruptedError as exc:
        raise CnnTrainingCancelled("CNN Training cancelled before Model publication.") from exc
    finally:
        if stage_container.exists():
            shutil.rmtree(stage_container)
