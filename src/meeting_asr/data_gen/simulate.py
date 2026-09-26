"""Build paired meeting audio from clean clips.

One conversation keeps the same turn order under every acoustic condition.
Overlap targets are 0, 0.15, and 0.30. Noise is clean, 15 dB, or 5 dB.
Until a MUSAN recording is passed in, noise is white. Each overlap is kept
inside [0.2s, min(1.5s, half of either adjacent utterance)] so two overlaps
around one turn cannot create a third speaker.
"""

from __future__ import annotations

import json
import math
import wave
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np

from meeting_asr.evaluation.overlap import measure_overlap_ratio, utterance_overlap_fractions
from meeting_asr.io import write_rttm, write_transcript_json
from meeting_asr.models import ASRSignals, DiarSignals, Segment, TranscriptDocument, Utterance
from meeting_asr.settings import config_hash

SAMPLE_RATE = 16000
OVERLAP_TOLERANCE = 0.03
PEAK_AMPLITUDE = 10 ** (-3 / 20)
MIN_CLIP_SEC = 0.05
GAP_SEC = (0.1, 1.0)
OVERLAP_FLOOR_SEC = 0.2
OVERLAP_CAP_SEC = 1.5


@dataclass(frozen=True, slots=True)
class Condition:
    overlap_label: str
    noise_label: str
    overlap: float
    snr_db: float | None


CONDITIONS: tuple[Condition, ...] = (
    Condition("ovl0", "clean", 0.0, None),
    Condition("ovl0", "snr15", 0.0, 15.0),
    Condition("ovl0", "snr5", 0.0, 5.0),
    Condition("ovl15", "clean", 0.15, None),
    Condition("ovl15", "snr15", 0.15, 15.0),
    Condition("ovl15", "snr5", 0.15, 5.0),
    Condition("ovl30", "clean", 0.30, None),
    Condition("ovl30", "snr15", 0.30, 15.0),
    Condition("ovl30", "snr5", 0.30, 5.0),
)


@dataclass(slots=True)
class Clip:
    clip_id: str
    speaker: str
    text: str
    waveform: np.ndarray
    source: str
    sample_rate: int = SAMPLE_RATE

    def __post_init__(self) -> None:
        if not self.clip_id or any(char.isspace() for char in self.clip_id):
            raise ValueError("clip_id must be a nonempty token")
        if not self.speaker or any(char.isspace() for char in self.speaker):
            raise ValueError("speaker must be a nonempty token")
        if not self.text.strip():
            raise ValueError("clip text must not be empty")
        if not self.source.strip():
            raise ValueError("clip source must not be empty")
        if self.sample_rate != SAMPLE_RATE:
            raise ValueError(f"clips must be {SAMPLE_RATE} Hz")
        if not np.issubdtype(self.waveform.dtype, np.floating) or self.waveform.ndim != 1:
            raise ValueError("waveform must be a mono floating-point array")
        waveform = np.ascontiguousarray(self.waveform, dtype=np.float32)
        if waveform.size == 0 or not np.all(np.isfinite(waveform)):
            raise ValueError("waveform must be nonempty and finite")
        if len(waveform) < int(MIN_CLIP_SEC * self.sample_rate):
            raise ValueError(f"clip is shorter than {MIN_CLIP_SEC}s")
        if float(np.max(np.abs(waveform))) < 1e-4:
            raise ValueError("clip is silent")
        self.waveform = waveform

    @property
    def duration(self) -> float:
        return len(self.waveform) / self.sample_rate


@dataclass(slots=True)
class SimulatedSession:
    stem: str
    waveform: np.ndarray
    sample_rate: int
    segments: list[Segment]
    clips: list[Clip]
    seed: int
    conversation_index: int
    overlap_target: float
    overlap_actual: float
    snr_db: float | None
    snr_actual_db: float | None
    noise_source: str

    @property
    def duration(self) -> float:
        return len(self.waveform) / self.sample_rate


