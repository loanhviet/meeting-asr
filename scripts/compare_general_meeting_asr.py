"""Compare DiCoW to PhoWhisper using exactly the saved predicted DiariZen turns.

This is a diagnostic acoustic/cascade comparison, not an isolated FDDT ablation
or a rerun of the historical Pyannote baseline. No reference enters the worker.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def prepare(out):
    selection = json.loads((out / "selection.json").read_text())
    hub = Path.home() / ".cache/huggingface/hub/models--vinai--PhoWhisper-medium"
    revision = (hub / "refs/main").read_text().strip()
    model = hub / "snapshots" / revision
    if not model.is_dir():
        raise FileNotFoundError("cached PhoWhisper snapshot unavailable")
    rows = []
    for row in selection["rows"]:
        if row["mode"] != "pipeline" or row["dataset"] not in {"fleurs_vi", "vimd", "vietmed"}:
            continue
        folder = out / "pipeline" / row["dataset"] / Path(row["id"]).stem
        run = json.loads((folder / "run.json").read_text())
        if run["audio_sha256"] != row["audio_sha256"]:
            raise ValueError("saved production run uses different source audio")
        key = next(s["key"] for s in run["result"]["stages"] if s["stage"] == "M1")
        rows.append(
            {
                "id": row["id"],
                "dataset": row["dataset"],
                "duration_sec": row["duration_sec"],
                "audio_sha256": row["audio_sha256"],
                "audio_array": str(out / "cache/preprocess" / (key + ".npy")),
                "audio_metadata": str(out / "cache/preprocess" / (key + ".json")),
                "predicted_rttm": str(folder / "diarization.rttm"),
                "output": str(
                    out / "phowhisper-control" / row["dataset"] / (Path(row["id"]).stem + ".json")
                ),
            }
        )
    value = {
        "model_name": "vinai/PhoWhisper-medium",
        "model_revision": revision,
        "model_path": str(model),
        "config": {
            "batch_size": 1,
            "boundary_pad": 0.1,
            "max_segment_sec": 28.0,
            "min_segment_sec": 0.3,
            "merge_same_speaker_gap": 0.0,
        },
        "note": "Production M1 + predicted DiariZen reused, no oracle, no LLM; backbone and conditioning method differ.",
        "inputs": rows,
    }
    (out / "phowhisper_inputs.json").write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps({"planned_controls": len(rows), "model_revision": revision}), flush=True)


def worker(out):
    import importlib.metadata

    import numpy as np
    import torch

    sys.path.insert(0, str(PROJECT / "src"))
    from meeting_asr.asr import WhisperDecoder, transcribe
    from meeting_asr.diarization import DiarizationResult
    from meeting_asr.io import read_rttm
    from meeting_asr.models import AudioBundle, DiarSignals, Segment

    payload = json.loads((out / "phowhisper_inputs.json").read_text())
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    torch.manual_seed(42)
    decoder = WhisperDecoder(payload["model_path"], device="cuda")
    for index, row in enumerate(payload["inputs"], 1):
        target = Path(row["output"])
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and json.loads(target.read_text())["status"] == "ok":
            continue
        started = time.perf_counter()
        meta = json.loads(Path(row["audio_metadata"]).read_text())
        audio = AudioBundle(
            np.load(row["audio_array"], allow_pickle=False),
            meta["sr"],
            meta["original_sr"],
            meta["source_path"],
        )
        # Crop only model frame padding outside physical audio, without using a reference.
        raw = read_rttm(row["predicted_rttm"])
        segments = [
            Segment(s.start, min(s.end, audio.duration), s.speaker)
            for s in raw
            if s.start < audio.duration
        ]
        diarization = DiarizationResult(segments, [DiarSignals(0.0) for _ in segments], "diarizen")
        status, error, utterances = "ok", None, []
        try:
            utterances = transcribe(
                audio, diarization, decoder=decoder, device="cuda", **payload["config"]
            )
        except (ValueError, RuntimeError, OSError, TypeError) as exc:
            status, error = "failed", f"{type(exc).__name__}: {exc}"
        value = {
            "status": status,
            "error": error,
            "utterances": [asdict(u) for u in utterances],
            "audio_sha256": row["audio_sha256"],
            "elapsed_sec": time.perf_counter() - started,
            "model_name": payload["model_name"],
            "model_revision": payload["model_revision"],
            "device": "cuda",
            "transformers": importlib.metadata.version("transformers"),
        }
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(target)
        print(
            json.dumps(
                {
                    "control": index,
                    "of": len(payload["inputs"]),
                    "id": row["id"],
                    "status": status,
                    "elapsed_sec": round(value["elapsed_sec"], 2),
                }
            ),
            flush=True,
        )
    decoder.close()


def score(out):
    from collections import defaultdict

    sys.path.insert(0, str(PROJECT / "scripts"))
    from run_asr_dev_baseline import error_counts

    selection = json.loads((out / "selection.json").read_text())
    rows = []
    for source in selection["rows"]:
        if source["mode"] != "pipeline" or source["dataset"] not in {
            "fleurs_vi",
            "vimd",
            "vietmed",
        }:
            continue
        target = (
            out / "phowhisper-control" / source["dataset"] / (Path(source["id"]).stem + ".json")
        )
        control = json.loads(target.read_text())
        hypothesis = " ".join(
            u["text"]
            for u in sorted(
                control["utterances"], key=lambda u: (u["start"], u["end"], u["speaker"])
            )
        )
        original = json.loads(
            (
                out / "pipeline" / source["dataset"] / Path(source["id"]).stem / "score.json"
            ).read_text()
        )
        rows.append(
            {
                "dataset": source["dataset"],
                "id": source["id"],
                "status": control["status"],
                "reference": source["reference_text"],
                "hypothesis": hypothesis,
                "dicow_wer": original["wer"],
                "phowhisper_wer": error_counts(source["reference_text"], hypothesis),
                "phowhisper_cer": error_counts(
                    source["reference_text"], hypothesis, characters=True
                ),
            }
        )
    groups = defaultdict(list)
    for row in rows:
        groups[row["dataset"]].append(row)
    summary = {}
    for name, items in groups.items():
        summary[name] = {"clips": len(items), "failed": sum(r["status"] != "ok" for r in items)}
        for metric in ("dicow_wer", "phowhisper_wer", "phowhisper_cer"):
            errors = sum(r[metric]["errors"] for r in items)
            units = sum(r[metric]["reference_units"] for r in items)
            summary[name][metric] = {
                "errors": errors,
                "reference_units": units,
                "rate": errors / units,
            }
    (out / "phowhisper_comparison_rows.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    )
    result = {
        "complete": True,
        "groups": summary,
        "scope": "Same production preprocessing and predicted DiariZen timeline; PhoWhisper cascaded vs DiCoW conditioned, short Vietnamese clips only.",
        "limitations": [
            "Different ASR backbones: does not isolate FDDT.",
            "Model resident and M2 reused; timing not comparable to end-to-end cold subprocess timing.",
            "No conclusion on 3+ speaker meetings or heavy overlap from these short clips.",
        ],
    }
    (out / "phowhisper_comparison_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "worker", "score"])
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args()
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("MKL_NUM_THREADS", "2")
    {"prepare": prepare, "worker": worker, "score": score}[arguments.command](
        arguments.out.resolve()
    )
