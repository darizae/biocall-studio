"""Trusted, bounded intake of immutable Train Model contracts."""

from __future__ import annotations

import json
import os
import tomllib
from importlib import util as importlib_util
from importlib.metadata import version
from pathlib import Path

from biocall_studio.detect.domain.models import (
    ModelFamily,
    ModelRole,
    ModelSnapshot,
    ScientificEvidenceState,
    VerifiedModelReference,
    _config_items,
    _ConfigItems,
)
from biocall_studio.shared.integrity import sha256_file
from biocall_studio.shared.paths import validate_relative_path
from biocall_studio.train.domain.model import validate_model_manifest
from biocall_studio.train.persistence.collection_metadata import validate_collection_manifest
from biocall_studio.train.persistence.models import (
    structurally_reload_cnn_directory,
    structurally_reload_rf_directory,
)

MAX_MODEL_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_COLLECTION_MANIFEST_BYTES = 16 * 1024 * 1024


def _read_json(path: Path, *, maximum_bytes: int, label: str) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is missing or unsafe.")
    if path.stat().st_size > maximum_bytes:
        raise ValueError(f"{label} exceeds its bounded read limit.")
    try:
        with path.open(encoding="utf-8") as stream:
            raw = json.load(stream)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON.") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object.")
    return raw


def _trusted_train_location(root: Path) -> None:
    models_root = root.parent
    alpaca_root = models_root.parent
    if (
        models_root.name != "models"
        or alpaca_root.name != ".alpaca"
        or models_root.is_symlink()
        or alpaca_root.is_symlink()
    ):
        raise ValueError(
            "Choose a Model from a trusted Train Model location (.alpaca/models)."
        )
    collection_path = alpaca_root / "collection.json"
    collection = _read_json(
        collection_path,
        maximum_bytes=MAX_COLLECTION_MANIFEST_BYTES,
        label="Train Collection manifest",
    )
    try:
        validate_collection_manifest(collection)
    except ValueError as exc:
        raise ValueError("The Model is not inside a verified local Train Collection.") from exc


def _verified_toolbox_import_origin() -> str:
    spec = importlib_util.find_spec("bioacoustics_dl_toolbox")
    if spec is None or spec.origin is None:
        raise ValueError("The verified bioacoustics toolbox runtime is unavailable.")
    origin = Path(spec.origin).resolve(strict=True)
    project_name: str | None = None
    for parent in origin.parents:
        metadata = parent / "pyproject.toml"
        if metadata.is_file():
            try:
                project = tomllib.loads(metadata.read_text(encoding="utf-8")).get("project", {})
            except (OSError, tomllib.TOMLDecodeError) as exc:
                raise ValueError("The toolbox import origin cannot be verified.") from exc
            project_name = project.get("name") if isinstance(project, dict) else None
            break
    if project_name is not None and project_name != "bioacoustics-dl-toolbox":
        raise ValueError("An ambiguous pipeline copy shadows the direct bioacoustics toolbox.")
    if "alpaca-pipelines" in {part.casefold() for part in origin.parts}:
        raise ValueError("An ambiguous pipeline copy shadows the direct bioacoustics toolbox.")
    return str(origin)


def _require_runtime(manifest: dict, family: ModelFamily) -> tuple[tuple[str, str], ...]:
    provenance = manifest["provenance"]
    expected = {
        "biocall-studio": provenance["trainer"]["version"],
        "bioacoustics-dl-toolbox": provenance["toolbox"]["version"],
    }
    if family is ModelFamily.CNN:
        expected["torch"] = provenance["torch_version"]
    else:
        expected.update(
            {
                "scikit-learn": provenance["scikit_learn_version"],
                "joblib": provenance["joblib_version"],
                "librosa": provenance["librosa_version"],
            }
        )
    observed = {name: version(name) for name in expected}
    if expected != observed:
        mismatch = next(name for name in expected if expected[name] != observed[name])
        raise ValueError(
            f"The Model requires a different {mismatch} runtime and cannot be loaded safely."
        )
    return tuple(sorted(observed.items()))


