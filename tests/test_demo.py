import numpy as np
import pytest

from meeting_asr.data_gen.demo import compose_demo
from meeting_asr.data_gen.simulate import Clip, read_mono_wav, write_session
from meeting_asr.io import read_transcript_json


def test_demo_conditions_preserve_turn_text_and_speakers(tmp_path):
    clips = [
        Clip(
            str(i),
            f"SPEAKER_{i % 2:02d}",
            f"Câu thử {i}",
            np.ones(32000, dtype=np.float32) * 0.1,
            "test synthetic",
        )
        for i in range(4)
    ]
    clean = compose_demo(clips, "clean")
    overlap = compose_demo(clips, "overlap", overlap=True)
    noisy = compose_demo(clips, "noisy", snr_db=10)
    assert clean.overlap_actual == 0
    assert overlap.overlap_actual > 0
    assert np.array_equal(noisy.waveform, compose_demo(clips, "noisy", snr_db=10).waveform)
    for session in (clean, overlap, noisy):
        path = write_session(tmp_path, session)
        samples, sr = read_mono_wav(path)
        assert sr == 16000 and np.max(np.abs(samples)) <= 0.801
        reference = read_transcript_json(path.with_suffix(".json"))
        assert [u.text for u in reference.utterances] == [c.text for c in clips]
        assert reference.num_speakers == 2
    with pytest.raises(ValueError, match="requires clips"):
        compose_demo([], "empty")
