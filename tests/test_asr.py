import numpy as np
import pytest

from meeting_asr.asr import Decoded, chunk_ranges, no_speech_probability, transcribe
from meeting_asr.diarization import DiarizationResult
from meeting_asr.models import AudioBundle, DiarSignals, Segment


def test_chunking_and_reassembly_keep_signals_and_raw_text():
    audio = AudioBundle(np.full(16000 * 8, 0.2, dtype=np.float32), 16000, 16000, "fixture")
    diar = DiarizationResult([Segment(0, 8, "A")], [DiarSignals(0.4)], "fixture")
    ranges = chunk_ranges(audio, 0, 8, 3)
    assert all(end - start <= 3 for start, end in ranges)
    assert ranges[-1][1] == 8

    class Decoder:
        def decode(self, waves, sr):
            return [Decoded("xin chào", -0.5, -1.2) for _ in waves]

    results = transcribe(audio, diar, max_segment_sec=3, decoder=Decoder())
    assert results[0].text == "xin chào"
    assert results[0].asr.was_split
    assert results[0].asr.avg_logprob == -0.5
    assert results[0].asr.no_speech_prob is None
    assert results[0].diar.overlap_ratio == 0.4


def test_oom_retries_smaller_batch():
    audio = AudioBundle(np.full(16000 * 6, 0.2, dtype=np.float32), 16000, 16000, "fixture")
    diar = DiarizationResult(
        [Segment(0, 2, "A"), Segment(3, 5, "B")], [DiarSignals(0), DiarSignals(0)], "fixture"
    )

    class Decoder:
        def decode(self, waves, sr):
            if len(waves) > 1:
                raise RuntimeError("CUDA out of memory")
            return [Decoded("xin chào")]

    assert len(transcribe(audio, diar, decoder=Decoder())) == 2


def test_silence_boundary_does_not_delete_legitimate_repeated_words():
    waveform = np.zeros(16000 * 5, dtype=np.float32)
    waveform[:16000] = 0.2
    audio = AudioBundle(waveform, 16000, 16000, "fixture")
    diar = DiarizationResult([Segment(0, 5, "A")], [DiarSignals(0)], "fixture")

    class Decoder:
        def decode(self, waves, sr):
            return [Decoded("xin chào") for _ in waves]

    results = transcribe(audio, diar, max_segment_sec=3, decoder=Decoder())
    assert results[0].text == "xin chào xin chào"


def test_no_speech_probability_and_rejected_masking():
    assert no_speech_probability([0.0, 20.0], 1) == pytest.approx(1)
    assert no_speech_probability([0.0, 0.0], 1) == pytest.approx(0.5)
    assert no_speech_probability([1.0], None) is None
    audio = AudioBundle(np.full(16000 * 2, 0.2, dtype=np.float32), 16000, 16000, "fixture")
    diar = DiarizationResult([Segment(0, 2, "A")], [DiarSignals(0)], "fixture")

    class Decoder:
        def decode(self, waves, sr):
            return [Decoded("xin chào", -0.2, -1.0, 0.25)]

    result = transcribe(audio, diar, decoder=Decoder())
    assert result[0].asr.no_speech_prob == pytest.approx(0.25)
    with pytest.raises(ValueError, match="masking"):
        transcribe(audio, diar, masking="input_masking", decoder=Decoder())
