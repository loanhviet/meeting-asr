import json

import pytest

from meeting_asr.evaluation.confidence import calibrate_margin, label_turns, variant_metrics
from meeting_asr.io import write_minutes_json, write_transcript_json
from meeting_asr.models import (
    ASRSignals,
    DiarSignals,
    MeetingMinutes,
    TranscriptDocument,
    Turn,
    Utterance,
)
from meeting_asr.settings import load_config


def test_turn_labels_include_all_matching_reference_and_report_unreviewable_speech():
    reference = TranscriptDocument(
        "x",
        6,
        16000,
        "a",
        [
            Utterance(0, 1, "A", "xin"),
            Utterance(1, 2, "A", "chào"),
            Utterance(4, 6, "B", "các bạn"),
        ],
    )
    utterance = Utterance(0, 2, "X", "xin chào")
    turns = [Turn("0", 0, 2, "X", "Xin chào", [utterance], 0.9)]
    labels, missed = label_turns(turns, reference)
    assert not labels[0].is_bad
    assert labels[0].reference_words == 2
    assert missed == pytest.approx(0.5)
    metrics = variant_metrics(turns, labels, 1)
    assert metrics["remaining_wer"] == 0


def test_calibration_rejects_test_data(tmp_path):
    manifest = tmp_path / "test.json"
    manifest.write_text(json.dumps({"split": "test", "sessions": [{"minutes": "x"}]}))
    with pytest.raises(ValueError, match="dev"):
        calibrate_margin(manifest, tmp_path / "calibration.json")


def test_dev_calibration_fits_and_loads_frozen_weights(tmp_path, monkeypatch):
    reference = TranscriptDocument(
        "x", 6, 16000, "fixture", [Utterance(i, i + 1, "A", "xin chào") for i in range(6)]
    )
    utterances = [
        Utterance(
            i,
            i + 1,
            "A",
            "sai" if i == 0 else "xin chào",
            ASRSignals(avg_logprob=-0.9 if i == 0 else -0.1),
            DiarSignals(0, 0.2 + i / 10),
        )
        for i in range(6)
    ]
    turns = [Turn(str(i), u.start, u.end, u.speaker, u.text, [u]) for i, u in enumerate(utterances)]
    write_minutes_json(tmp_path / "minutes.json", MeetingMinutes("x", 6, 1, turns))
    write_transcript_json(tmp_path / "reference.json", reference)
    manifest = tmp_path / "dev.json"
    manifest.write_text(
        json.dumps(
            {
                "split": "dev",
                "sessions": [
                    {"split": "dev", "minutes": "minutes.json", "reference_json": "reference.json"}
                ],
            }
        )
    )
    output = tmp_path / "calibration.json"
    result = calibrate_margin(manifest, output, fit_weights=True, trials=4)
    assert result["dev_mean_f1"] == 1
    monkeypatch.setenv("MEETING_CONFIDENCE_CALIBRATION", str(output))
    config = load_config()
    assert config["confidence"]["weights"] == result["weights"]
    assert config["confidence"]["margin_ref"] == result["margin_ref"]
