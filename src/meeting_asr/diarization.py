"""Interchangeable diarization backends; model imports are lazy."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Protocol

from meeting_asr.checkpoints import pyannote_checkpoint_context
from meeting_asr.evaluation.overlap import utterance_overlap_fractions
from meeting_asr.models import AudioBundle, DiarSignals, Segment


@dataclass
class DiarizationResult:
    segments: list[Segment]
    signals: list[DiarSignals]
    backend: str
    overlap_regions: list[tuple[float, float]] | None = None

    def __post_init__(self):
        if len(self.segments) != len(self.signals):
            raise ValueError("diarization segments and signals must align")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> DiarizationResult:
        return cls(
            [Segment(**s) for s in payload["segments"]],
            [DiarSignals(**s) for s in payload["signals"]],
            payload["backend"],
            [tuple(region) for region in payload["overlap_regions"]]
            if payload.get("overlap_regions") is not None
            else None,
        )


class DiarizationBackend(Protocol):
    def diarize(self, audio: AudioBundle, **options) -> DiarizationResult: ...


def resolve_device(requested: str = "auto") -> str:
    import torch

    if requested not in {"auto", "cpu", "cuda"}:
        raise ValueError("device must be auto, cpu or cuda")
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable; select runtime.device=cpu")
    return ("cuda" if torch.cuda.is_available() else "cpu") if requested == "auto" else requested


def release_gpu() -> None:
    import gc

    gc.collect()
    try:
        import torch
    except ImportError:
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


class PyannoteBackend:
    def __init__(self, model_name="pyannote/speaker-diarization-3.1", device="auto"):
        self.model_name, self.device = model_name, device

    def diarize(
        self,
        audio: AudioBundle,
        *,
        min_speakers=None,
        max_speakers=6,
        min_segment_duration=0.3,
        **unused,
    ) -> DiarizationResult:
        try:
            import torch
            from pyannote.audio import Pipeline
        except ImportError as exc:
            raise RuntimeError("Install inference dependencies: uv sync --extra inference") from exc
        with pyannote_checkpoint_context():
            pipeline = Pipeline.from_pretrained(
                self.model_name, use_auth_token=os.getenv("HF_TOKEN")
            )
        if pipeline is None:
            raise RuntimeError(
                "Cannot load pyannote. Accept diarization and segmentation model conditions "
                "on Hugging Face, then configure HF_TOKEN."
            )
        pipeline.to(torch.device(resolve_device(self.device)))
        options = {
            k: v
            for k, v in {
                "min_speakers": min_speakers,
                "max_speakers": max_speakers,
            }.items()
            if v is not None
        }
        try:
            annotation = pipeline(
                {
                    "waveform": torch.from_numpy(audio.waveform).unsqueeze(0),
                    "sample_rate": audio.sr,
                },
                **options,
            )
            segments = sorted(
                [
                    Segment(max(0, s.start), min(audio.duration, s.end), str(speaker))
                    for s, _, speaker in annotation.itertracks(yield_label=True)
                    if min(audio.duration, s.end) - max(0, s.start) >= min_segment_duration
                ],
                key=lambda s: (s.start, s.end, s.speaker),
            )
            signals = [DiarSignals(ratio) for ratio in utterance_overlap_fractions(segments)]
            return DiarizationResult(segments, signals, "pyannote")
        finally:
            del pipeline
            release_gpu()


def make_backend(config: dict, device="auto") -> DiarizationBackend:
    if config["backend"] == "pyannote":
        return PyannoteBackend(config.get("model_name", "pyannote/speaker-diarization-3.1"), device)
    if config["backend"] == "ecapa":
        from meeting_asr.ecapa import EcapaBackend

        return EcapaBackend(device=device, **config.get("ecapa", {}))
    raise ValueError(f"unknown diarization backend: {config['backend']}")
