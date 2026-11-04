from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from biocall_studio.review.domain.intake import EligibleCandidate
from biocall_studio.review.domain.sessions import DEFAULT_PRESET_ID, SpectrogramSettingsSnapshot
from biocall_studio.review.domain.spectrograms import (
    SPECTROGRAM_ALGORITHM_VERSION,
    SPECTROGRAM_RENDER_VERSION,
    Palette,
    SoundDetail,
    SpectrogramImageTier,
    SpectrogramSettings,
    plan_candidate_context,
    validate_spectrogram_content_key,
)
from biocall_studio.review.workflows.spectrograms import (
    SpectrogramRenderRequest,
    calculate_stft_power,
    render_spectrogram,
)


def _candidate(
    *,
    start_frame: int,
    end_frame: int,
    sample_rate_hz: int = 1_000,
    frame_count: int = 10_000,
    channels: int = 1,
) -> EligibleCandidate:
    def frame_ns(frame: int) -> int:
        return (frame * 1_000_000_000 + sample_rate_hz // 2) // sample_rate_hz

    return EligibleCandidate(
        ordinal=0,
        recording_ordinal=0,
        candidate_id="cand_" + "1" * 32,
        recording_ref="rec_" + "2" * 32,
        recording_key="recordings/call.wav",
        source_sha256="3" * 64,
        sample_rate_hz=sample_rate_hz,
        frame_count=frame_count,
        channels=channels,
        start_frame=start_frame,
        end_frame=end_frame,
        start_time_ns=frame_ns(start_frame),
        end_time_ns=frame_ns(end_frame),
        cnn_target_score=0.8,
        rf_target_score=None,
        contributing_windows=1,
    )


def test_context_clamps_exact_frames_and_preserves_one_coordinate_transform():
    """Case: UT-REVW-005."""
    left_candidate = _candidate(start_frame=200, end_frame=1_000)
    left = plan_candidate_context(left_candidate, context_seconds=2)

    assert (left.context_start_frame, left.context_end_frame) == (0, 3_000)
    assert (left.candidate_start_frame, left.candidate_end_frame) == (200, 1_000)
    assert left.context_duration_ns == 3_000_000_000
    assert left.candidate_duration_ns == 800_000_000
    assert left.frame_fraction(200) == pytest.approx(200 / 3_000)
    assert left.frame_fraction(1_000) == pytest.approx(1_000 / 3_000)
    assert left.frame_fraction(0) == 0
    assert left.frame_fraction(3_000) == 1

    right_candidate = _candidate(start_frame=9_500, end_frame=10_000, channels=2)
    right = plan_candidate_context(right_candidate, context_seconds=2)
    assert (right.context_start_frame, right.context_end_frame) == (7_500, 10_000)
    assert right.channels == 2
    assert right.frame_fraction(9_500) == pytest.approx(0.8)
    assert right.frame_fraction(10_000) == 1

    odd_rate = _candidate(
        start_frame=44_101,
        end_frame=44_111,
        sample_rate_hz=44_101,
        frame_count=200_000,
    )
    odd = plan_candidate_context(odd_rate, context_seconds=3)
    assert odd.context_start_frame == 0
    assert odd.context_end_frame == 176_414
    assert odd.candidate_start_time_ns == 1_000_000_000
    assert odd.context_end_time_ns == (
        odd.context_end_frame * 1_000_000_000 + odd.sample_rate_hz // 2
    ) // odd.sample_rate_hz

    with pytest.raises(ValueError, match="context"):
        plan_candidate_context(left_candidate, context_seconds=0)
    with pytest.raises(ValueError, match="outside"):
        left.frame_fraction(-1)
    with pytest.raises(FrozenInstanceError):
        left.context_start_frame = 1  # type: ignore[misc]
    assert left_candidate.start_frame == 200
    assert left_candidate.end_frame == 1_000


def test_explicit_stft_matches_r_reference_and_keys_every_rendering_input():
    """Case: UT-REVW-006."""
    # Independent R reference:
    # w <- .5-.5*cos(2*pi*(0:7)/7); Mod(fft(x*w)[1:5])^2
    signal = np.array([0, 1, 0, -1, 0, 1, 0, -1], dtype=np.float64)
    expected_r_power = np.array(
        [
            0.022791599075738,
            1.08235420046213,
            3.0625,
            1.08235420046213,
            0.022791599075738,
        ]
    )
    mono_power, centers_x2 = calculate_stft_power(
        signal[np.newaxis, :],
        window_samples=8,
        hop_samples=4,
        n_fft=8,
        remove_dc=True,
    )
    stereo_power, stereo_centers_x2 = calculate_stft_power(
        np.stack((signal, -signal)),
        window_samples=8,
        hop_samples=4,
        n_fft=8,
        remove_dc=True,
    )
    np.testing.assert_allclose(mono_power[:, 0], expected_r_power, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(stereo_power, mono_power, rtol=0, atol=0)
    assert centers_x2 == stereo_centers_x2 == (7,)

    balanced = SpectrogramSettings()
    plan = balanced.resolve(sample_rate_hz=48_000, available_frames=240_000)
    assert balanced.sound_detail is SoundDetail.BALANCED
    assert (plan.window_samples, plan.n_fft, plan.hop_samples) == (2_000, 2_048, 1_000)
    assert plan.frequency_max_hz == 4_200

    candidate = _candidate(start_frame=1_000, end_frame=2_000, frame_count=4_000)
    context = plan_candidate_context(candidate, context_seconds=1)
    samples = np.sin(np.arange(context.frame_count) * 2 * np.pi * 100 / 1_000)[None, :]
    request = SpectrogramRenderRequest(
        candidate_id=candidate.candidate_id,
        source_sha256=candidate.source_sha256,
        context=context,
        settings=SpectrogramSettings(
            frequency_max_hz=3_000,
            exact_window_ms=20,
            contrast_db=50,
        ),
        tier=SpectrogramImageTier.THUMBNAIL,
    )
    snapshot = SpectrogramSettingsSnapshot.create(
        preset_id=DEFAULT_PRESET_ID,
        preset_name="Default",
        preset_revision=1,
        algorithm_version=SPECTROGRAM_ALGORITHM_VERSION,
        render_version=SPECTROGRAM_RENDER_VERSION,
        effective_settings=request.settings.to_mapping(),
    )
    assert SpectrogramRenderRequest.from_snapshot(
        candidate_id=candidate.candidate_id,
        source_sha256=candidate.source_sha256,
        context=context,
        snapshot=snapshot,
        tier=SpectrogramImageTier.THUMBNAIL,
    ) == request
    legacy_snapshot = SpectrogramSettingsSnapshot.create(
        preset_id=DEFAULT_PRESET_ID,
        preset_name="Default",
        preset_revision=1,
        algorithm_version="old-algorithm",
        render_version="old-renderer",
        effective_settings=request.settings.to_mapping(),
    )
    with pytest.raises(ValueError, match="unsupported renderer"):
        SpectrogramRenderRequest.from_snapshot(
            candidate_id=candidate.candidate_id,
            source_sha256=candidate.source_sha256,
            context=context,
            snapshot=legacy_snapshot,
            tier=SpectrogramImageTier.THUMBNAIL,
        )
    rendered = render_spectrogram(samples, request)

    assert rendered.width == 320
    assert rendered.height == 120
    assert len(rendered.rgb_bytes) == 320 * 120 * 3
    assert rendered.metadata.orientation == "time-right-frequency-up"
    assert rendered.metadata.amplitude_scaling == "power-db-relative-to-displayed-band-peak"
    assert rendered.metadata.frequency_scale == "linear-hz"
    assert rendered.metadata.source_frame_count == candidate.frame_count
    assert rendered.metadata.settings_json
    assert rendered.metadata.context_start_frame == context.context_start_frame
    assert rendered.metadata.context_end_frame == context.context_end_frame
    assert rendered.metadata.candidate_x_edges == pytest.approx(
        (context.frame_fraction(1_000), context.frame_fraction(2_000))
    )
    assert rendered.metadata.frequency_min_hz == 0
    assert rendered.metadata.frequency_max_hz == 500
    assert rendered.metadata.frame_centers_x2
    assert rendered.metadata.frequency_centers_hz
    assert validate_spectrogram_content_key(rendered.content_key) == rendered.content_key

    short_candidate = _candidate(
        start_frame=0,
        end_frame=2,
        sample_rate_hz=1_000,
        frame_count=2,
    )
    short_context = plan_candidate_context(short_candidate, context_seconds=1)
    short = render_spectrogram(
        np.asarray(((-1.0, 1.0),)),
        SpectrogramRenderRequest(
            candidate_id=short_candidate.candidate_id,
            source_sha256=short_candidate.source_sha256,
            context=short_context,
            settings=SpectrogramSettings(frequency_max_hz=3_000, exact_window_ms=20),
            tier=SpectrogramImageTier.THUMBNAIL,
        ),
    )
    assert short.metadata.short_clip_window
    assert short.metadata.window_function == "short-clip-rectangular"
    assert max(short.relative_db) > -short.metadata.contrast_db
    silence = render_spectrogram(
        np.zeros((1, 2)),
        SpectrogramRenderRequest(
            candidate_id=short_candidate.candidate_id,
            source_sha256=short_candidate.source_sha256,
            context=short_context,
            settings=SpectrogramSettings(frequency_max_hz=3_000, exact_window_ms=20),
            tier=SpectrogramImageTier.THUMBNAIL,
        ),
    )
    assert set(silence.relative_db) == {-50.0}

    palette_key = render_spectrogram(
        samples,
        SpectrogramRenderRequest(
            candidate_id=candidate.candidate_id,
            source_sha256=candidate.source_sha256,
            context=context,
            settings=SpectrogramSettings(
                frequency_max_hz=3_000,
                exact_window_ms=20,
                contrast_db=50,
                palette=Palette.VIRIDIS,
            ),
            tier=SpectrogramImageTier.THUMBNAIL,
        ),
    ).content_key
    detail_key = render_spectrogram(
        samples,
        SpectrogramRenderRequest(
            candidate_id=candidate.candidate_id,
            source_sha256=candidate.source_sha256,
            context=context,
            settings=request.settings,
            tier=SpectrogramImageTier.DETAIL,
        ),
    ).content_key
    version_key = render_spectrogram(
        samples,
        SpectrogramRenderRequest(
            candidate_id=candidate.candidate_id,
            source_sha256=candidate.source_sha256,
            context=context,
            settings=request.settings,
            tier=SpectrogramImageTier.THUMBNAIL,
            render_version="review-raster-test-v2",
        ),
    ).content_key
    assert len({rendered.content_key, palette_key, detail_key, version_key}) == 4

    for invalid in (
        {"frequency_max_hz": 0},
        {"frequency_min_hz": 300, "frequency_max_hz": 300},
        {"contrast_db": float("nan")},
        {"context_seconds": 4},
        {"overlap_percent": 60},
        {"exact_window_ms": 21},
    ):
        with pytest.raises((TypeError, ValueError)):
            SpectrogramSettings(**invalid)
    for invalid_key in ("", "spec_bad", "spec_" + "0" * 63, "spec_" + "g" * 64):
        with pytest.raises(ValueError, match="identity"):
            validate_spectrogram_content_key(invalid_key)
