"""Run the unmodified DiariZen + DiCoW pipeline on a deterministic dev subset.

No LLM calls, oracle diarization, prompt tuning, or test-set selection. References
are read only by the selection/scoring process, never sent to inference. Each
clip uses the existing pipeline and isolated author subprocess as in production.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import subprocess
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import jiwer
import yaml

from meeting_asr.evaluation.metrics import normalize_for_wer
from meeting_asr.pipeline import run_pipeline
from meeting_asr.runtime import file_sha256
from meeting_asr.settings import config_hash, load_config


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def select_dev(root, fleurs_count):
    rng = random.Random(42)
    med = read_rows(root / "pilot/references/dev.jsonl")
    buckets = defaultdict(list)
    for row in sorted(med, key=lambda r: r["id"]):
        if row["duration_sec"] >= 5:
            buckets[row["speaker_id"]].append(row)
    selected = []
    for speaker in sorted(buckets):
        rng.shuffle(buckets[speaker])
        selected.append(buckets[speaker][0])
    fleurs = read_rows(root / "manifests/fleurs_vi/dev.jsonl")
    rng.shuffle(fleurs)
    genders = defaultdict(list)
    for row in fleurs:
        if row["duration_sec"] >= 5:
            genders[row["gender"]].append(row)
    seen = set()
    while len(seen) < fleurs_count:
        before = len(seen)
        for gender in sorted(genders):
            while genders[gender]:
                row = genders[gender].pop()
                if row["prompt_id"] not in seen:
                    selected.append(row)
                    seen.add(row["prompt_id"])
                    break
            if len(seen) == fleurs_count:
                break
        if len(seen) == before:
            raise ValueError("not enough distinct eligible FLEURS dev prompts")
    if any(row["split"] != "dev" for row in selected):
        raise ValueError("only dev data may enter this experiment")
    return selected


def error_counts(reference, hypothesis, *, characters=False):
    ref, hyp = normalize_for_wer(reference), normalize_for_wer(hypothesis)
    if characters:
        ref, hyp = ref.replace(" ", ""), hyp.replace(" ", "")
        result = jiwer.process_characters(ref, hyp)
    else:
        result = jiwer.process_words(ref, hyp)
    errors = result.substitutions + result.deletions + result.insertions
    units = result.hits + result.substitutions + result.deletions
    return {
        "substitutions": result.substitutions,
        "deletions": result.deletions,
        "insertions": result.insertions,
        "hits": result.hits,
        "errors": errors,
        "reference_units": units,
        "rate": errors / units if units else None,
    }


def aggregate(rows):
    result = {
        "clips": len(rows),
        "success": sum(r["status"] == "ok" for r in rows),
        "failed": sum(r["status"] != "ok" for r in rows),
        "audio_sec": sum(r["duration_sec"] for r in rows),
        "elapsed_sec_sum": sum(r["elapsed_sec"] for r in rows),
        "predicted_multi_speaker_clips": sum(r.get("predicted_speakers", 0) > 1 for r in rows),
    }
    for metric in ("wer", "cer", "display_wer"):
        counts = {
            key: sum(r[metric][key] for r in rows)
            for key in (
                "substitutions",
                "deletions",
                "insertions",
                "hits",
                "errors",
                "reference_units",
            )
        }
        counts["rate"] = (
            counts["errors"] / counts["reference_units"] if counts["reference_units"] else None
        )
        result[metric] = counts
    return result


def summarize(destination, rows, complete, total, experiment):
    datasets = sorted({r["dataset"] for r in rows})
    summary = {
        "complete": complete,
        "planned_clips": total,
        "completed_clips": len(rows),
        "llm_enabled": False,
        "oracle_rttm": None,
        "reference_status": "source_provided_not_project_verified",
        "experiment": experiment,
        "overall": aggregate(rows),
        "by_dataset": {d: aggregate([r for r in rows if r["dataset"] == d]) for d in datasets},
        "notes": [
            "WER uses project normalization and whitespace-separated units.",
            "CER uses the same normalization, removes spaces, keeps Vietnamese diacritics.",
            "Corpus rates sum edit counts per clip; alignment never crosses clip boundaries.",
            "Primary hypothesis is raw timestamped ASR text, all predicted speakers retained.",
            "display_wer additionally scores existing turn postprocessing; no LLM correction.",
            "Failed pipeline clips count as empty hypotheses, not silently excluded.",
            "Single-clip subprocess startup/model loading is included in elapsed time.",
            "No timestamped speaker references for this subset; DER/cpWER not measured.",
            "Small dev subset; no independent listening audit or statistical generalization.",
        ],
    }
    write_json(destination / "summary.json", summary)
    fields = [
        "id",
        "dataset",
        "status",
        "duration_sec",
        "reference",
        "hypothesis",
        "display_hypothesis",
        "wer",
        "cer",
        "display_wer",
        "predicted_speakers",
        "elapsed_sec",
        "error",
    ]
    with (destination / "review.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            value = {k: row.get(k) for k in fields}
            for key in ("wer", "cer", "display_wer"):
                value[key] = row[key]["rate"]
            writer.writerow(value)
    with (destination / "predictions.jsonl").open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/gold/vi_asr_v1"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--fleurs-clips", type=int, default=12)
    args = parser.parse_args()
    if args.fleurs_clips < 1:
        parser.error("--fleurs-clips must be positive")
    os.environ["MEETING_LLM_ENABLED"] = "false"
    os.environ["MEETING_DEVICE"] = "cuda"
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("MKL_NUM_THREADS", "2")
    root, destination = args.root.resolve(), args.out.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    config = load_config()
    config["runtime"]["device"] = "cuda"
    config["llm"]["enabled"] = False
    config["paths"]["cache_dir"] = str(destination / "cache")
    config["paths"]["results_dir"] = str(destination)
    selected = select_dev(root, args.fleurs_clips)
    for row in selected:
        path = (root / row["audio_path"]).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        row["audio_sha256"] = file_sha256(path)
    signature = hashlib.sha256(json.dumps(selected, sort_keys=True).encode()).hexdigest()
    experiment = {
        "config_hash": config_hash(config),
        "selection_sha256": signature,
        "seed": 42,
        "selection": "one >=5s clip per eligible pilot dev speaker; "
        "round-robin available FLEURS gender labels with distinct prompt IDs; no ASR-based filtering",
        "created_at": datetime.now(UTC).isoformat(),
        "labels_sent_to_inference": False,
    }
    saved = destination / "selection.json"
    if saved.exists() and json.loads(saved.read_text())["selection_sha256"] != signature:
        raise ValueError("existing output belongs to a different selection")
    write_json(saved, {**experiment, "rows": selected})
    (destination / "config.yaml").write_text(
        yaml.safe_dump(config, allow_unicode=True), encoding="utf-8"
    )
    rows = []
    print(
        json.dumps(
            {
                "planned_clips": len(selected),
                "audio_sec": sum(r["duration_sec"] for r in selected),
                "by_dataset": dict(Counter(r["dataset"] for r in selected)),
            }
        ),
        flush=True,
    )
    for index, source in enumerate(selected, 1):
        folder = destination / "clips" / source["dataset"] / Path(source["id"]).stem
        hypothesis = display = ""
        error, predicted_speakers, status = None, None, "ok"
        start = time.perf_counter()
        try:
            previous = folder / "run.json"
            reuse = False
            if previous.exists():
                run = json.loads(previous.read_text())
                reuse = (
                    run["config_hash"] == experiment["config_hash"]
                    and run["audio_sha256"] == source["audio_sha256"]
                )
            if not reuse:
                run_pipeline(root / source["audio_path"], config, folder, no_cache=True)
            transcript = json.loads((folder / "transcript.json").read_text())
            minutes = json.loads((folder / "minutes.json").read_text())
            summary_status = json.loads((folder / "summary_status.json").read_text())
            if summary_status["enabled"]:
                raise ValueError("LLM must remain disabled")
            hypothesis = " ".join(u["text"] for u in transcript["utterances"])
            display = " ".join(t["text"] for t in minutes["turns"])
            predicted_speakers = transcript["num_speakers"]
            elapsed = json.loads((folder / "run.json").read_text())["result"]["elapsed_sec"]
        except (
            OSError,
            RuntimeError,
            ValueError,
            KeyError,
            TypeError,
            subprocess.SubprocessError,
        ) as exc:
            elapsed = time.perf_counter() - start
            status, error = "failed", f"{type(exc).__name__}: {exc}"
        row = {
            "id": source["id"],
            "dataset": source["dataset"],
            "status": status,
            "duration_sec": source["duration_sec"],
            "audio_sha256": source["audio_sha256"],
            "recording_id": source.get("recording_id"),
            "speaker_id": source.get("speaker_id"),
            "accent": source.get("accent"),
            "gender": source.get("gender"),
            "reference": source["reference_text"],
            "hypothesis": hypothesis,
            "display_hypothesis": display,
            "predicted_speakers": predicted_speakers,
            "elapsed_sec": elapsed,
            "error": error,
            "wer": error_counts(source["reference_text"], hypothesis),
            "cer": error_counts(source["reference_text"], hypothesis, characters=True),
            "display_wer": error_counts(source["reference_text"], display),
        }
        rows.append(row)
        write_json(folder / "score.json", row)
        summarize(destination, rows, index == len(selected), len(selected), experiment)
        print(
            json.dumps(
                {
                    "completed": index,
                    "of": len(selected),
                    "id": source["id"],
                    "dataset": source["dataset"],
                    "status": status,
                    "wer": row["wer"]["rate"],
                    "elapsed_sec": round(elapsed, 1),
                }
            ),
            flush=True,
        )
        if len(rows) >= 3 and all(r["status"] == "failed" for r in rows[-3:]):
            raise RuntimeError("three consecutive inference failures; inspect local runtime logs")


if __name__ == "__main__":
    main()
