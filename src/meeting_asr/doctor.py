"""Read-only local readiness checks; never include credential values."""

from __future__ import annotations

import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def environment_report(config=None):
    from meeting_asr.settings import load_config

    config = load_config() if config is None else config
    versions = {}
    for package in (
        "torch",
        "torchaudio",
        "transformers",
        "pyannote.audio",
        "speechbrain",
        "silero-vad",
        "fastapi",
        "uvicorn",
        "reportlab",
    ):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    gpu, gpu_error = None, None
    try:
        import torch

        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            gpu = {"name": props.name, "memory_gib": round(props.total_memory / 1024**3, 2)}
    except (ImportError, RuntimeError, OSError) as exc:
        gpu_error = type(exc).__name__
    token = bool(os.getenv("HF_TOKEN"))
    try:
        from huggingface_hub import get_token

        token = token or bool(get_token())
    except ImportError:
        pass
    report = {
        "python": sys.version.split()[0],
        "executables": {
            name: shutil.which(name) is not None for name in ("ffmpeg", "ffprobe", "node", "npm")
        },
        "packages": versions,
        "gpu": gpu,
        "gpu_error": gpu_error,
        "hf_token_present": token,
        "model_access": "not verified",
        "llm_key_present": bool(os.getenv("MEETING_LLM_API_KEY")),
        "llm_model_configured": bool(os.getenv("MEETING_LLM_MODEL")),
        "asr_engine": config["asr"].get("engine", "whisper"),
        "asr_model": config["asr"]["model_name"],
        "diarization_backend": config["diarization"]["backend"],
    }
    if report["asr_engine"] == "dicow":
        from meeting_asr.dicow import author_runtime

        try:
            python, upstream = author_runtime(config)
            inspection = subprocess.run(
                [str(python), str(Path(__file__).with_name("dicow_runner.py")), "--inspect"],
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            )
            runtime = json.loads(inspection.stdout)
            report["dicow_runtime"] = {
                "ready": True,
                "executable": str(python),
                "upstream_dir": str(upstream),
                **runtime,
            }
            report["gpu"] = runtime["gpu"]
            report["gpu_error"] = None
            report["hf_token_present"] = token or runtime["hf_token_present"]
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            report["dicow_runtime"] = {"ready": False, "error": type(exc).__name__}
    return report
