import json
from pathlib import Path

import numpy as np
import pytest

from meeting_asr.data_gen.dataset import build_dataset
from meeting_asr.data_gen.simulate import write_mono_wav
from meeting_asr.evaluation.detection import overlap_detection_score
from meeting_asr.models import Segment
from meeting_asr.postprocess import normalize_dates


def test_dataset_uses_distinct_clips_and_supports_partial_dev_matrix(tmp_path):
    clips = []
    for speaker in range(6):
        for index in range(2):
            clip_id = f"{speaker}_{index}"
            wav = tmp_path / f"{clip_id}.wav"
            t = np.arange(32000) / 16000
            write_mono_wav(wav, 0.2 * np.sin(2 * np.pi * (200 + speaker * 30 + index) * t), 16000)
            clips.append(
                {
                    "clip_id": clip_id,
                    "speaker": str(speaker),
                    "text": "xin chào",
                    "source": "fixture",
                    "wav": wav.name,
                }
            )
    manifest = tmp_path / "dev.json"
    manifest.write_text(json.dumps({"split": "dev", "clips": clips}))
    result = build_dataset(
        manifest, tmp_path / "out", conversations=2, clips_per_speaker=2, session_limit=10
    )
    assert len(result["sessions"]) == 10
    originals = [result["sessions"][0], result["sessions"][9]]
    sets = [
        set(json.loads(Path(s["audio"]).with_suffix(".meta.json").read_text())["clip_ids"])
        for s in originals
    ]
    assert sets[0].isdisjoint(sets[1])


def test_overlap_detector_scores_time_and_dates_keep_unknown_months():
    reference = [Segment(0, 3, "A"), Segment(1, 2, "B")]
    score = overlap_detection_score(reference, [(1, 2.5)])
    assert score["overlap_precision"] == pytest.approx(2 / 3)
    assert score["overlap_recall"] == 1
    assert score["false_overlap_sec"] == 0.5
    assert normalize_dates("ngày hai mươi tháng chín") == "ngày 20/9"
    assert normalize_dates("hai tháng hai mươi") == "hai tháng hai mươi"
