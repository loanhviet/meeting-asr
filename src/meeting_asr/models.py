"""Shared, serializable contracts between pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any

import numpy as np


@dataclass(slots=True)
class AudioBundle:
    waveform: np.ndarray
    sr: int
    original_sr: int
    source_path: str
    normalization_method: str = "none"
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.waveform.ndim != 1 or self.waveform.dtype != np.float32:
            raise ValueError("waveform must be a mono float32 array")
        if self.sr <= 0 or self.original_sr <= 0:
            raise ValueError("sample rates must be positive")
        if not np.all(np.isfinite(self.waveform)):
            raise ValueError("waveform contains non-finite samples")

    @property
    def duration(self) -> float:
        return len(self.waveform) / self.sr


@dataclass(slots=True)
class Segment:
    start: float
    end: float
    speaker: str

    def __post_init__(self) -> None:
        if not (isfinite(self.start) and isfinite(self.end) and 0 <= self.start < self.end):
            raise ValueError("segment must have finite 0 <= start < end")
        if not self.speaker or any(char.isspace() for char in self.speaker):
            raise ValueError("speaker must be a nonempty token")

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(slots=True)
class DiarSignals:
    overlap_ratio: float
    cluster_margin: float | None = None
    n_windows: int | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.overlap_ratio <= 1:
            raise ValueError("overlap_ratio must be in [0, 1]")
        if self.n_windows is not None and self.n_windows < 0:
            raise ValueError("n_windows must be nonnegative")
        if self.cluster_margin is not None and not isfinite(self.cluster_margin):
            raise ValueError("cluster_margin must be finite or null")


@dataclass(slots=True)
class ASRSignals:
    avg_logprob: float | None = None
    no_speech_prob: float | None = None
    compression_ratio: float | None = None
    min_token_logprob: float | None = None
    was_split: bool = False

    def __post_init__(self):
        for name in ("avg_logprob", "min_token_logprob", "compression_ratio", "no_speech_prob"):
            value = getattr(self, name)
            if value is not None and not isfinite(value):
                raise ValueError(f"{name} must be finite or null")
        if self.no_speech_prob is not None and not 0 <= self.no_speech_prob <= 1:
            raise ValueError("no_speech_prob must be in [0, 1]")
        if self.compression_ratio is not None and self.compression_ratio < 0:
            raise ValueError("compression_ratio must be nonnegative")


@dataclass(slots=True)
class Utterance(Segment):
    text: str
    asr: ASRSignals = field(default_factory=ASRSignals)
    diar: DiarSignals | None = None


@dataclass(slots=True)
class TranscriptDocument:
    audio_id: str
    duration: float
    sample_rate: int
    config_hash: str
    utterances: list[Utterance]

    @property
    def num_speakers(self) -> int:
        return len({utterance.speaker for utterance in self.utterances})


@dataclass(slots=True)
class Turn:
    turn_id: str
    start: float
    end: float
    speaker: str
    text: str
    utterances: list[Utterance]
    confidence: float | None = None
    flagged: bool = False
    flag_reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MeetingMinutes:
    audio_id: str
    duration: float
    num_speakers: int
    turns: list[Turn]
    flagged_ratio: float = 0.0
    summary: str | None = None
    topics: list[str] = field(default_factory=list)
    action_items: list[dict[str, Any]] = field(default_factory=list)


SCHEMA_VERSION = 1
