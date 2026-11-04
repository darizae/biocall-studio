"""Deterministic CPU spectrogram calculation and data-only raster rendering."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

import numpy as np

from biocall_studio.review.domain.sessions import SpectrogramSettingsSnapshot
from biocall_studio.review.domain.spectrograms import (
    CHANNEL_POLICY,
    SPECTROGRAM_ALGORITHM_VERSION,
    SPECTROGRAM_RENDER_VERSION,
    CandidateContext,
    Palette,
    SpectrogramImageTier,
    SpectrogramMetadata,
    SpectrogramRaster,
    SpectrogramSettings,
)

_PALETTE_STOPS = {
    Palette.MAGMA: np.asarray(
        (
            (0, 0, 4),
            (28, 16, 68),
            (79, 18, 123),
            (129, 37, 129),
            (181, 54, 122),
            (229, 80, 100),
            (251, 135, 97),
            (254, 194, 135),
            (252, 253, 191),
        ),
        dtype=np.float64,
    ),
    Palette.VIRIDIS: np.asarray(
        (
            (68, 1, 84),
            (71, 44, 122),
            (59, 82, 139),
            (44, 113, 142),
            (33, 144, 141),
            (39, 173, 129),
            (92, 200, 99),
            (170, 220, 50),
            (253, 231, 37),
        ),
        dtype=np.float64,
    ),
}


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


def calculate_stft_power(
    samples: np.ndarray,
    *,
    window_samples: int,
    hop_samples: int,
    n_fft: int,
    remove_dc: bool,
) -> tuple[np.ndarray, tuple[int, ...]]:
    """Return channel-power-mean one-sided FFT power and exact doubled centers.

    Frames are full, non-centred, and unpadded at clip borders. FFT tail zero
    padding is controlled only by ``n_fft``. A symmetric Hann is used, matching
    the historical R expression ``0.5 - 0.5*cos(2*pi*k/(N-1))``.
    """

    audio = np.asarray(samples, dtype=np.float64)
    if audio.ndim != 2 or audio.shape[0] < 1 or audio.shape[1] < 1:
        raise ValueError("Spectrogram audio must contain channels and frames.")
    if not np.isfinite(audio).all():
        raise ValueError("Spectrogram audio contains non-finite samples.")
    for value, label in (
        (window_samples, "window"),
        (hop_samples, "hop"),
        (n_fft, "FFT"),
    ):
        if type(value) is not int or value <= 0:
            raise ValueError(f"Spectrogram {label} length is invalid.")
    if window_samples > audio.shape[1]:
        raise ValueError("Spectrogram window exceeds the available clip.")
    if n_fft < window_samples or n_fft & (n_fft - 1):
        raise ValueError("Spectrogram FFT length must be a power of two covering the window.")
    if not isinstance(remove_dc, bool):
        raise TypeError("Spectrogram DC policy is invalid.")

    working = audio - audio.mean(axis=1, keepdims=True) if remove_dc else audio
    starts = np.arange(0, working.shape[1] - window_samples + 1, hop_samples, dtype=np.int64)
    if starts.size == 0:
        starts = np.asarray((0,), dtype=np.int64)
    if window_samples < 3:
        # The symmetric Hann degenerates to all-zero weights at two samples.
        # A rectangular edge window preserves the only real samples without padding.
        window = np.ones(window_samples, dtype=np.float64)
    else:
        positions = np.arange(window_samples, dtype=np.float64)
        window = 0.5 - 0.5 * np.cos(2 * np.pi * positions / (window_samples - 1))

    accumulated = np.zeros((n_fft // 2 + 1, starts.size), dtype=np.float64)
    for channel in working:
        frames = np.stack(
            tuple(channel[int(start) : int(start) + window_samples] for start in starts),
            axis=0,
        )
        transformed = np.fft.rfft(frames * window[np.newaxis, :], n=n_fft, axis=1)
        accumulated += (transformed.real**2 + transformed.imag**2).T
    accumulated /= working.shape[0]
    centers_x2 = tuple(int(2 * start + window_samples - 1) for start in starts)
    return accumulated, centers_x2


def _frequency_edges(
    centers: np.ndarray,
    *,
    lower: float,
    upper: float,
    bin_width: float,
) -> tuple[float, ...]:
    if centers.size == 0:
        return (lower, upper)
    if centers.size == 1:
        return (lower, upper)
    midpoints = (centers[:-1] + centers[1:]) / 2
    edges = np.concatenate(
        (
            np.asarray((max(lower, centers[0] - bin_width / 2),)),
            midpoints,
            np.asarray((min(upper, centers[-1] + bin_width / 2),)),
        )
    )
    edges[0] = lower
    edges[-1] = upper
    return tuple(float(value) for value in edges)


def _resample_power(
    power: np.ndarray,
    *,
    frame_centers: np.ndarray,
    context_frames: int,
    frequencies: np.ndarray,
    frequency_min: float,
    frequency_max: float,
    width: int,
    height: int,
) -> np.ndarray:
    target_frames = (np.arange(width, dtype=np.float64) + 0.5) * context_frames / width
    time_resampled = np.empty((power.shape[0], width), dtype=np.float64)
    for frequency_index, row in enumerate(power):
        time_resampled[frequency_index] = np.interp(
            target_frames,
            frame_centers,
            row,
            left=row[0],
            right=row[-1],
        )
    target_frequencies = frequency_min + (
        (np.arange(height, dtype=np.float64) + 0.5)
        * (frequency_max - frequency_min)
        / height
    )
    raster = np.empty((height, width), dtype=np.float64)
    for column in range(width):
        raster[:, column] = np.interp(
            target_frequencies,
            frequencies,
            time_resampled[:, column],
        )
    return np.flipud(raster)


def _relative_db(power: np.ndarray, contrast_db: int, *, peak: float) -> np.ndarray:
    if not np.isfinite(peak) or peak <= 0:
        return np.full(power.shape, -float(contrast_db), dtype=np.float64)
    relative = np.full(power.shape, -float(contrast_db), dtype=np.float64)
    positive = power > 0
    relative[positive] = 10 * np.log10(power[positive] / peak)
    return np.clip(relative, -float(contrast_db), 0.0)


def _apply_palette(relative_db: np.ndarray, contrast_db: int, palette: Palette) -> bytes:
    normalized = np.clip((relative_db + contrast_db) / contrast_db, 0, 1)
    stops = _PALETTE_STOPS[palette]
    stop_x = np.linspace(0, 1, stops.shape[0])
    rgb = np.empty((*relative_db.shape, 3), dtype=np.uint8)
    for channel in range(3):
        rgb[:, :, channel] = np.rint(
            np.interp(normalized.ravel(), stop_x, stops[:, channel]).reshape(normalized.shape)
        ).astype(np.uint8)
    return rgb.tobytes(order="C")


def _content_key(request: SpectrogramRenderRequest, *, width: int, height: int) -> str:
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
    power, relative_centers_x2 = calculate_stft_power(
        audio,
        window_samples=plan.window_samples,
        hop_samples=plan.hop_samples,
        n_fft=plan.n_fft,
        remove_dc=True,
    )
    sample_rate = request.context.sample_rate_hz
    frequencies = np.arange(power.shape[0], dtype=np.float64) * sample_rate / plan.n_fft
    populated = (frequencies >= plan.frequency_min_hz) & (
        frequencies <= plan.frequency_max_hz
    )
    populated_centers = frequencies[populated]
    bin_width = sample_rate / plan.n_fft
    frequency_edges = _frequency_edges(
        populated_centers,
        lower=float(plan.frequency_min_hz),
        upper=float(plan.frequency_max_hz),
        bin_width=bin_width,
    )
    width, height = request.tier.dimensions
    relative_centers = np.asarray(relative_centers_x2, dtype=np.float64) / 2
    raster_power = _resample_power(
        power,
        frame_centers=relative_centers,
        context_frames=request.context.frame_count,
        frequencies=frequencies,
        frequency_min=float(plan.frequency_min_hz),
        frequency_max=float(plan.frequency_max_hz),
        width=width,
        height=height,
    )
    band_peak = float(np.max(power[populated])) if populated.any() else 0.0
    relative_db = _relative_db(
        raster_power,
        request.settings.contrast_db,
        peak=band_peak,
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
        window_function=(
            "symmetric-hann" if plan.window_samples >= 3 else "short-clip-rectangular"
        ),
        frame_centers_x2=tuple(
            center + 2 * request.context.context_start_frame
            for center in relative_centers_x2
        ),
        frequency_centers_hz=tuple(float(value) for value in populated_centers),
        frequency_edges_hz=frequency_edges,
        frequency_min_hz=float(plan.frequency_min_hz),
        frequency_max_hz=float(plan.frequency_max_hz),
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
        content_key=_content_key(request, width=width, height=height),
        width=width,
        height=height,
        rgb_bytes=_apply_palette(
            relative_db,
            request.settings.contrast_db,
            request.settings.palette,
        ),
        relative_db_f32=np.asarray(relative_db, dtype="<f4").tobytes(order="C"),
        metadata=metadata,
    )


__all__ = [
    "SpectrogramRenderRequest",
    "calculate_stft_power",
    "render_spectrogram",
]
