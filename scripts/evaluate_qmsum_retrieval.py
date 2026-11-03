"""Check production retrieval against QMSum manual evidence spans, without an LLM.

QMSum is English and spans can be broad. These scores diagnose context
selection, not semantic answer accuracy or Vietnamese product acceptance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from meeting_asr.ask import retrieve


def evaluate(root, out):
    meetings = [
        json.loads(line) for line in (root / "manifests/qmsum/val.jsonl").read_text().splitlines()
    ]
    rows = []
    started = time.perf_counter()
    variants = [
        ("production", 6, 12000),
        ("more_candidates_same_cap", 12, 12000),
        ("larger_context", 12, 24000),
    ]
    for meeting in meetings:
        fields = meeting["source_fields"]
        turns = [
            {
                "turn_id": str(i),
                "speaker": turn["speaker"],
                "text": turn["content"],
                "start": float(i),
                "end": float(i + 1),
                "flagged": False,
                "reviewed": True,
            }
            for i, turn in enumerate(fields["meeting_transcripts"])
        ]
        for index, query in enumerate(fields["specific_query_list"]):
            spans = [(int(a), int(b)) for a, b in query["relevant_text_span"]]
            relevant = {i for a, b in spans for i in range(a, b + 1)}
            for variant, top_k, max_chars in variants:
                retrieved = retrieve(query["query"], turns, top_k=top_k, max_chars=max_chars)
                ids = {int(t["turn_id"]) for t in retrieved}
                hits = [any(a <= i <= b for i in ids) for a, b in spans]
                rows.append(
                    {
                        "variant": variant,
                        "meeting_id": meeting["id"],
                        "query_index": index,
                        "query": query["query"],
                        "expected_spans": spans,
                        "retrieved_ids": sorted(ids),
                        "retrieved_turns": len(ids),
                        "relevant_turns": len(relevant),
                        "any_evidence_hit": bool(ids & relevant),
                        "every_span_hit": all(hits),
                        "span_hit_fraction": sum(hits) / len(hits),
                        "reference_turn_recall": len(ids & relevant) / len(relevant),
                        "retrieved_turn_precision": len(ids & relevant) / len(ids) if ids else 0,
                        "context_text_chars": sum(len(t["text"]) for t in retrieved),
                        "semantic_answer_score": None,
                    }
                )
    summaries = {}
    for variant, top_k, max_chars in variants:
        items = [r for r in rows if r["variant"] == variant]
        summaries[variant] = {
            "meetings": len(meetings),
            "specific_queries": len(items),
            "top_k": top_k,
            "max_chars": max_chars,
            **{
                key + "_rate": sum(r[key] for r in items) / len(items)
                for key in ("any_evidence_hit", "every_span_hit")
            },
            **{
                "mean_" + key: sum(r[key] for r in items) / len(items)
                for key in (
                    "span_hit_fraction",
                    "reference_turn_recall",
                    "retrieved_turn_precision",
                    "context_text_chars",
                )
            },
            "semantic_answer_score": None,
        }
    result = {
        "dataset": "QMSum validation",
        "mode": "retrieval only; no LLM calls",
        "source_manifest_sha256": hashlib.sha256(
            (root / "manifests/qmsum/val.jsonl").read_bytes()
        ).hexdigest(),
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "variants": summaries,
        "elapsed_sec": time.perf_counter() - started,
        "limitations": [
            "English supplemental evaluation, not Vietnamese product acceptance.",
            "A hit inside an annotated span does not prove a complete or correct answer.",
            "Broad spans make complete turn recall an unsuitable standalone acceptance target.",
            "Larger-context ablation uses a larger input budget; production settings unchanged.",
            "start/end values supplied to retrieval are ordinal positions, not audio timestamps.",
        ],
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "qmsum_retrieval_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    (out / "qmsum_retrieval_rows.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/gold/vi_asr_v1"))
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args()
    evaluate(arguments.root, arguments.out)
