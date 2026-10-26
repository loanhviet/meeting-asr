"""Freeze and evaluate a DiCoW beam grid on development recordings only."""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from pathlib import Path

from evaluate_general_meetings import collect, digest, prepare, read_rows, write_json

from meeting_asr.settings import PROJECT_ROOT, load_config


def validate_dev_rows(rows):
    if not rows or any(r.get("split") != "dev" or r.get("official_split") == "test" for r in rows):
        raise ValueError("decoding configuration selection requires development data only")
    if any(r.get("mode", "pipeline") != "pipeline" for r in rows):
        raise ValueError("decoding trials require full pipeline inputs")


def choose_candidate(candidates):
    """Apply the predeclared rule; incomplete grids cannot produce a recommendation."""
    baseline = next(c for c in candidates if c["beam"] == 1)
    for item in candidates:
        item["eligible"] = (
            item["complete"]
            and item["failed"] == 0
            and set(item["vietnamese_wer_by_dataset"]) == set(baseline["vietnamese_wer_by_dataset"])
            and all(
                rate <= baseline["vietnamese_wer_by_dataset"][name] + 1e-12
                for name, rate in item["vietnamese_wer_by_dataset"].items()
            )
            and item["ami_metrics"] is not None
            and baseline["ami_metrics"] is not None
            and item["ami_metrics"]["tcpwer"]["error_rate"]
            <= baseline["ami_metrics"]["tcpwer"]["error_rate"] + 1e-12
        )
    eligible = [c for c in candidates if c["eligible"]]
    if not all(c["complete"] for c in candidates):
        return None
    return (
        min(eligible, key=lambda c: (c["vi_macro_wer_objective"], c["beam"])) if eligible else None
    )


def freeze(manifest, out, beams):
    rows = read_rows(manifest)
    validate_dev_rows(rows)
    if 1 not in beams or len(set(beams)) != len(beams) or any(b < 1 for b in beams):
        raise ValueError("beam grid requires distinct positive counts and baseline beam 1")
    if (out / "experiment.json").exists():
        raise ValueError("experiment already frozen; use run/report to resume")
    out.mkdir(parents=True, exist_ok=True)
    for row in rows:
        for key in ("audio_path", "reference_json", "reference_rttm", "reference_uem"):
            if row.get(key):
                row[key] = str((manifest.parent / row[key]).resolve())
        if row.get("reference_json"):
            row["paper_metrics"] = True
    inputs = out / "inputs.dev.jsonl"
    inputs.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    for beam in beams:
        prepare(
            PROJECT_ROOT / "data/gold/vi_asr_v1",
            out / f"beam-{beam}",
            manifest=inputs,
            num_beams=beam,
        )
    experiment = {
        "manifest_sha256": digest(inputs),
        "original_manifest_sha256": digest(manifest),
        "beams": beams,
        "rows_per_beam": len(rows),
        "selection_split": "dev",
        "selection_rule": "Complete runs; no per-Vietnamese-dataset WER regression and "
        "no AMI dev tcpWER regression relative to beam 1. "
        "Minimize macro mean of Vietnamese dataset WERs; ties prefer fewer beams. "
        "English control excluded from the Vietnamese objective.",
        "test_used_for_selection": False,
        "training_performed": False,
        "runtime_note": "Local GPU, sequential pipeline subprocesses, offline cached weights, LLM disabled.",
    }
    write_json(out / "experiment.json", experiment)
    print(json.dumps(experiment, ensure_ascii=False), flush=True)


def run(out, only_beams):
    experiment = json.loads((out / "experiment.json").read_text())
    if digest(out / "inputs.dev.jsonl") != experiment["manifest_sha256"]:
        raise ValueError("development manifest changed after freezing")
    beams = only_beams or experiment["beams"]
    if not set(beams) <= set(experiment["beams"]):
        raise ValueError("beam count is not part of frozen experiment")
    env = os.environ.copy()
    env.update(
        MEETING_LLM_ENABLED="false",
        MEETING_DEVICE="cuda",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        OMP_NUM_THREADS="2",
        MKL_NUM_THREADS="2",
    )
    for beam in beams:
        folder = out / f"beam-{beam}"
        with (folder / "progress.log").open("a") as log:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "scripts/evaluate_general_meetings.py"),
                    "run",
                    "--out",
                    str(folder),
                ],
                cwd=PROJECT_ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        print(json.dumps({"beam": beam, "exit_code": completed.returncode}), flush=True)
        collect(folder)


def report(out):
    experiment = json.loads((out / "experiment.json").read_text())
    candidates = []
    for beam in experiment["beams"]:
        folder = out / f"beam-{beam}"
        collect(folder)
        summary = json.loads((folder / "summary.json").read_text())
        rows = read_rows(folder / "scores.jsonl")
        vi = {
            g["dataset"]: g["wer"]["rate"]
            for g in summary["groups"]
            if g["dataset"] != "ami_dev" and g["wer"] is not None
        }
        control = next((r.get("paper_metrics") for r in rows if r["dataset"] == "ami_dev"), None)
        peaks = []
        for row in rows:
            provenance = (
                folder
                / row["mode"]
                / row["dataset"]
                / Path(row["id"]).stem
                / "dicow-provenance.json"
            )
            if provenance.exists():
                value = json.loads(provenance.read_text())
                peaks.append(
                    max(
                        value["diarization_peak_cuda_allocated_bytes"],
                        value["asr_peak_cuda_allocated_bytes"],
                    )
                )
        candidates.append(
            {
                "beam": beam,
                "complete": summary["complete"],
                "failed": sum(g["failed"] for g in summary["groups"]),
                "vietnamese_wer_by_dataset": vi,
                "vi_macro_wer_objective": sum(vi.values()) / len(vi) if vi else None,
                "ami_metrics": control["metrics"] if control else None,
                "elapsed_sec": sum(r["elapsed_sec"] for r in rows),
                "audio_sec": sum(r["duration_sec"] for r in rows),
                "peak_cuda_allocated_bytes": max(peaks) if peaks else None,
            }
        )
    chosen = choose_candidate(candidates)
    value = {
        "complete": all(c["complete"] for c in candidates),
        "candidates": candidates,
        "recommended_beam": chosen["beam"] if chosen else None,
        "selection_rule": experiment["selection_rule"],
        "split": "dev",
        "test_generalization_established": False,
    }
    write_json(out / "comparison.json", value)
    if chosen:
        import yaml

        config = copy.deepcopy(load_config())
        config["runtime"]["device"] = "auto"
        config["llm"]["enabled"] = False
        config["dicow"]["num_beams"] = chosen["beam"]
        target = PROJECT_ROOT / "configs/recommended-dicow-round1.yaml"
        target.write_text(
            "# Selected on development data; general-meeting acceptance remains separate.\n"
            + yaml.safe_dump(config, allow_unicode=True)
        )
    print(json.dumps(value, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "run", "report"])
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--beams", type=int, nargs="+", default=None)
    args = parser.parse_args()
    if args.command == "prepare":
        if args.manifest is None:
            parser.error("prepare requires --manifest")
        freeze(args.manifest.resolve(), args.out.resolve(), args.beams or [1, 3, 5])
    elif args.command == "run":
        run(args.out.resolve(), args.beams)
    else:
        report(args.out.resolve())
