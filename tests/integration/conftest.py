"""Qt is loaded only when the integration suite is selected."""

from __future__ import annotations

import struct
import wave
from pathlib import Path

import pytest
from PySide6.QtCore import QStandardPaths

from biocall_studio.studio.application.app import create_application
from biocall_studio.train.application.workspace import WorkspaceController


@pytest.fixture(scope="session")
def qapp_args():
    QStandardPaths.setTestModeEnabled(True)
    return ["biocall-studio-tests"]


@pytest.fixture
def workspace(qapp, tmp_path):
    create_application()
    return WorkspaceController(tmp_path / "application-settings")


@pytest.fixture
def wav_factory():
    def write(path: Path, *, frames: int, rate: int = 16_000, channels: int = 1) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = bytearray()
        for frame in range(frames):
            for channel in range(channels):
                value = ((frame * 97 + channel * 701) % 20_000) - 10_000
                payload.extend(struct.pack("<h", value))
        with wave.open(str(path), "wb") as stream:
            stream.setnchannels(channels)
            stream.setsampwidth(2)
            stream.setframerate(rate)
            stream.writeframes(payload)
        return path

    return write


@pytest.fixture
def collection_factory(wav_factory):
    def create(root: Path, *, source_count: int = 2) -> Path:
        for index in range(source_count):
            stem = f"REC_{chr(ord('A') + index)}"
            wav_factory(root / "recordings" / f"{stem}.wav", frames=32_000)
            wav_factory(
                root / "positives" / f"{stem}__start-00500ms__end-01000ms__call{index + 1}.wav",
                frames=8_000,
            )
        return root

    return create