def order_turns(clips: Sequence[Clip], rng: np.random.Generator) -> list[Clip]:
    groups: dict[str, list[Clip]] = {}
    for clip in clips:
        groups.setdefault(clip.speaker, []).append(clip)
    counts = {speaker: len(group) for speaker, group in groups.items()}
    total = sum(counts.values())
    if total > 1 and max(counts.values()) > (total + 1) // 2:
        raise ValueError("one speaker has too many clips to avoid consecutive turns")
    for group in groups.values():
        rng.shuffle(group)
    ordered: list[Clip] = []
    last: str | None = None
    remaining = dict(counts)
    while sum(remaining.values()):
        choices = [speaker for speaker, count in remaining.items() if count > 0 and speaker != last]
        if not choices:
            raise ValueError("cannot order turns without repeating a speaker")
        most = max(remaining[speaker] for speaker in choices)
        tied = [speaker for speaker in choices if remaining[speaker] == most]
        speaker = str(rng.choice(tied))
        remaining[speaker] -= 1
        ordered.append(groups[speaker].pop())
        last = speaker
    return ordered


def mix_at_snr(
    speech: np.ndarray, noise: np.ndarray, snr_db: float, active: np.ndarray
) -> np.ndarray:
    if speech.shape != noise.shape or speech.ndim != 1:
        raise ValueError("speech and noise must be 1-D arrays of the same length")
    if active.shape != speech.shape or not bool(np.any(active)):
        raise ValueError("active mask must match speech and contain speech")
    speech_power = float(np.mean(np.square(speech[active])))
    noise_power = float(np.mean(np.square(noise[active])))
    if speech_power <= 0 or noise_power <= 0:
        raise ValueError("speech and noise must have energy on active samples")
    scale = math.sqrt(speech_power / (noise_power * 10 ** (snr_db / 10)))
    return speech + noise * scale


def peak_normalize(waveform: np.ndarray, peak: float = PEAK_AMPLITUDE) -> np.ndarray:
    maximum = float(np.max(np.abs(waveform)))
    if not math.isfinite(maximum) or maximum <= 0:
        raise ValueError("cannot normalize a silent or non-finite mixture")
    scaled = np.ascontiguousarray(waveform * (peak / maximum), dtype=np.float32)
    actual = float(np.max(np.abs(scaled)))
    if actual > peak:
        scaled *= np.float32(peak / actual)
    if float(np.max(np.abs(scaled))) >= 0.999:
        raise ValueError("peak normalization exceeded the sample ceiling")
    return scaled


def simulate_matrix(
    clips: Sequence[Clip],
    *,
    seed: int,
    index: int,
    n_speakers: int = 3,
    noise: np.ndarray | None = None,
    noise_source: str = "white",
) -> list[SimulatedSession]:
    if index < 0:
        raise ValueError("conversation index must be nonnegative")
    speakers = {clip.speaker for clip in clips}
    if len(speakers) != n_speakers:
        raise ValueError(f"expected {n_speakers} speakers, found {len(speakers)}")
    ordered = order_turns(clips, np.random.default_rng(_seed(seed, 0)))
    sessions = []
    for condition_index, condition in enumerate(CONDITIONS, start=1):
        sessions.append(
            render_condition(
                ordered,
                overlap=condition.overlap,
                snr_db=condition.snr_db,
                seed=seed,
                condition_index=condition_index,
                overlap_label=condition.overlap_label,
                noise_label=condition.noise_label,
                conversation_index=index,
                n_speakers=n_speakers,
                noise=noise,
                noise_source=noise_source,
            )
        )
    return sessions


