import copy
import json

import numpy as np
import pytest

from meeting_asr.data_gen.simulate import write_mono_wav
from meeting_asr.diarization import DiarizationResult
from meeting_asr.dicow import timestamped_utterances
from meeting_asr.models import DiarSignals, Segment, Utterance
from meeting_asr.pipeline import run_pipeline
from meeting_asr.settings import load_config


def test_generated_target_timestamps_keep_overlap_and_missing_confidence():
    utterances, rejected = timestamped_utterances(
        [
            "<|0.00|>xin chào<|2.00|><|3.00|>hẹn gặp lại<|4.00|>",
            "<|1.00|>chào bạn<|2.50|>",
        ],
        ["A", "B"],
        5,
    )
    assert [(u.start, u.end, u.speaker) for u in utterances] == [
        (0, 2, "A"),
        (1, 2.5, "B"),
        (3, 4, "A"),
    ]
    assert not rejected
    assert utterances[0].diar.overlap_ratio == pytest.approx(0.5)
    assert all(u.asr.avg_logprob is None for u in utterances)
    assert all(u.diar.cluster_margin is None for u in utterances)


def test_untimed_text_is_not_assigned_an_invented_span():
    with pytest.raises(ValueError, match="no usable generated timestamps"):
        timestamped_utterances(["xin chào"], ["A"], 5)
    with pytest.raises(ValueError, match="align"):
        timestamped_utterances(["<|0.00|>xin chào<|1.00|>"], ["A", "B"], 5)


def test_generated_timestamps_reject_outside_audio_and_allow_rounding():
    utterances, rejected = timestamped_utterances(
        ["<|4.00|>kết thúc<|5.02|><|7.00|>ảo giác<|8.00|>"], ["A"], 5
    )
    assert [(u.start, u.end, u.text) for u in utterances] == [(4, 5, "kết thúc")]
    assert rejected == [{"speaker": "A", "start": 7, "end": 8}]


def test_joint_cache_preserves_raw_diarization_and_invalidates_model_revision(
    tmp_path, monkeypatch
):
    config = copy.deepcopy(load_config())
    config["asr"]["engine"] = "dicow"
    config["diarization"]["backend"] = "diarizen"
    config["dicow"] = {"model_revision": "fixture-one"}
    config["llm"]["enabled"] = False
    config["paths"]["cache_dir"] = str(tmp_path / "cache")
    source = tmp_path / "recording.wav"
    write_mono_wav(source, np.sin(np.arange(96000) / 16000).astype(np.float32), 16000)
    calls = []

    def author(audio, config, destination, *, oracle_rttm, progress):
        calls.append(config["dicow"]["model_revision"])
        progress("M2", 0.2)
        progress("M3", 0.4)
        diar = DiarizationResult([Segment(0, 6, "A")], [DiarSignals(0)], "diarizen")
        # The ASR-generated timestamps differ from the original diarization.
        return diar, [Utterance(1, 4, "A", "xin chào")], {"fixture": True}, {"raw": True}

    monkeypatch.setattr("meeting_asr.dicow.recognize_author", author)
    out = tmp_path / "out"
    result = run_pipeline(source, config, out)
    assert result.turns[0].start == 1
    assert "0.000 6.000" in (out / "diarization.rttm").read_text()
    assert json.loads((out / "dicow-author-output.json").read_text()) == {"raw": True}
    run_pipeline(source, config, out)
    assert calls == ["fixture-one"]
    stages = json.loads((out / "run.json").read_text())["result"]["stages"]
    assert all(stage["cache_hit"] for stage in stages)
    config["dicow"]["model_revision"] = "fixture-two"
    run_pipeline(source, config, out)
    assert calls == ["fixture-one", "fixture-two"]
