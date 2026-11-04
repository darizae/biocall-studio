from __future__ import annotations

import hashlib
import io
import math
import struct
import wave
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QMediaPlayer

from biocall_studio.review.domain.intake import EligibleCandidate
from biocall_studio.review.domain.spectrograms import (
    SpectrogramImageTier,
    SpectrogramSettings,
)
from biocall_studio.review.gui.audio_proof import (
    AudioSpectrogramItem,
    AudioSpectrogramProof,
    PlaybackBackend,
    QtMediaPlayback,
)
from biocall_studio.review.workflows.audio import (
    AudioSourceError,
    AudioSourceProblem,
    read_candidate_audio,
)
from biocall_studio.review.workflows.spectrograms import (
    SpectrogramRenderRequest,
    render_spectrogram,
)

pytestmark = pytest.mark.integration


def _pcm_sample(value: int, width: int) -> bytes:
    if width == 1:
        return bytes((max(0, min(255, value + 128)),))
    if width == 2:
        return struct.pack("<h", max(-32_768, min(32_767, value * 256)))
    if width == 3:
        scaled = max(-(1 << 23), min((1 << 23) - 1, value * 65_536))
        return int(scaled).to_bytes(3, "little", signed=True)
    if width == 4:
        return struct.pack("<i", value * 16_777_216)
    raise AssertionError(width)