def render_condition(
    clips: Sequence[Clip],
    *,
    overlap: float,
    snr_db: float | None,
    seed: int,
    condition_index: int,
    overlap_label: str,
    noise_label: str,
    conversation_index: int,
    n_speakers: int,
    noise: np.ndarray | None = None,
    noise_source: str = "white",
) -> SimulatedSession:
    if not 0 <= overlap < 1:
        raise ValueError("overlap target must be in [0, 1)")
    if not clips:
        raise ValueError("a session needs at least one clip")
    ordered = list(clips)
    _reject_consecutive(ordered)
    durations = [clip.duration for clip in ordered]
    rng = np.random.default_rng(_seed(seed, condition_index))
    placed = _place(durations, overlap, rng)
    segments = [
        Segment(start, end, clip.speaker)
        for clip, (start, end) in zip(ordered, placed, strict=True)
    ]
    speech, length = _render_speech(ordered, segments)
    source_name = "white" if noise is None else noise_source
    snr_actual: float | None = None
    if snr_db is None:
        mixture = speech
    else:
        active = _active_mask(segments, length)
        noise_wave = _noise_for_length(rng, length, noise)
        mixture = mix_at_snr(speech, noise_wave, snr_db, active)
        residual = mixture - speech
        snr_actual = _snr_db(speech, residual, active)
    waveform = peak_normalize(mixture)
    actual = measure_overlap_ratio(segments)
    if abs(actual - overlap) >= OVERLAP_TOLERANCE:
        raise ValueError(
            f"overlap {actual:.4f} is outside {OVERLAP_TOLERANCE} of target {overlap:.4f}"
        )
    _validate_timeline(segments, waveform, n_speakers)
    stem = f"sim_{overlap_label}_{noise_label}_spk{n_speakers}_{conversation_index:03d}"
    return SimulatedSession(
        stem=stem,
        waveform=waveform,
        sample_rate=SAMPLE_RATE,
        segments=segments,
        clips=ordered,
        seed=seed,
        conversation_index=conversation_index,
        overlap_target=overlap,
        overlap_actual=actual,
        snr_db=snr_db,
        snr_actual_db=snr_actual,
        noise_source=source_name,
    )


def load_clips(manifest_path: str | Path) -> list[Clip]:
    path = Path(manifest_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload["clips"] if isinstance(payload, dict) else payload
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"manifest has no clips: {path}")
    clips = []
    for entry in entries:
        wav_path = Path(entry["wav"])
        if not wav_path.is_absolute():
            wav_path = path.parent / wav_path
        waveform, sample_rate = read_mono_wav(wav_path)
        clips.append(
            Clip(
                clip_id=str(entry["clip_id"]),
                speaker=str(entry["speaker"]),
                text=str(entry["text"]),
                waveform=waveform,
                source=str(entry["source"]),
                sample_rate=sample_rate,
            )
        )
    return clips


def write_session(directory: str | Path, session: SimulatedSession) -> Path:
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    wav_path = destination / f"{session.stem}.wav"
    write_mono_wav(wav_path, session.waveform, session.sample_rate)
    write_rttm(destination / f"{session.stem}.rttm", session.stem, session.segments)
    fractions = utterance_overlap_fractions(session.segments)
    utterances = [
        Utterance(
            start=segment.start,
            end=segment.end,
            speaker=segment.speaker,
            text=clip.text,
            asr=ASRSignals(),
            diar=DiarSignals(overlap_ratio=fraction),
        )
        for segment, clip, fraction in zip(session.segments, session.clips, fractions, strict=True)
    ]
    provenance = {
        "seed": session.seed,
        "conversation_index": session.conversation_index,
        "overlap_target": session.overlap_target,
        "snr_db": session.snr_db,
        "noise_source": session.noise_source,
        "clip_ids": [clip.clip_id for clip in session.clips],
    }
    write_transcript_json(
        destination / f"{session.stem}.json",
        TranscriptDocument(
            audio_id=session.stem,
            duration=session.duration,
            sample_rate=session.sample_rate,
            config_hash=config_hash(provenance),
            utterances=utterances,
        ),
    )
    meta = {
        **provenance,
        "stem": session.stem,
        "overlap_actual": session.overlap_actual,
        "snr_actual_db": session.snr_actual_db,
        "sample_rate": session.sample_rate,
        "turns": [
            {
                "clip_id": clip.clip_id,
                "source": clip.source,
                "speaker": clip.speaker,
                "text": clip.text,
                "start": segment.start,
                "end": segment.end,
            }
            for clip, segment in zip(session.clips, session.segments, strict=True)
        ],
    }
    _atomic_json(destination / f"{session.stem}.meta.json", meta)
    return wav_path


