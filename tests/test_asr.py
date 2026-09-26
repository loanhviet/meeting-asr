import numpy as np

from meeting_asr.asr import Decoded, chunk_ranges, transcribe
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
