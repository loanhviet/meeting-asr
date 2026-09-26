"""Measure wall time, RTF and peak CUDA allocation with explicit cache mode."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from meeting_asr.io import _atomic_text
from meeting_asr.pipeline import dependency_versions, run_pipeline


def benchmark(audio, config, out, repetitions=1, cached=False):
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("Install inference dependencies before benchmarking") from exc
    options = copy.deepcopy(config)
    options["llm"]["enabled"] = False
    destination = Path(out)
    rows = []
    for index in range(repetitions):
        if torch.cuda.is_available():
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
                "peak_cuda_allocated_gib": torch.cuda.max_memory_allocated() / 1024**3
                if torch.cuda.is_available()
                else None,
            }
        )
    payload = {
        "audio": str(Path(audio).resolve()),
        "versions": dependency_versions(),
        "runs": rows,
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    }
    _atomic_text(destination / "benchmark.json", json.dumps(payload, indent=2))
    return payload
