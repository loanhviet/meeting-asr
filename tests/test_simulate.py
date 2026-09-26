from __future__ import annotations

import json
import wave
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest

from meeting_asr.cli import main
from meeting_asr.data_gen.simulate import (
    PEAK_AMPLITUDE,
    Clip,
    load_clips,
    mix_at_snr,
    order_turns,
    simulate_matrix,
    write_session,
)
from meeting_asr.evaluation.overlap import measure_overlap_ratio
from meeting_asr.io import read_rttm, read_transcript_json

SAMPLE_RATE = 16000


def _tone(seconds: float, frequency: float, amplitude: float = 0.4) -> np.ndarray:
    time = np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE
    return (amplitude * np.sin(2 * np.pi * frequency * time)).astype(np.float32)


def _clips(seconds: float = 2.0) -> list[Clip]:
    clips = []
    for speaker_index, speaker in enumerate(("SPEAKER_00", "SPEAKER_01", "SPEAKER_02")):
        for turn in range(2):
            clips.append(
                Clip(
                    clip_id=f"{speaker}_{turn}",
                    speaker=speaker,
                    text=f"câu {speaker_index} {turn}",
                    waveform=_tone(seconds, 180 + 40 * speaker_index + 15 * turn),
                    source="synthetic",
                )
            )
    return clips


def _boundary_gap(previous_end: float, next_start: float) -> float:
    return next_start - previous_end


def test_simulate_overlap_ratio(tmp_path: Path) -> None:
    for seed in (0, 1, 2):
        sessions = simulate_matrix(_clips(), seed=seed, index=7)
        assert len(sessions) == 9
        for session in sessions:
            wav_path = write_session(tmp_path / f"seed{seed}", session)
            loaded = read_rttm(wav_path.with_suffix(".rttm"), expected_file_id=session.stem)
            measured = measure_overlap_ratio(loaded)
            assert measured == pytest.approx(session.overlap_actual, abs=1e-9)
            assert abs(measured - session.overlap_target) < 0.03
            assert all(segment.end > segment.start >= 0 for segment in loaded)
            assert max(segment.end for segment in loaded) <= session.duration + 0.01
            assert len({segment.speaker for segment in loaded}) == 3
            for previous, current in pairwise(loaded):
                gap = _boundary_gap(previous.end, current.start)
                if gap >= 0:
                    assert 0.09 <= gap <= 1.002
                else:
                    overlap = -gap
                    cap = min(1.5, 0.5 * previous.duration, 0.5 * current.duration)
                    assert 0.198 <= overlap <= cap + 0.002


def test_simulate_no_clipping() -> None:
    sessions = simulate_matrix(_clips(), seed=4, index=1)
    for session in sessions:
        peak = float(np.max(np.abs(session.waveform)))
        assert peak < 0.999
        assert peak == pytest.approx(PEAK_AMPLITUDE, abs=1e-5)
        assert session.waveform.dtype == np.float32


def test_no_consecutive_same_speaker() -> None:
    sessions = simulate_matrix(_clips(), seed=5, index=2)
    orders = []
    for session in sessions:
        speakers = [segment.speaker for segment in session.segments]
        assert all(left != right for left, right in pairwise(speakers))
        orders.append([(clip.speaker, clip.clip_id, clip.text) for clip in session.clips])
    assert orders.count(orders[0]) == 9

    skewed = [
        Clip(f"a{index}", "SPEAKER_00", f"a {index}", _tone(0.5, 200), "synthetic")
        for index in range(5)
    ]
    skewed.append(Clip("b0", "SPEAKER_01", "b 0", _tone(0.5, 300), "synthetic"))
    skewed.append(Clip("c0", "SPEAKER_02", "c 0", _tone(0.5, 400), "synthetic"))
    with pytest.raises(ValueError, match="consecutive"):
        order_turns(skewed, np.random.default_rng(0))


