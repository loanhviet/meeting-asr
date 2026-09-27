import pytest

from meeting_asr.evaluation.experiments import (
    experiment_log_rows,
    paired_bootstrap,
    transcript_scores,
)
from meeting_asr.evaluation.log import COLUMNS, append_experiment_rows
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


def test_experiment_log_appends_without_replacing_earlier_rows(tmp_path):
    config = {"asr": {"masking": "none"}}
    source = [
        {
            "condition": "ovl0_clean",
            "backend": "pyannote",
            "config_hash": "abc",
            "relaxed_der": 0.1,
            "strict_der": 0.2,
            "relaxed_miss": 0.1,
            "relaxed_false_alarm": 0,
            "relaxed_confusion": 0,
            "wer": 0.3,
            "oracle_cpwer": 0.2,
            "cpwer": 0.4,
            "conversation_id": "c01",
        }
    ]
    first = experiment_log_rows(source, config, created="2026-09-27_120000", commit="deadbee")
    assert first[0]["run_id"] == "2026-09-27_120000_000"
    assert first[0]["cpwer_cascaded"] == 0.4
    assert first[0]["miss"] == 0.1
    path = tmp_path / "experiments.csv"
    append_experiment_rows(first, path)
    append_experiment_rows(
        [{"run_id": "later", "dataset": "second", "notes": "kept"}],
        path,
    )
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == ",".join(COLUMNS)
    assert len(lines) == 3
    assert "ovl0_clean" in lines[1]
    assert "second" in lines[2]
