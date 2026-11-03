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


def test_each_weak_signal_has_its_vietnamese_reason():
    speech, repeat, speaker, short = (turn(index) for index in range(4))
    speech.utterances[0].asr.no_speech_prob = 0.8
    repeat.utterances[0].asr.compression_ratio = 6
    speaker.utterances[0].diar = DiarSignals(0, 0.2)
    short.utterances[0].end = short.end = short.start + 0.3
    reasons = {
        item.turn_id: item.flag_reasons
        for item in score_confidence(
            [speech, repeat, speaker, short], margin_ref=1, target_coverage=0
        )
    }
    assert "nghi không có tiếng nói" in reasons["0"]
    assert "nghi lặp/ảo giác" in reasons["1"]
    assert "khó phân biệt người nói" in reasons["2"]
    assert "đoạn quá ngắn" in reasons["3"]


def test_blacklist_keeps_text_and_random_is_reproducible():
    turns = [turn(i) for i in range(10)]
    turns[0].utterances[0].text = "cảm ơn các bạn đã xem"
    result = score_confidence(turns)
    assert result[0].confidence <= 0.05
    assert "nghi cụm ảo giác đã biết" in result[0].flag_reasons
    assert result[0].utterances[0].text == turns[0].utterances[0].text
    a = score_confidence(turns, variant="baseline_random")
    b = score_confidence(turns, variant="baseline_random")
    assert a == b


def test_decoding_loops_are_always_flagged_and_backchannels_skip_the_budget():
    from meeting_asr.postprocess import postprocess

    def utt(start, end, speaker, text, ratio=1.0):
        return Utterance(
            start, end, speaker, text, ASRSignals(compression_ratio=ratio), DiarSignals(0)
        )

    utterances = [
        utt(0, 6, "A", "nhà em ở gần chợ nên mọi thứ rất nhộn nhịp"),
        utt(5.6, 6.1, "B", "ừ"),
        utt(6.4, 12, "A", "mọi người hay nói chuyện với nhau"),
        utt(12.5, 43, "A", "ừ " * 200, ratio=44.0),
        utt(44, 45, "B", "không"),
    ]
    turns = postprocess(utterances)
    # A's speech is no longer split by B's "ừ"; the interjection stays a separate turn.
    assert [(t.speaker, t.backchannel) for t in turns] == [
        ("A", False),
        ("B", True),
        ("B", False),
    ]
    assert "nhộn nhịp mọi người" in turns[0].text
    scored = score_confidence(turns, target_coverage=0.0)
    # The loop is inside A's first turn: flagged even with a zero review budget.
    assert scored[0].flagged and "nghi lặp/ảo giác" in scored[0].flag_reasons
    assert not scored[1].flagged
    assert not score_confidence(turns, target_coverage=0.0, variant="no_diar")[0].flagged
