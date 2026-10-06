import json

import pytest

from meeting_asr.evaluation.acceptance import (
    evaluate_meetings,
    llm_readiness,
    meeting_manifest,
    score_semantic_reviews,
)
from meeting_asr.io import write_minutes_json
from meeting_asr.models import MeetingMinutes, Turn
from meeting_asr.settings import load_config


def fixture_manifest(tmp_path):
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"acceptance audio fixture; no inference in this test")
    minutes = tmp_path / "minutes.json"
    write_minutes_json(
        minutes,
        MeetingMinutes(
            "meeting", 10, 1, [Turn("t0", 0, 8, "Linh", "Linh nhận kiểm thử trước thứ năm.", [])]
        ),
    )
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "meetings": [
                    {
                        "id": "meeting",
                        "synthetic": True,
                        "audio": audio.name,
                        "minutes": minutes.name,
                        "source_url": "fixture://local",
                        "license": "test fixture",
                        "questions": [
                            {
                                "id": "owner",
                                "question": "Ai nhận kiểm thử?",
                                "status": "found",
                                "answer": "Linh",
                                "source_turn_ids": ["t0"],
                            }
                        ],
                    }
                ]
            }
        )
    )
    return path


class Answerer:
    def __init__(self):
        self.identity = {
            "provider": "fixture",
            "model": "scripted",
            "prompt_version": "fixture-v1",
            "base_url": "https://example.invalid/v1?token=do-not-export",
        }

    def answer(self, question, turns):
        return {"status": "found", "answer_points": [{"text": "Linh", "source_turn_ids": ["t0"]}]}


class Summary:
    def summarize(self, turns):
        return {
            "summary": "Linh nhận kiểm thử.",
            "summary_points": [],
            "decisions": [],
            "topics": [],
            "action_items": [],
        }


def test_acceptance_defaults_to_retrieval_and_retains_provenance(tmp_path):
    report = evaluate_meetings(fixture_manifest(tmp_path), load_config(), tmp_path / "out")
    assert report["semantic_accuracy"] is None
    assert report["provider_mode"] == "none"
    meeting = report["meetings"][0]
    assert meeting["questions"]["retrieval_complete_rate"] == 1
    assert meeting["synthetic"] and meeting["summaries"] == {}
    assert len(meeting["audio_sha256"]) == 64


def test_acceptance_uses_edited_snapshot_and_review_state(tmp_path):
    path = fixture_manifest(tmp_path)
    minutes = tmp_path / "minutes.json"
    raw = json.loads(minutes.read_text())
    raw["turns"][0].update(
        text="Linh nhận kiểm thử trước thứ sáu.",
        original_text="lời chưa sửa",
        original_speaker="S0",
        speaker_id="S0",
        flagged=True,
        reviewed=True,
    )
    minutes.write_text(json.dumps({"edited": raw, "revision": 2}))

    class EditedSummary:
        def summarize(self, turns):
            assert turns[0].text.endswith("thứ sáu.") and not turns[0].flagged
            return {
                "summary": "Đã sửa",
                "summary_points": [],
                "decisions": [],
                "topics": [],
                "action_items": [],
            }

    report = evaluate_meetings(
        path,
        load_config(),
        tmp_path / "out",
        provider_mode="configured",
        answerer_factory=Answerer,
        summarizer_factory=lambda _: EditedSummary(),
    )
    assert report["meetings"][0]["turns"][0]["reviewed"]


def test_semantic_scores_require_explicit_reviews_and_matching_responses(tmp_path):
    out = tmp_path / "out"
    evaluate_meetings(
        fixture_manifest(tmp_path),
        load_config(),
        out,
        provider_mode="configured",
        answerer_factory=Answerer,
        summarizer_factory=lambda template: Summary(),
    )
    path = out / "review-template.json"
    report_path = out / "report.json"
    report = json.loads(report_path.read_text())
    assert report["meetings"][0]["questions"]["provider_identity"]["model"] == "scripted"
    assert "do-not-export" not in report_path.read_text()
    assert score_semantic_reviews(report_path, path)["correct_rate"] is None
    reviews = json.loads(path.read_text())
    assert len(reviews["reviews"]) == 4
    first = reviews["reviews"][0]
    first.update(
        correct=True,
        complete=True,
        supported=False,
        reviewed_by="reviewer",
        reviewed_at="2026-10-06T00:00:00Z",
    )
    path.write_text(json.dumps(reviews))
    scores = score_semantic_reviews(report_path, path)
    assert scores["reviewed_cases"] == 1 and scores["coverage"] == 0.25
    assert scores["supported_rate"] == 0
    first["response_sha256"] = "stale"
    path.write_text(json.dumps(reviews))
    with pytest.raises(ValueError, match="stale"):
        score_semantic_reviews(report_path, path)


def test_acceptance_rejects_wrong_gold_ids_and_duplicate_meetings(tmp_path):
    path = fixture_manifest(tmp_path)
    payload = json.loads(path.read_text())
    payload["meetings"][0]["questions"][0]["source_turn_ids"] = ["invented"]
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="gold source"):
        evaluate_meetings(path, load_config(), tmp_path / "out")
    payload["meetings"].append(payload["meetings"][0])
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="unique"):
        meeting_manifest(path)


@pytest.mark.parametrize("answer", [None, ""])
def test_unanswerable_questions_allow_missing_gold_answer(tmp_path, answer):
    path = fixture_manifest(tmp_path)
    payload = json.loads(path.read_text())
    payload["meetings"][0]["questions"].append(
        {
            "question": "Ngân sách bao nhiêu?",
            "status": "not_found",
            "answer": answer,
            "source_turn_ids": [],
        }
    )
    path.write_text(json.dumps(payload))
    report = evaluate_meetings(path, load_config(), tmp_path / "out")
    assert report["meetings"][0]["questions"]["unanswerable_questions"] == 1


def test_llm_check_does_not_expose_secrets_or_send_requests(monkeypatch):
    for key in [
        "MEETING_LLM_PROVIDER",
        "MEETING_LLM_MODEL",
        "MEETING_LLM_BASE_URL",
        "MEETING_LLM_API_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)
    assert not llm_readiness({})["ready"]
    monkeypatch.setenv("MEETING_LLM_API_KEY", "never-print-this")
    report = llm_readiness({"provider": "http", "model": "chosen", "base_url": "http://local/v1"})
    assert report["ready"] and report["requests_sent"] == 0
    assert "never-print-this" not in json.dumps(report)
