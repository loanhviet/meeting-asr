import json
from pathlib import Path

from meeting_asr.evaluation.ask import evaluate_questions


def test_synthetic_suite_retrieves_gold_and_does_not_claim_semantic_accuracy():
    dataset = json.loads((Path(__file__).parent / "fixtures/askmeeting.json").read_text())
    turns = [
        {"turn_id": f"t{i:02d}", "text": text, "speaker": dataset["speakers"][i % 2]}
        for i, text in enumerate(dataset["script"])
    ]
    report = evaluate_questions(dataset, turns)
    assert report["questions"] == 14
    assert report["retrieval_complete_rate"] == 1
    assert report["unanswerable_questions"] == 6
    assert report["semantic_accuracy"] is None and report["status_accuracy"] is None


def test_independent_conversation_retrieves_owner_correction_and_open_status():
    dataset = json.loads((Path(__file__).parent / "fixtures/askmeeting_holdout.json").read_text())
    turns = [
        {"turn_id": f"t{i:02d}", "text": text, "speaker": dataset["speakers"][i % 2]}
        for i, text in enumerate(dataset["script"])
    ]
    report = evaluate_questions(dataset, turns)
    assert report["retrieval_complete_rate"] == 1
    assert report["answerable_questions"] == report["unanswerable_questions"] == 3