def _contained_artifact(root: Path, manifest: dict) -> Path:
    relative = validate_relative_path(manifest["artifact"]["path"])
    candidate = root / relative
    if candidate.is_symlink():
        raise ValueError("Model artifact cannot be a symlink.")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise FileNotFoundError("The selected Model artifact is missing.") from exc
    if not resolved.is_file() or not resolved.is_relative_to(root):
        raise ValueError("Model artifact escapes its selected folder.")
    artifact = manifest["artifact"]
    if resolved.stat().st_size != artifact["size_bytes"]:
        raise ValueError("Model artifact size disagrees with model.json.")
    if sha256_file(resolved) != artifact["sha256"]:
        raise ValueError("Model artifact digest disagrees with model.json.")
    return resolved


def _load_runtime_structure(root: Path, model_id: str, family: ModelFamily) -> None:
    if family is ModelFamily.CNN:
        structurally_reload_cnn_directory(root, model_id)
    else:
        structurally_reload_rf_directory(root, model_id)


def _snapshot(
    manifest: dict,
    *,
    manifest_sha256: str,
    runtime_versions: tuple[tuple[str, str], ...],
) -> ModelSnapshot:
    family = ModelFamily(manifest["family"])
    artifact = manifest["artifact"]
    input_spec = manifest["input"]
    source_revision = manifest["provenance"]["toolbox"]["revision"]
    token = json.dumps(
        {
            "manifest": manifest_sha256,
            "artifact": artifact["sha256"],
            "family": family.value,
            "runtime": runtime_versions,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    import hashlib

    snapshot_id = f"mdl_{hashlib.sha256(token).hexdigest()[:32]}"
    if family is ModelFamily.CNN:
        transforms = manifest["cnn"]["transforms"]
        role = ModelRole.PRIMARY_DETECTION
        probability_column = None
        feature_family = None
        feature_names: tuple[str, ...] = ()
        feature_config: _ConfigItems = ()
        spectrogram = _config_items(transforms["spectrogram"], label="spectrogram config")
        normalization = _config_items(
            transforms["normalization"], label="normalization config"
        )
        preprocessing = tuple(transforms["preprocessing_order"])
        loader_api = "bioacoustics_dl_toolbox.training.checkpoints.load_model"
        window_duration = input_spec["window_duration_ms"]
        window_samples = input_spec["window_length_samples"]
        frames = input_spec["sequence_length_frames"]
        minimum_duration = None
        short_policy = None
    else:
        rf = manifest["random_forest"]
        features = rf["features"]
        role = ModelRole.INTERVAL_REFINEMENT
        probability_column = rf["estimator"]["target_probability_column"]
        feature_family = features["family"]
        feature_names = tuple(features["names"])
        feature_config = _config_items(features["config"], label="RF feature config")
        spectrogram = ()
        normalization = ()
        preprocessing = tuple(input_spec["preprocessing_order"])
        loader_api = "joblib.load"
        window_duration = None
        window_samples = None
        frames = None
        minimum_duration = float(input_spec["min_duration_s"])
        short_policy = input_spec["short_segment_policy"]
    return ModelSnapshot(
        snapshot_id=snapshot_id,
        model_id=manifest["model_id"],
        label=manifest["label"],
        family=family,
        role=role,
        manifest_version=manifest["schema_version"],
        manifest_sha256=manifest_sha256,
        artifact_relative_path=artifact["path"],
        artifact_size_bytes=artifact["size_bytes"],
        artifact_sha256=artifact["sha256"],
        artifact_format=artifact["format"],
        artifact_format_version=artifact["format_version"],
        class_to_index=(("noise", 0), ("target", 1)),
        positive_class="target",
        positive_output_index=1,
        rf_probability_column=probability_column,
        channel_policy=input_spec["channel_policy"],
        sample_rate_policy=input_spec["sample_rate_policy"],
        sample_rate_hz=input_spec["sample_rate_hz"],
        window_duration_ms=window_duration,
        window_length_samples=window_samples,
        sequence_length_frames=frames,
        minimum_duration_seconds=minimum_duration,
        short_segment_policy=short_policy,
        preprocessing_order=preprocessing,
        spectrogram_config=spectrogram,
        normalization_config=normalization,
        rf_feature_family=feature_family,
        rf_feature_names=feature_names,
        rf_feature_config=feature_config,
        loader_api=loader_api,
        loader_distribution=(
            "bioacoustics-dl-toolbox" if family is ModelFamily.CNN else "joblib"
        ),
        loader_version=(
            version("bioacoustics-dl-toolbox")
            if family is ModelFamily.CNN
            else version("joblib")
        ),
        source_revision=source_revision,
        runtime_versions=runtime_versions,
        trusted=True,
        trust_reason="Verified current Train Collection, contained files, and declared checksums.",
        structure=ScientificEvidenceState.PASSED,
        runtime_loadable=ScientificEvidenceState.PASSED,
        prediction_parity=ScientificEvidenceState.UNPROVEN,
    )


def inspect_model_directory(root: Path) -> VerifiedModelReference:
    """Validate, trust, checksum, and only then structurally deserialize a Train Model."""
    selected = Path(root).expanduser()
    if selected.is_symlink():
        raise ValueError("Model folder cannot be a symlink.")
    try:
        resolved = selected.resolve(strict=True)
    except FileNotFoundError as exc:
        raise FileNotFoundError("The selected Model folder is missing.") from exc
    if not resolved.is_dir() or not os.access(resolved, os.R_OK | os.X_OK):
        raise ValueError("The selected Model folder cannot be read.")
    _trusted_train_location(resolved)
    manifest_path = resolved / "model.json"
    raw = _read_json(
        manifest_path,
        maximum_bytes=MAX_MODEL_MANIFEST_BYTES,
        label="Model manifest",
    )
    manifest = validate_model_manifest(raw)
    if manifest["model_id"] != resolved.name:
        raise ValueError("Model folder identity disagrees with model.json.")
    artifact_path = _contained_artifact(resolved, manifest)
    family = ModelFamily(manifest["family"])
    runtime_versions = _require_runtime(manifest, family)
    _verified_toolbox_import_origin()
    manifest_digest = sha256_file(manifest_path)
    artifact_digest = sha256_file(artifact_path)
    try:
        _load_runtime_structure(resolved, manifest["model_id"], family)
    except Exception as exc:
        raise ValueError(
            "The Model binary is not structurally loadable by the verified runtime."
        ) from exc
    if (
        sha256_file(manifest_path) != manifest_digest
        or artifact_path.stat().st_size != manifest["artifact"]["size_bytes"]
        or sha256_file(artifact_path) != artifact_digest
    ):
        raise ValueError("Model files changed during compatibility inspection.")
    snapshot = _snapshot(
        manifest,
        manifest_sha256=manifest_digest,
        runtime_versions=runtime_versions,
    )
    return VerifiedModelReference(resolved, snapshot)


def recheck_model_reference(reference: VerifiedModelReference) -> VerifiedModelReference:
    """Reject changed bytes before any repeat deserialization, then rerun intake checks."""
    manifest_path = reference.root / "model.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise FileNotFoundError("The selected Model manifest is missing.")
    if sha256_file(manifest_path) != reference.snapshot.manifest_sha256:
        raise ValueError("The Model changed since it was selected; choose it again.")
    artifact = reference.root / reference.snapshot.artifact_relative_path
    if not artifact.is_file() or artifact.is_symlink():
        raise FileNotFoundError("The selected Model artifact is missing.")
    if (
        artifact.stat().st_size != reference.snapshot.artifact_size_bytes
        or sha256_file(artifact) != reference.snapshot.artifact_sha256
    ):
        raise ValueError("The Model changed since it was selected; choose it again.")
    current = inspect_model_directory(reference.root)
    if current.snapshot != reference.snapshot:
        raise ValueError("The Model compatibility evidence changed since it was selected.")
    return current


__all__ = [
    "inspect_model_directory",
    "recheck_model_reference",
]
