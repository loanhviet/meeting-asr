"""Compare Kimi correction suggestions against frozen ASR dev predictions.

Inference inputs contain hypotheses and domain metadata only. Source references
are used by the scorer after each model response. Glossary terms are supplied
independently, never extracted automatically from reference transcripts.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import jiwer
from run_asr_dev_baseline import error_counts, write_json

from meeting_asr.correction import KimiProvider, propose_correction, source_hash
from meeting_asr.evaluation.metrics import normalize_for_wer


def reference_unit_changes(reference, before, after):
    """Flag previously correct reference units damaged even when total WER falls.

    This follows jiwer's alignment, can be ambiguous with repeated words, and does
    not count newly inserted words. It is a review signal, not semantic proof.
    """
    ref = normalize_for_wer(reference)

    def correct_units(hypothesis):
        aligned = jiwer.process_words(ref, normalize_for_wer(hypothesis))
        return {
            index
            for chunk in aligned.alignments[0]
            if chunk.type == "equal"
            for index in range(chunk.ref_start_idx, chunk.ref_end_idx)
        }

    old, new = correct_units(before), correct_units(after)
    return {
        "restored": len(new - old),
        "damaged": len(old - new),
        "damaged_reference_tokens": [ref.split()[i] for i in sorted(old - new)],
    }


def aggregate(rows):
    result = {
        "clips": len(rows),
        "api_failed": sum(r["status"] == "api_failed" for r in rows),
        "changed_clips": sum(r["hypothesis"] != r["corrected"] for r in rows),
        "improved_clips": sum(r["wer"]["errors"] < r["baseline_wer"]["errors"] for r in rows),
        "worsened_clips": sum(r["wer"]["errors"] > r["baseline_wer"]["errors"] for r in rows),
        "damaged_correct_clips": sum(
            r["baseline_wer"]["errors"] == 0 and r["wer"]["errors"] > 0 for r in rows
        ),
        "accepted_patch_suggestions": sum(len(r["correction"].get("edits", [])) for r in rows),
        "rejected_patch_suggestions": sum(
            len(r["correction"].get("rejected_edits", [])) for r in rows
        ),
        "cache_hits": sum(r["correction"].get("cache_hit", False) for r in rows),
        "restored_reference_units": sum(
            r.get("reference_unit_changes", {}).get("restored", 0) for r in rows
        ),
        "damaged_reference_units": sum(
            r.get("reference_unit_changes", {}).get("damaged", 0) for r in rows
        ),
    }
    for metric in ("wer", "cer", "baseline_wer", "baseline_cer"):
        count = {
            k: sum(r[metric][k] for r in rows)
            for k in (
                "substitutions",
                "deletions",
                "insertions",
                "hits",
                "errors",
                "reference_units",
            )
        }
        count["rate"] = (
            count["errors"] / count["reference_units"] if count["reference_units"] else None
        )
        result[metric] = count
    usage = Counter()
    for row in rows:
        if row["correction"].get("cache_hit"):
            continue
        for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
            usage[name] += row["correction"].get("usage", {}).get(name, 0)
    result["observed_usage_non_cached"] = dict(usage)
    result["requests_with_unknown_usage"] = sum(
        r["status"] == "api_failed"
        and not r["correction"].get("usage")
        and not r["correction"].get("cache_hit")
        for r in rows
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--api-key-csv", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--glossary", type=Path, default=Path("configs/correction-glossary.vi.json")
    )
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("--workers must be between 1 and 4")
    baseline_summary = json.loads((args.baseline / "summary.json").read_text())
    if not baseline_summary["complete"]:
        raise ValueError("finish the ASR baseline before LLM comparison")
    baseline_bytes = (args.baseline / "predictions.jsonl").read_bytes()
    baseline = [json.loads(line) for line in baseline_bytes.decode().splitlines()]
    if any(row["status"] != "ok" for row in baseline):
        raise ValueError("inspect baseline failures before testing corrections")
    glossary = json.loads(args.glossary.read_text())
    provider = KimiProvider.from_csv(args.api_key_csv, model="kimi-k3")
    args.out.mkdir(parents=True, exist_ok=True)
    previous_summary = args.out / "summary.json"
    if previous_summary.exists() and json.loads(previous_summary.read_text()).get("complete"):
        raise ValueError(
            "completed comparison exists; use a new --out or run report_llm_correction.py"
        )
    all_rows, inputs, text_results = [], [], {}
    contexts = {
        "vietmed": "Lời nói tiếng Việt trong nội dung y tế.",
        "fleurs_vi": "Lời đọc tiếng Việt về các chủ đề tổng quát.",
    }
    experiment = {
        "model": "kimi-k3",
        "baseline_sha256": source_hash(baseline_bytes.decode()),
        "glossary_sha256": source_hash(args.glossary.read_text()),
        "reference_sent_to_model": False,
        "audio_sent_to_model": False,
        "test_set_used": False,
        "source_reference_status": "not_project_verified",
        "glossary_origin": "20 generic medical terms; no reference-derived entity list",
        "max_change_fraction": 0.35,
        "max_output_tokens": 4096,
        "variants": ["text", "glossary"],
    }
    write_json(args.out / "experiment.json", experiment)

    def run_one(row, variant):
        terms = glossary.get(row["dataset"], []) if variant == "glossary" else []
        inference_input = {
            "variant": variant,
            "target": {"turn_id": row["id"], "text": row["hypothesis"]},
            "context": contexts[row["dataset"]],
            "glossary": terms,
        }
        if variant == "glossary" and not terms:
            previous = text_results[row["id"]]
            return inference_input, {
                **previous,
                "variant": variant,
                "correction": {
                    **previous["correction"],
                    "cache_hit": True,
                    "reused_variant": "text",
                },
            }
        try:
            correction = propose_correction(
                provider,
                inference_input["target"],
                context=inference_input["context"],
                glossary=terms,
                cache_dir=args.out / "cache",
            )
            status, error = "ok", None
            corrected = correction["suggested_text"]
        except (OSError, RuntimeError, ValueError, TypeError, KeyError) as exc:
            status, error = "api_failed", str(exc)
            corrected = row["hypothesis"]
            correction = {
                "edits": [],
                "rejected_edits": [],
                "status": "api_failed",
                **getattr(exc, "metadata", {}),
            }
        result = {
            "id": row["id"],
            "dataset": row["dataset"],
            "variant": variant,
            "status": status,
            "error": error,
            "hypothesis": row["hypothesis"],
            "corrected": corrected,
            "reference": row["reference"],
            "correction": correction,
            "baseline_wer": row["wer"],
            "baseline_cer": row["cer"],
            "wer": error_counts(row["reference"], corrected),
            "cer": error_counts(row["reference"], corrected, characters=True),
            "reference_unit_changes": reference_unit_changes(
                row["reference"], row["hypothesis"], corrected
            ),
        }
        return inference_input, result

    started = time.perf_counter()
    for variant in experiment["variants"]:
        variant_rows = []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(run_one, row, variant) for row in baseline]
            for future in as_completed(futures):
                model_input, result = future.result()
                inputs.append(model_input)
                variant_rows.append(result)
                write_json(
                    args.out / variant / f"{result['dataset']}_{Path(result['id']).stem}.json",
                    result,
                )
                print(
                    json.dumps(
                        {
                            "variant": variant,
                            "completed": len(variant_rows),
                            "of": len(baseline),
                            "id": result["id"],
                            "status": result["status"],
                            "baseline_wer": result["baseline_wer"]["rate"],
                            "corrected_wer": result["wer"]["rate"],
                            "patches": len(result["correction"]["edits"]),
                        }
                    ),
                    flush=True,
                )
        all_rows.extend(sorted(variant_rows, key=lambda r: (r["dataset"], r["id"])))
        if variant == "text":
            text_results.update({row["id"]: row for row in variant_rows})
        datasets = sorted({r["dataset"] for r in baseline})
        results = {
            v: {
                "overall": aggregate([r for r in all_rows if r["variant"] == v]),
                "by_dataset": {
                    d: aggregate([r for r in all_rows if r["variant"] == v and r["dataset"] == d])
                    for d in datasets
                },
            }
            for v in experiment["variants"]
            if any(r["variant"] == v for r in all_rows)
        }
        write_json(
            args.out / "summary.json",
            {
                "complete": variant == experiment["variants"][-1],
                "experiment": experiment,
                "elapsed_sec": time.perf_counter() - started,
                "results": results,
            },
        )
        for name, rows in (("inference_inputs.jsonl", inputs), ("results.jsonl", all_rows)):
            (args.out / name).write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
            )
    if (args.baseline / "predictions.jsonl").read_bytes() != baseline_bytes:
        raise RuntimeError("baseline predictions were modified during comparison")


if __name__ == "__main__":
    main()