def _write_pcm(
    path: Path,
    *,
    frames: int,
    rate: int,
    channels: int,
    width: int,
    opposed: bool = False,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = bytearray()
    for frame in range(frames):
        value = round(100 * math.sin(2 * math.pi * 500 * frame / rate))
        for channel in range(channels):
            channel_value = -value if opposed and channel % 2 else value
            payload.extend(_pcm_sample(channel_value, width))
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(width)
        stream.setframerate(rate)
        stream.writeframes(payload)
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate(
    source_root: Path,
    source: Path,
    *,
    start_frame: int,
    end_frame: int,
    rate: int,
    frame_count: int,
    channels: int,
    digest: str | None = None,
    token: str = "1",
) -> EligibleCandidate:
    def frame_ns(frame: int) -> int:
        return (frame * 1_000_000_000 + rate // 2) // rate

    return EligibleCandidate(
        ordinal=0,
        recording_ordinal=0,
        candidate_id="cand_" + token * 32,
        recording_ref="rec_" + "2" * 32,
        recording_key=source.relative_to(source_root).as_posix(),
        source_sha256=digest or _sha256(source),
        sample_rate_hz=rate,
        frame_count=frame_count,
        channels=channels,
        start_frame=start_frame,
        end_frame=end_frame,
        start_time_ns=frame_ns(start_frame),
        end_time_ns=frame_ns(end_frame),
        cnn_target_score=0.9,
        rf_target_score=None,
        contributing_windows=1,
    )


def _wav_payload(value: bytes) -> tuple[int, int, int, int, bytes]:
    with wave.open(io.BytesIO(value), "rb") as stream:
        facts = (
            stream.getnchannels(),
            stream.getsampwidth(),
            stream.getframerate(),
            stream.getnframes(),
        )
        return (*facts, stream.readframes(stream.getnframes()))


def test_real_pcm_context_and_spectrogram_are_exact_and_non_mutating(tmp_path):
    """Case: IT-REVW-004."""
    source_root = tmp_path / "source"
    source = _write_pcm(
        source_root / "recordings" / "opposed.wav",
        frames=48_000,
        rate=8_000,
        channels=2,
        width=2,
        opposed=True,
    )
    original = source.read_bytes()
    candidate = _candidate(
        source_root,
        source,
        start_frame=800,
        end_frame=1_600,
        rate=8_000,
        frame_count=48_000,
        channels=2,
    )
    audio = read_candidate_audio(source_root, candidate, context_seconds=1)

    assert (audio.context.context_start_frame, audio.context.context_end_frame) == (0, 9_600)
    assert audio.samples.shape == (2, 9_600)
    assert not audio.samples.flags.writeable
    assert np.max(np.abs(audio.samples[0] + audio.samples[1])) < 1e-12
    assert _wav_payload(audio.wav_bytes)[:4] == (2, 2, 8_000, 9_600)
    with wave.open(str(source), "rb") as stream:
        expected_pcm = stream.readframes(9_600)
    assert _wav_payload(audio.wav_bytes)[4] == expected_pcm

    rendered = render_spectrogram(
        audio.samples,
        SpectrogramRenderRequest(
            candidate_id=candidate.candidate_id,
            source_sha256=candidate.source_sha256,
            context=audio.context,
            settings=SpectrogramSettings(
                frequency_max_hz=3_000,
                exact_window_ms=20,
                contrast_db=50,
            ),
            tier=SpectrogramImageTier.THUMBNAIL,
        ),
    )
    assert -3 < max(rendered.relative_db) <= 0
    assert rendered.metadata.candidate_x_edges == pytest.approx((800 / 9_600, 1_600 / 9_600))
    assert rendered.metadata.frequency_max_hz == 3_000
    assert source.read_bytes() == original

    for width, rate in zip((1, 2, 3, 4), (8_000, 16_000, 48_000, 96_000), strict=True):
        frames = max(1_000, rate // 8)
        pcm = _write_pcm(
            source_root / "recordings" / f"pcm-{width}.wav",
            frames=frames,
            rate=rate,
            channels=1,
            width=width,
        )
        row = _candidate(
            source_root,
            pcm,
            start_frame=100,
            end_frame=200,
            rate=rate,
            frame_count=frames,
            channels=1,
            token=str(width),
        )
        decoded = read_candidate_audio(source_root, row, context_seconds=1)
        assert decoded.sample_width_bytes == width
        assert decoded.samples.shape == (1, frames)
        assert np.isfinite(decoded.samples).all()

    stale_digest = candidate.source_sha256
    source.write_bytes(original[:-2] + b"\0\0")
    with pytest.raises(AudioSourceError) as changed:
        read_candidate_audio(source_root, candidate, context_seconds=1)
    assert changed.value.problem is AudioSourceProblem.CHANGED
    source.write_bytes(original)
    assert _sha256(source) == stale_digest
    with pytest.raises(AudioSourceError) as cancelled:
        read_candidate_audio(
            source_root,
            candidate,
            context_seconds=1,
            cancelled=lambda: True,
        )
    assert cancelled.value.problem is AudioSourceProblem.CANCELLED
    assert source.read_bytes() == original

    missing_candidate = _candidate(
        source_root,
        source,
        start_frame=800,
        end_frame=1_600,
        rate=8_000,
        frame_count=48_000,
        channels=2,
    )
    source.unlink()
    with pytest.raises(AudioSourceError) as missing:
        read_candidate_audio(source_root, missing_candidate, context_seconds=1)
    assert missing.value.problem is AudioSourceProblem.MISSING

    truncated = _write_pcm(
        source_root / "recordings" / "truncated.wav",
        frames=2_000,
        rate=8_000,
        channels=1,
        width=2,
    )
    truncated.write_bytes(truncated.read_bytes()[:-200])
    truncated_candidate = _candidate(
        source_root,
        truncated,
        start_frame=100,
        end_frame=200,
        rate=8_000,
        frame_count=2_000,
        channels=1,
    )
    with pytest.raises(AudioSourceError) as short:
        read_candidate_audio(source_root, truncated_candidate, context_seconds=1)
    assert short.value.problem is AudioSourceProblem.TRUNCATED

    unsupported = source_root / "recordings" / "unsupported.wav"
    unsupported.write_bytes(b"not a wave file")
    unsupported_candidate = _candidate(
        source_root,
        unsupported,
        start_frame=1,
        end_frame=2,
        rate=8_000,
        frame_count=10,
        channels=1,
    )
    with pytest.raises(AudioSourceError) as bad:
        read_candidate_audio(source_root, unsupported_candidate, context_seconds=1)
    assert bad.value.problem is AudioSourceProblem.UNSUPPORTED


class _FakePlayback(PlaybackBackend):
    def __init__(self):
        super().__init__()
        self.events: list[object] = []
        self.loaded_duration = 0

    def load_clip(self, wav_bytes: bytes) -> None:
        self.events.append("load")
        facts = _wav_payload(wav_bytes)
        self.loaded_duration = round(facts[3] * 1_000 / facts[2])
        self.duration_changed.emit(self.loaded_duration)

    def play(self) -> None:
        self.events.append("play")
        self.playing_changed.emit(True)

    def pause(self) -> None:
        self.events.append("pause")
        self.playing_changed.emit(False)

    def stop(self) -> None:
        self.events.append("stop")
        self.playing_changed.emit(False)

    def set_position(self, position_ms: int) -> None:
        self.events.append(("seek", position_ms))
        self.position_changed.emit(position_ms)


def test_native_qt_playback_navigation_focus_failure_and_close(qtbot, tmp_path):
    """Case: IT-REVW-005."""
    source_root = tmp_path / "source"
    source = _write_pcm(
        source_root / "recordings" / "call.wav",
        frames=16_000,
        rate=8_000,
        channels=1,
        width=2,
    )
    source_bytes = source.read_bytes()
    items = []
    for index, (start, end) in enumerate(((800, 1_600), (4_000, 4_800))):
        candidate = _candidate(
            source_root,
            source,
            start_frame=start,
            end_frame=end,
            rate=8_000,
            frame_count=16_000,
            channels=1,
            token=str(index + 1),
        )
        audio = read_candidate_audio(source_root, candidate, context_seconds=1)
        rendered = render_spectrogram(
            audio.samples,
            SpectrogramRenderRequest(
                candidate_id=candidate.candidate_id,
                source_sha256=candidate.source_sha256,
                context=audio.context,
                settings=SpectrogramSettings(
                    frequency_max_hz=3_000,
                    exact_window_ms=20,
                ),
                tier=SpectrogramImageTier.THUMBNAIL,
            ),
        )
        items.append(
            AudioSpectrogramItem(
                candidate_id=candidate.candidate_id,
                recording_name="call.wav",
                audio=audio,
                spectrogram=rendered,
            )
        )

    # The production adapter is a genuine QMediaPlayer/QAudioOutput pair. It is
    # muted here so the background suite exercises lifecycle without desktop audio.
    qt_media = QtMediaPlayback(muted=True)
    assert isinstance(qt_media.player, QMediaPlayer)
    assert qt_media.player.playbackRate() == 1.0
    qt_media.load_clip(items[0].audio.wav_bytes)
    qt_media.play()
    qt_media.pause()
    qt_media.set_position(10)
    qt_media.stop()
    qt_media.close()

    labels = {item.candidate_id: "unreviewed" for item in items}
    backend = _FakePlayback()
    widget = AudioSpectrogramProof(tuple(items), playback=backend)
    qtbot.addWidget(widget)
    widget.resize(720, 420)
    widget.show()
    qtbot.waitExposed(widget)
    widget.activateWindow()
    qtbot.waitUntil(widget.isActiveWindow)

    assert widget.current_index == 0
    assert widget.previous_button.toolTip() == "Previous · J or ←"
    assert widget.play_button.toolTip() == "Play / Pause · K or Space"
    assert widget.next_button.toolTip() == "Next · L or →"
    assert backend.events[-2:] == ["stop", "load"]

    qtbot.mouseClick(widget.play_button, Qt.MouseButton.LeftButton)
    assert backend.events[-1] == "play"
    widget.seek_slider.setValue(250)
    widget.seek_slider.sliderMoved.emit(250)
    assert backend.events[-1] == ("seek", 250)

    before_focus_key = list(backend.events)
    widget.seek_slider.setFocus()
    qtbot.keyClick(widget.seek_slider, Qt.Key.Key_K)
    assert backend.events == before_focus_key

    widget.next_button.setFocus()
    qtbot.keyClick(widget.next_button, Qt.Key.Key_L)
    assert widget.current_index == 1
    assert backend.events[-2:] == ["stop", "load"]
    widget.previous_button.setFocus()
    qtbot.keyClick(widget.previous_button, Qt.Key.Key_J)
    assert widget.current_index == 0
    assert backend.events[-2:] == ["stop", "load"]

    backend.failure.emit("device unavailable")
    assert widget.status_label.text() == "Couldn't play this recording."
    assert labels == {item.candidate_id: "unreviewed" for item in items}

    image_rect = widget.spectrogram_view.image_rect()
    metadata = items[0].spectrogram.metadata
    assert widget.spectrogram_view.frame_x(metadata.context_start_frame) == pytest.approx(
        image_rect.left()
    )
    assert widget.spectrogram_view.frame_x(metadata.context_end_frame) == pytest.approx(
        image_rect.right()
    )
    candidate_left = widget.spectrogram_view.frame_x(metadata.candidate_start_frame)
    candidate_right = widget.spectrogram_view.frame_x(metadata.candidate_end_frame)
    assert image_rect.left() <= candidate_left < candidate_right <= image_rect.right()
    for dpr in (1.0, 1.5, 2.0):
        target = QImage(
            round(widget.spectrogram_view.width() * dpr),
            round(widget.spectrogram_view.height() * dpr),
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        target.setDevicePixelRatio(dpr)
        target.fill(Qt.GlobalColor.transparent)
        widget.spectrogram_view.render(target)
        assert not target.isNull()
        assert target.width() > 0 and target.height() > 0

    event_count = len(backend.events)
    widget.close()
    assert backend.events[event_count:] == ["stop"]
    assert source.read_bytes() == source_bytes
