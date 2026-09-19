from __future__ import annotations

from pathlib import Path

import pytest

from meeting_asr.io import read_rttm, read_transcript_json, write_rttm, write_transcript_json
from meeting_asr.models import ASRSignals, DiarSignals, Segment, TranscriptDocument, Utterance


def test_rttm_roundtrip_uses_duration_and_keeps_overlap(tmp_path: Path) -> None:
    segments = [
        Segment(0.5, 3.74, "SPEAKER_00"),
        Segment(3.0, 5.0, "SPEAKER_01"),
    ]
    path = tmp_path / "sample.rttm"

    write_rttm(path, "meeting_001", segments)

    assert "1 0.500 3.240 <NA>" in path.read_text(encoding="utf-8")
    loaded = read_rttm(path, expected_file_id="meeting_001")
    assert [s.speaker for s in loaded] == ["SPEAKER_00", "SPEAKER_01"]
    assert [(s.start, s.end) for s in loaded] == pytest.approx([(0.5, 3.74), (3.0, 5.0)])


def test_transcript_json_preserves_signals_and_unicode(tmp_path: Path) -> None:
    original = TranscriptDocument(
        audio_id="họp_01",
        duration=10.0,
        sample_rate=16000,
        config_hash="abc123",
        utterances=[
            Utterance(
                start=1.0,
                end=2.0,
                speaker="SPEAKER_00",
                text="Chào mọi người",
                asr=ASRSignals(avg_logprob=-0.24, no_speech_prob=0.02),
                diar=DiarSignals(overlap_ratio=0.3, cluster_margin=None),
            )
        ],
    )
    path = tmp_path / "transcript.json"

    write_transcript_json(path, original)
    loaded = read_transcript_json(path)

    assert loaded == original
    assert loaded.num_speakers == 1
    assert "Chào mọi người" in path.read_text(encoding="utf-8")


def test_rttm_reader_interprets_field_as_duration(tmp_path: Path) -> None:
    path = tmp_path / "incorrect.rttm"
    path.write_text("SPEAKER a 1 0.500 3.740 <NA> <NA> SPEAKER_00 <NA> <NA>\n")
    segment = read_rttm(path)[0]
    assert segment.end == pytest.approx(4.24)
