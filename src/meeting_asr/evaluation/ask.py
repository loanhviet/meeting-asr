"""Report retrieval and answer checks; semantic correctness still needs review."""

from __future__ import annotations

from meeting_asr.ask import retrieve


def evaluate_questions(dataset, turns, answerer=None):
    rows = []
    for case in dataset["questions"]:
        context = retrieve(case["question"], turns)
        retrieved_ids = {turn["turn_id"] for turn in context}
        expected_ids = set(case["source_turn_ids"])
        row = {
            "question": case["question"],
            "expected_status": case["status"],
            "expected_answer": case["answer"],
            "expected_sources": sorted(expected_ids),
            "retrieved_sources": sorted(retrieved_ids),
            "retrieval_complete": expected_ids <= retrieved_ids if expected_ids else None,
        }
        if answerer is not None:
            try:
                answer = answerer.answer(case["question"], turns)
                cited = {i for point in answer["answer_points"] for i in point["source_turn_ids"]}
                row.update(
                    response=answer,
                    status_correct=answer["status"] == case["status"],
                    source_recall=len(cited & expected_ids) / len(expected_ids)
                    if expected_ids
                    else None,
                    # This is ID membership, not proof that a claim is semantically supported.
                    valid_source_ids=cited <= retrieved_ids,
                    semantic_review_required=True,
                )
            except (ValueError, RuntimeError, TypeError, KeyError, OSError) as exc:
                row.update(
                    error=type(exc).__name__, status_correct=False, semantic_review_required=True
                )
        rows.append(row)
    answerable = [row for row in rows if row["retrieval_complete"] is not None]
    missing = [row for row in rows if row["expected_status"] == "not_found"]
    return {
        "synthetic": bool(dataset.get("synthetic")),
        "mode": "retrieval-only" if answerer is None else "retrieval-and-provider",
        "questions": len(rows),
        "answerable_questions": len(answerable),
        "unanswerable_questions": len(missing),
        "retrieval_complete_rate": sum(row["retrieval_complete"] for row in answerable)
        / len(answerable)
        if answerable
        else None,
        "status_accuracy": sum(row["status_correct"] for row in rows) / len(rows)
        if answerer and rows
        else None,
        "abstention_accuracy": sum(row["status_correct"] for row in missing) / len(missing)
        if answerer and missing
        else None,
        "semantic_accuracy": None,
        "limitations": "Scripted synthetic data. ID validity/status checks do not measure semantic answer quality, ASR accuracy or real meeting performance.",
        "cases": rows,
    }
