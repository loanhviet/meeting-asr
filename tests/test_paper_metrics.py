import pytest

from meeting_asr.evaluation.paper import score_segments, validate_segments
from meeting_asr.settings import PROJECT_ROOT


@pytest.fixture
def scorer():
    python = PROJECT_ROOT / ".cache/paper-eval/venv/bin/python"
    if not python.exists():
        pytest.skip("install requirements/paper-evaluation.txt in the isolated scorer environment")
    return python


def segment(speaker, words, start=0, end=1):
    return {
        "session_id": "audio",
        "speaker": speaker,
        "words": words,
        "start_time": start,
        "end_time": end,
    }


def test_temporal_errors_are_not_reported_as_plain_cpwer(scorer):
    result = score_segments(
        [segment("A", "xin chào")],
        [segment("X", "xin chào", 20, 21)],
        collar=5,
        scorer_python=scorer,
    )
    assert result["metrics"]["cpwer"]["errors"] == 0
    assert result["metrics"]["tcpwer"]["errors"] == 4
    assert result["metrics"]["tcpwer"]["error_rate"] == 2
    assert result["metrics"]["tcorcwer"]["errors"] == 4


def test_global_speaker_permutation_and_empty_predictions(scorer):
    reference = [segment("A", "xin chào"), segment("B", "hẹn gặp", 2, 3)]
    swapped = [segment("Y", "xin chào"), segment("X", "hẹn gặp", 2, 3)]
    result = score_segments(reference, swapped, scorer_python=scorer)
    assert all(v["errors"] == 0 for v in result["metrics"].values())
    empty = score_segments(reference, [], scorer_python=scorer)
    assert all(v["errors"] == v["length"] == 4 for v in empty["metrics"].values())


def test_orc_does_not_penalize_merging_speaker_streams(scorer):
    reference = [segment("A", "xin chào"), segment("B", "hẹn gặp", 2, 3)]
    merged = [segment("X", "xin chào"), segment("X", "hẹn gặp", 2, 3)]
    result = score_segments(reference, merged, scorer_python=scorer)
    assert result["metrics"]["cpwer"]["errors"] > 0
    assert result["metrics"]["tcorcwer"]["errors"] == 0


@pytest.mark.parametrize("start,end", [(float("nan"), 1), (-1, 1), (2, 1), (True, 1)])
def test_invalid_scoring_timestamps_are_rejected(start, end):
    with pytest.raises(ValueError, match="timestamp"):
        validate_segments([segment("A", "x", start, end)])
