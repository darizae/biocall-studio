"""Minimal native proof for Review spectrogram painting and single-player audio."""

from __future__ import annotations

from dataclasses import dataclass

from alp_ui.components import Button
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QRectF, QSize, Qt, QUrl, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QImage,
    QKeySequence,
    QPainter,
    QPen,
    QShortcut,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from biocall_studio.review.domain.spectrograms import SpectrogramMetadata, SpectrogramRaster
from biocall_studio.review.workflows.audio import CandidateAudio


class PlaybackBackend(QObject):
    """Small signal contract shared by Qt multimedia and deterministic tests."""

    position_changed = Signal(int)
    duration_changed = Signal(int)
    playing_changed = Signal(bool)
    failure = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

    def load_clip(self, wav_bytes: bytes) -> None:  # pragma: no cover - interface guard
        raise NotImplementedError

    def play(self) -> None:  # pragma: no cover - interface guard
        raise NotImplementedError

    def pause(self) -> None:  # pragma: no cover - interface guard
        raise NotImplementedError

    def stop(self) -> None:  # pragma: no cover - interface guard
        raise NotImplementedError

    def set_position(self, position_ms: int) -> None:  # pragma: no cover - interface guard
        raise NotImplementedError

    def close(self) -> None:
        self.stop()


class QtMediaPlayback(PlaybackBackend):
    """One natural-speed QMediaPlayer backed by an immutable in-memory WAV."""

    def __init__(self, parent: QObject | None = None, *, muted: bool = False):
        super().__init__(parent)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setMuted(muted)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setPlaybackRate(1.0)
        self._buffer: QBuffer | None = None
        self.player.positionChanged.connect(lambda value: self.position_changed.emit(int(value)))
        self.player.durationChanged.connect(lambda value: self.duration_changed.emit(int(value)))
        self.player.playbackStateChanged.connect(
            lambda state: self.playing_changed.emit(
                state == QMediaPlayer.PlaybackState.PlayingState
            )
        )
        self.player.errorOccurred.connect(
            lambda _error, message: self.failure.emit(message or self.player.errorString())
        )

    def load_clip(self, wav_bytes: bytes) -> None:
        if not isinstance(wav_bytes, bytes) or not wav_bytes.startswith(b"RIFF"):
            raise ValueError("Playback requires a verified in-memory WAV clip.")
        self.stop()
        if self._buffer is not None:
            self._buffer.close()
            self._buffer.deleteLater()
        self._buffer = QBuffer(self)
        self._buffer.setData(QByteArray(wav_bytes))
        if not self._buffer.open(QIODevice.OpenModeFlag.ReadOnly):
            raise RuntimeError("Playback buffer could not be opened.")
        self.player.setSourceDevice(self._buffer, QUrl("memory.wav"))

    def play(self) -> None:
        if self._buffer is None:
            self.failure.emit("No audio clip is loaded.")
            return
        self.player.play()

    def pause(self) -> None:
        self.player.pause()

    def stop(self) -> None:
        self.player.stop()

    def set_position(self, position_ms: int) -> None:
        if type(position_ms) is not int or position_ms < 0:
            raise ValueError("Playback position is invalid.")
        self.player.setPosition(position_ms)

    def close(self) -> None:
        self.stop()
        self.player.setSource(QUrl())
        if self._buffer is not None:
            self._buffer.close()
            self._buffer = None


