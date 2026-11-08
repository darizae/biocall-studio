"""Deterministic CPU spectrogram calculation and data-only raster rendering."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

import numpy as np

from bioacoustics_dl_toolbox.visualization.spectrogram import (
    calculate_stft_power,
    rasterize_spectrogram,
)

from biocall_studio.review.domain.sessions import SpectrogramSettingsSnapshot
from biocall_studio.review.domain.spectrograms import (
    CHANNEL_POLICY,
    SPECTROGRAM_ALGORITHM_VERSION,
    SPECTROGRAM_RENDER_VERSION,
    CandidateContext,
    SpectrogramImageTier,
    SpectrogramMetadata,
    SpectrogramRaster,
    SpectrogramSettings,
)


def _settings_json(settings: SpectrogramSettings) -> str:
    return json.dumps(settings.to_mapping(), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class SpectrogramRenderRequest:
    candidate_id: str
    source_sha256: str
    context: CandidateContext
    settings: SpectrogramSettings
    tier: SpectrogramImageTier
    algorithm_version: str = SPECTROGRAM_ALGORITHM_VERSION
    render_version: str = SPECTROGRAM_RENDER_VERSION

    def __post_init__(self) -> None:
        if self.candidate_id != self.context.candidate_id:
            raise ValueError("Spectrogram candidate identity does not match its context.")
        if self.source_sha256 != self.context.source_sha256:
            raise ValueError("Spectrogram source identity does not match its context.")
        if not isinstance(self.settings, SpectrogramSettings):
            raise TypeError("Spectrogram settings are invalid.")
        if not isinstance(self.tier, SpectrogramImageTier):
            raise TypeError("Spectrogram image tier is invalid.")
        for value, label in (
            (self.algorithm_version, "algorithm"),
            (self.render_version, "renderer"),
        ):
            if not isinstance(value, str) or not value or len(value) > 200:
                raise ValueError(f"Spectrogram {label} version is invalid.")

    @classmethod
    def from_snapshot(
        cls,
        *,
        candidate_id: str,
        source_sha256: str,
        context: CandidateContext,
        snapshot: SpectrogramSettingsSnapshot,
        tier: SpectrogramImageTier,
    ) -> SpectrogramRenderRequest:
        if (
            snapshot.algorithm_version != SPECTROGRAM_ALGORITHM_VERSION
            or snapshot.render_version != SPECTROGRAM_RENDER_VERSION
        ):
            raise ValueError("Spectrogram settings use an unsupported renderer version.")
        return cls(
            candidate_id=candidate_id,
            source_sha256=source_sha256,
            context=context,
            settings=SpectrogramSettings.from_mapping(snapshot.effective_settings),
            tier=tier,
            algorithm_version=snapshot.algorithm_version,
            render_version=snapshot.render_version,
        )


def spectrogram_content_key(request: SpectrogramRenderRequest) -> str:
    """Return the complete immutable cache identity without rendering pixels."""
    if not isinstance(request, SpectrogramRenderRequest):
        raise TypeError("Spectrogram render request is invalid.")
    width, height = request.tier.dimensions
    payload = {
        "algorithm_version": request.algorithm_version,
        "render_version": request.render_version,
        "candidate_id": request.candidate_id,
        "source_sha256": request.source_sha256,
        "context": asdict(request.context),
        "settings": request.settings.to_mapping(),
        "channel_policy": CHANNEL_POLICY,
        "tier": request.tier.value,
        "width": width,
        "height": height,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "spec_" + hashlib.sha256(b"biocall-review-spectrogram-v1\n" + encoded).hexdigest()


def render_spectrogram(
    samples: np.ndarray,
    request: SpectrogramRenderRequest,
) -> SpectrogramRaster:
    audio = np.asarray(samples, dtype=np.float64)
    if audio.ndim != 2 or audio.shape != (
        request.context.channels,
        request.context.frame_count,
    ):
        raise ValueError("Spectrogram audio shape does not match verified context metadata.")
    plan = request.settings.resolve(
        sample_rate_hz=request.context.sample_rate_hz,
        available_frames=request.context.frame_count,
    )
    sample_rate = request.context.sample_rate_hz
    width, height = request.tier.dimensions

    # Only NumPy display DSP lives upstream. Studio continues to own the
    # validated source context, settings, cache identity and result metadata.
    spectral = calculate_stft_power(
        audio,
        sample_rate_hz=sample_rate,
        window_samples=plan.window_samples,
        hop_samples=plan.hop_samples,
        n_fft=plan.n_fft,
        remove_dc=True,
        source_start_frame=request.context.context_start_frame,
    )
    raster = rasterize_spectrogram(
        spectral,
        width=width,
        height=height,
        frequency_min_hz=plan.frequency_min_hz,
        frequency_max_hz=plan.frequency_max_hz,
        contrast_db=request.settings.contrast_db,
        palette=request.settings.palette.value,
    )
    metadata = SpectrogramMetadata(
        algorithm_version=request.algorithm_version,
        render_version=request.render_version,
        source_sha256=request.source_sha256,
        candidate_id=request.candidate_id,
        sample_rate_hz=sample_rate,
        channels=request.context.channels,
        source_frame_count=request.context.source_frame_count,
        channel_policy=CHANNEL_POLICY,
        dc_policy="subtract-per-channel-displayed-clip-mean",
        context_start_frame=request.context.context_start_frame,
        context_end_frame=request.context.context_end_frame,
        candidate_start_frame=request.context.candidate_start_frame,
        candidate_end_frame=request.context.candidate_end_frame,
        window_samples=plan.window_samples,
        requested_window_samples=plan.requested_window_samples,
        n_fft=plan.n_fft,
        hop_samples=plan.hop_samples,
        window_function=spectral.window_function,
        frame_centers_x2=raster.frame_centers_x2,
        frequency_centers_hz=raster.frequency_centers_hz,
        frequency_edges_hz=raster.frequency_edges_hz,
        frequency_min_hz=raster.frequency_min_hz,
        frequency_max_hz=raster.frequency_max_hz,
        width=width,
        height=height,
        tier=request.tier,
        palette=request.settings.palette,
        contrast_db=request.settings.contrast_db,
        settings_json=_settings_json(request.settings),
        amplitude_scaling="power-db-relative-to-displayed-band-peak",
        frequency_scale="linear-hz",
        interpolation="linear-power-to-pixel-centres-v1",
        orientation="time-right-frequency-up",
        short_clip_window=plan.short_clip_window,
    )
    return SpectrogramRaster(
        content_key=spectrogram_content_key(request),
        width=width,
        height=height,
        rgb_bytes=raster.rgb_bytes,
        relative_db_f32=raster.relative_db_f32_bytes,
        metadata=metadata,
    )


__all__ = [
    "SpectrogramRenderRequest",
    "render_spectrogram",
    "spectrogram_content_key",
]
