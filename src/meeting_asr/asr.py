"""Segment-wise Whisper inference retaining real generation signals."""

from __future__ import annotations

import logging
import zlib
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from meeting_asr.diarization import DiarizationResult, release_gpu, resolve_device
from meeting_asr.models import ASRSignals, AudioBundle, Utterance

logger = logging.getLogger(__name__)


@dataclass
class Decoded:
    text: str
    avg_logprob: float | None = None
    min_token_logprob: float | None = None
    no_speech_prob: float | None = None


class Decoder(Protocol):
    def decode(self, waveforms: list[np.ndarray], sr: int) -> list[Decoded]: ...


def no_speech_probability(logits, token_id):
    """Softmax probability of one token. Out-of-range ids stay missing."""
    if token_id is None or token_id < 0 or token_id >= len(logits):
        return None
    shifted = np.asarray(logits, dtype=np.float64)
    shifted = shifted - np.max(shifted)
    weights = np.exp(shifted)
    total = float(weights.sum())
    if not np.isfinite(total) or total <= 0:
        return None
    return float(weights[token_id] / total)


def join_overlap(left: str, right: str) -> str:
    a, b = left.split(), right.split()
    for width in range(min(30, len(a), len(b)), 0, -1):
        if [s.casefold().strip(".,!?") for s in a[-width:]] == [
            s.casefold().strip(".,!?") for s in b[:width]
        ]:
            return " ".join(a + b[width:])
    return " ".join(a + b)


def chunk_ranges(audio: AudioBundle, start: float, end: float, maximum: float) -> list[tuple]:
    if maximum < 1 or maximum > 28:
        raise ValueError("max_segment_sec must be between 1 and 28")
    chunks = []
    cursor = start
    while end - cursor > maximum:
        stop = cursor + maximum
        # Look for an actual low-energy 100 ms frame near the boundary.
        candidates = np.arange(max(cursor + maximum / 2, stop - 1), stop - 0.1, 0.05)
        energies = [
            float(np.mean(audio.waveform[int(t * audio.sr) : int((t + 0.1) * audio.sr)] ** 2))
            for t in candidates
        ]
        cut = stop
        silence = False
        if energies:
            index = int(np.argmin(energies))
            if energies[index] < 1e-5:
                cut = float(candidates[index] + 0.05)
                silence = True
        chunks.append((cursor, cut))
        cursor = cut if silence else cut - 0.5
    chunks.append((cursor, end))
    return chunks


class WhisperDecoder:
    def __init__(
        self,
        model_name: str,
        language="vi",
        device="auto",
        temperature=0.0,
        collect_no_speech=False,
    ):
        try:
            import torch
            from transformers import AutoProcessor, WhisperForConditionalGeneration
        except ImportError as exc:
            raise RuntimeError("Install inference dependencies: uv sync --extra inference") from exc
        if temperature != 0:
            raise ValueError("reproducible baseline requires temperature=0")
        self.device = resolve_device(device)
        self.dtype = torch.float16 if self.device == "cuda" else torch.float32
        self.processor = AutoProcessor.from_pretrained(model_name)
        self.model = (
            WhisperForConditionalGeneration.from_pretrained(
                model_name,
                torch_dtype=self.dtype,
            )
            .to(self.device)
            .eval()
        )
        self.language = language
        self.collect_no_speech = bool(collect_no_speech)
        self.no_speech_token_id = self._no_speech_token_id() if self.collect_no_speech else None
        if not self.collect_no_speech:
            logger.info("no_speech_prob collection is disabled; recorded as null")
        elif self.no_speech_token_id is None:
            logger.info("no_speech token is absent; no_speech_prob is recorded as null")

    def _no_speech_token_id(self):
        tokenizer = self.processor.tokenizer
        token_id = tokenizer.convert_tokens_to_ids("<|nospeech|>")
        unknown = getattr(tokenizer, "unk_token_id", None)
        if isinstance(token_id, int) and token_id >= 0 and token_id != unknown:
            return token_id
        timestamps = getattr(self.model.generation_config, "no_timestamps_token_id", None)
        if isinstance(timestamps, int) and timestamps > 0:
            return timestamps - 1
        return None

    def _no_speech_probabilities(self, features):
        if self.no_speech_token_id is None:
            return None
        import torch

        try:
            decoder_input = torch.full(
                (features["input_features"].shape[0], 1),
                self.model.config.decoder_start_token_id,
                dtype=torch.long,
                device=self.device,
            )
            with torch.inference_mode():
                logits = self.model(
                    features["input_features"],
                    attention_mask=features.get("attention_mask"),
                    decoder_input_ids=decoder_input,
                ).logits[:, -1, :]
            return [
                no_speech_probability(row.float().cpu().numpy(), self.no_speech_token_id)
                for row in logits
            ]
        except (RuntimeError, ValueError, TypeError):
            logger.warning("no_speech_prob could not be read; recorded as null")
            release_gpu()
            return None

    def decode(self, waveforms: list[np.ndarray], sr: int) -> list[Decoded]:
        import torch

        features = self.processor(
            waveforms, sampling_rate=sr, return_tensors="pt", return_attention_mask=True
        )
        inputs = {
            k: v.to(self.device, dtype=self.dtype) if k == "input_features" else v.to(self.device)
            for k, v in features.items()
        }
        with torch.inference_mode():
            output = self.model.generate(
                **inputs,
                language=self.language,
                task="transcribe",
                do_sample=False,
                no_repeat_ngram_size=3,
                max_new_tokens=440,
                return_dict_in_generate=True,
                output_scores=True,
            )
            scores = self.model.compute_transition_scores(
                output.sequences,
                output.scores,
                normalize_logits=True,
            )
        texts = self.processor.batch_decode(output.sequences, skip_special_tokens=True)
        tokens = output.sequences[:, -scores.shape[1] :]
        special = set(self.processor.tokenizer.all_special_ids)
        silence = self._no_speech_probabilities(inputs) if self.collect_no_speech else None
        results = []
        for row, text in enumerate(texts):
            kept = [
                float(score)
                for token, score in zip(tokens[row], scores[row], strict=True)
                if int(token) not in special and torch.isfinite(score)
            ]
            results.append(
                Decoded(
                    text.strip(),
                    float(np.mean(kept)) if kept else None,
                    min(kept) if kept else None,
                    None if silence is None else silence[row],
                )
            )
        return results

    def close(self):
        del self.model
        release_gpu()