class SpectrogramView(QWidget):
    """Paint a data-only raster, axes, and detection from one metadata transform."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._raster: SpectrogramRaster | None = None
        self._image = QImage()
        self.setMinimumSize(280, 170)
        self.setAccessibleName("Spectrogram with detected interval")

    def sizeHint(self) -> QSize:
        return QSize(720, 300)

    @property
    def metadata(self) -> SpectrogramMetadata | None:
        return None if self._raster is None else self._raster.metadata

    def set_spectrogram(self, raster: SpectrogramRaster) -> None:
        if not isinstance(raster, SpectrogramRaster):
            raise TypeError("Spectrogram view requires a verified raster.")
        self._raster = raster
        self._image = QImage(
            raster.rgb_bytes,
            raster.width,
            raster.height,
            raster.width * 3,
            QImage.Format.Format_RGB888,
        ).copy()
        self.update()

    def image_rect(self) -> QRectF:
        left = 54.0
        top = 12.0
        right = 12.0
        bottom = 34.0
        return QRectF(
            left,
            top,
            max(1.0, self.width() - left - right),
            max(1.0, self.height() - top - bottom),
        )

    def frame_x(self, frame: int) -> float:
        metadata = self.metadata
        if metadata is None:
            raise ValueError("No spectrogram is loaded.")
        rect = self.image_rect()
        return rect.left() + metadata.frame_fraction(frame) * rect.width()

    def frequency_y(self, frequency_hz: float) -> float:
        metadata = self.metadata
        if metadata is None:
            raise ValueError("No spectrogram is loaded.")
        rect = self.image_rect()
        return rect.bottom() - metadata.frequency_fraction(frequency_hz) * rect.height()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("white"))
        if self._raster is None or self._image.isNull():
            return
        metadata = self._raster.metadata
        image_rect = self.image_rect()
        painter.drawImage(image_rect, self._image)

        detected_left = self.frame_x(metadata.candidate_start_frame)
        detected_right = self.frame_x(metadata.candidate_end_frame)
        detected = QRectF(
            detected_left,
            image_rect.top(),
            max(0.0, detected_right - detected_left),
            image_rect.height(),
        )
        painter.fillRect(detected, QColor(255, 193, 7, 52))
        painter.setPen(QPen(QColor(167, 92, 0), 2))
        painter.drawLine(detected.topLeft(), detected.bottomLeft())
        painter.drawLine(detected.topRight(), detected.bottomRight())

        painter.setPen(QPen(QColor(52, 58, 64), 1))
        painter.drawLine(image_rect.bottomLeft(), image_rect.bottomRight())
        painter.drawLine(image_rect.topLeft(), image_rect.bottomLeft())
        duration_frames = metadata.context_end_frame - metadata.context_start_frame
        for fraction in (0.0, 0.5, 1.0):
            x = image_rect.left() + fraction * image_rect.width()
            frame = metadata.context_start_frame + round(duration_frames * fraction)
            seconds = frame / metadata.sample_rate_hz
            painter.drawLine(x, image_rect.bottom(), x, image_rect.bottom() + 4)
            label = f"{seconds:.2f} s"
            bounds = painter.fontMetrics().boundingRect(label)
            painter.drawText(
                x - bounds.width() / 2,
                image_rect.bottom() + bounds.height() + 5,
                label,
            )
        for fraction in (0.0, 0.5, 1.0):
            frequency = metadata.frequency_min_hz + fraction * (
                metadata.frequency_max_hz - metadata.frequency_min_hz
            )
            y = image_rect.bottom() - fraction * image_rect.height()
            painter.drawLine(image_rect.left() - 4, y, image_rect.left(), y)
            label = f"{frequency / 1_000:g} kHz"
            bounds = painter.fontMetrics().boundingRect(label)
            painter.drawText(image_rect.left() - bounds.width() - 7, y + bounds.height() / 3, label)


@dataclass(frozen=True, slots=True)
class AudioSpectrogramItem:
    candidate_id: str
    recording_name: str
    audio: CandidateAudio
    spectrogram: SpectrogramRaster

    def __post_init__(self) -> None:
        if not self.recording_name or "/" in self.recording_name or "\\" in self.recording_name:
            raise ValueError("Recording display name is invalid.")
        if (
            self.candidate_id != self.audio.context.candidate_id
            or self.candidate_id != self.spectrogram.metadata.candidate_id
        ):
            raise ValueError("Audio and spectrogram candidate identities disagree.")


class AudioSpectrogramProof(QWidget):
    """Small One-by-one proof; RV-05 owns the production Review workspace."""

    def __init__(
        self,
        items: tuple[AudioSpectrogramItem, ...],
        *,
        playback: PlaybackBackend | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        if not items:
            raise ValueError("Audio proof requires at least one eligible candidate.")
        if len({item.candidate_id for item in items}) != len(items):
            raise ValueError("Audio proof candidate identities must be unique.")
        self.items = items
        self.playback = playback or QtMediaPlayback(self)
        if self.playback.parent() is None:
            self.playback.setParent(self)
        self.current_index = 0
        self._playing = False
        self._shortcuts: list[QShortcut] = []

        self.item_label = QLabel()
        self.item_label.setAccessibleName("Current recording and time")
        self.spectrogram_view = SpectrogramView()
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setAccessibleName("Audio position")
        self.previous_button = Button("Previous", variant="outline")
        self.play_button = Button("Play", variant="primary")
        self.next_button = Button("Next", variant="outline")
        self.status_label = QLabel()
        self.status_label.setAccessibleName("Playback status")

        self.previous_button.setToolTip("Previous · J or ←")
        self.play_button.setToolTip("Play / Pause · K or Space")
        self.next_button.setToolTip("Next · L or →")
        self.previous_button.setAccessibleDescription(self.previous_button.toolTip())
        self.play_button.setAccessibleDescription(self.play_button.toolTip())
        self.next_button.setAccessibleDescription(self.next_button.toolTip())

        controls = QHBoxLayout()
        controls.addWidget(self.previous_button)
        controls.addWidget(self.play_button)
        controls.addWidget(self.next_button)
        controls.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addWidget(self.item_label)
        layout.addWidget(self.spectrogram_view, 1)
        layout.addWidget(self.seek_slider)
        layout.addLayout(controls)
        layout.addWidget(self.status_label)

        self.previous_button.clicked.connect(self.previous)
        self.play_button.clicked.connect(self.toggle_playback)
        self.next_button.clicked.connect(self.next)
        self.seek_slider.sliderMoved.connect(self.playback.set_position)
        self.playback.position_changed.connect(self._set_position)
        self.playback.duration_changed.connect(self._set_duration)
        self.playback.playing_changed.connect(self._set_playing)
        self.playback.failure.connect(self._playback_failed)
        self._add_shortcuts()
        self._activate(0)

    def _shortcut_allowed(self) -> bool:
        application = QApplication.instance()
        if application is not None and application.activeModalWidget() is not None:
            return False
        focus = QApplication.focusWidget()
        return not isinstance(
            focus,
            (
                QAbstractSlider,
                QAbstractSpinBox,
                QComboBox,
                QLineEdit,
                QPlainTextEdit,
                QTextEdit,
            ),
        )

    def _shortcut(self, sequence: str, action) -> None:
        shortcut = QShortcut(QKeySequence(sequence), self)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.setAutoRepeat(False)
        shortcut.activated.connect(lambda: action() if self._shortcut_allowed() else None)
        self._shortcuts.append(shortcut)

    def _add_shortcuts(self) -> None:
        for sequence in ("J", "Left"):
            self._shortcut(sequence, self.previous)
        for sequence in ("K", "Space"):
            self._shortcut(sequence, self.toggle_playback)
        for sequence in ("L", "Right"):
            self._shortcut(sequence, self.next)

    def _activate(self, index: int) -> None:
        if not 0 <= index < len(self.items):
            raise ValueError("Audio proof position is outside the eligible sequence.")
        self.playback.stop()
        self.current_index = index
        item = self.items[index]
        self.spectrogram_view.set_spectrogram(item.spectrogram)
        start = item.audio.context.candidate_start_time_ns / 1_000_000_000
        end = item.audio.context.candidate_end_time_ns / 1_000_000_000
        self.item_label.setText(f"{item.recording_name} · {start:.3f}–{end:.3f} s")
        self.status_label.clear()
        self.seek_slider.setValue(0)
        self.playback.load_clip(item.audio.wav_bytes)
        self.previous_button.setEnabled(index > 0)
        self.next_button.setEnabled(index + 1 < len(self.items))

    def previous(self) -> None:
        if self.current_index > 0:
            self._activate(self.current_index - 1)

    def next(self) -> None:
        if self.current_index + 1 < len(self.items):
            self._activate(self.current_index + 1)

    def toggle_playback(self) -> None:
        if self._playing:
            self.playback.pause()
        else:
            self.playback.play()

    def _set_duration(self, duration_ms: int) -> None:
        self.seek_slider.setRange(0, max(0, duration_ms))

    def _set_position(self, position_ms: int) -> None:
        if not self.seek_slider.isSliderDown():
            self.seek_slider.setValue(max(0, position_ms))

    def _set_playing(self, playing: bool) -> None:
        self._playing = playing
        self.play_button.setText("Pause" if playing else "Play")

    def _playback_failed(self, _detail: str) -> None:
        self._set_playing(False)
        self.status_label.setText("Couldn't play this recording.")

    def closeEvent(self, event: QCloseEvent) -> None:
        self.playback.close()
        super().closeEvent(event)


__all__ = [
    "AudioSpectrogramItem",
    "AudioSpectrogramProof",
    "PlaybackBackend",
    "QtMediaPlayback",
    "SpectrogramView",
]
