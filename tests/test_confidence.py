import pytest

from meeting_asr.confidence import review_coverage, score_confidence, select_review
from meeting_asr.models import ASRSignals, DiarSignals, Turn, Utterance


def turn(index, duration=1, logprob=-0.2, overlap=0):
    u = Utterance(
        index,
        index + duration,
        "A",
        "xin chào",
        ASRSignals(avg_logprob=logprob),
        DiarSignals(overlap),
    )
    return Turn(str(index), u.start, u.end, "A", u.text, [u])


def test_missing_signals_renormalize_and_monotonicity():
    original = [turn(0, logprob=None)]
    result = score_confidence(original, weights={"asr": 0.5, "ovl": 0.5})
    assert result[0].confidence == 1
    assert original[0].confidence is None
    good = score_confidence([turn(0)])[0]
    bad = score_confidence([turn(0, logprob=-0.9, overlap=0.9)])[0]
    assert bad.confidence < good.confidence
    assert "độ tin cậy ASR thấp" in bad.flag_reasons
    assert "chồng lấn 90%" in bad.flag_reasons


def test_budget_skips_long_turns_and_breaks_ties_by_id():
    turns = [turn(0, duration=8, logprob=-1), turn(1, logprob=-0.8), turn(2, logprob=-0.8)]
    result = score_confidence(turns, target_coverage=0.2)
    assert {t.turn_id for t in result if t.flagged} == {"1", "2"}
    assert review_coverage(result) == pytest.approx(0.2)
    assert select_review(result, 0) == set()


def test_blacklist_keeps_text_and_random_is_reproducible():
    turns = [turn(i) for i in range(10)]
    turns[0].utterances[0].text = "cảm ơn các bạn đã xem"
    result = score_confidence(turns)
    assert result[0].confidence <= 0.05
    assert "hallucination_blacklist" in result[0].flag_reasons
    assert result[0].utterances[0].text == turns[0].utterances[0].text
    a = score_confidence(turns, variant="baseline_random")
    b = score_confidence(turns, variant="baseline_random")
    assert a == b
