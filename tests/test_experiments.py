import pytest

from meeting_asr.evaluation.experiments import paired_bootstrap, transcript_scores
from meeting_asr.models import TranscriptDocument, Utterance


def test_transcript_comparison_and_paired_bootstrap_keep_negative_gaps():
    ref = TranscriptDocument(
        "x", 4, 16000, "a", [Utterance(0, 2, "A", "xin chào"), Utterance(2, 4, "B", "các bạn")]
    )
    hyp = TranscriptDocument(
        "x", 4, 16000, "a", [Utterance(0, 2, "Y", "xin chào"), Utterance(2, 4, "X", "các bạn")]
    )
    assert transcript_scores(ref, hyp)["cpwer"] == 0
    rows = [{"conversation_id": "one", "delta_cpwer": -0.1}] * 9
    rows += [{"conversation_id": "two", "delta_cpwer": 0.3}]
    result = paired_bootstrap(rows)
    assert result["conversations"] == 2
    assert result["mean"] == pytest.approx(0.1)
    assert result["ci_low"] < 0