def transcribe(
    audio: AudioBundle,
    diarization: DiarizationResult,
    *,
    model_name="vinai/PhoWhisper-medium",
    language="vi",
    batch_size=8,
    max_segment_sec=28.0,
    min_segment_sec=0.3,
    boundary_pad=0.1,
    temperature=0.0,
    masking="none",
    collect_no_speech=False,
    device="auto",
    decoder: Decoder | None = None,
) -> list[Utterance]:
    if batch_size < 1 or not 0 <= boundary_pad <= 0.5:
        raise ValueError("invalid ASR batch size or boundary padding")
    if masking != "none":
        raise ValueError("masking must be 'none' until the Input Masking comparison is implemented")
    tasks = []
    valid = []
    for segment, signals in zip(diarization.segments, diarization.signals, strict=True):
        if segment.end > audio.duration + 1 / audio.sr:
            raise ValueError("diarization extends past audio duration")
        if segment.duration < min_segment_sec:
            continue
        index = len(valid)
        valid.append((segment, signals))
        ranges = chunk_ranges(audio, segment.start, segment.end, max_segment_sec)
        for chunk_index, (start, end) in enumerate(ranges):
            a = max(0, int((start - boundary_pad) * audio.sr))
            b = min(len(audio.waveform), int((end + boundary_pad) * audio.sr))
            waveform = audio.waveform[a:b].copy()
            overlap = chunk_index > 0 and start < ranges[chunk_index - 1][1] - 1e-6
            tasks.append((index, chunk_index, start, end, waveform, overlap))
    if not tasks:
        return []
    owned = decoder is None
    if owned:
        decoder = WhisperDecoder(
            model_name, language, device, temperature, collect_no_speech=collect_no_speech
        )
    decoded = {}
    ordered = sorted(tasks, key=lambda t: len(t[4]))
    cursor, size = 0, batch_size
    try:
        while cursor < len(ordered):
            batch = ordered[cursor : cursor + size]
            try:
                output = decoder.decode([t[4] for t in batch], audio.sr)
            except RuntimeError as exc:
                if "out of memory" not in str(exc).lower() or size == 1:
                    raise
                size = max(1, size // 2)
                release_gpu()
                logger.warning("ASR out of memory; retrying batch_size=%s", size)
                continue
            if len(output) != len(batch):
                raise RuntimeError("decoder returned wrong batch length")
            for task, result in zip(batch, output, strict=True):
                decoded[(task[0], task[1])] = (result, task[3] - task[2], task[5])
            cursor += len(batch)
    finally:
        if owned:
            decoder.close()
    utterances = []
    for index, (segment, signals) in enumerate(valid):
        parts = [decoded[key] for key in sorted(decoded) if key[0] == index]
        text = ""
        for part, _, overlap in parts:
            text = (
                join_overlap(text, part.text)
                if overlap
                else " ".join((text + " " + part.text).split())
            )

        def average(field, parts=parts):
            available = [
                (getattr(p, field), duration)
                for p, duration, _ in parts
                if getattr(p, field) is not None
            ]
            return (
                sum(v * d for v, d in available) / sum(d for _, d in available)
                if available
                else None
            )

        minima = [p.min_token_logprob for p, _, _ in parts if p.min_token_logprob is not None]
        raw = text.encode("utf-8")
        utterances.append(
            Utterance(
                segment.start,
                segment.end,
                segment.speaker,
                text,
                ASRSignals(
                    average("avg_logprob"),
                    average("no_speech_prob"),
                    len(raw) / len(zlib.compress(raw)) if raw else 0,
                    min(minima) if minima else None,
                    len(parts) > 1,
                ),
                signals,
            )
        )
    return utterances
