from __future__ import annotations

import unicodedata

import pytest

from meeting_asr.evaluation.metrics import (
    cp_word_error_rate,
    diarization_error_rate,
    normalize_for_wer,
    score_diarization,
    word_error_rate,
)
from meeting_asr.evaluation.overlap import measure_overlap_ratio
from meeting_asr.models import Segment


def test_overlap_ratio_calc() -> None:
    cases = [
        ([Segment(0, 1, "A"), Segment(2, 3, "B")], 0.0),
        ([Segment(0, 1, "A"), Segment(1, 2, "B")], 0.0),
        ([Segment(0, 2, "A"), Segment(1, 3, "B")], 1 / 3),
        ([Segment(0, 2, "A"), Segment(0, 2, "B")], 1.0),
        ([Segment(0, 4, "A"), Segment(1, 2, "B"), Segment(3, 5, "C")], 0.4),
        ([Segment(0, 2, "A"), Segment(1, 3, "A")], 0.0),
    ]
    for segments, expected in cases:
        assert measure_overlap_ratio(segments) == pytest.approx(expected)


def test_wer_nfc_normalization() -> None:
    nfc = "chữ ế"
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    assert word_error_rate(nfc, nfd) == 0
    assert word_error_rate("Xin chào!", "xin chào") == 0
    assert normalize_for_wer("Xin chào!") == "xin chào"
    assert word_error_rate("một hai ba", "một hai") == pytest.approx(1 / 3)


def test_cpwer_permutation() -> None:
    reference = {"SPEAKER_00": "một hai ba", "SPEAKER_01": "bốn năm"}
    swapped = {"X": "bốn năm", "Y": "một hai ba"}
    renamed = {"SPEAKER_9": "bốn năm", "SPEAKER_1": "một hai ba"}
    assert cp_word_error_rate(reference, swapped) == 0
    assert cp_word_error_rate(reference, renamed) == 0
    one_error = {"X": "bốn năm", "Y": "một hai bốn"}
    assert cp_word_error_rate(reference, one_error) == pytest.approx(0.2)
    nfd = {
        "X": unicodedata.normalize("NFD", "bốn năm"),
        "Y": unicodedata.normalize("NFD", "một hai ba"),
    }
    assert cp_word_error_rate(reference, nfd) == 0


def test_der_reports_both_modes() -> None:
    reference = [Segment(0, 10, "A"), Segment(10, 20, "B")]
    perfect = [Segment(0, 10, "OTHER"), Segment(10, 20, "NAMES")]
    missed = [Segment(0, 8, "A"), Segment(10, 20, "B")]
    confused = [Segment(0, 10, "A"), Segment(10, 20, "A")]
    alarm = [Segment(0, 10, "A"), Segment(10, 22, "B")]

    perfect_scores = score_diarization(reference, perfect)
    assert perfect_scores["relaxed"].der == pytest.approx(0)
    assert perfect_scores["strict"].der == pytest.approx(0)

    strict_miss = score_diarization(reference, missed)["strict"]
    assert strict_miss.miss == pytest.approx(0.1)
    assert strict_miss.false_alarm == pytest.approx(0)
    assert strict_miss.confusion == pytest.approx(0)
    assert strict_miss.der == pytest.approx(0.1)

    strict_confusion = score_diarization(reference, confused)["strict"]
    assert strict_confusion.confusion == pytest.approx(0.5)
    assert strict_confusion.der == pytest.approx(0.5)

    strict_alarm = score_diarization(reference, alarm)["strict"]
    assert strict_alarm.false_alarm == pytest.approx(0.1)
    assert strict_alarm.der == pytest.approx(0.1)
    assert score_diarization(reference, missed)["relaxed"].collar == 0.25
    assert score_diarization(reference, missed)["strict"].skip_overlap is False


def test_der_keeps_speakers_with_identical_boundaries() -> None:
    reference = [Segment(0, 10, "A"), Segment(0, 10, "B")]
    hypothesis = [Segment(0, 10, "B")]
    score = diarization_error_rate(reference, hypothesis, collar=0, skip_overlap=False)
    assert score.der == pytest.approx(0.5)
    assert score.miss == pytest.approx(0.5)