def read_mono_wav(path: str | Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        sample_rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    if channels != 1 or sample_width != 2 or sample_rate != SAMPLE_RATE:
        raise ValueError(f"clip must be mono 16-bit {SAMPLE_RATE} Hz PCM: {path}")
    pcm = np.frombuffer(frames, dtype="<i2").astype(np.float32) / np.float32(32768.0)
    return np.ascontiguousarray(pcm), sample_rate


def write_mono_wav(path: str | Path, waveform: np.ndarray, sample_rate: int) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    pcm = np.clip(np.round(waveform.astype(np.float64) * 32767.0), -32768, 32767).astype("<i2")
    with wave.open(str(temporary), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    temporary.replace(destination)


def _seed(seed: int, stream: int) -> np.random.SeedSequence:
    return np.random.SeedSequence([seed, stream])


def _reject_consecutive(clips: Sequence[Clip]) -> None:
    for previous, current in pairwise(clips):
        if previous.speaker == current.speaker:
            raise ValueError("ordered clips repeat a speaker on consecutive turns")


def _place(
    durations: list[float], overlap_target: float, rng: np.random.Generator
) -> list[tuple[float, float]]:
    overlaps = {} if overlap_target == 0 else _allocate_overlaps(durations, overlap_target, rng)
    starts = [0.0]
    ends = [durations[0]]
    for index in range(1, len(durations)):
        boundary = index - 1
        if boundary in overlaps:
            start = ends[-1] - overlaps[boundary]
        else:
            start = ends[-1] + float(rng.uniform(*GAP_SEC))
        starts.append(start)
        ends.append(start + durations[index])
    snapped = [_snap(start, end) for start, end in zip(starts, ends, strict=True)]
    return snapped


def _allocate_overlaps(
    durations: list[float], overlap_target: float, rng: np.random.Generator
) -> dict[int, float]:
    total = float(sum(durations))
    budget = overlap_target / (1.0 + overlap_target) * total
    caps = [
        _boundary_cap(durations[index], durations[index + 1]) for index in range(len(durations) - 1)
    ]
    chosen = _select_boundaries(caps, budget, rng)
    remaining = budget
    assigned: dict[int, float] = {}
    for position, boundary in enumerate(chosen):
        later = chosen[position + 1 :]
        min_later = OVERLAP_FLOOR_SEC * len(later)
        max_later = sum(caps[item] for item in later)
        low = max(OVERLAP_FLOOR_SEC, remaining - max_later)
        high = min(caps[boundary], remaining - min_later)
        if high < low - 1e-9:
            raise ValueError("overlap budget does not fit the selected boundaries")
        if position == len(chosen) - 1 or high <= low:
            value = remaining if position == len(chosen) - 1 else low
        else:
            value = float(rng.uniform(low, high))
        assigned[boundary] = float(value)
        remaining -= value
    last = chosen[-1]
    assigned[last] += remaining
    for boundary, value in assigned.items():
        if not OVERLAP_FLOOR_SEC - 1e-6 <= value <= caps[boundary] + 1e-6:
            raise ValueError("allocated overlap left the legal range")
    return assigned


def _select_boundaries(caps: list[float], budget: float, rng: np.random.Generator) -> list[int]:
    eligible = [index for index, cap in enumerate(caps) if cap >= OVERLAP_FLOOR_SEC - 1e-12]
    capacity = sum(caps[index] for index in eligible)
    if capacity < budget - 1e-6:
        raise ValueError(
            "clips are too short or too few to reach the overlap target within the 0.2–1.5s limit"
        )

    def covers(chosen: list[int]) -> bool:
        if not chosen:
            return False
        enough = sum(caps[index] for index in chosen) >= budget - 1e-9
        floors_fit = OVERLAP_FLOOR_SEC * len(chosen) <= budget + 1e-9
        return enough and floors_fit

    def take(order: list[int]) -> list[int] | None:
        chosen: list[int] = []
        for boundary in order:
            if OVERLAP_FLOOR_SEC * (len(chosen) + 1) > budget + 1e-9:
                continue
            chosen.append(boundary)
            if sum(caps[index] for index in chosen) >= budget - 1e-9:
                break
        return chosen if covers(chosen) else None

    shuffled = eligible[:]
    rng.shuffle(shuffled)
    chosen = take(shuffled)
    if chosen is None:
        largest_first = sorted(eligible, key=lambda index: caps[index], reverse=True)
        chosen = take(largest_first)
    if chosen is None:
        raise ValueError("cannot place overlap within 0.2s and half-utterance limits")
    return chosen


def _boundary_cap(left: float, right: float) -> float:
    # Half of each utterance is also the limit that keeps a third speaker out.
    return min(OVERLAP_CAP_SEC, 0.5 * left, 0.5 * right)


def _snap(start: float, end: float) -> tuple[float, float]:
    snapped_start = round(start, 3)
    snapped_end = round(end, 3)
    if snapped_end <= snapped_start:
        snapped_end = round(snapped_start + 0.001, 3)
    return snapped_start, snapped_end


def _render_speech(clips: Sequence[Clip], segments: Sequence[Segment]) -> tuple[np.ndarray, int]:
    placements = []
    for clip, segment in zip(clips, segments, strict=True):
        start = round(segment.start * SAMPLE_RATE)
        end = round(segment.end * SAMPLE_RATE)
        span = end - start
        waveform = clip.waveform
        if len(waveform) > span:
            piece = waveform[:span]
        elif len(waveform) < span:
            piece = np.pad(waveform, (0, span - len(waveform)))
        else:
            piece = waveform
        placements.append((start, piece))
    length = max(start + len(piece) for start, piece in placements)
    speech = np.zeros(length, dtype=np.float64)
    for start, piece in placements:
        speech[start : start + len(piece)] += piece
    return speech, length


def _active_mask(segments: Sequence[Segment], n_samples: int) -> np.ndarray:
    mask = np.zeros(n_samples, dtype=bool)
    for segment in segments:
        start = max(0, round(segment.start * SAMPLE_RATE))
        end = min(n_samples, round(segment.end * SAMPLE_RATE))
        if end > start:
            mask[start:end] = True
    if not mask.any():
        raise ValueError("mixture has no active speech")
    return mask


def _noise_for_length(
    rng: np.random.Generator, n_samples: int, noise: np.ndarray | None
) -> np.ndarray:
    if noise is None:
        return rng.standard_normal(n_samples)
    if noise.ndim != 1 or len(noise) == 0 or not np.all(np.isfinite(noise)):
        raise ValueError("noise must be a nonempty finite 1-D waveform")
    if len(noise) >= n_samples:
        start = int(rng.integers(0, len(noise) - n_samples + 1))
        return np.asarray(noise[start : start + n_samples], dtype=np.float64)
    repeats = math.ceil(n_samples / len(noise))
    return np.asarray(np.tile(noise, repeats)[:n_samples], dtype=np.float64)


def _snr_db(speech: np.ndarray, noise: np.ndarray, active: np.ndarray) -> float:
    speech_power = float(np.mean(np.square(speech[active])))
    noise_power = float(np.mean(np.square(noise[active])))
    return 10 * math.log10(speech_power / noise_power)


def _validate_timeline(segments: list[Segment], waveform: np.ndarray, n_speakers: int) -> None:
    if any(segment.end <= segment.start or segment.start < 0 for segment in segments):
        raise ValueError("segment times are not positive")
    duration = len(waveform) / SAMPLE_RATE
    if max(segment.end for segment in segments) > duration + 0.01:
        raise ValueError("a segment ends after the waveform")
    if len({segment.speaker for segment in segments}) != n_speakers:
        raise ValueError("session speaker count does not match the request")
    for previous, current in pairwise(segments):
        if previous.speaker == current.speaker:
            raise ValueError("consecutive turns share a speaker")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
