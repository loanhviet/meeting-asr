"""Decode WAV/MP3/M4A to mono 16 kHz float32 audio."""

from __future__ import annotations

import json
import subprocess
import warnings
from pathlib import Path

import numpy as np
import pyloudnorm as pyln

from meeting_asr.models import AudioBundle

SUPPORTED_SUFFIXES = {".wav", ".mp3", ".m4a"}
SILENCE_LIMIT = 1e-4
PEAK_TARGET = 10 ** (-1 / 20)


def _probe_audio(path: Path) -> tuple[int, int]:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=sample_rate,channels",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffprobe is required to read audio") from exc
    if result.returncode != 0:
        raise OSError(f"cannot inspect audio file {path}: {result.stderr.strip()}")
    streams = json.loads(result.stdout).get("streams", [])
    if not streams:
        raise OSError(f"audio stream not found: {path}")
    return int(streams[0]["sample_rate"]), int(streams[0]["channels"])


def _decode(path: Path, target_sr: int, channels: int) -> np.ndarray:
    if channels not in (1, 2):
        raise ValueError(f"expected mono or stereo audio, found {channels} channels: {path}")
    filters = []
    if channels == 2:
        filters.append("pan=mono|c0=0.5*c0+0.5*c1")
    filters.append("aresample=resampler=soxr:precision=28")
    command = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-vn",
        "-af",
        ",".join(filters),
        "-ar",
        str(target_sr),
        "-ac",
        "1",
        "-f",
        "f32le",
        "-acodec",
        "pcm_f32le",
        "pipe:1",
    ]
    try:
        result = subprocess.run(command, capture_output=True, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg is required to decode audio") from exc
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise OSError(f"cannot decode audio file {path}: {message}")
    return np.frombuffer(result.stdout, dtype="<f4").copy()


def _normalize(waveform: np.ndarray, sr: int) -> tuple[np.ndarray, str]:
    try:
        loudness = pyln.Meter(sr).integrated_loudness(waveform)
        if np.isfinite(loudness):
            normalized = pyln.normalize.loudness(waveform, loudness, -23.0)
            method = "lufs_-23"
        else:
            raise ValueError("non-finite loudness")
    except (ValueError, RuntimeError):
        normalized = waveform * (PEAK_TARGET / np.max(np.abs(waveform)))
        method = "peak_-1dbfs"
    peak = float(np.max(np.abs(normalized)))
    if peak > PEAK_TARGET:
        normalized = normalized * (PEAK_TARGET / peak)
        method += "_peak_limited"
    return normalized.astype(np.float32), method


def preprocess(
    path: str | Path,
    target_sr: int = 16000,
    normalize: bool = True,
    denoise: bool = False,
    max_duration_sec: float = 1800,
) -> AudioBundle:
    """Decode, downmix by arithmetic mean, resample and normalize one recording.

    Files longer than ``max_duration_sec`` are processed with a warning, per the spec.
    """
    source = Path(path)
    if source.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"unsupported audio type: {source.suffix}")
    if not source.is_file():
        raise FileNotFoundError(source)
    if target_sr != 16000:
        raise ValueError("the current pipeline contract requires target_sr=16000")
    if denoise:
        raise NotImplementedError("denoise is reserved for a later pipeline stage")

    original_sr, channels = _probe_audio(source)
    waveform = _decode(source, target_sr, channels)
    duration = len(waveform) / target_sr
    if duration < 5:
        raise ValueError(f"audio must be at least 5 seconds: {source}")
    if not np.all(np.isfinite(waveform)):
        raise ValueError(f"audio contains non-finite samples: {source}")
    if float(np.max(np.abs(waveform))) < SILENCE_LIMIT:
        raise ValueError(f"audio is silent: {source}")

    notes: list[str] = []
    if original_sr < target_sr:
        notes.append(f"upsampled from {original_sr} Hz; ASR quality may degrade")
    if duration > max_duration_sec:
        notes.append(f"audio duration {duration:.1f}s exceeds {max_duration_sec:.1f}s")
    for note in notes:
        warnings.warn(note, stacklevel=2)

    method = "none"
    if normalize:
        waveform, method = _normalize(waveform, target_sr)
    waveform = np.clip(waveform, -1.0, 1.0).astype(np.float32, copy=False)
    return AudioBundle(
        waveform=waveform,
        sr=target_sr,
        original_sr=original_sr,
        source_path=str(source),
        normalization_method=method,
        warnings=notes,
    )
