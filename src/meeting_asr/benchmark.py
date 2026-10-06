"""Measure wall time, RTF and peak CUDA allocation with explicit cache mode."""

from __future__ import annotations

import copy
import csv
import json
import platform
from datetime import UTC, datetime
from pathlib import Path

from meeting_asr.diarization import resolve_device
from meeting_asr.evaluation.log import append_experiment_rows
from meeting_asr.io import _atomic_text
from meeting_asr.pipeline import dependency_versions, run_pipeline
from meeting_asr.runtime import file_sha256, git_commit
from meeting_asr.settings import config_hash


def benchmark(audio, config, out, repetitions=1, cached=False, log_path=None):
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("Install inference dependencies before benchmarking") from exc
    options = copy.deepcopy(config)
    options["llm"]["enabled"] = False
    destination = Path(out)
    device = resolve_device(options.get("runtime", {}).get("device", "auto"))
    use_cuda = device.startswith("cuda")
    rows = []
    for index in range(repetitions):
        if use_cuda:
            torch.cuda.reset_peak_memory_stats()
        directory = destination / f"run_{index:03d}"
        run_pipeline(audio, options, directory, no_cache=not cached)
        run = json.loads((directory / "run.json").read_text())["result"]
        rows.append(
            {
                "run": index,
                "cache_allowed": cached,
                "elapsed_sec": run["elapsed_sec"],
                "rtf": run["rtf"],
                "stages": run["stages"],
                "stage_elapsed_sec": run.get("stage_elapsed_sec", {}),
                "audio_duration_sec": run.get("audio_duration_sec"),
                "peak_cuda_allocated_gib": torch.cuda.max_memory_allocated() / 1024**3
                if use_cuda
                else None,
            }
        )
    payload = {
        "audio": str(Path(audio).resolve()),
        "audio_sha256": file_sha256(audio),
        "config_hash": config_hash(options),
        "device": device,
        "platform": platform.platform(),
        "cpu": platform.processor(),
        "versions": dependency_versions(),
        "runs": rows,
        "gpu": torch.cuda.get_device_name(0) if use_cuda else None,
    }
    _atomic_text(destination / "benchmark.json", json.dumps(payload, indent=2))
    stamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    commit = git_commit()
    append_experiment_rows(
        [
            {
                "run_id": f"{stamp}_{row['run']:03d}",
                "git_commit": commit,
                "config_hash": config_hash(options),
                "dataset": Path(audio).stem,
                "diar_backend": options["diarization"]["backend"],
                "masking": options["asr"].get("masking", "none"),
                "rtf": row["rtf"],
                "notes": "benchmark; peak allocated VRAM is not logged in this schema",
            }
            for row in rows
        ],
        log_path,
    )
    return payload


def benchmark_suite(audio_files, config, out, repetitions=1, cached=False):
    """Benchmark supplied recordings; never pad/repeat audio to imply real meetings."""
    if not audio_files:
        raise ValueError("provide at least one recording")
    destination = Path(out)
    reports = []
    for index, audio in enumerate(audio_files):
        reports.append(
            benchmark(
                audio,
                config,
                destination / f"audio_{index:03d}",
                repetitions=repetitions,
                cached=cached,
                log_path=destination / "experiments.csv",
            )
        )
        _atomic_text(destination / "suite.json", json.dumps({"recordings": reports}, indent=2))
    rows = []
    for report in reports:
        for run in report["runs"]:
            rows.append(
                {
                    "audio": report["audio"],
                    "device": report["device"],
                    "gpu": report["gpu"],
                    **{k: v for k, v in run.items() if k not in {"stages", "stage_elapsed_sec"}},
                    **{
                        f"{stage}_sec": elapsed
                        for stage, elapsed in run["stage_elapsed_sec"].items()
                    },
                }
            )
    with (destination / "suite.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted({k for row in rows for k in row}))
        writer.writeheader()
        writer.writerows(rows)
    return {"recordings": reports}
