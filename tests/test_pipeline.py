import json

import numpy as np
import pytest

from meeting_asr.data_gen.simulate import write_mono_wav
from meeting_asr.diarization import DiarizationResult
from meeting_asr.io import minutes_from_dict
from meeting_asr.models import DiarSignals, Segment, Utterance
from meeting_asr.pipeline import run_pipeline
from meeting_asr.postprocess import postprocess
from meeting_asr.settings import load_config


def test_turn_merge_keeps_raw_utterances():
    original = [
        Utterance(0, 1, "A", "ừ xin chào"),
        Utterance(1.5, 2, "A", "các bạn"),
        Utterance(2, 3, "B", "chào"),
    ]
    turns = postprocess(original, remove_fillers=True)
    assert len(turns) == 2
    assert turns[0].text == "Xin chào các bạn"
    assert turns[0].utterances[0].text == "ừ xin chào"
    assert turns[0].confidence is None


def test_pipeline_resumes_after_asr_failure_and_invalidates_upstream(tmp_path, monkeypatch):
    source = tmp_path / "audio.wav"
    t = np.arange(96000) / 16000
    write_mono_wav(source, 0.2 * np.sin(2 * np.pi * 200 * t), 16000)
    config = load_config()
    config["paths"]["cache_dir"] = str(tmp_path / "cache")
    calls = []

    class Backend:
        def diarize(self, audio, **kwargs):
            calls.append("diar")
            return DiarizationResult([Segment(0, 6, "A")], [DiarSignals(0)], "fixture")

    monkeypatch.setattr("meeting_asr.pipeline.make_backend", lambda *args: Backend())

    def fail(*args, **kwargs):
        raise RuntimeError("test interrupted ASR")

    monkeypatch.setattr("meeting_asr.pipeline.transcribe", fail)
    out = tmp_path / "out"
    with pytest.raises(RuntimeError, match="interrupted"):
        run_pipeline(source, config, out)
    monkeypatch.setattr(
        "meeting_asr.pipeline.transcribe", lambda *a, **k: [Utterance(0, 6, "A", "xin chào")]
    )
    minutes = run_pipeline(source, config, out)
    assert calls == ["diar"]
    assert minutes_from_dict(json.loads((out / "minutes.json").read_text())) == minutes
    run_pipeline(source, config, out)
    stages = json.loads((out / "run.json").read_text())["result"]["stages"]
    assert all(stage["cache_hit"] for stage in stages)
    config["preprocess"]["normalize"] = False
    run_pipeline(source, config, out)
    assert calls == ["diar", "diar"]