def test_clean_gaps_stay_silent_and_noise_does_not() -> None:
    sessions = simulate_matrix(_clips(), seed=6, index=3)
    clean = next(
        session for session in sessions if session.snr_db is None and session.overlap_target == 0
    )
    noisy = next(
        session for session in sessions if session.snr_db == 5 and session.overlap_target == 0
    )
    gap_start = round(clean.segments[0].end * SAMPLE_RATE)
    gap_end = round(clean.segments[1].start * SAMPLE_RATE)
    assert gap_end > gap_start
    assert float(np.max(np.abs(clean.waveform[gap_start:gap_end]))) == 0
    noisy_start = round(noisy.segments[0].end * SAMPLE_RATE)
    noisy_end = round(noisy.segments[1].start * SAMPLE_RATE)
    assert noisy_end > noisy_start
    assert float(np.max(np.abs(noisy.waveform[noisy_start:noisy_end]))) > 1e-4
    assert noisy.snr_actual_db == pytest.approx(5.0, abs=0.05)
    assert clean.noise_source == "white"


def test_simulate_snr_matches_the_requested_level() -> None:
    time = np.arange(SAMPLE_RATE) / SAMPLE_RATE
    speech = 0.2 * np.sin(2 * np.pi * 220 * time)
    noise = np.random.default_rng(1).standard_normal(SAMPLE_RATE)
    active = np.ones(SAMPLE_RATE, dtype=bool)
    mixed = mix_at_snr(speech, noise, 15.0, active)
    residual = mixed - speech
    speech_power = float(np.mean(np.square(speech[active])))
    noise_power = float(np.mean(np.square(residual[active])))
    measured = 10 * np.log10(speech_power / noise_power)
    assert measured == pytest.approx(15.0, abs=0.05)


def test_simulate_is_reproducible() -> None:
    first = simulate_matrix(_clips(), seed=8, index=4)
    second = simulate_matrix(_clips(), seed=8, index=4)
    for left, right in zip(first, second, strict=True):
        assert left.stem == right.stem
        assert np.array_equal(left.waveform, right.waveform)
        assert [(segment.start, segment.end, segment.speaker) for segment in left.segments] == [
            (segment.start, segment.end, segment.speaker) for segment in right.segments
        ]


def test_cli_simulate_writes_reference_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clips = _clips()
    manifest_clips = []
    for clip in clips:
        wav_path = tmp_path / f"{clip.clip_id}.wav"
        _write_pcm(wav_path, clip.waveform)
        manifest_clips.append(
            {
                "clip_id": clip.clip_id,
                "speaker": clip.speaker,
                "text": clip.text,
                "source": clip.source,
                "wav": wav_path.name,
            }
        )
    manifest = tmp_path / "clips.json"
    manifest.write_text(json.dumps({"clips": manifest_clips}), encoding="utf-8")
    out_dir = tmp_path / "out"

    assert (
        main(["simulate", str(manifest), "--out", str(out_dir), "--index", "7", "--seed", "9"]) == 0
    )

    summary = json.loads(capsys.readouterr().out)
    assert summary["seed"] == 9
    assert len(summary["sessions"]) == 9
    loaded_clips = load_clips(manifest)
    assert [clip.clip_id for clip in loaded_clips] == [clip.clip_id for clip in clips]
    transcript = read_transcript_json(out_dir / "sim_ovl15_snr15_spk3_007.json")
    assert transcript.audio_id == "sim_ovl15_snr15_spk3_007"
    assert transcript.utterances
    assert all(utterance.asr.avg_logprob is None for utterance in transcript.utterances)
    meta = json.loads((out_dir / "sim_ovl15_snr15_spk3_007.meta.json").read_text(encoding="utf-8"))
    assert meta["seed"] == 9
    assert meta["turns"]


def _write_pcm(path: Path, waveform: np.ndarray) -> None:
    pcm = np.clip(np.round(waveform.astype(np.float64) * 32767.0), -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm.tobytes())
