import json

import pytest

from meeting_asr.evaluation.confidence import calibrate_margin, label_turns, variant_metrics
from meeting_asr.models import TranscriptDocument, Turn, Utterance


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
