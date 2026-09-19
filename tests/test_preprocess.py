from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

from meeting_asr.preprocess import preprocess

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="FFmpeg and ffprobe are required",
)


def write_wav(
    path: Path, left: np.ndarray, right: np.ndarray | None = None, sr: int = 44100
) -> None:
    samples = left[:, None] if right is None else np.column_stack((left, right))
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(samples.shape[1])
        handle.setsampwidth(2)
        handle.setframerate(sr)
        handle.writeframes(pcm.tobytes())


def test_stereo_is_averaged_and_resampled(tmp_path: Path) -> None:
    sr = 44100
    seconds = 6
    time = np.arange(sr * seconds) / sr
    left = 0.4 * np.sin(2 * np.pi * 440 * time)
    path = tmp_path / "stereo.wav"
    write_wav(path, left, np.zeros_like(left))

    audio = preprocess(path, normalize=False)

    assert audio.sr == 16000
    assert audio.original_sr == sr
    assert audio.waveform.dtype == np.float32
    assert audio.waveform.ndim == 1
    assert audio.duration == pytest.approx(seconds, abs=0.01)
    assert np.max(np.abs(audio.waveform)) == pytest.approx(0.2, abs=0.01)


def test_normalization_keeps_audio_within_range(tmp_path: Path) -> None:
    sr = 16000
    time = np.arange(sr * 6) / sr
    path = tmp_path / "quiet.wav"
    write_wav(path, 0.01 * np.sin(2 * np.pi * 440 * time), sr=sr)

    audio = preprocess(path)

    assert audio.normalization_method != "none"
    assert 0 < np.max(np.abs(audio.waveform)) <= 1


@pytest.mark.parametrize("extension", ["mp3", "m4a"])
def test_compressed_inputs_are_decoded(tmp_path: Path, extension: str) -> None:
    sr = 16000
    time = np.arange(sr * 6) / sr
    source = tmp_path / "source.wav"
    target = tmp_path / f"encoded.{extension}"
    write_wav(source, 0.2 * np.sin(2 * np.pi * 440 * time), sr=sr)
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            str(target),
        ],
        check=True,
    )

    audio = preprocess(target, normalize=False)

    assert audio.sr == 16000
    assert audio.duration == pytest.approx(6, abs=0.1)
    assert np.max(np.abs(audio.waveform)) > 0.1


@pytest.mark.parametrize("seconds,silent", [(4, False), (6, True)])
def test_rejects_short_or_silent_audio(tmp_path: Path, seconds: int, silent: bool) -> None:
    sr = 16000
    time = np.arange(sr * seconds) / sr
    signal = np.zeros(len(time)) if silent else 0.2 * np.sin(2 * np.pi * 440 * time)
    path = tmp_path / "input.wav"
    write_wav(path, signal, sr=sr)

    with pytest.raises(ValueError):
        preprocess(path)
